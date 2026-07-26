"""Editable message templates. Admins can customize these via the bot's
'📝 مدیریت متن‌ها' menu. Each entry has a default text (with Python
str.format placeholders) and a human-readable list of the variables
available for that message.
"""

TEMPLATES = {
    "tpl_welcome": {
        "label": "👋 پیام خوش‌آمدگویی (استارت)",
        "default": "👋 سلام {name} عزیز!\n\n🌐 به {bot_name} خوش آمدید\n🔒 ارائه دهنده سرویس‌های VPN پرسرعت و پایدار\n\nاز منوی زیر گزینه مورد نظر را انتخاب کنید 👇",
        "vars": "{name} = اسم کاربر، {bot_name} = نام ربات",
    },
    "tpl_purchase_success": {
        "label": "🎉 پیام خرید موفق",
        "default": "🎉 <b>خرید موفق!</b>\n\n📦 {plan_name}\n📊 {traffic} | 📅 {days} روز | 👥 {users}\n\n🔗 لینک سابسکریپشن (شامل همه‌ی لوکیشن‌ها):\n<code>{sub_link}</code>{config_block}\n\nبرای مشاهده به «سرویس‌های من» مراجعه کنید.",
        "vars": "{plan_name}, {traffic}, {days}, {users}, {sub_link}, {config_block}",
    },
    "tpl_test_success": {
        "label": "🎁 پیام دریافت تست رایگان",
        "default": "🎁 <b>سرویس تست آماده شد!</b>\n\n📊 {traffic}MB | 📅 {days} روز\n\n🔗 <code>{sub_link}</code>{config_block}",
        "vars": "{traffic}, {days}, {sub_link}, {config_block}",
    },
    "tpl_renew_success": {
        "label": "🔄 پیام تمدید موفق",
        "default": "✅ سرویس با موفقیت تمدید شد!\n📅 انقضای جدید: {new_expiry}",
        "vars": "{new_expiry}",
    },
}


def render(text, **kwargs):
    """Formats a template, falling back gracefully if the admin's custom
    text is missing a variable or has a typo in the placeholders."""
    try:
        return text.format(**kwargs)
    except Exception:
        return text
