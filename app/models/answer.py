from pydantic import BaseModel


class Citation(BaseModel):
    chunk_id: str
    claim: str
    supported: bool = False
    explanation: str = ""


class Answerability(BaseModel):
    answerable: bool
    explanation: str


class GeneratedAnswer(BaseModel):
    answer: str
    citations: list[Citation]
    answerability: Answerability | None = None
    confidence: float = 0.0