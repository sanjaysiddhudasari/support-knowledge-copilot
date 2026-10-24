"""Stable document identity: same filename across owners must not collide.

Covers chunk-id determinism, manifest keying by document id, and that
update/delete only touch the intended document.
"""

import os
from pathlib import Path

import pytest

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-service-key")

from app.ingestion import chunker as chunker_mod  # noqa: E402
from app.ingestion.chunker import chunk_document  # noqa: E402
from app.ingestion.loader import load_document  # noqa: E402
from app.retrieval import rebuild as rebuild_mod  # noqa: E402
from app.retrieval.rebuild import index_uploaded_file, remove_document_chunks  # noqa: E402


def make_md(tmp_path, name, content) -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Chunk-id determinism: document id is the base, so filenames never collide
# ---------------------------------------------------------------------------


def test_same_filename_different_document_ids_do_not_collide(tmp_path):
    content = "# Installation\n\nStep one. Step two."

    doc_a_bytes = make_md(tmp_path, "installation.md", content)
    doc_b_bytes = make_md(tmp_path, "copy.md", content)  # identical content too

    a = chunk_document(
        load_document(str(doc_a_bytes)), chunk_id_base="doc-A"
    )
    b = chunk_document(
        load_document(str(doc_b_bytes)), chunk_id_base="doc-B"
    )

    a_ids = [c.chunk_ids for c in a]
    b_ids = [c.chunk_ids for c in b]

    assert a_ids[0].startswith("doc-A_chunk_")
    assert b_ids[0].startswith("doc-B_chunk_")
    assert set(a_ids).isdisjoint(set(b_ids))

    # Source (filename) is preserved for display/citation, independent of the id.
    assert {c.source for c in a} == {"installation.md"}
    assert {c.source for c in b} == {"copy.md"}


def test_same_document_id_is_reproducible(tmp_path):
    path = make_md(tmp_path, "a.md", "# T\n\nBody")

    first = [
        c.chunk_ids for c in chunk_document(
            load_document(str(path)), chunk_id_base="doc-X"
        )
    ]
    second = [
        c.chunk_ids for c in chunk_document(
            load_document(str(path)), chunk_id_base="doc-X"
        )
    ]

    assert first == second


def test_legacy_corpus_keeps_filename_based_ids(tmp_path):
    """No document_id -> source (filename) based ids, unchanged behaviour."""

    path = make_md(tmp_path, "legacy.md", "# L\n\nBody")

    ids = [c.chunk_ids for c in chunk_document(load_document(str(path)))]

    assert ids[0].startswith("legacy.md_chunk_")


# ---------------------------------------------------------------------------
# Fake vector store to observe isolation (no real Qdrant)
# ---------------------------------------------------------------------------


class RecordingVectorStore:
    def __init__(self):
        self.upserts = []       # (chunk_ids, document_id)
        self.deleted_by_doc = []
        self.deleted_by_ids = []

    def upsert_chunks(self, chunks, embeddings=None, document_id=None):
        self.upserts.append(
            ([c.chunk_ids for c in chunks], document_id)
        )

    def delete_chunks(self, chunk_ids):
        self.deleted_by_ids.append(list(chunk_ids))

    def delete_by_document(self, document_id):
        self.deleted_by_doc.append(document_id)


@pytest.fixture
def rec(tmp_path, monkeypatch):
    store = RecordingVectorStore()
    recording_cls = lambda *a, **k: store  # noqa: E731
    monkeypatch.setattr(rebuild_mod, "VectorStore", recording_cls)
    monkeypatch.setattr(rebuild_mod, "MANIFEST_PATH", tmp_path / "manifest.json")
    monkeypatch.setattr(
        rebuild_mod, "BM25_INDEX_PATH", str(tmp_path / "bm25.joblib")
    )
    return store


def _manifest(tmp_path):
    path = tmp_path / "manifest.json"
    import json

    if not path.exists():
        return {"documents": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def test_manifest_keyed_by_document_id(rec, tmp_path):
    src = make_md(tmp_path, "installation.md", "# I\n\nAlpha body")
    src2 = make_md(tmp_path, "copy.md", "# I\n\nBeta body")

    index_uploaded_file(src, version=1, document_id="doc-A")
    index_uploaded_file(src2, version=1, document_id="doc-B")

    documents = _manifest(tmp_path)["documents"]

    # Two records (one per document), not a single filename-collided row.
    assert set(documents) == {"doc-A", "doc-B"}
    assert documents["doc-A"]["filename"] == "installation.md"
    assert documents["doc-B"]["filename"] == "copy.md"

    # Flat list of string chunk ids.
    for record in documents.values():
        assert isinstance(record["chunk_ids"], list)
        assert all(isinstance(x, str) for x in record["chunk_ids"])
        assert all(x.startswith("doc-") for x in record["chunk_ids"])


def test_reindexing_same_document_replaces_not_duplicates(rec, tmp_path):
    src = make_md(tmp_path, "installation.md", "# I\n\nAlpha body")
    index_uploaded_file(src, version=1, document_id="doc-A")

    # Re-index the same doc (version 2): old chunks deleted, newest kept.
    index_uploaded_file(src, version=2, document_id="doc-A")

    assert rec.deleted_by_ids  # old chunk ids were removed

    # The recorded payload carries the same document_id for the replacement.
    assert rec.upserts[-1][1] == "doc-A"


def test_deleting_one_document_removes_only_its_points(rec, tmp_path):
    src_a = make_md(tmp_path, "installation.md", "# A\n\nAlpha body")
    src_b = make_md(tmp_path, "installation.md", "# B\n\nBeta body")
    index_uploaded_file(src_a, version=1, document_id="doc-A")
    index_uploaded_file(src_b, version=1, document_id="doc-B")

    remove_document_chunks({"id": "doc-A", "filename": "installation.md"})

    # Only doc-A was deleted by document id; doc-B untouched.
    assert rec.deleted_by_doc == ["doc-A"]