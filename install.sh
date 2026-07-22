#!/bin/bash
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}╔══════════════════════════════════╗"
echo "║     ربات فروش VPN - نصب         ║"
echo -e "╚══════════════════════════════════╝${NC}"

if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}با root اجرا کنید: sudo bash install.sh${NC}"
    exit 1
fi

INSTALL_DIR="$(pwd)"

echo -e "${YELLOW}نصب وابستگی‌ها...${NC}"
apt-get update -qq
apt-get install -y python3 python3-pip python3-venv -qq

echo -e "${YELLOW}ساخت محیط Python...${NC}"
python3 -m venv venv
source venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt

echo ""
echo -e "${YELLOW}══════ تنظیمات ربات ══════${NC}"
read -p "توکن ربات (از @BotFather): " BOT_TOKEN
read -p "آیدی عددی ادمین: " ADMIN_IDS
echo ""
echo -e "${YELLOW}══════ اطلاعات پنل 3x-ui ══════${NC}"
read -p "آدرس پنل (مثال: http://1.2.3.4:8080): " PANEL_URL
read -p "مسیر پنل: " PANEL_PATH
read -p "یوزرنیم پنل: " PANEL_USERNAME
read -p "پسورد پنل: " PANEL_PASSWORD
read -p "شماره Inbound [1]: " INBOUND_ID
INBOUND_ID=${INBOUND_ID:-1}
echo ""
read -p "شماره کارت: " CARD_NUMBER
read -p "نام صاحب کارت: " CARD_HOLDER
echo ""
read -p "نام ربات [فروشگاه VPN]: " BOT_NAME
BOT_NAME=${BOT_NAME:-"فروشگاه VPN"}
read -p "یوزرنیم پشتیبانی (بدون @): " SUPPORT_USERNAME

cat > .env << EOF
BOT_TOKEN=$BOT_TOKEN
ADMIN_IDS=$ADMIN_IDS
DATABASE_URL=sqlite:///vpnbot.db
EOF

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

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable vpnbot

echo -e "${YELLOW}تنظیم پنل و کارت...${NC}"
source venv/bin/activate

python3 << PYEOF
import asyncio, os
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
echo -e "${GREEN}✅ نصب کامل شد!${NC}"
systemctl status vpnbot --no-pager | head -5
echo ""
echo -e "لاگ: ${YELLOW}journalctl -u vpnbot -f${NC}"
