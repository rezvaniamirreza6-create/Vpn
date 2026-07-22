from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder


def phone_request_kb():
    b = ReplyKeyboardBuilder()
    b.row(KeyboardButton(text="📱 ارسال شماره من", request_contact=True))
    return b.as_markup(resize_keyboard=True)


def main_menu_kb():
    b = ReplyKeyboardBuilder()
    b.row(KeyboardButton(text="🛒 خرید اشتراک"))
    b.row(KeyboardButton(text="🎁 تست رایگان"), KeyboardButton(text="🔄 تمدید سرویس"))
    b.row(KeyboardButton(text="💰 کیف پول"), KeyboardButton(text="📦 سرویس‌های من"))
    b.row(KeyboardButton(text="👥 شارژ رایگان"), KeyboardButton(text="🏆 مسابقه"))
    b.row(KeyboardButton(text="📞 پشتیبانی"), KeyboardButton(text="📖 آموزش اتصال"))
    return b.as_markup(resize_keyboard=True)


# Maps each admin menu button to the permission required to see/use it.
# perm=None means every recognized admin (owner or sub-admin) can see it.
ADMIN_MENU_BUTTONS = [
    ("📊 آمار ربات", "stats"),
    ("📢 پیام همگانی", "broadcast"),
    ("📦 مدیریت پلن‌ها", "plans"),
    ("🗂 دسته‌بندی‌ها", "plans"),
    ("💳 تایید پرداخت‌ها", "payment"),
    ("🏆 قرعه‌کشی", "lottery"),
    ("👥 مدیریت ادمین‌ها", "all"),
    ("🎫 کد تخفیف", "discount"),
    ("📈 برترین معرف‌ها", "stats"),
    ("💎 برترین خریداران", "stats"),
    ("🔍 جستجوی کاربر", "user_manage"),
    ("♻️ ریست تست رایگان", "settings"),
    ("🗑 حذف سرویس‌های منقضی", "plans"),
    ("🔒 بستن سرویس‌های زیرمجموعه‌ای", "plans"),
    ("💾 بکاپ‌گیری", "all"),
    ("♻️ بازیابی بکاپ", "all"),
    ("🔌 خاموش/روشن ربات", "all"),
    ("🚫 بن کاربر", "ban"),
    ("⚙️ تنظیمات", "settings"),
    ("💰 کسر/افزایش موجودی", "wallet"),
    ("📢 کانال‌های اجباری", "settings"),
]


def admin_menu_kb(perms=None):
    """Build the admin reply keyboard.

    perms=None -> full owner menu (config.ADMIN_IDS), show everything.
    perms=<list> -> sub-admin, only show buttons they actually have access to.
    """
    b = ReplyKeyboardBuilder()
    is_owner = perms is None
    allowed = set(perms or [])
    for text, perm in ADMIN_MENU_BUTTONS:
        if is_owner or perm in allowed or "all" in allowed:
            b.row(KeyboardButton(text=text))
    b.row(KeyboardButton(text="🔙 منوی اصلی"))
    return b.as_markup(resize_keyboard=True)


def categories_kb(cats):
    b = InlineKeyboardBuilder()
    for c in cats:
        b.row(InlineKeyboardButton(text=f"{c.icon} {c.name}", callback_data=f"cat:{c.id}"))
    return b.as_markup()


def plans_kb(plans, back=False):
    b = InlineKeyboardBuilder()
    for p in plans:
        t_text = "نامحدود" if p.traffic_gb == 0 else f"{p.traffic_gb}GB"
        b.row(InlineKeyboardButton(text=f"📦 {p.name} | {t_text} | {p.days}روز | {int(p.price):,}T", callback_data=f"plan:{p.id}"))
    if back:
        b.row(InlineKeyboardButton(text="🔙 برگشت", callback_data="buy_back"))
    return b.as_markup()


def confirm_plan_kb(plan_id, discount_code=""):
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="✅ پرداخت از کیف پول", callback_data=f"confirm_buy:{plan_id}:{discount_code}"))
    b.row(InlineKeyboardButton(text="🏷 کد تخفیف دارم", callback_data=f"add_discount:{plan_id}"))
    b.row(InlineKeyboardButton(text="❌ انصراف", callback_data="cancel"))
    return b.as_markup()


def wallet_kb(has_zarinpal=False, has_card=True):
    b = InlineKeyboardBuilder()
    if has_card:
        b.row(InlineKeyboardButton(text="💳 کارت به کارت", callback_data="charge:card"))
    if has_zarinpal:
        b.row(InlineKeyboardButton(text="🏦 زرین‌پال", callback_data="charge:zarinpal"))
    return b.as_markup()


def charge_amounts_kb():
    b = InlineKeyboardBuilder()
    for a in [50000, 100000, 200000, 500000]:
        b.button(text=f"{a:,} تومان", callback_data=f"charge_amount:{a}")
    b.adjust(2)
    b.row(InlineKeyboardButton(text="✏️ مبلغ دلخواه", callback_data="charge_amount:custom"))
    return b.as_markup()


def service_detail_kb(svc_id):
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔗 لینک سابسکریپشن", callback_data=f"sub_link:{svc_id}"))
    b.row(InlineKeyboardButton(text="📷 QR Code", callback_data=f"qr_code:{svc_id}"))
    b.row(InlineKeyboardButton(text="✏️ تغییر نام", callback_data=f"rename_svc:{svc_id}"))
    b.row(InlineKeyboardButton(text="🔄 بروزرسانی", callback_data=f"refresh_svc:{svc_id}"))
    b.row(InlineKeyboardButton(text="🔙 برگشت", callback_data="my_services"))
    return b.as_markup()


def payment_confirm_kb(pay_id, user_tid):
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="✅ تأیید", callback_data=f"pay_ok:{pay_id}:{user_tid}"),
        InlineKeyboardButton(text="❌ رد", callback_data=f"pay_rej:{pay_id}:{user_tid}"),
    )
    return b.as_markup()


def admin_plans_kb(plans):
    b = InlineKeyboardBuilder()
    for p in plans:
        s = "✅" if p.is_active else "❌"
        b.row(InlineKeyboardButton(text=f"{s} {p.name} - {int(p.price):,}T", callback_data=f"aplan:{p.id}"))
    b.row(InlineKeyboardButton(text="➕ پلن جدید", callback_data="add_plan"))
    if plans:
        b.row(InlineKeyboardButton(text="🔲 انتخاب", callback_data="admin_plans_select"))
    return b.as_markup()


def admin_plans_select_kb(plans, selected_ids):
    b = InlineKeyboardBuilder()
    for p in plans:
        mark = "☑️" if p.id in selected_ids else "☐"
        b.row(InlineKeyboardButton(text=f"{mark} {p.name}", callback_data=f"selplan:{p.id}"))
    label = f"➕ افزودن {len(selected_ids)} پلن به دسته‌بندی" if selected_ids else "➕ افزودن به دسته‌بندی"
    b.row(InlineKeyboardButton(text=label, callback_data="bulk_add_cat"))
    b.row(InlineKeyboardButton(text="❌ انصراف", callback_data="cancel_select_mode"))
    return b.as_markup()


def referral_services_select_kb(svcs, selected_ids):
    b = InlineKeyboardBuilder()
    for s in svcs:
        u = s.user
        label = f"@{u.username}" if u and u.username else (u.full_name if u else s.panel_email)
        mark = "☑️" if s.id in selected_ids else "☐"
        b.row(InlineKeyboardButton(text=f"{mark} {label}", callback_data=f"selref:{s.id}"))
    label2 = f"🗑 بستن {len(selected_ids)} سرویس انتخابی" if selected_ids else "🗑 بستن سرویس‌های انتخابی"
    b.row(InlineKeyboardButton(text=label2, callback_data="close_ref_selected"))
    b.row(InlineKeyboardButton(text="❌ انصراف", callback_data="cancel"))
    return b.as_markup()


def admin_plan_detail_kb(plan_id):
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="✏️ ویرایش", callback_data=f"edit_plan:{plan_id}"))
    b.row(InlineKeyboardButton(text="🗑 حذف", callback_data=f"del_plan:{plan_id}"))
    b.row(InlineKeyboardButton(text="🔙 برگشت", callback_data="admin_plans"))
    return b.as_markup()


def plan_cat_select_kb(cats, prefix="pcat"):
    b = InlineKeyboardBuilder()
    for c in cats:
        b.row(InlineKeyboardButton(text=f"{c.icon} {c.name}", callback_data=f"{prefix}:{c.id}"))
    b.row(InlineKeyboardButton(text="🚫 بدون دسته‌بندی", callback_data=f"{prefix}:none"))
    return b.as_markup()


def admin_cats_kb(cats):
    b = InlineKeyboardBuilder()
    for c in cats:
        s = "✅" if c.is_active else "❌"
        b.row(InlineKeyboardButton(text=f"{s} {c.icon} {c.name}", callback_data=f"acat:{c.id}"))
    b.row(InlineKeyboardButton(text="➕ دسته‌بندی جدید", callback_data="add_cat"))
    return b.as_markup()


def admin_cat_detail_kb(cat_id):
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="✏️ ویرایش نام", callback_data=f"edit_cat:{cat_id}"))
    b.row(InlineKeyboardButton(text="🗑 حذف", callback_data=f"del_cat:{cat_id}"))
    b.row(InlineKeyboardButton(text="🔙 برگشت", callback_data="admin_cats"))
    return b.as_markup()


def admin_settings_kb(test_enabled=True, sub_https=True):
    b = InlineKeyboardBuilder()
    items = [
        ("💳 شماره کارت", "set_card"), ("👤 نام صاحب کارت", "set_card_holder"),
        ("🤖 نام ربات", "set_botname"),
        ("📞 پشتیبانی", "set_support"), ("🎁 تنظیم تست رایگان", "set_test"),
        ("💰 پاداش دعوت", "set_referral"), ("🏦 زرین‌پال", "set_zarinpal"),
        ("🔗 پنل VPN", "set_panel"), ("🌐 پورت/مسیر ساب", "set_sub"),
        ("🔢 شناسه Inbound", "set_inbound"),
        ("🧪 شناسه Inbound تست", "set_test_inbound"),
        ("⚡️ ارسال خودکار", "toggle_auto_config"),
    ]
    for t, c in items:
        b.row(InlineKeyboardButton(text=t, callback_data=c))
    test_toggle = "🔴 خاموش کردن تست رایگان" if test_enabled else "🟢 روشن کردن تست رایگان"
    b.row(InlineKeyboardButton(text=test_toggle, callback_data="toggle_free_test"))
    sub_toggle = "🔓 تغییر لینک ساب به http" if sub_https else "🔒 تغییر لینک ساب به https"
    b.row(InlineKeyboardButton(text=sub_toggle, callback_data="toggle_sub_https"))
    return b.as_markup()


def lottery_admin_kb(is_active):
    b = InlineKeyboardBuilder()
    t = "🔴 غیرفعال کردن" if is_active else "🟢 فعال کردن"
    b.row(InlineKeyboardButton(text=t, callback_data="toggle_lottery"))
    b.row(InlineKeyboardButton(text="🎲 انجام قرعه‌کشی", callback_data="do_lottery"))
    return b.as_markup()


def admin_admins_kb(admins):
    b = InlineKeyboardBuilder()
    for a in admins:
        b.row(InlineKeyboardButton(text=f"👤 {a.full_name} ({a.telegram_id})", callback_data=f"admin_detail:{a.telegram_id}"))
    b.row(InlineKeyboardButton(text="➕ ادمین جدید", callback_data="add_admin"))
    return b.as_markup()


def back_kb(cb="cancel"):
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 برگشت/انصراف", callback_data=cb)]])


def force_join_kb(channels):
    b = InlineKeyboardBuilder()
    for ch in channels:
        link = ch.invite_link or f"https://t.me/{ch.channel_id.lstrip('@')}"
        b.row(InlineKeyboardButton(text=f"📢 {ch.channel_name or ch.channel_id}", url=link))
    b.row(InlineKeyboardButton(text="✅ عضو شدم", callback_data="check_join"))
    return b.as_markup()
