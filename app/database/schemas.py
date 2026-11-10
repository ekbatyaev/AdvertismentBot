from pydantic import BaseModel, ConfigDict
from typing import Optional
import numpy as np

class Chunk(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    id: Optional[int] = None

    text: str
    embedding: np.ndarray

class SearchResult(BaseModel):
    chunk: Chunk
    score: float
