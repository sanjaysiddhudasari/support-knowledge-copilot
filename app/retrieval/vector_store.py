import os
from uuid import NAMESPACE_URL, uuid5

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    ExtendedPointId,
    FieldCondition,
    Filter,
    FilterSelector,
    MatchValue,
    PointIdsList,
    PointStruct,
    VectorParams,
    Document,
)

load_dotenv()

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

COLLECTION_NAME = "support_chunks"
VECTOR_SIZE = 384
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def _build_payload(chunk, document_id: str | None = None) -> dict:
    """Build the Qdrant payload for a chunk.

    The core fields are always present so existing collections stay
    compatible. ``file_type``, ``page`` and ``document_id`` are optional
    ingestion metadata written only when known/available.
    """

    payload = {
        "chunk_ids": chunk.chunk_ids,
        "text": chunk.text,
        "source": chunk.source,
        "section": chunk.section,
        "last_updated": str(chunk.last_updated),
        "document_type": chunk.document_type,
        "access_level": chunk.access_level,
        "version": getattr(chunk, "version", 1),
    }

    file_type = getattr(chunk, "file_type", None)
    page = getattr(chunk, "page", None)

    if file_type is not None:
        payload["file_type"] = file_type

    if page is not None:
        payload["page"] = page

    if document_id is not None:
        payload["document_id"] = document_id

    return payload


class VectorStore:

    def __init__(self, path: str = "data/qdrant"):
        self.cloud = bool(QDRANT_URL and QDRANT_API_KEY)

        if self.cloud:
            self.client = QdrantClient(
                url=QDRANT_URL,
                api_key=QDRANT_API_KEY,
                cloud_inference=True,
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

    def upsert_chunks(self, chunks, embeddings=None, document_id=None):
        points = []

        for index, chunk in enumerate(chunks):
            if self.cloud and embeddings is None:
                vector = Document(
                    text=chunk.text,
                    model=EMBEDDING_MODEL,
                )
            else:
                if embeddings is None:
                    raise ValueError(
                        "Embeddings are required for local Qdrant."
                    )
                vector = embeddings[index]

            point = PointStruct(
                id=str(uuid5(NAMESPACE_URL, chunk.chunk_ids)),
                vector=vector,
                payload=_build_payload(chunk, document_id),
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

    def delete_by_document(self, document_id: str) -> int:
        """Delete a document's vectors by payload filter.

        Independent of the local manifest: after a redeploy (which resets
        data/index/manifest.json) deletes still find the vectors because the
        document id is stored in each chunk's payload.
        """

        selector = FilterSelector(
            filter=Filter(
                must=[
                    FieldCondition(
                        key="document_id",
                        match=MatchValue(value=document_id),
                    )
                ]
            )
        )

        self.client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=selector,
        )

        # Qdrant does not count deleted points synchronously here; returning
        # the number we asked to delete keeps callers simple.
        return 0

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

    def search_text(
        self,
        query: str,
        top_k: int = 5,
    ):
        if not self.cloud:
            raise RuntimeError(
                "Cloud text inference requires QDRANT_URL and QDRANT_API_KEY."
            )

        response = self.client.query_points(
            collection_name=COLLECTION_NAME,
            query=Document(
                text=query,
                model=EMBEDDING_MODEL,
            ),
            limit=top_k,
            with_payload=True,
        )

        return [
            (point.score, point.payload)
            for point in response.points
        ]
