from app.retrieval.retrieval_service import RetrievalService


def main():

    retrieval_service = RetrievalService()

    query = "I forgot my password. How can I access my account?"

    results = retrieval_service.retrieve(
        query=query,
        top_k=4,
    )

    print(f"\nQuery: {query}\n")

    for rank, result in enumerate(results, start=1):

        chunk = result["chunk"]

        print("=" * 60)
        print(f"Rank: {rank}")
        print(f"RRF Score: {result['rrf_score']:.6f}")
        print(f"Rerank Score: {result['rerank_score']:.6f}")
        print(f"Chunk ID: {chunk.chunk_ids}")
        print(f"Section: {chunk.section}")
        print(f"Source: {chunk.source}")
        print(f"Text:\n{chunk.text}")


if __name__ == "__main__":
    main()