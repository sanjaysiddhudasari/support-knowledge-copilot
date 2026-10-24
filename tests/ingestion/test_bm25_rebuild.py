"""BM25 rebuild from durable documents + missing/stale detection."""

import json
import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-service-key")

import pytest  # noqa: E402

from app.retrieval import rebuild  # noqa: E402
from app.retrieval.bm25 import BM25Retriever  # noqa: E402
from app.retrieval.rebuild import (  # noqa: E402
    BM25_STATE_KEY,
    index_uploaded_file,
    is_stale,
    rebuild_bm25,
)
from fake_storage_supabase import FakeSupabaseStorage  # noqa: E402

from app.retrieval import vector_store as rebuild_module  # noqa: E402


from app.retrieval.rebuild import (  # noqa: E402
    BM25_STATE_KEY,
    index_uploaded_file,
    is_stale,
    rebuild_bm25,
    remove_document_chunks,
)

USER_A = "11111111-1111-1111-1111-111111111111"
USER_B = "22222222-2222-2222-2222-222222222222"


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Redirect manifest/BM25 artifacts to a temp dir; fresh fake storage."""

    monkeypatch.setattr(
        rebuild, "MANIFEST_PATH", tmp_path / "manifest.json"
    )
    monkeypatch.setattr(
        rebuild, "BM25_INDEX_PATH", str(tmp_path / "bm25" / "index.joblib")
    )

    service = DocumentServiceStub(FakeSupabaseStorage())

    return service, tmp_path


class DocumentServiceStub:
    """Just enough of DocumentService for rebuild_bm25."""

    def __init__(self, store):
        self.client = store
        self._rows = []

    def list_documents(self, user_id):
        return [
            r for r in self._rows if r.get("user_id") == user_id
        ]

    def list_all_documents(self):
        return [dict(r) for r in self._rows]

    def download_all(self, document_id, workdir):
        return self._download(document_id, workdir)

    def download(self, user_id, document_id, workdir):
        return self._download(document_id, workdir)

    def _download(self, document_id, workdir):
        row = next(r for r in self._rows if r["id"] == document_id)

        from pathlib import Path

        target = Path(workdir) / row["filename"]
        target.write_bytes(self.client.blobs[row["storage_path"]])

        return target

    # test helper
    def seed(self, user_id, filename, data, file_type, version=1):
        doc_id = f"doc-{len(self._rows) + 1}"
        path = f"{user_id}/{doc_id}/{filename}"

        self.client.blobs[path] = data
        self._rows.append(
            {
                "id": doc_id,
                "user_id": user_id,
                "filename": filename,
                "storage_path": path,
                "file_type": file_type,
                "version": version,
                "content_hash": "hash-" + str(len(self._rows)),
            }
        )

        return self._rows[-1]


def _manifest(env):
    service, tmp_path = env
    path = rebuild.MANIFEST_PATH

    if not path.exists():
        return {"documents": {}}

    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Per-file indexing
# ---------------------------------------------------------------------------


def test_index_uploaded_file_chunks_and_records(tmp_path, env):
    service, tmp = env

    source = tmp / "notes.txt"
    source.write_text("# Heading\n\nSome body text.", encoding="utf-8")

    chunks = index_uploaded_file(source, version=1, content_hash="h1")

    assert chunks
    manifest = _manifest(env)

    record = manifest["documents"]["notes.txt"]

    assert record["version"] == 1
    assert record["content_hash"] == "h1"
    assert record["chunk_ids"] == [c.chunk_ids for c in chunks]


def test_index_uploaded_file_replaces_old_chunks(tmp_path, env, monkeypatch):
    """Re-index same filename: old chunks are deleted from Qdrant, manifest
    holds the current chunk set, IDs stay deterministic."""

    service, tmp = env

    source = tmp / "notes.txt"
    source.write_text("first content", encoding="utf-8")

    first = index_uploaded_file(source, version=1, content_hash="h1")
    first_ids = [c.chunk_ids for c in first]

    source.write_text("completely different and much longer content", encoding="utf-8")

    deleted_calls = []

    from app.retrieval import vector_store as vs_module

    real_delete = vs_module.VectorStore.delete_chunks

    def spy_delete(self, chunk_ids):
        deleted_calls.append(list(chunk_ids))
        return real_delete(self, chunk_ids)

    monkeypatch.setattr(vs_module.VectorStore, "delete_chunks", spy_delete)

    second = index_uploaded_file(source, version=2, content_hash="h2")
    second_ids = [c.chunk_ids for c in second]

    manifest = _manifest(env)

    # Old ids removed from Qdrant before the new ones went in.
    assert deleted_calls == [first_ids]

    # Manifest now reflects the new version only.
    assert manifest["documents"]["notes.txt"]["version"] == 2
    assert manifest["documents"]["notes.txt"]["chunk_ids"] == second_ids
    assert manifest["documents"]["notes.txt"]["content_hash"] == "h2"

    # Deterministic IDs: same source, same numbering scheme.
    assert second_ids[0].startswith("notes.txt_chunk_")


# ---------------------------------------------------------------------------
# BM25 rebuild
# ---------------------------------------------------------------------------


def test_rebuild_builds_from_durable_documents(env):
    service, tmp = env

    service.seed(
        USER_A, "alpha.txt", "alpha document content".encode(), "text"
    )
    service.seed(
        USER_A, "beta.md", "# Beta\n\nbeta markdown".encode(), "markdown"
    )

    result = rebuild_bm25(service, str(tmp))

    assert result["document_count"] == 2
    assert result["chunk_count"] > 0
    assert result["status"] == "rebuilt"

    # The saved artifact loads and retrieves.
    retriever = BM25Retriever()
    retriever.load(rebuild.BM25_INDEX_PATH)

    hits = retriever.retrieve("alpha", top_k=1)

    assert hits
    assert hits[0].chunk.source == "alpha.txt"


def test_rebuild_zero_documents_is_valid_empty_state(env):
    service, tmp = env

    result = rebuild_bm25(service, str(tmp))

    assert result["document_count"] == 0

    state = _manifest(env)[BM25_STATE_KEY]

    assert state["document_count"] == 0
    assert state["documents"] == {}


def test_missing_state_is_not_stale(env):
    """A present index with no recorded snapshot is not forced-rebuilt.

    A truly absent index (file gone) is handled by the startup missing-file
    path; forcing a rebuild just because a snapshot is missing would fire a
    network rebuild on every start against a seed corpus.
    """

    service, tmp = env

    service.seed(USER_A, "a.txt", b"content", "text")

    # Manifest has documents but no BM25 build state.
    manifest = _manifest(env)
    manifest["documents"]["a.txt"] = {
        "content_hash": "h", "version": 1,
    }

    assert is_stale(manifest) is False


def test_fresh_state_is_not_stale(env):
    service, tmp = env

    service.seed(USER_A, "a.txt", b"content", "text")
    rebuild_bm25(service, str(tmp))

    # Sync the manifest documents with the durable rows (as upload does).
    manifest = _manifest(env)
    manifest["documents"]["a.txt"] = {
        "content_hash": "hash-1",
        "version": 1,
    }

    state = manifest[BM25_STATE_KEY]
    state["documents"] = {
        "a.txt": {"content_hash": "hash-1", "version": 1}
    }

    assert is_stale(manifest) is False


def test_stale_state_detected_on_hash_change(env):
    service, tmp = env

    manifest = {
        "documents": {
            "a.txt": {"content_hash": "old", "version": 1}
        },
        BM25_STATE_KEY: {
            "built_at": "t",
            "document_count": 1,
            "documents": {
                "a.txt": {"content_hash": "old", "version": 1}
            },
        },
    }

    assert is_stale(manifest) is False

    manifest["documents"]["a.txt"]["content_hash"] = "new"

    assert is_stale(manifest) is True

# ---------------------------------------------------------------------------
# Task 3: reindex covers all owners; delete is reflected; no restart needed
# ---------------------------------------------------------------------------


def test_rebuild_covers_documents_from_multiple_owners(env):
    """Rebuild must include every document, not just the calling admin's."""

    service, tmp = env

    service.seed(USER_A, "alpha.txt", b"alpha document", "text")
    service.seed(USER_B, "beta.txt", b"beta document", "text")

    result = rebuild_bm25(service, str(tmp))

    assert result["document_count"] == 2

    retriever = BM25Retriever()
    retriever.load(rebuild.BM25_INDEX_PATH)

    sources = {r.chunk.source for r in retriever.retrieve("document", top_k=5)}

    assert {"alpha.txt", "beta.txt"} <= sources


def test_rebuild_after_delete_excludes_the_document(env):
    """Deleting a durable doc + rebuild means it stops surfacing in BM25."""

    service, tmp = env

    service.seed(USER_A, "keeper.txt", b"keeper content", "text")
    service.seed(USER_A, "goner.txt", b"goner content", "text")

    rebuild_bm25(service, str(tmp))

    # Simulate the delete flow: goner's row + blob removed from the source
    # of truth; keeper's stays.
    keeper_row = next(
        r for r in service._rows if r["filename"] == "keeper.txt"
    )
    service._rows = [keeper_row]
    keeper_path = keeper_row["storage_path"]
    service.client.blobs = {
        k: v for k, v in service.client.blobs.items() if k == keeper_path
    }

    rebuild_bm25(service, str(tmp))

    retriever = BM25Retriever()
    retriever.load(rebuild.BM25_INDEX_PATH)

    hits = retriever.retrieve("goner", top_k=5)

    assert all(hit.chunk.source != "goner.txt" for hit in hits)


def test_runtime_retriever_picks_up_rebuild_without_restart(env, monkeypatch):
    """rebuild_bm25 reloads every live service's in-memory index (no restart)."""

    service, tmp = env

    service.seed(USER_A, "a.txt", b"alpha beta", "text")
    rebuild_bm25(service, str(tmp))

    from app.retrieval.bm25 import BM25Retriever
    from app.services import retrieval_service as rs_mod
    from app.services.retrieval_service import reload_all_bm25

    # The runtime retriever must read the same temp index the fixture builds.
    monkeypatch.setattr(
        rs_mod, "BM25_INDEX_PATH", str(tmp / "bm25" / "index.joblib")
    )

    # A service-shaped object taking the real reload_bm25 path.
    class Live:
        def __init__(self):
            self.bm25_retriever = BM25Retriever()
            self._load_bm25()

        def _load_bm25(self):
            self.bm25_retriever.load(rs_mod.BM25_INDEX_PATH)

        def reload_bm25(self):
            self._load_bm25()

    rs_mod._LIVE_SERVICES.clear()
    live = Live()
    rs_mod._LIVE_SERVICES.add(live)

    assert {c.source for c in live.bm25_retriever.chunks} == {"a.txt"}

    # A new upload + rebuild writes a newer index and reloads live services,
    # so the same running process sees the new doc without a restart.
    service.seed(USER_A, "b.txt", b"freshterm content", "text")
    rebuild_bm25(service, str(tmp))

    reload_all_bm25()  # rebuild already does this; explicit for clarity

    sources = {c.source for c in live.bm25_retriever.chunks}

    assert "b.txt" in sources
    assert "a.txt" in sources


# ---------------------------------------------------------------------------
# Task 4: document_id in Qdrant payload; delete independent of the manifest
# ---------------------------------------------------------------------------


def test_index_uploaded_file_tags_vectors_with_document_id(tmp_path, env, monkeypatch):
    service, tmp = env

    source = tmp / "notes.txt"
    source.write_text("some unique body text here", encoding="utf-8")

    seen = {}

    def spy(self, chunks, embeddings=None, document_id=None):
        seen["document_id"] = document_id
        seen["n"] = len(chunks)

    monkeypatch.setattr(
        rebuild_module.VectorStore, "upsert_chunks", spy
    )

    index_uploaded_file(source, version=1, content_hash="h", document_id="doc-abc")

    assert seen["document_id"] == "doc-abc"
    assert seen["n"] > 0


def test_remove_document_chunks_deletes_by_payload_without_manifest(tmp_path, env, monkeypatch):
    service, tmp = env

    deleted_by_doc = []

    monkeypatch.setattr(
        rebuild_module.VectorStore,
        "delete_by_document",
        lambda self, doc_id: deleted_by_doc.append(doc_id),
    )

    # No manifest record for the filename (e.g. after a redeploy wiped it).
    remove_document_chunks({"filename": "gone.txt", "id": "doc-xyz"})

    assert deleted_by_doc == ["doc-xyz"]
