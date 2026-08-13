from app.generation.answerability import AnswerabilityDetector
from app.generation.citation_verifier import CitationVerifier
from app.generation.generator import AnswerGenerator
from app.retrieval.retrieval_service import RetrievalService
from app.services.confidence import ConfidenceScorer


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
    ):

        results = self.retrieval_service.retrieve(
            query=query,
            top_k=5,
            candidate_k=20,
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

            return {
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
            }

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

        return {
            "answer": generated_answer.answer,
            "citations": generated_answer.citations,
            "answerability": generated_answer.answerability,
            "confidence": generated_answer.confidence,
            "confidence_breakdown": confidence,
        }