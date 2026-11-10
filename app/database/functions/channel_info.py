from app.schemas import BotChannelInfo
from contextlib import closing
from urllib.parse import urlsplit, urlunsplit
from app.settings import logger, settings
import re
import sqlite3

MAX_CHANNEL_HOSTS = {"max.ru", "web.max.ru"}

# Каналы, которые бот уже обслуживает. Нужны, чтобы проверка работала сразу
# после деплоя, не дожидаясь события bot_added / bot_admin_permissions_changed.
SEED_CHANNELS: tuple[BotChannelInfo, ...] = (
    BotChannelInfo(
        chat_id=-70937669495409,
        title="Systeme Electric",
        link="https://max.ru/channel_systeme_electric",
        is_public=True,
    ),
)


def normalize_channel_link(link: str) -> str:
    """Приводит ссылку на канал к виду https://<host>/<alias> без хвостового слэша."""
    value = (link or "").strip()
    if not value:
        return ""

    if "://" not in value:
        value = "https://" + value

    parts = urlsplit(value)
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = re.sub(r"/+$", "", parts.path)
    return urlunsplit(("https", host, path, "", ""))


def channel_alias(link: str) -> str:
    """Последний сегмент ссылки: алиас канала или его числовой id."""
    normalized = normalize_channel_link(link)
    if not normalized:
        return ""
    return normalized.rsplit("/", 1)[-1]


def chat_id_from_link(link: str) -> int | None:
    """Числовой id канала из ссылки. Id каналов MAX отрицательные."""
    alias = channel_alias(link)
    if not re.fullmatch(r"-?\d+", alias):
        return None
    chat_id = int(alias)
    return chat_id if chat_id < 0 else -chat_id


def is_channel_link(link: str) -> bool:
    """Ссылка вида https://max.ru/<alias> или https://web.max.ru/<id>."""
    normalized = normalize_channel_link(link)
    if not normalized:
        return False
    parts = urlsplit(normalized)
    if parts.hostname not in MAX_CHANNEL_HOSTS:
        return False
    return bool(re.fullmatch(r"[-A-Za-z0-9_]+", parts.path.strip("/")))


def _channel_from_row(row: sqlite3.Row) -> BotChannelInfo:
    return BotChannelInfo.model_validate(dict(row))


def _select_channel(connection: sqlite3.Connection, chat_id: int) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT chat_id, title, link, description, is_public "
        "FROM channelInfo WHERE chat_id = ?",
        (chat_id,),
    ).fetchone()


async def get_channel_by_chat_id(chat_id: int) -> BotChannelInfo | None:
    try:
        with closing(sqlite3.connect(settings.database_path)) as connection:
            connection.row_factory = sqlite3.Row
            row = _select_channel(connection, chat_id)
        if row is not None:
            return _channel_from_row(row)
        logger.info(f"Канал {chat_id} не найден в БД")
    except sqlite3.Error as e:
        logger.exception(f"Неожиданная ошибка SQLite для поиска канала {chat_id}: {e}")
    return None


async def get_channel_by_link(link: str) -> BotChannelInfo | None:
    key = channel_alias(link).lower()
    if not key:
        return None

    try:
        with closing(sqlite3.connect(settings.database_path)) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT chat_id, title, link, description, is_public FROM channelInfo"
            ).fetchall()
        # Ссылки сравниваем по алиасу: max.ru и web.max.ru — один и тот же канал.
        for row in rows:
            if channel_alias(row["link"] or "").lower() == key:
                return _channel_from_row(row)
        logger.info(f"Канал по ссылке {link} не найден")
    except sqlite3.Error as e:
        logger.exception(f"Неожиданная ошибка SQLite для поиска ссылки {link}: {e}")
    return None


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
                    "VALUES (?, ?, ?, ?, ?) "
                    "ON CONFLICT(chat_id) DO UPDATE SET "
                    "title = excluded.title, link = excluded.link, "
                    "description = excluded.description, is_public = excluded.is_public",
                    (
                        chat_info.chat_id,
                        chat_info.title,
                        chat_info.link,
                        chat_info.description,
                        chat_info.is_public,
                    ),
                )
        logger.info(
            f"Запись о канале: {chat_info.model_dump(exclude_none=True)} успешно сохранена."
        )
        return True

    except sqlite3.IntegrityError as e:
        # дубль ссылки у другого chat_id или None в NOT NULL-колонке
        logger.warning(f"Канал {chat_info.chat_id} не сохранён (integrity): {e}")
    except sqlite3.OperationalError as e:
        # нет таблицы, база заблокирована, нет доступа к файлу
        logger.error(f"Ошибка БД при сохранении канала {chat_info.chat_id}: {e}")
    except sqlite3.Error as e:
        # всё остальное из sqlite3
        logger.exception(f"Неожиданная ошибка SQLite для канала {chat_info.chat_id}: {e}")
    return False


async def init_channel_info(conn: sqlite3.Connection) -> None:
    # Создание таблицы данных о каналах
    conn.execute(
        "CREATE TABLE IF NOT EXISTS channelInfo (chat_id INTEGER PRIMARY KEY, "
        "title TEXT, link TEXT, description TEXT, is_public BOOLEAN NOT NULL)"
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_channelInfo_link "
        "ON channelInfo(link) WHERE link IS NOT NULL"
    )
    for channel in SEED_CHANNELS:
        conn.execute(
            "INSERT OR IGNORE INTO channelInfo "
            "(chat_id, title, link, description, is_public) VALUES (?, ?, ?, ?, ?)",
            (
                channel.chat_id,
                channel.title,
                channel.link,
                channel.description,
                channel.is_public,
            ),
        )
