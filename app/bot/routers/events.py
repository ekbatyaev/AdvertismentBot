from maxapi import Router
from maxapi.types.updates.bot_added import BotAdded
from maxapi.types.updates.bot_removed import BotRemoved
from app.settings import logger
from app.schemas import BotChannelInfo
from app.database.functions.channel_info import add_channel_info, delete_channel_info

# Инициализация путей использования бота
event_router = Router(router_id="event")

@event_router.bot_added()
async def process_bot_added(event: BotAdded):
    try:
        data = await event.bot.get_chat_by_id(event.chat_id)
        chat_info = BotChannelInfo(chat_id=data.chat_id, title=data.title, link=data.link,
                                   description=data.description, is_public=data.is_public)
    except Exception as e:
        logger.exception(f"Ошибка, get_chat_by_id({event.chat_id}) failed: {e}")
        return

    logger.info(
        f"Бот добавлен в канал, информация о канале: {chat_info.model_dump(exclude_none=True)})"
    )

    await add_channel_info(chat_info)

@event_router.bot_removed()
async def process_bot_removed(event: BotRemoved):
    await delete_channel_info(event.chat_id)
