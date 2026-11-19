from pydantic import BaseModel


class LegalBlock(BaseModel):
    text: str
    document_title: str
    article_title: str = ""
    context: tuple[str, ...] = ()