"""YAML-style front matter handling for Markdown documents.

Only Markdown uses front matter. Non-Markdown formats fall back to the
default metadata defined here. Behaviour matches the previous inline
implementation that lived in ``app/ingestion/ingest.py`` and
``app/retrieval/indexer.py``.
"""

import re
from datetime import date


DEFAULT_LAST_UPDATED = date(2026, 8, 1)
DEFAULT_DOCUMENT_TYPE = "guide"
DEFAULT_ACCESS_LEVEL = "internal"

_FRONT_MATTER_RE = re.compile(
    r"^---\s*\n(.*?)\n---\s*\n",
    re.DOTALL,
)


def default_metadata() -> dict:
    """Metadata defaults used when no front matter is present."""

    return {
        "last_updated": DEFAULT_LAST_UPDATED,
        "document_type": DEFAULT_DOCUMENT_TYPE,
        "access_level": DEFAULT_ACCESS_LEVEL,
    }


def remove_front_matter(text: str) -> str:
    """Return ``text`` without its leading YAML front matter block."""

    if not text.startswith("---"):
        return text

    match = _FRONT_MATTER_RE.match(text)

    if match:
        return text[match.end():]

    return text


def parse_front_matter(text: str) -> dict:
    """Extract ``last_updated``, ``document_type`` and ``access_level``."""

    metadata = default_metadata()

    if not text.startswith("---"):
        return metadata

    match = _FRONT_MATTER_RE.match(text)

    if not match:
        return metadata

    for line in match.group(1).splitlines():

        if ":" not in line:
            continue

        key, value = line.split(":", 1)

        key = key.strip()
        value = value.strip()

        if key == "last_updated":

            try:
                year, month, day = (
                    int(part)
                    for part in value.split("-")[:3]
                )
            except (TypeError, ValueError):
                continue

            metadata["last_updated"] = date(
                year,
                month,
                day,
            )

        elif key == "document_type":
            metadata["document_type"] = value

        elif key == "access_level":
            metadata["access_level"] = value

    return metadata
