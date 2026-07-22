import os
from dotenv import load_dotenv
load_dotenv()

class Config:
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///vpnbot.db")
    PANEL_URL: str = os.getenv("PANEL_URL", "")
    CONFIG_HOST: str = os.getenv("CONFIG_HOST", "")
    PANEL_PATH: str = os.getenv("PANEL_PATH", "")
    PANEL_USERNAME: str = os.getenv("PANEL_USERNAME", "")
    PANEL_PASSWORD: str = os.getenv("PANEL_PASSWORD", "")
    SUB_PORT: str = os.getenv("SUB_PORT", "")
    SUB_PATH: str = os.getenv("SUB_PATH", "sub")
    INBOUND_IDS = [int(x) for x in os.getenv("INBOUND_IDS", "1").split(",") if x.strip()]
    CARD_NUMBER: str = os.getenv("CARD_NUMBER", "")
    CARD_HOLDER: str = os.getenv("CARD_HOLDER", "")
    BOT_NAME: str = os.getenv("BOT_NAME", "فروشگاه VPN")
    SUPPORT_USERNAME: str = os.getenv("SUPPORT_USERNAME", "")
    FREE_TEST_TRAFFIC_GB: int = int(os.getenv("FREE_TEST_TRAFFIC_GB", "1"))
    FREE_TEST_DAYS: int = int(os.getenv("FREE_TEST_DAYS", "1"))
    REFERRAL_REWARD: int = int(os.getenv("REFERRAL_REWARD", "50000"))
    ZARINPAL_MERCHANT: str = os.getenv("ZARINPAL_MERCHANT", "")
    FORCE_JOIN_CHANNELS: str = os.getenv("FORCE_JOIN_CHANNELS", "")
    WEBHOOK_URL: str = os.getenv("WEBHOOK_URL", "")

config = Config()
