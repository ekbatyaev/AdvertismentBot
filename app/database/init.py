from app.database.functions.channel_info import init_channel_info
from app.settings import logger, settings
from app.database.functions.chunks import init_chunks
import sqlite3


async def init_database() -> None:
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)  # создаём папку под базу, если её нет
    connection = sqlite3.connect(settings.database_path)

    logger.info("Инициализация таблицы данных информации о каналх")

    await init_channel_info(connection)

    logger.info("Инициализация таблицы данных для векторного поиска")

    await init_chunks(connection)

    logger.info("Инициализация базы данных завершена")
