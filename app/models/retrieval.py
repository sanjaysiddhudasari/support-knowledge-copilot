from pydantic import BaseModel
from app.models.chunk import Chunk

class RetrievalResult(BaseModel):
    chunk:Chunk
    score:float
    rank:int 
    source:str