from app.retrieval.indexer import Indexer


def main():

    indexer = Indexer()

    indexer.vector_store.create_collection()

    indexer.index_corpus(
        directory="data/raw"
    )


if __name__ == "__main__":
    main()