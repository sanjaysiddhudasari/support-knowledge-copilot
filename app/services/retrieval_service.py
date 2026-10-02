import os

from app.retrieval.access_control import AccessController
from app.retrieval.bm25 import BM25Retriever
from app.retrieval.hybrid import HybridRetriever
from app.retrieval.retriever import DenseRetriever
from app.retrieval.reranker import Reranker


BM25_INDEX_PATH = "data/bm25/index.joblib"


class RetrievalService:

    def __init__(self):
        self.dense_retriever = DenseRetriever()

        self.bm25_retriever = BM25Retriever()
        self.bm25_retriever.load(BM25_INDEX_PATH)

        self.hybrid_retriever = HybridRetriever(
            dense_retriever=self.dense_retriever,
            bm25_retriever=self.bm25_retriever,
        )

        self.strategy = os.getenv(
            "RETRIEVAL_STRATEGY",
            "hybrid_rerank",
        )

        self.reranker = (
            Reranker()
            if self.strategy == "hybrid_rerank"
            else None
        )

        self.access_controller = AccessController()

    def retrieve(
        self,
        query: str,
        strategy: str | None = None,
        top_k: int = 5,
        candidate_k: int = 10,
        user_access_level: str = "public",
    ):
        strategy = strategy or self.strategy

        if strategy == "dense":
            results = self.dense_retriever.retrieve(
                query=query,
                top_k=top_k,
            )

            return self.access_controller.filter_results(
                results,
                user_access_level=user_access_level,
            )

        if strategy == "bm25":
            results = self.bm25_retriever.retrieve(
                query=query,
                top_k=top_k,
            )

            return self.access_controller.filter_results(
                results,
                user_access_level=user_access_level,
            )

        if strategy == "hybrid":
            results = self.hybrid_retriever.retrieve(
                query=query,
                top_k=top_k,
                candidate_k=candidate_k,
            )

            return self.access_controller.filter_results(
                results,
                user_access_level=user_access_level,
            )

        if strategy == "hybrid_rerank":
            if self.reranker is None:
                self.reranker = Reranker()

            hybrid_results = self.hybrid_retriever.retrieve(
                query=query,
                top_k=top_k,
                candidate_k=candidate_k,
            )

            filtered_results = self.access_controller.filter_results(
                hybrid_results,
                user_access_level=user_access_level,
            )

            return self.reranker.rerank(
                query,
                filtered_results,
                top_k=top_k,
            )

        raise ValueError(
            f"Unknown retrieval strategy: {strategy}"
        )

    def retrieve_diagnostic(
        self,
        query: str,
        candidate_k: int = 20,
    ):
        dense_results = self.dense_retriever.retrieve(
            query=query,
            top_k=candidate_k,
        )

        bm25_results = self.bm25_retriever.retrieve(
            query=query,
            top_k=candidate_k,
        )

        hybrid_results = self.hybrid_retriever.retrieve(
            query=query,
            top_k=candidate_k,
        )

        reranked_results = (
            self.reranker.rerank(
                query=query,
                results=hybrid_results,
                top_k=candidate_k,
            )
            if self.reranker is not None
            else []
        )

        return {
            "dense": dense_results,
            "bm25": bm25_results,
            "hybrid": hybrid_results,
            "hybrid_rerank": reranked_results,
        }
