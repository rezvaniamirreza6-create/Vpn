from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from database.db import Category, Plan
from typing import List


# ─── Main Menu ───────────────────────────────────────────────────────────────

def main_menu_kb(settings: dict = None) -> ReplyKeyboardMarkup:
    s = settings or {}
    btn = lambda k, d: s.get(k, d)
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text=btn("btn_buy", "🛒 خرید اشتراک")))
    builder.row(
        KeyboardButton(text=btn("btn_test", "🎁 تست رایگان")),
        KeyboardButton(text=btn("btn_wallet", "💰 کیف پول")),
    )
    builder.row(
        KeyboardButton(text=btn("btn_services", "📦 سرویس‌های من")),
        KeyboardButton(text=btn("btn_referral", "👥 شارژ رایگان")),
    )
    builder.row(
        KeyboardButton(text=btn("btn_lottery", "🏆 مسابقه")),
        KeyboardButton(text=btn("btn_support", "📞 پشتیبانی")),
    )
    builder.row(KeyboardButton(text=btn("btn_guide", "📖 آموزش اتصال")))
    return builder.as_markup(resize_keyboard=True)


def admin_menu_kb() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(
        KeyboardButton(text="📊 آمار ربات"),
        KeyboardButton(text="📢 پیام همگانی"),
    )
    builder.row(
        KeyboardButton(text="📦 مدیریت پلن‌ها"),
        KeyboardButton(text="🗂 دسته‌بندی‌ها"),
    )
    builder.row(
        KeyboardButton(text="💳 تایید پرداخت‌ها"),
        KeyboardButton(text="🏆 قرعه‌کشی"),
    )
    builder.row(
        KeyboardButton(text="👥 مدیریت ادمین‌ها"),
        KeyboardButton(text="🚫 بن کاربر"),
    )
    builder.row(
        KeyboardButton(text="⚙️ تنظیمات"),
        KeyboardButton(text="💾 بکاپ"),
    )
    builder.row(KeyboardButton(text="🔙 منوی اصلی"))
    return builder.as_markup(resize_keyboard=True)


# ─── Categories ──────────────────────────────────────────────────────────────

def categories_kb(categories: List[Category]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for cat in categories:
        builder.row(InlineKeyboardButton(
            text=f"{cat.icon} {cat.name}",
            callback_data=f"cat:{cat.id}"
        ))
    return builder.as_markup()


def plans_kb(plans: List[Plan], back_cat_id: int = None) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for plan in plans:
        builder.row(InlineKeyboardButton(
            text=f"📦 {plan.name} | {plan.traffic_gb}GB | {plan.days}روز | {int(plan.price):,}T",
            callback_data=f"plan:{plan.id}"
        ))
    if back_cat_id:
        builder.row(InlineKeyboardButton(text="🔙 برگشت", callback_data="buy_back"))
    return builder.as_markup()


def confirm_plan_kb(plan_id: int, final_price: float, discount_code: str = "") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(
        text=f"✅ پرداخت از کیف پول ({int(final_price):,} تومان)",
        callback_data=f"confirm_buy:{plan_id}:{discount_code}"
    ))
    builder.row(InlineKeyboardButton(
        text="🏷 کد تخفیف دارم",
        callback_data=f"add_discount:{plan_id}"
    ))
    builder.row(InlineKeyboardButton(text="❌ انصراف", callback_data="cancel"))
    return builder.as_markup()


# ─── Wallet ──────────────────────────────────────────────────────────────────

def wallet_kb(has_zarinpal: bool = False, has_card: bool = True) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if has_card:
        builder.row(InlineKeyboardButton(text="💳 کارت به کارت", callback_data="charge:card"))
    if has_zarinpal:
        builder.row(InlineKeyboardButton(text="🏦 زرین‌پال", callback_data="charge:zarinpal"))
    return builder.as_markup()


def charge_amounts_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    amounts = [50000, 100000, 200000, 500000]
    for a in amounts:
        builder.button(text=f"{a:,} تومان", callback_data=f"charge_amount:{a}")
    builder.adjust(2)
    builder.row(InlineKeyboardButton(text="✏️ مبلغ دلخواه", callback_data="charge_amount:custom"))
    return builder.as_markup()


# ─── Service detail ──────────────────────────────────────────────────────────

def service_detail_kb(svc_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔗 لینک سابسکریپشن", callback_data=f"sub_link:{svc_id}"))
    builder.row(InlineKeyboardButton(text="📋 کپی کانفیگ VLESS", callback_data=f"vless_link:{svc_id}"))
    builder.row(InlineKeyboardButton(text="📷 QR Code", callback_data=f"qr_code:{svc_id}"))
    builder.row(InlineKeyboardButton(text="✏️ تغییر نام سرویس", callback_data=f"rename_svc:{svc_id}"))
    builder.row(InlineKeyboardButton(text="🔄 بروزرسانی", callback_data=f"refresh_svc:{svc_id}"))
    builder.row(InlineKeyboardButton(text="🔙 برگشت", callback_data="my_services"))
    return builder.as_markup()


def renew_kb(svc_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🔄 تمدید سرویس", callback_data=f"renew:{svc_id}"))
    return builder.as_markup()


# ─── Admin payment confirm ────────────────────────────────────────────────────

def payment_confirm_kb(pay_id: int, user_tid: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ تأیید", callback_data=f"pay_ok:{pay_id}:{user_tid}"),
        InlineKeyboardButton(text="❌ رد", callback_data=f"pay_rej:{pay_id}:{user_tid}"),
    )
    return builder.as_markup()


# ─── Admin plans ─────────────────────────────────────────────────────────────

def admin_plans_kb(plans: List[Plan]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for plan in plans:
        status = "✅" if plan.is_active else "❌"
        builder.row(InlineKeyboardButton(
            text=f"{status} {plan.name} - {int(plan.price):,}T",
            callback_data=f"aplan:{plan.id}"
        ))
    builder.row(InlineKeyboardButton(text="➕ پلن جدید", callback_data="add_plan"))
    return builder.as_markup()


def admin_plan_detail_kb(plan_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✏️ ویرایش", callback_data=f"edit_plan:{plan_id}"))
    builder.row(InlineKeyboardButton(text="🗂 دسته‌بندی", callback_data=f"sort_plan:{plan_id}"))
    builder.row(InlineKeyboardButton(text="🗑 حذف", callback_data=f"del_plan:{plan_id}"))
    builder.row(InlineKeyboardButton(text="🔙 برگشت", callback_data="admin_plans"))
    return builder.as_markup()


# ─── Admin categories ────────────────────────────────────────────────────────

def admin_cats_kb(cats: List[Category]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for cat in cats:
        status = "✅" if cat.is_active else "❌"
        builder.row(InlineKeyboardButton(
            text=f"{status} {cat.icon} {cat.name}",
            callback_data=f"acat:{cat.id}"
        ))
    builder.row(InlineKeyboardButton(text="➕ دسته‌بندی جدید", callback_data="add_cat"))
    return builder.as_markup()


def admin_cat_detail_kb(cat_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✏️ ویرایش نام", callback_data=f"edit_cat:{cat_id}"))
    builder.row(InlineKeyboardButton(text="🔢 تغییر ترتیب", callback_data=f"sort_cat:{cat_id}"))
    builder.row(InlineKeyboardButton(text="🗑 حذف", callback_data=f"del_cat:{cat_id}"))
    builder.row(InlineKeyboardButton(text="🔙 برگشت", callback_data="admin_cats"))
    return builder.as_markup()


# ─── Admin settings ──────────────────────────────────────────────────────────

def admin_settings_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    items = [
        ("💳 کارت بانکی", "set_card"),
        ("🤖 نام ربات", "set_botname"),
        ("📞 پشتیبانی", "set_support"),
        ("🎁 تست رایگان", "set_test"),
        ("💰 پاداش دعوت", "set_referral"),
        ("🏦 زرین‌پال", "set_zarinpal"),
        ("🔗 پنل VPN", "set_panel"),
        ("📢 جوین اجباری", "set_forcejoin"),
        ("⚡️ ارسال خودکار کانفیگ", "toggle_auto_config"),
        ("🏆 قرعه‌کشی خودکار", "toggle_lottery_auto"),
        ("✏️ ویرایش متون", "edit_texts"),
        ("🔢 شناسه Inbound", "set_inbound"),
    ]
    for text, cb in items:
        builder.row(InlineKeyboardButton(text=text, callback_data=cb))
    return builder.as_markup()


# ─── Admin lottery ───────────────────────────────────────────────────────────

def lottery_admin_kb(is_active: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    toggle = "🔴 غیرفعال کردن" if is_active else "🟢 فعال کردن"
    builder.row(InlineKeyboardButton(text=toggle, callback_data="toggle_lottery"))
    builder.row(InlineKeyboardButton(text="🎲 انجام قرعه‌کشی", callback_data="do_lottery"))
    builder.row(InlineKeyboardButton(text="📊 آمار شرکت‌کنندگان", callback_data="lottery_stats"))
    return builder.as_markup()


# ─── Admin admins ────────────────────────────────────────────────────────────

def admin_admins_kb(admins) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for a in admins:
        builder.row(InlineKeyboardButton(
            text=f"👤 {a.full_name} ({a.telegram_id})",
            callback_data=f"admin_detail:{a.telegram_id}"
        ))
    builder.row(InlineKeyboardButton(text="➕ ادمین جدید", callback_data="add_admin"))
    return builder.as_markup()


# ─── Back ────────────────────────────────────────────────────────────────────

def back_kb(cb: str = "cancel") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 برگشت / انصراف", callback_data=cb)]
    ])


def force_join_kb(channels: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for ch in channels:
        link = ch.invite_link or f"https://t.me/{ch.channel_id.lstrip('@')}"
        builder.row(InlineKeyboardButton(
            text=f"📢 {ch.channel_name or ch.channel_id}",
            url=link
        ))
    builder.row(InlineKeyboardButton(text="✅ عضو شدم، بررسی کن", callback_data="check_join"))
    return builder.as_markup()
