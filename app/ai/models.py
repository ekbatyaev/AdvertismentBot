from typing import Any

from pydantic import BaseModel

class AiClientSendRequestResponse(BaseModel):
    result: Any
    input_tokens: int = 0
    output_tokens: int = 0
