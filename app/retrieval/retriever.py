from app.retrieval.embedding import EmbeddingService
from app.retrieval.vector_store import VectorStore
from app.models.chunk import Chunk
from app.models.retrieval import RetrievalResult


class DenseRetriever:

    def __init__(self):
        self.embedding_service = EmbeddingService()
        self.vector_store = VectorStore()


    def retrieve(
    self,
    query: str,
    top_k: int = 5,
):
        query_embedding = self.embedding_service.embed_text(query)

        results = self.vector_store.search(
            query_vector=query_embedding,
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
            )

            retrieval_results.append(
                RetrievalResult(
                    chunk=chunk,
                    score=score,
                    rank=rank,
                    source="dense",
                )
            )

        return retrieval_results
