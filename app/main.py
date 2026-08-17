from fastapi import FastAPI

from app.api.routes import router
from app.api.ingestion import router as ingestion_router


app = FastAPI(
    title="Support Knowledge Copilot",
    description=(
        "RAG-based support knowledge assistant "
        "with verified citations."
    ),
    version="1.0.0",
)


app.include_router(router)
app.include_router(ingestion_router)


@app.get("/health")
def health():

    return {
        "status": "ok"
    }