from datetime import date, timedelta

from app.retrieval.freshness import FreshnessScorer


def test_newer_document_is_fresher():

    scorer = FreshnessScorer()

    today = date(2026, 10, 1)

    recent = scorer.score(
        last_updated=today - timedelta(days=5),
        reference_date=today,
    )

    old = scorer.score(
        last_updated=today - timedelta(days=300),
        reference_date=today,
    )

    assert recent > old


def test_future_date_does_not_break():

    scorer = FreshnessScorer()

    today = date(2026, 10, 1)

    score = scorer.score(
        last_updated=date(2026, 10, 5),
        reference_date=today,
    )

    assert score == 1.0