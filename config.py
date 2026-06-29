import os
from dataclasses import dataclass, field
from typing import List


@dataclass
class Config:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    ADMIN_IDS: List[int] = field(default_factory=lambda: [
        int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()
    ])
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///vpnbot.db")
    WEBHOOK_URL: str = os.getenv("WEBHOOK_URL", "")
    PORT: int = int(os.getenv("PORT", "8000"))


config = Config()
