import json
from pathlib import Path


DIAGNOSTICS_PATH = (
    "data/golden/retrieval_diagnostics.json"
)


STAGES = [
    "dense",
    "bm25",
    "hybrid",
    "hybrid_rerank",
]


def recall_at_k(
    expected_ranks,
    k,
):
    if not expected_ranks:
        return 0.0

    found = sum(
        1
        for rank in expected_ranks.values()
        if rank is not None and rank <= k
    )

    return found / len(expected_ranks)


def main():

    with open(
        DIAGNOSTICS_PATH,
        "r",
        encoding="utf-8",
    ) as file:

        data = json.load(file)

    print("=" * 70)
    print("RETRIEVAL DIAGNOSTIC ANALYSIS")
    print("=" * 70)

    print(
        f"Questions: {len(data)}"
    )

    # --------------------------------------------------
    # Overall expected-chunk recall
    # --------------------------------------------------

    for k in [5, 10, 20]:

        print("\n" + "-" * 70)
        print(f"EXPECTED CHUNK RECALL@{k}")
        print("-" * 70)

        for stage in STAGES:

            total_expected = 0
            total_found = 0

            for item in data:

                expected_ranks = item[
                    "expected_ranks"
                ][stage]

                for rank in expected_ranks.values():

                    total_expected += 1

                    if (
                        rank is not None
                        and rank <= k
                    ):
                        total_found += 1

            recall = (
                total_found / total_expected
                if total_expected
                else 0.0
            )

            print(
                f"{stage:<16}"
                f"{recall:.4f} "
                f"({total_found}/{total_expected})"
            )

    # --------------------------------------------------
    # Single vs multi-chunk
    # --------------------------------------------------

    print("\n" + "=" * 70)
    print("SINGLE VS MULTI-CHUNK")
    print("=" * 70)

    groups = {
        "single_chunk": [],
        "multi_chunk": [],
    }

    for item in data:

        count = len(
            item["expected_chunks"]
        )

        if count == 1:
            groups["single_chunk"].append(item)

        elif count > 1:
            groups["multi_chunk"].append(item)

    for group_name, items in groups.items():

        print(
            f"\n{group_name}: "
            f"{len(items)} questions"
        )

        for stage in STAGES:

            total_expected = 0
            total_found = 0

            for item in items:

                ranks = item[
                    "expected_ranks"
                ][stage]

                for rank in ranks.values():

                    total_expected += 1

                    if (
                        rank is not None
                        and rank <= 5
                    ):
                        total_found += 1

            recall = (
                total_found / total_expected
                if total_expected
                else 0.0
            )

            print(
                f"  {stage:<14}"
                f"Recall@5 = {recall:.4f}"
            )

    # --------------------------------------------------
    # Where expected chunks disappear
    # --------------------------------------------------

    print("\n" + "=" * 70)
    print("STAGE-TO-STAGE LOSSES")
    print("=" * 70)

    transitions = [
        ("dense", "hybrid"),
        ("hybrid", "hybrid_rerank"),
    ]

    for previous, current in transitions:

        disappeared = 0
        total = 0

        for item in data:

            previous_ranks = item[
                "expected_ranks"
            ][previous]

            current_ranks = item[
                "expected_ranks"
            ][current]

            for chunk_id, previous_rank in (
                previous_ranks.items()
            ):

                if previous_rank is None:
                    continue

                total += 1

                current_rank = (
                    current_ranks.get(chunk_id)
                )

                if current_rank is None:
                    disappeared += 1

        loss_rate = (
            disappeared / total
            if total
            else 0.0
        )

        print(
            f"{previous} → {current}: "
            f"{disappeared}/{total} "
            f"({loss_rate:.4f})"
        )


if __name__ == "__main__":
    main()