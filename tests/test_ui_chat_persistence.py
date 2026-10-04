"""End-to-end check of the reported bug, through the real Streamlit script.

Two queries are answered by a mocked API. Each assistant turn must keep its own
confidence/citations — the second query must not overwrite the first one's.
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


@pytest.fixture
def app(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        query = (kwargs.get("json") or {}).get("query")
        calls.append(query)
        return FakeResponse(ANSWERS[query])

    monkeypatch.setattr(requests, "post", fake_post)

    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.session_state["access_token"] = "token"
    at.session_state["user"] = {
        "email": "user@example.com",
        "access_level": "public",
    }
    at.run()

    assert not at.exception, at.exception

    return at, calls


def rendered_text(at) -> str:
    parts = [element.value for element in at.markdown]
    parts += [element.value for element in at.caption]
    return "\n".join(parts)


def test_two_queries_keep_separate_confidence(app):
    at, calls = app

    at.chat_input[0].set_value("Q1").run()
    assert not at.exception, at.exception

    at.chat_input[0].set_value("Q2").run()
    assert not at.exception, at.exception

    assert calls == ["Q1", "Q2"]

    messages = at.session_state["messages"]
    assistants = [m for m in messages if m["role"] == "assistant"]

    assert [round(m["confidence"], 2) for m in assistants] == [0.91, 0.74]
    assert [m["answerable"] for m in assistants] == [True, False]
    assert len(assistants[0]["citations"]) == 1
    assert assistants[1]["citations"] == []
    assert assistants[0]["query_id"] != assistants[1]["query_id"]


def test_history_renders_each_message_with_its_own_metadata(app):
    at, _ = app

    at.chat_input[0].set_value("Q1").run()
    at.chat_input[0].set_value("Q2").run()

    text = rendered_text(at)

    # The older answer still shows its own 91%, not the latest 74%.
    assert "Confidence 91%" in text
    assert "Confidence 74%" in text

    # Citation markers are stripped for display but kept in the stored answer.
    assert "[manual.pdf_chunk_2]" not in text
    assert "[manual.pdf_chunk_2]" in at.session_state["messages"][1]["content"]


def test_source_card_shows_format_and_page(app):
    at, _ = app

    at.chat_input[0].set_value("Q1").run()

    text = rendered_text(at)

    assert "manual.pdf" in text
    assert "PDF · Page 2" in text
    assert "📄 PDF" in text


def test_new_chat_clears_history_without_logging_out(app):
    at, _ = app

    at.chat_input[0].set_value("Q1").run()
    assert at.session_state["messages"]

    new_chat_button = next(
        button for button in at.button if button.label == "+ New Chat"
    )
    new_chat_button.click().run()

    assert at.session_state["messages"] == []
    assert at.session_state["access_token"] == "token"


def test_api_failure_preserves_earlier_messages(monkeypatch):
    responses = {**ANSWERS}

    def fake_post(url, **kwargs):
        query = (kwargs.get("json") or {}).get("query")

        if query == "Q2":
            raise requests.RequestException("connection refused")

        return FakeResponse(responses[query])

    monkeypatch.setattr(requests, "post", fake_post)

    at = AppTest.from_file(APP_PATH, default_timeout=30)
    at.session_state["access_token"] = "token"
    at.session_state["user"] = {"email": "u@e.com", "access_level": "public"}
    at.run()

    at.chat_input[0].set_value("Q1").run()
    at.chat_input[0].set_value("Q2").run()

    messages = at.session_state["messages"]

    # Q1 answer survives, Q2's question is kept, and the error is shown.
    assert len(messages) == 4
    assert messages[1]["confidence"] == 0.91
    assert messages[2]["content"] == "Q2"
    assert messages[3]["error"]
