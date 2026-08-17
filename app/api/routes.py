from fastapi import APIRouter
from pydantic import BaseModel

from app.services.qa_service import QAService


router = APIRouter(
    prefix="/api",
    tags=["QA"],
)

# lazy singleton to prevent lock contention on module import / reload
_qa_service = None


def get_qa_service() -> QAService:
    global _qa_service
    if _qa_service is None:
        _qa_service = QAService()
    return _qa_service


class QueryRequest(BaseModel):
    query: str


@router.post("/query")
def query(request: QueryRequest):

    result = get_qa_service().answer(
        query=request.query
    )

    return {
        "answer": result["answer"],
        "answerable": result[
            "answerability"
        ].answerable,
        "citations": [
            citation.model_dump()
            for citation in result["citations"]
        ],
        "confidence": result["confidence"],
    }