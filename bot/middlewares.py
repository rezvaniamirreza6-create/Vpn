from aiogram import BaseMiddleware
from cachetools import TTLCache

throttle_cache = TTLCache(maxsize=10000, ttl=1)


class ThrottlingMiddleware(BaseMiddleware):
    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        if user:
            key = f"t:{user.id}"
            if key in throttle_cache:
                return
            throttle_cache[key] = 1
        return await handler(event, data)


class BotToggleMiddleware(BaseMiddleware):
    """When the bot is switched off by the owner, blocks everyone except admins
    and replies with the given reason instead."""
    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        if user:
            from config import config
            if user.id not in config.ADMIN_IDS:
                from database.db import AsyncSessionLocal
                from database import crud
                async with AsyncSessionLocal() as db:
                    enabled = await crud.get_setting(db, "bot_enabled", "true")
                    reason = await crud.get_setting(db, "bot_off_reason", "")
                if enabled == "false":
                    if hasattr(event, "answer"):
                        try:
                            text = "⛔️ ربات موقتاً خاموش است."
                            if reason:
                                text += f"\n📝 دلیل: {reason}"
                            await event.answer(text)
                        except Exception:
                            pass
                    return
        return await handler(event, data)


force_join_ok_cache = TTLCache(maxsize=20000, ttl=600)


class ForceJoinMiddleware(BaseMiddleware):
    """Enforces mandatory channel-join on every interaction, not just /start.
    Results are cached for a few minutes per user so we don't hammer the
    Telegram API with a get_chat_member call for every single message."""
    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        if user:
            from config import config
            if user.id not in config.ADMIN_IDS:
                text = getattr(event, "text", None)
                cb_data = getattr(event, "data", None)
                is_start = bool(text and text.startswith("/start"))
                is_check_join = (cb_data == "check_join")
                if not is_start and not is_check_join:
                    if force_join_ok_cache.get(user.id):
                        return await handler(event, data)
                    from bot.handlers.user import check_force_join
                    from bot.keyboards import force_join_kb
                    try:
                        not_joined = await check_force_join(event.bot, user.id)
                    except Exception:
                        not_joined = []
                    if not_joined:
                        msg_text = "📢 برای استفاده از ربات ابتدا در کانال‌های زیر عضو شوید:"
                        try:
                            if hasattr(event, "message") and event.message:
                                await event.answer()
                                await event.message.answer(msg_text, reply_markup=force_join_kb(not_joined))
                            else:
                                await event.answer(msg_text, reply_markup=force_join_kb(not_joined))
                        except Exception:
                            pass
                        return
                    else:
                        force_join_ok_cache[user.id] = True
        return await handler(event, data)


class PhoneVerifyMiddleware(BaseMiddleware):
    """Requires a verified Iranian phone number before any interaction,
    not just /start (same bypass class as the ban/force-join bugs)."""
    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        if user:
            from config import config
            if user.id not in config.ADMIN_IDS:
                text = getattr(event, "text", None)
                is_start = bool(text and text.startswith("/start"))
                is_contact = bool(getattr(event, "contact", None))
                if not is_start and not is_contact:
                    from database.db import AsyncSessionLocal
                    from database import crud
                    async with AsyncSessionLocal() as db:
                        db_user = await crud.get_user(db, user.id)
                    if not db_user or (not db_user.phone and not db_user.phone_exempt):
                        from bot.keyboards import phone_request_kb
                        msg_text = "🔐 برای استفاده از ربات، لطفاً اول شماره تلفنتون رو با دکمه‌ی زیر ارسال کنید."
                        try:
                            if hasattr(event, "message") and event.message:
                                await event.answer()
                                await event.message.answer(msg_text, reply_markup=phone_request_kb())
                            else:
                                await event.answer(msg_text, reply_markup=phone_request_kb())
                        except Exception:
                            pass
                        return
        return await handler(event, data)


class BanCheckMiddleware(BaseMiddleware):
    """Blocks every message/callback from a banned user, not just /start."""
    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        if user:
            from config import config
            if user.id not in config.ADMIN_IDS:
                from database.db import AsyncSessionLocal, UserStatus
                from database import crud
                async with AsyncSessionLocal() as db:
                    db_user = await crud.get_user(db, user.id)
                if db_user and db_user.status == UserStatus.BANNED:
                    if hasattr(event, "answer"):
                        try:
                            await event.answer("⛔️ حساب شما مسدود شده است.")
                        except Exception:
                            pass
                    return
        return await handler(event, data)
