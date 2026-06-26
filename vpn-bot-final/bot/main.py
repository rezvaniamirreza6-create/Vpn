import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from bot.handlers import user, admin, payment
from bot.middlewares import JoinCheckMiddleware, ThrottlingMiddleware
from database.db import init_db
from config import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def main():
    # Validate required config
    if not config.BOT_TOKEN:
        raise ValueError("BOT_TOKEN environment variable is not set!")
    if not config.ADMIN_IDS:
        raise ValueError("ADMIN_IDS environment variable is not set!")

    await init_db()
    logger.info("Database initialized.")

    bot = Bot(token=config.BOT_TOKEN)
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Middlewares
    dp.message.middleware(ThrottlingMiddleware())
    dp.callback_query.middleware(ThrottlingMiddleware())

    if config.FORCE_JOIN_CHANNELS:
        dp.message.middleware(JoinCheckMiddleware(bot))
        dp.callback_query.middleware(JoinCheckMiddleware(bot))

    # Routers
    dp.include_router(user.router)
    dp.include_router(admin.router)
    dp.include_router(payment.router)

    logger.info(f"Bot starting... Admin IDs: {config.ADMIN_IDS}")
    logger.info(f"Panel URL: {config.PANEL_URL}")
    logger.info(f"Database: {'PostgreSQL' if 'postgresql' in config.DATABASE_URL else 'SQLite'}")

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
