from zoneinfo import ZoneInfo
from loguru import logger
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    telegram_bot_token: str
    yandex_cloud_model: str
    yandex_cloud_folder: str
    yandex_cloud_api_key: str
    vector_store_id: str

    yandex_cloud_llm_url: str

    ai_logs_dir: Path = LOG_DIR / "ai_logs"

settings = Settings()

if __name__ == "__main__":
    print(settings.model_dump())
