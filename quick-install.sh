#!/bin/bash
set -e
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

REPO_URL="https://github.com/rezvaniamirreza6-create/Vpn.git"
INSTALL_DIR="/opt/vpnbot"

echo -e "${GREEN}╔══════════════════════════════════╗"
echo "║   Dragon VPN Bot - نصب یک‌مرحله‌ای   ║"
echo -e "╚══════════════════════════════════╝${NC}"

if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}با root اجرا کنید: sudo bash -c \"\$(curl -fsSL <URL>)\"${NC}"
    exit 1
fi

echo -e "${YELLOW}نصب git (در صورت نیاز)...${NC}"
apt-get update -qq
apt-get install -y git -qq

if [ -d "$INSTALL_DIR" ]; then
    echo -e "${YELLOW}پوشه‌ی $INSTALL_DIR از قبل وجود دارد.${NC}"
    read -p "پاک شود و از نو نصب شود؟ (y/N): " CONFIRM
    if [[ "$CONFIRM" == "y" || "$CONFIRM" == "Y" ]]; then
        rm -rf "$INSTALL_DIR"
    else
        echo -e "${RED}نصب لغو شد.${NC}"
        exit 1
    fi
fi

echo -e "${YELLOW}دریافت پروژه از گیت‌هاب...${NC}"
git clone "$REPO_URL" "$INSTALL_DIR"
cd "$INSTALL_DIR"

if [ ! -f install.sh ]; then
    echo -e "${RED}فایل install.sh تو ریپازیتوری پیدا نشد!${NC}"
    exit 1
fi

chmod +x install.sh
echo -e "${GREEN}شروع نصب و تنظیمات...${NC}"
bash install.sh
