from pathlib import Path
import hashlib
import json
import os

from app.ingestion.chunker import chunk_document
from app.ingestion.loader import (
    SUPPORTED_EXTENSIONS,
    get_loader,
    load_document,
)
from app.retrieval.vector_store import VectorStore
from app.retrieval.bm25 import BM25Retriever

BM25_INDEX_PATH = "data/bm25/index.joblib"
MANIFEST_PATH = Path("data/index/manifest.json")


class Indexer:

    def __init__(self, manifest_path=MANIFEST_PATH):

        self.manifest_path = Path(manifest_path)

        self.vector_store = VectorStore()
        self.bm25_retriever = BM25Retriever()

        self.embedding_service = None
        if not (os.getenv("QDRANT_URL") and os.getenv("QDRANT_API_KEY")):
            from app.retrieval.embedding import EmbeddingService
            self.embedding_service = EmbeddingService()

    def _load_manifest(self):
        if not self.manifest_path.exists():
            return {"documents": {}}

        with open(self.manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _calculate_hash(self, path: Path) -> str:
        content = path.read_bytes()
        return hashlib.sha256(content).hexdigest()

    def _discover_files(self, directory: Path) -> list[Path]:
        """Return every supported document in ``directory``, sorted by name.

        This replaces the previous Markdown-only ``glob("*.md")`` discovery.
        Supported extensions are owned by the ingestion layer.
        """

        if not directory.exists():
            return []

        return sorted(
            (
                path
                for path in directory.iterdir()
                if path.is_file()
                and path.suffix.lower() in SUPPORTED_EXTENSIONS
            ),
            key=lambda path: path.name,
        )

    def _load_chunks(self, path: Path, version: int) -> list:
        """Load and chunk a single supported document."""

        document = load_document(str(path))

        return chunk_document(document, version=version)

    def _get_changes(self, directory: Path):

        manifest = self._load_manifest()
        documents = manifest.get("documents", {})

        current_files = {
            path.name: path
            for path in self._discover_files(directory)
        }

        new_files = []
        modified_files = []
        deleted_files = []
        unchanged_files = []

        for filename, path in current_files.items():
            current_hash = self._calculate_hash(path)

            old_record = documents.get(filename)

            if old_record is None:
                new_files.append(path)

            elif old_record["content_hash"] == current_hash:
                unchanged_files.append(path)

            else:
                modified_files.append(path)

        for filename in documents:
            if filename not in current_files:
                deleted_files.append(filename)

        return {
            "new": new_files,
            "modified": modified_files,
            "unchanged": unchanged_files,
            "deleted": deleted_files,
        }

    def _save_manifest(self, manifest):
        self.manifest_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

    def _build_embeddings(self, chunks):
        if not chunks:
            return None

        if self.embedding_service is not None:
            return self.embedding_service.embed_texts(
                [chunk.text for chunk in chunks]
            )

        return None

    def index_corpus(
        self,
        directory: str = "data/raw",
    ):

        directory_path = Path(directory)

        documents = self._discover_files(directory_path)

        if not documents:
            raise RuntimeError(
                f"No supported documents found in {directory}"
            )

        all_chunks = []

        print(f"Found {len(documents)} documents.")

        self.vector_store.create_collection()

        for path in documents:

            source = path.name

            chunks = self._load_chunks(path, version=1)

            all_chunks.extend(chunks)

            print(
                f"{source}: {len(chunks)} chunks"
            )

        print(
            f"\nTotal chunks: {len(all_chunks)}"
        )

        self.bm25_retriever.build_index(all_chunks)
        self.bm25_retriever.save(BM25_INDEX_PATH)

        embeddings = self._build_embeddings(all_chunks)

        self.vector_store.upsert_chunks(
            chunks=all_chunks,
            embeddings=embeddings,
        )

        print(
            f"Indexed {len(all_chunks)} chunks into Qdrant."
        )

        manifest = {"documents": {}}

        for path in documents:
            manifest["documents"][path.name] = {
                "content_hash": self._calculate_hash(path),
                "chunk_ids": [
                    chunk.chunk_ids
                    for chunk in all_chunks
                    if chunk.source == path.name
                ],
                "version": 1,
                "file_type": get_loader(path).file_type,
            }

        self._save_manifest(manifest)

        print(
            f"Saved manifest: {self.manifest_path}"
        )

    def index_incremental(
        self,
        directory: str = "data/raw",
    ):
        directory_path = Path(directory)

        changes = self._get_changes(directory_path)

        new_files = changes["new"]
        modified_files = changes["modified"]
        unchanged_files = changes["unchanged"]
        deleted_files = changes["deleted"]

        print("\nIncremental indexing")
        print("-" * 50)
        print(f"New:       {len(new_files)}")
        print(f"Modified:  {len(modified_files)}")
        print(f"Unchanged: {len(unchanged_files)}")
        print(f"Deleted:   {len(deleted_files)}")

        manifest = self._load_manifest()
        documents = manifest.setdefault(
            "documents",
            {},
        )

        for filename in deleted_files:

            old_record = documents.get(
                filename,
                {},
            )
            old_chunk_ids = old_record.get(
                "chunk_ids",
                [],
            )

            self.vector_store.delete_chunks(
                old_chunk_ids
            )

            documents.pop(
                filename,
                None,
            )

            print(
                f"Deleted document: {filename}"
            )

        for path in modified_files:

            filename = path.name

            old_record = documents.get(
                filename,
                {},
            )
            old_chunk_ids = old_record.get(
                "chunk_ids",
                [],
            )

            self.vector_store.delete_chunks(
                old_chunk_ids
            )

            print(
                f"Removed old chunks: {filename}"
            )

        files_to_index = (
            new_files + modified_files
        )

        all_new_chunks = []

        for path in files_to_index:

            source = path.name

            old_record = documents.get(
                source,
                {},
            )
            old_version = old_record.get(
                "version",
                0,
            )

            chunks = self._load_chunks(
                path,
                version=old_version + 1,
            )

            all_new_chunks.extend(chunks)

            documents[source] = {
                "content_hash": self._calculate_hash(path),
                "chunk_ids": [
                    chunk.chunk_ids
                    for chunk in chunks
                ],
                "version": old_version + 1,
                "file_type": get_loader(path).file_type,
            }

            print(
                f"{source}: {len(chunks)} chunks "
                f"(version {old_version + 1})"
            )

        if all_new_chunks:

            embeddings = self._build_embeddings(
                all_new_chunks
            )

            self.vector_store.upsert_chunks(
                chunks=all_new_chunks,
                embeddings=embeddings,
            )

            print(
                f"Indexed {len(all_new_chunks)} new chunks."
            )

        all_chunks = []

        for path in self._discover_files(directory_path):

            record = documents[path.name]

            chunks = self._load_chunks(
                path,
                version=record["version"],
            )

            all_chunks.extend(chunks)

        self.bm25_retriever.build_index(all_chunks)
        self.bm25_retriever.save(BM25_INDEX_PATH)

        self._save_manifest(manifest)

        print(
            f"Saved manifest: {self.manifest_path}"
        )

        print(
            "\nIncremental indexing complete."
        )
