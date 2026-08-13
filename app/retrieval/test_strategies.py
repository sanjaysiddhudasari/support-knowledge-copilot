from app.services.retrieval_service import RetrievalService


def main():

    service = RetrievalService()

    query = "I forgot my password. How can I access my account?"

    strategies = [
        "dense",
        "bm25",
        "hybrid",
        "hybrid_rerank",
    ]

    for strategy in strategies:

        print("\n" + "=" * 70)
        print(f"STRATEGY: {strategy}")
        print("=" * 70)

        results = service.retrieve(
            query=query,
            strategy=strategy,
            top_k=5,
            candidate_k=20,
        )

        for rank, result in enumerate(
            results,
            start=1,
        ):

            # Dense and BM25 return RetrievalResult objects, while hybrid
            # strategies return dictionaries with scoring metadata.
            chunk = (
                result["chunk"]
                if isinstance(result, dict)
                else result.chunk
            )

            print(
                f"{rank}. "
                f"{chunk.chunk_ids} "
                f"-> {chunk.section}"
            )


if __name__ == "__main__":
    main()
