import logging
import os
import tempfile
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import router
from app.api.conversations import router as conversations_router
from app.api.ingestion import router as ingestion_router
from app.api.auth import router as auth_router

logger = logging.getLogger(__name__)


def _ensure_bm25_derived_index() -> None:
    """Rebuild the derived BM25 index at startup when it is missing or stale.

    data/bm25/index.joblib is derived/cache state; the source of truth is
    Supabase (Postgres list -> Storage download). It is rebuilt when the file
    is absent (fresh deploy) or when the recorded build snapshot no longer
    matches the current documents (hash/version changed out-of-band).

    Tolerant: without Supabase credentials this is a no-op and dense-only
    retrieval still works. A present, matching index is not rebuilt, so normal
    restarts (and tests) don't pay a network round-trip.
    """

    from app.retrieval.indexer import BM25_INDEX_PATH
    from app.retrieval.rebuild import is_stale

    if os.path.exists(BM25_INDEX_PATH) and not is_stale():
        return

    try:
        from app.retrieval.rebuild import rebuild_bm25
        from app.services.document_storage import DocumentService

        with tempfile.TemporaryDirectory() as workdir:
            logger.info(
                "Rebuilding derived BM25 index from durable documents...",
            )
            rebuild_bm25(DocumentService(), workdir)
    except Exception:  # pragma: no cover - depends on live creds
        # Never block startup: if rebuild fails, retrieval continues on dense
        # only (hybrid degrades safely).
        logger.warning("BM25 rebuild at startup failed", exc_info=True)


@asynccontextmanager
async def lifespan(_app):
    _ensure_bm25_derived_index()
    yield


app = FastAPI(
    title="Support Knowledge Copilot",
    description=(
        "RAG-based support knowledge assistant "
        "with verified citations."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


app.include_router(router)
app.include_router(conversations_router)
app.include_router(ingestion_router)
app.include_router(auth_router)


@app.get("/health")
def health():

    return {
        "status": "ok"
    }