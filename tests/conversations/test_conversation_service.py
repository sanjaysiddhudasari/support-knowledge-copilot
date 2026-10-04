"""ConversationService behaviour against an in-memory Supabase fake."""

import pytest

from app.services.conversation_service import (
    ConversationNotFound,
    ConversationService,
    ConversationValidationError,
    derive_title,
)
from conversations.fake_supabase import FakeSupabase

USER_A = "11111111-1111-1111-1111-111111111111"
USER_B = "22222222-2222-2222-2222-222222222222"


@pytest.fixture
def service():
    return ConversationService(FakeSupabase())


# ---------------------------------------------------------------------------
# Title derivation (no LLM)
# ---------------------------------------------------------------------------


def test_derive_title_normalizes_whitespace():
    assert derive_title("  Reset   my\n\npassword ") == "Reset my password"


def test_derive_title_truncates_with_ellipsis():
    title = derive_title("word " * 40)

    assert title.endswith("...")
    assert len(title) <= 63


def test_derive_title_falls_back_for_empty_input():
    assert derive_title("") == "New Chat"
    assert derive_title(None) == "New Chat"
    assert derive_title("   \n ") == "New Chat"


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------


def test_create_conversation_defaults(service):
    row = service.create_conversation(USER_A)

    assert row["user_id"] == USER_A
    assert row["title"] == "New Chat"
    assert row["id"]


def test_list_conversations_is_scoped_to_the_user(service):
    service.create_conversation(USER_A, "mine")
    service.create_conversation(USER_B, "theirs")

    titles = [row["title"] for row in service.list_conversations(USER_A)]

    assert titles == ["mine"]


def test_list_conversations_orders_by_newest_activity(service):
    service.client.add(
        "conversations",
        {
            "id": "old",
            "user_id": USER_A,
            "title": "old",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        },
    )
    service.client.add(
        "conversations",
        {
            "id": "recent",
            "user_id": USER_A,
            "title": "recent",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-06-01T00:00:00+00:00",
        },
    )

    ids = [row["id"] for row in service.list_conversations(USER_A)]

    assert ids == ["recent", "old"]


def test_foreign_conversation_is_reported_as_missing(service):
    theirs = service.create_conversation(USER_B, "theirs")

    with pytest.raises(ConversationNotFound):
        service.get_conversation(USER_A, theirs["id"])

    with pytest.raises(ConversationNotFound):
        service.list_messages(USER_A, theirs["id"])


def test_add_message_to_foreign_conversation_is_missing(service):
    theirs = service.create_conversation(USER_B)

    with pytest.raises(ConversationNotFound):
        service.add_message(USER_A, theirs["id"], "user", "hi")


def test_rename_and_delete(service):
    row = service.create_conversation(USER_A, "Chat")

    renamed = service.rename_conversation(USER_A, row["id"], "  New   name ")

    assert renamed["title"] == "New name"

    service.delete_conversation(USER_A, row["id"])

    assert service.list_conversations(USER_A) == []


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


def test_user_message_persists_content_and_query_id(service):
    conversation = service.create_conversation(USER_A)

    stored = service.add_message(
        USER_A,
        conversation["id"],
        role="user",
        content="How do I reset my password?",
        query_id="abc123",
    )

    assert stored["role"] == "user"
    assert stored["content"] == "How do I reset my password?"
    assert stored["query_id"] == "abc123"


def test_assistant_message_persists_rag_metadata(service):
    conversation = service.create_conversation(USER_A)

    citations = [
        {
            "chunk_id": "notifications.md_chunk_2",
            "source": "notifications.md",
            "section": "Notification Types",
            "page": None,
            "supported": True,
        }
    ]

    stored = service.add_message(
        USER_A,
        conversation["id"],
        role="assistant",
        content="Reset it from settings.",
        query_id="abc123",
        confidence=0.91,
        answerable=True,
        citations=citations,
    )

    assert stored["confidence"] == 0.91
    assert stored["answerable"] is True
    assert stored["citations"] == citations
    assert stored["query_id"] == "abc123"


def test_messages_are_returned_chronologically(service):
    conversation = service.create_conversation(USER_A)

    for content in ("first", "second", "third"):
        service.add_message(
            USER_A, conversation["id"], role="user", content=content
        )

    messages = service.list_messages(USER_A, conversation["id"])

    assert [m["content"] for m in messages] == ["first", "second", "third"]


def test_duplicate_submission_is_idempotent(service):
    """A Streamlit rerun must not double-write a turn."""

    conversation = service.create_conversation(USER_A)

    first = service.add_message(
        USER_A, conversation["id"], "user", "hello", query_id="q1"
    )
    second = service.add_message(
        USER_A, conversation["id"], "user", "hello", query_id="q1"
    )

    assert first["id"] == second["id"]
    assert len(service.list_messages(USER_A, conversation["id"])) == 1

    # The assistant turn for the same query id is a distinct row.
    service.add_message(
        USER_A, conversation["id"], "assistant", "hi", query_id="q1"
    )

    assert len(service.list_messages(USER_A, conversation["id"])) == 2


def test_add_message_bumps_updated_at_and_names_the_chat(service):
    conversation = service.create_conversation(USER_A)

    before = conversation["updated_at"]

    service.add_message(
        USER_A,
        conversation["id"],
        role="user",
        content="Why is my invoice overdue?",
    )

    after = service.get_conversation(USER_A, conversation["id"])

    assert after["updated_at"] != before
    assert after["title"] == "Why is my invoice overdue?"


def test_explicit_title_is_not_overwritten_by_first_message(service):
    conversation = service.create_conversation(USER_A, "Billing")

    service.add_message(
        USER_A, conversation["id"], "user", "some question"
    )

    assert service.get_conversation(USER_A, conversation["id"])["title"] == (
        "Billing"
    )


def test_unsupported_role_is_rejected(service):
    conversation = service.create_conversation(USER_A)

    with pytest.raises(ConversationValidationError):
        service.add_message(
            USER_A, conversation["id"], "system", "nope"
        )

    assert service.list_messages(USER_A, conversation["id"]) == []


def test_deleting_a_conversation_removes_its_messages(service):
    conversation = service.create_conversation(USER_A)

    service.add_message(
        USER_A, conversation["id"], "user", "hello", query_id="q1"
    )

    service.delete_conversation(USER_A, conversation["id"])

    assert service.client.rows("messages") == []
