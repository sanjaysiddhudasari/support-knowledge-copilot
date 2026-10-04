import time
from collections import defaultdict

from app.observability.tracing import describe_result, span


class HybridRetriever:

    def __init__(
        self,
        dense_retriever,
        bm25_retriever,
    ):
        self.dense_retriever = dense_retriever
        self.bm25_retriever = bm25_retriever

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        candidate_k: int = 10,
        rrf_k: int = 60,
    ):

        started = time.perf_counter()

        with span(
            "Hybrid Fusion",
            run_type="chain",
            tags=["rag", "hybrid"],
            metadata={
                "retrieval_type": "hybrid",
                "fusion": "rrf",
                "rrf_k": rrf_k,
                "top_k": top_k,
                "candidate_k": candidate_k,
            },
            inputs={"query": query},
        ) as run:

            dense_results = self.dense_retriever.retrieve(
                query,
                top_k=candidate_k,
            )

            bm25_results = self.bm25_retriever.retrieve(
                query,
                top_k=candidate_k,
            )

            fused = self._rrf(
                dense_results,
                bm25_results,
                top_k,
                rrf_k,
            )

            run.add_metadata(
                {
                    "dense_count": len(dense_results),
                    "bm25_count": len(bm25_results),
                    "fused_count": len(fused),
                    "latency_ms": round(
                        (time.perf_counter() - started) * 1000, 2
                    ),
                }
            )

            run.add_outputs(
                {
                    "fused": [
                        describe_result(result)
                        for result in fused
                    ]
                }
            )

            return fused

    def _rrf(
        self,
        dense_results,
        bm25_results,
        top_k,
        rrf_k,
    ):

        scores = defaultdict(float)

        chunks = {}

        for result in dense_results:

            chunk_id = result.chunk.chunk_ids

            scores[chunk_id] += (
                1 / (rrf_k + result.rank)
            )

            chunks[chunk_id] = result.chunk

        for result in bm25_results:

            chunk_id = result.chunk.chunk_ids

            scores[chunk_id] += (
                1 / (rrf_k + result.rank)
            )

            chunks[chunk_id] = result.chunk

        ranked = sorted(
            scores.items(),
            key=lambda item: item[1],
            reverse=True,
        )[:top_k]

        return [
            {
                "chunk": chunks[chunk_id],
                "rrf_score": score,
            }
            for chunk_id, score in ranked
        ]
