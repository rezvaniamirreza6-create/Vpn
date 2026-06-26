import asyncio
from typing import Callable, Dict, Any, Awaitable
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Message, CallbackQuery
from cachetools import TTLCache
from config import config


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(self, rate_limit: float = 0.7):
        self._cache: TTLCache = TTLCache(maxsize=10000, ttl=rate_limit)

    async def __call__(self, handler: Callable, event: TelegramObject, data: Dict[str, Any]) -> Any:
        user = data.get("event_from_user")
        if user:
            if user.id in self._cache:
                return
            self._cache[user.id] = True
        return await handler(event, data)


class JoinCheckMiddleware(BaseMiddleware):
    def __init__(self, bot):
        self.bot = bot

    async def __call__(self, handler: Callable, event: TelegramObject, data: Dict[str, Any]) -> Any:
        if not config.FORCE_JOIN_CHANNELS:
            return await handler(event, data)

        user = data.get("event_from_user")
        if not user or user.id in config.ADMIN_IDS:
            return await handler(event, data)

        not_joined = []
        for ch in config.FORCE_JOIN_CHANNELS:
            try:
                member = await self.bot.get_chat_member(ch, user.id)
                if member.status in ("left", "kicked"):
                    not_joined.append(ch)
            except Exception:
                pass

        if not_joined:
            from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
            buttons = [[InlineKeyboardButton(text=f"📢 عضویت در کانال {ch}", url=f"https://t.me/{ch.lstrip('@')}")] for ch in not_joined]
            buttons.append([InlineKeyboardButton(text="✅ عضو شدم", callback_data="check_join")])
            kb = InlineKeyboardMarkup(inline_keyboard=buttons)
            text = "⚠️ برای استفاده از ربات، ابتدا در کانال‌های زیر عضو شوید:"
            if isinstance(event, Message):
                await event.answer(text, reply_markup=kb)
            elif isinstance(event, CallbackQuery):
                await event.message.edit_text(text, reply_markup=kb)
            return
        return await handler(event, data)
