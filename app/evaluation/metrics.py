def hit_at_k(
    retrieved_ids: list[str],
    expected_ids: list[str],
    k: int,
) -> float:

    if not expected_ids:
        return 0.0

    retrieved = set(retrieved_ids[:k])
    expected = set(expected_ids)

    return float(bool(retrieved & expected))


def recall_at_k(
    retrieved_ids: list[str],
    expected_ids: list[str],
    k: int,
) -> float:

    if not expected_ids:
        return 0.0

    retrieved = set(retrieved_ids[:k])
    expected = set(expected_ids)

    return len(
        retrieved & expected
    ) / len(expected)


def no_answer_accuracy(
    predicted_answerable: bool,
    expected_answerable: bool,
) -> float:

    return float(
        predicted_answerable
        == expected_answerable
    )