"""Observability tests.

No live LangSmith account is required: the tracer is either disabled or
replaced with in-memory fakes. The two guarantees under test are that tracing
never breaks a RAG request, and that the important metadata actually reaches
the spans.
"""

import time
from datetime import date
from types import SimpleNamespace

import pytest
from unittest.mock import MagicMock

from app.generation.generator import AnswerGenerator
from app.models.answer import Answerability, Citation
from app.models.chunk import Chunk
from app.observability import tracing
from app.observability.tracing import (
    describe_result,
    span,
    tracing_enabled,
    usage_metadata,
)
from app.retrieval.bm25 import BM25Retriever
from app.services.qa_service import _finish


def make_chunk(chunk_id="policy.md_chunk_1", text="secret document body"):
    return Chunk(
        chunk_ids=chunk_id,
        text=text,
        source="policy.md",
        section="General",
        last_updated=date(2026, 8, 1),
        document_type="guide",
        access_level="internal",
        version=1,
        file_type="markdown",
    )


# ---------------------------------------------------------------------------
# Fake tracer
# ---------------------------------------------------------------------------


class CapturingRun:
    """Stands in for a LangSmith RunTree: same metadata-mutator surface."""

    def __init__(self, name, run_type, tags, metadata, inputs):
        self.name = name
        self.run_type = run_type
        self.tags = list(tags or [])
        self.metadata = dict(metadata or {})
        self.inputs = dict(inputs or {})
        self.outputs = {}

    def add_metadata(self, metadata):
        self.metadata.update(metadata or {})
        return self

    def add_outputs(self, outputs):
        self.outputs.update(outputs or {})
        return self

    def add_tags(self, tags):
        self.tags.extend(tags or [])
        return self


class FakeContextManager:
    def __init__(self, run):
        self.run = run

    def __enter__(self):
        return self.run

    def __exit__(self, exc_type, exc, tb):
        return False


def install_fake_tracer(monkeypatch, capture=None):
    """Enable tracing and capture every span in memory."""

    runs = capture if capture is not None else []

    def fake_trace(name, run_type="chain", tags=None, metadata=None, inputs=None):
        run = CapturingRun(name, run_type, tags, metadata, inputs)
        runs.append(run)
        return FakeContextManager(run)

    monkeypatch.setattr(tracing, "_ls_trace", fake_trace)
    monkeypatch.setattr(tracing, "_tracing_is_enabled", lambda: True)
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-key")

    return runs


def find(runs, name):
    matches = [run for run in runs if run.name == name]
    assert matches, f"no span named {name!r}; got {[r.name for r in runs]}"
    return matches[0]


# ---------------------------------------------------------------------------
# Configuration / fail-safety
# ---------------------------------------------------------------------------


def test_tracing_disabled_without_configuration(monkeypatch):
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)

    assert tracing_enabled() is False

    executed = False

    with span("RAG Query", run_type="chain") as run:
        executed = True
        run.add_metadata({"confidence": 0.91})

    assert executed is True
    assert run.run is None


def test_tracing_enabled_requires_flag_and_key(monkeypatch):
    monkeypatch.setattr(tracing, "_tracing_is_enabled", lambda: True)
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-key")

    assert tracing_enabled() is True

    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    monkeypatch.delenv("LANGCHAIN_API_KEY", raising=False)

    assert tracing_enabled() is False


def test_missing_sdk_does_not_break_anything(monkeypatch):
    monkeypatch.setattr(tracing, "_ls_trace", None)
    monkeypatch.setattr(tracing, "_tracing_is_enabled", None)
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-key")
    monkeypatch.setenv("LANGSMITH_TRACING", "true")

    assert tracing_enabled() is False

    with span("RAG Query") as run:
        run.add_outputs({"answer_chars": 3})

    assert run.run is None


def test_tracer_constructor_failure_is_swallowed(monkeypatch):
    def exploding_trace(*args, **kwargs):
        raise RuntimeError("langsmith unreachable")

    monkeypatch.setattr(tracing, "_ls_trace", exploding_trace)
    monkeypatch.setattr(tracing, "_tracing_is_enabled", lambda: True)
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-key")

    with span("RAG Query") as run:
        run.add_metadata({"confidence": 0.5})

    assert run.run is None


def test_run_method_failure_is_swallowed(monkeypatch):
    class BrokenRun(CapturingRun):
        def add_metadata(self, metadata):
            raise RuntimeError("serialization failed")

        def add_outputs(self, outputs):
            raise RuntimeError("serialization failed")

    def fake_trace(name, run_type="chain", tags=None, metadata=None, inputs=None):
        return FakeContextManager(
            BrokenRun(name, run_type, tags, metadata, inputs)
        )

    monkeypatch.setattr(tracing, "_ls_trace", fake_trace)
    monkeypatch.setattr(tracing, "_tracing_is_enabled", lambda: True)
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-key")

    with span("RAG Query") as run:
        run.add_metadata({"confidence": 0.5}).add_outputs({"x": 1})


def test_application_exception_still_propagates(monkeypatch):
    install_fake_tracer(monkeypatch)

    with pytest.raises(ValueError):
        with span("RAG Query"):
            raise ValueError("real application error")


def test_suppressing_context_manager_cannot_hide_errors(monkeypatch):
    """Even an SDK context manager that returns True must not eat the error."""

    class SuppressingContextManager:
        def __enter__(self):
            return CapturingRun("RAG Query", "chain", [], {}, {})

        def __exit__(self, exc_type, exc, tb):
            return True

    monkeypatch.setattr(
        tracing,
        "_ls_trace",
        lambda *args, **kwargs: SuppressingContextManager(),
    )
    monkeypatch.setattr(tracing, "_tracing_is_enabled", lambda: True)
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-key")

    with pytest.raises(ValueError):
        with span("RAG Query"):
            raise ValueError("real application error")


def test_application_exception_propagates_without_tracing():
    with pytest.raises(ValueError):
        with span("RAG Query"):
            raise ValueError("real application error")


# ---------------------------------------------------------------------------
# Metadata helpers
# ---------------------------------------------------------------------------


def test_describe_result_never_includes_document_text():
    described = describe_result({"chunk": make_chunk(), "rrf_score": 0.5})

    assert "text" not in described
    assert "secret document body" not in str(described)
    assert described["chunk_id"] == "policy.md_chunk_1"
    assert described["source"] == "policy.md"
    assert described["file_type"] == "markdown"
    assert described["access_level"] == "internal"
    assert described["retrieval_method"] == "hybrid"


def test_describe_result_supports_object_shape():
    from app.models.retrieval import RetrievalResult

    result = RetrievalResult(
        chunk=make_chunk(),
        score=0.42,
        rank=1,
        source="dense",
    )

    described = describe_result(result)

    assert described["retrieval_score"] == 0.42
    assert described["retrieval_method"] == "dense"
    assert "text" not in described


def test_usage_metadata_only_reports_what_is_present():
    usage = SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15)

    assert usage_metadata(usage) == {
        "input_tokens": 10,
        "output_tokens": 5,
        "total_tokens": 15,
    }
    assert usage_metadata(None) == {}
    assert usage_metadata(SimpleNamespace()) == {}


# ---------------------------------------------------------------------------
# Pipeline metadata (spans actually carry what the spec asks for)
# ---------------------------------------------------------------------------


def test_bm25_span_records_retrieval_metadata(monkeypatch):
    runs = install_fake_tracer(monkeypatch)

    retriever = BM25Retriever()
    retriever.build_index(
        [
            make_chunk("a.md_chunk_1", "forgot password reset link"),
            make_chunk("b.md_chunk_1", "billing invoice settings"),
            make_chunk("c.md_chunk_1", "upload limit storage"),
        ]
    )

    results = retriever.retrieve("forgot password", top_k=2)

    run = find(runs, "BM25 Retrieval")

    assert run.run_type == "retriever"
    assert run.metadata["retrieval_type"] == "bm25"
    assert run.metadata["top_k"] == 2
    assert run.metadata["result_count"] == len(results) == 2
    assert run.metadata["latency_ms"] >= 0
    assert "rag" in run.tags and "bm25" in run.tags
    assert run.inputs["query"] == "forgot password"
    assert run.outputs["retrieved"][0]["chunk_id"]
    assert all("text" not in item for item in run.outputs["retrieved"])


def test_generation_span_records_model_and_token_usage(monkeypatch):
    runs = install_fake_tracer(monkeypatch)

    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "Answer text [a.md_chunk_1]"
    mock_client.chat.completions.create.return_value = MagicMock(
        choices=[mock_choice],
        usage=SimpleNamespace(
            prompt_tokens=11, completion_tokens=7, total_tokens=18
        ),
    )

    generator = AnswerGenerator.__new__(AnswerGenerator)
    generator.client = mock_client
    generator.model = "test-model"

    result = generator.generate("query", [{"chunk": make_chunk()}])

    assert result.answer == "Answer text [a.md_chunk_1]"

    generation = find(runs, "Generation")

    assert generation.run_type == "llm"
    assert generation.metadata["model"] == "test-model"
    assert generation.metadata["total_tokens"] == 18
    assert generation.metadata["input_tokens"] == 11
    assert generation.metadata["output_tokens"] == 7
    assert generation.metadata["latency_ms"] >= 0
    # The prompt/context is not sent to the tracing backend.
    assert "secret document body" not in str(generation.inputs)
    assert "context" not in generation.inputs

    preparation = find(runs, "Context Preparation")
    assert preparation.metadata["chunk_count"] == 1
    assert preparation.metadata["context_chars"] > 0


def test_citation_verification_span_records_counts(monkeypatch):
    runs = install_fake_tracer(monkeypatch)

    from app.generation.citation_verifier import CitationVerifier

    verifier = CitationVerifier.__new__(CitationVerifier)
    verifier.model = "test-model"
    monkeypatch.setattr(
        verifier,
        "_verify_claim",
        lambda claim, evidence: {"supported": True, "explanation": "ok"},
    )

    verified = verifier.verify(
        [
            Citation(chunk_id="policy.md_chunk_1", claim="claim one"),
            Citation(chunk_id="missing.md_chunk_9", claim="claim two"),
        ],
        [{"chunk": make_chunk()}],
    )

    assert len(verified) == 2

    run = find(runs, "Citation Verification")

    assert run.metadata["citation_count"] == 2
    assert run.metadata["resolved_count"] == 1
    assert run.metadata["unresolved_count"] == 1
    assert run.metadata["supported_count"] == 1
    assert run.metadata["unsupported_count"] == 1
    assert run.metadata["citation_validity"] == 0.5
    assert run.metadata["citation_support"] == 0.5
    assert run.metadata["model"] == "test-model"


def test_query_summary_records_confidence_and_answerability():
    run = CapturingRun("RAG Query", "chain", [], {}, {})

    result = {
        "answer": "answer text",
        "citations": [
            Citation(chunk_id="a.md_chunk_1", claim="c", supported=True),
            Citation(chunk_id="b.md_chunk_1", claim="c", supported=False),
        ],
        "answerability": Answerability(answerable=True, explanation="ok"),
        "confidence": 0.91,
        "confidence_breakdown": {},
    }

    assert _finish(run, time.perf_counter(), "hybrid", result) is result

    assert run.metadata["confidence"] == 0.91
    assert run.metadata["answerable"] is True
    assert run.metadata["citation_count"] == 2
    assert run.metadata["supported_citations"] == 1
    assert run.metadata["retrieval_strategy"] == "hybrid"
    assert "answerable" in run.tags
    assert run.outputs["citation_chunk_ids"] == [
        "a.md_chunk_1",
        "b.md_chunk_1",
    ]


def test_unanswerable_summary_tags_the_run():
    run = CapturingRun("RAG Query", "chain", [], {}, {})

    _finish(
        run,
        time.perf_counter(),
        "dense",
        {
            "answer": "insufficient",
            "citations": [],
            "answerability": Answerability(
                answerable=False, explanation="not enough"
            ),
            "confidence": 0.0,
            "confidence_breakdown": {},
        },
    )

    assert "unanswerable" in run.tags
    assert run.metadata["citation_count"] == 0
    assert run.metadata["confidence"] == 0.0


# ---------------------------------------------------------------------------
# Regression: observability must not change retrieval behaviour
# ---------------------------------------------------------------------------


def _bm25_chunk_ids(retriever, query, top_k=5):
    return [
        result.chunk.chunk_ids
        for result in retriever.retrieve(query, top_k=top_k)
    ]


def test_retrieval_results_are_identical_with_broken_tracing(monkeypatch):
    retriever = BM25Retriever()
    retriever.build_index(
        [
            make_chunk("a.md_chunk_1", "forgot password reset link email"),
            make_chunk("b.md_chunk_1", "billing invoice settings plan"),
            make_chunk("c.md_chunk_1", "upload limit storage file size"),
            make_chunk("d.md_chunk_1", "password policy minimum length"),
        ]
    )

    baseline = _bm25_chunk_ids(retriever, "password reset")

    def exploding_trace(*args, **kwargs):
        raise RuntimeError("langsmith is down")

    monkeypatch.setattr(tracing, "_ls_trace", exploding_trace)
    monkeypatch.setattr(tracing, "_tracing_is_enabled", lambda: True)
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-key")

    with_tracing = _bm25_chunk_ids(retriever, "password reset")

    assert with_tracing == baseline
    assert baseline


def test_query_endpoint_still_succeeds_with_broken_tracing(monkeypatch):
    """A RAG request must succeed even when every trace attempt fails."""

    import os

    os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
    os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
    os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-service-key")

    from fastapi.testclient import TestClient

    from app.api import routes
    from app.auth.dependencies import get_current_user
    from app.auth.models import User
    from app.main import app

    def exploding_trace(*args, **kwargs):
        raise RuntimeError("langsmith is down")

    monkeypatch.setattr(tracing, "_ls_trace", exploding_trace)
    monkeypatch.setattr(tracing, "_tracing_is_enabled", lambda: True)
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-key")

    class FakeQA:
        def answer(self, query, user_access_level="public", user_id=None):
            return {
                "answer": "Answer text.",
                "answerability": SimpleNamespace(answerable=True),
                "citations": [],
                "confidence": 0.5,
            }

    monkeypatch.setattr(routes, "_qa_service", FakeQA())

    app.dependency_overrides[get_current_user] = lambda: User(
        id="1", email="user@example.com", access_level="public"
    )

    try:
        with TestClient(app) as client:
            response = client.post("/api/query", json={"query": "how?"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["answer"] == "Answer text."
