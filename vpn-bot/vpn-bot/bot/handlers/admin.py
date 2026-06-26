import logging
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from database.db import AsyncSessionLocal, TransactionType, PaymentMethod, PaymentStatus
from database import crud
from bot.keyboards import (
    admin_plans_list_keyboard, discounts_list_keyboard,
    lottery_draw_keyboard, payment_confirm_keyboard, back_keyboard
)
from config import config

logger = logging.getLogger(__name__)
router = Router()


def is_admin(uid: int) -> bool:
    return uid in config.ADMIN_IDS


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


class AddPlanState(StatesGroup):
    name = State()
    traffic = State()
    days = State()
    price = State()


class AddDiscountState(StatesGroup):
    code = State()
    percent = State()
    max_uses = State()


class BroadcastState(StatesGroup):
    message = State()


class EditSettingState(StatesGroup):
    referral_reward = State()


# ─── ADMIN GUARD ──────────────────────────────────────────────────────────────
def admin_only(func):
    async def wrapper(event, *args, **kwargs):
        uid = event.from_user.id
        if not is_admin(uid):
            return
        return await func(event, *args, **kwargs)
    wrapper.__name__ = func.__name__
    return wrapper


@router.message(Command("admin"))
async def admin_cmd(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    await msg.answer("⚙️ پنل ادمین", reply_markup=admin_menu_keyboard())


@router.message(F.text == "🔙 منوی اصلی")
async def back_to_main(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    from bot.keyboards import main_menu_keyboard
    await msg.answer("منوی اصلی 👇", reply_markup=main_menu_keyboard())


# ─── STATS ───────────────────────────────────────────────────────────────────
@router.message(F.text == "📊 آمار ربات")
async def stats(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    async with AsyncSessionLocal() as db:
        users = await crud.get_user_count(db)
        services = await crud.get_service_count(db)
    await msg.answer(
        f"📊 <b>آمار ربات</b>\n\n"
        f"👥 کاربران: <b>{users}</b>\n"
        f"📦 سرویس‌های فعال: <b>{services}</b>",
        parse_mode="HTML"
    )


# ─── BROADCAST ───────────────────────────────────────────────────────────────
@router.message(F.text == "📢 پیام همگانی")
async def broadcast_start(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return
    await state.set_state(BroadcastState.message)
    await msg.answer("📢 پیام خود را بنویسید (متن، عکس، ویدیو):\n\n/cancel برای انصراف")


@router.message(BroadcastState.message)
async def broadcast_send(msg: Message, state: FSMContext, bot: Bot):
    if not is_admin(msg.from_user.id):
        return
    await state.clear()
    async with AsyncSessionLocal() as db:
        users = await crud.get_all_active_users(db)
    sent = failed = 0
    for user in users:
        try:
            await msg.copy_to(user.telegram_id)
            sent += 1
        except Exception:
            failed += 1
    await msg.answer(f"✅ ارسال شد!\n📤 موفق: {sent}\n❌ ناموفق: {failed}")


# ─── PLANS ───────────────────────────────────────────────────────────────────
@router.message(F.text == "📦 مدیریت پلن‌ها")
async def manage_plans(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    async with AsyncSessionLocal() as db:
        plans = await crud.get_active_plans(db)
    await msg.answer(
        f"📦 <b>پلن‌های فعال ({len(plans)} عدد)</b>\nبرای حذف روی پلن کلیک کنید:",
        reply_markup=admin_plans_list_keyboard(plans),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "add_plan")
async def add_plan_start(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return
    await state.set_state(AddPlanState.name)
    await cb.message.edit_text("➕ <b>پلن جدید</b>\n\nنام پلن را وارد کنید:", parse_mode="HTML")


@router.message(AddPlanState.name)
async def plan_name(msg: Message, state: FSMContext):
    await state.update_data(name=msg.text.strip())
    await state.set_state(AddPlanState.traffic)
    await msg.answer("📊 حجم سرویس را به گیگابایت وارد کنید (مثال: 30):")


@router.message(AddPlanState.traffic)
async def plan_traffic(msg: Message, state: FSMContext):
    try:
        gb = int(msg.text.strip())
    except ValueError:
        await msg.answer("❌ عدد صحیح وارد کنید.")
        return
    await state.update_data(traffic=gb)
    await state.set_state(AddPlanState.days)
    await msg.answer("📅 مدت سرویس را به روز وارد کنید (مثال: 30):")


@router.message(AddPlanState.days)
async def plan_days(msg: Message, state: FSMContext):
    try:
        days = int(msg.text.strip())
    except ValueError:
        await msg.answer("❌ عدد صحیح وارد کنید.")
        return
    await state.update_data(days=days)
    await state.set_state(AddPlanState.price)
    await msg.answer("💰 قیمت پلن را به تومان وارد کنید (مثال: 120000):")


@router.message(AddPlanState.price)
async def plan_price(msg: Message, state: FSMContext):
    try:
        price = float(msg.text.replace(",", "").strip())
    except ValueError:
        await msg.answer("❌ عدد صحیح وارد کنید.")
        return
    data = await state.get_data()
    async with AsyncSessionLocal() as db:
        plan = await crud.create_plan(db, data["name"], data["traffic"], data["days"], price)
    await state.clear()
    await msg.answer(
        f"✅ <b>پلن ایجاد شد!</b>\n\n"
        f"📦 {plan.name}\n"
        f"📊 {plan.traffic_gb} GB | 📅 {plan.days} روز\n"
        f"💰 {int(plan.price):,} تومان",
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("del_plan:"))
async def del_plan(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return
    plan_id = int(cb.data.split(":")[1])
    async with AsyncSessionLocal() as db:
        await crud.disable_plan(db, plan_id)
        plans = await crud.get_active_plans(db)
    await cb.answer("✅ پلن حذف شد.")
    await cb.message.edit_text(
        f"📦 <b>پلن‌های فعال ({len(plans)} عدد)</b>:",
        reply_markup=admin_plans_list_keyboard(plans),
        parse_mode="HTML"
    )


# ─── DISCOUNT CODES ──────────────────────────────────────────────────────────
@router.message(F.text == "🏷 کدهای تخفیف")
async def manage_discounts(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    async with AsyncSessionLocal() as db:
        codes = await crud.get_all_discounts(db)
    await msg.answer(
        f"🏷 <b>کدهای تخفیف ({len(codes)} عدد)</b>\nبرای حذف روی کد کلیک کنید:",
        reply_markup=discounts_list_keyboard(codes),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "add_dc")
async def add_dc_start(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return
    await state.set_state(AddDiscountState.code)
    await cb.message.edit_text("🏷 <b>کد تخفیف جدید</b>\n\nکد را وارد کنید (مثال: SUMMER30):", parse_mode="HTML")


@router.message(AddDiscountState.code)
async def dc_code(msg: Message, state: FSMContext):
    code = msg.text.strip().upper()
    if len(code) < 3 or len(code) > 20:
        await msg.answer("❌ کد باید ۳ تا ۲۰ کاراکتر باشد.")
        return
    await state.update_data(code=code)
    await state.set_state(AddDiscountState.percent)
    await msg.answer("💸 درصد تخفیف را وارد کنید (مثال: 20 برای ۲۰٪):")


@router.message(AddDiscountState.percent)
async def dc_percent(msg: Message, state: FSMContext):
    try:
        pct = int(msg.text.strip())
        if not 1 <= pct <= 100:
            raise ValueError
    except ValueError:
        await msg.answer("❌ عدد بین ۱ تا ۱۰۰ وارد کنید.")
        return
    await state.update_data(percent=pct)
    await state.set_state(AddDiscountState.max_uses)
    await msg.answer("🔢 حداکثر تعداد استفاده را وارد کنید (مثال: 1 برای یک‌بار):")


@router.message(AddDiscountState.max_uses)
async def dc_max_uses(msg: Message, state: FSMContext):
    try:
        uses = int(msg.text.strip())
    except ValueError:
        await msg.answer("❌ عدد صحیح وارد کنید.")
        return
    data = await state.get_data()
    async with AsyncSessionLocal() as db:
        dc = await crud.create_discount(db, data["code"], data["percent"], uses)
    await state.clear()
    await msg.answer(
        f"✅ <b>کد تخفیف ایجاد شد!</b>\n\n"
        f"🏷 کد: <code>{dc.code}</code>\n"
        f"💸 تخفیف: {dc.percent}%\n"
        f"🔢 تعداد استفاده: {dc.max_uses} بار",
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("del_dc:"))
async def del_dc(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return
    dc_id = int(cb.data.split(":")[1])
    async with AsyncSessionLocal() as db:
        await crud.delete_discount(db, dc_id)
        codes = await crud.get_all_discounts(db)
    await cb.answer("✅ کد حذف شد.")
    await cb.message.edit_text(
        f"🏷 <b>کدهای تخفیف ({len(codes)} عدد)</b>:",
        reply_markup=discounts_list_keyboard(codes),
        parse_mode="HTML"
    )


# ─── PAYMENT APPROVAL ─────────────────────────────────────────────────────────
@router.message(F.text == "💳 تایید پرداخت‌ها")
async def pending_payments(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    async with AsyncSessionLocal() as db:
        payments = await crud.get_pending_card_payments(db)
    if not payments:
        await msg.answer("✅ هیچ پرداخت کارتی در انتظار تایید نیست.")
        return
    await msg.answer(f"💳 {len(payments)} پرداخت در انتظار تایید.\nدر پیام‌های قبلی تایید/رد کنید.")


@router.callback_query(F.data.startswith("approve_pay:"))
async def approve_pay(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id):
        return
    _, pay_id, user_tid = cb.data.split(":")
    pay_id, user_tid = int(pay_id), int(user_tid)
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        from database.db import Payment
        r = await db.execute(select(Payment).where(Payment.id == pay_id))
        pay = r.scalar_one_or_none()
        if not pay or pay.status != PaymentStatus.PENDING:
            await cb.answer("این پرداخت قبلاً پردازش شده!", show_alert=True)
            return
        pay.status = PaymentStatus.PAID
        user = await crud.get_user(db, user_tid)
        await crud.update_wallet(db, user, pay.amount, "شارژ کیف پول (کارت)", TransactionType.DEPOSIT)
    await cb.answer("✅ تایید شد!")
    await cb.message.edit_caption(
        cb.message.caption + f"\n\n✅ <b>تایید شد توسط ادمین</b>",
        parse_mode="HTML"
    )
    try:
        await bot.send_message(user_tid,
            f"✅ پرداخت شما تایید شد!\n💰 {int(pay.amount):,} تومان به کیف پول اضافه شد.")
    except Exception:
        pass


@router.callback_query(F.data.startswith("reject_pay:"))
async def reject_pay(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id):
        return
    _, pay_id, user_tid = cb.data.split(":")
    pay_id, user_tid = int(pay_id), int(user_tid)
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select
        from database.db import Payment
        r = await db.execute(select(Payment).where(Payment.id == pay_id))
        pay = r.scalar_one_or_none()
        if not pay:
            return
        pay.status = PaymentStatus.REJECTED
        await db.commit()
    await cb.answer("❌ رد شد.")
    await cb.message.edit_caption(cb.message.caption + "\n\n❌ <b>رد شد</b>", parse_mode="HTML")
    try:
        await bot.send_message(user_tid, "❌ پرداخت شما تایید نشد. با پشتیبانی تماس بگیرید.")
    except Exception:
        pass


# ─── LOTTERY ADMIN ───────────────────────────────────────────────────────────
@router.message(F.text == "🎰 قرعه‌کشی ادمین")
async def admin_lottery(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select, func
        from database.db import User
        r = await db.execute(
            select(func.count()).select_from(User).where(User.lottery_number.isnot(None))
        )
        count = r.scalar()
        is_active = await crud.get_setting(db, "lottery_active", "false")

    status = "🟢 فعال" if is_active == "true" else "🔴 غیرفعال"
    await msg.answer(
        f"🎰 <b>مدیریت قرعه‌کشی</b>\n\n"
        f"وضعیت: {status}\n"
        f"شرکت‌کنندگان: <b>{count} نفر</b>\n\n"
        f"برای انجام قرعه‌کشی، تعداد برنده را انتخاب کنید:",
        reply_markup=lottery_draw_keyboard(),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("draw:"))
async def do_draw(cb: CallbackQuery, bot: Bot):
    if not is_admin(cb.from_user.id):
        return
    count = int(cb.data.split(":")[1])
    async with AsyncSessionLocal() as db:
        winners = await crud.draw_lottery(db, count)
        await crud.set_setting(db, "lottery_active", "true")

    if not winners:
        await cb.answer("هیچ شرکت‌کننده‌ای وجود ندارد!", show_alert=True)
        return

    result_text = f"🎰 <b>نتیجه قرعه‌کشی</b>\n\n🏆 برنده‌ها ({len(winners)} نفر):\n\n"
    for i, w in enumerate(winners, 1):
        name = w.full_name or f"کاربر{w.telegram_id}"
        result_text += f"{i}. 🎫 شماره <b>{w.lottery_number}</b> — {name}\n"

    await cb.message.edit_text(result_text, parse_mode="HTML")

    # اعلام به همه کاربران
    async with AsyncSessionLocal() as db:
        all_users = await crud.get_all_active_users(db)
    winner_ids = {w.telegram_id for w in winners}
    for u in all_users:
        try:
            if u.telegram_id in winner_ids:
                await bot.send_message(u.telegram_id,
                    f"🎉🎊 تبریک! شماره قرعه‌کشی شما برنده شد!\n"
                    f"🎫 شماره: <b>{u.lottery_number}</b>\n\n"
                    f"با پشتیبانی تماس بگیرید تا جایزه خود را دریافت کنید.",
                    parse_mode="HTML")
            else:
                await bot.send_message(u.telegram_id,
                    f"🎰 قرعه‌کشی برگزار شد!\n"
                    f"متاسفانه این بار موفق نشدید.\n"
                    f"منتظر قرعه‌کشی بعدی باشید! 🍀")
        except Exception:
            pass


# ─── BOT SETTINGS ────────────────────────────────────────────────────────────
@router.message(F.text == "⚙️ تنظیمات ربات")
async def bot_settings(msg: Message):
    if not is_admin(msg.from_user.id):
        return
    async with AsyncSessionLocal() as db:
        reward = await crud.get_setting(db, "referral_reward", "50000")
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"🎊 پاداش دعوت: {int(reward):,} تومان — ویرایش",
            callback_data="edit_referral_reward"
        )],
    ])
    await msg.answer(
        f"⚙️ <b>تنظیمات ربات</b>\n\n"
        f"🎊 پاداش دعوت کاربر: <b>{int(reward):,} تومان</b>",
        reply_markup=kb, parse_mode="HTML"
    )


@router.callback_query(F.data == "edit_referral_reward")
async def edit_reward_start(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return
    await state.set_state(EditSettingState.referral_reward)
    await cb.message.edit_text(
        "🎊 مقدار جدید پاداش دعوت را به تومان وارد کنید (مثال: 50000):"
    )


@router.message(EditSettingState.referral_reward)
async def set_reward(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        return
    try:
        amount = int(msg.text.replace(",", "").strip())
        if amount < 0:
            raise ValueError
    except ValueError:
        await msg.answer("❌ عدد صحیح مثبت وارد کنید.")
        return
    async with AsyncSessionLocal() as db:
        await crud.set_setting(db, "referral_reward", str(amount))
    await state.clear()
    await msg.answer(f"✅ پاداش دعوت به <b>{amount:,} تومان</b> تغییر یافت.", parse_mode="HTML")


@router.callback_query(F.data == "admin_back")
async def admin_back(cb: CallbackQuery):
    try:
        await cb.message.delete()
    except Exception:
        pass
