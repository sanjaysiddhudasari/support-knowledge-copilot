from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    VectorParams,
)
from uuid import uuid5, NAMESPACE_URL

COLLECTION_NAME = "support_chunks"
VECTOR_SIZE = 384


class VectorStore:

    def __init__(self, path: str = "data/qdrant"):
        self.client = QdrantClient(path=path)


    def create_collection(self):

        collections = self.client.get_collections().collections

        existing_names = {
            collection.name
            for collection in collections
        }

        if COLLECTION_NAME in existing_names:
            self.client.delete_collection(
                collection_name=COLLECTION_NAME
            )

        self.client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(
                size=VECTOR_SIZE,
                distance=Distance.COSINE,
            ),
        )
    
    def upsert_chunks(self, chunks, embeddings):

        points = []

        for chunk, embedding in zip(chunks, embeddings):

            point = PointStruct(
                id=str(uuid5(NAMESPACE_URL, chunk.chunk_ids)),
                vector=embedding,
                payload={
                    "chunk_ids": chunk.chunk_ids,
                    "text": chunk.text,
                    "source": chunk.source,
                    "section": chunk.section,
                    "last_updated": str(chunk.last_updated),
                    "document_type": chunk.document_type,
                    "access_level": chunk.access_level,
                },
            )

            points.append(point)

        self.client.upsert(
            collection_name=COLLECTION_NAME,
            points=points,
        )

    def search(
            self,
            query_vector: list[float],
            top_k: int = 5,
        ):
            response = self.client.query_points(
                collection_name=COLLECTION_NAME,
                query=query_vector,
                limit=top_k,
            )
            return [(p.score, p.payload) for p in response.points]
    