"""Upload the Northstar test fixtures through the real ingest pipeline.

Stores each file in Supabase Storage, writes metadata to Postgres, indexes
into Qdrant, and rebuilds BM25 - identical to the app's upload flow, but run
from this machine against your configured cloud services. Honours the parsed
access level (MD frontmatter), so the public/admin fixtures keep their levels.

Run:  python test-fixtures/company-knowledge/_upload_fixtures.py
      (uses .env; requires the deployed/configured Supabase + Qdrant)
"""

import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv

repo = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo))
sys.path.insert(0, str(repo / "tests" / "ingestion"))

load_dotenv()

from app.ingestion.loader import load_document  # noqa: E402
from app.retrieval.rebuild import index_uploaded_file, rebuild_bm25  # noqa: E402
from app.services.document_storage import DocumentService  # noqa: E402

HERE = Path(__file__).resolve().parent
FILES = [
    HERE / "acmecloud_travel_expenses.pdf",
    HERE / "acmecloud_vendor_onboarding.docx",
    HERE / "acmecloud_laptop_provisioning.md",
    HERE / "acmecloud_incident_communications.txt",
    HERE / "acmecloud_change_management.md",
    HERE / "acmecloud_support_handoff.html",
]


def admin_user_id(service: DocumentService) -> str:
    resp = service.client.table("profiles").select("id").eq(
        "access_level", "admin"
    ).limit(1).execute()
    data = getattr(resp, "data", None) or []
    if data:
        return str(data[0]["id"])
    resp = service.client.table("profiles").select("id").limit(1).execute()
    return str(resp.data[0]["id"])


def main() -> int:
    service = DocumentService()
    user_id = admin_user_id(service)

    with tempfile.TemporaryDirectory() as tmp:
        for path in FILES:
            data = path.read_bytes()
            loaded = load_document(str(path))
            level = loaded.metadata.get("access_level", "internal")

            doc = service.upload(
                user_id=user_id,
                filename=path.name,
                data=data,
                file_type=loaded.file_type,
                access_level=level,
            )

            stored = service.download(user_id, doc["id"], tmp)
            chunks = index_uploaded_file(
                stored,
                version=doc["version"],
                content_hash=doc["content_hash"],
                document_id=doc["id"],
            )
            service.mark_status(user_id, doc["id"], "ready")

            print(
                f"ok  {path.name:<42} level={level:<9} chunks={len(chunks)}"
            )

        rebuild_bm25(service, tmp)

    print("\nUploaded 6 fixtures. Re-run is idempotent (same filename bumps version).")
    return 0


if __name__ == "__main__":
    sys.exit(main())