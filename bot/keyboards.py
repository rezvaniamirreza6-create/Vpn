from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from typing import List
from database.db import Plan, DiscountCode


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛒 خرید سرویس"), KeyboardButton(text="🎁 سرویس تست رایگان")],
            [KeyboardButton(text="📦 سرویس‌های من"), KeyboardButton(text="💰 کیف پول")],
            [KeyboardButton(text="🎰 قرعه‌کشی"), KeyboardButton(text="🎊 شارژ رایگان")],
            [KeyboardButton(text="📞 پشتیبانی"), KeyboardButton(text="📖 راهنما")],
        ],
        resize_keyboard=True
    )


def admin_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 آمار ربات"), KeyboardButton(text="📢 پیام همگانی")],
            [KeyboardButton(text="📦 مدیریت پلن‌ها"), KeyboardButton(text="🏷 کدهای تخفیف")],
            [KeyboardButton(text="💳 تایید پرداخت‌ها"), KeyboardButton(text="🎰 قرعه‌کشی ادمین")],
            [KeyboardButton(text="⚙️ تنظیمات ربات"), KeyboardButton(text="🔙 منوی اصلی")],
        ],
        resize_keyboard=True
    )


def plans_keyboard(plans: List[Plan]) -> InlineKeyboardMarkup:
    buttons = []
    for p in plans:
        label = f"📦 {p.name} | {p.traffic_gb}GB | {p.days}روز | {int(p.price):,}تومان"
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"buy_plan:{p.id}")])
    buttons.append([InlineKeyboardButton(text="❌ انصراف", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def confirm_purchase_keyboard(plan_id: int, final_price: float, discount_code: str = "") -> InlineKeyboardMarkup:
    extra = f":{discount_code}" if discount_code else ":"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"✅ پرداخت {int(final_price):,} تومان از کیف پول",
            callback_data=f"confirm_buy:{plan_id}{extra}"
        )],
        [InlineKeyboardButton(text="🏷 کد تخفیف دارم", callback_data=f"add_discount:{plan_id}")],
        [InlineKeyboardButton(text="❌ انصراف", callback_data="cancel")],
    ])


def wallet_keyboard(has_zarinpal: bool, has_card: bool) -> InlineKeyboardMarkup:
    buttons = []
    if has_zarinpal:
        buttons.append([InlineKeyboardButton(text="💳 پرداخت آنلاین (زرین‌پال)", callback_data="charge:zarinpal")])
    if has_card:
        buttons.append([InlineKeyboardButton(text="🏦 کارت به کارت", callback_data="charge:card")])
    buttons.append([InlineKeyboardButton(text="❌ انصراف", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def charge_amounts_keyboard() -> InlineKeyboardMarkup:
    amounts = [50000, 100000, 200000, 500000]
    rows = []
    for i in range(0, len(amounts), 2):
        rows.append([
            InlineKeyboardButton(text=f"{amounts[i]:,}تومان", callback_data=f"charge_amount:{amounts[i]}"),
            InlineKeyboardButton(text=f"{amounts[i+1]:,}تومان", callback_data=f"charge_amount:{amounts[i+1]}"),
        ])
    rows.append([InlineKeyboardButton(text="💰 مبلغ دلخواه", callback_data="charge_amount:custom")])
    rows.append([InlineKeyboardButton(text="❌ انصراف", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def service_detail_keyboard(svc_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 لینک سابسکریپشن", callback_data=f"sub_link:{svc_id}")],
        [InlineKeyboardButton(text="🔄 بروزرسانی مصرف", callback_data=f"refresh_svc:{svc_id}")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="my_services")],
    ])


def payment_confirm_keyboard(pay_id: int, user_tid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ تایید", callback_data=f"approve_pay:{pay_id}:{user_tid}"),
        InlineKeyboardButton(text="❌ رد", callback_data=f"reject_pay:{pay_id}:{user_tid}"),
    ]])


def admin_plans_list_keyboard(plans: List[Plan]) -> InlineKeyboardMarkup:
    buttons = []
    for p in plans:
        buttons.append([InlineKeyboardButton(
            text=f"🗑 {p.name} ({int(p.price):,}تومان) — حذف",
            callback_data=f"del_plan:{p.id}"
        )])
    buttons.append([InlineKeyboardButton(text="➕ پلن جدید", callback_data="add_plan")])
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin_back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def discounts_list_keyboard(codes: List[DiscountCode]) -> InlineKeyboardMarkup:
    buttons = []
    for dc in codes:
        status = "✅" if dc.is_active else "❌"
        buttons.append([InlineKeyboardButton(
            text=f"{status} {dc.code} | {dc.percent}% | {dc.used_count}/{dc.max_uses}",
            callback_data=f"del_dc:{dc.id}"
        )])
    buttons.append([InlineKeyboardButton(text="➕ کد جدید", callback_data="add_dc")])
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin_back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def lottery_draw_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🎯 ۱ برنده", callback_data="draw:1"),
            InlineKeyboardButton(text="🎯 ۳ برنده", callback_data="draw:3"),
            InlineKeyboardButton(text="🎯 ۵ برنده", callback_data="draw:5"),
        ],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="admin_back")],
    ])


def back_keyboard(cb: str = "cancel") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data=cb)]
    ])
