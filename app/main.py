from fastapi import FastAPI

from app.api.routes import router
from app.api.conversations import router as conversations_router
from app.api.ingestion import router as ingestion_router
from app.api.auth import router as auth_router


app = FastAPI(
    title="Support Knowledge Copilot",
    description=(
        "RAG-based support knowledge assistant "
        "with verified citations."
    ),
    version="1.0.0",
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