"""End-to-end check of persistent chat history through the real Streamlit script.

A fake backend stands in for FastAPI + Supabase: it answers RAG queries and
stores conversations/messages in memory, so the tests exercise the real UI flow
(persist -> retrieve -> render) without network or credentials.
"""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "test-service-key")

import pathlib  # noqa: E402

import pytest  # noqa: E402
import requests  # noqa: E402

pytest.importorskip("streamlit.testing.v1")

from streamlit.testing.v1 import AppTest  # noqa: E402


APP_PATH = str(
    pathlib.Path(__file__).resolve().parents[1] / "ui" / "app.py"
)

ANSWERS = {
    "Q1": {
        "answer": "First answer. [manual.pdf_chunk_2]",
        "answerable": True,
        "confidence": 0.91,
        "citations": [
            {
                "chunk_id": "manual.pdf_chunk_2",
                "claim": "First claim",
                "supported": True,
                "explanation": "supported by evidence",
                "source": "manual.pdf",
                "file_type": "pdf",
                "page": 2,
            }
        ],
    },
    "Q2": {
        "answer": "Second answer.",
        "answerable": False,
        "confidence": 0.74,
        "citations": [],
    },
}


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.RequestException(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class FakeBackend:
    """In-memory stand-in for the conversations API + RAG endpoint."""

    def __init__(self):
        self.conversations = []
        self.messages = {}
        self.queries = []
        self.fail_queries = set()
        self.rag_calls = 0
        self._counter = 0

    # -- RAG --------------------------------------------------------------

    def _answer_query(self, payload):
        query = (payload or {}).get("query")
        self.queries.append(query)
        self.rag_calls += 1

        if query in self.fail_queries:
            raise requests.RequestException("connection refused")

        return FakeResponse(ANSWERS[query])

    # -- /api/conversations ----------------------------------------------

    def _conversation_id_from(self, url):
        return url.split("/api/conversations/")[1].split("/")[0]

    def create_conversation(self):
        self._counter += 1

        conversation = {
            "id": f"conv-{self._counter}",
            "title": "New Chat",
            "updated_at": f"2026-01-01T00:00:{self._counter:02d}+00:00",
        }

        self.conversations.insert(0, conversation)
        self.messages[conversation["id"]] = []

        return FakeResponse(conversation)

    def add_message(self, url, payload):
        conversation_id = self._conversation_id_from(url)
        row = {
            "id": f"msg-{len(self.messages[conversation_id]) + 1}",
            "conversation_id": conversation_id,
            **payload,
        }

        self.messages[conversation_id].append(row)

        conversation = next(
            c for c in self.conversations if c["id"] == conversation_id
        )

        if payload.get("role") == "user" and conversation["title"] == "New Chat":
            conversation["title"] = payload["content"][:60]

        return FakeResponse(row)

    # -- requests surface -------------------------------------------------

    def post(self, url, **kwargs):
        if url.endswith("/api/query"):
            return self._answer_query(kwargs.get("json"))

        if url.rstrip("/").endswith("/api/conversations"):
            return self.create_conversation()

        return self.add_message(url, kwargs.get("json") or {})

    def get(self, url, **kwargs):
        if url.rstrip("/").endswith("/api/conversations"):
            return FakeResponse(list(self.conversations))

        conversation_id = self._conversation_id_from(url)

        return FakeResponse(list(self.messages.get(conversation_id, [])))

    def delete(self, url, **kwargs):
        conversation_id = self._conversation_id_from(url)

        self.conversations = [
            c for c in self.conversations if c["id"] != conversation_id
        ]
        self.messages.pop(conversation_id, None)

        return FakeResponse({"status": "deleted"})

    # -- helpers ----------------------------------------------------------

    def all_messages(self):
        return [
            row
            for conversation_id in self.messages
            for row in self.messages[conversation_id]
        ]


def open_app(backend, monkeypatch):
    """Run ui/app.py against the fake backend, as a signed-in user."""

    monkeypatch.setattr(requests, "post", backend.post)
    monkeypatch.setattr(requests, "get", backend.get)
    monkeypatch.setattr(requests, "delete", backend.delete)

    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.session_state["access_token"] = "token"
    at.session_state["user"] = {
        "email": "user@example.com",
        "access_level": "public",
    }
    at.run()

    assert not at.exception, at.exception

    return at


@pytest.fixture
def app(monkeypatch):
    backend = FakeBackend()
    return open_app(backend, monkeypatch), backend


def rendered_text(at) -> str:
    parts = [element.value for element in at.markdown]
    parts += [element.value for element in at.caption]
    return "\n".join(parts)


def ask(at, question):
    at.chat_input[0].set_value(question).run()
    assert not at.exception, at.exception


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def test_question_creates_a_conversation_and_persists_both_turns(app):
    at, backend = app

    ask(at, "Q1")

    assert len(backend.conversations) == 1

    rows = backend.all_messages()

    assert [row["role"] for row in rows] == ["user", "assistant"]
    assert rows[0]["content"] == "Q1"
    assert rows[1]["content"].startswith("First answer.")


def test_assistant_metadata_is_persisted(app):
    at, backend = app

    ask(at, "Q1")

    assistant = backend.all_messages()[1]

    assert assistant["confidence"] == 0.91
    assert assistant["answerable"] is True
    assert assistant["citations"][0]["chunk_id"] == "manual.pdf_chunk_2"
    assert assistant["citations"][0]["page"] == 2


def test_both_turns_share_one_query_id(app):
    at, backend = app

    ask(at, "Q1")

    user_row, assistant_row = backend.all_messages()

    assert user_row["query_id"]
    assert user_row["query_id"] == assistant_row["query_id"]


def test_one_submission_writes_exactly_two_rows(app):
    at, backend = app

    ask(at, "Q1")

    assert len(backend.all_messages()) == 2


def test_conversation_title_comes_from_the_first_question(app):
    at, backend = app

    ask(at, "Q1")

    assert backend.conversations[0]["title"] == "Q1"


def test_two_queries_keep_separate_confidence(app):
    at, backend = app

    ask(at, "Q1")
    ask(at, "Q2")

    assistants = [
        row
        for row in backend.all_messages()
        if row["role"] == "assistant"
    ]

    assert [round(row["confidence"], 2) for row in assistants] == [0.91, 0.74]
    assert [row["answerable"] for row in assistants] == [True, False]
    assert len(assistants[0]["citations"]) == 1
    assert assistants[1]["citations"] == []
    assert assistants[0]["query_id"] != assistants[1]["query_id"]


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def test_history_renders_each_message_with_its_own_metadata(app):
    at, _ = app

    ask(at, "Q1")
    ask(at, "Q2")

    text = rendered_text(at)

    assert "Confidence 91%" in text
    assert "Confidence 74%" in text

    # Citation markers are stripped for display but kept in storage.
    assert "[manual.pdf_chunk_2]" not in text


def test_source_card_shows_format_and_page(app):
    at, _ = app

    ask(at, "Q1")

    text = rendered_text(at)

    assert "manual.pdf" in text
    assert "PDF · Page 2" in text
    assert "📄 PDF" in text


# ---------------------------------------------------------------------------
# Refresh + history restore
# ---------------------------------------------------------------------------


def test_refresh_restores_history_from_storage(app, monkeypatch):
    at, backend = app

    ask(at, "Q1")

    rag_calls_before = backend.rag_calls

    # A brand-new session = page refresh / re-login: session state is gone,
    # so what renders must have come from storage.
    reloaded = open_app(backend, monkeypatch)

    text = rendered_text(reloaded)

    assert "First answer." in text
    assert "Confidence 91%" in text

    # Restoring history must not run retrieval, generation or verification.
    assert backend.rag_calls == rag_calls_before


def test_selecting_an_older_conversation_restores_it(app):
    at, backend = app

    ask(at, "Q1")

    new_chat_button = next(
        button for button in at.button if button.label == "+ New Chat"
    )
    new_chat_button.click().run()
    assert not at.exception, at.exception

    assert len(backend.conversations) == 2
    assert at.session_state["messages"] == []

    rag_calls_before = backend.rag_calls

    # Re-open the first conversation from the sidebar.
    first_conversation = next(
        button for button in at.button if button.label == "Q1"
    )
    first_conversation.click().run()
    assert not at.exception, at.exception

    text = rendered_text(at)

    assert "First answer." in text
    assert "Confidence 91%" in text
    assert backend.rag_calls == rag_calls_before


# ---------------------------------------------------------------------------
# New chat / delete
# ---------------------------------------------------------------------------


def test_new_chat_starts_a_conversation_without_logging_out(app):
    at, backend = app

    ask(at, "Q1")

    new_chat_button = next(
        button for button in at.button if button.label == "+ New Chat"
    )
    new_chat_button.click().run()
    assert not at.exception, at.exception

    assert len(backend.conversations) == 2
    assert at.session_state["messages"] == []
    assert at.session_state["access_token"] == "token"


def test_deleting_a_conversation_removes_it(app):
    at, backend = app

    ask(at, "Q1")
    assert len(backend.conversations) == 1

    delete_button = next(
        button for button in at.button if button.label == "🗑"
    )
    delete_button.click().run()
    assert not at.exception, at.exception

    assert backend.conversations == []
    assert backend.messages == {}
    assert at.session_state["messages"] == []


# ---------------------------------------------------------------------------
# Failure handling
# ---------------------------------------------------------------------------


def test_failed_rag_keeps_the_question_and_invents_no_answer(monkeypatch):
    backend = FakeBackend()
    backend.fail_queries = {"Q2"}

    at = open_app(backend, monkeypatch)

    ask(at, "Q1")
    ask(at, "Q2")

    rows = backend.all_messages()

    # Q1's answer survives; Q2 is stored as a question only.
    assert [row["role"] for row in rows] == ["user", "assistant", "user"]
    assert rows[1]["confidence"] == 0.91
    assert rows[2]["content"] == "Q2"

    # The failure is surfaced, not hidden.
    assert any(at.error)


def test_answer_is_shown_even_if_it_cannot_be_persisted(app, monkeypatch):
    at, backend = app

    def failing_post(url, **kwargs):
        if url.rstrip("/").endswith("/messages"):
            raise requests.RequestException("storage down")

        return backend.post(url, **kwargs)

    monkeypatch.setattr(requests, "post", failing_post)

    ask(at, "Q1")

    text = rendered_text(at)

    assert "First answer." in text
    assert "could not be saved" in text


def test_chat_still_works_when_storage_is_unreachable(monkeypatch):
    """e.g. the migration has not been applied yet: degrade, do not crash."""

    backend = FakeBackend()

    def conversation_down(url, **kwargs):
        if "/api/conversations" in url:
            raise requests.RequestException("storage down")

        return backend.post(url, **kwargs)

    def get_down(url, **kwargs):
        if "/api/conversations" in url:
            raise requests.RequestException("storage down")

        return backend.get(url, **kwargs)

    monkeypatch.setattr(requests, "post", conversation_down)
    monkeypatch.setattr(requests, "get", get_down)

    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.session_state["access_token"] = "token"
    at.session_state["user"] = {"email": "u@example.com", "access_level": "public"}
    at.run()

    assert not at.exception, at.exception

    ask(at, "Q1")

    # Retrieval still ran and the answer is on screen; nothing was stored.
    assert backend.rag_calls == 1
    assert "First answer." in rendered_text(at)
    assert backend.conversations == []
