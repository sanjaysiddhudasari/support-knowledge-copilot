import time
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

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
        # generate should still have been called only once due to cache!
        assert mock_gen.generate.call_count == 1
