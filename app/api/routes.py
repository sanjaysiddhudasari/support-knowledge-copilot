from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.auth.models import User

router = APIRouter(
    prefix="/api",
    tags=["QA"],
)

_qa_service = None


def get_qa_service():
    global _qa_service

    if _qa_service is None:
        from app.services.qa_service import QAService
        _qa_service = QAService()

    return _qa_service


class QueryRequest(BaseModel):
    query: str
    # Optional client-supplied correlation id. When present it is stored on the
    # conversation's user + assistant messages and attached to the LangSmith
    # trace for this query, so a stored message maps to one RAG trace.
    query_id: str | None = None


@router.get("/me")
def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/query")
def query(
    request: QueryRequest,
    current_user: User = Depends(get_current_user),
):
    kwargs = {
        "query": request.query,
        "user_access_level": current_user.access_level,
        "user_id": current_user.id,
    }

    # Only forwarded when the caller sends one, so the pipeline behaves
    # exactly as before for callers that do not correlate messages.
    if request.query_id:
        kwargs["query_id"] = request.query_id

    result = get_qa_service().answer(**kwargs)

    return {
        "answer": result["answer"],
        "answerable": result["answerability"].answerable,
        "citations": [
            citation.model_dump()
            for citation in result["citations"]
        ],
        "confidence": result["confidence"],
        "query_id": request.query_id,
    }
