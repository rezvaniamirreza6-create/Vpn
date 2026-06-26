import os
from dataclasses import dataclass, field
from typing import List


@dataclass
class Config:
    # Telegram
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    ADMIN_IDS: List[int] = field(default_factory=lambda: [
        int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()
    ])

    # 3X-UI Panel (بدون SSL)
    PANEL_URL: str = os.getenv("PANEL_URL", "")           # e.g. http://1.2.3.4:2053
    PANEL_USERNAME: str = os.getenv("PANEL_USERNAME", "")
    PANEL_PASSWORD: str = os.getenv("PANEL_PASSWORD", "")
    PANEL_PATH: str = os.getenv("PANEL_PATH", "")

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///vpnbot.db")

    # ZarinPal
    ZARINPAL_MERCHANT: str = os.getenv("ZARINPAL_MERCHANT", "")
    ZARINPAL_SANDBOX: bool = os.getenv("ZARINPAL_SANDBOX", "false").lower() == "true"

    # Card to Card
    CARD_NUMBER: str = os.getenv("CARD_NUMBER", "")
    CARD_HOLDER: str = os.getenv("CARD_HOLDER", "")

    # Bot Settings
    FORCE_JOIN_CHANNELS: List[str] = field(default_factory=lambda: [
        x.strip() for x in os.getenv("FORCE_JOIN_CHANNELS", "").split(",") if x.strip()
    ])
    BOT_NAME: str = os.getenv("BOT_NAME", "فروشگاه VPN")
    SUPPORT_USERNAME: str = os.getenv("SUPPORT_USERNAME", "")
    FREE_TEST_TRAFFIC_GB: int = int(os.getenv("FREE_TEST_TRAFFIC_GB", "1"))
    FREE_TEST_DAYS: int = int(os.getenv("FREE_TEST_DAYS", "1"))

    # Inbound IDs از پنل 3X-UI
    INBOUND_IDS: List[int] = field(default_factory=lambda: [
        int(x) for x in os.getenv("INBOUND_IDS", "1").split(",") if x.strip()
    ])

    # Referral
    REFERRAL_REWARD: int = int(os.getenv("REFERRAL_REWARD", "50000"))

    # Railway / Webhook
    WEBHOOK_URL: str = os.getenv("WEBHOOK_URL", "")
    PORT: int = int(os.getenv("PORT", "8000"))


config = Config()
