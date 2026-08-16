import json
from pathlib import Path

from app.services.retrieval_service import RetrievalService


DATASET_PATH = "data/golden/golden_dataset.json"


def get_chunk_ids(results):

    chunk_ids = []

    for result in results:

        if isinstance(result, dict):

            chunk = result["chunk"]

        else:

            chunk = result.chunk

        chunk_ids.append(chunk.chunk_ids)

    return chunk_ids


def analyze_question(
    service,
    item,
    candidate_k=20,
):

    query = item["question"]
    expected = item["expected_chunks"]

    stages = service.retrieve_diagnostic(
        query=query,
        candidate_k=candidate_k,
    )

    stage_ids = {
        name: get_chunk_ids(results)
        for name, results in stages.items()
    }

    diagnostics = {}

    for stage, ids in stage_ids.items():

        diagnostics[stage] = {
            chunk_id: (
                ids.index(chunk_id) + 1
                if chunk_id in ids
                else None
            )
            for chunk_id in expected
        }

    return {
        "id": item["id"],
        "question": query,
        "expected_chunks": expected,
        "stages": stage_ids,
        "expected_ranks": diagnostics,
    }


def main():

    path = Path(DATASET_PATH)

    with open(
        path,
        "r",
        encoding="utf-8",
    ) as file:

        questions = json.load(file)

    service = RetrievalService()

    results = []

    for item in questions:

        result = analyze_question(
            service=service,
            item=item,
            candidate_k=20,
        )

        results.append(result)

    output_path = Path(
        "data/golden/retrieval_diagnostics.json"
    )

    with open(
        output_path,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            results,
            file,
            indent=2,
        )

    print("=" * 70)
    print("RETRIEVAL DIAGNOSTICS COMPLETE")
    print("=" * 70)
    print(
        f"Questions analyzed: {len(results)}"
    )
    print(
        f"Saved to: {output_path}"
    )


if __name__ == "__main__":
    main()