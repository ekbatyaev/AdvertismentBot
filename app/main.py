import asyncio
from app.settings import settings, logger
from app.bot.config import dp, bot
from app.bot.routers import user_router

async def main():
    logger.info("Старт работы бота")
    dp.include_routers(user_router)

    await bot.delete_webhook()  # убираем старые подписки
    await bot.subscribe_webhook(
        url=f"{settings.webhook_url}{settings.webhook_path}",
        secret=settings.webhook_secret,
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