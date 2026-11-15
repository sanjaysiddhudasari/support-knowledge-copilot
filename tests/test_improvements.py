import time
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from app.config import Settings
from app.core.rate_limiter import RateLimiter
from app.main import app
from app.models.chunk import Chunk
from app.models.retrieval import RetrievalResult
from app.retrieval.hybrid import HybridRetriever
from app.services.cache import QueryCache
from app.services.qa_service import QAService


def test_query_cache_basic_and_expiration():
    cache = QueryCache(ttl_seconds=1, max_size=2)
    cache.set("what is the limit?", "public", {"answer": "10 GB"})

    # Hit
    cached = cache.get("what is the limit?", "public")
    assert cached == {"answer": "10 GB"}

    # Normalized hit (casing & spacing)
    cached_norm = cache.get("  WHAT is THE limit?  ", "public")
    assert cached_norm == {"answer": "10 GB"}

    # Different access level is a miss
    assert cache.get("what is the limit?", "admin") is None

    # Wait for TTL expiration
    time.sleep(1.05)
    assert cache.get("what is the limit?", "public") is None


def test_query_cache_conversation_separation():
    cache = QueryCache(ttl_seconds=60, max_size=10)
    cache.set("how do I reset?", "public", {"answer": "Click settings"}, conversation_id="conv-1")
    cache.set("how do I reset?", "public", {"answer": "Contact admin"}, conversation_id="conv-2")

    assert cache.get("how do I reset?", "public", conversation_id="conv-1") == {"answer": "Click settings"}
    assert cache.get("how do I reset?", "public", conversation_id="conv-2") == {"answer": "Contact admin"}
    # Without conversation_id is a separate key
    assert cache.get("how do I reset?", "public") is None


def test_query_cache_lru_eviction():
    cache = QueryCache(ttl_seconds=60, max_size=2)
    cache.set("q1", "public", {"val": 1})
    cache.set("q2", "public", {"val": 2})

    # Access q1 to make q2 oldest
    assert cache.get("q1", "public") == {"val": 1}

    # Add q3 -> q2 should be evicted
    cache.set("q3", "public", {"val": 3})

    assert cache.get("q1", "public") is not None
    assert cache.get("q3", "public") is not None
    assert cache.get("q2", "public") is None


def test_query_cache_invalidation():
    cache = QueryCache(ttl_seconds=60, max_size=10)
    cache.set("q1", "public", {"val": 1})
    cache.set("q2", "admin", {"val": 2})

    cache.invalidate()

    assert cache.get("q1", "public") is None
    assert cache.get("q2", "admin") is None


def test_cors_middleware_headers():
    client = TestClient(app)
    # Origin from allowed list
    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:8501",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:8501"


def test_parallel_hybrid_retrieval():
    mock_dense = MagicMock()
    mock_bm25 = MagicMock()

    chunk1 = Chunk(
        chunk_ids="c1",
        text="text 1",
        source="s1.md",
        section="sec1",
        last_updated="2026-01-01",
        document_type="guide",
        access_level="public",
    )
    chunk2 = Chunk(
        chunk_ids="c2",
        text="text 2",
        source="s2.md",
        section="sec2",
        last_updated="2026-01-01",
        document_type="guide",
        access_level="public",
    )

    mock_dense.retrieve.return_value = [
        RetrievalResult(chunk=chunk1, score=0.9, rank=1, source="dense")
    ]
    mock_bm25.retrieve.return_value = [
        RetrievalResult(chunk=chunk2, score=5.0, rank=1, source="bm25")
    ]

    retriever = HybridRetriever(mock_dense, mock_bm25)
    results = retriever.retrieve("query", top_k=2)

    assert len(results) == 2
    mock_dense.retrieve.assert_called_once()
    mock_bm25.retrieve.assert_called_once()


def test_qa_service_cache_and_multiturn():
    with patch("app.services.qa_service.RetrievalService"), \
         patch("app.services.qa_service.AnswerGenerator") as mock_gen_cls, \
         patch("app.services.qa_service.CitationVerifier") as mock_ver_cls, \
         patch("app.services.qa_service.AnswerabilityDetector") as mock_ans_cls, \
         patch("app.services.qa_service.ConfidenceScorer") as mock_conf_cls, \
         patch("app.services.qa_service.ConversationService") as mock_conv_cls:

        mock_ans = mock_ans_cls.return_value
        mock_ans.check.return_value = MagicMock(answerable=True)

        mock_gen = mock_gen_cls.return_value
        mock_gen.generate.return_value = MagicMock(
            answer="Generated answer",
            citations=[],
            answerability=MagicMock(answerable=True),
            confidence=0.9,
        )

        mock_ver = mock_ver_cls.return_value
        mock_ver.verify.return_value = []

        mock_conf = mock_conf_cls.return_value
        mock_conf.calculate.return_value = {"confidence": 0.9}

        mock_conv = mock_conv_cls.return_value
        mock_conv.get_recent_messages.return_value = [
            {"role": "user", "content": "previous turn"}
        ]

        qa = QAService()

        # First call: cache miss, invokes generate with history
        result1 = qa.answer(
            query="test query",
            user_access_level="public",
            user_id="user-123",
            conversation_id="conv-123",
        )
        assert result1["answer"] == "Generated answer"
        mock_conv.get_recent_messages.assert_called_once_with(
            user_id="user-123",
            conversation_id="conv-123",
        )
        assert mock_gen.generate.call_count == 1
        history_arg = mock_gen.generate.call_args[1].get("history")
        assert history_arg == [{"role": "user", "content": "previous turn"}]

        # Second call with same parameters: should hit cache
        result2 = qa.answer(
            query="test query",
            user_access_level="public",
            user_id="user-123",
            conversation_id="conv-123",
        )
        assert result2["answer"] == "Generated answer"
        assert mock_gen.generate.call_count == 1


def test_settings_validation():
    s = Settings(
        CORS_ORIGINS="https://app.example.com, https://test.example.com",
        RATE_LIMIT_PER_MINUTE="50",
    )
    assert s.cors_origins == ["https://app.example.com", "https://test.example.com"]
    assert s.rate_limit_per_minute == 50


def test_rate_limiter_allows_and_throttles():
    limiter = RateLimiter(requests_per_minute=2)
    mock_request = MagicMock()
    mock_request.headers.get.return_value = "192.168.1.100"

    # 1st request: OK
    limiter(mock_request)
    # 2nd request: OK
    limiter(mock_request)

    # 3rd request: Throttled (429)
    from fastapi import HTTPException
    import pytest
    with pytest.raises(HTTPException) as exc_info:
        limiter(mock_request)
    assert exc_info.value.status_code == 429
    assert "Retry-After" in exc_info.value.headers


def test_streaming_answer_endpoint():
    client = TestClient(app)
    from app.auth.models import User
    from app.auth.dependencies import get_current_user

    mock_user = User(id="user-test", email="test@example.com", access_level="public")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    try:
        with patch("app.api.routes.get_qa_service") as mock_get_qa:
            mock_qa = mock_get_qa.return_value
            mock_qa.answer_stream.return_value = iter(["Hello", " ", "World", "!"])

            response = client.post(
                "/api/query/stream",
                json={"query": "test streaming"},
            )
            assert response.status_code == 200
            assert response.text == "Hello World!"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_message_feedback_endpoint():
    client = TestClient(app)
    from app.auth.models import User
    from app.auth.dependencies import get_current_user
    from app.api.conversations import get_conversation_service

    mock_user = User(id="user-test", email="test@example.com", access_level="public")
    mock_conv_service = MagicMock()
    mock_conv_service.submit_feedback.return_value = {
        "id": "msg-123",
        "feedback": "positive",
        "feedback_comment": "Great answer",
    }

    app.dependency_overrides[get_current_user] = lambda: mock_user
    app.dependency_overrides[get_conversation_service] = lambda: mock_conv_service

    try:
        response = client.post(
            "/api/conversations/conv-123/messages/msg-123/feedback",
            json={"feedback": "positive", "feedback_comment": "Great answer"},
        )
        assert response.status_code == 200
        assert response.json()["feedback"] == "positive"
        mock_conv_service.submit_feedback.assert_called_once_with(
            user_id="user-test",
            conversation_id="conv-123",
            message_id="msg-123",
            feedback="positive",
            feedback_comment="Great answer",
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_conversation_service, None)



def test_query_processor_normalization_and_expansion():
    from app.retrieval.query_processor import QueryProcessor

    qp = QueryProcessor()
    processed = qp.process("   How do I configure   SSO and MFA?   ")

    assert processed.normalized == "How do I configure SSO and MFA?"
    assert "Single Sign-On (SSO)" in processed.expanded
    assert "Multi-Factor Authentication (MFA)" in processed.expanded
    assert "sso" in processed.keywords
    assert "mfa" in processed.keywords



def test_merged_answerability_unanswerable():
    from app.generation.generator import AnswerGenerator

    mock_client = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = "[UNANSWERABLE] The document does not describe backup restore procedures."
    mock_client.chat.completions.create.return_value = MagicMock(choices=[mock_choice])

    gen = AnswerGenerator.__new__(AnswerGenerator)
    gen.client = mock_client
    gen.model = "test-model"

    chunk_mock = MagicMock()
    chunk_mock.chunk_ids = "chunk_1"
    chunk_mock.section = "Overview"
    chunk_mock.source = "overview.md"
    chunk_mock.text = "Evidence content"

    result = gen.generate("how to restore backup?", [{"chunk": chunk_mock}])
    assert result.answerability.answerable is False
    assert "backup restore procedures" in result.answerability.explanation
    assert result.citations == []


def test_admin_analytics_endpoint():
    client = TestClient(app)
    from app.auth.models import User
    from app.auth.dependencies import get_current_user
    from app.api.analytics import get_analytics_service

    mock_admin = User(id="admin-1", email="admin@example.com", access_level="admin")
    mock_analytics_service = MagicMock()
    mock_analytics_service.get_system_analytics.return_value = {
        "queries": {
            "total_queries": 42,
            "total_answers": 40,
            "answerability_rate": 0.95,
            "average_confidence": 0.88,
        },
        "feedback": {
            "positive": 18,
            "negative": 2,
            "satisfaction_rate": 0.9,
        },
        "sources": {"top_cited": []},
        "documents": {"total_count": 5, "total_size_kb": 120},
    }

    app.dependency_overrides[get_current_user] = lambda: mock_admin
    app.dependency_overrides[get_analytics_service] = lambda: mock_analytics_service

    try:
        response = client.get("/api/admin/analytics")
        assert response.status_code == 200
        data = response.json()
        assert data["queries"]["total_queries"] == 42
        assert data["feedback"]["satisfaction_rate"] == 0.9
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_analytics_service, None)


def test_admin_analytics_forbidden_for_public():
    client = TestClient(app)
    from app.auth.models import User
    from app.auth.dependencies import get_current_user

    mock_user = User(id="user-1", email="user@example.com", access_level="public")
    app.dependency_overrides[get_current_user] = lambda: mock_user

    try:
        response = client.get("/api/admin/analytics")
        assert response.status_code == 403
        assert "Admin access required" in response.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_api_v1_versioning_and_backward_compatibility():
    """Verify that both /api/v1/ and legacy /api/ routes resolve correctly."""
    client = TestClient(app)
    from app.auth.models import User
    from app.auth.dependencies import get_current_user
    from app.api.analytics import get_analytics_service

    mock_admin = User(id="admin-1", email="admin@example.com", access_level="admin")
    mock_analytics_service = MagicMock()
    mock_analytics_service.get_system_analytics.return_value = {"status": "ok", "queries": {"total_queries": 10}}

    app.dependency_overrides[get_current_user] = lambda: mock_admin
    app.dependency_overrides[get_analytics_service] = lambda: mock_analytics_service

    try:
        # 1. Analytics endpoint available on both v1 and legacy
        v1_resp = client.get("/api/v1/admin/analytics")
        assert v1_resp.status_code == 200
        assert v1_resp.json()["queries"]["total_queries"] == 10

        legacy_resp = client.get("/api/admin/analytics")
        assert legacy_resp.status_code == 200
        assert legacy_resp.json()["queries"]["total_queries"] == 10

        # 2. Me endpoint available on both v1 and legacy
        v1_me = client.get("/api/v1/me")
        assert v1_me.status_code == 200
        assert v1_me.json()["email"] == "admin@example.com"

        legacy_me = client.get("/api/me")
        assert legacy_me.status_code == 200
        assert legacy_me.json()["email"] == "admin@example.com"

        # 3. Documents endpoint available on both v1 and legacy
        from app.api.ingestion import get_document_service
        mock_doc_service = MagicMock()
        mock_doc_service.list_documents.return_value = []
        app.dependency_overrides[get_document_service] = lambda: mock_doc_service

        v1_docs = client.get("/api/v1/documents")
        assert v1_docs.status_code == 200
        assert v1_docs.json() == []

        legacy_docs = client.get("/api/documents")
        assert legacy_docs.status_code == 200
        assert legacy_docs.json() == []

    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_analytics_service, None)
        app.dependency_overrides.pop(get_document_service, None)


def test_analytics_service_expanded_metrics():
    """Verify that AnalyticsService computes confidence distributions, gaps, and unique conversations."""
    from app.services.analytics_service import AnalyticsService

    class FakeTable:
        def __init__(self, data):
            self.data = data
        def select(self, *args, **kwargs):
            return self
        def order(self, *args, **kwargs):
            return self
        def limit(self, *args, **kwargs):
            return self
        def execute(self):
            return MagicMock(data=self.data)

    mock_messages = [
        {"id": "m1", "conversation_id": "c1", "role": "user", "content": "hello"},
        {
            "id": "m2",
            "conversation_id": "c1",
            "role": "assistant",
            "content": "Hi there!",
            "confidence": 0.95,
            "answerable": True,
            "citations": [{"source": "guide.pdf", "chunk_id": "guide.pdf_chunk_1"}],
            "feedback": "positive",
        },
        {"id": "m3", "conversation_id": "c2", "role": "user", "content": "How to cook lasagna?"},
        {
            "id": "m4",
            "conversation_id": "c2",
            "role": "assistant",
            "content": "I do not know how to cook lasagna.",
            "confidence": 0.20,
            "answerable": False,
            "citations": [],
            "feedback": "negative",
            "feedback_comment": "irrelevant topic",
        },
    ]

    mock_docs = [
        {"id": "d1", "file_type": "pdf", "status": "indexed", "size_bytes": 10240},
        {"id": "d2", "file_type": "docx", "status": "indexed", "size_bytes": 5120},
    ]

    mock_client = MagicMock()
    mock_client.table.side_effect = lambda table_name: FakeTable(
        mock_messages if table_name == "messages" else mock_docs
    )

    service = AnalyticsService(client=mock_client)
    res = service.get_system_analytics()

    assert res["queries"]["total_queries"] == 2
    assert res["queries"]["total_answers"] == 2
    assert res["queries"]["total_conversations"] == 2
    assert res["queries"]["answerable_count"] == 1
    assert res["queries"]["unanswerable_count"] == 1
    assert res["queries"]["confidence_distribution"]["high"] == 1
    assert res["queries"]["confidence_distribution"]["low"] == 1
    assert len(res["queries"]["recent_unanswerable"]) == 1
    assert "lasagna" in res["queries"]["recent_unanswerable"][0]["answer_preview"]

    assert res["feedback"]["positive"] == 1
    assert res["feedback"]["negative"] == 1
    assert res["feedback"]["satisfaction_rate"] == 0.5
    assert len(res["feedback"]["recent_negative_feedback"]) == 1
    assert res["feedback"]["recent_negative_feedback"][0]["comment"] == "irrelevant topic"

    assert res["documents"]["total_count"] == 2
    assert res["documents"]["by_file_type"]["pdf"] == 1
    assert res["documents"]["by_file_type"]["docx"] == 1
