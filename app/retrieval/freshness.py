from datetime import date


class FreshnessScorer:

    def __init__(
        self,
        freshness_weight: float = 0.15,
    ):
        self.freshness_weight = freshness_weight

    def score(
        self,
        last_updated: date,
        reference_date: date | None = None,
    ) -> float:

        if reference_date is None:
            reference_date = date.today()

        age_days = max(
            (reference_date - last_updated).days,
            0,
        )

        # Linear decay over 365 days.
        freshness = max(
            0.0,
            1.0 - (age_days / 365.0),
        )

        return freshness

    def apply(
        self,
        results,
        reference_date: date | None = None,
    ):
        scores = [result["rerank_score"] for result in results]

        min_score = min(scores)
        max_score = max(scores)

        for result in results:
            if max_score > min_score:
                relevance = (
                    (result["rerank_score"] - min_score)
                    / (max_score - min_score)
                )
            else:
                relevance = 1.0

            freshness = self.score(
                last_updated=result["chunk"].last_updated,
                reference_date=reference_date,
            )

            result["freshness_score"] = freshness
            result["relevance_score"] = relevance

            result["final_score"] = (
                (1 - self.freshness_weight) * relevance
                + self.freshness_weight * freshness
            )

        results.sort(
            key=lambda result: result["final_score"],
            reverse=True,
        )

        return results