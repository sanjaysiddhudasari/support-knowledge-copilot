"""One-time migration: upload data/raw/* into durable Supabase storage.

Runs the exact pipeline the API uses (DocumentService -> Storage + Postgres,
then index_uploaded_file -> Qdrant + manifest) but directly from this machine
against the shared cloud services. No Render, no HTTP, no login.

Usage:
    uvicorn is NOT needed. Just run from the repo root (uses your .env):
        python migrate_raw.py
"""

import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from app.ingestion.loader import (  # noqa: E402
    DocumentLoadError,
    UnsupportedFormatError,
    load_document,
)
from app.retrieval.rebuild import index_uploaded_file  # noqa: E402
from app.services.document_storage import DocumentService  # noqa: E402

RAW_DIR = Path(__file__).resolve().parent / "data" / "raw"


def _admin_user_id(service: DocumentService) -> str:
    """Any user who owns documents; prefer an admin id from profiles."""

    response = (
        service.client.table("profiles")
        .select("id, access_level")
        .eq("access_level", "admin")
        .limit(1)
        .execute()
    )

    data = getattr(response, "data", None)

    if data:
        return str(data[0]["id"])

    # Fall back to any profile so the script still works on small setups.
    response = (
        service.client.table("profiles").select("id").limit(1).execute()
    )

    return str(response.data[0]["id"])


def _existing_document(
    service: DocumentService, user_id: str, filename: str
) -> str | None:
    """Return the document id if a row already exists for this user+filename.

    The DB enforces a unique (user_id, filename), so a migration that always
    INSERTs would collide on re-run. Skipping existing rows makes the script
    idempotent: re-running just fills in whatever is still missing.
    """

    response = (
        service.client.table("documents")
        .select("id")
        .eq("user_id", user_id)
        .eq("filename", filename)
        .limit(1)
        .execute()
    )

    data = getattr(response, "data", None) or []

    return str(data[0]["id"]) if data else None


def main() -> int:
    files = sorted(
        path
        for path in RAW_DIR.iterdir()
        if path.is_file() and path.name not in {".gitkeep"}
    )

    if not files:
        print(f"No files in {RAW_DIR}")
        return 0

    service = DocumentService()
    user_id = _admin_user_id(service)

    print(f"{len(files)} files -> storage as user {user_id}")

    ok = skipped = failed = 0

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)

        for path in files:
            if _existing_document(service, user_id, path.name):
                skipped += 1
                print(f"  skip  {path.name} (already stored)")
                continue

            data = path.read_bytes()

            # Validate/parse first so unparsable files are skipped cleanly.
            try:
                loaded = load_document(str(path))
            except (UnsupportedFormatError, DocumentLoadError) as error:
                failed += 1
                print(f"  SKIP {path.name}: {error}")
                continue

            document = service.upload(
                user_id=user_id,
                filename=path.name,
                data=data,
                file_type=loaded.file_type,
            )

            # Index from the stored bytes (download via the service).
            stored = service.download(user_id, document["id"], str(tmp_dir))

            chunks = index_uploaded_file(
                stored,
                version=document["version"],
                content_hash=document["content_hash"],
            )

            service.mark_status(user_id, document["id"], "ready")

            ok += 1
            print(f"  ok   {path.name} ({len(chunks)} chunks, v{document['version']})")

    print(f"\ndone: {ok} ok, {skipped} already-stored (skipped), {failed} failed")

    # Rebuild BM25 from durable docs so the laptop-derived index is current.
    return 0


if __name__ == "__main__":
    sys.exit(main())