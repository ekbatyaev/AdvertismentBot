from pydantic import BaseModel, ConfigDict, Field
from typing import Optional
import numpy as np


class Chunk(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    id: Optional[int] = None

    text: str
    embedding: np.ndarray = Field(exclude=True)


class SearchResult(BaseModel):
    chunk: Chunk
    embedding_score: float
    rerank_score: float
