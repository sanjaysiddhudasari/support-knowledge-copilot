"""DocumentService: storage paths, sanitization, ownership, partial failure."""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-service-key")

import pytest  # noqa: E402

from app.services.document_storage import (  # noqa: E402
    DocumentError,
    DocumentNotFound,
    DocumentService,
    sanitize_filename,
    storage_path,
)
from fake_storage_supabase import FakeSupabaseStorage  # noqa: E402

USER_A = "11111111-1111-1111-1111-111111111111"
USER_B = "22222222-2222-2222-2222-222222222222"


@pytest.fixture
def service():
    return DocumentService(FakeSupabaseStorage())


# ---------------------------------------------------------------------------
# Filename sanitization / paths
# ---------------------------------------------------------------------------


def test_sanitize_strips_traversal_and_characters():
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("..\\evil.txt") == "evil.txt"
    assert sanitize_filename("my doc (v2).pdf") == "my_doc_v2_.pdf" or (
        sanitize_filename("my doc (v2).pdf").startswith("my_doc")
    )
    assert sanitize_filename("clean.md") == "clean.md"


def test_sanitize_rejects_empty():
    for bad in ("", ".", "..", None):
        with pytest.raises(DocumentError):
            sanitize_filename(bad)

    # Whitespace-only collapses to a safe placeholder rather than raising.
    assert sanitize_filename("   ") == "document"


def test_storage_path_is_user_document_scoped(service):
    path = storage_path(USER_A, "doc-1", "../../secret report.pdf")

    assert path == f"{USER_A}/doc-1/secret_report.pdf"
    assert ".." not in path


# ---------------------------------------------------------------------------
# Upload / metadata
# ---------------------------------------------------------------------------


def test_upload_stores_blob_and_row(service):
    row = service.upload(
        USER_A, "manual.pdf", b"%PDF-bytes", file_type="pdf"
    )

    assert row["filename"] == "manual.pdf"
    assert row["file_type"] == "pdf"
    assert row["size_bytes"] == len(b"%PDF-bytes")
    assert row["version"] == 1
    assert row["status"] == "pending"
    assert row["storage_path"].startswith(f"{USER_A}/")
    assert row["id"] in row["storage_path"]

    blob = service.client.blobs[row["storage_path"]]

    assert blob == b"%PDF-bytes"


def test_upload_creates_stable_document_id_not_filename_identity(service):
    first = service.upload(USER_A, "a.md", b"one", file_type="markdown")
    second = service.upload(USER_A, "a.md", b"two", file_type="markdown")

    # Different document ids: the same filename is a new document revision,
    # not a blob collision.
    assert first["id"] != second["id"]
    assert first["storage_path"] != second["storage_path"]


def test_upload_failure_leaves_no_orphaned_blob():
    class ExplodingTable:
        def __init__(self, store):
            self.store = store

        def select(self, *a, **k):
            return self

        def insert(self, payload):
            raise RuntimeError("db down")

        def execute(self):
            return None

    store = FakeSupabaseStorage()
    store.table = lambda name: ExplodingTable(store)

    service = DocumentService(store)

    with pytest.raises(Exception):
        service.upload(USER_A, "x.txt", b"data", file_type="text")

    assert store.blobs == {}, "orphaned Storage blob after DB failure"


# ---------------------------------------------------------------------------
# Ownership
# ---------------------------------------------------------------------------


def test_foreign_document_is_not_found(service):
    row = service.upload(USER_B, "theirs.txt", b"data", file_type="text")

    for call in (
        lambda: service.get_document(USER_A, row["id"]),
        lambda: service.download(USER_A, row["id"], "."),
        lambda: service.delete_document(USER_A, row["id"]),
        lambda: service.mark_status(USER_A, row["id"], "ready"),
    ):
        with pytest.raises(DocumentNotFound):
            call()


def test_list_documents_scoped_to_user(service):
    service.upload(USER_A, "mine.txt", b"a", file_type="text")
    service.upload(USER_B, "theirs.txt", b"b", file_type="text")

    names = [row["filename"] for row in service.list_documents(USER_A)]

    assert names == ["mine.txt"]


# ---------------------------------------------------------------------------
# Version / hash / status
# ---------------------------------------------------------------------------


def test_replace_content_bumps_version_and_hash(service):
    row = service.upload(USER_A, "doc.txt", b"v1", file_type="text")
    original_hash = row["content_hash"]

    updated = service.replace_content(
        USER_A, row["id"], b"v2-longer", file_type="text"
    )

    assert updated["version"] == 2
    assert updated["content_hash"] != original_hash
    assert updated["id"] == row["id"]


def test_mark_status(service):
    row = service.upload(USER_A, "doc.txt", b"data", file_type="text")

    service.mark_status(USER_A, row["id"], "ready")

    assert service.get_document(USER_A, row["id"])["status"] == "ready"


# ---------------------------------------------------------------------------
# Download / delete
# ---------------------------------------------------------------------------


def test_download_writes_original_bytes(service, tmp_path):
    row = service.upload(USER_A, "guide.pdf", b"%PDF-1.4 test", file_type="pdf")

    target = service.download(USER_A, row["id"], str(tmp_path))

    assert target.read_bytes() == b"%PDF-1.4 test"
    assert target.name == "guide.pdf"


def test_delete_removes_row_and_blob(service, tmp_path):
    row = service.upload(USER_A, "gone.txt", b"data", file_type="text")

    deleted = service.delete_document(USER_A, row["id"])

    assert deleted["id"] == row["id"]
    assert service.list_documents(USER_A) == []
    assert row["storage_path"] not in service.client.blobs