"""AccessController must accept both result shapes.

dense/bm25 return RetrievalResult objects; hybrid returns {"chunk", ...} dicts.
Both route through filter_results, so both must be filtered correctly.
"""

from datetime import date

import pytest

from app.models.chunk import Chunk
from app.models.retrieval import RetrievalResult
from app.retrieval.access_control import AccessController


def make_chunk(chunk_id: str, access_level: str) -> Chunk:
    return Chunk(
        chunk_ids=chunk_id,
        text="text",
        source="doc.md",
        section="General",
        last_updated=date(2026, 8, 1),
        document_type="guide",
        access_level=access_level,
    )


def test_filters_object_shape():
    controller = AccessController()

    results = [
        RetrievalResult(
            chunk=make_chunk("a.md_chunk_1", "public"),
            score=1.0,
            rank=1,
            source="dense",
        ),
        RetrievalResult(
            chunk=make_chunk("b.md_chunk_1", "admin"),
            score=0.9,
            rank=2,
            source="dense",
        ),
    ]

    kept = controller.filter_results(results, user_access_level="public")

    assert [result.chunk.chunk_ids for result in kept] == ["a.md_chunk_1"]


def test_filters_dict_shape():
    controller = AccessController()

    results = [
        {"chunk": make_chunk("a.md_chunk_1", "internal"), "rrf_score": 0.5},
        {"chunk": make_chunk("b.md_chunk_1", "public"), "rrf_score": 0.4},
    ]

    kept = controller.filter_results(results, user_access_level="internal")

    assert [result["chunk"].chunk_ids for result in kept] == [
        "a.md_chunk_1",
        "b.md_chunk_1",
    ]


def test_missing_chunk_fails_closed():
    """A result with no chunk is dropped rather than raising."""
    kept = AccessController().filter_results(
        [{"rrf_score": 0.5}],
        user_access_level="admin",
    )

    assert kept == []


def test_unknown_access_level_raises():
    with pytest.raises(ValueError):
        AccessController().filter_results([], user_access_level="superuser")
