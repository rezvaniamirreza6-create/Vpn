import asyncio
import logging
import socket
import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.exceptions import TelegramNetworkError
from bot.handlers import user, admin
from bot.middlewares import ThrottlingMiddleware, BanCheckMiddleware, BotToggleMiddleware, ForceJoinMiddleware, PhoneVerifyMiddleware
from database.db import init_db
from config import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def build_session() -> AiohttpSession:
    session = AiohttpSession()
    session._connector_init = {
        "family": socket.AF_INET,
        "limit": 100,
        "ttl_dns_cache": 60,
    }
    return session


async def wait_for_bot(bot: Bot, attempts: int = 8, delay: float = 3.0):
    last_err = None
    for i in range(1, attempts + 1):
        try:
            me = await bot.get_me(request_timeout=10)
            logger.info(f"Connected as @{me.username}")
            return me
        except (TelegramNetworkError, asyncio.TimeoutError) as e:
            last_err = e
            logger.warning(f"getMe attempt {i}/{attempts} failed: {e}. Retrying in {delay}s...")
            await asyncio.sleep(delay)
    raise last_err


async def main():
    if not config.BOT_TOKEN:
        raise ValueError("BOT_TOKEN environment variable is not set!")
    if not config.ADMIN_IDS:
        raise ValueError("ADMIN_IDS environment variable is not set!")

    await init_db()
    logger.info("Database initialized.")

    from database.db import AsyncSessionLocal
    from panels.sanei import panel
    async with AsyncSessionLocal() as db:
        await panel.reload_settings(db)
    logger.info(f"Panel URL: {panel.base_url}")

    bot = Bot(token=config.BOT_TOKEN, session=build_session())
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    dp.message.middleware(ThrottlingMiddleware())
    dp.callback_query.middleware(ThrottlingMiddleware())
    dp.message.middleware(BanCheckMiddleware())
    dp.callback_query.middleware(BanCheckMiddleware())
    dp.message.middleware(PhoneVerifyMiddleware())
    dp.callback_query.middleware(PhoneVerifyMiddleware())
    dp.message.middleware(BotToggleMiddleware())
    dp.callback_query.middleware(BotToggleMiddleware())
    dp.message.middleware(ForceJoinMiddleware())
    dp.callback_query.middleware(ForceJoinMiddleware())

    dp.include_router(user.router)
    dp.include_router(admin.router)

    logger.info(f"Bot starting... Admins: {config.ADMIN_IDS}")

    await wait_for_bot(bot)

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
