import os
from uuid import NAMESPACE_URL, uuid5

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    ExtendedPointId,
    PointIdsList,
    PointStruct,
    VectorParams,
)

load_dotenv()

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

COLLECTION_NAME = "support_chunks"
VECTOR_SIZE = 384


class VectorStore:

    def __init__(self, path: str = "data/qdrant"):
        if QDRANT_URL and QDRANT_API_KEY:
            self.client = QdrantClient(
                url=QDRANT_URL,
                api_key=QDRANT_API_KEY,
            )
        else:
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
                    "version": getattr(chunk, "version", 1),
                },
            )
            points.append(point)

        self.client.upsert(
            collection_name=COLLECTION_NAME,
            points=points,
        )

    def delete_chunks(self, chunk_ids: list[str]) -> None:
        if not chunk_ids:
            return

        point_ids: list[ExtendedPointId] = [
            uuid5(NAMESPACE_URL, chunk_id)
            for chunk_id in chunk_ids
        ]

        self.client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=PointIdsList(points=point_ids),
        )

        print(
            f"Deleted {len(point_ids)} chunks from Qdrant."
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
