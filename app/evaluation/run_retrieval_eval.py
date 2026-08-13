import json
from pathlib import Path

from app.evaluation.evaluator import Evaluator


STRATEGIES = [
    "dense",
    "bm25",
    "hybrid",
    "hybrid_rerank",
]


def main():

    evaluator = Evaluator()

    output = {}

    for strategy in STRATEGIES:

        print("\n" + "=" * 70)
        print(
            f"EVALUATING: {strategy}"
        )
        print("=" * 70)

        results = (
            evaluator.evaluate_retrieval(
                strategy=strategy,
                max_k=20,
                candidate_k=20,
            )
        )

        summary = evaluator.summarize(
            results
        )

        output[strategy] = {
            "summary": summary,
            "questions": results,
        }

        for k in (5, 10, 20):
            print(f"Hit@{k}: {summary[f'hit_at_{k}']}")
            print(f"Recall@{k}: {summary[f'recall_at_{k}']}")

    output_path = Path(
        "data/golden/retrieval_eval.json"
    )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        output_path,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            output,
            file,
            indent=2,
        )

    print("\n" + "=" * 70)
    print("EVALUATION COMPLETE")
    print("=" * 70)
    print(
        f"Saved to: {output_path}"
    )


if __name__ == "__main__":
    main()  
