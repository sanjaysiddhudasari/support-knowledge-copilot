import time

from app.models.chunk import Chunk
from app.models.retrieval import RetrievalResult
from app.observability.tracing import describe_result, span
from app.retrieval.vector_store import (
    COLLECTION_NAME,
    EMBEDDING_MODEL,
    VectorStore,
)


class DenseRetriever:

    def __init__(self):
        self.vector_store = VectorStore()

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
    ):

        started = time.perf_counter()

        with span(
            "Dense Retrieval",
            run_type="retriever",
            tags=["rag", "dense"],
            metadata={
                "retrieval_type": "dense",
                "top_k": top_k,
                "collection_name": COLLECTION_NAME,
                "embedding_model": EMBEDDING_MODEL,
            },
            inputs={"query": query},
        ) as run:

            results = self.vector_store.search_text(
                query=query,
                top_k=top_k,
            )

            retrieval_results = []

            for rank, result in enumerate(results, start=1):
                score, payload = result
                if payload is None:
                    continue

                chunk = Chunk(
                    chunk_ids=payload["chunk_ids"],
                    text=payload["text"],
                    source=payload["source"],
                    section=payload["section"],
                    last_updated=payload["last_updated"],
                    document_type=payload["document_type"],
                    access_level=payload["access_level"],
                    version=payload.get("version", 1),
                    file_type=payload.get("file_type"),
                    page=payload.get("page"),
                )

                retrieval_results.append(
                    RetrievalResult(
                        chunk=chunk,
                        score=score,
                        rank=rank,
                        source="dense",
                    )
                )

            run.add_metadata(
                {
                    "result_count": len(retrieval_results),
                    "latency_ms": round(
                        (time.perf_counter() - started) * 1000, 2
                    ),
                }
            )

            run.add_outputs(
                {
                    "retrieved": [
                        describe_result(result)
                        for result in retrieval_results
                    ]
                }
            )

            return retrieval_results
