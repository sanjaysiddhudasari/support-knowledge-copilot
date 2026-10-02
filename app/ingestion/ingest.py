from pathlib import Path

from app.ingestion.chunker import chunk_document
from app.ingestion.loader import SUPPORTED_EXTENSIONS, load_document


RAW_DIR = Path("data/raw")


def ingest_document(path: Path):
    """Load and chunk any supported document."""

    document = load_document(str(path))

    return chunk_document(document, version=1)


def discover_documents(directory: Path) -> list[Path]:
    """Return every supported document in ``directory``, sorted by name."""

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


def main():

    documents = discover_documents(RAW_DIR)

    if not documents:
        raise RuntimeError(
            "No supported documents found in data/raw/"
        )

    total_chunks = 0

    print(
        f"Found {len(documents)} documents."
    )

    for path in documents:

        chunks = ingest_document(path)

        total_chunks += len(chunks)

        print("\n" + "=" * 70)
        print(f"DOCUMENT: {path.name}")
        print(f"CHUNKS: {len(chunks)}")
        print("=" * 70)

        for chunk in chunks:

            print(
                f"\nChunk ID: {chunk.chunk_ids}"
            )

            print(
                f"Section: {chunk.section}"
            )

            print(
                f"Source: {chunk.source}"
            )

            print(
                f"Last Updated: {chunk.last_updated}"
            )

            print(
                f"Document Type: {chunk.document_type}"
            )

            print(
                f"Access Level: {chunk.access_level}"
            )

            if chunk.file_type is not None:
                print(
                    f"File Type: {chunk.file_type}"
                )

            if chunk.page is not None:
                print(
                    f"Page: {chunk.page}"
                )

            print("\nText:")
            print(chunk.text)

    print("\n" + "=" * 70)
    print("INGESTION COMPLETE")
    print("=" * 70)
    print(f"Documents: {len(documents)}")
    print(f"Total chunks: {total_chunks}")


if __name__ == "__main__":
    main()
