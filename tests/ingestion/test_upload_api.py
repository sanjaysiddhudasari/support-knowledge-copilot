"""Upload endpoint validation tests.

The indexer is replaced with a no-op fake and the raw directory is redirected
to a temp folder, so these tests never touch Qdrant, BM25 or the real corpus.
"""

import os
from pathlib import Path

import pytest

# The auth client requires these to be present at import time.
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-service-key")

from fastapi.testclient import TestClient  # noqa: E402

from pdf_factory import build_pdf_bytes  # noqa: E402

from app.api import ingestion as ingestion_api  # noqa: E402
from app.auth.dependencies import get_current_user  # noqa: E402
from app.auth.models import User  # noqa: E402
from app.main import app  # noqa: E402
from app.retrieval import indexer as indexer_module  # noqa: E402


ADMIN = User(id="1", email="admin@example.com", access_level="admin")
VIEWER = User(id="2", email="viewer@example.com", access_level="public")


class FakeIndexer:
    def __init__(self):
        self.calls = []

    def index_incremental(self, directory=None):
        self.calls.append(directory)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(ingestion_api, "RAW_DIR", tmp_path)

    fake = FakeIndexer()
    monkeypatch.setattr(
        indexer_module,
        "Indexer",
        lambda *args, **kwargs: fake,
    )

    app.dependency_overrides[get_current_user] = lambda: ADMIN

    with TestClient(app) as client:
        yield client, tmp_path, fake

    app.dependency_overrides.clear()


def upload(client, filename, content, content_type="application/octet-stream"):
    return client.post(
        "/api/documents",
        files={"file": (filename, content, content_type)},
    )


def test_upload_txt_succeeds(env):
    client, raw_dir, fake = env

    response = upload(client, "notes.txt", b"Hello plain text.")

    assert response.status_code == 200
    assert response.json()["filename"] == "notes.txt"
    assert (raw_dir / "notes.txt").exists()
    assert fake.calls == [str(raw_dir)]


def test_upload_pdf_succeeds(env):
    client, raw_dir, _ = env

    payload = build_pdf_bytes(["Real page text"])

    response = upload(client, "guide.pdf", payload, "application/pdf")

    assert response.status_code == 200
    assert (raw_dir / "guide.pdf").exists()


def test_unsupported_extension_rejected(env):
    client, raw_dir, fake = env

    response = upload(client, "data.csv", b"a,b,c")

    assert response.status_code == 400
    assert "Supported formats" in response.json()["detail"]
    assert not (raw_dir / "data.csv").exists()
    assert fake.calls == []


def test_empty_upload_rejected(env):
    client, _, fake = env

    response = upload(client, "empty.txt", b"")

    assert response.status_code == 400
    assert fake.calls == []


def test_oversize_upload_rejected(env, monkeypatch):
    client, raw_dir, fake = env

    monkeypatch.setattr(ingestion_api, "MAX_UPLOAD_BYTES", 16)

    response = upload(client, "big.txt", b"x" * 64)

    assert response.status_code == 413
    assert not (raw_dir / "big.txt").exists()
    assert fake.calls == []


def test_scanned_pdf_rejected_and_not_kept(env):
    client, raw_dir, fake = env

    payload = build_pdf_bytes([""], include_text=False)

    response = upload(client, "scan.pdf", payload, "application/pdf")

    assert response.status_code == 400
    assert "OCR" in response.json()["detail"]
    # The malformed/unusable file must not poison the corpus.
    assert not (raw_dir / "scan.pdf").exists()
    assert fake.calls == []


def test_path_traversal_filename_is_sanitized(env):
    client, raw_dir, _ = env

    response = upload(client, "../../evil.txt", b"content")

    assert response.status_code == 200
    assert (raw_dir / "evil.txt").exists()
    assert not (raw_dir.parent.parent / "evil.txt").exists()


def test_non_admin_forbidden(env):
    client, _, fake = env

    app.dependency_overrides[get_current_user] = lambda: VIEWER

    response = upload(client, "notes.txt", b"Hello")

    assert response.status_code == 403
    assert fake.calls == []
