import time
from typing import TypedDict

from app.generation.answerability import AnswerabilityDetector
from app.generation.citation_verifier import CitationVerifier
from app.generation.generator import AnswerGenerator
from app.models.answer import Answerability, Citation
from app.observability.tracing import span
from app.services.retrieval_service import RetrievalService
from app.services.confidence import ConfidenceScorer


class QAAnswerResult(TypedDict):
    answer: str
    citations: list[Citation]
    answerability: Answerability
    confidence: float
    confidence_breakdown: dict[str, float]


def _finish(run, started, strategy, result) -> QAAnswerResult:
    """Close the query trace with the summary the observability spec requires.

    Records the already-computed confidence/answerability/citation values and
    tags the run. Nothing is recomputed here.
    """

    citations = result["citations"]

    run.add_tags(
        [
            "answerable"
            if result["answerability"].answerable
            else "unanswerable"
        ]
    )

    run.add_metadata(
        {
            "confidence": result["confidence"],
            "answerable": result["answerability"].answerable,
            "citation_count": len(citations),
            "supported_citations": sum(
                1 for citation in citations if citation.supported
            ),
            "retrieval_strategy": strategy,
            "latency_ms": round(
                (time.perf_counter() - started) * 1000, 2
            ),
        }
    )

    run.add_outputs(
        {
            "answer_chars": len(result["answer"]),
            "citation_count": len(citations),
            "citation_chunk_ids": [
                citation.chunk_id for citation in citations
            ],
        }
    )

    return result


class QAService:

    def __init__(self):

        self.retrieval_service = RetrievalService()

        self.answer_generator = AnswerGenerator()

        self.citation_verifier = CitationVerifier()

        self.answerability_detector = (
            AnswerabilityDetector()
        )

        self.confidence_scorer = ConfidenceScorer()

    def answer(
        self,
        query: str,
        user_access_level:str="public",
        user_id: str | None = None,
    ) -> QAAnswerResult:

        started = time.perf_counter()

        strategy = self.retrieval_service.strategy

        with span(
            "RAG Query",
            run_type="chain",
            tags=["rag", strategy],
            metadata={
                "user_id": user_id,
                "access_level": user_access_level,
                "retrieval_strategy": strategy,
            },
            inputs={"query": query},
        ) as run:

            results = self.retrieval_service.retrieve(
                query=query,
                top_k=5,
                candidate_k=20,
                user_access_level=user_access_level,
            )

            answerability = (
                self.answerability_detector.check(
                    query=query,
                    results=results,
                )
            )

            # Do not generate an answer when the
            # documentation is insufficient.
            if not answerability.answerable:

                return _finish(
                    run,
                    started,
                    strategy,
                    {
                        "answer": (
                            "I couldn't find enough information "
                            "in the available documentation to "
                            "verify an answer to this question."
                        ),
                        "citations": [],
                        "answerability": answerability,
                        "confidence": 0.0,
                        "confidence_breakdown": {
                            "retrieval_score": 0.0,
                            "citation_support_rate": 0.0,
                            "answerability_score": 0.0,
                        },
                    },
                )

            generated_answer = (
                self.answer_generator.generate(
                    query=query,
                    results=results,
                )
            )

            verified_citations = (
                self.citation_verifier.verify(
                    citations=generated_answer.citations,
                    results=results,
                )
            )

            confidence = self.confidence_scorer.calculate(
                results=results,
                citations=verified_citations,
                answerable=answerability.answerable,
            )

            generated_answer.citations = (
                verified_citations
            )

            generated_answer.answerability = (
                answerability
            )

            generated_answer.confidence = (
                confidence["confidence"]
            )

            return _finish(
                run,
                started,
                strategy,
                {
                    "answer": generated_answer.answer,
                    "citations": generated_answer.citations,
                    "answerability": generated_answer.answerability,
                    "confidence": generated_answer.confidence,
                    "confidence_breakdown": confidence,
                },
            )
