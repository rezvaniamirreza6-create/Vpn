import json
import logging
import io
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from database.db import AsyncSessionLocal, TransactionType, UserStatus, PaymentStatus, PaymentMethod
from database import crud
from panels.sanei import panel
from bot.keyboards import (
    admin_plans_kb, admin_plan_detail_kb, admin_cats_kb, admin_cat_detail_kb,
    admin_settings_kb, lottery_admin_kb, admin_admins_kb, back_kb, payment_confirm_kb
)
from config import config

logger = logging.getLogger(__name__)
router = Router()

PERMISSIONS = ["payment", "broadcast", "plans", "stats", "lottery", "ban", "settings", "all"]
PERM_NAMES = {
    "payment": "✅ تایید پرداخت",
    "broadcast": "📢 پیام همگانی",
    "plans": "📦 مدیریت پلن‌ها",
    "stats": "📊 آمار",
    "lottery": "🏆 قرعه‌کشی",
    "ban": "🚫 بن کاربر",
    "settings": "⚙️ تنظیمات",
    "all": "🔑 همه دسترسی‌ها",
}


def admin_menu_kb() -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.row(KeyboardButton(text="📊 آمار ربات"), KeyboardButton(text="📢 پیام همگانی"))
    builder.row(KeyboardButton(text="📦 مدیریت پلن‌ها"), KeyboardButton(text="🗂 دسته‌بندی‌ها"))
    builder.row(KeyboardButton(text="💳 تایید پرداخت‌ها"), KeyboardButton(text="🏆 قرعه‌کشی"))
    builder.row(KeyboardButton(text="👥 مدیریت ادمین‌ها"), KeyboardButton(text="🚫 بن کاربر"))
    builder.row(KeyboardButton(text="⚙️ تنظیمات"), KeyboardButton(text="💾 بکاپ"))
    builder.row(KeyboardButton(text="💰 کسر/افزایش موجودی"), KeyboardButton(text="📢 کانال‌های اجباری"))
    builder.row(KeyboardButton(text="🔙 منوی اصلی"))
    return builder.as_markup(resize_keyboard=True)


async def is_admin(user_id: int, perm: str = None) -> bool:
    if user_id in config.ADMIN_IDS:
        return True
    async with AsyncSessionLocal() as db:
        admin = await crud.get_admin(db, user_id)
        if not admin:
            return False
        if perm:
            return crud.admin_has_perm(admin, perm)
        return True


class PlanState(StatesGroup):
    name = State()
    traffic = State()
    days = State()
    price = State()
    category = State()
    inbound = State()
    edit_field = State()
    edit_value = State()


class CatState(StatesGroup):
    name = State()
    icon = State()
    edit_name = State()
    sort_order = State()


class SettingState(StatesGroup):
    waiting_value = State()


class BanState(StatesGroup):
    waiting_id = State()


class AdjustState(StatesGroup):
    waiting_id = State()
    waiting_amount = State()


class BroadcastState(StatesGroup):
    waiting_msg = State()


class AdminAddState(StatesGroup):
    selecting_perms = State()
    waiting_id = State()


class ForceJoinState(StatesGroup):
    waiting_channel = State()


# ─── Admin check middleware ───────────────────────────────────────────────────

@router.message(F.text == "🔙 منوی اصلی")
async def back_main(msg: Message):
    from bot.handlers.user import main_menu_kb
    async with AsyncSessionLocal() as db:
        settings = await crud.get_all_settings(db)
    from bot.keyboards import main_menu_kb as mk
    await msg.answer("منوی اصلی 🏠", reply_markup=mk(settings))


# ─── STATS ───────────────────────────────────────────────────────────────────

@router.message(F.text == "📊 آمار ربات")
async def admin_stats(msg: Message):
    if not await is_admin(msg.from_user.id, "stats"):
        return
    async with AsyncSessionLocal() as db:
        total_users = await crud.get_user_count(db)
        total_services = await crud.get_service_count(db)
        pending = await crud.get_pending_card_payments(db)
        participants = await crud.get_lottery_participants_count(db)
    await msg.answer(
        f"📊 <b>آمار ربات</b>\n\n"
        f"👥 کاربران: <b>{total_users}</b>\n"
        f"📦 سرویس‌های فعال: <b>{total_services}</b>\n"
        f"💳 پرداخت‌های در انتظار: <b>{len(pending)}</b>\n"
        f"🏆 شرکت‌کنندگان قرعه‌کشی: <b>{participants}</b>",
        parse_mode="HTML"
    )


# ─── BROADCAST ───────────────────────────────────────────────────────────────

@router.message(F.text == "📢 پیام همگانی")
async def broadcast_start(msg: Message, state: FSMContext):
    if not await is_admin(msg.from_user.id, "broadcast"):
        return
    await state.set_state(BroadcastState.waiting_msg)
    await msg.answer("📢 پیام همگانی را ارسال کنید (متن، عکس، ویدیو):", reply_markup=back_kb("cancel"))


@router.message(BroadcastState.waiting_msg)
async def do_broadcast(msg: Message, state: FSMContext):
    await state.clear()
    async with AsyncSessionLocal() as db:
        users = await crud.get_all_active_users(db)
    sent = 0
    for user in users:
        try:
            await msg.copy_to(user.telegram_id)
            sent += 1
        except Exception:
            pass
    await msg.answer(f"✅ پیام به {sent} کاربر ارسال شد.")


# ─── PLANS ───────────────────────────────────────────────────────────────────

@router.message(F.text == "📦 مدیریت پلن‌ها")
async def admin_plans(msg: Message):
    if not await is_admin(msg.from_user.id, "plans"):
        return
    async with AsyncSessionLocal() as db:
        plans = await crud.get_all_plans(db)
    await msg.answer("📦 <b>مدیریت پلن‌ها</b>", reply_markup=admin_plans_kb(plans), parse_mode="HTML")


@router.callback_query(F.data == "admin_plans")
async def admin_plans_cb(cb: CallbackQuery):
    async with AsyncSessionLocal() as db:
        plans = await crud.get_all_plans(db)
    await cb.message.edit_text("📦 <b>مدیریت پلن‌ها</b>", reply_markup=admin_plans_kb(plans), parse_mode="HTML")


@router.callback_query(F.data.startswith("aplan:"))
async def plan_detail(cb: CallbackQuery):
    plan_id = int(cb.data.split(":")[1])
    async with AsyncSessionLocal() as db:
        plan = await crud.get_plan(db, plan_id)
        cat_name = "بدون دسته‌بندی"
        if plan.category_id:
            cat = await crud.get_category(db, plan.category_id)
            cat_name = cat.name if cat else "—"
    status = "✅ فعال" if plan.is_active else "❌ غیرفعال"
    await cb.message.edit_text(
        f"📦 <b>{plan.name}</b>\n\n"
        f"📊 حجم: {plan.traffic_gb} GB\n"
        f"📅 مدت: {plan.days} روز\n"
        f"💰 قیمت: {int(plan.price):,} تومان\n"
        f"🗂 دسته: {cat_name}\n"
        f"🔢 Inbound: {plan.inbound_id or 'پیش‌فرض'}\n"
        f"📶 وضعیت: {status}\n"
        f"🔢 ترتیب: {plan.sort_order}",
        reply_markup=admin_plan_detail_kb(plan_id),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "add_plan")
async def add_plan_start(cb: CallbackQuery, state: FSMContext):
    await state.set_state(PlanState.name)
    await cb.message.edit_text("📦 نام پلن را وارد کنید:", reply_markup=back_kb("admin_plans"))


@router.message(PlanState.name)
async def plan_name(msg: Message, state: FSMContext):
    await state.update_data(name=msg.text.strip())
    await state.set_state(PlanState.traffic)
    await msg.answer("📊 حجم (GB) را وارد کنید:", reply_markup=back_kb("admin_plans"))


@router.message(PlanState.traffic)
async def plan_traffic(msg: Message, state: FSMContext):
    try:
        gb = int(msg.text.strip())
    except ValueError:
        await msg.answer("❌ عدد صحیح وارد کنید.")
        return
    await state.update_data(traffic=gb)
    await state.set_state(PlanState.days)
    await msg.answer("📅 تعداد روز را وارد کنید:")


@router.message(PlanState.days)
async def plan_days(msg: Message, state: FSMContext):
    try:
        days = int(msg.text.strip())
    except ValueError:
        await msg.answer("❌ عدد صحیح وارد کنید.")
        return
    await state.update_data(days=days)
    await state.set_state(PlanState.price)
    await msg.answer("💰 قیمت (تومان) را وارد کنید:")


@router.message(PlanState.price)
async def plan_price(msg: Message, state: FSMContext):
    try:
        price = float(msg.text.replace(",", "").strip())
    except ValueError:
        await msg.answer("❌ عدد صحیح وارد کنید.")
        return
    await state.update_data(price=price)
    await state.set_state(PlanState.category)
    async with AsyncSessionLocal() as db:
        cats = await crud.get_all_categories(db)
    builder = InlineKeyboardBuilder()
    for cat in cats:
        builder.row(InlineKeyboardButton(text=f"{cat.icon} {cat.name}", callback_data=f"plan_cat:{cat.id}"))
    builder.row(InlineKeyboardButton(text="بدون دسته‌بندی", callback_data="plan_cat:0"))
    await msg.answer("🗂 دسته‌بندی را انتخاب کنید:", reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("plan_cat:"))
async def plan_category(cb: CallbackQuery, state: FSMContext):
    cat_id = int(cb.data.split(":")[1])
    await state.update_data(category_id=cat_id if cat_id else None)
    await state.set_state(PlanState.inbound)
    await cb.message.edit_text("🔢 شماره Inbound را وارد کنید (Enter برای پیش‌فرض):")


@router.message(PlanState.inbound)
async def plan_inbound(msg: Message, state: FSMContext):
    text = msg.text.strip()
    inbound_id = int(text) if text.isdigit() else None
    data = await state.get_data()
    await state.clear()
    async with AsyncSessionLocal() as db:
        plan = await crud.create_plan(
            db, data["name"], data["traffic"], data["days"], data["price"],
            category_id=data.get("category_id"), inbound_id=inbound_id
        )
    await msg.answer(f"✅ پلن «{plan.name}» ساخته شد!")


@router.callback_query(F.data.startswith("edit_plan:"))
async def edit_plan_start(cb: CallbackQuery, state: FSMContext):
    plan_id = int(cb.data.split(":")[1])
    await state.update_data(plan_id=plan_id)
    await state.set_state(PlanState.edit_field)
    builder = InlineKeyboardBuilder()
    fields = [("نام", "name"), ("حجم GB", "traffic_gb"), ("روز", "days"), ("قیمت", "price"), ("ترتیب", "sort_order")]
    for label, field in fields:
        builder.row(InlineKeyboardButton(text=label, callback_data=f"ef:{field}"))
    builder.row(InlineKeyboardButton(text="فعال/غیرفعال", callback_data="ef:toggle"))
    await cb.message.edit_text("✏️ کدام فیلد را ویرایش کنید?", reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("ef:"))
async def edit_field_select(cb: CallbackQuery, state: FSMContext):
    field = cb.data.split(":")[1]
    if field == "toggle":
        data = await state.get_data()
        plan_id = data["plan_id"]
        async with AsyncSessionLocal() as db:
            plan = await crud.get_plan(db, plan_id)
            await crud.update_plan(db, plan_id, is_active=not plan.is_active)
        await state.clear()
        await cb.message.edit_text(f"✅ وضعیت پلن تغییر کرد.")
        return
    await state.update_data(edit_field=field)
    await state.set_state(PlanState.edit_value)
    await cb.message.edit_text(f"✏️ مقدار جدید برای {field} را وارد کنید:")


@router.message(PlanState.edit_value)
async def edit_plan_value(msg: Message, state: FSMContext):
    data = await state.get_data()
    plan_id = data["plan_id"]
    field = data["edit_field"]
    val = msg.text.strip()
    try:
        if field in ("traffic_gb", "days", "sort_order"):
            val = int(val)
        elif field == "price":
            val = float(val.replace(",", ""))
    except ValueError:
        await msg.answer("❌ مقدار نامعتبر.")
        return
    async with AsyncSessionLocal() as db:
        await crud.update_plan(db, plan_id, **{field: val})
    await state.clear()
    await msg.answer(f"✅ پلن بروزرسانی شد.")


@router.callback_query(F.data.startswith("sort_plan:"))
async def sort_plan(cb: CallbackQuery, state: FSMContext):
    plan_id = int(cb.data.split(":")[1])
    await state.update_data(plan_id=plan_id, edit_field="sort_order")
    await state.set_state(PlanState.edit_value)
    await cb.message.edit_text("🔢 ترتیب جدید (عدد کمتر = اول):")


@router.callback_query(F.data.startswith("del_plan:"))
async def del_plan(cb: CallbackQuery):
    plan_id = int(cb.data.split(":")[1])
    async with AsyncSessionLocal() as db:
        await crud.delete_plan(db, plan_id)
    await cb.message.edit_text("🗑 پلن حذف شد.")


# ─── CATEGORIES ──────────────────────────────────────────────────────────────

@router.message(F.text == "🗂 دسته‌بندی‌ها")
async def admin_cats(msg: Message):
    if not await is_admin(msg.from_user.id, "plans"):
        return
    async with AsyncSessionLocal() as db:
        cats = await crud.get_all_categories(db)
    await msg.answer("🗂 <b>دسته‌بندی‌ها</b>", reply_markup=admin_cats_kb(cats), parse_mode="HTML")


@router.callback_query(F.data == "admin_cats")
async def admin_cats_cb(cb: CallbackQuery):
    async with AsyncSessionLocal() as db:
        cats = await crud.get_all_categories(db)
    await cb.message.edit_text("🗂 <b>دسته‌بندی‌ها</b>", reply_markup=admin_cats_kb(cats), parse_mode="HTML")


@router.callback_query(F.data == "add_cat")
async def add_cat_start(cb: CallbackQuery, state: FSMContext):
    await state.set_state(CatState.name)
    await cb.message.edit_text("🗂 نام دسته‌بندی را وارد کنید:")


@router.message(CatState.name)
async def cat_name(msg: Message, state: FSMContext):
    await state.update_data(name=msg.text.strip())
    await state.set_state(CatState.icon)
    await msg.answer("📌 ایموجی دسته‌بندی را وارد کنید (مثلاً 🎮):")


@router.message(CatState.icon)
async def cat_icon(msg: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    async with AsyncSessionLocal() as db:
        cat = await crud.create_category(db, data["name"], msg.text.strip())
    await msg.answer(f"✅ دسته‌بندی «{cat.icon} {cat.name}» ساخته شد!")


@router.callback_query(F.data.startswith("acat:"))
async def cat_detail(cb: CallbackQuery):
    cat_id = int(cb.data.split(":")[1])
    async with AsyncSessionLocal() as db:
        cat = await crud.get_category(db, cat_id)
        plans = await crud.get_active_plans(db, category_id=cat_id)
    status = "✅ فعال" if cat.is_active else "❌ غیرفعال"
    await cb.message.edit_text(
        f"{cat.icon} <b>{cat.name}</b>\n\n"
        f"📦 تعداد پلن: {len(plans)}\n"
        f"🔢 ترتیب: {cat.sort_order}\n"
        f"📶 وضعیت: {status}",
        reply_markup=admin_cat_detail_kb(cat_id),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("edit_cat:"))
async def edit_cat(cb: CallbackQuery, state: FSMContext):
    cat_id = int(cb.data.split(":")[1])
    await state.update_data(cat_id=cat_id)
    await state.set_state(CatState.edit_name)
    await cb.message.edit_text("✏️ نام جدید دسته‌بندی را وارد کنید:")


@router.message(CatState.edit_name)
async def do_edit_cat(msg: Message, state: FSMContext):
    data = await state.get_data()
    async with AsyncSessionLocal() as db:
        await crud.update_category(db, data["cat_id"], name=msg.text.strip())
    await state.clear()
    await msg.answer("✅ نام دسته‌بندی بروزرسانی شد.")


@router.callback_query(F.data.startswith("sort_cat:"))
async def sort_cat(cb: CallbackQuery, state: FSMContext):
    cat_id = int(cb.data.split(":")[1])
    await state.update_data(cat_id=cat_id)
    await state.set_state(CatState.sort_order)
    await cb.message.edit_text("🔢 ترتیب جدید (عدد کمتر = اول) را وارد کنید:")


@router.message(CatState.sort_order)
async def do_sort_cat(msg: Message, state: FSMContext):
    data = await state.get_data()
    try:
        order = int(msg.text.strip())
    except ValueError:
        await msg.answer("❌ عدد صحیح وارد کنید.")
        return
    async with AsyncSessionLocal() as db:
        await crud.update_category(db, data["cat_id"], sort_order=order)
    await state.clear()
    await msg.answer("✅ ترتیب بروزرسانی شد.")


@router.callback_query(F.data.startswith("del_cat:"))
async def del_cat(cb: CallbackQuery):
    cat_id = int(cb.data.split(":")[1])
    async with AsyncSessionLocal() as db:
        await crud.delete_category(db, cat_id)
    await cb.message.edit_text("🗑 دسته‌بندی حذف شد.")


# ─── PAYMENTS ────────────────────────────────────────────────────────────────

@router.message(F.text == "💳 تایید پرداخت‌ها")
async def pending_payments(msg: Message):
    if not await is_admin(msg.from_user.id, "payment"):
        return
    async with AsyncSessionLocal() as db:
        payments = await crud.get_pending_card_payments(db)
    if not payments:
        await msg.answer("✅ پرداخت در انتظاری وجود ندارد.")
        return
    for pay in payments:
        await msg.bot.send_photo(
            msg.chat.id,
            pay.receipt_file_id,
            caption=(
                f"💳 <b>پرداخت #{pay.id}</b>\n\n"
                f"👤 {pay.user.full_name} (@{pay.user.username or '-'})\n"
                f"🆔 <code>{pay.user.telegram_id}</code>\n"
                f"💰 {int(pay.amount):,} تومان\n"
                f"📅 {pay.created_at.strftime('%Y/%m/%d %H:%M')}"
            ),
            reply_markup=payment_confirm_kb(pay.id, pay.user.telegram_id),
            parse_mode="HTML"
        )


@router.callback_query(F.data.startswith("pay_ok:"))
async def confirm_payment(cb: CallbackQuery):
    parts = cb.data.split(":")
    pay_id, user_tid = int(parts[1]), int(parts[2])
    async with AsyncSessionLocal() as db:
        pay = await crud.get_payment(db, pay_id)
        if not pay or pay.status != PaymentStatus.PENDING:
            await cb.answer("قبلاً پردازش شده.", show_alert=True)
            return
        pay.status = PaymentStatus.PAID
        user = pay.user
        await crud.update_wallet(db, user, pay.amount, f"شارژ تایید شده #{pay_id}", TransactionType.DEPOSIT)
        await db.commit()
    await cb.message.edit_caption(f"✅ تأیید شد - {int(pay.amount):,} تومان")
    try:
        await cb.bot.send_message(user_tid, f"✅ پرداخت شما تأیید شد!\n💰 {int(pay.amount):,} تومان به کیف پول شما اضافه شد.")
    except Exception:
        pass


@router.callback_query(F.data.startswith("pay_rej:"))
async def reject_payment(cb: CallbackQuery):
    parts = cb.data.split(":")
    pay_id, user_tid = int(parts[1]), int(parts[2])
    async with AsyncSessionLocal() as db:
        pay = await crud.get_payment(db, pay_id)
        if not pay:
            await cb.answer("یافت نشد.", show_alert=True)
            return
        pay.status = PaymentStatus.REJECTED
        await db.commit()
    await cb.message.edit_caption("❌ رد شد")
    try:
        await cb.bot.send_message(user_tid, "❌ پرداخت شما تأیید نشد. لطفاً با پشتیبانی تماس بگیرید.")
    except Exception:
        pass


# ─── LOTTERY ─────────────────────────────────────────────────────────────────

@router.message(F.text == "🏆 قرعه‌کشی")
async def lottery_admin(msg: Message):
    if not await is_admin(msg.from_user.id, "lottery"):
        return
    async with AsyncSessionLocal() as db:
        is_active = await crud.get_setting(db, "lottery_active", "false")
        count = await crud.get_lottery_participants_count(db)
    await msg.answer(
        f"🏆 <b>مدیریت قرعه‌کشی</b>\n\n"
        f"وضعیت: {'🟢 فعال' if is_active == 'true' else '🔴 غیرفعال'}\n"
        f"👥 شرکت‌کنندگان: {count} نفر",
        reply_markup=lottery_admin_kb(is_active == "true"),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "toggle_lottery")
async def toggle_lottery(cb: CallbackQuery):
    async with AsyncSessionLocal() as db:
        current = await crud.get_setting(db, "lottery_active", "false")
        new_val = "false" if current == "true" else "true"
        await crud.set_setting(db, "lottery_active", new_val)
        count = await crud.get_lottery_participants_count(db)
        auto_send = await crud.get_setting(db, "lottery_auto_send", "true")
        bot_name = await crud.get_setting(db, "bot_name", "VPN")
        if new_val == "true":
            users = await crud.get_all_active_users(db)

    if new_val == "true":
        sent = 0
        for user in users:
            try:
                num = await _get_user_lottery_num(user.telegram_id)
                await cb.bot.send_message(
                    user.telegram_id,
                    f"🎊 <b>قرعه‌کشی {bot_name} شروع شد!</b>\n\n"
                    f"🎫 شماره شانس شما: <b>{num}</b>\n\n"
                    f"برای شرکت در قرعه‌کشی به ربات مراجعه کنید.",
                    parse_mode="HTML"
                )
                sent += 1
            except Exception:
                pass
        await cb.message.edit_text(f"🟢 قرعه‌کشی فعال شد! پیام به {sent} کاربر ارسال شد.")
    else:
        await cb.message.edit_text("🔴 قرعه‌کشی غیرفعال شد.")


async def _get_user_lottery_num(tid: int) -> int:
    async with AsyncSessionLocal() as db:
        user = await crud.get_user(db, tid)
        if user:
            return await crud.get_or_create_lottery_number(db, user)
    return 0


@router.callback_query(F.data == "lottery_stats")
async def lottery_stats(cb: CallbackQuery):
    async with AsyncSessionLocal() as db:
        count = await crud.get_lottery_participants_count(db)
    await cb.answer(f"👥 {count} نفر شرکت کرده‌اند.", show_alert=True)


@router.callback_query(F.data == "do_lottery")
async def do_lottery(cb: CallbackQuery):
    async with AsyncSessionLocal() as db:
        winners = await crud.draw_lottery(db, count=1)
        auto_send = await crud.get_setting(db, "lottery_auto_send", "true")
        prize_gb = int(await crud.get_setting(db, "lottery_prize_gb", "10"))
        prize_days = int(await crud.get_setting(db, "lottery_prize_days", "30"))
        inbound_id = int(await crud.get_setting(db, "inbound_id", "1"))
        panel_url = await crud.get_setting(db, "panel_url", "")
        panel_path = await crud.get_setting(db, "panel_path", "")

    if not winners:
        await cb.answer("شرکت‌کننده‌ای وجود ندارد!", show_alert=True)
        return
    winner = winners[0]
    await cb.message.answer(
        f"🎊 <b>برنده قرعه‌کشی:</b>\n\n"
        f"👤 {winner.full_name}\n"
        f"🆔 <code>{winner.telegram_id}</code>\n"
        f"🎫 شماره: {winner.lottery_number}",
        parse_mode="HTML"
    )
    if auto_send == "true":
        import random, string
        email = f"prize{winner.telegram_id}{''.join(random.choices(string.ascii_lowercase, k=4))}"
        result = await panel.add_client(inbound_id, email, prize_gb, prize_days)
        if result:
            async with AsyncSessionLocal() as db:
                sub_link = panel.get_subscription_url(panel_url, panel_path, email)
                await crud.create_service(db, winner.id, None, result["uuid"], email,
                    inbound_id, prize_gb, prize_days, sub_link=sub_link)
            try:
                await cb.bot.send_message(
                    winner.telegram_id,
                    f"🎊 <b>تبریک! شما برنده قرعه‌کشی شدید!</b>\n\n"
                    f"🎁 جایزه: {prize_gb}GB - {prize_days} روز\n\n"
                    f"🔗 <b>لینک سرویس:</b>\n<code>{sub_link}</code>",
                    parse_mode="HTML"
                )
            except Exception:
                pass
    else:
        builder = InlineKeyboardBuilder()
        builder.row(InlineKeyboardButton(text="📨 ارسال سرویس به برنده", callback_data=f"send_prize:{winner.telegram_id}"))
        await cb.message.answer("⚠️ ارسال خودکار غیرفعال است. دستی ارسال کنید:", reply_markup=builder.as_markup())


# ─── BAN ─────────────────────────────────────────────────────────────────────

@router.message(F.text == "🚫 بن کاربر")
async def ban_start(msg: Message, state: FSMContext):
    if not await is_admin(msg.from_user.id, "ban"):
        return
    await state.set_state(BanState.waiting_id)
    await msg.answer("🆔 آیدی عددی کاربر را وارد کنید:", reply_markup=back_kb("cancel"))


@router.message(BanState.waiting_id)
async def do_ban(msg: Message, state: FSMContext):
    try:
        tid = int(msg.text.strip())
    except ValueError:
        await msg.answer("❌ آیدی عددی وارد کنید.")
        return
    async with AsyncSessionLocal() as db:
        user = await crud.get_user(db, tid)
        if not user:
            await msg.answer("❌ کاربر یافت نشد.")
            return
        if user.status == UserStatus.BANNED:
            await crud.unban_user(db, tid)
            await msg.answer(f"✅ کاربر {user.full_name} از بن خارج شد.")
        else:
            await crud.ban_user(db, tid)
            await msg.answer(f"🚫 کاربر {user.full_name} بن شد.")
    await state.clear()


# ─── ADJUST WALLET ────────────────────────────────────────────────────────────

@router.message(F.text == "💰 کسر/افزایش موجودی")
async def adjust_start(msg: Message, state: FSMContext):
    if not await is_admin(msg.from_user.id):
        return
    await state.set_state(AdjustState.waiting_id)
    await msg.answer("🆔 آیدی عددی کاربر را وارد کنید:", reply_markup=back_kb("cancel"))


@router.message(AdjustState.waiting_id)
async def adjust_id(msg: Message, state: FSMContext):
    try:
        tid = int(msg.text.strip())
    except ValueError:
        await msg.answer("❌ آیدی عددی وارد کنید.")
        return
    async with AsyncSessionLocal() as db:
        user = await crud.get_user(db, tid)
    if not user:
        await msg.answer("❌ کاربر یافت نشد.")
        return
    await state.update_data(tid=tid)
    await state.set_state(AdjustState.waiting_amount)
    await msg.answer(
        f"👤 کاربر: {user.full_name}\n💰 موجودی: {int(user.wallet):,} تومان\n\n"
        f"مقدار تغییر را وارد کنید (مثبت = افزایش، منفی = کسر):"
    )


@router.message(AdjustState.waiting_amount)
async def do_adjust(msg: Message, state: FSMContext):
    data = await state.get_data()
    try:
        amount = float(msg.text.replace(",", "").strip())
    except ValueError:
        await msg.answer("❌ عدد وارد کنید.")
        return
    async with AsyncSessionLocal() as db:
        user = await crud.get_user(db, data["tid"])
        await crud.update_wallet(db, user, amount, f"تنظیم دستی توسط ادمین", TransactionType.ADJUST)
        new_bal = user.wallet + amount
    await state.clear()
    action = "افزایش" if amount > 0 else "کسر"
    await msg.answer(f"✅ {abs(int(amount)):,} تومان {action} یافت.\nموجودی جدید: {int(new_bal):,} تومان")
    try:
        await msg.bot.send_message(
            data["tid"],
            f"{'💰 موجودی شما افزایش یافت' if amount > 0 else '💸 موجودی شما کسر شد'}!\n"
            f"مقدار: {abs(int(amount)):,} تومان"
        )
    except Exception:
        pass


# ─── FORCE JOIN ──────────────────────────────────────────────────────────────

@router.message(F.text == "📢 کانال‌های اجباری")
async def force_join_admin(msg: Message):
    if not await is_admin(msg.from_user.id, "settings"):
        return
    async with AsyncSessionLocal() as db:
        channels = await crud.get_all_force_joins(db)
        enabled = await crud.get_setting(db, "force_join_enabled", "false")
    builder = InlineKeyboardBuilder()
    for ch in channels:
        status = "✅" if ch.is_active else "❌"
        builder.row(InlineKeyboardButton(
            text=f"{status} {ch.channel_name or ch.channel_id}",
            callback_data=f"del_fj:{ch.id}"
        ))
    toggle = "🔴 غیرفعال کردن" if enabled == "true" else "🟢 فعال کردن"
    builder.row(InlineKeyboardButton(text=toggle, callback_data="toggle_fj"))
    builder.row(InlineKeyboardButton(text="➕ افزودن کانال", callback_data="add_fj"))
    await msg.answer(
        f"📢 <b>کانال‌های اجباری</b>\n\nوضعیت: {'🟢 فعال' if enabled == 'true' else '🔴 غیرفعال'}",
        reply_markup=builder.as_markup(), parse_mode="HTML"
    )


@router.callback_query(F.data == "toggle_fj")
async def toggle_fj(cb: CallbackQuery):
    async with AsyncSessionLocal() as db:
        current = await crud.get_setting(db, "force_join_enabled", "false")
        await crud.set_setting(db, "force_join_enabled", "false" if current == "true" else "true")
    await cb.answer("✅ تغییر یافت.")


@router.callback_query(F.data == "add_fj")
async def add_fj_start(cb: CallbackQuery, state: FSMContext):
    await state.set_state(ForceJoinState.waiting_channel)
    await cb.message.edit_text(
        "📢 آیدی کانال را وارد کنید (مثلاً @mychannel یا -100123456789):"
    )


@router.message(ForceJoinState.waiting_channel)
async def do_add_fj(msg: Message, state: FSMContext):
    channel_id = msg.text.strip()
    try:
        chat = await msg.bot.get_chat(channel_id)
        name = chat.title or channel_id
        invite = await msg.bot.export_chat_invite_link(chat.id)
    except Exception:
        name = channel_id
        invite = None
    async with AsyncSessionLocal() as db:
        await crud.add_force_join(db, channel_id, name, invite)
    await state.clear()
    await msg.answer(f"✅ کانال «{name}» اضافه شد.")


@router.callback_query(F.data.startswith("del_fj:"))
async def del_fj(cb: CallbackQuery):
    fj_id = int(cb.data.split(":")[1])
    async with AsyncSessionLocal() as db:
        await crud.remove_force_join(db, fj_id)
    await cb.answer("🗑 کانال حذف شد.")


# ─── SETTINGS ────────────────────────────────────────────────────────────────

@router.message(F.text == "⚙️ تنظیمات")
async def admin_settings(msg: Message):
    if not await is_admin(msg.from_user.id, "settings"):
        return
    await msg.answer("⚙️ <b>تنظیمات ربات</b>", reply_markup=admin_settings_kb(), parse_mode="HTML")


SETTING_MAP = {
    "set_card": ("card_number", "💳 شماره کارت جدید:"),
    "set_botname": ("bot_name", "🤖 نام ربات:"),
    "set_support": ("support_username", "📞 یوزرنیم پشتیبانی (بدون @):"),
    "set_referral": ("referral_reward", "💰 مبلغ پاداش دعوت (تومان):"),
    "set_zarinpal": ("zarinpal_merchant", "🏦 Merchant ID زرین‌پال:"),
    "set_inbound": ("inbound_id", "🔢 شماره Inbound پیش‌فرض:"),
}


@router.callback_query(F.data.startswith("set_"))
async def setting_start(cb: CallbackQuery, state: FSMContext):
    key_cb = cb.data
    if key_cb in SETTING_MAP:
        setting_key, prompt = SETTING_MAP[key_cb]
        await state.set_state(SettingState.waiting_value)
        await state.update_data(setting_key=setting_key)
        await cb.message.edit_text(prompt, reply_markup=back_kb("cancel"))
    elif key_cb == "set_card":
        await state.set_state(SettingState.waiting_value)
        await state.update_data(setting_key="card_number")
        await cb.message.edit_text("💳 شماره کارت جدید:", reply_markup=back_kb("cancel"))
    elif key_cb == "set_test":
        await cb.message.edit_text(
            "🎁 تنظیمات تست رایگان:\nمقدار را به صورت: MB/روز وارد کنید\nمثال: 500/1",
            reply_markup=back_kb("cancel")
        )
        await state.set_state(SettingState.waiting_value)
        await state.update_data(setting_key="test_config")
    elif key_cb == "set_panel":
        await cb.message.edit_text(
            "🔗 اطلاعات پنل را وارد کنید:\nURL|USERNAME|PASSWORD|PATH\nمثال: https://1.2.3.4:8080|admin|pass|rGkKcl",
            reply_markup=back_kb("cancel")
        )
        await state.set_state(SettingState.waiting_value)
        await state.update_data(setting_key="panel_config")


@router.message(SettingState.waiting_value)
async def save_setting(msg: Message, state: FSMContext):
    data = await state.get_data()
    key = data["setting_key"]
    val = msg.text.strip()
    await state.clear()
    async with AsyncSessionLocal() as db:
        if key == "test_config":
            parts = val.split("/")
            if len(parts) == 2:
                await crud.set_setting(db, "free_test_traffic_mb", parts[0])
                await crud.set_setting(db, "free_test_days", parts[1])
                await msg.answer(f"✅ تست: {parts[0]}MB / {parts[1]} روز")
            return
        elif key == "panel_config":
            parts = val.split("|")
            if len(parts) >= 3:
                await crud.set_setting(db, "panel_url", parts[0])
                await crud.set_setting(db, "panel_username", parts[1])
                await crud.set_setting(db, "panel_password", parts[2])
                if len(parts) > 3:
                    await crud.set_setting(db, "panel_path", parts[3])
                from panels.sanei import panel
                panel._logged_in = False
                await msg.answer("✅ پنل تنظیم شد.")
            return
        await crud.set_setting(db, key, val)
    await msg.answer(f"✅ تنظیم ذخیره شد.")


@router.callback_query(F.data == "toggle_auto_config")
async def toggle_auto_config(cb: CallbackQuery):
    async with AsyncSessionLocal() as db:
        current = await crud.get_setting(db, "auto_config_send", "true")
        new_val = "false" if current == "true" else "true"
        await crud.set_setting(db, "auto_config_send", new_val)
    status = "فعال" if new_val == "true" else "غیرفعال"
    await cb.answer(f"ارسال خودکار کانفیگ: {status}", show_alert=True)


@router.callback_query(F.data == "toggle_lottery_auto")
async def toggle_lottery_auto(cb: CallbackQuery):
    async with AsyncSessionLocal() as db:
        current = await crud.get_setting(db, "lottery_auto_send", "true")
        new_val = "false" if current == "true" else "true"
        await crud.set_setting(db, "lottery_auto_send", new_val)
    status = "فعال" if new_val == "true" else "غیرفعال"
    await cb.answer(f"ارسال خودکار جایزه: {status}", show_alert=True)


# ─── ADMINS ──────────────────────────────────────────────────────────────────

@router.message(F.text == "👥 مدیریت ادمین‌ها")
async def manage_admins(msg: Message):
    if msg.from_user.id not in config.ADMIN_IDS:
        return
    async with AsyncSessionLocal() as db:
        admins = await crud.get_all_admins(db)
    await msg.answer("👥 <b>ادمین‌ها</b>", reply_markup=admin_admins_kb(admins), parse_mode="HTML")


@router.callback_query(F.data == "add_admin")
async def add_admin_start(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id not in config.ADMIN_IDS:
        return
    builder = InlineKeyboardBuilder()
    for perm, name in PERM_NAMES.items():
        builder.row(InlineKeyboardButton(text=f"☐ {name}", callback_data=f"perm:{perm}"))
    builder.row(InlineKeyboardButton(text="✅ تأیید دسترسی‌ها", callback_data="perms_done"))
    await state.set_state(AdminAddState.selecting_perms)
    await state.update_data(selected_perms=[])
    await cb.message.edit_text("🔑 دسترسی‌های ادمین را انتخاب کنید:", reply_markup=builder.as_markup())


@router.callback_query(F.data.startswith("perm:"), AdminAddState.selecting_perms)
async def toggle_perm(cb: CallbackQuery, state: FSMContext):
    perm = cb.data.split(":")[1]
    data = await state.get_data()
    perms = data.get("selected_perms", [])
    if perm in perms:
        perms.remove(perm)
    else:
        perms.append(perm)
    await state.update_data(selected_perms=perms)
    builder = InlineKeyboardBuilder()
    for p, name in PERM_NAMES.items():
        check = "✅" if p in perms else "☐"
        builder.row(InlineKeyboardButton(text=f"{check} {name}", callback_data=f"perm:{p}"))
    builder.row(InlineKeyboardButton(text="✅ تأیید", callback_data="perms_done"))
    await cb.message.edit_reply_markup(reply_markup=builder.as_markup())


@router.callback_query(F.data == "perms_done", AdminAddState.selecting_perms)
async def perms_done(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AdminAddState.waiting_id)
    await cb.message.edit_text("🆔 آیدی عددی ادمین جدید را وارد کنید:")


@router.message(AdminAddState.waiting_id)
async def do_add_admin(msg: Message, state: FSMContext):
    try:
        tid = int(msg.text.strip())
    except ValueError:
        await msg.answer("❌ آیدی عددی وارد کنید.")
        return
    data = await state.get_data()
    perms = data.get("selected_perms", [])
    async with AsyncSessionLocal() as db:
        user = await crud.get_user(db, tid)
        name = user.full_name if user else str(tid)
        await crud.add_admin(db, tid, name, perms, msg.from_user.id)
    await state.clear()
    await msg.answer(f"✅ ادمین جدید اضافه شد.\n🆔 {tid}\n🔑 دسترسی‌ها: {', '.join([PERM_NAMES.get(p, p) for p in perms])}")


@router.callback_query(F.data.startswith("admin_detail:"))
async def admin_detail(cb: CallbackQuery):
    if cb.from_user.id not in config.ADMIN_IDS:
        return
    tid = int(cb.data.split(":")[1])
    async with AsyncSessionLocal() as db:
        admin = await crud.get_admin(db, tid)
    if not admin:
        await cb.answer("یافت نشد!", show_alert=True)
        return
    perms = json.loads(admin.permissions or "[]")
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🗑 حذف ادمین", callback_data=f"del_admin:{tid}"))
    builder.row(InlineKeyboardButton(text="✏️ ویرایش دسترسی", callback_data=f"edit_admin_perms:{tid}"))
    builder.row(InlineKeyboardButton(text="🔙 برگشت", callback_data="back_admins"))
    await cb.message.edit_text(
        f"👤 <b>{admin.full_name}</b>\n"
        f"🆔 <code>{tid}</code>\n"
        f"🔑 دسترسی‌ها: {', '.join([PERM_NAMES.get(p, p) for p in perms]) or 'ندارد'}",
        reply_markup=builder.as_markup(), parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("del_admin:"))
async def del_admin(cb: CallbackQuery):
    if cb.from_user.id not in config.ADMIN_IDS:
        return
    tid = int(cb.data.split(":")[1])
    async with AsyncSessionLocal() as db:
        await crud.remove_admin(db, tid)
    await cb.message.edit_text("🗑 ادمین حذف شد.")


# ─── BACKUP ──────────────────────────────────────────────────────────────────

@router.message(F.text == "💾 بکاپ")
async def backup(msg: Message):
    if not await is_admin(msg.from_user.id):
        return
    async with AsyncSessionLocal() as db:
        data = await crud.get_full_backup(db)
    buf = io.BytesIO(json.dumps(data, ensure_ascii=False, indent=2).encode())
    from datetime import datetime
    fname = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    await msg.answer_document(
        BufferedInputFile(buf.read(), fname),
        caption="💾 بکاپ کامل ربات"
    )
