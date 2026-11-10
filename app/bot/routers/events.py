from maxapi import Router
from maxapi.enums.chat_permission import ChatPermission
from maxapi.types.updates.bot_added import BotAdded
from maxapi.types.updates.bot_removed import BotRemoved
from maxapi.types.updates.bot_admin_permissions_changed import (
    BotAdminPermissionsChanged,
)
from app.settings import logger
from app.schemas import BotChannelInfo
from app.database.functions.channel_info import add_channel_info, delete_channel_info

# Инициализация путей использования бота
event_router = Router(router_id="event")


async def _save_channel(bot, chat_id: int) -> None:
    """Забирает данные канала из API и сохраняет (или обновляет) их в БД."""
    try:
        data = await bot.get_chat_by_id(chat_id)
        chat_info = BotChannelInfo(chat_id=data.chat_id, title=data.title, link=data.link,
                                   description=data.description, is_public=data.is_public)
    except Exception as e:
        logger.exception(f"Ошибка, get_chat_by_id({chat_id}) failed: {e}")
        return

    logger.info(
        f"Информация о канале: {chat_info.model_dump(exclude_none=True)}"
    )

    await add_channel_info(chat_info)


@event_router.bot_added()
async def process_bot_added(event: BotAdded):
    if not event.is_channel:
        logger.info(f"Бот добавлен в чат {event.chat_id} — это не канал, пропускаем.")
        return

    logger.info(f"Бот добавлен в канал {event.chat_id}")
    await _save_channel(event.bot, event.chat_id)


@event_router.bot_removed()
async def process_bot_removed(event: BotRemoved):
    if not event.is_channel:
        logger.info(f"Бот удалён из чата {event.chat_id} — это не канал, пропускаем.")
        return

    logger.info(f"Бот удалён из канала {event.chat_id}")
    await delete_channel_info(event.chat_id)


@event_router.bot_admin_permissions_changed()
async def process_bot_admin_permissions_changed(event: BotAdminPermissionsChanged):
    """Бот получил или потерял права администратора канала."""
    if not event.is_channel:
        logger.info(
            f"Права бота изменились в чате {event.chat_id} — это не канал, пропускаем."
        )
        return

    if not event.is_admin:
        logger.warning(
            f"Бот перестал быть администратором канала {event.chat_id}: "
            "проверка канала недоступна до выдачи прав."
        )
        return

    if ChatPermission.READ_ALL_MESSAGES not in (event.permissions or []):
        logger.warning(
            f"Бот администратор канала {event.chat_id}, но без права "
            "«Читать все сообщения»."
        )

    # Права выдали — сохраняем или обновляем данные канала.
    logger.info(f"Бот получил права администратора канала {event.chat_id}")
    await _save_channel(event.bot, event.chat_id)
