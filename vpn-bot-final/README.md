# 🤖 ربات فروش VPN

ربات تلگرام فروش VPN با اتصال به پنل 3x-ui (Sanaei)

## امکانات
- 🛒 خرید سرویس با پلن‌های مختلف
- 💰 کیف پول + شارژ کارت به کارت / زرین‌پال
- 🎁 سرویس تست رایگان
- 🎊 سیستم رفرال
- 🎰 قرعه‌کشی
- 🏷 کدهای تخفیف
- 📢 پیام همگانی
- 📦 مدیریت پلن‌ها

---

## 🚀 دیپلوی روی Railway

### ۱. ساخت پروژه در Railway
1. به [railway.app](https://railway.app) بروید
2. **New Project → Deploy from GitHub repo** را انتخاب کنید
3. این ریپو را انتخاب کنید

### ۲. افزودن PostgreSQL
1. در پروژه Railway روی **+ New** کلیک کنید
2. **Database → PostgreSQL** را انتخاب کنید
3. Railway به صورت خودکار `DATABASE_URL` را ست می‌کند

### ۳. تنظیم Environment Variables
در تب **Variables** سرویس ربات:

| متغیر | توضیح | مثال |
|-------|-------|------|
| `BOT_TOKEN` | توکن ربات از @BotFather | `123456:AAxx...` |
| `ADMIN_IDS` | آیدی عددی ادمین‌ها (با کاما) | `123456789` |
| `PANEL_URL` | آدرس پنل 3x-ui | `http://1.2.3.4:2053` |
| `PANEL_USERNAME` | یوزرنیم پنل | `admin` |
| `PANEL_PASSWORD` | پسورد پنل | `yourpassword` |
| `PANEL_PATH` | مسیر پنل (اگر دارد) | خالی یا `/panel` |
| `INBOUND_IDS` | آیدی inbound (با کاما) | `1` |
| `CARD_NUMBER` | شماره کارت | `6037-9912-xxxx-xxxx` |
| `CARD_HOLDER` | نام صاحب کارت | `علی احمدی` |
| `BOT_NAME` | نام ربات | `فروشگاه VPN` |
| `SUPPORT_USERNAME` | یوزرنیم پشتیبانی | `support_user` |
| `FREE_TEST_TRAFFIC_GB` | حجم تست رایگان | `1` |
| `FREE_TEST_DAYS` | مدت تست رایگان | `1` |
| `REFERRAL_REWARD` | پاداش دعوت (تومان) | `50000` |
| `FORCE_JOIN_CHANNELS` | کانال‌های اجباری | `@mychannel` |

> ⚠️ `DATABASE_URL` را خودتان ست نکنید - Railway آن را خودکار از PostgreSQL می‌گیرد.

---

## 🔧 اجرای محلی (توسعه)

```bash
# نصب
pip install -r requirements.txt

# تنظیم env
cp .env.example .env
# فایل .env را ویرایش کنید

# اجرا
python -m bot.main
```

## 📁 ساختار پروژه

```
├── bot/
│   ├── main.py           # نقطه ورود
│   ├── middlewares.py    # throttling + forced join
│   ├── keyboards.py      # کیبوردها
│   └── handlers/
│       ├── user.py       # دستورات کاربر
│       ├── admin.py      # پنل ادمین
│       └── payment.py    # پرداخت
├── database/
│   ├── db.py             # مدل‌های SQLAlchemy
│   └── crud.py           # توابع دیتابیس
├── panels/
│   └── sanei.py          # API پنل 3x-ui
├── payments/
│   └── zarinpal.py       # درگاه زرین‌پال
├── config.py             # تنظیمات از env
├── requirements.txt
├── Procfile
└── railway.json
```
