from app.schemas import BotChannelInfo
from contextlib import closing
from app.settings import logger, settings
import sqlite3

async def get_channel_by_link(link: str) -> BotChannelInfo | None:
    try:
        with closing(sqlite3.connect(settings.database_path)) as connection:
            connection.row_factory = sqlite3.Row
            row = connection.execute(
                    "SELECT chat_id, title, link FROM channelInfo WHERE link = ?",
                    (link,),
                ).fetchone()
        if row is not None:
            return BotChannelInfo.model_validate(**dict(row))
        else:
            logger.info(f"Канал по ссылке: {link} не найден")
    except sqlite3.IntegrityError as e:
        logger.warning(f"Ccskrf {link} не сохранена (integrity): {e}")
    except sqlite3.Error as e:
        logger.exception(f"Неожиданная ошибка SQLite для поиска ссылки {link}: {e}")

async def delete_channel_info(chat_id: int) -> bool:
    try:
        with closing(sqlite3.connect(settings.database_path)) as connection:
            with connection:
                cursor = connection.execute(
                    "DELETE FROM channelInfo WHERE chat_id = ?",
                    (chat_id,),
                )

        if cursor.rowcount == 0:
            logger.warning(f"Канал {chat_id} не найден в БД — удалять нечего.")
            return False

        logger.info(f"Запись о канале {chat_id} удалена.")
        return True

    except sqlite3.OperationalError as e:
        # нет таблицы, база заблокирована, нет доступа к файлу
        logger.error(f"Ошибка БД при удалении канала {chat_id}: {e}")
    except sqlite3.Error as e:
        logger.exception(f"Неожиданная ошибка SQLite при удалении канала {chat_id}: {e}")
    return False

async def add_channel_info(chat_info: BotChannelInfo) -> bool:
    try:
        with closing(sqlite3.connect(settings.database_path)) as connection:
            with connection:
                connection.execute(
                    "INSERT INTO channelInfo (chat_id, title, link, description, is_public) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (chat_info.chat_id, chat_info.title, chat_info.link, chat_info.description, chat_info.is_public)
                )
        logger.info(f"Запись о канале: {chat_info.model_dump(exclude_none=True)} успешно добавлена.")
        return True

    except sqlite3.IntegrityError as e:
        # дубль chat_id или None в NOT NULL-колонке
        logger.warning(f"Канал {chat_info.chat_id} не сохранён (integrity): {e}")
    except sqlite3.OperationalError as e:
        # нет таблицы, база заблокирована, нет доступа к файлу
        logger.error(f"Ошибка БД при сохранении канала {chat_info.chat_id}: {e}")
    except sqlite3.Error as e:
        # всё остальное от sqlite3
        logger.exception(f"Неожиданная ошибка SQLite для канала {chat_info.chat_id}: {e}")
    return False

async def init_channel_info(conn) -> None:
    # Создание таблицы данных о каналах
    conn.execute("CREATE TABLE IF NOT EXISTS channelInfo (chat_id INTEGER PRIMARY KEY, "
                       "title TEXT, link TEXT, description TEXT, is_public BOOLEAN NOT NULL)")

    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_channelInfo_link "
        "ON channelInfo(link) WHERE link IS NOT NULL"
    )
