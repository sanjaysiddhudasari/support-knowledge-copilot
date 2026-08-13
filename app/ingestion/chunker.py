import re
from datetime import date

from app.models.chunk import Chunk


def chunk_markdown(
    text: str,
    source: str,
    last_updated: date,
    document_type: str,
    access_level: str,
) -> list[Chunk]:

    lines = text.splitlines()

    chunks: list[Chunk] = []

    current_heading = "General"
    current_content: list[str] = []
    chunk_number = 1

    def save_current_chunk():
        nonlocal chunk_number

        content = "\n".join(current_content).strip()

        if not content:
            return

        chunk_text = f"{current_heading}\n\n{content}"

        chunks.append(
            Chunk(
                chunk_ids=f"{source}_chunk_{chunk_number}",
                text=chunk_text,
                source=source,
                section=current_heading,
                last_updated=last_updated,
                document_type=document_type,
                access_level=access_level,
            )
        )

        chunk_number += 1

    for line in lines:

        heading_match = re.match(
            r"^(#{1,3})\s+(.+?)\s*$",
            line
        )

        if heading_match:
            save_current_chunk()

            current_heading = heading_match.group(2).strip()
            current_content = []

        else:
            if line.strip():
                current_content.append(line)

    save_current_chunk()

    return chunks