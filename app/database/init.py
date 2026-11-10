from app.database.functions.channel_info import init_channel_info
from app.settings import logger, settings
from app.database.functions.chunks import init_chunks
import shutil
import sqlite3


LEGACY_DB_PATH = settings.database_path.parent / "chunks.db"


def _prepare_database() -> None:
    """Переносит базу знаний в bot.db, чтобы не считать эмбеддинги заново."""
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    if settings.database_path.exists():
        # Пустой файл мог остаться после неудачного старта — пересоздаём.
        if settings.database_path.stat().st_size > 0 or not LEGACY_DB_PATH.exists():
            return
        settings.database_path.unlink()

    if not LEGACY_DB_PATH.exists():
        return

    shutil.copy2(LEGACY_DB_PATH, settings.database_path)
    logger.info(
        f"База знаний скопирована: {LEGACY_DB_PATH} -> {settings.database_path}"
    )


async def init_database() -> None:
    _prepare_database()

    connection = sqlite3.connect(settings.database_path)
    try:
        logger.info("Инициализация таблицы данных информации о каналах")
        await init_channel_info(connection)

        logger.info("Инициализация таблицы данных для векторного поиска")
        await init_chunks(connection)

        connection.commit()
    finally:
        connection.close()

    logger.info("Инициализация базы данных завершена")
