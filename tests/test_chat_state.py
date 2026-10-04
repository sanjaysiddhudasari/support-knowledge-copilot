"""Conversation-state behaviour for the Streamlit UI.

The key guarantee: every assistant turn keeps its own confidence/answerability/
citations, so older answers never get re-rendered with the latest query's data.
"""

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "ui"))

from chat_state import (  # noqa: E402
    FORMAT_META,
    add_assistant_message,
    add_user_message,
    citation_page,
    citation_source_name,
    conversation_title,
    format_badge,
    format_line,
    format_meta,
    get_messages,
    init_chat_state,
    message_from_row,
    messages_from_rows,
    new_chat,
    normalize_answerable,
    normalize_confidence,
    strip_citations,
)


def test_two_responses_keep_separate_confidence():
    state = {}
    init_chat_state(state)

    add_user_message(state, "Q1")
    add_assistant_message(
        state,
        "A1",
        confidence=0.91,
        answerable=True,
        citations=[{"chunk_id": "a.md_chunk_1", "supported": True}],
    )

    add_user_message(state, "Q2")
    add_assistant_message(state, "A2", confidence=0.74, answerable=False)

    assistants = [
        message
        for message in get_messages(state)
        if message["role"] == "assistant"
    ]

    assert [round(m["confidence"], 2) for m in assistants] == [0.91, 0.74]
    assert [m["answerable"] for m in assistants] == [True, False]
    assert len(assistants[0]["citations"]) == 1
    assert assistants[1]["citations"] == []
    assert assistants[0]["query_id"] != assistants[1]["query_id"]


def test_add_user_message_shape():
    state = {}
    init_chat_state(state)

    message = add_user_message(state, "hello")

    assert message == {"role": "user", "content": "hello"}
    assert get_messages(state) == [message]


def test_error_turn_preserves_earlier_messages():
    state = {}
    init_chat_state(state)

    add_user_message(state, "Q1")
    add_assistant_message(state, "A1", confidence=0.91, answerable=True)
    add_user_message(state, "Q2")
    add_assistant_message(state, "", error="Could not reach the API")

    messages = get_messages(state)

    assert len(messages) == 4
    assert messages[1]["confidence"] == 0.91
    assert messages[3]["error"] == "Could not reach the API"
    # the user's query is not lost on failure
    assert messages[2]["content"] == "Q2"


def test_new_chat_clears_messages_but_not_session():
    state = {"access_token": "token", "user": {"email": "a@b.c"}}
    init_chat_state(state)
    add_user_message(state, "Q1")

    new_chat(state)

    assert state["messages"] == []
    assert state["access_token"] == "token"
    assert state["user"] == {"email": "a@b.c"}


def test_confidence_normalisation():
    assert normalize_confidence(0.91) == 0.91
    assert normalize_confidence({"confidence": 0.74}) == 0.74
    assert normalize_confidence(None) == 0.0
    assert normalize_confidence("nonsense") == 0.0
    assert normalize_answerable({"answerable": True}) is True
    assert normalize_answerable(None) is False


def test_format_meta_known_and_fallback():
    assert format_meta("pdf") == {"label": "PDF", "icon": "📄"}
    assert format_meta("Markdown") == FORMAT_META["markdown"]
    assert format_badge("markdown") == "📚 Markdown"
    # unknown / missing type falls back gracefully
    assert format_meta(None)["label"] == "Document"
    assert format_meta("xlsx")["icon"] == "📎"
    assert format_meta("") == {"label": "Document", "icon": "📎"}


def test_format_line_includes_page_only_for_pdf_like_citations():
    assert format_line("pdf", 7) == "PDF · Page 7"
    assert format_line("docx") == "DOCX"
    assert format_line(None) == "Document"


def test_strip_citations_and_source_name():
    assert strip_citations("Reset it. [password-policy.md_chunk_2]") == "Reset it."
    assert citation_source_name({"source": "manual.pdf"}) == "manual.pdf"
    assert citation_source_name({"chunk_id": "manual.pdf_chunk_2"}) == "manual.pdf"
    assert citation_source_name({}) == "Unknown"
    assert citation_page({"page": 2}) == 2
    assert citation_page({"page": None}) is None


# ---------------------------------------------------------------------------
# Stored rows -> display messages
# ---------------------------------------------------------------------------


def test_assistant_row_keeps_its_stored_metadata():
    message = message_from_row(
        {
            "role": "assistant",
            "content": "Answer. [manual.pdf_chunk_2]",
            "confidence": 0.91,
            "answerable": True,
            "citations": [
                {"chunk_id": "manual.pdf_chunk_2", "page": 2}
            ],
            "query_id": "abc123",
            "created_at": "2026-01-01T00:00:00+00:00",
        }
    )

    assert message["confidence"] == 0.91
    assert message["answerable"] is True
    assert message["citations"] == [
        {"chunk_id": "manual.pdf_chunk_2", "page": 2}
    ]
    assert message["query_id"] == "abc123"
    assert message["error"] is None


def test_user_row_has_no_assistant_metadata():
    message = message_from_row({"role": "user", "content": "hi"})

    assert message == {
        "role": "user",
        "content": "hi",
        "query_id": None,
        "created_at": None,
    }


def test_missing_confidence_and_citations_are_tolerated():
    message = message_from_row(
        {"role": "assistant", "content": "x", "citations": None}
    )

    assert message["confidence"] == 0.0
    assert message["answerable"] is False
    assert message["citations"] == []


def test_citations_survive_a_json_string_column():
    message = message_from_row(
        {
            "role": "assistant",
            "content": "x",
            "citations": '[{"chunk_id": "a.md_chunk_1"}]',
        }
    )

    assert message["citations"] == [{"chunk_id": "a.md_chunk_1"}]


def test_messages_from_rows_preserves_order():
    messages = messages_from_rows(
        [
            {"role": "user", "content": "one"},
            {"role": "assistant", "content": "two"},
        ]
    )

    assert [m["content"] for m in messages] == ["one", "two"]


def test_conversation_title_falls_back_when_blank():
    assert conversation_title({"title": "  Billing  "}) == "Billing"
    assert conversation_title({"title": "   "}) == "New Chat"
    assert conversation_title(None) == "New Chat"
