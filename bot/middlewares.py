from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from cachetools import TTLCache
from typing import Any, Callable, Dict
import time

throttle_cache = TTLCache(maxsize=10000, ttl=1)


class ThrottlingMiddleware(BaseMiddleware):
    async def __call__(self, handler: Callable, event: Any, data: Dict) -> Any:
        user = getattr(event, "from_user", None)
        if user:
            key = f"throttle:{user.id}"
            if key in throttle_cache:
                return
            throttle_cache[key] = 1
        return await handler(event, data)
