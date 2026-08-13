from app.retrieval.retriever import DenseRetriever


def main():

    retriever = DenseRetriever()

    query = "I forgot my password. How can I access my account?"

    results = retriever.retrieve(
        query=query,
        top_k=4,
    )

    print(f"\nQuery: {query}\n")

    for rank, result in enumerate(results, start=1):

        score, payload = result

        print("=" * 60)
        print(f"Rank: {rank}")
        print(f"Score: {float(score):.4f}")
        print(f"Chunk ID: {payload['chunk_ids']}")
        print(f"Source: {payload['source']}")
        print(f"Section: {payload['section']}")
        print(f"Text:\n{payload['text']}")


if __name__ == "__main__":
    main()