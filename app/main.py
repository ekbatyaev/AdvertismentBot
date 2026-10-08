import asyncio
from app.settings import logger
from app.bot.config import dp, bot
from app.bot.routers import user_router

async def main():
    logger.info("Старт работы бота")
    dp.include_router(user_router)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())