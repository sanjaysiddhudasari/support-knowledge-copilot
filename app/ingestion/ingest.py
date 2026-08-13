from datetime import date
from pathlib import Path
import re

from app.ingestion.chunker import chunk_markdown
from app.ingestion.loader import load_document


RAW_DIR = Path("data/raw")


def parse_metadata(text: str) -> dict:
    """
    Extract YAML-style front matter from a Markdown document.
    """

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


def remove_front_matter(text: str) -> str:
    """
    Remove YAML front matter before Markdown chunking.
    """

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


def ingest_document(path: Path):

    source = path.name

    raw_text = load_document(str(path))

    metadata = parse_metadata(raw_text)

    text = remove_front_matter(raw_text)

    chunks = chunk_markdown(
        text=text,
        source=source,
        last_updated=metadata["last_updated"],
        document_type=metadata["document_type"],
        access_level=metadata["access_level"],
    )

    return chunks


def main():

    documents = sorted(
        RAW_DIR.glob("*.md")
    )

    if not documents:
        raise RuntimeError(
            "No Markdown documents found in data/raw/"
        )

    total_chunks = 0

    print(
        f"Found {len(documents)} Markdown documents."
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

            print("\nText:")
            print(chunk.text)

    print("\n" + "=" * 70)
    print("INGESTION COMPLETE")
    print("=" * 70)
    print(f"Documents: {len(documents)}")
    print(f"Total chunks: {total_chunks}")


if __name__ == "__main__":
    main()