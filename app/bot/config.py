from maxapi import Bot, Dispatcher
from maxapi.context import SimpleEventIsolation

from app.settings import settings

# Инициализация бота
bot = Bot(token = settings.max_bot_token)
dp = Dispatcher(use_create_task = True,
                event_isolation = SimpleEventIsolation())
