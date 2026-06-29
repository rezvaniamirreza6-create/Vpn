#!/bin/bash
# ربات فروش VPN - اسکریپت نصب خودکار
# استفاده: bash install.sh

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}"
echo "╔══════════════════════════════════╗"
echo "║     ربات فروش VPN - نصب         ║"
echo "╚══════════════════════════════════╝"
echo -e "${NC}"

# بررسی root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}لطفاً با root اجرا کنید: sudo bash install.sh${NC}"
    exit 1
fi

INSTALL_DIR="/opt/vpnbot"

# نصب وابستگی‌ها
echo -e "${YELLOW}نصب وابستگی‌ها...${NC}"
apt-get update -qq
apt-get install -y python3 python3-pip python3-venv git curl -qq

# ساخت پوشه
mkdir -p $INSTALL_DIR
cd $INSTALL_DIR

# کپی فایل‌ها (اگر از گیت‌هاب)
if [ ! -f "$INSTALL_DIR/bot/main.py" ]; then
    echo -e "${YELLOW}دانلود فایل‌ها از گیت‌هاب...${NC}"
    REPO_URL=""
    if [ -z "$REPO_URL" ]; then
        echo -e "${RED}لطفاً ابتدا فایل‌ها را در پوشه $INSTALL_DIR قرار دهید${NC}"
        echo -e "یا REPO_URL را در اسکریپت تنظیم کنید"
        exit 1
    fi
    git clone $REPO_URL $INSTALL_DIR
fi

# ساخت virtual environment
echo -e "${YELLOW}ساخت محیط Python...${NC}"
python3 -m venv $INSTALL_DIR/venv
source $INSTALL_DIR/venv/bin/activate
pip install -q --upgrade pip
pip install -q -r $INSTALL_DIR/requirements.txt

# دریافت اطلاعات
echo ""
echo -e "${YELLOW}══════ تنظیمات ربات ══════${NC}"
read -p "توکن ربات (از @BotFather): " BOT_TOKEN
read -p "آیدی عددی ادمین: " ADMIN_IDS
echo ""
echo -e "${YELLOW}══════ اطلاعات پنل 3x-ui ══════${NC}"
read -p "آدرس پنل (مثال: https://1.2.3.4:8080): " PANEL_URL
read -p "مسیر پنل (مثال: rGkKcl3fSw6oI9D): " PANEL_PATH
read -p "یوزرنیم پنل: " PANEL_USERNAME
read -p "پسورد پنل: " PANEL_PASSWORD
read -p "شماره Inbound [1]: " INBOUND_ID
INBOUND_ID=${INBOUND_ID:-1}
echo ""
echo -e "${YELLOW}══════ اطلاعات کارت ══════${NC}"
read -p "شماره کارت: " CARD_NUMBER
read -p "نام صاحب کارت: " CARD_HOLDER
echo ""
echo -e "${YELLOW}══════ تنظیمات دیگر ══════${NC}"
read -p "نام ربات [فروشگاه VPN]: " BOT_NAME
BOT_NAME=${BOT_NAME:-"فروشگاه VPN"}
read -p "یوزرنیم پشتیبانی (بدون @): " SUPPORT_USERNAME

# ساخت .env
cat > $INSTALL_DIR/.env << EOF
BOT_TOKEN=$BOT_TOKEN
ADMIN_IDS=$ADMIN_IDS
DATABASE_URL=sqlite:///vpnbot.db
EOF

# ساخت سرویس systemd
cat > /etc/systemd/system/vpnbot.service << EOF
[Unit]
Description=VPN Telegram Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$INSTALL_DIR/.env
ExecStart=$INSTALL_DIR/venv/bin/python3 -m bot.main
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable vpnbot
systemctl start vpnbot

# تنظیم پنل و کارت در دیتابیس
echo -e "${YELLOW}تنظیم اطلاعات پنل...${NC}"
source $INSTALL_DIR/venv/bin/activate
cd $INSTALL_DIR

python3 << PYEOF
import asyncio
import os
os.environ['BOT_TOKEN'] = '$BOT_TOKEN'
os.environ['ADMIN_IDS'] = '$ADMIN_IDS'
os.environ['DATABASE_URL'] = 'sqlite:///vpnbot.db'

async def setup():
    from database.db import init_db, AsyncSessionLocal
    from database.crud import set_setting
    await init_db()
    async with AsyncSessionLocal() as db:
        await set_setting(db, 'panel_url', '$PANEL_URL')
        await set_setting(db, 'panel_path', '$PANEL_PATH')
        await set_setting(db, 'panel_username', '$PANEL_USERNAME')
        await set_setting(db, 'panel_password', '$PANEL_PASSWORD')
        await set_setting(db, 'inbound_id', '$INBOUND_ID')
        await set_setting(db, 'card_number', '$CARD_NUMBER')
        await set_setting(db, 'card_holder', '$CARD_HOLDER')
        await set_setting(db, 'bot_name', '$BOT_NAME')
        await set_setting(db, 'support_username', '$SUPPORT_USERNAME')
        print('Settings saved!')

asyncio.run(setup())
PYEOF

systemctl restart vpnbot
sleep 2

echo ""
echo -e "${GREEN}══════════════════════════════════${NC}"
echo -e "${GREEN}✅ نصب کامل شد!${NC}"
echo ""
echo -e "وضعیت ربات:"
systemctl status vpnbot --no-pager | head -5
echo ""
echo -e "دستورات مفید:"
echo -e "  مشاهده لاگ:  ${YELLOW}journalctl -u vpnbot -f${NC}"
echo -e "  راه‌اندازی:   ${YELLOW}systemctl start vpnbot${NC}"
echo -e "  توقف:         ${YELLOW}systemctl stop vpnbot${NC}"
echo -e "  ریستارت:      ${YELLOW}systemctl restart vpnbot${NC}"
echo -e "${GREEN}══════════════════════════════════${NC}"
