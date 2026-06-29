import logging
import random
import string
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.db import AsyncSessionLocal, TransactionType, PaymentMethod, PaymentStatus
from database import crud
from panels.sanei import panel
from bot.keyboards import (
    main_menu_keyboard, plans_keyboard, confirm_purchase_keyboard,
    wallet_keyboard, charge_amounts_keyboard, service_detail_keyboard, back_keyboard
)
from config import config

logger = logging.getLogger(__name__)
router = Router()


class BuyStates(StatesGroup):
    waiting_discount = State()


class ChargeStates(StatesGroup):
    waiting_custom_amount = State()
    waiting_receipt = State()


def gen_email(tid: int) -> str:
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=5))
    return f"u{tid}{suffix}"


@router.message(CommandStart())
async def cmd_start(msg: Message, state: FSMContext, bot: Bot):
    await state.clear()
    args = msg.text.split()
    ref_id = None
    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            ref_id = int(args[1][4:])
        except ValueError:
            pass

    async with AsyncSessionLocal() as db:
        user, is_new = await crud.get_or_create_user(
            db, msg.from_user.id,
            username=msg.from_user.username,
            full_name=msg.from_user.full_name,
            referred_by=ref_id if ref_id and ref_id != msg.from_user.id else None
        )
        if is_new and ref_id and ref_id != msg.from_user.id:
            referrer = await crud.get_user(db, ref_id)
            if referrer:
                reward = int(await crud.get_setting(db, "referral_reward", "50000"))
                await crud.update_wallet(db, referrer, reward,
                    f"پاداش دعوت کاربر {msg.from_user.full_name}", TransactionType.REFERRAL)
                try:
                    await bot.send_message(ref_id,
                        f"🎊 یک نفر با لینک دعوت شما وارد ربات شد!\n"
                        f"💰 {reward:,} تومان به کیف پول شما اضافه شد.")
                except Exception:
                    pass

    is_admin = msg.from_user.id in config.ADMIN_IDS
    from bot.handlers.admin import admin_menu_keyboard as amk
    await msg.answer(
        f"👋 سلام {msg.from_user.first_name or 'کاربر'} عزیز!\n\n"
        f"🌐 به {config.BOT_NAME} خوش آمدید.\n"
        f"🔒 ارائه دهنده سرویس‌های VPN پرسرعت و پایدار\n\n"
        f"از منوی زیر گزینه مورد نظر را انتخاب کنید 👇",
        reply_markup=amk() if is_admin else main_menu_keyboard()
    )


@router.callback_query(F.data == "check_join")
async def check_join(cb: CallbackQuery):
    await cb.answer("✅ ممنون! دوباره /start بزنید.", show_alert=True)


# ─── BUY ─────────────────────────────────────────────────────────────────────
@router.message(F.text == "🛒 خرید سرویس")
async def buy_service(msg: Message):
    async with AsyncSessionLocal() as db:
        plans = await crud.get_active_plans(db)
    if not plans:
        await msg.answer("⚠️ در حال حاضر پلنی فعال نیست.")
        return
    await msg.answer("📦 <b>پلن‌های موجود</b>\n\nیک پلن انتخاب کنید:",
        reply_markup=plans_keyboard(plans), parse_mode="HTML")


@router.callback_query(F.data.startswith("buy_plan:"))
async def select_plan(cb: CallbackQuery, state: FSMContext):
    plan_id = int(cb.data.split(":")[1])
    async with AsyncSessionLocal() as db:
        plan = await crud.get_plan(db, plan_id)
        user = await crud.get_user(db, cb.from_user.id)
    if not plan:
        await cb.answer("پلن یافت نشد!", show_alert=True)
        return
    await state.update_data(plan_id=plan_id)
    wallet_ok = user.wallet >= plan.price
    await cb.message.edit_text(
        f"📦 <b>{plan.name}</b>\n\n"
        f"🔹 حجم: {plan.traffic_gb} GB\n📅 مدت: {plan.days} روز\n"
        f"💰 قیمت: <b>{int(plan.price):,} تومان</b>\n"
        f"👛 کیف پول شما: <b>{int(user.wallet):,} تومان</b>\n\n"
        f"{'✅ موجودی کافی است' if wallet_ok else '❌ موجودی کافی نیست'}",
        reply_markup=confirm_purchase_keyboard(plan_id, plan.price),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("add_discount:"))
async def ask_discount(cb: CallbackQuery, state: FSMContext):
    await state.set_state(BuyStates.waiting_discount)
    await state.update_data(plan_id=int(cb.data.split(":")[1]))
    await cb.message.edit_text("🏷 کد تخفیف خود را وارد کنید:", reply_markup=back_keyboard("cancel"))


@router.message(BuyStates.waiting_discount)
async def apply_discount(msg: Message, state: FSMContext):
    data = await state.get_data()
    code = msg.text.strip().upper()
    async with AsyncSessionLocal() as db:
        plan = await crud.get_plan(db, data["plan_id"])
        dc = await crud.get_discount(db, code)
    if not dc:
        await msg.answer("❌ کد تخفیف نامعتبر یا منقضی است.")
        return
    final = plan.price * (1 - dc.percent / 100)
    await state.update_data(discount_code=code)
    await state.set_state(None)
    await msg.answer(
        f"✅ کد <b>{code}</b> اعمال شد! تخفیف: {dc.percent}%\n"
        f"💰 قیمت نهایی: <b>{int(final):,} تومان</b>",
        reply_markup=confirm_purchase_keyboard(data["plan_id"], final, code),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("confirm_buy:"))
async def confirm_buy(cb: CallbackQuery, state: FSMContext):
    parts = cb.data.split(":")
    plan_id = int(parts[1])
    discount_code = parts[2] if len(parts) > 2 and parts[2] else ""

    async with AsyncSessionLocal() as db:
        plan = await crud.get_plan(db, plan_id)
        user = await crud.get_user(db, cb.from_user.id)
        final_price = plan.price
        dc = None
        if discount_code:
            dc = await crud.get_discount(db, discount_code)
            if dc:
                final_price = plan.price * (1 - dc.percent / 100)

        if user.wallet < final_price:
            await cb.answer("❌ موجودی کافی نیست!", show_alert=True)
            return

        inbound_id = config.INBOUND_IDS[0]
        email = gen_email(cb.from_user.id)
        result = await panel.add_client(inbound_id, email, plan.traffic_gb, plan.days)
        if not result:
            await cb.answer("❌ خطا در اتصال به پنل. با پشتیبانی تماس بگیرید.", show_alert=True)
            return

        sub_link = panel.get_subscription_url(email)
        await crud.create_service(db, user.id, plan.id, result["uuid"], email,
            inbound_id, plan.traffic_gb, plan.days, sub_link=sub_link)
        await crud.update_wallet(db, user, -final_price,
            f"خرید پلن {plan.name}", TransactionType.PURCHASE)
        if dc:
            await crud.use_discount(db, dc)

    await cb.message.edit_text(
        f"🎉 <b>خرید موفق!</b>\n\n📦 پلن: {plan.name}\n"
        f"📊 حجم: {plan.traffic_gb} GB | 📅 مدت: {plan.days} روز\n"
        f"💰 پرداخت: {int(final_price):,} تومان\n\n"
        f"از منوی <b>سرویس‌های من</b> لینک اتصال را دریافت کنید.",
        parse_mode="HTML"
    )
    await state.clear()


# ─── FREE TEST ────────────────────────────────────────────────────────────────
@router.message(F.text == "🎁 سرویس تست رایگان")
async def free_test(msg: Message):
    async with AsyncSessionLocal() as db:
        user = await crud.get_user(db, msg.from_user.id)
        if user.has_used_test:
            await msg.answer("⚠️ شما قبلاً از سرویس تست استفاده کرده‌اید.")
            return
        email = gen_email(msg.from_user.id) + "t"
        result = await panel.add_client(config.INBOUND_IDS[0], email,
            config.FREE_TEST_TRAFFIC_GB, config.FREE_TEST_DAYS)
        if not result:
            await msg.answer("❌ خطا در ایجاد سرویس. لطفاً بعداً امتحان کنید.")
            return
        sub_link = panel.get_subscription_url(email)
        await crud.create_service(db, user.id, None, result["uuid"], email,
            config.INBOUND_IDS[0], config.FREE_TEST_TRAFFIC_GB,
            config.FREE_TEST_DAYS, is_test=True, sub_link=sub_link)
        user.has_used_test = True
        await db.commit()
    await msg.answer(
        f"🎁 <b>سرویس تست رایگان فعال شد!</b>\n\n"
        f"📊 {config.FREE_TEST_TRAFFIC_GB} GB | 📅 {config.FREE_TEST_DAYS} روز\n\n"
        f"از منوی <b>سرویس‌های من</b> لینک اتصال را دریافت کنید.",
        parse_mode="HTML"
    )


# ─── MY SERVICES ─────────────────────────────────────────────────────────────
@router.message(F.text == "📦 سرویس‌های من")
@router.callback_query(F.data == "my_services")
async def my_services(event):
    is_cb = isinstance(event, CallbackQuery)
    msg = event.message if is_cb else event
    uid = event.from_user.id
    async with AsyncSessionLocal() as db:
        user = await crud.get_user(db, uid)
        services = await crud.get_user_services(db, user.id)

    if not services:
        text = "📦 شما هنوز سرویسی ندارید.\n\nاز «🛒 خرید سرویس» اقدام کنید."
        if is_cb:
            await msg.edit_text(text)
        else:
            await msg.answer(text)
        return

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    buttons = []
    for svc in services:
        icon = "🎁" if svc.is_test else "📦"
        label = f"{icon} {svc.traffic_gb}GB | {svc.days}روز"
        buttons.append([InlineKeyboardButton(text=label, callback_data=f"svc_detail:{svc.id}")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    text = f"📦 <b>سرویس‌های شما ({len(services)} عدد)</b>\nروی هر کدام کلیک کنید:"
    if is_cb:
        await msg.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await msg.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("svc_detail:"))
async def svc_detail(cb: CallbackQuery):
    svc_id = int(cb.data.split(":")[1])
    async with AsyncSessionLocal() as db:
        svc = await crud.get_service(db, svc_id)
    if not svc:
        await cb.answer("سرویس یافت نشد!", show_alert=True)
        return
    traffic = await panel.get_client_traffic(svc.panel_email)
    used = 0
    if traffic:
        used = round((traffic.get("up", 0) + traffic.get("down", 0)) / 1024**3, 2)
    remaining = max(0, svc.traffic_gb - used)
    expires = svc.expires_at.strftime("%Y/%m/%d") if svc.expires_at else "نامشخص"
    await cb.message.edit_text(
        f"📦 <b>جزئیات سرویس</b>\n\n"
        f"📊 حجم کل: {svc.traffic_gb} GB\n"
        f"📉 مصرف شده: {used} GB\n"
        f"📈 باقی‌مانده: {remaining} GB\n"
        f"📅 انقضا: {expires}\n"
        f"{'🎁 تست رایگان' if svc.is_test else '💎 سرویس اصلی'}",
        reply_markup=service_detail_keyboard(svc.id), parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("sub_link:"))
async def send_sub_link(cb: CallbackQuery):
    svc_id = int(cb.data.split(":")[1])
    async with AsyncSessionLocal() as db:
        svc = await crud.get_service(db, svc_id)
    if not svc or not svc.sub_link:
        await cb.answer("لینک موجود نیست!", show_alert=True)
        return
    await cb.message.answer(
        f"🔗 <b>لینک سابسکریپشن شما:</b>\n\n<code>{svc.sub_link}</code>\n\n"
        f"در v2rayNG / Hiddify / Nekoray وارد کنید.",
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("refresh_svc:"))
async def refresh_svc(cb: CallbackQuery):
    await cb.answer("🔄 بروزرسانی...")
    await svc_detail(cb)


# ─── WALLET ───────────────────────────────────────────────────────────────────
@router.message(F.text == "💰 کیف پول")
async def wallet_menu(msg: Message):
    async with AsyncSessionLocal() as db:
        user = await crud.get_user(db, msg.from_user.id)
    await msg.answer(
        f"💰 <b>کیف پول</b>\n\n💵 موجودی: <b>{int(user.wallet):,} تومان</b>\n\nروش شارژ انتخاب کنید:",
        reply_markup=wallet_keyboard(bool(config.ZARINPAL_MERCHANT), bool(config.CARD_NUMBER)),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("charge:"))
async def charge_start(cb: CallbackQuery, state: FSMContext):
    method = cb.data.split(":")[1]
    await state.update_data(method=method)
    await cb.message.edit_text("💰 مبلغ شارژ را انتخاب کنید:", reply_markup=charge_amounts_keyboard())


@router.callback_query(F.data.startswith("charge_amount:"))
async def charge_amount(cb: CallbackQuery, state: FSMContext):
    val = cb.data.split(":")[1]
    data = await state.get_data()
    method = data.get("method", "card")
    if val == "custom":
        await state.set_state(ChargeStates.waiting_custom_amount)
        await cb.message.edit_text("💰 مبلغ دلخواه را به تومان وارد کنید:", reply_markup=back_keyboard("cancel"))
        return
    await _do_charge(cb, state, int(val), method)


@router.message(ChargeStates.waiting_custom_amount)
async def custom_amount(msg: Message, state: FSMContext):
    try:
        amount = int(msg.text.replace(",", "").strip())
        if amount < 10000:
            await msg.answer("❌ حداقل ۱۰،۰۰۰ تومان.")
            return
    except ValueError:
        await msg.answer("❌ عدد صحیح وارد کنید.")
        return
    data = await state.get_data()
    await _do_charge_msg(msg, state, amount, data.get("method", "card"))


async def _do_charge(cb: CallbackQuery, state: FSMContext, amount: int, method: str):
    if method == "zarinpal":
        from payments.zarinpal import create_zarinpal_payment
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        cb_url = f"{config.WEBHOOK_URL}/payment/zarinpal" if config.WEBHOOK_URL else "https://t.me"
        authority, pay_url = await create_zarinpal_payment(amount, f"شارژ {config.BOT_NAME}", cb_url)
        if not authority:
            await cb.message.edit_text(f"❌ خطا: {pay_url}")
            return
        async with AsyncSessionLocal() as db:
            user = await crud.get_user(db, cb.from_user.id)
            await crud.create_payment(db, user.id, amount, PaymentMethod.ZARINPAL, authority)
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 رفتن به درگاه پرداخت", url=pay_url)],
            [InlineKeyboardButton(text="🔙 انصراف", callback_data="cancel")],
        ])
        await cb.message.edit_text(
            f"💳 <b>پرداخت زرین‌پال</b>\n\n💰 مبلغ: {amount:,} تومان\n\nروی دکمه زیر کلیک کنید:",
            reply_markup=kb, parse_mode="HTML")
    else:
        await state.update_data(amount=amount)
        await state.set_state(ChargeStates.waiting_receipt)
        await cb.message.edit_text(
            f"🏦 <b>کارت به کارت</b>\n\n"
            f"💰 مبلغ: <b>{amount:,} تومان</b>\n\n"
            f"واریز به:\n<code>{config.CARD_NUMBER}</code>\nبه نام: {config.CARD_HOLDER}\n\n"
            f"✅ سپس تصویر رسید را ارسال کنید:",
            parse_mode="HTML", reply_markup=back_keyboard("cancel")
        )


async def _do_charge_msg(msg: Message, state: FSMContext, amount: int, method: str):
    if method == "card":
        await state.update_data(amount=amount)
        await state.set_state(ChargeStates.waiting_receipt)
        await msg.answer(
            f"🏦 <b>کارت به کارت</b>\n\n💰 مبلغ: <b>{amount:,} تومان</b>\n\n"
            f"واریز به:\n<code>{config.CARD_NUMBER}</code>\nبه نام: {config.CARD_HOLDER}\n\n"
            f"✅ سپس تصویر رسید را ارسال کنید:",
            parse_mode="HTML", reply_markup=back_keyboard("cancel")
        )


@router.message(ChargeStates.waiting_receipt, F.photo)
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
    await msg.answer("✅ رسید دریافت شد. پس از تایید ادمین، کیف پول شارژ می‌شود.")
    from bot.keyboards import payment_confirm_keyboard
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_photo(admin_id, file_id,
                caption=(
                    f"💳 <b>درخواست شارژ کارتی</b>\n\n"
                    f"👤 {msg.from_user.full_name} (@{msg.from_user.username or '-'})\n"
                    f"🆔 <code>{msg.from_user.id}</code>\n"
                    f"💰 {amount:,} تومان"
                ),
                reply_markup=payment_confirm_keyboard(pay_id, msg.from_user.id),
                parse_mode="HTML"
            )
        except Exception:
            pass


# ─── REFERRAL ─────────────────────────────────────────────────────────────────
@router.message(F.text == "🎊 شارژ رایگان")
async def referral_menu(msg: Message):
    async with AsyncSessionLocal() as db:
        user = await crud.get_user(db, msg.from_user.id)
        ref_count = await crud.count_referrals(db, msg.from_user.id)
        reward = int(await crud.get_setting(db, "referral_reward", "50000"))
    bot_me = await msg.bot.get_me()
    ref_link = f"https://t.me/{bot_me.username}?start=ref_{msg.from_user.id}"
    await msg.answer(
        f"🎊 <b>شارژ رایگان با دعوت دوستان</b>\n\n"
        f"به ازای هر دوستی که با لینک شما ثبت‌نام کند،\n"
        f"💰 <b>{reward:,} تومان</b> به کیف پول شما اضافه می‌شود!\n\n"
        f"👥 دعوت‌های موفق: <b>{ref_count} نفر</b>\n"
        f"💵 موجودی شما: <b>{int(user.wallet):,} تومان</b>\n\n"
        f"🔗 <b>لینک اختصاصی:</b>\n<code>{ref_link}</code>\n\n"
        f"همین الان برای دوستانتان ارسال کنید 👆",
        parse_mode="HTML"
    )


# ─── LOTTERY ─────────────────────────────────────────────────────────────────
@router.message(F.text == "🎰 قرعه‌کشی")
async def lottery_menu(msg: Message):
    async with AsyncSessionLocal() as db:
        user = await crud.get_user(db, msg.from_user.id)
        num = await crud.get_or_create_lottery_number(db, user)
        is_active = await crud.get_setting(db, "lottery_active", "false")
    status = "🟢 قرعه‌کشی فعال است" if is_active == "true" else "🔴 قرعه‌کشی هنوز برگزار نشده"
    await msg.answer(
        f"🎰 <b>قرعه‌کشی</b>\n\n{status}\n\n"
        f"🎫 <b>شماره قرعه‌کشی شما:</b>\n\n"
        f"┌──────────────┐\n"
        f"│   <b>{num}   </b>│\n"
        f"└──────────────┘\n\n"
        f"این شماره منحصر‌به‌فرد شماست 🍀\n"
        f"منتظر اعلام نتیجه از طرف ادمین باشید!",
        parse_mode="HTML"
    )


# ─── MISC ─────────────────────────────────────────────────────────────────────
@router.message(F.text == "📞 پشتیبانی")
async def support(msg: Message):
    s = f"@{config.SUPPORT_USERNAME}" if config.SUPPORT_USERNAME else "از طریق ربات"
    await msg.answer(f"📞 <b>پشتیبانی</b>\n\nارتباط: {s}\n⏰ ۹ صبح تا ۱۲ شب", parse_mode="HTML")


@router.message(F.text == "📖 راهنما")
async def guide(msg: Message):
    await msg.answer(
        "📖 <b>راهنمای استفاده</b>\n\n"
        "1️⃣ خرید سرویس → انتخاب پلن\n"
        "2️⃣ کیف پول → شارژ موجودی\n"
        "3️⃣ سرویس‌های من → لینک اتصال\n"
        "4️⃣ تست رایگان → یک بار برای همه\n\n"
        "📱 <b>نرم‌افزارهای پیشنهادی:</b>\n"
        "• اندروید: v2rayNG\n• iOS: Streisand\n• ویندوز: Hiddify",
        parse_mode="HTML"
    )


@router.callback_query(F.data == "cancel")
async def cancel_cb(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await cb.message.delete()
    except Exception:
        pass
