from zoneinfo import ZoneInfo
from loguru import logger
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

BASE_DIR = Path(__file__).resolve().parent.parent

ENV_PATH = BASE_DIR / ".env"
LOG_DIR = BASE_DIR / "logs"

MOSCOW_TZ = ZoneInfo("Europe/Moscow")

logger.add(
    LOG_DIR / "app.log",
    rotation="00:00",
    retention="14 days",
    encoding="utf-8",
    enqueue=True
)

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_PATH,
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    telegram_bot_token: str = Field(repr=False, exclude=True)
    max_bot_token: str = Field(repr=False, exclude=True)

    webhook_secret: str = Field(repr=False, exclude=True)
    webhook_port: int
    webhook_url: str
    webhook_path: str = "/max-webhook"

    llm_base_url: str
    llm_api_key: str = Field(repr=False, exclude=True)
    llm_model_name: str

    embedding_model_name: str

    embedding_model_dir: Path = BASE_DIR / "app" / "ai/database/embedding_model/user-bge-m3-int8"
    docs_dir: Path = BASE_DIR / "app" / "database" / "docs"
    ai_logs_dir: Path = LOG_DIR / "ai_logs"

    database_path: Path = BASE_DIR / "app" / "ai/database/data/bot.db"

settings = Settings()

if __name__ == "__main__":
    print(settings.model_dump())
