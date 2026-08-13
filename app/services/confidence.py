import math


class ConfidenceScorer:

    def calculate(
        self,
        results,
        citations,
        answerable: bool,
    ) -> dict:

        retrieval_score = self._retrieval_score(
            results
        )

        citation_score = self._citation_score(
            citations
        )

        answerability_score = (
            1.0 if answerable else 0.0
        )

        confidence = (
            0.4 * retrieval_score
            + 0.3 * citation_score
            + 0.3 * answerability_score
        )

        return {
            "confidence": round(
                confidence,
                4,
            ),
            "retrieval_score": round(
                retrieval_score,
                4,
            ),
            "citation_support_rate": round(
                citation_score,
                4,
            ),
            "answerability_score": round(
                answerability_score,
                4,
            ),
        }

    @staticmethod
    def _retrieval_score(results):

        if not results:
            return 0.0

        top_score = results[0]["rerank_score"]

        # Convert the cross-encoder score into
        # a value between 0 and 1.
        return 1 / (
            1 + math.exp(-top_score)
        )

    @staticmethod
    def _citation_score(citations):

        if not citations:
            return 0.0

        supported = sum(
            citation.supported
            for citation in citations
        )

        return supported / len(citations)