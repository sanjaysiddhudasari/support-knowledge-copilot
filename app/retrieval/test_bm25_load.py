from app.retrieval.bm25 import BM25Retriever


BM25_INDEX_PATH = "data/bm25/index.joblib"


def main():

    retriever = BM25Retriever()

    retriever.load(BM25_INDEX_PATH)

    query = "forgot password"

    results = retriever.retrieve(
        query=query,
        top_k=4,
    )

    print(f"\nQuery: {query}\n")

    for rank, result in enumerate(results, start=1):

        chunk = result.chunk

        print("=" * 60)
        print(f"Rank: {rank}")
        print(f"Score: {result.score:.4f}")
        print(f"Chunk ID: {chunk.chunk_ids}")
        print(f"Section: {chunk.section}")
        print(f"Text:\n{chunk.text}")


if __name__ == "__main__":
    main()