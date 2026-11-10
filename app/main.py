import asyncio
from app.database.embedding_model.config import load_embedding_model
from app.database.init import init_database
from app.settings import settings, logger
from app.bot.config import dp, bot
from app.bot.routers.user import user_router
from app.bot.routers.events import event_router

async def main():
    logger.info("Старт инициализации сервиса")

    logger.info("Загрузка Embedding модели")

    load_embedding_model()

    logger.info("Загрузка базы данных")

    await init_database()

    logger.info("Инициализация бота")
    dp.include_routers(user_router)
    dp.include_routers(event_router)

    await bot.delete_webhook()  # убираем старые подписки
    await bot.subscribe_webhook(
        url=settings.webhook_url.rstrip("/") + settings.webhook_path,
        secret=settings.webhook_secret
    )

    await dp.handle_webhook(
        bot=bot,
        host="0.0.0.0",
        port=settings.webhook_port,
        path=settings.webhook_path,
        secret=settings.webhook_secret,
    )

if __name__ == "__main__":
    asyncio.run(main())
