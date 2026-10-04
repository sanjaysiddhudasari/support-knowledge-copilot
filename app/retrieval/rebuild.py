"""Derived-index operations backed by durable (Storage/Postgres) documents.

- one-file indexing for uploads (never treat the rest of the corpus as deleted)
- BM25 rebuild from Postgres documents via Storage downloads
- chunk cleanup for deletes

The manifest stays the single bookkeeping file (``data/index/manifest.json``);
BM25 build state lives under its ``bm25`` key instead of a second manifest.
``data/bm25/index.joblib`` is derived/cache state: safe to delete and rebuild.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.ingestion.chunker import chunk_document
from app.ingestion.loader import load_document
from app.retrieval.bm25 import BM25Retriever
from app.retrieval.indexer import MANIFEST_PATH, BM25_INDEX_PATH
from app.retrieval.vector_store import VectorStore
from app.observability.tracing import span

BM25_STATE_KEY = "bm25"


def _load_manifest() -> dict:
    if not MANIFEST_PATH.exists():
        return {"documents": {}}

    with open(MANIFEST_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_manifest(manifest: dict) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)


def index_uploaded_file(
    path: Path,
    version: int,
    content_hash: str | None = None,
) -> list:
    """Chunk one uploaded file, replace its Qdrant chunks, update manifest.

    Deliberately does NOT reuse Indexer.index_incremental: that diffs the
    whole directory against the manifest and would classify every other
    corpus document as deleted when pointed at a temp dir.
    """

    filename = path.name
    manifest = _load_manifest()
    documents = manifest.setdefault("documents", {})

    old_record = documents.get(filename, {})
    old_chunk_ids = old_record.get("chunk_ids", [])

    document = load_document(str(path))
    chunks = chunk_document(document, version=version)

    vector_store = VectorStore()

    if old_chunk_ids:
        vector_store.delete_chunks(old_chunk_ids)

    vector_store.upsert_chunks(chunks=chunks)

    documents[filename] = {
        "content_hash": content_hash or old_record.get("content_hash", ""),
        "chunk_ids": [chunk.chunk_ids for chunk in chunks],
        "version": version,
        "file_type": document.file_type,
    }

    _save_manifest(manifest)

    return chunks


def remove_document_chunks(row: dict) -> int:
    """Delete a document's Qdrant chunks and manifest entry."""

    manifest = _load_manifest()
    documents = manifest.setdefault("documents", {})

    record = documents.pop(row["filename"], None)

    removed = 0

    if record and record.get("chunk_ids"):
        vector_store = VectorStore()
        vector_store.delete_chunks(record["chunk_ids"])
        removed = len(record["chunk_ids"])

    _save_manifest(manifest)

    return removed


def _bm25_state(manifest: dict, documents: list[dict]) -> dict:
    return {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "document_count": len(documents),
        "documents": {
            row["filename"]: {
                "content_hash": row.get("content_hash"),
                "version": row.get("version"),
            }
            for row in documents
        },
    }


def is_stale(manifest: dict | None = None) -> bool:
    """True when BM25 build state does not match the manifest documents.

    Compares the per-document hash/version snapshot recorded at build time
    against the manifest's current document records. Missing state = stale.
    """

    manifest = manifest or _load_manifest()
    state = manifest.get(BM25_STATE_KEY)

    if not state or not state.get("documents"):
        return bool(manifest.get("documents"))

    current = {
        filename: (record.get("content_hash"), record.get("version"))
        for filename, record in manifest.get("documents", {}).items()
    }

    recorded = {
        filename: (record.get("content_hash"), record.get("version"))
        for filename, record in state["documents"].items()
    }

    return current != recorded


def rebuild_bm25(service, admin_user_id: str, workdir: str) -> dict:
    """Rebuild BM25 from durable documents.

    Postgres lists the documents; Storage supplies the bytes; the normal
    loader/chunker pipeline does the rest. Also validates staleness against
    the state recorded in the manifest.
    """

    with span(
        "BM25 Rebuild",
        run_type="chain",
        tags=["ingestion", "bm25"],
        metadata={"trigger": "manual"},
    ) as run:
        documents = service.list_documents(admin_user_id)

        if not documents:
            # Valid empty state: BM25 with no documents retrieves nothing
            # but does not crash.
            retriever = BM25Retriever()
            retriever.build_index([])
            retriever.save(BM25_INDEX_PATH)

            manifest = _load_manifest()
            manifest[BM25_STATE_KEY] = _bm25_state(manifest, [])
            _save_manifest(manifest)

            run.add_metadata({"bm25_document_count": 0, "chunk_count": 0})

            return {
                "status": "rebuilt",
                "document_count": 0,
                "chunk_count": 0,
            }

        chunks = []

        for row in documents:
            document_path = service.download(
                admin_user_id, row["id"], workdir
            )

            loaded = load_document(str(document_path))

            chunks.extend(
                chunk_document(loaded, version=row.get("version") or 1)
            )

        retriever = BM25Retriever()
        retriever.build_index(chunks)
        retriever.save(BM25_INDEX_PATH)

        manifest = _load_manifest()
        state = _bm25_state(manifest, documents)

        manifest[BM25_STATE_KEY] = state
        _save_manifest(manifest)

        run.add_metadata(
            {
                "bm25_document_count": len(documents),
                "chunk_count": len(chunks),
            }
        )

        return {
            "status": "rebuilt",
            "document_count": len(documents),
            "chunk_count": len(chunks),
        }
