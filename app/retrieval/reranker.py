import time

from app.observability.tracing import describe_result, span


class Reranker:

    def __init__(
        self,
        model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
    ):
        from sentence_transformers import CrossEncoder

        self.model_name = model_name

        self.model = CrossEncoder(
            model_name,
            device="cpu",
        )

    def rerank(
        self,
        query: str,
        results,
        top_k: int = 5,
    ):
        if not results:
            return []

        started = time.perf_counter()

        with span(
            "Reranker",
            run_type="chain",
            tags=["rag", "reranked"],
            metadata={
                "reranker_enabled": True,
                "reranker_model": self.model_name,
                "input_count": len(results),
                "top_k": top_k,
            },
            inputs={"query": query},
        ) as run:

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

            top_results = reranked[:top_k]

            run.add_metadata(
                {
                    "output_count": len(top_results),
                    "latency_ms": round(
                        (time.perf_counter() - started) * 1000, 2
                    ),
                }
            )

            run.add_outputs(
                {
                    "reranked": [
                        describe_result(result)
                        for result in top_results
                    ]
                }
            )

            return top_results
