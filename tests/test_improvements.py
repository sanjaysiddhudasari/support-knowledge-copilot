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
