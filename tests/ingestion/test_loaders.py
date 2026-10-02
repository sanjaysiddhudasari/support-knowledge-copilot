"""Unit tests for the format-specific document loaders."""

from datetime import date
from pathlib import Path

import pytest

from pdf_factory import write_docx, write_pdf

from app.ingestion.loader import (
    FILE_TYPE_DOCX,
    FILE_TYPE_HTML,
    FILE_TYPE_MARKDOWN,
    FILE_TYPE_PDF,
    FILE_TYPE_TEXT,
    SUPPORTED_EXTENSIONS,
    DocumentLoadError,
    OCRNotSupportedError,
    UnsupportedFormatError,
    get_loader,
    is_supported,
    load_document,
)


# --------------------------------------------------------------------------
# Markdown
# --------------------------------------------------------------------------

FRONT_MATTER_MD = """---
source: sample.md
last_updated: 2026-07-16
document_type: guide
access_level: public
version: 3.3
---

# Authentication

## Overview
Sign in at the console.

## Reset
Use the reset link.
"""


def test_markdown_front_matter_and_text(tmp_path):
    path = tmp_path / "sample.md"
    path.write_text(FRONT_MATTER_MD, encoding="utf-8")

    document = load_document(str(path))

    assert document.file_type == FILE_TYPE_MARKDOWN
    assert document.heading_aware is True
    assert document.document_type == "guide"
    assert document.metadata["last_updated"] == date(2026, 7, 16)
    assert document.metadata["access_level"] == "public"

    # Front matter must not leak into the chunked text.
    assert not document.text.startswith("---")
    assert "last_updated" not in document.text
    assert document.text.startswith("# Authentication")


def test_markdown_without_front_matter_uses_defaults(tmp_path):
    path = tmp_path / "plain.md"
    path.write_text("# Title\n\nBody text.", encoding="utf-8")

    document = load_document(str(path))

    assert document.document_type == "guide"
    assert document.metadata["last_updated"] == date(2026, 8, 1)
    assert document.metadata["access_level"] == "internal"


# --------------------------------------------------------------------------
# Plain text
# --------------------------------------------------------------------------


def test_text_loader(tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("First paragraph.\n\nSecond paragraph.", encoding="utf-8")

    document = load_document(str(path))

    assert document.file_type == FILE_TYPE_TEXT
    assert document.heading_aware is False
    assert document.text == "First paragraph.\n\nSecond paragraph."
    assert document.metadata["document_type"] == "guide"
    assert document.metadata["access_level"] == "internal"


# --------------------------------------------------------------------------
# PDF
# --------------------------------------------------------------------------


def test_pdf_extracts_every_page(tmp_path):
    path = write_pdf(
        tmp_path / "guide.pdf",
        ["Page one alpha content", "Page two beta content"],
    )

    document = load_document(str(path))

    assert document.file_type == FILE_TYPE_PDF
    assert len(document.pages) == 2
    assert "Page one alpha content" in document.pages[0]
    assert "Page two beta content" in document.pages[1]
    assert "alpha" in document.text and "beta" in document.text
    assert document.metadata["page_count"] == 2


def test_scanned_pdf_raises_ocr_error(tmp_path):
    path = write_pdf(tmp_path / "scan.pdf", ["", ""], include_text=False)

    with pytest.raises(OCRNotSupportedError) as error:
        load_document(str(path))

    assert "OCR" in str(error.value)
    assert "not supported" in str(error.value)


def test_malformed_pdf_raises_load_error(tmp_path):
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"this is definitely not a pdf")

    with pytest.raises(DocumentLoadError):
        load_document(str(path))


# --------------------------------------------------------------------------
# DOCX
# --------------------------------------------------------------------------


def test_docx_paragraphs_in_order_and_headings(tmp_path):
    path = write_docx(
        tmp_path / "manual.docx",
        [
            ("heading1", "Overview"),
            ("paragraph", "First paragraph."),
            ("heading2", "Details"),
            ("paragraph", "Second paragraph."),
        ],
    )

    document = load_document(str(path))

    assert document.file_type == FILE_TYPE_DOCX
    assert document.heading_aware is True

    lines = document.text.splitlines()
    assert lines[0] == "# Overview"
    assert lines[1] == "First paragraph."
    assert lines[2] == "## Details"
    assert lines[3] == "Second paragraph."


def test_docx_without_headings_is_generic(tmp_path):
    path = write_docx(
        tmp_path / "plain.docx",
        [
            ("paragraph", "Only body text one."),
            ("paragraph", "Only body text two."),
        ],
    )

    document = load_document(str(path))

    assert document.heading_aware is False
    assert "Only body text one." in document.text
    assert "Only body text two." in document.text


def test_malformed_docx_raises_load_error(tmp_path):
    path = tmp_path / "broken.docx"
    path.write_bytes(b"not a docx at all")

    with pytest.raises(DocumentLoadError):
        load_document(str(path))


# --------------------------------------------------------------------------
# HTML
# --------------------------------------------------------------------------

HTML_DOCUMENT = """
<html>
  <head>
    <title>Ignored title</title>
    <style>.hidden { color: red; }</style>
    <script>alert('nope');</script>
  </head>
  <body>
    <h1>Getting Started</h1>
    <p>Hello <b>world</b>.</p>
    <noscript>enable javascript</noscript>
    <h2>Steps</h2>
    <ul>
      <li>First step</li>
      <li>Second step</li>
    </ul>
  </body>
</html>
"""


def test_html_visible_text_and_headings(tmp_path):
    path = tmp_path / "page.html"
    path.write_text(HTML_DOCUMENT, encoding="utf-8")

    document = load_document(str(path))

    assert document.file_type == FILE_TYPE_HTML
    assert document.heading_aware is True

    assert "# Getting Started" in document.text
    assert "## Steps" in document.text
    assert "Hello world" in document.text
    assert "First step" in document.text


def test_html_strips_script_style_noscript(tmp_path):
    path = tmp_path / "page.htm"
    path.write_text(HTML_DOCUMENT, encoding="utf-8")

    document = load_document(str(path))

    lowered = document.text.lower()
    assert "alert" not in lowered
    assert "color: red" not in lowered
    assert "hidden" not in lowered
    assert "enable javascript" not in lowered


def test_html_without_block_elements_falls_back_to_text(tmp_path):
    path = tmp_path / "fragment.html"
    path.write_text("<body>Just some text</body>", encoding="utf-8")

    document = load_document(str(path))

    assert "Just some text" in document.text


def test_empty_html_raises(tmp_path):
    path = tmp_path / "empty.html"
    path.write_text("   \n  ", encoding="utf-8")

    with pytest.raises(DocumentLoadError):
        load_document(str(path))


# --------------------------------------------------------------------------
# Dispatch / validation
# --------------------------------------------------------------------------


def test_supported_extensions_cover_required_formats():
    assert SUPPORTED_EXTENSIONS == {
        ".md",
        ".txt",
        ".pdf",
        ".docx",
        ".html",
        ".htm",
    }


def test_unsupported_extension_rejected(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("a,b,c", encoding="utf-8")

    with pytest.raises(UnsupportedFormatError):
        load_document(str(path))

    assert is_supported(path) is False


def test_get_loader_dispatch():
    assert get_loader("a.md").file_type == FILE_TYPE_MARKDOWN
    assert get_loader("a.txt").file_type == FILE_TYPE_TEXT
    assert get_loader("a.pdf").file_type == FILE_TYPE_PDF
    assert get_loader("a.docx").file_type == FILE_TYPE_DOCX
    assert get_loader("a.html").file_type == FILE_TYPE_HTML
    assert get_loader("a.HTM").file_type == FILE_TYPE_HTML


def test_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        load_document("data/raw/does-not-exist.md")
