from app.retrieval.bm25 import BM25Retriever
from app.retrieval.hybrid import HybridRetriever
from app.retrieval.retriever import DenseRetriever
from app.retrieval.reranker import Reranker


BM25_INDEX_PATH = "data/bm25/index.joblib"


class RetrievalService:

    def __init__(self):

        self.dense_retriever = DenseRetriever()

        self.bm25_retriever = BM25Retriever()
        self.bm25_retriever.load(
            BM25_INDEX_PATH
        )

        self.hybrid_retriever = HybridRetriever(
            dense_retriever=self.dense_retriever,
            bm25_retriever=self.bm25_retriever,
        )

        self.reranker = Reranker()

    def retrieve(
        self,
        query: str,
        strategy: str = "hybrid_rerank",
        top_k: int = 5,
        candidate_k: int = 20,
    ):

        if strategy == "dense":

            return self.dense_retriever.retrieve(
                query=query,
                top_k=top_k,
            )

        if strategy == "bm25":

            return self.bm25_retriever.retrieve(
                query=query,
                top_k=top_k,
            )

        if strategy == "hybrid":

            return self.hybrid_retriever.retrieve(
                query=query,
                top_k=top_k,
                candidate_k=candidate_k,
            )

        if strategy == "hybrid_rerank":

            candidates = (
                self.hybrid_retriever.retrieve(
                    query=query,
                    top_k=candidate_k,
                )
            )

            return self.reranker.rerank(
                query=query,
                results=candidates,
                top_k=top_k,
            )

        raise ValueError(
            f"Unknown retrieval strategy: {strategy}"
        )