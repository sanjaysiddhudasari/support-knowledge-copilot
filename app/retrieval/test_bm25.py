from app.ingestion.chunker import chunk_document
from app.ingestion.loader import load_document
from app.retrieval.bm25 import BM25Retriever


def main():

    source = "password-policy.md"

    document = load_document(
        f"data/raw/{source}"
    )

    chunks = chunk_document(
        document,
        version=1,
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