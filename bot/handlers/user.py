import logging
import random
import string
from datetime import datetime, timedelta
from urllib.parse import quote
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, URLInputFile
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton
from database.db import AsyncSessionLocal, TransactionType, PaymentMethod, UserStatus, ServiceStatus
from database import crud
from panels.sanei import panel
from bot.keyboards import main_menu_kb, categories_kb, plans_kb, confirm_plan_kb, wallet_kb, charge_amounts_kb, service_detail_kb, back_kb, force_join_kb, phone_request_kb
from config import config

logger = logging.getLogger(__name__)
router = Router()

class BuyState(StatesGroup):
    waiting_discount = State()

class ChargeState(StatesGroup):
    waiting_custom_amount = State()
    waiting_receipt = State()

class RenameState(StatesGroup):
    waiting_name = State()

def gen_email(tid):
    return f"u{tid}{''.join(random.choices(string.ascii_lowercase, k=5))}"

import re as _re

def parse_inbound_ids(raw):
    """Settings can hold a single inbound id ('3') or several comma-separated
    ones ('3,9') to sell multiple locations (e.g. Germany + USA) together."""
    if not raw:
        return []
    return [int(x.strip()) for x in str(raw).split(",") if x.strip()]


async def gen_client_name(db, tid, username):
    """Uses the user's real Telegram @username as the service/client name.
    Falls back to a generated name if they have no username. Appends a
    number if that name is already taken."""
    base = _re.sub(r"[^a-zA-Z0-9_]", "", username or "")
    if not base:
        base = gen_email(tid)
    name = base
    n = 1
    while await crud.email_exists(db, name):
        n += 1
        name = f"{base}{n}"
    return name


async def send_sub_qr(bot: Bot, chat_id: int, sub_link: str):
    """Sends a QR code image for the given subscription link using a free
    public QR-generation endpoint, so no extra Python packages are needed."""
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=350x350&data={quote(sub_link, safe='')}"
    try:
        await bot.send_photo(chat_id, photo=qr_url, caption="📱 اسکن کن برای افزودن سریع سرویس")
    except Exception as e:
        logger.error(f"send_sub_qr failed: {type(e).__name__}: {e}")
        try:
            await bot.send_message(chat_id, f"📱 QR کد: {qr_url}")
        except Exception:
            pass

async def check_force_join(bot, user_id):
    async with AsyncSessionLocal() as db:
        enabled = await crud.get_setting(db, "force_join_enabled", "false")
        if enabled != "true":
            return []
        channels = await crud.get_active_force_joins(db)
    not_joined = []
    for ch in channels:
        try:
            m = await bot.get_chat_member(ch.channel_id, user_id)
            if m.status in ("left", "kicked"):
                not_joined.append(ch)
        except Exception:
            not_joined.append(ch)
    return not_joined

async def is_admin_user(user_id):
    if user_id in config.ADMIN_IDS:
        return True
    async with AsyncSessionLocal() as db:
        a = await crud.get_admin(db, user_id)
        return a is not None


async def get_admin_perms(user_id):
    """Returns None for owner-level admins (full menu), or a list of perms for sub-admins."""
    import json
    if user_id in config.ADMIN_IDS:
        return None
    async with AsyncSessionLocal() as db:
        a = await crud.get_admin(db, user_id)
    if not a:
        return []
    return json.loads(a.permissions or "[]")

@router.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext):
    await state.clear()
    args = msg.text.split()
    ref_id = None
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            ref_id = int(args[1][4:])
        except ValueError:
            pass

    async with AsyncSessionLocal() as db:
        user, is_new = await crud.get_or_create_user(db, msg.from_user.id, msg.from_user.username, msg.from_user.full_name, referred_by=ref_id if ref_id and ref_id != msg.from_user.id else None)
        if user.status == UserStatus.BANNED:
            await msg.answer("⛔️ حساب شما مسدود شده است.")
            return
        if is_new and ref_id and ref_id != msg.from_user.id:
            referrer = await crud.get_user(db, ref_id)
            if referrer:
                reward = int(await crud.get_setting(db, "referral_reward", "50000"))
                await crud.update_wallet(db, referrer, reward, "پاداش دعوت", TransactionType.REFERRAL)
                try:
                    await msg.bot.send_message(ref_id, f"🎊 یک نفر با لینک شما وارد ربات شد!\n💰 {reward:,} تومان اضافه شد.")
                except Exception:
                    pass
        bot_name = await crud.get_setting(db, "bot_name", "فروشگاه VPN")

    not_joined = await check_force_join(msg.bot, msg.from_user.id)
    if not_joined:
        await msg.answer("📢 برای استفاده از ربات در کانال‌های زیر عضو شوید:", reply_markup=force_join_kb(not_joined))
        return

    is_admin = await is_admin_user(msg.from_user.id)

    if not is_admin:
        async with AsyncSessionLocal() as db:
            db_user = await crud.get_user(db, msg.from_user.id)
        if not db_user or (not db_user.phone and not db_user.phone_exempt):
            await msg.answer(
                "🔐 برای شروع، لطفاً برای احراز هویت شماره تلفن خودتون رو با دکمه‌ی زیر ارسال کنید.\n"
                "⚠️ فقط شماره ایران قبول می‌شه و باید شماره‌ی خودتون باشه (نه شماره‌ی شخص دیگه).",
                reply_markup=phone_request_kb()
            )
            return

    welcome = f"👋 سلام {msg.from_user.first_name or 'کاربر'} عزیز!\n\n🌐 به {bot_name} خوش آمدید\n🔒 ارائه دهنده سرویس‌های VPN پرسرعت و پایدار\n\nاز منوی زیر گزینه مورد نظر را انتخاب کنید 👇"
    if is_admin:
        from bot.keyboards import admin_menu_kb
        perms = await get_admin_perms(msg.from_user.id)
        await msg.answer(welcome, reply_markup=admin_menu_kb(perms))
    else:
        await msg.answer(welcome, reply_markup=main_menu_kb())


@router.message(F.contact)
async def receive_phone(msg: Message, state: FSMContext):
    contact = msg.contact
    if not contact or contact.user_id != msg.from_user.id:
        await msg.answer("❌ لطفاً فقط شماره‌ی خودتون رو با دکمه‌ی زیر ارسال کنید (نه شماره‌ی شخص دیگه).", reply_markup=phone_request_kb())
        return
    raw = contact.phone_number.strip().replace(" ", "").replace("-", "")
    if not raw.startswith("+"):
        raw = "+" + raw
    is_iran = raw.startswith("+98") and len(raw) == 13 and raw[3] == "9"
    if not is_iran:
        await msg.answer("❌ فقط شماره‌های ایران (مثلاً +98912xxxxxxx) قبول می‌شه. لطفاً شماره‌ی درست رو ارسال کنید.", reply_markup=phone_request_kb())
        return
    async with AsyncSessionLocal() as db:
        user, _ = await crud.get_or_create_user(db, msg.from_user.id, msg.from_user.username, msg.from_user.full_name)
        await crud.set_user_phone(db, msg.from_user.id, raw)
    await msg.answer("✅ شماره‌ی شما با موفقیت ثبت شد.", reply_markup=main_menu_kb())

@router.callback_query(F.data == "check_join")
async def check_join_cb(cb: CallbackQuery):
    not_joined = await check_force_join(cb.bot, cb.from_user.id)
    if not_joined:
        await cb.answer("❌ هنوز عضو نشدید!", show_alert=True)
        return
    await cb.message.delete()
    await cb.message.answer("✅ خوش آمدید!", reply_markup=main_menu_kb())

@router.message(F.text == "🛒 خرید اشتراک")
async def buy_service(msg: Message):
    async with AsyncSessionLocal() as db:
        cats = await crud.get_active_categories(db)
    if cats:
        await msg.answer("🛒 لطفاً دسته‌بندی را انتخاب کنید:", reply_markup=categories_kb(cats))
    else:
        async with AsyncSessionLocal() as db:
            plans = await crud.get_active_plans(db)
        if not plans:
            await msg.answer("❌ پلنی موجود نیست.")
            return
        await msg.answer("🛒 یک پلن انتخاب کنید:", reply_markup=plans_kb(plans))

@router.callback_query(F.data.startswith("cat:"))
async def select_cat(cb: CallbackQuery):
    cat_id = int(cb.data.split(":")[1])
    async with AsyncSessionLocal() as db:
        plans = await crud.get_active_plans(db, category_id=cat_id)
        cat = await crud.get_category(db, cat_id)
    if not plans:
        await cb.answer("پلنی در این دسته نیست.", show_alert=True)
        return
    await cb.message.edit_text(f"{cat.icon} {cat.name}\n\nیک پلن انتخاب کنید:", reply_markup=plans_kb(plans, back=True))

@router.callback_query(F.data == "buy_back")
async def buy_back(cb: CallbackQuery):
    async with AsyncSessionLocal() as db:
        cats = await crud.get_active_categories(db)
    await cb.message.edit_text("🛒 لطفاً دسته‌بندی را انتخاب کنید:", reply_markup=categories_kb(cats))

@router.callback_query(F.data.startswith("plan:"))
async def select_plan(cb: CallbackQuery):
    plan_id = int(cb.data.split(":")[1])
    async with AsyncSessionLocal() as db:
        plan = await crud.get_plan(db, plan_id)
        user = await crud.get_user(db, cb.from_user.id)
        if not user:
            user, _ = await crud.get_or_create_user(db, cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
    if not plan:
        await cb.answer("یافت نشد!", show_alert=True)
        return
    ok = user.wallet >= plan.price
    users_text = "نامحدود" if plan.max_users == 0 else f"{plan.max_users} کاربر"
    traffic_text = "نامحدود" if plan.traffic_gb == 0 else f"{plan.traffic_gb}GB"
    await cb.message.edit_text(f"📦 <b>{plan.name}</b>\n\n🔹 حجم: {traffic_text}\n📅 مدت: {plan.days}روز\n👥 کاربر: {users_text}\n💰 قیمت: {int(plan.price):,} تومان\n👛 موجودی: {int(user.wallet):,} تومان\n\n{'✅ موجودی کافیست' if ok else '❌ موجودی ناکافی'}", reply_markup=confirm_plan_kb(plan_id), parse_mode="HTML")

@router.callback_query(F.data.startswith("add_discount:"))
async def ask_discount(cb: CallbackQuery, state: FSMContext):
    plan_id = int(cb.data.split(":")[1])
    await state.set_state(BuyState.waiting_discount)
    await state.update_data(plan_id=plan_id)
    await cb.message.edit_text("🏷 کد تخفیف را وارد کنید:", reply_markup=back_kb("cancel"))

@router.message(BuyState.waiting_discount)
async def apply_discount(msg: Message, state: FSMContext):
    data = await state.get_data()
    code = msg.text.strip().upper()
    async with AsyncSessionLocal() as db:
        plan = await crud.get_plan(db, data["plan_id"])
        dc = await crud.get_discount(db, code)
    if not dc:
        await msg.answer("❌ کد نامعتبر.")
        return
    await state.clear()
    final = plan.price * (1 - dc.percent / 100)
    await msg.answer(f"✅ کد اعمال شد! قیمت نهایی: {int(final):,} تومان", reply_markup=confirm_plan_kb(data["plan_id"], code))

@router.callback_query(F.data.startswith("confirm_buy:"))
async def confirm_buy(cb: CallbackQuery, state: FSMContext):
    parts = cb.data.split(":")
    plan_id = int(parts[1])
    discount_code = parts[2] if len(parts) > 2 else ""

    async with AsyncSessionLocal() as db:
        plan = await crud.get_plan(db, plan_id)
        user = await crud.get_user(db, cb.from_user.id)
        if not user:
            user, _ = await crud.get_or_create_user(db, cb.from_user.id, cb.from_user.username, cb.from_user.full_name)
        final_price = plan.price
        dc = None
        if discount_code:
            dc = await crud.get_discount(db, discount_code)
            if dc:
                final_price = plan.price * (1 - dc.percent / 100)

        if user.wallet < final_price:
            card = await crud.get_setting(db, "card_number", "")
            await cb.message.edit_text(f"❌ موجودی کافی نیست!\n\nموجودی: {int(user.wallet):,}\nلازم: {int(final_price):,}\n\nکیف پول را شارژ کنید:", reply_markup=wallet_kb(has_card=bool(card)))
            return

        raw_inbounds = plan.inbound_id or await crud.get_setting(db, "inbound_id", "1")
        inbound_ids = parse_inbound_ids(raw_inbounds) or [1]
        base_name = await gen_client_name(db, cb.from_user.id, cb.from_user.username)
        sub_id = base_name
        sub_link = panel.get_subscription_url(sub_id)
        locations = []
        for ib_id in inbound_ids:
            loc_email = base_name if len(inbound_ids) == 1 else f"{base_name}-{ib_id}"
            result = await panel.add_client(ib_id, loc_email, plan.traffic_gb, plan.days, limit_ip=plan.max_users, sub_id=sub_id)
            if not result:
                continue
            cfg_link = await panel.get_client_config_link(ib_id, result["uuid"], loc_email)
            await crud.create_service(db, user.id, plan_id, result["uuid"], loc_email, ib_id, plan.traffic_gb, plan.days, sub_link=sub_link, vless_link=cfg_link, max_users=plan.max_users)
            locations.append(cfg_link)
        if not locations:
            await cb.answer("❌ خطا در اتصال به پنل.", show_alert=True)
            return
        await crud.update_wallet(db, user, -final_price, f"خرید {plan.name}", TransactionType.DEPOSIT)
        if dc:
            await crud.use_discount(db, dc)

    config_block = ""
    if len(locations) > 1:
        for i, link in enumerate(locations, 1):
            config_block += f"\n\n⚙️ کانفیگ لوکیشن {i}:\n<code>{link}</code>"
    elif locations:
        config_block = f"\n\n⚙️ کانفیگ مستقیم:\n<code>{locations[0]}</code>"
    users_text = "نامحدود" if plan.max_users == 0 else f"{plan.max_users} کاربر"
    traffic_text = "نامحدود" if plan.traffic_gb == 0 else f"{plan.traffic_gb}GB"
    await cb.message.edit_text(f"🎉 <b>خرید موفق!</b>\n\n📦 {plan.name}\n📊 {traffic_text} | 📅 {plan.days} روز | 👥 {users_text}\n\n🔗 لینک سابسکریپشن (شامل همه‌ی لوکیشن‌ها):\n<code>{sub_link}</code>{config_block}\n\nبرای مشاهده به «سرویس‌های من» مراجعه کنید.", parse_mode="HTML")
    await state.clear()

@router.callback_query(F.data == "cancel")
async def cancel_cb(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await cb.message.delete()
    except Exception:
        pass

@router.message(F.text == "🎁 تست رایگان")
async def free_test(msg: Message):
    async with AsyncSessionLocal() as db:
        enabled = await crud.get_setting(db, "free_test_enabled", "true")
        if enabled != "true":
            await msg.answer("❌ تست رایگان غیرفعال است.")
            return
        user = await crud.get_user(db, msg.from_user.id)
        if not user:
            user, _ = await crud.get_or_create_user(db, msg.from_user.id, msg.from_user.username, msg.from_user.full_name)
        if user.has_used_test:
            await msg.answer("⚠️ قبلاً استفاده کرده‌اید.")
            return
        traffic_mb = int(await crud.get_setting(db, "free_test_traffic_mb", "500"))
        days = int(await crud.get_setting(db, "free_test_days", "1"))
        default_inbound = await crud.get_setting(db, "inbound_id", "1")
        inbound_id = int(await crud.get_setting(db, "test_inbound_id", default_inbound) or default_inbound)
        email = await gen_client_name(db, msg.from_user.id, msg.from_user.username)

    traffic_gb = round(traffic_mb / 1024, 2)
    if traffic_gb < 0.1:
        traffic_gb = 0.1
    await msg.answer("⏳ در حال ساخت سرویس...")
    result = await panel.add_client(inbound_id, email, traffic_gb, days, limit_ip=1)
    if not result:
        await msg.answer("❌ خطا در ایجاد سرویس. لطفاً بعداً امتحان کنید.")
        return
    async with AsyncSessionLocal() as db:
        from sqlalchemy import text
        sub_link = panel.get_subscription_url(email)
        config_link = await panel.get_client_config_link(inbound_id, result["uuid"], email)
        await crud.create_service(db, user.id, None, result["uuid"], email, inbound_id, traffic_gb, days, is_test=True, sub_link=sub_link, vless_link=config_link)
        await db.execute(text("UPDATE users SET has_used_test = 1 WHERE id = :uid"), {"uid": user.id})
        await db.commit()
    config_block = f"\n\n⚙️ کانفیگ مستقیم:\n<code>{config_link}</code>" if config_link else ""
    await msg.answer(f"🎁 <b>سرویس تست آماده شد!</b>\n\n📊 {traffic_mb}MB | 📅 {days} روز\n\n🔗 <code>{sub_link}</code>{config_block}", parse_mode="HTML")

@router.message(F.text == "📦 سرویس‌های من")
@router.callback_query(F.data == "my_services")
async def my_services(event):
    is_cb = isinstance(event, CallbackQuery)
    msg = event.message if is_cb else event
    uid = event.from_user.id
    async with AsyncSessionLocal() as db:
        user = await crud.get_user(db, uid)
        if not user:
            user, _ = await crud.get_or_create_user(db, uid, event.from_user.username, event.from_user.full_name)
        services = await crud.get_user_services(db, user.id)
    if not services:
        text = "📦 سرویس فعالی ندارید."
        if is_cb:
            await msg.edit_text(text)
        else:
            await msg.answer(text)
        return
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    buttons = []
    for svc in services:
        icon = "🎁" if svc.is_test else "📦"
        t_text = "نامحدود" if svc.traffic_gb == 0 else f"{svc.traffic_gb}GB"
        name = svc.service_name or f"{icon} {t_text}/{svc.days}روز"
        buttons.append([InlineKeyboardButton(text=name, callback_data=f"svc:{svc.id}")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    text = f"📦 سرویس‌های شما ({len(services)}):"
    if is_cb:
        await msg.edit_text(text, reply_markup=kb)
    else:
        await msg.answer(text, reply_markup=kb)

@router.callback_query(F.data.startswith("svc:"))
async def svc_detail(cb: CallbackQuery):
    svc_id = int(cb.data.split(":")[1])
    async with AsyncSessionLocal() as db:
        svc = await crud.get_service(db, svc_id)
    if not svc:
        await cb.answer("یافت نشد!", show_alert=True)
        return
    traffic = await panel.get_client_traffic(svc.panel_email)
    used = round((traffic.get("up", 0) + traffic.get("down", 0)) / 1024**3, 2) if traffic else 0
    if svc.traffic_gb == 0:
        total_text = "نامحدود"
        remaining_text = "نامحدود"
    else:
        remaining = max(0, svc.traffic_gb - used)
        total_text = f"{svc.traffic_gb}GB"
        remaining_text = f"{remaining}GB"
    expires = svc.expires_at.strftime("%Y/%m/%d") if svc.expires_at else "?"
    name = svc.service_name or svc.panel_email
    await cb.message.edit_text(f"📦 <b>{name}</b>\n\n📊 کل: {total_text}\n📉 مصرف: {used}GB\n📈 باقی: {remaining_text}\n📅 انقضا: {expires}", reply_markup=service_detail_kb(svc.id), parse_mode="HTML")

@router.callback_query(F.data.startswith("sub_link:"))
async def send_sub_link(cb: CallbackQuery):
    svc_id = int(cb.data.split(":")[1])
    async with AsyncSessionLocal() as db:
        svc = await crud.get_service(db, svc_id)
    if not svc or not svc.sub_link:
        await cb.answer("لینک موجود نیست!", show_alert=True)
        return
    text = f"🔗 سابسکریپشن:\n<code>{svc.sub_link}</code>"
    if svc.vless_link:
        text += f"\n\n⚙️ کانفیگ مستقیم:\n<code>{svc.vless_link}</code>"
    await cb.message.answer(text, parse_mode="HTML")

@router.callback_query(F.data.startswith("rename_svc:"))
async def rename_svc(cb: CallbackQuery, state: FSMContext):
    svc_id = int(cb.data.split(":")[1])
    await state.set_state(RenameState.waiting_name)
    await state.update_data(svc_id=svc_id)
    await cb.message.answer("✏️ نام جدید را وارد کنید:")

@router.message(RenameState.waiting_name)
async def do_rename(msg: Message, state: FSMContext):
    data = await state.get_data()
    name = msg.text.strip()[:64]
    async with AsyncSessionLocal() as db:
        await crud.update_service(db, data["svc_id"], service_name=name)
    await state.clear()
    await msg.answer(f"✅ نام تغییر کرد: {name}")

@router.callback_query(F.data.startswith("refresh_svc:"))
async def refresh_svc(cb: CallbackQuery):
    await svc_detail(cb)

@router.message(F.text == "💰 کیف پول")
async def wallet_menu(msg: Message):
    async with AsyncSessionLocal() as db:
        user = await crud.get_user(db, msg.from_user.id)
        if not user:
            user, _ = await crud.get_or_create_user(db, msg.from_user.id, msg.from_user.username, msg.from_user.full_name)
        card = await crud.get_setting(db, "card_number", "")
    await msg.answer(f"💰 موجودی: {int(user.wallet):,} تومان", reply_markup=wallet_kb(has_card=bool(card)))

@router.callback_query(F.data.startswith("charge:"))
async def charge_start(cb: CallbackQuery, state: FSMContext):
    method = cb.data.split(":")[1]
    await state.update_data(method=method)
    await cb.message.edit_text("💰 مبلغ را انتخاب کنید:", reply_markup=charge_amounts_kb())

@router.callback_query(F.data.startswith("charge_amount:"))
async def charge_amount(cb: CallbackQuery, state: FSMContext):
    val = cb.data.split(":")[1]
    if val == "custom":
        await state.set_state(ChargeState.waiting_custom_amount)
        await cb.message.edit_text("💰 مبلغ دلخواه:")
        return
    amount = int(val)
    await state.update_data(amount=amount)
    await state.set_state(ChargeState.waiting_receipt)
    async with AsyncSessionLocal() as db:
        card = await crud.get_setting(db, "card_number", "")
        holder = await crud.get_setting(db, "card_holder", "")
    await cb.message.edit_text(f"🏦 مبلغ: {amount:,}\nکارت: {card}\nبه نام: {holder}\n\nرسید را ارسال کنید:")

@router.message(ChargeState.waiting_custom_amount)
async def custom_amount(msg: Message, state: FSMContext):
    try:
        amount = int(msg.text.replace(",", ""))
    except ValueError:
        await msg.answer("❌ عدد وارد کنید.")
        return
    await state.update_data(amount=amount)
    await state.set_state(ChargeState.waiting_receipt)
    async with AsyncSessionLocal() as db:
        card = await crud.get_setting(db, "card_number", "")
        holder = await crud.get_setting(db, "card_holder", "")
    await msg.answer(f"🏦 مبلغ: {amount:,}\nکارت: {card}\nبه نام: {holder}\n\nرسید را ارسال کنید:")

@router.message(ChargeState.waiting_receipt, F.photo)
async def receipt_received(msg: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    amount = data["amount"]
    file_id = msg.photo[-1].file_id
    async with AsyncSessionLocal() as db:
        user = await crud.get_user(db, msg.from_user.id)
        pay = await crud.create_payment(db, user.id, amount, PaymentMethod.CARD)
        pay.receipt_file_id = file_id
        await db.commit()
        pay_id = pay.id
    await state.clear()
    await msg.answer("✅ رسید دریافت شد، منتظر تأیید باشید.")
    from bot.keyboards import payment_confirm_kb
    async with AsyncSessionLocal() as db:
        sub_admin_ids = await crud.get_admins_with_perm(db, "payment")
        sender_user = await crud.get_user(db, msg.from_user.id)
    phone_line = f"\n📱 {sender_user.phone}" if sender_user and sender_user.phone else ""
    notify_ids = set(config.ADMIN_IDS) | set(sub_admin_ids)
    for admin_id in notify_ids:
        try:
            await bot.send_photo(admin_id, file_id, caption=f"💳 درخواست شارژ\n👤 {msg.from_user.full_name}\n🆔 {msg.from_user.id}{phone_line}\n💰 {amount:,}", reply_markup=payment_confirm_kb(pay_id, msg.from_user.id))
        except Exception:
            pass

@router.message(F.text == "👥 شارژ رایگان")
async def referral_menu(msg: Message):
    async with AsyncSessionLocal() as db:
        user = await crud.get_user(db, msg.from_user.id)
        if not user:
            user, _ = await crud.get_or_create_user(db, msg.from_user.id, msg.from_user.username, msg.from_user.full_name)
        ref_count = await crud.count_referrals(db, msg.from_user.id)
        reward = int(await crud.get_setting(db, "referral_reward", "50000"))
    bot_me = await msg.bot.get_me()
    link = f"https://t.me/{bot_me.username}?start=ref_{msg.from_user.id}"
    await msg.answer(f"👥 پاداش هر دعوت: {reward:,}\n👤 دعوت‌ها: {ref_count}\n💵 موجودی: {int(user.wallet):,}\n\n🔗 {link}")

@router.message(F.text == "🏆 مسابقه")
async def lottery_menu(msg: Message):
    async with AsyncSessionLocal() as db:
        user = await crud.get_user(db, msg.from_user.id)
        if not user:
            user, _ = await crud.get_or_create_user(db, msg.from_user.id, msg.from_user.username, msg.from_user.full_name)
        num = await crud.get_or_create_lottery_number(db, user)
        active = await crud.get_setting(db, "lottery_active", "false")
    status = "🟢 فعال" if active == "true" else "🔴 غیرفعال"
    await msg.answer(f"🏆 مسابقه: {status}\n\n🎫 شماره شانس شما: {num}")

@router.message(F.text == "📞 پشتیبانی")
async def support_menu(msg: Message):
    async with AsyncSessionLocal() as db:
        support = await crud.get_setting(db, "support_username", "")
    s = f"@{support}" if support else "نامشخص"
    await msg.answer(f"📞 پشتیبانی: {s}")

@router.message(F.text == "📖 آموزش اتصال")
async def guide_menu(msg: Message):
    await msg.answer("📖 اندروید: v2rayNG\nآیفون: Streisand\nویندوز: Hiddify")


# ---------------- Renew service ----------------

@router.message(F.text == "🔄 تمدید سرویس")
async def renew_list(msg: Message):
    async with AsyncSessionLocal() as db:
        user = await crud.get_user(db, msg.from_user.id)
        if not user:
            await msg.answer("📦 سرویس فعالی ندارید.")
            return
        services = await crud.get_user_services(db, user.id)
    if not services:
        await msg.answer("📦 سرویس فعالی برای تمدید ندارید.")
        return
    b = InlineKeyboardBuilder()
    for svc in services:
        exp = svc.expires_at.strftime("%Y/%m/%d") if svc.expires_at else "-"
        name = svc.service_name or svc.panel_email
        b.row(InlineKeyboardButton(text=f"{name} (تا {exp})", callback_data=f"renew:{svc.id}"))
    await msg.answer("🔄 کدوم سرویس رو می‌خوای تمدید کنی؟", reply_markup=b.as_markup())


@router.callback_query(F.data.startswith("renew:"))
async def renew_confirm(cb: CallbackQuery):
    svc_id = int(cb.data.split(":")[1])
    async with AsyncSessionLocal() as db:
        svc = await crud.get_service(db, svc_id)
        if not svc:
            await cb.answer("یافت نشد!", show_alert=True)
            return
        plan = await crud.get_plan(db, svc.plan_id) if svc.plan_id else None
    if not plan:
        await cb.answer("این سرویس به یک پلن مشخص وصل نیست، نمی‌شه از این طریق تمدیدش کرد. با پشتیبانی تماس بگیرید.", show_alert=True)
        return
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text=f"✅ تمدید به مبلغ {int(plan.price):,} تومان", callback_data=f"do_renew:{svc_id}"))
    b.row(InlineKeyboardButton(text="❌ انصراف", callback_data="cancel"))
    name = svc.service_name or svc.panel_email
    await cb.message.edit_text(
        f"🔄 تمدید «{name}»\n📊 {plan.traffic_gb}GB | 📅 {plan.days} روز\n💰 هزینه: {int(plan.price):,} تومان\n\nمبلغ از کیف پولتان کسر می‌شود.",
        reply_markup=b.as_markup()
    )


@router.callback_query(F.data.startswith("do_renew:"))
async def do_renew(cb: CallbackQuery):
    svc_id = int(cb.data.split(":")[1])
    async with AsyncSessionLocal() as db:
        svc = await crud.get_service(db, svc_id)
        if not svc:
            await cb.answer("یافت نشد!", show_alert=True)
            return
        plan = await crud.get_plan(db, svc.plan_id) if svc.plan_id else None
        if not plan:
            await cb.answer("پلن این سرویس پیدا نشد.", show_alert=True)
            return
        user = await crud.get_user(db, cb.from_user.id)
        if user.wallet < plan.price:
            await cb.answer("❌ موجودی کافی نیست. اول کیف پول را شارژ کنید.", show_alert=True)
            return
        try:
            await panel.delete_client(svc.inbound_id, svc.panel_uuid, email=svc.panel_email)
        except Exception:
            pass
        result = await panel.add_client(svc.inbound_id, svc.panel_email, plan.traffic_gb, plan.days, limit_ip=plan.max_users, sub_id=svc.panel_email)
        if not result:
            await cb.answer("❌ خطا در ارتباط با پنل. دوباره امتحان کنید.", show_alert=True)
            return
        new_expiry = datetime.utcnow() + timedelta(days=plan.days)
        await crud.update_service(db, svc.id, panel_uuid=result["uuid"], expires_at=new_expiry, status=ServiceStatus.ACTIVE, panel_removed=False)
        await crud.update_wallet(db, user, -plan.price, f"تمدید {svc.panel_email}", TransactionType.DEPOSIT)
    await cb.message.edit_text(f"✅ سرویس با موفقیت تمدید شد!\n📅 انقضای جدید: {new_expiry.strftime('%Y/%m/%d')}")
