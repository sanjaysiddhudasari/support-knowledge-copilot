"""Durable document storage: Supabase Storage for original bytes, Postgres for
metadata.

Free of FastAPI/Streamlit so it is unit-testable against a fake client. The
existing ingestion pipeline (loaders -> chunk_document -> Indexer) is reused
untouched; this module only replaces "the file lives on Render's disk" with
"the file lives in Supabase Storage and is downloaded to a temp dir to index".
"""

from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path
from typing import Any

from app.auth.client import supabase_admin

BUCKET = "documents"
DEFAULT_ACCESS_LEVEL = "public"


class DocumentError(Exception):
    """Generic storage/metadata failure."""


class DocumentNotFound(DocumentError):
    pass


class DocumentAccessDenied(DocumentError):
    pass


# ------------------------------------------------------------------
# helpers
# ------------------------------------------------------------------


def sanitize_filename(name: str) -> str:
    """Bare filename, path traversal removed, restricted to safe characters."""

    bare = Path(name or "").name

    if not bare or bare in {".", ".."}:
        raise DocumentError("Filename is required.")

    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", bare).strip("._") or "document"

    return cleaned


def storage_path(user_id: str, document_id: str, filename: str) -> str:
    """Deterministic, user/document-scoped path: no traversal possible."""

    return f"{user_id}/{document_id}/{sanitize_filename(filename)}"


def content_hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _row(response: Any) -> dict | None:
    data = getattr(response, "data", None)

    if data is None:
        return None

    if isinstance(data, list):
        return data[0] if data else None

    return data


def _rows(response: Any) -> list[dict]:
    data = getattr(response, "data", None)

    if data is None:
        return []

    return list(data) if isinstance(data, list) else [data]


# ------------------------------------------------------------------
# service
# ------------------------------------------------------------------


class DocumentService:
    """Original bytes -> Storage; metadata -> Postgres ``documents`` table."""

    def __init__(
        self,
        client: Any | None = None,
        bucket: str | None = None,
    ):
        self._client = client if client is not None else supabase_admin
        self._bucket = bucket or BUCKET

    @property
    def client(self):
        return self._client

    # -- ownership ---------------------------------------------------------

    def _owned(self, user_id: str, document_id: str) -> dict:
        """Fetch the row only when it belongs to ``user_id``."""

        response = (
            self._client.table("documents")
            .select("*")
            .eq("id", document_id)
            .execute()
        )

        row = _row(response)

        if row is None or str(row.get("user_id")) != str(user_id):
            # Same answer for missing and foreign: no existence leak.
            raise DocumentNotFound(document_id)

        return row

    # -- create ------------------------------------------------------------

    def upload(
        self,
        user_id: str,
        filename: str,
        data: bytes,
        file_type: str,
        access_level: str = DEFAULT_ACCESS_LEVEL,
    ) -> dict:
        """Store the original bytes and create the metadata row.

        Order matters: Storage first, metadata second, with cleanup on
        metadata failure so no orphaned blob is left behind.
        """

        clean_name = sanitize_filename(filename)

        # Same (user_id, filename) = a new revision, not a duplicate row
        # (the DB enforces a unique constraint). Overwrite the blob at the
        # SAME storage path and bump the version, so re-uploading a file the
        # user already sent updates it instead of 500ing.
        existing = self.find_by_filename(user_id, clean_name)

        if existing is not None:
            return self._overwrite_current(
                existing, clean_name, data, file_type
            )

        document_id = str(uuid.uuid4())
        path = storage_path(user_id, document_id, clean_name)

        # Storage upload
        self._client.storage.from_(self._bucket).upload(
            path,
            data,
            {"content-type": "application/octet-stream"},
        )

        # Metadata row; on failure, remove the just-uploaded object.
        payload = {
            "id": document_id,
            "user_id": user_id,
            "filename": clean_name,
            "storage_path": path,
            "file_type": file_type,
            "size_bytes": len(data),
            "content_hash": content_hash_bytes(data),
            "version": 1,
            "access_level": access_level,
            "status": "pending",
        }

        try:
            response = (
                self._client.table("documents")
                .insert(payload)
                .execute()
            )
        except Exception:
            try:
                self._client.storage.from_(self._bucket).remove([path])
            except Exception:
                pass  # recoverable: orphaned blob, no false DB record
            raise

        return _row(response) or payload

    def find_by_filename(
        self, user_id: str, filename: str
    ) -> dict | None:
        """Metadata row for a user's filename, or None."""

        response = (
            self._client.table("documents")
            .select("*")
            .eq("user_id", user_id)
            .eq("filename", sanitize_filename(filename))
            .limit(1)
            .execute()
        )

        return _row(response)

    def _overwrite_current(
        self,
        existing: dict,
        filename: str,
        data: bytes,
        file_type: str,
    ) -> dict:
        """Replace the bytes and bump the version of an existing document.

        Keeps the same document id and storage path so no orphan blob is left
        and historical references (chunk ids, citations) stay stable; only the
        content hash, size, type, version and status move forward.
        """

        path = existing["storage_path"]

        self._client.storage.from_(self._bucket).update(path, data)

        payload = {
            "content_hash": content_hash_bytes(data),
            "size_bytes": len(data),
            "file_type": file_type,
            "version": int(existing.get("version") or 1) + 1,
            "status": "pending",
        }

        response = (
            self._client.table("documents")
            .update(payload)
            .eq("id", existing["id"])
            .execute()
        )

        return _row(response) or {**existing, **payload}

    # -- reads ---------------------------------------------------------------

    def list_documents(self, user_id: str) -> list[dict]:
        response = (
            self._client.table("documents")
            .select("*")
            .eq("user_id", user_id)
            .order("updated_at", desc=True)
            .execute()
        )

        return _rows(response)

    def get_document(self, user_id: str, document_id: str) -> dict:
        return self._owned(user_id, document_id)

    # -- download ------------------------------------------------------------

    def download(self, user_id: str, document_id: str, destination_dir: str) -> Path:
        """Download the original bytes into a temp dir; returns the temp file.

        The caller removes the file (and dir) after indexing.
        """

        row = self._owned(user_id, document_id)

        blob = (
            self._client.storage.from_(self._bucket)
            .download(row["storage_path"])
        )

        directory = Path(destination_dir)
        directory.mkdir(parents=True, exist_ok=True)

        target = directory / row["filename"]
        target.write_bytes(blob)

        return target

    # -- update / delete -----------------------------------------------------

    def replace_content(
        self,
        user_id: str,
        document_id: str,
        data: bytes,
        file_type: str,
    ) -> dict:
        """Same document_id, new bytes: hash/version/status move forward."""

        row = self._owned(user_id, document_id)

        payload = {
            "content_hash": content_hash_bytes(data),
            "size_bytes": len(data),
            "file_type": file_type,
            "version": int(row.get("version") or 1) + 1,
            "status": "pending",
        }

        response = (
            self._client.table("documents")
            .update(payload)
            .eq("id", document_id)
            .execute()
        )

        return _row(response) or {**row, **payload}

    def mark_status(self, user_id: str, document_id: str, status: str) -> dict:
        self._owned(user_id, document_id)

        response = (
            self._client.table("documents")
            .update({"status": status})
            .eq("id", document_id)
            .execute()
        )

        return _row(response) or {"id": document_id, "status": status}

    def delete_document(self, user_id: str, document_id: str) -> dict:
        """Delete metadata first, then the blob (cleanup best effort)."""

        row = self._owned(user_id, document_id)

        (
            self._client.table("documents")
            .delete()
            .eq("id", document_id)
            .execute()
        )

        try:
            self._client.storage.from_(self._bucket).remove(
                [row["storage_path"]]
            )
        except Exception:
            pass  # orphaned blob; metadata + chunks are already gone

        return row
