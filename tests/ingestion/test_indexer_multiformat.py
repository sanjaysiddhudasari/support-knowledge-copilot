"""Indexer tests covering discovery, incremental versioning and deletion for
every supported format. Vector store and BM25 are replaced with in-memory
fakes so no Qdrant/BM25 side effects or network calls occur.
"""

import json
from pathlib import Path

import pytest

from pdf_factory import write_docx, write_pdf

from app.retrieval import indexer as indexer_module
from app.retrieval.indexer import Indexer


class FakeVectorStore:
    def __init__(self):
        self.created = 0
        self.upserted = []
        self.deleted = []

    def create_collection(self):
        self.created += 1

    def upsert_chunks(self, chunks, embeddings=None):
        self.upserted.append(list(chunks))

    def delete_chunks(self, chunk_ids):
        self.deleted.append(list(chunk_ids))


class FakeBM25:
    def __init__(self):
        self.chunks = None
        self.saved_to = None

    def build_index(self, chunks):
        self.chunks = list(chunks)

    def save(self, path):
        self.saved_to = path


@pytest.fixture
def indexer(tmp_path, monkeypatch):
    monkeypatch.setattr(indexer_module, "VectorStore", FakeVectorStore)
    monkeypatch.setattr(indexer_module, "BM25Retriever", FakeBM25)
    monkeypatch.setattr(
        indexer_module,
        "BM25_INDEX_PATH",
        str(tmp_path / "bm25.joblib"),
    )
    # Force the cloud branch so no local SentenceTransformer is imported.
    monkeypatch.setenv("QDRANT_URL", "http://qdrant.invalid")
    monkeypatch.setenv("QDRANT_API_KEY", "test-key")

    return Indexer(manifest_path=tmp_path / "manifest.json")


def read_manifest(indexer) -> dict:
    return json.loads(
        indexer.manifest_path.read_text(encoding="utf-8")
    )


def make_corpus(directory: Path) -> None:
    (directory / "a.txt").write_text(
        "Plain text document.", encoding="utf-8"
    )
    write_pdf(
        directory / "b.pdf",
        ["First page text.", "Second page text."],
    )
    write_docx(
        directory / "c.docx",
        [("heading1", "Overview"), ("paragraph", "Word body.")],
    )
    (directory / "d.html").write_text(
        "<h1>Web</h1><p>HTML body.</p>", encoding="utf-8"
    )
    (directory / "e.md").write_text(
        "# Markdown\n\nMarkdown body.", encoding="utf-8"
    )
    (directory / "f.htm").write_text(
        "<h1>Alt</h1><p>Htm body.</p>", encoding="utf-8"
    )


def test_discovery_covers_all_supported_and_ignores_others(indexer, tmp_path):
    make_corpus(tmp_path)
    (tmp_path / "ignored.csv").write_text("a,b", encoding="utf-8")
    (tmp_path / "ignored.png").write_bytes(b"\x89PNG")
    (tmp_path / "ignored.pptx").write_bytes(b"pk")

    names = [path.name for path in indexer._discover_files(tmp_path)]

    assert names == ["a.txt", "b.pdf", "c.docx", "d.html", "e.md", "f.htm"]


def test_get_changes_detects_new_files_for_all_formats(indexer, tmp_path):
    make_corpus(tmp_path)

    changes = indexer._get_changes(tmp_path)

    assert {p.name for p in changes["new"]} == {
        "a.txt",
        "b.pdf",
        "c.docx",
        "d.html",
        "e.md",
        "f.htm",
    }
    assert changes["modified"] == []
    assert changes["unchanged"] == []
    assert changes["deleted"] == []


def test_incremental_versioning_and_deletion(indexer, tmp_path):
    make_corpus(tmp_path)

    # --- new documents -------------------------------------------------
    indexer.index_incremental(directory=str(tmp_path))

    manifest = read_manifest(indexer)["documents"]

    assert set(manifest) == {
        "a.txt",
        "b.pdf",
        "c.docx",
        "d.html",
        "e.md",
        "f.htm",
    }
    assert manifest["a.txt"]["version"] == 1
    assert manifest["a.txt"]["chunk_ids"] == ["a.txt_chunk_1"]
    assert manifest["a.txt"]["file_type"] == "text"
    assert manifest["b.pdf"]["chunk_ids"] == [
        "b.pdf_chunk_1",
        "b.pdf_chunk_2",
    ]
    assert manifest["b.pdf"]["file_type"] == "pdf"
    assert manifest["c.docx"]["file_type"] == "docx"
    assert manifest["d.html"]["file_type"] == "html"

    old_pdf_chunks = list(manifest["b.pdf"]["chunk_ids"])

    vector_store = indexer.vector_store
    assert vector_store.deleted == []
    assert sum(len(batch) for batch in vector_store.upserted) == 7

    # --- unchanged run does nothing ------------------------------------
    indexer.index_incremental(directory=str(tmp_path))

    after_unchanged = read_manifest(indexer)["documents"]

    assert after_unchanged["b.pdf"]["version"] == 1
    assert vector_store.deleted == []
    assert sum(len(batch) for batch in vector_store.upserted) == 7

    # --- modified PDF bumps version and replaces chunks ----------------
    write_pdf(
        tmp_path / "b.pdf",
        ["Updated page one.", "Updated page two."],
    )

    indexer.index_incremental(directory=str(tmp_path))

    after_modified = read_manifest(indexer)["documents"]

    assert after_modified["b.pdf"]["version"] == 2
    # Old chunk IDs were deleted before re-indexing.
    assert vector_store.deleted[-1] == old_pdf_chunks
    # Re-indexed chunks use the new version.
    new_pdf_chunks = [
        chunk
        for batch in vector_store.upserted[-1:]
        for chunk in batch
        if chunk.source == "b.pdf"
    ]
    assert new_pdf_chunks
    assert {chunk.version for chunk in new_pdf_chunks} == {2}
    # Other documents keep version 1.
    assert after_modified["a.txt"]["version"] == 1

    # --- deleted document removes chunks and manifest record -----------
    (tmp_path / "c.docx").unlink()
    removed_chunks = list(after_modified["c.docx"]["chunk_ids"])

    indexer.index_incremental(directory=str(tmp_path))

    after_delete = read_manifest(indexer)["documents"]

    assert "c.docx" not in after_delete
    assert removed_chunks
    assert removed_chunks in vector_store.deleted


def test_reindexing_reproduces_identical_chunk_ids(indexer, tmp_path):
    write_pdf(
        tmp_path / "b.pdf",
        ["Stable page one.", "Stable page two."],
    )

    first = indexer._load_chunks(tmp_path / "b.pdf", version=1)
    second = indexer._load_chunks(tmp_path / "b.pdf", version=1)

    assert [c.chunk_ids for c in first] == [c.chunk_ids for c in second]
    assert [c.text for c in first] == [c.text for c in second]


def test_existing_markdown_manifest_record_is_not_invalidated(
    indexer, tmp_path
):
    path = tmp_path / "legacy.md"
    path.write_text("# Legacy\n\nUnchanged body.", encoding="utf-8")

    chunk_ids = indexer._load_chunks(path, version=1)
    ids = [chunk.chunk_ids for chunk in chunk_ids]

    indexer.manifest_path.write_text(
        json.dumps(
            {
                "documents": {
                    "legacy.md": {
                        "content_hash": indexer._calculate_hash(path),
                        "chunk_ids": ids,
                        "version": 1,
                    }
                }
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    changes = indexer._get_changes(tmp_path)

    assert [p.name for p in changes["unchanged"]] == ["legacy.md"]
    assert changes["new"] == []
    assert changes["modified"] == []

    indexer.index_incremental(directory=str(tmp_path))

    manifest = read_manifest(indexer)["documents"]

    assert manifest["legacy.md"]["version"] == 1
    assert manifest["legacy.md"]["chunk_ids"] == ids
    assert indexer.vector_store.upserted == []
    assert indexer.vector_store.deleted == []
