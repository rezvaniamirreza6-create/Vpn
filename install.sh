#!/bin/bash
set -e

# رنگ‌بندی برای خروجی
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
print_green() { echo -e "${GREEN}$1${NC}"; }
print_yellow() { echo -e "${YELLOW}$1${NC}"; }

print_green "=========================================="
print_green "   راه‌اندازی خودکار ربات VPN (Fast ping)   "
print_green "=========================================="

# 1. بررسی اینکه آیا در مسیر درست هستیم (پوشه bot باید وجود داشته باشد)
if [ ! -d "bot" ]; then
    print_yellow "⚠️  پوشه bot پیدا نشد! لطفاً اسکریپت را از ریشه پروژه اجرا کنید."
    exit 1
fi

# 2. ساخت فایل .env با اطلاعات شما (در صورت نبود یا بازنویسی)
print_green "➡️  ایجاد فایل .env با اطلاعات وارد شده..."
cat > .env <<'EOF'
BOT_TOKEN=8718652017:AAGQqeHKSnX3UqXlxHaOz-VL0PqjS4JOjUY
ADMIN_IDS=5993860770
PANEL_URL=http://188.121.107.171:2053
PANEL_PATH=wBuEUNmiC9w6heLM1W
PANEL_USERNAME=amir
PANEL_PASSWORD=amir
INBOUND_IDS=3
CARD_NUMBER=6277601368776066
CARD_HOLDER=علی رضوانی
BOT_NAME=Fast ping
SUPPORT_USERNAME=suportssh
FREE_TEST_TRAFFIC_GB=0.2
FREE_TEST_DAYS=1
REFERRAL_REWARD=50000
DATABASE_URL=sqlite:///vpnbot.db
EOF
print_green "✅ فایل .env ساخته شد."

# 3. ساخت requirements.txt استاندارد (برای دستور pip install شما)
print_green "➡️  ایجاد فایل requirements.txt به‌روز..."
cat > requirements.txt <<'EOF'
aiogram==3.4.1
python-dotenv==1.0.1
sqlalchemy==2.0.30
aiohttp==3.9.5
aiosqlite==0.20.0
EOF
print_green "✅ requirements.txt ساخته شد."

# 4. بازنویسی فایل bot/config.py (هماهنگ با متغیرهای جدید)
print_green "➡️  به‌روزرسانی فایل bot/config.py ..."
cat > bot/config.py <<'EOF'
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # تلگرام
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(",")))
    BOT_NAME = os.getenv("BOT_NAME", "VPN Bot")
    SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME")

    # پنل 3X-UI (با ساختار جدید)
    PANEL_URL = os.getenv("PANEL_URL")
    PANEL_PATH = os.getenv("PANEL_PATH")
    PANEL_USERNAME = os.getenv("PANEL_USERNAME")
    PANEL_PASSWORD = os.getenv("PANEL_PASSWORD")
    INBOUND_IDS = list(map(int, os.getenv("INBOUND_IDS", "3").split(",")))

    # پرداخت
    CARD_NUMBER = os.getenv("CARD_NUMBER")
    CARD_HOLDER = os.getenv("CARD_HOLDER")

    # تنظیمات تست و دعوت
    FREE_TEST_TRAFFIC_GB = float(os.getenv("FREE_TEST_TRAFFIC_GB", 0.2))
    FREE_TEST_DAYS = int(os.getenv("FREE_TEST_DAYS", 1))
    REFERRAL_REWARD = int(os.getenv("REFERRAL_REWARD", 50000))

    # دیتابیس (SQLite)
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///vpnbot.db")
EOF
print_green "✅ config.py به‌روزرسانی شد."

# 5. بازنویسی فایل panels/xui.py (استفاده از PATH جدید)
print_green "➡️  به‌روزرسانی فایل panels/xui.py ..."
cat > panels/xui.py <<'EOF'
import aiohttp
from bot.config import Config

async def get_xui_cookie():
    async with aiohttp.ClientSession() as session:
        payload = {
            "username": Config.PANEL_USERNAME,
            "password": Config.PANEL_PASSWORD
        }
        # ساخت آدرس کامل با در نظر گرفتن مسیر (PATH)
        login_url = f"{Config.PANEL_URL}/{Config.PANEL_PATH}/login"
        async with session.post(login_url, json=payload) as resp:
            return resp.cookies

async def create_service(user_id: int, months: int, inbound_id: int = 3):
    # منطق واقعی ساخت سرویس با API پنل (در حال حاضر Mock)
    # در آینده می‌توانید با استفاده از کوکی، اینباند مورد نظر را بسازید
    return f"vless://generated-{user_id}@{Config.PANEL_URL}/?path=/{Config.PANEL_PATH}"
EOF
print_green "✅ xui.py به‌روزرسانی شد."

# 6. نصب وابستگی‌های پایتون (اختیاری ولی ایمن)
print_green "➡️  نصب کتابخانه‌های پایتون (در صورت نیاز)..."
if [ -f "venv/bin/pip" ]; then
    venv/bin/pip install --upgrade pip
    venv/bin/pip install -r requirements.txt
else
    print_yellow "⚠️  محیط مجازی (venv) پیدا نشد! لطفاً ابتدا آن را بسازید."
fi

# 7. راه‌اندازی سرویس systemd برای اجرای دائمی
print_green "➡️  ثبت ربات به عنوان سرویس سیستمی..."
SERVICE_PATH="/etc/systemd/system/vpn-bot.service"
CURRENT_USER=$(whoami)
CURRENT_PATH=$(pwd)

sudo bash -c "cat > $SERVICE_PATH" <<EOF
[Unit]
Description=VPN Telegram Bot Service (Fast ping)
After=network.target
Wants=network.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$CURRENT_PATH
ExecStart=$CURRENT_PATH/venv/bin/python $CURRENT_PATH/bot/main.py
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable vpn-bot.service

print_green "=============================================="
print_green "✅ نصب با موفقیت به پایان رسید!"
print_green "=============================================="
print_yellow "🔸 برای اجرای دستی (تست اولیه):"
print_yellow "   cd $CURRENT_PATH && source venv/bin/activate && python bot/main.py"
print_yellow ""
print_yellow "🔸 برای اجرا در پس‌زمینه (سرویس):"
print_yellow "   sudo systemctl start vpn-bot.service"
print_yellow ""
print_yellow "🔸 برای دیدن لاگ‌های لحظه‌ای:"
print_yellow "   sudo journalctl -u vpn-bot.service -f"
print_yellow ""
print_yellow "🔸 برای مشاهده وضعیت سرویس:"
print_yellow "   sudo systemctl status vpn-bot.service"
print_green "=============================================="
