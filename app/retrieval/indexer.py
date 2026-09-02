from pathlib import Path
from datetime import date
import re

from app.ingestion.chunker import chunk_markdown
from app.ingestion.loader import load_document
from app.retrieval.embedding import EmbeddingService
from app.retrieval.vector_store import VectorStore
from app.retrieval.bm25 import BM25Retriever


BM25_INDEX_PATH = "data/bm25/index.joblib"


class Indexer:

    def __init__(self):
        self.embedding_service = EmbeddingService()
        self.vector_store = VectorStore()
        self.bm25_retriever = BM25Retriever()

    def _parse_metadata(self, text: str) -> dict:

        metadata = {
            "last_updated": date(2026, 8, 1),
            "document_type": "guide",
            "access_level": "internal",
        }

        if not text.startswith("---"):
            return metadata

        match = re.match(
            r"^---\s*\n(.*?)\n---\s*\n",
            text,
            re.DOTALL,
        )

        if not match:
            return metadata

        front_matter = match.group(1)

        for line in front_matter.splitlines():

            if ":" not in line:
                continue

            key, value = line.split(":", 1)

            key = key.strip()
            value = value.strip()

            if key == "last_updated":

                year, month, day = map(
                    int,
                    value.split("-"),
                )

                metadata["last_updated"] = date(
                    year,
                    month,
                    day,
                )

            elif key == "document_type":
                metadata["document_type"] = value

            elif key == "access_level":
                metadata["access_level"] = value

        return metadata

    def _remove_front_matter(self, text: str) -> str:

        if not text.startswith("---"):
            return text

        match = re.match(
            r"^---\s*\n.*?\n---\s*\n",
            text,
            re.DOTALL,
        )

        if match:
            return text[match.end():]

        return text

    def index_corpus(
        self,
        directory: str = "data/raw",
    ):

        directory_path = Path(directory)

        documents = sorted(
            directory_path.glob("*.md")
        )

        if not documents:
            raise RuntimeError(
                f"No Markdown documents found in {directory}"
            )

        all_chunks = []

        print(
            f"Found {len(documents)} documents."
        )

        for path in documents:

            source = path.name

            raw_text = load_document(
                str(path)
            )

            metadata = self._parse_metadata(
                raw_text
            )

            text = self._remove_front_matter(
                raw_text
            )

            chunks = chunk_markdown(
                text=text,
                source=source,
                last_updated=metadata[
                    "last_updated"
                ],
                document_type=metadata[
                    "document_type"
                ],
                access_level=metadata[
                    "access_level"
                ],
            )

            all_chunks.extend(chunks)

            print(
                f"{source}: "
                f"{len(chunks)} chunks"
            )

        print(
            f"\nTotal chunks: "
            f"{len(all_chunks)}"
        )

        # --------------------------------------------------
        # Build BM25 ONCE using the complete corpus
        # --------------------------------------------------

        self.bm25_retriever.build_index(
            all_chunks
        )

        self.bm25_retriever.save(
            BM25_INDEX_PATH
        )

        print(
            f"Saved BM25 index: "
            f"{BM25_INDEX_PATH}"
        )

        # --------------------------------------------------
        # Create embeddings for all chunks
        # --------------------------------------------------

        embeddings = (
            self.embedding_service.embed_texts(
                [
                    chunk.text
                    for chunk in all_chunks
                ]
            )
        )

        # --------------------------------------------------
        # Store all chunks in Qdrant
        # --------------------------------------------------

        self.vector_store.upsert_chunks(
            chunks=all_chunks,
            embeddings=embeddings,
        )

        print(
            f"Indexed {len(all_chunks)} chunks "
            f"into Qdrant."
        )
