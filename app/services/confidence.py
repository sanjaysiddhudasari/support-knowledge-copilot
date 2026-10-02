import math


class ConfidenceScorer:

    def calculate(
        self,
        results,
        citations,
        answerable: bool,
    ) -> dict:

        retrieval_score = self._retrieval_score(results)

        citation_score = self._citation_score(citations)

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

        top_result = results[0]

        # Reranked results use the cross-encoder score.
        if "rerank_score" in top_result:
            rerank_score = float(
                top_result["rerank_score"]
            )

            return 1 / (
                1 + math.exp(-rerank_score)
            )

        # Hybrid results use Reciprocal Rank Fusion.
        # The maximum possible RRF score is obtained when
        # the same chunk is ranked first by both retrievers.
        if "rrf_score" in top_result:
            rrf_score = float(
                top_result["rrf_score"]
            )

            max_rrf_score = 2 / (60 + 1)

            return min(
                rrf_score / max_rrf_score,
                1.0,
            )

        # Dense retrieval exposes a similarity score.
        if "score" in top_result:
            score = float(
                top_result["score"]
            )

            return max(
                0.0,
                min(score, 1.0),
            )

        return 0.0

    @staticmethod
    def _citation_score(citations):

        if not citations:
            return 0.0

        supported = sum(
            citation.supported
            for citation in citations
        )

        return supported / len(citations)
