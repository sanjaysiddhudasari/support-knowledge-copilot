"""Unit tests for format-appropriate chunking and deterministic chunk IDs."""

from datetime import date

from pdf_factory import write_docx, write_pdf

from app.ingestion.chunker import (
    DEFAULT_MAX_CHARS,
    chunk_document,
    chunk_markdown,
    chunk_text,
)
from app.ingestion.loader import load_document


LAST_UPDATED = date(2026, 8, 1)


def test_generic_text_chunking_splits_long_text():
    paragraphs = [
        f"Paragraph number {index} " + ("word " * 40)
        for index in range(30)
    ]
    text = "\n\n".join(paragraphs)

    chunks = chunk_text(
        text,
        source="long.txt",
        last_updated=LAST_UPDATED,
        document_type="guide",
        access_level="internal",
    )

    assert len(chunks) > 1
    # Chunk IDs are sequential and deterministic.
    assert [c.chunk_ids for c in chunks] == [
        f"long.txt_chunk_{number}"
        for number in range(1, len(chunks) + 1)
    ]
    # Everything is preserved and no chunk blows past the budget.
    assert all(len(c.text) <= DEFAULT_MAX_CHARS for c in chunks)
    joined = " ".join(c.text for c in chunks)
    for paragraph in paragraphs:
        assert paragraph.split(" word")[0] in joined


def test_generic_chunking_merges_short_paragraphs():
    chunks = chunk_text(
        "One.\n\nTwo.\n\nThree.",
        source="short.txt",
        last_updated=LAST_UPDATED,
        document_type="guide",
        access_level="internal",
    )

    assert len(chunks) == 1
    assert chunks[0].chunk_ids == "short.txt_chunk_1"
    assert "One." in chunks[0].text and "Three." in chunks[0].text


def test_chunk_text_is_deterministic():
    text = "\n\n".join(f"Paragraph {i}." for i in range(50))

    first = chunk_text(
        text, "x.txt", LAST_UPDATED, "guide", "internal"
    )
    second = chunk_text(
        text, "x.txt", LAST_UPDATED, "guide", "internal"
    )

    assert [c.model_dump() for c in first] == [c.model_dump() for c in second]


def test_chunk_document_markdown_matches_chunk_markdown(tmp_path):
    path = tmp_path / "doc.md"
    path.write_text(
        "# Title\n\nIntro text.\n\n## Section\n\nBody text.\n",
        encoding="utf-8",
    )

    document = load_document(str(path))

    from_pipeline = chunk_document(document)
    from_legacy = chunk_markdown(
        document.text,
        source="doc.md",
        last_updated=document.metadata["last_updated"],
        document_type=document.document_type,
        access_level=document.metadata["access_level"],
    )

    # The only difference is the optional file_type field added by the loader.
    assert [
        c.model_dump(exclude={"file_type"}) for c in from_pipeline
    ] == [
        c.model_dump(exclude={"file_type"}) for c in from_legacy
    ]


def test_txt_document_uses_generic_chunking_with_file_type(tmp_path):
    path = tmp_path / "doc.txt"
    path.write_text(
        "First block.\n\nSecond block.",
        encoding="utf-8",
    )

    chunks = chunk_document(load_document(str(path)))

    assert len(chunks) == 1
    assert chunks[0].file_type == "text"
    assert chunks[0].page is None
    assert chunks[0].section == "General"


def test_pdf_chunks_preserve_page_metadata(tmp_path):
    path = write_pdf(
        tmp_path / "guide.pdf",
        ["Alpha on page one", "Beta on page two"],
    )

    chunks = chunk_document(load_document(str(path)))

    assert [c.chunk_ids for c in chunks] == [
        "guide.pdf_chunk_1",
        "guide.pdf_chunk_2",
    ]
    assert [c.page for c in chunks] == [1, 2]
    assert [c.section for c in chunks] == ["Page 1", "Page 2"]
    assert chunks[0].file_type == "pdf"
    assert "Alpha" in chunks[0].text
    assert "Beta" in chunks[1].text


def test_html_chunks_are_heading_aware(tmp_path):
    path = tmp_path / "doc.html"
    path.write_text(
        "<h1>Overview</h1><p>Intro.</p><h2>Details</h2><p>Body.</p>",
        encoding="utf-8",
    )

    chunks = chunk_document(load_document(str(path)))

    assert [c.section for c in chunks] == ["Overview", "Details"]
    assert chunks[0].text.startswith("Overview")


def test_docx_chunks_are_heading_aware(tmp_path):
    path = write_docx(
        tmp_path / "doc.docx",
        [
            ("heading1", "Overview"),
            ("paragraph", "Intro."),
            ("heading2", "Details"),
            ("paragraph", "Body."),
        ],
    )

    chunks = chunk_document(load_document(str(path)))

    assert [c.section for c in chunks] == ["Overview", "Details"]


def test_metadata_propagates_to_chunks(tmp_path):
    path = tmp_path / "doc.md"
    path.write_text(
        "---\nlast_updated: 2026-07-16\n"
        "document_type: guide\naccess_level: public\n---\n\n"
        "# Title\n\nBody.",
        encoding="utf-8",
    )

    chunk = chunk_document(load_document(str(path)), version=4)[0]

    assert chunk.last_updated == date(2026, 7, 16)
    assert chunk.document_type == "guide"
    assert chunk.access_level == "public"
    assert chunk.version == 4
    assert chunk.source == "doc.md"
