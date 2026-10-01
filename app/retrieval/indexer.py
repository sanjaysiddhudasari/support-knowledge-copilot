from pathlib import Path
from datetime import date
import re
import hashlib
import json

from app.ingestion.chunker import chunk_markdown
from app.ingestion.loader import load_document
from app.retrieval.embedding import EmbeddingService
from app.retrieval.vector_store import VectorStore
from app.retrieval.bm25 import BM25Retriever

BM25_INDEX_PATH = "data/bm25/index.joblib"
MANIFEST_PATH = Path("data/index/manifest.json")


class Indexer:

    def __init__(self, manifest_path=MANIFEST_PATH):

        self.manifest_path = Path(manifest_path)

        self.embedding_service = EmbeddingService()
        self.vector_store = VectorStore()
        self.bm25_retriever = BM25Retriever()

    def _load_manifest(self):
        if not self.manifest_path.exists():
            return {"documents": {}}

        with open(self.manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)

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
            return text[match.end() :]

        return text

    def index_corpus(
        self,
        directory: str = "data/raw",
    ):

        directory_path = Path(directory)

        documents = sorted(directory_path.glob("*.md"))

        if not documents:
            raise RuntimeError(f"No Markdown documents found in {directory}")

        all_chunks = []

        print(f"Found {len(documents)} documents.")

        for path in documents:

            source = path.name

            raw_text = load_document(str(path))

            metadata = self._parse_metadata(raw_text)

            text = self._remove_front_matter(raw_text)

            chunks = chunk_markdown(
                text=text,
                source=source,
                last_updated=metadata["last_updated"],
                document_type=metadata["document_type"],
                access_level=metadata["access_level"],
                version=1,
            )

            all_chunks.extend(chunks)

            print(f"{source}: " f"{len(chunks)} chunks")

        print(f"\nTotal chunks: " f"{len(all_chunks)}")

        # --------------------------------------------------
        # Build BM25 ONCE using the complete corpus
        # --------------------------------------------------

        self.bm25_retriever.build_index(all_chunks)

        self.bm25_retriever.save(BM25_INDEX_PATH)

        print(f"Saved BM25 index: " f"{BM25_INDEX_PATH}")

        # --------------------------------------------------
        # Create embeddings for all chunks
        # --------------------------------------------------

        embeddings = self.embedding_service.embed_texts(
            [chunk.text for chunk in all_chunks]
        )

        # --------------------------------------------------
        # Store all chunks in Qdrant
        # --------------------------------------------------

        self.vector_store.upsert_chunks(
            chunks=all_chunks,
            embeddings=embeddings,
        )

        print(f"Indexed {len(all_chunks)} chunks " f"into Qdrant.")

        # --------------------------------------------------
        # Save indexing manifest
        # --------------------------------------------------

        manifest = {"documents": {}}

        for path in documents:
            manifest["documents"][path.name] = {
                "content_hash": self._calculate_hash(path),
                "chunk_ids": [
                    chunk.chunk_ids for chunk in all_chunks if chunk.source == path.name
                ],
                "version":1,
            }

        self._save_manifest(manifest)

        print(f"Saved manifest: " f"{self.manifest_path}")

    def _calculate_hash(self, path: Path) -> str:
        content = path.read_bytes()
        return hashlib.sha256(content).hexdigest()

    def _get_changes(self, directory: Path):

        manifest = self._load_manifest()
        documents = manifest.get("documents", {})

        current_files = {path.name: path for path in directory.glob("*.md")}

        new_files = []
        modified_files = []
        deleted_files = []
        unchanged_files = []

        for filename, path in current_files.items():
            current_hash = self._calculate_hash(path=path)

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
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)

        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

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
        documents = manifest.setdefault("documents", {})

        # --------------------------------------------------
        # 1. Delete chunks belonging to deleted documents
        # --------------------------------------------------

        for filename in deleted_files:

            old_record = documents.get(filename, {})
            old_chunk_ids = old_record.get("chunk_ids", [])

            self.vector_store.delete_chunks(old_chunk_ids)

            documents.pop(filename, None)

            print(f"Deleted document: {filename}")

        # --------------------------------------------------
        # 2. Delete old chunks for modified documents
        # --------------------------------------------------

        for path in modified_files:

            filename = path.name

            old_record = documents.get(filename, {})
            old_chunk_ids = old_record.get("chunk_ids", [])

            self.vector_store.delete_chunks(old_chunk_ids)

            print(f"Removed old chunks: {filename}")

        # --------------------------------------------------
        # 3. Process new + modified documents
        # --------------------------------------------------

        files_to_index = new_files + modified_files

        all_new_chunks = []

        for path in files_to_index:
            source = path.name

            old_record = documents.get(source, {})
            old_version = old_record.get("version", 0)

            raw_text = load_document(str(path))

            metadata = self._parse_metadata(raw_text)
            text = self._remove_front_matter(raw_text)

            chunks = chunk_markdown(
                text=text,
                source=source,
                last_updated=metadata["last_updated"],
                document_type=metadata["document_type"],
                access_level=metadata["access_level"],
                version=old_version+1,
            )

            all_new_chunks.extend(chunks)

            documents[source] = {
                "content_hash": self._calculate_hash(path),
                "chunk_ids": [
                    chunk.chunk_ids
                    for chunk in chunks
                ],
                "version": old_version + 1,
            }

            print(
                f"{source}: {len(chunks)} chunks "
                f"(version {old_version + 1})"
            )

        # --------------------------------------------------
        # 4. Embed only new/modified chunks
        # --------------------------------------------------

        if all_new_chunks:

            embeddings = self.embedding_service.embed_texts(
                [chunk.text for chunk in all_new_chunks]
            )

            # --------------------------------------------------
            # 5. Upsert only new/modified chunks
            # --------------------------------------------------

            self.vector_store.upsert_chunks(
                chunks=all_new_chunks,
                embeddings=embeddings,
            )

            print(f"Indexed {len(all_new_chunks)} new chunks.")

        # --------------------------------------------------
        # 6. Rebuild BM25
        # --------------------------------------------------

        all_chunks = []

        for path in sorted(directory_path.glob("*.md")):

            raw_text = load_document(str(path))

            metadata = self._parse_metadata(raw_text)

            text = self._remove_front_matter(raw_text)

            record = documents[path.name]

            chunks = chunk_markdown(
                text=text,
                source=path.name,
                last_updated=metadata["last_updated"],
                document_type=metadata["document_type"],
                access_level=metadata["access_level"],
                version=record["version"],
            )

            all_chunks.extend(chunks)

        self.bm25_retriever.build_index(all_chunks)

        self.bm25_retriever.save(BM25_INDEX_PATH)

        # --------------------------------------------------
        # 7. Save manifest
        # --------------------------------------------------

        self._save_manifest(manifest)

        print(f"Saved manifest: {self.manifest_path}")

        print("\nIncremental indexing complete.")
