from typing import Optional
from pydantic import BaseModel

class BotChannelInfo(BaseModel):
    chat_id: int

    title: Optional[str] = None
    link: Optional[str] = None
    description: Optional[str] = None

    is_public: bool = False
