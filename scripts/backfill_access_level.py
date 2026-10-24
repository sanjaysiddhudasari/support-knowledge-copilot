"""One-time backfill: align documents.access_level with parsed front matter.

Earlier uploads never passed an access level, so every row defaulted to
'public' while retrieval enforced the level parsed from the document's
front matter (default 'internal'). This re-derives each document's level from
its stored bytes and updates the Postgres row to match what is enforced.

Idempotent: safe to re-run. Uses list_all_documents (service path) so every
document is covered, not just the calling user's.

Usage (repo root, uses .env):
    python scripts/backfill_access_level.py
"""

import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv

# scripts/ isn't a package; put the repo root on sys.path so `app` imports,
# regardless of the cwd it's launched from.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

load_dotenv()

from app.ingestion.loader import load_document  # noqa: E402
from app.services.document_storage import DocumentService  # noqa: E402


def main() -> int:
    service = DocumentService()
    documents = service.list_all_documents()

    if not documents:
        print("no documents to backfill")
        return 0

    updated = 0

    with tempfile.TemporaryDirectory() as tmp:
        for row in documents:
            try:
                target = service.download(
                    row["user_id"], row["id"], tmp
                )
                loaded = load_document(str(target))
                level = loaded.metadata.get("access_level")
            except Exception as error:
                print(f"  SKIP {row['filename']}: {error}")
                continue

            if level is None or level == row.get("access_level"):
                continue

            # Update only access_level; do NOT bump version or touch status
            # (it is already indexed/ready).
            service.client.table("documents").update(
                {"access_level": level}
            ).eq("id", row["id"]).execute()

            updated += 1
            print(f"  fix  {row['filename']}: {row.get('access_level')} -> {level}")

    print(f"\ndone: access_level corrected on {updated} document(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())