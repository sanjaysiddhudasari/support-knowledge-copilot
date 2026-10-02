from datetime import date

from pydantic import BaseModel


class Chunk(BaseModel):
    chunk_ids:str
    text:str

    source:str
    section:str

    last_updated:date
    document_type:str
    access_level:str="public"
    version: int = 1

    # Optional, backward-compatible ingestion metadata. ``None`` for chunks
    # produced before multi-format ingestion and for Markdown-only corpora.
    file_type: str | None = None
    page: int | None = None
