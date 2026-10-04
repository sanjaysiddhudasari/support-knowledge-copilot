"""Conversation state + display metadata for the Streamlit UI.

Deliberately free of Streamlit imports so the persistence behaviour is
unit-testable: every assistant message owns its confidence, answerability and
citations, and history rendering never reads the latest query's globals.
"""

import json
import re
import time
import uuid


MESSAGES_KEY = "messages"
TOKEN_KEY = "access_token"
USER_KEY = "user"

# UI state only — the database is the source of truth for history.
CONVERSATIONS_KEY = "conversations"
CURRENT_CONVERSATION_KEY = "current_conversation_id"

FORMAT_META = {
    "markdown": {"label": "Markdown", "icon": "📚"},
    "text": {"label": "Text", "icon": "📝"},
    "pdf": {"label": "PDF", "icon": "📄"},
    "docx": {"label": "DOCX", "icon": "📘"},
    "html": {"label": "HTML", "icon": "🌐"},
}

UNKNOWN_FORMAT = {"label": "Document", "icon": "📎"}

_CITATION_RE = re.compile(r"\[[\w.-]+_chunk_\d+\]")


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------


def format_meta(file_type: str | None) -> dict:
    """Format metadata for a normalized ``file_type``, with a safe fallback."""

    if not file_type:
        return dict(UNKNOWN_FORMAT)

    return dict(
        FORMAT_META.get(str(file_type).strip().lower(), UNKNOWN_FORMAT)
    )


def format_badge(file_type: str | None) -> str:
    """e.g. ``📄 PDF``."""

    meta = format_meta(file_type)
    return f"{meta['icon']} {meta['label']}"


def format_line(file_type: str | None, page: int | None = None) -> str:
    """e.g. ``PDF · Page 7`` or ``DOCX``."""

    label = format_meta(file_type)["label"]

    if page is not None:
        return f"{label} · Page {page}"

    return label


def normalize_confidence(value) -> float:
    """Accept a float, None, or the API's confidence dict."""

    if isinstance(value, dict):
        value = value.get("confidence", 0)

    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def normalize_answerable(value) -> bool:
    """Accept a bool, None, or the API's answerability dict."""

    if isinstance(value, dict):
        value = value.get("answerable", False)

    return bool(value)


def strip_citations(text: str) -> str:
    """Remove inline ``[file.md_chunk_1]`` markers for display."""

    cleaned = _CITATION_RE.sub("", text or "")

    return re.sub(r"[ \t]+\n", "\n", cleaned).strip()


def citation_source_name(citation: dict) -> str:
    """Prefer the citation's ``source``; fall back to the chunk id prefix."""

    citation = citation or {}

    source = citation.get("source")

    if source:
        return source

    chunk_id = citation.get("chunk_id") or ""

    if "_chunk_" in chunk_id:
        return chunk_id.split("_chunk_")[0]

    return chunk_id or "Unknown"


def citation_page(citation: dict):
    page = (citation or {}).get("page")

    try:
        return int(page)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Conversation state
# ---------------------------------------------------------------------------


def init_chat_state(state) -> list:
    """Ensure the session state has the keys the chat UI relies on."""

    state.setdefault(MESSAGES_KEY, [])
    return state[MESSAGES_KEY]


def get_messages(state) -> list:
    return state.setdefault(MESSAGES_KEY, [])


def add_user_message(state, content: str) -> dict:
    message = {"role": "user", "content": content}

    get_messages(state).append(message)

    return message


def add_assistant_message(
    state,
    content: str,
    confidence=None,
    answerable=False,
    citations=None,
    error: str | None = None,
    query_id: str | None = None,
) -> dict:
    """Append an assistant turn, storing its own metadata snapshot.

    ``query_id`` correlates this turn with the user turn it answers and with
    the LangSmith trace for the RAG request. It is generated when not supplied.
    """

    message = {
        "role": "assistant",
        "content": content,
        "confidence": normalize_confidence(confidence),
        "answerable": normalize_answerable(answerable),
        "citations": [dict(citation) for citation in (citations or [])],
        "error": error,
        "query_id": query_id or uuid.uuid4().hex,
        "created_at": time.time(),
    }

    get_messages(state).append(message)

    return message


def new_chat(state) -> list:
    """Clear the conversation without touching the session/login."""

    state[MESSAGES_KEY] = []

    return state[MESSAGES_KEY]


# ---------------------------------------------------------------------------
# Stored row -> display message
# ---------------------------------------------------------------------------


def _citations_from_row(value) -> list:
    """A ``jsonb`` column may arrive as a list or (rarely) a JSON string."""

    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (TypeError, ValueError):
            return []

    if not isinstance(value, list):
        return []

    return [
        dict(citation)
        for citation in value
        if isinstance(citation, dict)
    ]


def message_from_row(row: dict) -> dict:
    """Map a stored ``messages`` record to the shape the chat UI renders.

    Assistant turns carry their stored confidence/answerability/citations —
    nothing is recomputed when history is restored.
    """

    row = row or {}

    role = row.get("role") or "assistant"

    message = {
        "role": role,
        "content": row.get("content") or "",
        "query_id": row.get("query_id"),
        "created_at": row.get("created_at"),
    }

    if role == "assistant":
        message["confidence"] = normalize_confidence(row.get("confidence"))
        message["answerable"] = normalize_answerable(row.get("answerable"))
        message["citations"] = _citations_from_row(row.get("citations"))
        message["error"] = None

    return message


def messages_from_rows(rows) -> list:
    """Chronological stored rows -> display messages."""

    return [message_from_row(row) for row in (rows or [])]


def conversation_title(row) -> str:
    """Sidebar label for a conversation record."""

    title = (row or {}).get("title")

    if isinstance(title, str) and title.strip():
        return title.strip()

    return "New Chat"
