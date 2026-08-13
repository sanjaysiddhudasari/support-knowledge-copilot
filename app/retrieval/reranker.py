from sentence_transformers import CrossEncoder


class Reranker:

    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
    ):
        self.model = CrossEncoder(model_name)

    def rerank(
        self,
        query: str,
        results,
        top_k: int = 5,
    ):
        if not results:
            return []

        pairs = [
            (
                query,
                result["chunk"].text,
            )
            for result in results
        ]

        scores = self.model.predict(pairs)

        reranked = []

        for result, score in zip(results, scores):
            reranked.append(
                {
                    "chunk": result["chunk"],
                    "rrf_score": result["rrf_score"],
                    "rerank_score": float(score),
                }
            )

        reranked.sort(
            key=lambda result: result["rerank_score"],
            reverse=True,
        )

        return reranked[:top_k] 