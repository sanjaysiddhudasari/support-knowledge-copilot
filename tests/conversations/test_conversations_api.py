"""Conversation API endpoints: auth, isolation, persistence, ordering."""

import os
from types import SimpleNamespace

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-service-key")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api.conversations import get_conversation_service  # noqa: E402
from app.auth.dependencies import get_current_user  # noqa: E402
from app.auth.models import User  # noqa: E402
from app.main import app  # noqa: E402
from app.services.conversation_service import ConversationService  # noqa: E402
from conversations.fake_supabase import FakeSupabase  # noqa: E402

USER_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
USER_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


@pytest.fixture
def env():
    fake = FakeSupabase()
    service = ConversationService(fake)
    state = {"user_id": USER_A}

    def current_user():
        return User(
            id=state["user_id"],
            email=f"{state['user_id'][:4]}@example.com",
            access_level="public",
        )

    app.dependency_overrides[get_current_user] = current_user
    app.dependency_overrides[get_conversation_service] = lambda: service

    with TestClient(app) as client:
        yield SimpleNamespace(
            client=client, fake=fake, service=service, state=state
        )

    app.dependency_overrides.clear()


def as_user(env, user_id):
    env.state["user_id"] = user_id
    return env.client


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def test_create_returns_201_with_a_conversation(env):
    response = env.client.post("/api/conversations", json={})

    assert response.status_code == 201

    body = response.json()

    assert body["id"]
    assert body["title"] == "New Chat"
    assert body["user_id"] == USER_A


def test_list_returns_only_own_conversations(env):
    env.client.post("/api/conversations", json={"title": "mine"})
    env.service.create_conversation(USER_B, "theirs")

    body = env.client.get("/api/conversations").json()

    assert [row["title"] for row in body] == ["mine"]


def test_list_is_empty_for_a_new_user(env):
    assert env.client.get("/api/conversations").json() == []


def test_add_and_read_messages(env):
    conversation_id = env.client.post(
        "/api/conversations", json={}
    ).json()["id"]

    created = env.client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={
            "role": "user",
            "content": "How do I reset my password?",
            "query_id": "abc123",
        },
    )

    assert created.status_code == 201
    assert created.json()["query_id"] == "abc123"

    messages = env.client.get(
        f"/api/conversations/{conversation_id}/messages"
    ).json()

    assert [m["content"] for m in messages] == [
        "How do I reset my password?"
    ]


def test_assistant_metadata_round_trips_through_the_api(env):
    conversation_id = env.client.post(
        "/api/conversations", json={}
    ).json()["id"]

    citations = [
        {"chunk_id": "manual.pdf_chunk_2", "source": "manual.pdf", "page": 2}
    ]

    env.client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={
            "role": "assistant",
            "content": "See page 2.",
            "query_id": "abc123",
            "confidence": 0.87,
            "answerable": True,
            "citations": citations,
        },
    )

    assistant = env.client.get(
        f"/api/conversations/{conversation_id}/messages"
    ).json()[0]

    assert assistant["confidence"] == 0.87
    assert assistant["answerable"] is True
    assert assistant["citations"] == citations
    assert assistant["query_id"] == "abc123"


def test_rename_conversation(env):
    conversation_id = env.client.post(
        "/api/conversations", json={}
    ).json()["id"]

    response = env.client.patch(
        f"/api/conversations/{conversation_id}", json={"title": "Renamed"}
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Renamed"


def test_delete_conversation_then_it_is_gone(env):
    conversation_id = env.client.post(
        "/api/conversations", json={}
    ).json()["id"]

    assert env.client.delete(
        f"/api/conversations/{conversation_id}"
    ).status_code == 200

    assert env.client.get(
        f"/api/conversations/{conversation_id}"
    ).status_code == 404


def test_unsupported_role_is_a_400(env):
    conversation_id = env.client.post(
        "/api/conversations", json={}
    ).json()["id"]

    response = env.client.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"role": "system", "content": "nope"},
    )

    assert response.status_code == 400


# ---------------------------------------------------------------------------
# Isolation: User A must not touch User B's data
# ---------------------------------------------------------------------------


def test_user_b_cannot_read_user_a_conversation(env):
    conversation_id = env.client.post(
        "/api/conversations", json={}
    ).json()["id"]

    client_b = as_user(env, USER_B)

    assert client_b.get(
        f"/api/conversations/{conversation_id}"
    ).status_code == 404
    assert client_b.get(
        f"/api/conversations/{conversation_id}/messages"
    ).status_code == 404


def test_user_b_cannot_write_to_user_a_conversation(env):
    conversation_id = env.client.post(
        "/api/conversations", json={}
    ).json()["id"]

    client_b = as_user(env, USER_B)

    response = client_b.post(
        f"/api/conversations/{conversation_id}/messages",
        json={"role": "user", "content": "intruding"},
    )

    assert response.status_code == 404
    assert env.service.list_messages(USER_A, conversation_id) == []


def test_user_b_cannot_delete_user_a_conversation(env):
    conversation_id = env.client.post(
        "/api/conversations", json={}
    ).json()["id"]

    client_b = as_user(env, USER_B)

    assert client_b.delete(
        f"/api/conversations/{conversation_id}"
    ).status_code == 404

    # Still there for its owner.
    owner = as_user(env, USER_A)

    assert owner.get(
        f"/api/conversations/{conversation_id}"
    ).status_code == 200


def test_storage_failure_does_not_leak_details(env, monkeypatch):
    class Exploding:
        def table(self, name):
            raise RuntimeError("password=hunter2 host=db.internal")

    app.dependency_overrides[get_conversation_service] = lambda: (
        ConversationService(Exploding())
    )

    response = env.client.get("/api/conversations")

    assert response.status_code == 503

    body = response.text

    assert "hunter2" not in body
    assert "db.internal" not in body
    assert "Traceback" not in body


# ---------------------------------------------------------------------------
# RAG correlation id
# ---------------------------------------------------------------------------


def test_query_endpoint_forwards_and_echoes_query_id(env, monkeypatch):
    from app.api import routes

    captured = {}

    class FakeQA:
        def answer(self, query, user_access_level="public", user_id=None,
                   query_id=None):
            captured["query_id"] = query_id
            return {
                "answer": "Answer.",
                "answerability": SimpleNamespace(answerable=True),
                "citations": [],
                "confidence": 0.5,
            }

    monkeypatch.setattr(routes, "_qa_service", FakeQA())

    response = env.client.post(
        "/api/query", json={"query": "hi", "query_id": "trace-1"}
    )

    assert response.status_code == 200
    assert response.json()["query_id"] == "trace-1"
    assert captured["query_id"] == "trace-1"
