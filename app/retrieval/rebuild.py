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
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

from app.ingestion.chunker import chunk_document
from app.ingestion.loader import load_document
from app.retrieval.bm25 import BM25Retriever
from app.retrieval.indexer import MANIFEST_PATH, BM25_INDEX_PATH
from app.retrieval.vector_store import VectorStore
from app.services.retrieval_service import reload_all_bm25
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
    document_id: str | None = None,
) -> list:
    """Chunk one uploaded file, replace its Qdrant chunks, update manifest.

    Deliberately does NOT reuse Indexer.index_incremental: that diffs the
    whole directory against the manifest and would classify every other
    corpus document as deleted when pointed at a temp dir.
    """

    filename = path.name
    manifest = _load_manifest()
    documents = manifest.setdefault("documents", {})

    # Manifest records are keyed by the stable document id so identical
    # filenames across owners never overwrite one another's bookkeeping.
    # document_id must be non-empty for Supabase uploads; legacy callers with
    # a bare filename keep the old filename key for backward compatibility.
    key = document_id or filename
    old_record = documents.get(key, {})
    old_chunk_ids = old_record.get("chunk_ids", [])

    document = load_document(str(path))

    # Deterministic chunk ids per document: {document_id}_chunk_{n}. Different
    # document ids never collide even with identical filenames. Legacy corpus
    # (no document_id) keeps filename-based ids.
    chunks = chunk_document(
        document, version=version, chunk_id_base=document_id
    )

    vector_store = VectorStore()

    if old_chunk_ids:
        vector_store.delete_chunks(old_chunk_ids)

    vector_store.upsert_chunks(chunks=chunks, document_id=document_id)

    documents[key] = {
        "filename": filename,
        "content_hash": content_hash or old_record.get("content_hash", ""),
        # flat list of string chunk ids
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

    document_id = row.get("id")
    # Latest uploads record under document_id; legacy corpus under filename.
    record = documents.pop(document_id, None) or documents.pop(
        row.get("filename"), None
    )

    vector_store = VectorStore()
    removed = 0

    if document_id:
        # Primary path: delete by payload filter so a lost manifest (redeploy)
        # never leaks vectors. Chunk ids are only a fallback.
        vector_store.delete_by_document(document_id)
        removed = len(record["chunk_ids"]) if record else 0
    elif record and record.get("chunk_ids"):
        vector_store.delete_chunks(record["chunk_ids"])
        removed = len(record["chunk_ids"])

    _save_manifest(manifest)

    return removed


def _bm25_state(manifest: dict, documents: list[dict]) -> dict:
    return {
        "built_at": datetime.now(timezone.utc).isoformat(),
        "document_count": len(documents),
        "documents": {
            (row.get("id") or row["filename"]): {
                "content_hash": row.get("content_hash"),
                "version": row.get("version"),
            }
            for row in documents
        },
    }


def is_stale(manifest: dict | None = None) -> bool:
    """True when a recorded BM25 build no longer matches current documents.

    Compares the per-document hash/version snapshot captured at build time
    against the manifest's current document records. A missing snapshot is
    NOT treated as stale here: a truly absent index is handled by the startup
    missing-file path, and a present index built before snapshots existed
    (seed corpus) should not force a network rebuild on every start.
    """

    manifest = manifest or _load_manifest()
    state = manifest.get(BM25_STATE_KEY) or {}
    recorded = state.get("documents")

    if not recorded:
        return False

    current = {
        key: (record.get("content_hash"), record.get("version"))
        for key, record in manifest.get("documents", {}).items()
        if key != BM25_STATE_KEY
    }

    rec = {
        key: (record.get("content_hash"), record.get("version"))
        for key, record in recorded.items()
    }

    return current != rec


def rebuild_bm25(service, workdir: str) -> dict:
    """Rebuild BM25 from durable documents.

    Postgres lists every document (service path, all owners); Storage
    supplies the bytes; the normal loader/chunker pipeline does the rest.
    """

    with span(
        "BM25 Rebuild",
        run_type="chain",
        tags=["ingestion", "bm25"],
        metadata={"trigger": "manual"},
    ) as run:
        documents = service.list_all_documents()

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

            reload_all_bm25()

            return {
                "status": "rebuilt",
                "document_count": 0,
                "chunk_count": 0,
            }

        chunks = []
        skipped = []

        for row in documents:
            try:
                document_path = service.download_all(row["id"], workdir)
                loaded = load_document(str(document_path))
                chunks.extend(
                    chunk_document(
                        loaded,
                        version=row.get("version") or 1,
                        chunk_id_base=row.get("id"),
                    )
                )
            except Exception as error:
                # One corrupt unparsable document must not fail the whole
                # rebuild (which would also block new uploads). Skip it, log
                # loudly, and continue with the healthy corpus.
                skipped.append(row.get("filename"))
                logger.warning(
                    "BM25 rebuild: skipping unloadable document %r: %s",
                    row.get("filename"),
                    error,
                )
                continue

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
                "skipped_document_count": len(skipped),
            }
        )

        reload_all_bm25()

        return {
            "status": "rebuilt",
            "document_count": len(documents),
            "chunk_count": len(chunks),
            "skipped_documents": skipped,
        }
