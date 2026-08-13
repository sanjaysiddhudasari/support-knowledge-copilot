from datetime import date

from app.ingestion.chunker import chunk_markdown
from app.ingestion.loader import load_document
from app.retrieval.bm25 import BM25Retriever


def main():

    source = "password-policy.md"

    text = load_document(
        f"data/raw/{source}"
    )

    chunks = chunk_markdown(
        text=text,
        source=source,
        last_updated=date(2026, 8, 1),
        document_type="policy",
        access_level="internal",
    )

    retriever = BM25Retriever()

    retriever.build_index(chunks)

    query = "forgot password"

    results = retriever.retrieve(
        query=query,
        top_k=4,
    )

    print(f"\nQuery: {query}\n")

    for rank, result in enumerate(results, start=1):

        chunk = result["chunk"]

        print("=" * 60)
        print(f"Rank: {rank}")
        print(f"Score: {result['score']:.4f}")
        print(f"Chunk ID: {chunk.chunk_ids}")
        print(f"Section: {chunk.section}")
        print(f"Text:\n{chunk.text}")


if __name__ == "__main__":
    main()