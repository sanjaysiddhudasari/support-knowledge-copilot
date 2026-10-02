"""Chunking for every supported document format.

The public entry point for the ingestion pipeline is :func:`chunk_document`,
which dispatches on the normalized :class:`~app.ingestion.loader.LoadedDocument`
produced by the loader layer.

``chunk_markdown`` is kept as a thin, behaviour-preserving wrapper used by the
existing local scripts; all formats ultimately flow through the shared
``chunk_sections`` / ``chunk_text`` helpers so chunking logic is not duplicated.

All chunk IDs are deterministic: ``{source}_chunk_{number}`` numbered
sequentially from 1 in document order.
"""

import re
from datetime import date

from app.ingestion.loader import FILE_TYPE_PDF, LoadedDocument
from app.models.chunk import Chunk


DEFAULT_SECTION = "General"
DEFAULT_MAX_CHARS = 1200

_HEADING_RE = re.compile(
    r"^(#{1,3})\s+(.+?)\s*$"
)

_PARAGRAPH_RE = re.compile(
    r"\n\s*\n"
)


def _parse_heading_sections(text: str) -> list[tuple[str, list[str]]]:
    """Split Markdown-style text into ``(heading, content lines)`` sections.

    Reproduces the original Markdown chunker's parsing exactly: ``#``-``###``
    headings start a new section, blank lines are dropped and everything else
    is content.
    """

    sections: list[tuple[str, list[str]]] = []

    current_heading = DEFAULT_SECTION
    current_content: list[str] = []

    for line in text.splitlines():

        heading_match = _HEADING_RE.match(line)

        if heading_match:
            sections.append((current_heading, current_content))

            current_heading = heading_match.group(2).strip()
            current_content = []

        elif line.strip():
            current_content.append(line)

    sections.append((current_heading, current_content))

    return sections


def chunk_sections(
    sections: list[tuple[str, list[str]]],
    source: str,
    last_updated: date,
    document_type: str,
    access_level: str,
    version: int = 1,
    start_number: int = 1,
    file_type: str | None = None,
    page: int | None = None,
) -> list[Chunk]:
    """Build heading-aware chunks from parsed sections."""

    chunks: list[Chunk] = []

    chunk_number = start_number

    for heading, content_lines in sections:

        content = "\n".join(content_lines).strip()

        if not content:
            continue

        chunk_text = f"{heading}\n\n{content}"

        chunks.append(
            Chunk(
                chunk_ids=f"{source}_chunk_{chunk_number}",
                text=chunk_text,
                source=source,
                section=heading,
                last_updated=last_updated,
                document_type=document_type,
                access_level=access_level,
                version=version,
                file_type=file_type,
                page=page,
            )
        )

        chunk_number += 1

    return chunks


def chunk_markdown(
    text: str,
    source: str,
    last_updated: date,
    document_type: str,
    access_level: str,
    version:int=1,
) -> list[Chunk]:
    """Heading-aware Markdown chunking. Preserved for backward compatibility."""

    return chunk_sections(
        _parse_heading_sections(text),
        source=source,
        last_updated=last_updated,
        document_type=document_type,
        access_level=access_level,
        version=version,
    )


def _split_paragraphs(text: str) -> list[str]:
    """Split text into non-empty paragraphs on blank lines."""

    return [
        paragraph.strip()
        for paragraph in _PARAGRAPH_RE.split(text)
        if paragraph.strip()
    ]


def _split_long_paragraph(
    paragraph: str,
    max_chars: int,
) -> list[str]:
    """Hard-wrap an over-long paragraph on word boundaries."""

    if len(paragraph) <= max_chars:
        return [paragraph]

    pieces: list[str] = []
    current = ""

    for word in paragraph.split():

        if current and len(current) + 1 + len(word) > max_chars:
            pieces.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()

    if current:
        pieces.append(current)

    return pieces


def _group_paragraphs(
    paragraphs: list[str],
    max_chars: int,
) -> list[str]:
    """Group paragraphs into chunks of at most ``max_chars`` characters."""

    groups: list[str] = []

    current: list[str] = []
    current_length = 0

    for paragraph in paragraphs:

        for piece in _split_long_paragraph(paragraph, max_chars):

            separator = 2 if current else 0

            if (
                current
                and current_length + separator + len(piece) > max_chars
            ):
                groups.append("\n\n".join(current))
                current = [piece]
                current_length = len(piece)
            else:
                current.append(piece)
                current_length += separator + len(piece)

    if current:
        groups.append("\n\n".join(current))

    return groups


def chunk_text(
    text: str,
    source: str,
    last_updated: date,
    document_type: str,
    access_level: str,
    version: int = 1,
    start_number: int = 1,
    section: str = DEFAULT_SECTION,
    file_type: str | None = None,
    page: int | None = None,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> list[Chunk]:
    """Generic paragraph-based chunking for non-heading formats (.txt, .pdf)."""

    chunks: list[Chunk] = []

    chunk_number = start_number

    for group in _group_paragraphs(
        _split_paragraphs(text),
        max_chars,
    ):
        chunks.append(
            Chunk(
                chunk_ids=f"{source}_chunk_{chunk_number}",
                text=group,
                source=source,
                section=section,
                last_updated=last_updated,
                document_type=document_type,
                access_level=access_level,
                version=version,
                file_type=file_type,
                page=page,
            )
        )

        chunk_number += 1

    return chunks


def chunk_pages(
    pages: list[str],
    source: str,
    last_updated: date,
    document_type: str,
    access_level: str,
    version: int = 1,
    start_number: int = 1,
    file_type: str | None = FILE_TYPE_PDF,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> list[Chunk]:
    """Page-aware chunking for PDFs, preserving page numbers as metadata."""

    chunks: list[Chunk] = []

    chunk_number = start_number

    for page_number, page_text in enumerate(pages, start=1):

        for group in _group_paragraphs(
            _split_paragraphs(page_text),
            max_chars,
        ):
            chunks.append(
                Chunk(
                    chunk_ids=f"{source}_chunk_{chunk_number}",
                    text=group,
                    source=source,
                    section=f"Page {page_number}",
                    last_updated=last_updated,
                    document_type=document_type,
                    access_level=access_level,
                    version=version,
                    file_type=file_type,
                    page=page_number,
                )
            )

            chunk_number += 1

    return chunks


def chunk_document(
    document: LoadedDocument,
    version: int = 1,
    start_number: int = 1,
) -> list[Chunk]:
    """Chunk a loaded document using format-appropriate behaviour.

    ``.md`` / ``.html`` -> heading-aware, ``.docx`` -> heading-aware when
    headings exist, otherwise generic, ``.txt`` -> generic, ``.pdf`` ->
    page-aware generic.
    """

    if document.file_type == FILE_TYPE_PDF and document.pages is not None:

        return chunk_pages(
            document.pages,
            source=document.source,
            last_updated=document.metadata["last_updated"],
            document_type=document.document_type,
            access_level=document.metadata["access_level"],
            version=version,
            start_number=start_number,
            file_type=document.file_type,
        )

    if document.heading_aware:

        return chunk_sections(
            _parse_heading_sections(document.text),
            source=document.source,
            last_updated=document.metadata["last_updated"],
            document_type=document.document_type,
            access_level=document.metadata["access_level"],
            version=version,
            start_number=start_number,
            file_type=document.file_type,
        )

    return chunk_text(
        document.text,
        source=document.source,
        last_updated=document.metadata["last_updated"],
        document_type=document.document_type,
        access_level=document.metadata["access_level"],
        version=version,
        start_number=start_number,
        file_type=document.file_type,
    )
