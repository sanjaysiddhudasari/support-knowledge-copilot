import json
from pathlib import Path

from app.services.retrieval_service import RetrievalService
from app.evaluation.metrics import (
    hit_at_k,
    recall_at_k,
)


class Evaluator:

    def __init__(
        self,
        dataset_path: str = (
            "data/golden/golden_dataset.json"
        ),
    ):

        path = Path(dataset_path)

        with open(
            path,
            "r",
            encoding="utf-8",
        ) as file:

            self.questions = json.load(file)

        self.retrieval_service = (
            RetrievalService()
        )

    def evaluate_retrieval(
    self,
    strategy: str,
    max_k: int = 20,
    candidate_k: int = 20,
):

        evaluation_results = []

        for item in self.questions:

            query = item["question"]

            expected_ids = item["expected_chunks"]

            results = (
                self.retrieval_service.retrieve(
                    query=query,
                    strategy=strategy,
                    top_k=max_k,
                    candidate_k=candidate_k,
                )
            )

            retrieved_ids = [
                (
                    result["chunk"].chunk_ids
                    if isinstance(result, dict)
                    else result.chunk.chunk_ids
                )
                for result in results
            ]

            result = {
                "id": item["id"],
                "question": query,
                "expected_chunks": expected_ids,
                "retrieved_chunks": retrieved_ids,
            }

            for k in [5, 10, 20]:

                result[f"hit_at_{k}"] = hit_at_k(
                    retrieved_ids,
                    expected_ids,
                    k,
                )

                result[f"recall_at_{k}"] = recall_at_k(
                    retrieved_ids,
                    expected_ids,
                    k,
                )

            evaluation_results.append(result)

        return evaluation_results

    @staticmethod
    def summarize(results):

        if not results:
            return {
                "hit_at_5": 0.0,
                "recall_at_5": 0.0,
                "hit_at_10": 0.0,
                "recall_at_10": 0.0,
                "hit_at_20": 0.0,
                "recall_at_20": 0.0,
            }

        summary = {}

        for k in [5, 10, 20]:

            summary[f"hit_at_{k}"] = round(
                sum(
                    r[f"hit_at_{k}"]
                    for r in results
                ) / len(results),
                4,
            )

            summary[f"recall_at_{k}"] = round(
                sum(
                    r[f"recall_at_{k}"]
                    for r in results
                ) / len(results),
                4,
            )

        return summary
