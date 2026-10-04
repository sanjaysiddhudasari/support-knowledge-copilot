"""Upload/documents endpoints: validation, persistence, ownership, failures.

DocumentService is replaced with an in-memory fake (real loaders still run),
and the derived-index path is stubbed so no Qdrant/BM25 state is touched.
"""

import os
from pathlib import Path

import pytest

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-service-key")

from fastapi.testclient import TestClient  # noqa: E402

from pdf_factory import build_pdf_bytes  # noqa: E402

from app.api import ingestion as ingestion_api  # noqa: E402
from app.api.ingestion import get_document_service  # noqa: E402
from app.auth.dependencies import get_current_user  # noqa: E402
from app.auth.models import User  # noqa: E402
from app.main import app  # noqa: E402
from app.retrieval import rebuild as rebuild_module  # noqa: E402
from fake_storage_supabase import FakeSupabaseStorage  # noqa: E402

ADMIN = User(id="1", email="admin@example.com", access_level="admin")
VIEWER = User(id="2", email="viewer@example.com", access_level="public")


class FakeService:
    """DocumentService against FakeSupabaseStorage, plus upload bookkeeping."""

    def __init__(self):
        self.store = FakeSupabaseStorage()
        self.indexed = []
        self.statuses = []
        self.fail_indexing = False

    # real-surface methods used by the API
    def upload(self, user_id, filename, data, file_type):
        import uuid

        from app.services.document_storage import (
            content_hash_bytes,
            sanitize_filename,
            storage_path,
        )

        clean = sanitize_filename(filename)
        document_id = str(uuid.uuid4())
        path = storage_path(user_id, document_id, clean)

        self.store.blobs[path] = bytes(data)

        payload = {
            "id": document_id,
            "user_id": user_id,
            "filename": clean,
            "storage_path": path,
            "file_type": file_type,
            "size_bytes": len(data),
            "content_hash": content_hash_bytes(data),
            "version": 1,
            "status": "pending",
        }

        self.store.rows("documents").append(payload)

        return dict(payload)

    def download(self, user_id, document_id, workdir):
        row = next(
            r for r in self.store.rows("documents") if r["id"] == document_id
        )

        target = Path(workdir) / row["filename"]
        target.write_bytes(self.store.blobs[row["storage_path"]])

        return target

    def mark_status(self, user_id, document_id, status):
        row = next(
            r for r in self.store.rows("documents") if r["id"] == document_id
        )
        row["status"] = status
        self.statuses.append((row["filename"], status))

        return dict(row)

    def list_documents(self, user_id):
        return [
            dict(r)
            for r in self.store.rows("documents")
            if r["user_id"] == user_id
        ]

    def get_document(self, user_id, document_id):
        row = next(
            (
                r
                for r in self.store.rows("documents")
                if r["id"] == document_id
            ),
            None,
        )

        if row is None or row["user_id"] != user_id:
            from app.services.document_storage import DocumentNotFound

            raise DocumentNotFound(document_id)

        return dict(row)

    def delete_document(self, user_id, document_id):
        row = self.get_document(user_id, document_id)

        self.store.rows("documents").remove(
            next(
                r
                for r in self.store.rows("documents")
                if r["id"] == document_id
            )
        )
        self.store.blobs.pop(row["storage_path"], None)

        return row


@pytest.fixture
def env(monkeypatch, tmp_path):
    service = FakeService()

    monkeypatch.setattr(rebuild_module, "MANIFEST_PATH", tmp_path / "m.json")
    monkeypatch.setattr(
        rebuild_module, "BM25_INDEX_PATH", str(tmp_path / "bm25.joblib")
    )

    def fake_index(path, version, content_hash):
        if service.fail_indexing:
            raise RuntimeError("qdrant down")

        service.indexed.append((path.name, version))

        # Minimal manifest record, as index_uploaded_file would write.
        import json

        manifest_path = rebuild_module.MANIFEST_PATH
        manifest = {"documents": {}}

        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        manifest["documents"][path.name] = {
            "content_hash": content_hash,
            "chunk_ids": [f"{path.name}_chunk_1"],
            "version": version,
        }
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        return []

    monkeypatch.setattr(
        rebuild_module, "index_uploaded_file", fake_index
    )

    app.dependency_overrides[get_current_user] = lambda: ADMIN
    app.dependency_overrides[get_document_service] = lambda: service

    with TestClient(app) as client:
        yield client, service

    app.dependency_overrides.clear()


def upload(client, filename, content, content_type="application/octet-stream"):
    return client.post(
        "/api/documents/upload",
        files={"file": (filename, content, content_type)},
    )


# ---------------------------------------------------------------------------
# Validation (unchanged rules, backend-enforced)
# ---------------------------------------------------------------------------


def test_upload_txt_roundtrip(env):
    client, service = env

    response = upload(client, "notes.txt", b"Hello plain text.")

    assert response.status_code == 200

    body = response.json()

    assert body["status"] == "success"
    assert body["file_type"] == "text"
    assert body["document_id"]

    assert service.indexed == [("notes.txt", 1)]
    assert service.statuses[-1] == ("notes.txt", "ready")


def test_upload_pdf_roundtrip(env):
    client, service = env

    response = upload(
        client, "guide.pdf", build_pdf_bytes(["Real page text"]), "application/pdf"
    )

    assert response.status_code == 200
    assert response.json()["file_type"] == "pdf"


def test_unsupported_extension_rejected(env):
    client, service = env

    response = upload(client, "data.csv", b"a,b,c")

    assert response.status_code == 400
    assert "Supported formats" in response.json()["detail"]
    assert service.store.rows("documents") == []
    assert service.store.blobs == {}


def test_empty_upload_rejected(env):
    client, service = env

    response = upload(client, "empty.txt", b"")

    assert response.status_code == 400
    assert service.store.rows("documents") == []


def test_oversize_upload_rejected(env, monkeypatch):
    client, service = env

    monkeypatch.setattr(ingestion_api, "MAX_UPLOAD_BYTES", 16)

    response = upload(client, "big.txt", b"x" * 64)

    assert response.status_code == 413
    assert service.store.rows("documents") == []


def test_scanned_pdf_rejected_before_storage(env):
    client, service = env

    response = upload(
        client, "scan.pdf", build_pdf_bytes([""], include_text=False)
    )

    assert response.status_code == 400
    assert "OCR" in response.json()["detail"]
    # Nothing stored, nothing indexed.
    assert service.store.rows("documents") == []
    assert service.store.blobs == {}


def test_legacy_post_documents_still_works(env):
    client, service = env

    response = client.post(
        "/api/documents",
        files={"file": ("legacy.txt", b"content", "text/plain")},
    )

    assert response.status_code == 200
    assert service.indexed == [("legacy.txt", 1)]


# ---------------------------------------------------------------------------
# Failure handling
# ---------------------------------------------------------------------------


def test_indexing_failure_marks_failed_and_reports(env):
    client, service = env
    service.fail_indexing = True

    response = upload(client, "bad.txt", b"content")

    assert response.status_code == 500
    assert "indexing failed" in response.json()["detail"].lower()
    assert service.statuses[-1] == ("bad.txt", "failed")
    # The document itself is durably stored; only indexing failed.
    assert len(service.store.rows("documents")) == 1


def test_storage_failure_reports_503(monkeypatch, env):
    client, service = env

    from app.services.document_storage import DocumentError

    def broken_upload(*args, **kwargs):
        raise DocumentError("storage unavailable")

    monkeypatch.setattr(service, "upload", broken_upload)

    response = upload(client, "x.txt", b"content")

    assert response.status_code == 503
    assert "storage" in response.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Ownership
# ---------------------------------------------------------------------------


def test_document_list_is_per_user(env):
    client, service = env

    upload(client, "mine.txt", b"mine")

    app.dependency_overrides[get_current_user] = lambda: VIEWER

    theirs = client.get("/api/documents")

    assert theirs.json() == []

    app.dependency_overrides[get_current_user] = lambda: ADMIN

    mine = client.get("/api/documents")

    assert [row["filename"] for row in mine.json()] == ["mine.txt"]


def test_viewer_cannot_upload(env):
    client, _ = env

    app.dependency_overrides[get_current_user] = lambda: VIEWER

    response = upload(client, "nope.txt", b"content")

    # Upload stays admin-gated as before.
    assert response.status_code == 403


def test_foreign_document_is_404(env):
    client, service = env

    created = upload(client, "a.txt", b"data").json()

    app.dependency_overrides[get_current_user] = lambda: VIEWER

    got = client.get(f"/api/documents/{created['document_id']}")
    deleted = client.delete(f"/api/documents/{created['document_id']}")

    assert got.status_code == 404
    assert deleted.status_code == 404


def test_delete_removes_document(env):
    client, service = env

    created = upload(client, "doomed.txt", b"data").json()

    response = client.delete(f"/api/documents/{created['document_id']}")

    assert response.status_code == 200
    assert service.list_documents("1") == []
    assert service.store.blobs == {}


def test_get_document_metadata(env):
    client, _ = env

    created = upload(client, "meta.txt", b"abc").json()

    response = client.get(f"/api/documents/{created['document_id']}")

    assert response.status_code == 200

    body = response.json()

    assert body["filename"] == "meta.txt"
    assert body["size_bytes"] == 3
    assert body["version"] == 1
    assert body["status"] == "ready"
    assert body["content_hash"]
