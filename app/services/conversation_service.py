"""Persistent conversation storage.

Backed by the project's existing Supabase Postgres database — no new datastore
is introduced. Everything here is scoped to the authenticated user: a
conversation that belongs to somebody else is reported as *missing*, so the API
never reveals whether a foreign conversation id exists.

The service is deliberately free of FastAPI and Streamlit imports so it can be
unit-tested against an in-memory fake of the Supabase client.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from app.auth.client import supabase_admin


CONVERSATIONS_TABLE = "conversations"
MESSAGES_TABLE = "messages"

DEFAULT_TITLE = "New Chat"
TITLE_MAX_LENGTH = 60
VALID_ROLES = ("user", "assistant")


class ConversationNotFound(Exception):
    """Raised when a conversation does not exist for this user."""


class ConversationValidationError(Exception):
    """Raised when a message payload is not storable."""


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def utc_now() -> str:
    """Timestamp string the database stores as ``timestamptz``."""

    return datetime.now(timezone.utc).isoformat()


def derive_title(text: str | None) -> str:
    """Title from the first user message. No LLM call, no extra cost."""

    normalized = re.sub(r"\s+", " ", text or "").strip()

    if not normalized:
        return DEFAULT_TITLE

    if len(normalized) <= TITLE_MAX_LENGTH:
        return normalized

    return normalized[:TITLE_MAX_LENGTH].rstrip() + "..."


def _rows(response: Any) -> list[dict]:
    data = getattr(response, "data", None)

    if data is None:
        return []

    if isinstance(data, list):
        return list(data)

    return [data]


def _row(response: Any) -> dict | None:
    rows = _rows(response)

    return rows[0] if rows else None


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class ConversationService:
    """CRUD over ``conversations``/``messages`` with per-user isolation."""

    def __init__(self, client: Any | None = None):
        self._client = client if client is not None else supabase_admin

    @property
    def client(self) -> Any:
        return self._client

    # -- ownership ---------------------------------------------------------

    def _owned_conversation(
        self,
        user_id: str,
        conversation_id: str,
    ) -> dict | None:
        """Return the conversation only when it belongs to ``user_id``."""

        response = (
            self.client.table(CONVERSATIONS_TABLE)
            .select("*")
            .eq("id", conversation_id)
            .execute()
        )

        row = _row(response)

        if row is None:
            return None

        # Never trust a conversation id from the browser on its own.
        if str(row.get("user_id")) != str(user_id):
            return None

        return row

    def _require_owned(
        self,
        user_id: str,
        conversation_id: str,
    ) -> dict:
        row = self._owned_conversation(user_id, conversation_id)

        if row is None:
            raise ConversationNotFound(conversation_id)

        return row

    # -- conversations -----------------------------------------------------

    def create_conversation(
        self,
        user_id: str,
        title: str | None = None,
    ) -> dict:
        payload = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "title": derive_title(title) if title else DEFAULT_TITLE,
            "created_at": utc_now(),
            "updated_at": utc_now(),
        }

        response = (
            self.client.table(CONVERSATIONS_TABLE)
            .insert(payload)
            .execute()
        )

        return _row(response) or payload

    def list_conversations(self, user_id: str) -> list[dict]:
        response = (
            self.client.table(CONVERSATIONS_TABLE)
            .select("*")
            .eq("user_id", user_id)
            .order("updated_at", desc=True)
            .execute()
        )

        return _rows(response)

    def get_conversation(self, user_id: str, conversation_id: str) -> dict:
        return self._require_owned(user_id, conversation_id)

    def rename_conversation(
        self,
        user_id: str,
        conversation_id: str,
        title: str,
    ) -> dict:
        self._require_owned(user_id, conversation_id)

        response = (
            self.client.table(CONVERSATIONS_TABLE)
            .update({"title": derive_title(title)})
            .eq("id", conversation_id)
            .execute()
        )

        return _row(response) or {
            "id": conversation_id,
            "title": derive_title(title),
        }

    def delete_conversation(self, user_id: str, conversation_id: str) -> None:
        self._require_owned(user_id, conversation_id)

        # Messages go with it via `on delete cascade`.
        (
            self.client.table(CONVERSATIONS_TABLE)
            .delete()
            .eq("id", conversation_id)
            .execute()
        )

    # -- messages ----------------------------------------------------------

    def list_messages(
        self,
        user_id: str,
        conversation_id: str,
    ) -> list[dict]:
        self._require_owned(user_id, conversation_id)

        response = (
            self.client.table(MESSAGES_TABLE)
            .select("*")
            .eq("conversation_id", conversation_id)
            .order("created_at", desc=False)
            .execute()
        )

        return _rows(response)

    def _existing_message(
        self,
        conversation_id: str,
        query_id: str,
        role: str,
    ) -> dict | None:
        """Idempotency guard: a Streamlit rerun must not double-write."""

        response = (
            self.client.table(MESSAGES_TABLE)
            .select("*")
            .eq("conversation_id", conversation_id)
            .eq("query_id", query_id)
            .eq("role", role)
            .execute()
        )

        return _row(response)

    def add_message(
        self,
        user_id: str,
        conversation_id: str,
        role: str,
        content: str,
        query_id: str | None = None,
        confidence: float | None = None,
        answerable: bool | None = None,
        citations: list[dict] | None = None,
    ) -> dict:
        """Persist one turn and bump the conversation's ``updated_at``.

        When a ``query_id`` is supplied the write is idempotent: repeating the
        same (conversation, query_id, role) triple returns the stored row
        instead of inserting a duplicate.
        """

        if role not in VALID_ROLES:
            raise ConversationValidationError(f"Unsupported role: {role!r}")

        conversation = self._require_owned(user_id, conversation_id)

        if query_id:
            existing = self._existing_message(
                conversation_id, query_id, role
            )

            if existing is not None:
                return existing

        payload: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "query_id": query_id,
            "confidence": confidence,
            "answerable": answerable,
            # JSONB: store the existing citation model verbatim.
            "citations": [dict(citation) for citation in (citations or [])]
            if citations
            else None,
            "created_at": utc_now(),
        }

        response = (
            self.client.table(MESSAGES_TABLE).insert(payload).execute()
        )

        stored = _row(response) or payload

        self._touch_conversation(conversation, role, content)

        return stored

    def _touch_conversation(
        self,
        conversation: dict,
        role: str,
        content: str,
    ) -> None:
        """Mark activity and name an untitled chat after its first turn.

        ``updated_at`` is owned by the database (a ``before update`` trigger
        restamps it with the server clock), so the value sent here is only a
        fallback for databases where the trigger has not been installed.
        """

        update: dict[str, Any] = {"updated_at": utc_now()}

        title = (conversation.get("title") or "").strip()

        if role == "user" and title in ("", DEFAULT_TITLE):
            update["title"] = derive_title(content)

        (
            self.client.table(CONVERSATIONS_TABLE)
            .update(update)
            .eq("id", conversation["id"])
            .execute()
        )
