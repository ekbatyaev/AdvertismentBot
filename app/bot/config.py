from aiogram import Bot, Dispatcher
from app.settings import settings

# Инициализация бота
bot = Bot(token=settings.telegram_bot_token)
dp = Dispatcher()
