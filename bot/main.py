import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from bot.handlers import user, admin
from bot.middlewares import ThrottlingMiddleware
from database.db import init_db
from config import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def check_usage_notifications(bot: Bot):
    """بررسی مصرف 80% هر ساعت"""
    from database.db import AsyncSessionLocal
    from database import crud
    while True:
        try:
            async with AsyncSessionLocal() as db:
                services = await crud.get_services_to_check(db)
                usage_text = await crud.get_setting(db, "usage_80_text", "")
            for svc in services:
                try:
                    traffic = None
                    from panels.sanei import panel
                    traffic = await panel.get_client_traffic(svc.panel_email)
                    if not traffic:
                        continue
                    used_bytes = traffic.get("up", 0) + traffic.get("down", 0)
                    total_bytes = svc.traffic_gb * 1024**3
                    if total_bytes == 0:
                        continue
                    percent = (used_bytes / total_bytes) * 100
                    if percent >= 80:
                        used_gb = round(used_bytes / 1024**3, 2)
                        remaining = max(0, round(svc.traffic_gb - used_gb, 2))
                        text = usage_text.replace("{percent}", str(int(percent)))
                        text = text.replace("{total}", str(svc.traffic_gb))
                        text = text.replace("{used}", str(used_gb))
                        text = text.replace("{remaining}", str(remaining))
                        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
                        kb = InlineKeyboardMarkup(inline_keyboard=[[
                            InlineKeyboardButton(text="🔄 تمدید سرویس", callback_data=f"renew:{svc.id}")
                        ]])
                        await bot.send_message(svc.user.telegram_id, text, reply_markup=kb)
                        async with AsyncSessionLocal() as db2:
                            await crud.update_service(db2, svc.id, notified_80=True,
                                used_traffic_gb=used_gb)
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"Usage check error: {e}")
        await asyncio.sleep(3600)


async def main():
    if not config.BOT_TOKEN:
        raise ValueError("BOT_TOKEN not set!")

    await init_db()
    logger.info("Database initialized.")

    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.middleware(ThrottlingMiddleware())
    dp.callback_query.middleware(ThrottlingMiddleware())

    dp.include_router(user.router)
    dp.include_router(admin.router)

    logger.info(f"Bot starting... Admins: {config.ADMIN_IDS}")

    asyncio.create_task(check_usage_notifications(bot))

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
