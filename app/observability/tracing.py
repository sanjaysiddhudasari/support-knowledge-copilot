"""Observability for the RAG pipeline (LangSmith).

Design rules, in priority order:

1. Tracing is **optional**. With tracing disabled, unconfigured, or the SDK
   missing, every helper here degrades to a no-op and the pipeline behaves
   exactly as it did before.
2. A tracing failure must never fail a RAG request. All LangSmith interaction
   is wrapped so exceptions cannot escape.
3. Only identifiers and metadata are attached to spans — never document bodies,
   prompts, credentials or auth tokens.

LangSmith records run latency itself; ``latency_ms`` is attached as metadata
too so it is visible in the metadata panel and available to filters.
"""

from __future__ import annotations

import os
from typing import Any

try:  # langsmith is an optional runtime dependency
    from langsmith import trace as _ls_trace
    from langsmith.utils import tracing_is_enabled as _tracing_is_enabled
except Exception:  # pragma: no cover - exercised by the missing-SDK test
    _ls_trace = None
    _tracing_is_enabled = None


def tracing_enabled() -> bool:
    """True only when the SDK is present, tracing is turned on, and a key exists.

    Requiring the API key too keeps ``LANGSMITH_TRACING=true`` alone inert
    instead of producing runs that can never be uploaded.
    """

    if _ls_trace is None or _tracing_is_enabled is None:
        return False

    try:
        if not _tracing_is_enabled():
            return False
    except Exception:
        return False

    return bool(
        os.getenv("LANGSMITH_API_KEY") or os.getenv("LANGCHAIN_API_KEY")
    )


class Span:
    """A tracing span that never raises, whatever the SDK does."""

    def __init__(self, context_manager=None):
        self._cm = context_manager
        self.run = None

    def __enter__(self) -> "Span":
        if self._cm is not None:
            try:
                self.run = self._cm.__enter__()
            except Exception:
                # Tracing could not start: continue as a no-op span.
                self._cm = None
                self.run = None

        return self

    def __exit__(self, exc_type, exc, traceback):
        if self._cm is None:
            # Never swallow the application's own exception.
            return False

        try:
            self._cm.__exit__(exc_type, exc, traceback)
        except Exception:
            pass

        # Whatever the SDK returns, the application's exception always
        # propagates: tracing must not be able to hide a real failure.
        return False

    # ------------------------------------------------------------------
    # Metadata helpers: no-ops when tracing is off, never raise otherwise.
    # ------------------------------------------------------------------

    def _apply(self, method: str, payload: Any) -> "Span":
        if self.run is not None:
            try:
                getattr(self.run, method)(payload)
            except Exception:
                pass

        return self

    def add_metadata(self, metadata: dict) -> "Span":
        return self._apply("add_metadata", dict(metadata or {}))

    def add_outputs(self, outputs: dict) -> "Span":
        return self._apply("add_outputs", dict(outputs or {}))

    def add_tags(self, tags: list) -> "Span":
        return self._apply("add_tags", list(tags or []))


def span(
    name: str,
    run_type: str = "chain",
    tags: list | None = None,
    metadata: dict | None = None,
    inputs: dict | None = None,
) -> Span:
    """Open a child span, or a safe no-op when tracing is unavailable."""

    if not tracing_enabled():
        return Span()

    try:
        context_manager = _ls_trace(
            name=name,
            run_type=run_type,
            tags=tags,
            metadata=metadata,
            inputs=inputs,
        )
    except Exception:
        return Span()

    return Span(context_manager)


def _chunk_of(result):
    """Resolve the chunk from either result shape used in this codebase."""

    if isinstance(result, dict):
        return result.get("chunk")

    return getattr(result, "chunk", None)


def describe_result(result) -> dict:
    """Metadata-only view of a retrieval result.

    Deliberately excludes ``chunk.text``: document contents are not sent to the
    tracing backend. Sensitive fields (tokens, headers, credentials) never
    appear here.
    """

    chunk = _chunk_of(result)

    if chunk is None:
        return {}

    described = {
        "chunk_id": getattr(chunk, "chunk_ids", None),
        "source": getattr(chunk, "source", None),
        "section": getattr(chunk, "section", None),
        "file_type": getattr(chunk, "file_type", None),
        "page": getattr(chunk, "page", None),
        "document_type": getattr(chunk, "document_type", None),
        "version": getattr(chunk, "version", None),
        "access_level": getattr(chunk, "access_level", None),
    }

    if isinstance(result, dict):
        described["retrieval_score"] = result.get("rrf_score")
        described["retrieval_method"] = (
            "hybrid" if "rrf_score" in result else None
        )
    else:
        described["retrieval_score"] = getattr(result, "score", None)
        # RetrievalResult.source is already "dense" or "bm25".
        described["retrieval_method"] = getattr(result, "source", None)

    return {
        key: value
        for key, value in described.items()
        if value is not None
    }


def usage_metadata(usage) -> dict:
    """Token usage from a provider response, when the provider reports it."""

    if usage is None:
        return {}

    reported = {}

    for source_field, target_field in (
        ("prompt_tokens", "input_tokens"),
        ("completion_tokens", "output_tokens"),
        ("total_tokens", "total_tokens"),
    ):
        value = getattr(usage, source_field, None)

        if value is None and isinstance(usage, dict):
            value = usage.get(source_field)

        if isinstance(value, (int, float)):
            reported[target_field] = int(value)

    return reported
