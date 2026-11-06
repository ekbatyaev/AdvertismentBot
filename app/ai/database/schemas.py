from pydantic import BaseModel
from typing import Optional
import numpy as np

class Chunk(BaseModel):
    id: Optional[int] = None

    text: str
    embedding: np.ndarray
