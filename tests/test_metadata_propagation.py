"""file_type/page must survive the whole pipeline:

loader -> Chunk -> Qdrant payload -> retrieval result -> Citation -> API response
"""

import os
import pathlib
import sys
from datetime import date
from types import SimpleNamespace

# The auth client needs these at import time.
os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-service-key")

sys.path.insert(0, str(pathlib.Path(__file__).parent / "ingestion"))

from pdf_factory import build_pdf_bytes  # noqa: E402

from app.generation import citation_verifier as verifier_module  # noqa: E402
from app.ingestion.chunker import chunk_document  # noqa: E402
from app.ingestion.loader import load_document  # noqa: E402
from app.models.answer import Citation  # noqa: E402
from app.models.chunk import Chunk  # noqa: E402
from app.retrieval.retriever import DenseRetriever  # noqa: E402
from app.retrieval.vector_store import _build_payload  # noqa: E402


def make_chunk(**overrides) -> Chunk:
    values = {
        "chunk_ids": "manual.pdf_chunk_2",
        "text": "Alpha text",
        "source": "manual.pdf",
        "section": "Page 2",
        "last_updated": date(2026, 8, 1),
        "document_type": "guide",
        "access_level": "public",
        "version": 1,
        "file_type": "pdf",
        "page": 2,
    }
    values.update(overrides)
    return Chunk(**values)


# ---------------------------------------------------------------------------
# loader -> Chunk
# ---------------------------------------------------------------------------


def test_loader_to_chunk_preserves_file_type_and_page(tmp_path):
    path = tmp_path / "manual.pdf"
    path.write_bytes(build_pdf_bytes(["Alpha page", "Beta page"]))

    loaded = load_document(str(path))
    chunks = chunk_document(loaded)

    assert loaded.file_type == "pdf"
    assert all(chunk.file_type == "pdf" for chunk in chunks)
    assert [chunk.page for chunk in chunks] == [1, 2]


def test_markdown_chunks_carry_markdown_file_type(tmp_path):
    path = tmp_path / "policy.md"
    path.write_text("# Title\n\nBody.", encoding="utf-8")

    chunks = chunk_document(load_document(str(path)))

    assert chunks[0].file_type == "markdown"
    assert chunks[0].page is None


# ---------------------------------------------------------------------------
# Chunk -> Qdrant payload
# ---------------------------------------------------------------------------


def test_payload_carries_file_type_and_page():
    payload = _build_payload(make_chunk())

    assert payload["file_type"] == "pdf"
    assert payload["page"] == 2

    for field in (
        "chunk_ids",
        "text",
        "source",
        "section",
        "last_updated",
        "document_type",
        "access_level",
        "version",
    ):
        assert field in payload


def test_payload_omits_optional_fields_when_unknown():
    """Old/legacy chunks must stay compatible."""

    chunk = make_chunk(file_type=None, page=None)

    payload = _build_payload(chunk)

    assert "file_type" not in payload
    assert "page" not in payload


# ---------------------------------------------------------------------------
# Qdrant payload -> retrieval result
# ---------------------------------------------------------------------------


class FakeStore:
    def __init__(self, payloads):
        self.payloads = payloads

    def search_text(self, query, top_k=5):
        return [(0.9, payload) for payload in self.payloads[:top_k]]


def _dense_retriever(payload) -> DenseRetriever:
    retriever = DenseRetriever.__new__(DenseRetriever)
    retriever.vector_store = FakeStore([payload])
    return retriever


def test_retrieval_result_reconstructs_file_type_and_page():
    results = _dense_retriever(_build_payload(make_chunk())).retrieve("q", top_k=1)

    assert results[0].chunk.file_type == "pdf"
    assert results[0].chunk.page == 2
    assert results[0].chunk.source == "manual.pdf"


def test_retrieval_tolerates_legacy_payload():
    legacy = {
        "chunk_ids": "legacy.md_chunk_1",
        "text": "text",
        "source": "legacy.md",
        "section": "General",
        "last_updated": "2026-08-01",
        "document_type": "guide",
        "access_level": "public",
        "version": 1,
    }

    chunk = _dense_retriever(legacy).retrieve("q", top_k=1)[0].chunk

    assert chunk.file_type is None
    assert chunk.page is None


# ---------------------------------------------------------------------------
# retrieval result -> Citation
# ---------------------------------------------------------------------------


def test_citation_verifier_sets_file_type_and_page(monkeypatch):
    verifier = verifier_module.CitationVerifier.__new__(
        verifier_module.CitationVerifier
    )
    monkeypatch.setattr(
        verifier,
        "_verify_claim",
        lambda claim, evidence: {"supported": True, "explanation": "ok"},
    )

    verified = verifier.verify(
        [Citation(chunk_id="manual.pdf_chunk_2", claim="Alpha claim")],
        [{"chunk": make_chunk()}],
    )

    assert verified[0].supported is True
    assert verified[0].source == "manual.pdf"
    assert verified[0].file_type == "pdf"
    assert verified[0].page == 2


def test_citation_verifier_tolerates_chunk_without_file_type(monkeypatch):
    verifier = verifier_module.CitationVerifier.__new__(
        verifier_module.CitationVerifier
    )
    monkeypatch.setattr(
        verifier,
        "_verify_claim",
        lambda claim, evidence: {"supported": True, "explanation": "ok"},
    )

    verified = verifier.verify(
        [Citation(chunk_id="manual.pdf_chunk_2", claim="claim")],
        [{"chunk": make_chunk(file_type=None, page=None)}],
    )

    assert verified[0].file_type is None


# ---------------------------------------------------------------------------
# Citation -> API response
# ---------------------------------------------------------------------------


def test_query_response_exposes_citation_file_type(monkeypatch):
    from fastapi.testclient import TestClient

    from app.api import routes
    from app.auth.dependencies import get_current_user
    from app.auth.models import User
    from app.main import app

    class FakeQA:
        def answer(self, query, user_access_level="public"):
            return {
                "answer": "Answer text.",
                "answerability": SimpleNamespace(answerable=True),
                "citations": [
                    Citation(
                        chunk_id="manual.pdf_chunk_2",
                        claim="claim",
                        supported=True,
                        explanation="explanation",
                        source="manual.pdf",
                        file_type="pdf",
                        page=2,
                    )
                ],
                "confidence": 0.91,
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

    body = response.json()

    assert set(("answer", "answerable", "citations", "confidence")) <= set(body)

    citation = body["citations"][0]

    assert citation["file_type"] == "pdf"
    assert citation["page"] == 2
    assert citation["source"] == "manual.pdf"
