from datetime import date

from pydantic import BaseModel


class Chunk(BaseModel):
    chunk_ids:str
    text:str

    source:str
    section:str

    last_updated:date
    document_type:str
    access_level:str

    