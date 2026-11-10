from app.database.functions.channel_info import init_channel_info
from app.settings import logger, settings
from app.database.functions.chunks import init_chunks
import sqlite3

async def init_database() -> None:
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
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
