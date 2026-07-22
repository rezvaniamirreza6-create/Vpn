import json
import logging
import asyncio
from datetime import datetime, timedelta
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from database.db import AsyncSessionLocal, TransactionType, UserStatus, PaymentStatus, PaymentMethod, ServiceStatus
from database import crud
from panels.sanei import panel
from bot.keyboards import (
    admin_menu_kb, admin_plans_kb, admin_plan_detail_kb, admin_cats_kb,
    admin_cat_detail_kb, admin_settings_kb, lottery_admin_kb, admin_admins_kb,
    back_kb, payment_confirm_kb, main_menu_kb, plan_cat_select_kb, admin_plans_select_kb,
    referral_services_select_kb
)
from config import config

logger = logging.getLogger(__name__)
router = Router()

PERM_NAMES = {
    "payment": "✅ تایید پرداخت", "broadcast": "📢 پیام همگانی",
    "plans": "📦 مدیریت پلن‌ها", "stats": "📊 آمار", "lottery": "🏆 قرعه‌کشی",
    "ban": "🚫 بن کاربر", "settings": "⚙️ تنظیمات", "wallet": "💰 کسر/افزایش موجودی",
    "discount": "🎫 کد تخفیف", "user_manage": "🔍 جستجو/مدیریت کاربر", "all": "🔑 همه",
}


async def is_admin(uid, perm=None):
    if uid in config.ADMIN_IDS:
        return True
    async with AsyncSessionLocal() as db:
        a = await crud.get_admin(db, uid)
        if not a:
            return False
        return crud.admin_has_perm(a, perm) if perm else True


class PlanState(StatesGroup):
    name = State(); traffic = State(); days = State(); price = State(); max_users = State()
    category = State(); inbound = State(); edit_field = State(); edit_value = State()


class CatState(StatesGroup):
    name = State(); icon = State(); edit_name = State()


class SettingState(StatesGroup):
    waiting_value = State()


class BanState(StatesGroup):
    waiting_id = State()


class AdjustState(StatesGroup):
    waiting_id = State(); waiting_amount = State()


class BroadcastState(StatesGroup):
    waiting_msg = State()


class AdminAddState(StatesGroup):
    selecting_perms = State(); waiting_id = State()


class ForceJoinState(StatesGroup):
    waiting_channel = State()


@router.message(F.text == "🔙 منوی اصلی")
async def back_main(msg: Message):
    await msg.answer("منوی اصلی 🏠", reply_markup=main_menu_kb())


@router.message(F.text == "📊 آمار ربات")
async def admin_stats(msg: Message):
    if not await is_admin(msg.from_user.id, "stats"):
        return
    async with AsyncSessionLocal() as db:
        users = await crud.get_user_count(db)
        services = await crud.get_service_count(db)
        pending = await crud.get_pending_card_payments(db)
    await msg.answer(f"📊 کاربران: {users}\n📦 سرویس فعال: {services}\n💳 پرداخت در انتظار: {len(pending)}")


@router.message(F.text == "📢 پیام همگانی")
async def broadcast_start(msg: Message, state: FSMContext):
    if not await is_admin(msg.from_user.id, "broadcast"):
        return
    await state.set_state(BroadcastState.waiting_msg)
    await msg.answer("📢 پیام را ارسال کنید:", reply_markup=back_kb("cancel"))


@router.message(BroadcastState.waiting_msg)
async def do_broadcast(msg: Message, state: FSMContext):
    await state.clear()
    async with AsyncSessionLocal() as db:
        users = await crud.get_all_active_users(db)
    sent = 0
    for u in users:
        try:
            await msg.copy_to(u.telegram_id)
            sent += 1
        except Exception:
            pass
    await msg.answer(f"✅ به {sent} کاربر ارسال شد.")


@router.message(F.text == "📦 مدیریت پلن‌ها")
async def admin_plans(msg: Message):
    if not await is_admin(msg.from_user.id, "plans"):
        return
    async with AsyncSessionLocal() as db:
        plans = await crud.get_all_plans(db)
    await msg.answer("📦 مدیریت پلن‌ها", reply_markup=admin_plans_kb(plans))


@router.callback_query(F.data == "admin_plans")
async def admin_plans_cb(cb: CallbackQuery):
    async with AsyncSessionLocal() as db:
        plans = await crud.get_all_plans(db)
    await cb.message.edit_text("📦 مدیریت پلن‌ها", reply_markup=admin_plans_kb(plans))


@router.callback_query(F.data.startswith("aplan:"))
async def plan_detail(cb: CallbackQuery):
    plan_id = int(cb.data.split(":")[1])
    async with AsyncSessionLocal() as db:
        plan = await crud.get_plan(db, plan_id)
    status = "✅ فعال" if plan.is_active else "❌ غیرفعال"
    users_text = "نامحدود" if plan.max_users == 0 else f"{plan.max_users} کاربر"
    traffic_text = "نامحدود" if plan.traffic_gb == 0 else f"{plan.traffic_gb}GB"
    await cb.message.edit_text(
        f"📦 {plan.name}\n📊 {traffic_text} | 📅 {plan.days}روز | 💰 {int(plan.price):,}T\n👥 {users_text} | 📶 {status}",
        reply_markup=admin_plan_detail_kb(plan_id)
    )


@router.callback_query(F.data == "add_plan")
async def add_plan_start(cb: CallbackQuery, state: FSMContext):
    await state.set_state(PlanState.name)
    await cb.message.edit_text("📦 نام پلن:")


@router.message(PlanState.name)
async def plan_name(msg: Message, state: FSMContext):
    await state.update_data(name=msg.text.strip())
    await state.set_state(PlanState.traffic)
    await msg.answer("📊 حجم (GB):")


@router.message(PlanState.traffic)
async def plan_traffic(msg: Message, state: FSMContext):
    text = msg.text.strip()
    if text in ("نامحدود", "0", "بی نهایت", "بی‌نهایت", "unlimited"):
        gb = 0
    else:
        try:
            gb = int(text)
            if gb < 0:
                raise ValueError
        except ValueError:
            await msg.answer("❌ عدد وارد کنید یا برای نامحدود بنویسید «نامحدود».")
            return
    await state.update_data(traffic=gb)
    await state.set_state(PlanState.days)
    await msg.answer("📅 تعداد روز:")


@router.message(PlanState.days)
async def plan_days(msg: Message, state: FSMContext):
    try:
        days = int(msg.text.strip())
    except ValueError:
        await msg.answer("❌ عدد وارد کنید.")
        return
    await state.update_data(days=days)
    await state.set_state(PlanState.price)
    await msg.answer("💰 قیمت (تومان):")


@router.message(PlanState.price)
async def plan_price(msg: Message, state: FSMContext):
    try:
        price = float(msg.text.replace(",", ""))
    except ValueError:
        await msg.answer("❌ عدد وارد کنید.")
        return
    await state.update_data(price=price)
    await state.set_state(PlanState.max_users)
    await msg.answer("👥 چند کاربره باشد؟ (تعداد اتصال همزمان مجاز، عدد ۱ یعنی تک‌کاربره، صفر یعنی نامحدود):")


@router.message(PlanState.max_users)
async def plan_max_users(msg: Message, state: FSMContext):
    try:
        max_users = int(msg.text.strip())
        if max_users < 0:
            raise ValueError
    except ValueError:
        await msg.answer("❌ عدد صحیح و غیرمنفی وارد کنید (مثلاً 1 یا 5 یا 0 برای نامحدود).")
        return
    await state.update_data(max_users=max_users)
    async with AsyncSessionLocal() as db:
        cats = await crud.get_all_categories(db)
    if not cats:
        # No categories exist yet, skip straight to creating the plan
        data = await state.get_data()
        await state.clear()
        async with AsyncSessionLocal() as db:
            plan = await crud.create_plan(db, data["name"], data["traffic"], data["days"], data["price"], max_users=max_users)
        await msg.answer(f"✅ پلن «{plan.name}» ساخته شد!\n(دسته‌بندی‌ای وجود نداشت، بدون دسته ساخته شد)")
        return
    await state.set_state(PlanState.category)
    await msg.answer("🗂 این پلن در کدام دسته‌بندی نمایش داده شود؟", reply_markup=plan_cat_select_kb(cats))


@router.callback_query(F.data.startswith("pcat:"), PlanState.category)
async def plan_category_selected(cb: CallbackQuery, state: FSMContext):
    cat_part = cb.data.split(":")[1]
    category_id = None if cat_part == "none" else int(cat_part)
    data = await state.get_data()
    await state.clear()
    async with AsyncSessionLocal() as db:
        plan = await crud.create_plan(
            db, data["name"], data["traffic"], data["days"], data["price"],
            category_id=category_id, max_users=data["max_users"]
        )
    users_text = "نامحدود" if data["max_users"] == 0 else f"{data['max_users']} کاربر"
    await cb.message.edit_text(f"✅ پلن «{plan.name}» ساخته شد!\n👥 {users_text}")


@router.callback_query(F.data.startswith("edit_plan:"))
async def edit_plan_start(cb: CallbackQuery, state: FSMContext):
    plan_id = int(cb.data.split(":")[1])
    await state.update_data(plan_id=plan_id)
    b = InlineKeyboardBuilder()
    for label, field in [("نام", "name"), ("حجم", "traffic_gb"), ("روز", "days"), ("قیمت", "price"), ("تعداد کاربر", "max_users")]:
        b.row(InlineKeyboardButton(text=label, callback_data=f"ef:{field}"))
    b.row(InlineKeyboardButton(text="🗂 دسته‌بندی", callback_data="ef:category_id"))
    b.row(InlineKeyboardButton(text="فعال/غیرفعال", callback_data="ef:toggle"))
    await cb.message.edit_text("✏️ فیلد:", reply_markup=b.as_markup())


@router.callback_query(F.data.startswith("ef:"))
async def edit_field(cb: CallbackQuery, state: FSMContext):
    field = cb.data.split(":")[1]
    data = await state.get_data()
    if field == "toggle":
        async with AsyncSessionLocal() as db:
            plan = await crud.get_plan(db, data["plan_id"])
            await crud.update_plan(db, data["plan_id"], is_active=not plan.is_active)
        await state.clear()
        await cb.message.edit_text("✅ وضعیت تغییر کرد.")
        return
    if field == "category_id":
        async with AsyncSessionLocal() as db:
            cats = await crud.get_all_categories(db)
        await cb.message.edit_text("🗂 دسته‌بندی جدید را انتخاب کنید:", reply_markup=plan_cat_select_kb(cats, prefix="efcat"))
        return
    await state.update_data(edit_field=field)
    await state.set_state(PlanState.edit_value)
    await cb.message.edit_text(f"مقدار جدید:")


@router.callback_query(F.data.startswith("efcat:"))
async def edit_plan_category(cb: CallbackQuery, state: FSMContext):
    cat_part = cb.data.split(":")[1]
    category_id = None if cat_part == "none" else int(cat_part)
    data = await state.get_data()
    await state.clear()
    async with AsyncSessionLocal() as db:
        await crud.update_plan(db, data["plan_id"], category_id=category_id)
    await cb.message.edit_text("✅ دسته‌بندی پلن بروزرسانی شد.")


@router.message(PlanState.edit_value)
async def edit_value(msg: Message, state: FSMContext):
    data = await state.get_data()
    field = data["edit_field"]
    val = msg.text.strip()
    try:
        if field == "traffic_gb" and val in ("نامحدود", "بی نهایت", "بی‌نهایت", "unlimited"):
            val = 0
        elif field in ("traffic_gb", "days", "max_users"):
            val = int(val)
        elif field == "price":
            val = float(val.replace(",", ""))
    except ValueError:
        await msg.answer("❌ نامعتبر.")
        return
    async with AsyncSessionLocal() as db:
        await crud.update_plan(db, data["plan_id"], **{field: val})
    await state.clear()
    await msg.answer("✅ بروزرسانی شد.")


@router.callback_query(F.data.startswith("del_plan:"))
async def del_plan(cb: CallbackQuery):
    plan_id = int(cb.data.split(":")[1])
    async with AsyncSessionLocal() as db:
        await crud.delete_plan(db, plan_id)
    await cb.message.edit_text("🗑 حذف شد.")


@router.message(F.text == "🗂 دسته‌بندی‌ها")
async def admin_cats(msg: Message):
    if not await is_admin(msg.from_user.id, "plans"):
        return
    async with AsyncSessionLocal() as db:
        cats = await crud.get_all_categories(db)
    await msg.answer("🗂 دسته‌بندی‌ها", reply_markup=admin_cats_kb(cats))


@router.callback_query(F.data == "admin_cats")
async def admin_cats_cb(cb: CallbackQuery):
    async with AsyncSessionLocal() as db:
        cats = await crud.get_all_categories(db)
    await cb.message.edit_text("🗂 دسته‌بندی‌ها", reply_markup=admin_cats_kb(cats))


@router.callback_query(F.data == "add_cat")
async def add_cat_start(cb: CallbackQuery, state: FSMContext):
    await state.set_state(CatState.name)
    await cb.message.edit_text("🗂 نام دسته‌بندی:")


@router.message(CatState.name)
async def cat_name(msg: Message, state: FSMContext):
    await state.update_data(name=msg.text.strip())
    await state.set_state(CatState.icon)
    await msg.answer("📌 ایموجی (مثلاً 🎮):")


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
    status = "✅" if cat.is_active else "❌"
    await cb.message.edit_text(f"{cat.icon} {cat.name}\n{status}", reply_markup=admin_cat_detail_kb(cat_id))


@router.callback_query(F.data.startswith("edit_cat:"))
async def edit_cat(cb: CallbackQuery, state: FSMContext):
    cat_id = int(cb.data.split(":")[1])
    await state.update_data(cat_id=cat_id)
    await state.set_state(CatState.edit_name)
    await cb.message.edit_text("✏️ نام جدید:")


@router.message(CatState.edit_name)
async def do_edit_cat(msg: Message, state: FSMContext):
    data = await state.get_data()
    async with AsyncSessionLocal() as db:
        await crud.update_category(db, data["cat_id"], name=msg.text.strip())
    await state.clear()
    await msg.answer("✅ بروزرسانی شد.")


@router.callback_query(F.data.startswith("del_cat:"))
async def del_cat(cb: CallbackQuery):
    cat_id = int(cb.data.split(":")[1])
    async with AsyncSessionLocal() as db:
        await crud.delete_category(db, cat_id)
    await cb.message.edit_text("🗑 حذف شد.")


@router.message(F.text == "💳 تایید پرداخت‌ها")
async def pending_payments(msg: Message):
    if not await is_admin(msg.from_user.id, "payment"):
        return
    async with AsyncSessionLocal() as db:
        payments = await crud.get_pending_card_payments(db)
    if not payments:
        await msg.answer("✅ پرداخت در انتظاری نیست.")
        return
    for pay in payments:
        await msg.bot.send_photo(
            msg.chat.id, pay.receipt_file_id,
            caption=f"💳 #{pay.id}\n👤 {pay.user.full_name}\n🆔 {pay.user.telegram_id}\n💰 {int(pay.amount):,}",
            reply_markup=payment_confirm_kb(pay.id, pay.user.telegram_id)
        )


@router.callback_query(F.data.startswith("pay_ok:"))
async def confirm_payment(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id, "payment"):
        return
    parts = cb.data.split(":")
    pay_id, user_tid = int(parts[1]), int(parts[2])
    async with AsyncSessionLocal() as db:
        pay = await crud.get_payment(db, pay_id)
        if not pay or pay.status != PaymentStatus.PENDING:
            await cb.answer("قبلاً پردازش شده.", show_alert=True)
            return
        pay.status = PaymentStatus.PAID
        user = pay.user
        await crud.update_wallet(db, user, pay.amount, "شارژ", TransactionType.DEPOSIT)
        await db.commit()
    await cb.message.edit_caption(f"✅ تأیید شد - {int(pay.amount):,}")
    try:
        await cb.bot.send_message(user_tid, f"✅ پرداخت تأیید شد! {int(pay.amount):,} تومان اضافه شد.")
    except Exception:
        pass


@router.callback_query(F.data.startswith("pay_rej:"))
async def reject_payment(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id, "payment"):
        return
    parts = cb.data.split(":")
    pay_id, user_tid = int(parts[1]), int(parts[2])
    async with AsyncSessionLocal() as db:
        pay = await crud.get_payment(db, pay_id)
        pay.status = PaymentStatus.REJECTED
        await db.commit()
    await cb.message.edit_caption("❌ رد شد")
    try:
        await cb.bot.send_message(user_tid, "❌ پرداخت تأیید نشد.")
    except Exception:
        pass


@router.message(F.text == "🏆 قرعه‌کشی")
async def lottery_admin(msg: Message):
    if not await is_admin(msg.from_user.id, "lottery"):
        return
    async with AsyncSessionLocal() as db:
        active = await crud.get_setting(db, "lottery_active", "false")
        count = await crud.get_lottery_participants_count(db)
    await msg.answer(f"🏆 وضعیت: {'فعال' if active=='true' else 'غیرفعال'}\n👥 شرکت‌کنندگان: {count}", reply_markup=lottery_admin_kb(active == "true"))


@router.callback_query(F.data == "toggle_lottery")
async def toggle_lottery(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id, "lottery"):
        return
    async with AsyncSessionLocal() as db:
        current = await crud.get_setting(db, "lottery_active", "false")
        new_val = "false" if current == "true" else "true"
        await crud.set_setting(db, "lottery_active", new_val)
        if new_val == "true":
            users = await crud.get_all_active_users(db)
        else:
            await crud.reset_lottery(db)
    if new_val == "true":
        sent = 0
        for u in users:
            try:
                await cb.bot.send_message(u.telegram_id, "🎊 قرعه‌کشی شروع شد! برای شرکت به ربات مراجعه کنید.")
                sent += 1
            except Exception:
                pass
        await cb.message.edit_text(f"🟢 فعال شد! به {sent} نفر اطلاع داده شد.\n(شماره‌های جدید و غیرتکراری به هر کاربر داده می‌شود)")
    else:
        await cb.message.edit_text("🔴 غیرفعال شد و آمار/شماره‌های قرعه‌کشی ریست شد.\n(دور بعد که فعال کنید، از صفر شروع می‌شود)")


@router.callback_query(F.data == "do_lottery")
async def do_lottery(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id, "lottery"):
        return
    async with AsyncSessionLocal() as db:
        winners = await crud.draw_lottery(db, count=1)
    if not winners:
        await cb.answer("شرکت‌کننده‌ای نیست!", show_alert=True)
        return
    w = winners[0]
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🎁 دادن جایزه", callback_data=f"give_prize:{w.telegram_id}"))
    await cb.message.answer(f"🎊 برنده: {w.full_name}\n🆔 {w.telegram_id}\n🎫 {w.lottery_number}", reply_markup=b.as_markup())


class PrizeState(StatesGroup):
    amount = State()


@router.callback_query(F.data.startswith("give_prize:"))
async def give_prize_start(cb: CallbackQuery, state: FSMContext):
    if not await is_admin(cb.from_user.id, "lottery"):
        return
    tid = int(cb.data.split(":")[1])
    await state.update_data(prize_tid=tid)
    await state.set_state(PrizeState.amount)
    await cb.message.answer(f"💰 چقدر به کیف پول کاربر {tid} اضافه شود؟ (تومان)")


@router.message(PrizeState.amount)
async def give_prize_amount(msg: Message, state: FSMContext):
    try:
        amount = int(msg.text.strip())
        if amount <= 0:
            raise ValueError
    except ValueError:
        await msg.answer("❌ یک عدد صحیح مثبت وارد کنید.")
        return
    data = await state.get_data()
    tid = data["prize_tid"]
    await state.clear()
    async with AsyncSessionLocal() as db:
        user = await crud.get_user(db, tid)
        if not user:
            await msg.answer("❌ کاربر یافت نشد.")
            return
        await crud.update_wallet(db, user, amount, "جایزه قرعه‌کشی", TransactionType.LOTTERY)
    await msg.answer(f"✅ {amount:,} تومان به کیف پول {tid} اضافه شد.")
    try:
        await msg.bot.send_message(tid, f"🎁 تبریک! جایزه‌ی قرعه‌کشی شما به مبلغ {amount:,} تومان به کیف پولتان اضافه شد.")
    except Exception:
        pass


@router.message(F.text == "🚫 بن کاربر")
async def ban_start(msg: Message, state: FSMContext):
    if not await is_admin(msg.from_user.id, "ban"):
        return
    await state.set_state(BanState.waiting_id)
    await msg.answer("🆔 آیدی عددی کاربر:", reply_markup=back_kb("cancel"))


@router.message(BanState.waiting_id)
async def do_ban(msg: Message, state: FSMContext):
    try:
        tid = int(msg.text.strip())
    except ValueError:
        await msg.answer("❌ عدد وارد کنید.")
        return
    async with AsyncSessionLocal() as db:
        user = await crud.get_user(db, tid)
        if not user:
            await msg.answer("❌ یافت نشد.")
            return
        if user.status == UserStatus.BANNED:
            await crud.unban_user(db, tid)
            await msg.answer(f"✅ {user.full_name} از بن خارج شد.")
        else:
            await crud.ban_user(db, tid)
            await msg.answer(f"🚫 {user.full_name} بن شد.")
    await state.clear()


@router.message(F.text == "💰 کسر/افزایش موجودی")
async def adjust_start(msg: Message, state: FSMContext):
    if not await is_admin(msg.from_user.id, "wallet"):
        return
    await state.set_state(AdjustState.waiting_id)
    await msg.answer("🆔 آیدی عددی کاربر:", reply_markup=back_kb("cancel"))


@router.message(AdjustState.waiting_id)
async def adjust_id(msg: Message, state: FSMContext):
    try:
        tid = int(msg.text.strip())
    except ValueError:
        await msg.answer("❌ عدد وارد کنید.")
        return
    async with AsyncSessionLocal() as db:
        user = await crud.get_user(db, tid)
    if not user:
        await msg.answer("❌ یافت نشد.")
        return
    await state.update_data(tid=tid)
    await state.set_state(AdjustState.waiting_amount)
    await msg.answer(f"👤 {user.full_name}\n💰 موجودی: {int(user.wallet):,}\n\nمقدار تغییر (+ یا -):")


@router.message(AdjustState.waiting_amount)
async def do_adjust(msg: Message, state: FSMContext):
    data = await state.get_data()
    try:
        amount = float(msg.text.replace(",", ""))
    except ValueError:
        await msg.answer("❌ عدد وارد کنید.")
        return
    async with AsyncSessionLocal() as db:
        user = await crud.get_user(db, data["tid"])
        await crud.update_wallet(db, user, amount, "تنظیم دستی", TransactionType.ADJUST)
        new_bal = user.wallet
    await state.clear()
    await msg.answer(f"✅ موجودی جدید: {int(new_bal):,}")
    try:
        await msg.bot.send_message(data["tid"], f"موجودی شما تغییر کرد: {int(amount):+,} تومان")
    except Exception:
        pass


@router.message(F.text == "📢 کانال‌های اجباری")
async def force_join_admin(msg: Message):
    if not await is_admin(msg.from_user.id, "settings"):
        return
    async with AsyncSessionLocal() as db:
        channels = await crud.get_all_force_joins(db)
        enabled = await crud.get_setting(db, "force_join_enabled", "false")
    b = InlineKeyboardBuilder()
    for ch in channels:
        b.row(InlineKeyboardButton(text=f"{ch.channel_name}", callback_data=f"del_fj:{ch.id}"))
    toggle = "🔴 غیرفعال" if enabled == "true" else "🟢 فعال"
    b.row(InlineKeyboardButton(text=toggle, callback_data="toggle_fj"))
    b.row(InlineKeyboardButton(text="➕ افزودن کانال", callback_data="add_fj"))
    await msg.answer(f"📢 وضعیت: {enabled}", reply_markup=b.as_markup())


@router.callback_query(F.data == "toggle_fj")
async def toggle_fj(cb: CallbackQuery):
    async with AsyncSessionLocal() as db:
        current = await crud.get_setting(db, "force_join_enabled", "false")
        await crud.set_setting(db, "force_join_enabled", "false" if current == "true" else "true")
    await cb.answer("✅ تغییر یافت.")


@router.callback_query(F.data == "add_fj")
async def add_fj_start(cb: CallbackQuery, state: FSMContext):
    await state.set_state(ForceJoinState.waiting_channel)
    await cb.message.edit_text("📢 آیدی کانال (@channel):")


@router.message(ForceJoinState.waiting_channel)
async def do_add_fj(msg: Message, state: FSMContext):
    channel_id = msg.text.strip()
    try:
        chat = await msg.bot.get_chat(channel_id)
        name = chat.title or channel_id
        invite = await msg.bot.export_chat_invite_link(chat.id)
    except Exception:
        name, invite = channel_id, None
    async with AsyncSessionLocal() as db:
        await crud.add_force_join(db, channel_id, name, invite)
    await state.clear()
    await msg.answer(f"✅ «{name}» اضافه شد.")


@router.callback_query(F.data.startswith("del_fj:"))
async def del_fj(cb: CallbackQuery):
    fj_id = int(cb.data.split(":")[1])
    async with AsyncSessionLocal() as db:
        await crud.remove_force_join(db, fj_id)
    await cb.answer("🗑 حذف شد.")


@router.message(F.text == "⚙️ تنظیمات")
async def admin_settings(msg: Message):
    if not await is_admin(msg.from_user.id, "settings"):
        return
    async with AsyncSessionLocal() as db:
        test_enabled = await crud.get_setting(db, "free_test_enabled", "true")
        sub_https = await crud.get_setting(db, "sub_https", "true")
    await msg.answer("⚙️ تنظیمات", reply_markup=admin_settings_kb(test_enabled == "true", sub_https == "true"))


@router.callback_query(F.data == "toggle_free_test")
async def toggle_free_test(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id, "settings"):
        return
    async with AsyncSessionLocal() as db:
        current = await crud.get_setting(db, "free_test_enabled", "true")
        new_val = "false" if current == "true" else "true"
        await crud.set_setting(db, "free_test_enabled", new_val)
        sub_https = await crud.get_setting(db, "sub_https", "true")
    await cb.answer("✅ تست رایگان روشن شد." if new_val == "true" else "✅ تست رایگان خاموش شد.", show_alert=True)
    await cb.message.edit_reply_markup(reply_markup=admin_settings_kb(new_val == "true", sub_https == "true"))


@router.callback_query(F.data == "toggle_sub_https")
async def toggle_sub_https(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id, "settings"):
        return
    async with AsyncSessionLocal() as db:
        current = await crud.get_setting(db, "sub_https", "true")
        new_val = "false" if current == "true" else "true"
        await crud.set_setting(db, "sub_https", new_val)
        test_enabled = await crud.get_setting(db, "free_test_enabled", "true")
    panel.sub_https = (new_val == "true")
    scheme = "https" if panel.sub_https else "http"
    await cb.answer(f"✅ لینک ساب از این به بعد با {scheme}:// ساخته می‌شود.", show_alert=True)
    await cb.message.edit_reply_markup(reply_markup=admin_settings_kb(test_enabled == "true", new_val == "true"))


SETTING_MAP = {
    "set_card": ("card_number", "💳 شماره کارت:"),
    "set_card_holder": ("card_holder", "👤 نام صاحب کارت (دقیقاً مطابق کارت بانکی):"),
    "set_botname": ("bot_name", "🤖 نام ربات:"),
    "set_support": ("support_username", "📞 یوزرنیم پشتیبانی:"),
    "set_referral": ("referral_reward", "💰 پاداش دعوت:"),
    "set_zarinpal": ("zarinpal_merchant", "🏦 Merchant ID:"),
    "set_inbound": ("inbound_id", "🔢 شماره Inbound:"),
    "set_test_inbound": ("test_inbound_id", "🧪 شماره Inbound مخصوص تست رایگان:"),
}


@router.callback_query(F.data.startswith("set_"))
async def setting_start(cb: CallbackQuery, state: FSMContext):
    key_cb = cb.data
    if key_cb in SETTING_MAP:
        setting_key, prompt = SETTING_MAP[key_cb]
        await state.set_state(SettingState.waiting_value)
        await state.update_data(setting_key=setting_key)
        await cb.message.edit_text(prompt, reply_markup=back_kb("cancel"))
    elif key_cb == "set_test":
        await state.set_state(SettingState.waiting_value)
        await state.update_data(setting_key="test_config")
        await cb.message.edit_text("🎁 فرمت: MB/روز مثال: 500/1")
    elif key_cb == "set_panel":
        await state.set_state(SettingState.waiting_value)
        await state.update_data(setting_key="panel_config")
        await cb.message.edit_text("🔗 فرمت: URL|USER|PASS|PATH")
    elif key_cb == "set_sub":
        await state.set_state(SettingState.waiting_value)
        await state.update_data(setting_key="sub_config")
        await cb.message.edit_text("🔗 پورت و مسیر ساب (subscription) پنل — این با پورت خود پنل فرق دارد.\nفرمت: PORT|PATH\nمثال: 2096|sub")


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
            await msg.answer("✅ تنظیم شد.")
            return
        elif key == "panel_config":
            parts = val.split("|")
            if len(parts) >= 3:
                await crud.set_setting(db, "panel_url", parts[0])
                await crud.set_setting(db, "panel_username", parts[1])
                await crud.set_setting(db, "panel_password", parts[2])
                if len(parts) > 3:
                    await crud.set_setting(db, "panel_path", parts[3])
                await panel.reload_settings(db)
            await msg.answer("✅ پنل تنظیم شد.")
            return
        elif key == "sub_config":
            parts = val.split("|")
            if len(parts) >= 1:
                await crud.set_setting(db, "sub_port", parts[0].strip())
            if len(parts) >= 2:
                await crud.set_setting(db, "sub_path", parts[1].strip())
            await panel.reload_settings(db)
            await msg.answer("✅ تنظیمات ساب ذخیره شد.")
            return
        await crud.set_setting(db, key, val)
    await msg.answer("✅ ذخیره شد.")


@router.callback_query(F.data == "toggle_auto_config")
async def toggle_auto(cb: CallbackQuery):
    async with AsyncSessionLocal() as db:
        current = await crud.get_setting(db, "auto_config_send", "true")
        await crud.set_setting(db, "auto_config_send", "false" if current == "true" else "true")
    await cb.answer("✅ تغییر یافت.", show_alert=True)


@router.message(F.text == "👥 مدیریت ادمین‌ها")
async def manage_admins(msg: Message):
    if not await is_admin(msg.from_user.id, "all"):
        return
    async with AsyncSessionLocal() as db:
        admins = await crud.get_all_admins(db)
    await msg.answer("👥 ادمین‌ها", reply_markup=admin_admins_kb(admins))


@router.callback_query(F.data == "add_admin")
async def add_admin_start(cb: CallbackQuery, state: FSMContext):
    if not await is_admin(cb.from_user.id, "all"):
        return
    b = InlineKeyboardBuilder()
    for perm, name in PERM_NAMES.items():
        b.row(InlineKeyboardButton(text=f"☐ {name}", callback_data=f"perm:{perm}"))
    b.row(InlineKeyboardButton(text="✅ تأیید", callback_data="perms_done"))
    await state.set_state(AdminAddState.selecting_perms)
    await state.update_data(selected_perms=[])
    await cb.message.edit_text("🔑 دسترسی‌ها:", reply_markup=b.as_markup())


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
    b = InlineKeyboardBuilder()
    for p, name in PERM_NAMES.items():
        check = "✅" if p in perms else "☐"
        b.row(InlineKeyboardButton(text=f"{check} {name}", callback_data=f"perm:{p}"))
    b.row(InlineKeyboardButton(text="✅ تأیید", callback_data="perms_done"))
    await cb.message.edit_reply_markup(reply_markup=b.as_markup())


@router.callback_query(F.data == "perms_done", AdminAddState.selecting_perms)
async def perms_done(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AdminAddState.waiting_id)
    await cb.message.edit_text("🆔 آیدی عددی:")


@router.message(AdminAddState.waiting_id)
async def do_add_admin(msg: Message, state: FSMContext):
    try:
        tid = int(msg.text.strip())
    except ValueError:
        await msg.answer("❌ عدد وارد کنید.")
        return
    data = await state.get_data()
    perms = data.get("selected_perms", [])
    try:
        async with AsyncSessionLocal() as db:
            user = await crud.get_user(db, tid)
            name = user.full_name if user else str(tid)
            await crud.add_admin(db, tid, name, perms, msg.from_user.id)
        await state.clear()
        await msg.answer(f"✅ ادمین اضافه شد. 🆔 {tid}")
    except Exception as e:
        logger.error(f"add_admin failed for {tid}: {e}")
        await state.clear()
        await msg.answer("❌ خطایی رخ داد و ادمین اضافه نشد. دوباره تلاش کنید.")


@router.callback_query(F.data.startswith("admin_detail:"))
async def admin_detail(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id, "all"):
        return
    tid = int(cb.data.split(":")[1])
    async with AsyncSessionLocal() as db:
        admin = await crud.get_admin(db, tid)
    if not admin:
        await cb.answer("یافت نشد!", show_alert=True)
        return
    perms = json.loads(admin.permissions or "[]")
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🗑 حذف", callback_data=f"del_admin:{tid}"))
    await cb.message.edit_text(f"👤 {admin.full_name}\n🆔 {tid}\n🔑 {', '.join(perms)}", reply_markup=b.as_markup())


@router.callback_query(F.data.startswith("del_admin:"))
async def del_admin(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id, "all"):
        return
    tid = int(cb.data.split(":")[1])
    async with AsyncSessionLocal() as db:
        await crud.remove_admin(db, tid)
    await cb.message.edit_text("🗑 حذف شد.")


# ---------------- Discount codes ----------------

class DiscountState(StatesGroup):
    code = State()
    percent = State()
    duration_amount = State()
    max_uses = State()


@router.message(F.text == "🎫 کد تخفیف")
async def discount_menu(msg: Message):
    if not await is_admin(msg.from_user.id, "discount"):
        return
    async with AsyncSessionLocal() as db:
        codes = await crud.get_all_discounts(db)
    b = InlineKeyboardBuilder()
    for c in codes[:25]:
        status = "✅" if c.is_active else "❌"
        exp = f" ⏳{c.expires_at.strftime('%Y-%m-%d %H:%M')}" if c.expires_at else " ♾"
        b.row(InlineKeyboardButton(text=f"{status} {c.code} | {c.percent}% | {c.used_count}/{c.max_uses}{exp}", callback_data=f"disc_detail:{c.id}"))
    b.row(InlineKeyboardButton(text="➕ ساخت کد تخفیف", callback_data="add_discount_code"))
    await msg.answer("🎫 کدهای تخفیف:" if codes else "🎫 هنوز کد تخفیفی ساخته نشده.", reply_markup=b.as_markup())


@router.callback_query(F.data == "add_discount_code")
async def add_discount_start(cb: CallbackQuery, state: FSMContext):
    if not await is_admin(cb.from_user.id, "discount"):
        return
    await state.set_state(DiscountState.code)
    await cb.message.edit_text("🏷 کد تخفیف را وارد کنید (مثلاً OFF20):")


@router.message(DiscountState.code)
async def discount_code_input(msg: Message, state: FSMContext):
    code = msg.text.strip().upper()
    if not code or " " in code:
        await msg.answer("❌ کد نامعتبر است، دوباره وارد کنید:")
        return
    async with AsyncSessionLocal() as db:
        existing = await crud.get_discount(db, code)
    if existing:
        await msg.answer("❌ این کد قبلاً وجود دارد، یک کد دیگر وارد کنید:")
        return
    await state.update_data(code=code)
    await state.set_state(DiscountState.percent)
    await msg.answer("📊 درصد تخفیف را وارد کنید (عدد بین ۱ تا ۱۰۰، مثلاً 20):")


@router.message(DiscountState.percent)
async def discount_percent_input(msg: Message, state: FSMContext):
    try:
        percent = int(msg.text.strip())
        if not (0 < percent <= 100):
            raise ValueError
    except ValueError:
        await msg.answer("❌ عدد بین 1 تا 100 وارد کنید.")
        return
    await state.update_data(percent=percent)
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="⏰ ساعت", callback_data="dur:hour"))
    b.row(InlineKeyboardButton(text="📅 روز", callback_data="dur:day"))
    b.row(InlineKeyboardButton(text="🗓 ماه", callback_data="dur:month"))
    b.row(InlineKeyboardButton(text="♾ بدون انقضا", callback_data="dur:none"))
    await msg.answer("⏳ واحد زمانی اعتبار این کد چیست؟", reply_markup=b.as_markup())


@router.callback_query(F.data.startswith("dur:"))
async def discount_duration_unit(cb: CallbackQuery, state: FSMContext):
    unit = cb.data.split(":")[1]
    if unit == "none":
        await state.update_data(duration_unit=None, duration_amount=None)
        await state.set_state(DiscountState.max_uses)
        await cb.message.edit_text("👥 ظرفیت کد چند نفر باشد؟ (عدد وارد کنید)")
        return
    await state.update_data(duration_unit=unit)
    await state.set_state(DiscountState.duration_amount)
    unit_fa = {"hour": "ساعت", "day": "روز", "month": "ماه"}[unit]
    await cb.message.edit_text(f"⏳ چند {unit_fa} اعتبار داشته باشد؟ یک عدد وارد کنید:")


@router.message(DiscountState.duration_amount)
async def discount_duration_amount_input(msg: Message, state: FSMContext):
    try:
        amount = int(msg.text.strip())
        if amount <= 0:
            raise ValueError
    except ValueError:
        await msg.answer("❌ یک عدد صحیح مثبت وارد کنید.")
        return
    await state.update_data(duration_amount=amount)
    await state.set_state(DiscountState.max_uses)
    await msg.answer("👥 ظرفیت کد چند نفر باشد؟ (عدد وارد کنید)")


@router.message(DiscountState.max_uses)
async def discount_max_uses_input(msg: Message, state: FSMContext):
    try:
        max_uses = int(msg.text.strip())
        if max_uses <= 0:
            raise ValueError
    except ValueError:
        await msg.answer("❌ یک عدد صحیح مثبت وارد کنید.")
        return
    data = await state.get_data()
    await state.clear()
    expires_at = None
    unit = data.get("duration_unit")
    amount = data.get("duration_amount")
    if unit and amount:
        delta_map = {"hour": timedelta(hours=amount), "day": timedelta(days=amount), "month": timedelta(days=amount * 30)}
        expires_at = datetime.utcnow() + delta_map[unit]
    async with AsyncSessionLocal() as db:
        dc = await crud.create_discount(db, data["code"], data["percent"], max_uses=max_uses, expires_at=expires_at)
    exp_text = f"⏳ انقضا: {expires_at.strftime('%Y-%m-%d %H:%M')}" if expires_at else "♾ بدون انقضا"
    await msg.answer(f"✅ کد تخفیف ساخته شد!\n\n🏷 کد: {dc.code}\n📊 درصد: {dc.percent}%\n👥 ظرفیت: {dc.max_uses} نفر\n{exp_text}")


@router.callback_query(F.data.startswith("disc_detail:"))
async def discount_detail(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id, "discount"):
        return
    did = int(cb.data.split(":")[1])
    async with AsyncSessionLocal() as db:
        codes = await crud.get_all_discounts(db)
    dc = next((c for c in codes if c.id == did), None)
    if not dc:
        await cb.answer("یافت نشد!", show_alert=True)
        return
    exp_text = dc.expires_at.strftime('%Y-%m-%d %H:%M') if dc.expires_at else "بدون انقضا"
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🗑 حذف", callback_data=f"del_discount:{did}"))
    status = "✅ فعال" if dc.is_active else "❌ غیرفعال"
    await cb.message.edit_text(f"🏷 {dc.code}\n📊 {dc.percent}% تخفیف\n👥 استفاده: {dc.used_count}/{dc.max_uses}\n⏳ انقضا: {exp_text}\n{status}", reply_markup=b.as_markup())


@router.callback_query(F.data.startswith("del_discount:"))
async def del_discount(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id, "discount"):
        return
    did = int(cb.data.split(":")[1])
    async with AsyncSessionLocal() as db:
        await crud.delete_discount(db, did)
    await cb.message.edit_text("🗑 کد تخفیف حذف شد.")


# ---------------- Leaderboards ----------------

class TopListState(StatesGroup):
    referrers_count = State()
    buyers_count = State()


@router.message(F.text == "📈 برترین معرف‌ها")
async def top_referrers_start(msg: Message, state: FSMContext):
    if not await is_admin(msg.from_user.id, "stats"):
        return
    await state.set_state(TopListState.referrers_count)
    await msg.answer("📈 چند نفر اول نمایش داده شود؟ (عدد وارد کنید، مثلاً 10)")


@router.message(TopListState.referrers_count)
async def top_referrers_show(msg: Message, state: FSMContext):
    try:
        n = int(msg.text.strip())
        if n <= 0:
            raise ValueError
    except ValueError:
        await msg.answer("❌ عدد صحیح مثبت وارد کنید.")
        return
    await state.clear()
    async with AsyncSessionLocal() as db:
        top = await crud.get_top_referrers(db, n)
    if not top:
        await msg.answer("هنوز کسی کسی رو دعوت نکرده.")
        return
    lines = [f"📈 <b>{len(top)} معرف برتر:</b>\n"]
    for i, (u, tid, cnt) in enumerate(top, 1):
        name = (u.full_name or u.username or str(tid)) if u else str(tid)
        uname = f" (@{u.username})" if u and u.username else ""
        lines.append(f"{i}. {name}{uname}\n   🆔 {tid} | 👥 {cnt} دعوت")
    await msg.answer("\n".join(lines), parse_mode="HTML")


@router.message(F.text == "💎 برترین خریداران")
async def top_buyers_start(msg: Message, state: FSMContext):
    if not await is_admin(msg.from_user.id, "stats"):
        return
    await state.set_state(TopListState.buyers_count)
    await msg.answer("💎 چند نفر اول نمایش داده شود؟ (عدد وارد کنید، مثلاً 10)")


@router.message(TopListState.buyers_count)
async def top_buyers_show(msg: Message, state: FSMContext):
    try:
        n = int(msg.text.strip())
        if n <= 0:
            raise ValueError
    except ValueError:
        await msg.answer("❌ عدد صحیح مثبت وارد کنید.")
        return
    await state.clear()
    async with AsyncSessionLocal() as db:
        top = await crud.get_top_buyers(db, n)
    if not top:
        await msg.answer("هنوز خریدی ثبت نشده.")
        return
    lines = [f"💎 <b>{len(top)} خریدار برتر:</b>\n"]
    for i, (u, total) in enumerate(top, 1):
        name = (u.full_name or u.username or str(u.telegram_id)) if u else "نامشخص"
        tid = u.telegram_id if u else "-"
        lines.append(f"{i}. {name}\n   🆔 {tid} | 💰 {total:,.0f} تومان")
    await msg.answer("\n".join(lines), parse_mode="HTML")


# ---------------- User search & management ----------------

class UserSearchState(StatesGroup):
    query = State()


class UserWalletState(StatesGroup):
    amount = State()


@router.message(F.text == "🔍 جستجوی کاربر")
async def user_search_start(msg: Message, state: FSMContext):
    if not await is_admin(msg.from_user.id, "user_manage"):
        return
    await state.set_state(UserSearchState.query)
    await msg.answer("🔍 آیدی عددی یا یوزرنیم کاربر را ارسال کنید:")


async def _render_user_card(user, db):
    services = await crud.get_user_services(db, user.id)
    ref_count = await crud.count_referrals(db, user.telegram_id)
    status_text = "🚫 بن شده" if user.status == UserStatus.BANNED else "✅ فعال"
    test_text = "✅ استفاده کرده" if user.has_used_test else "⭐️ استفاده نکرده"
    phone_text = user.phone if user.phone else ("⚠️ ثبت نشده (استثنا شده)" if user.phone_exempt else "⚠️ ثبت نشده")
    text = (
        f"👤 <b>{user.full_name or '-'}</b>\n"
        f"🆔 <code>{user.telegram_id}</code>\n"
        f"👤 یوزرنیم: @{user.username or '-'}\n"
        f"📱 شماره تلفن: {phone_text}\n"
        f"💰 موجودی: {user.wallet:,.0f} تومان\n"
        f"📊 وضعیت: {status_text}\n"
        f"🎁 تست رایگان: {test_text}\n"
        f"👥 تعداد دعوت: {ref_count}\n"
        f"📦 تعداد سرویس: {len(services)}"
    )
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="💰 افزودن/کسر موجودی", callback_data=f"usr_wallet:{user.telegram_id}"))
    if services:
        b.row(InlineKeyboardButton(text=f"📦 سرویس‌ها ({len(services)})", callback_data=f"usr_services:{user.telegram_id}:0"))
    ban_label = "✅ خارج کردن از بن" if user.status == UserStatus.BANNED else "🚫 بن کردن"
    b.row(InlineKeyboardButton(text=ban_label, callback_data=f"usr_toggleban:{user.telegram_id}"))
    if not user.phone:
        exempt_label = "🔓 لغو استثنای احراز هویت" if user.phone_exempt else "🔑 استثنا از احراز هویت (بدون شماره)"
        b.row(InlineKeyboardButton(text=exempt_label, callback_data=f"usr_toggleexempt:{user.telegram_id}"))
    return text, b.as_markup()


@router.callback_query(F.data.startswith("usr_toggleexempt:"))
async def usr_toggle_exempt(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id, "user_manage"):
        return
    tid = int(cb.data.split(":")[1])
    async with AsyncSessionLocal() as db:
        user = await crud.get_user(db, tid)
        if not user:
            await cb.answer("یافت نشد!", show_alert=True)
            return
        await crud.set_phone_exempt(db, tid, not user.phone_exempt)
        user = await crud.get_user(db, tid)
        text, kb = await _render_user_card(user, db)
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)


@router.message(UserSearchState.query)
async def user_search_result(msg: Message, state: FSMContext):
    q = msg.text.strip()
    await state.clear()
    async with AsyncSessionLocal() as db:
        user = await crud.search_user(db, q)
        if not user:
            await msg.answer("❌ کاربری با این مشخصات پیدا نشد.")
            return
        text, kb = await _render_user_card(user, db)
    await msg.answer(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("usr_toggleban:"))
async def usr_toggle_ban(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id, "user_manage"):
        return
    tid = int(cb.data.split(":")[1])
    async with AsyncSessionLocal() as db:
        user = await crud.get_user(db, tid)
        if not user:
            await cb.answer("یافت نشد!", show_alert=True)
            return
        if user.status == UserStatus.BANNED:
            await crud.unban_user(db, tid)
        else:
            await crud.ban_user(db, tid)
        user = await crud.get_user(db, tid)
        text, kb = await _render_user_card(user, db)
    await cb.message.edit_text(text, parse_mode="HTML", reply_markup=kb)


@router.callback_query(F.data.startswith("usr_wallet:"))
async def usr_wallet_start(cb: CallbackQuery, state: FSMContext):
    if not await is_admin(cb.from_user.id, "user_manage"):
        return
    tid = int(cb.data.split(":")[1])
    await state.update_data(target_tid=tid)
    await state.set_state(UserWalletState.amount)
    await cb.message.answer("💰 مبلغ را وارد کنید (برای کسر، عدد منفی بزنید. مثلاً 50000 یا -20000):")


@router.message(UserWalletState.amount)
async def usr_wallet_apply(msg: Message, state: FSMContext):
    try:
        amount = int(msg.text.strip())
        if amount == 0:
            raise ValueError
    except ValueError:
        await msg.answer("❌ یک عدد معتبر (مثبت یا منفی) وارد کنید.")
        return
    data = await state.get_data()
    tid = data["target_tid"]
    await state.clear()
    async with AsyncSessionLocal() as db:
        user = await crud.get_user(db, tid)
        if not user:
            await msg.answer("❌ کاربر یافت نشد.")
            return
        await crud.update_wallet(db, user, amount, "تغییر دستی توسط ادمین", TransactionType.ADJUST)
    sign = "➕" if amount > 0 else "➖"
    await msg.answer(f"✅ {sign} {abs(amount):,} تومان اعمال شد. موجودی جدید: {user.wallet:,.0f} تومان")
    try:
        await msg.bot.send_message(tid, f"💰 موجودی کیف پول شما توسط پشتیبانی {sign}{abs(amount):,} تومان تغییر کرد.")
    except Exception:
        pass


@router.callback_query(F.data.startswith("usr_services:"))
async def usr_services_list(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id, "user_manage"):
        return
    parts = cb.data.split(":")
    tid, idx = int(parts[1]), int(parts[2])
    async with AsyncSessionLocal() as db:
        user = await crud.get_user(db, tid)
        services = await crud.get_user_services(db, user.id)
    if not services or idx >= len(services):
        await cb.answer("سرویسی نیست.", show_alert=True)
        return
    svc = services[idx]
    status_text = "✅ فعال" if svc.status == ServiceStatus.ACTIVE else "❌ منقضی/غیرفعال"
    exp = svc.expires_at.strftime("%Y-%m-%d") if svc.expires_at else "-"
    text = (f"📦 سرویس {idx+1}/{len(services)}\n"
            f"📧 {svc.panel_email}\n📊 {svc.traffic_gb}GB | 📅 {svc.days} روز\n"
            f"⏳ انقضا: {exp}\n📌 وضعیت: {status_text}")
    b = InlineKeyboardBuilder()
    nav = []
    if idx > 0:
        nav.append(InlineKeyboardButton(text="◀️ قبلی", callback_data=f"usr_services:{tid}:{idx-1}"))
    if idx < len(services) - 1:
        nav.append(InlineKeyboardButton(text="بعدی ▶️", callback_data=f"usr_services:{tid}:{idx+1}"))
    if nav:
        b.row(*nav)
    if svc.status == ServiceStatus.ACTIVE:
        b.row(InlineKeyboardButton(text="⛔️ غیرفعال کردن سرویس", callback_data=f"usr_svcoff:{tid}:{svc.id}:{idx}"))
    await cb.message.edit_text(text, reply_markup=b.as_markup())


@router.callback_query(F.data.startswith("usr_svcoff:"))
async def usr_service_disable(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id, "user_manage"):
        return
    _, tid, svc_id, idx = cb.data.split(":")
    svc_id, idx = int(svc_id), int(idx)
    ok = False
    async with AsyncSessionLocal() as db:
        svc = await crud.get_service(db, svc_id)
        if svc:
            try:
                ok = await panel.delete_client(svc.inbound_id, svc.panel_uuid, email=svc.panel_email)
            except Exception:
                ok = False
            await crud.update_service(db, svc_id, status=ServiceStatus.EXPIRED, panel_removed=ok)
    if ok:
        await cb.answer("✅ سرویس از پنل حذف و غیرفعال شد.", show_alert=True)
    else:
        await cb.answer("⚠️ در دیتابیس غیرفعال شد ولی حذف از پنل ناموفق بود.", show_alert=True)
    await usr_services_list(cb)


# ---------------- Reset free test ----------------

@router.message(F.text == "♻️ ریست تست رایگان")
async def reset_test_confirm(msg: Message):
    if not await is_admin(msg.from_user.id, "settings"):
        return
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="✅ بله، ریست کن", callback_data="do_reset_test"))
    b.row(InlineKeyboardButton(text="❌ انصراف", callback_data="cancel"))
    await msg.answer("⚠️ با این کار همه‌ی کاربران دوباره می‌توانند یک بار تست رایگان بگیرند. مطمئنید؟", reply_markup=b.as_markup())


@router.callback_query(F.data == "do_reset_test")
async def do_reset_test(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id, "settings"):
        return
    async with AsyncSessionLocal() as db:
        count = await crud.reset_all_tests(db)
    await cb.message.edit_text(f"✅ تست رایگان برای {count} کاربر ریست شد. حالا همه می‌توانند دوباره تست بگیرند.")


# ---------------- Expired service cleanup ----------------

async def _find_truly_expired_services(db):
    """A service counts as needing cleanup if:
    - it's still marked EXPIRED locally but was never actually confirmed
      removed from the panel (leftover from before this was tracked), OR
    - it's ACTIVE locally but expired by our local time record, OR
    - it's ACTIVE locally but the panel itself reports it as disabled /
      out of traffic / past its own expiry time, OR the client no longer
      exists on the panel at all.
    """
    candidates = await crud.get_services_pending_panel_removal(db)
    now = datetime.utcnow()
    now_ms = int(now.timestamp() * 1000)
    ended = []
    for svc in candidates:
        if svc.status == ServiceStatus.EXPIRED:
            ended.append(svc)
            continue
        if svc.status != ServiceStatus.ACTIVE:
            continue
        is_ended = bool(svc.expires_at and svc.expires_at < now)
        if not is_ended:
            try:
                info = await panel.get_client_traffic(svc.panel_email)
            except Exception:
                info = None
            if info is None:
                is_ended = True  # client not found on panel anymore
            else:
                if info.get("enable") is False:
                    is_ended = True
                total = info.get("total") or 0
                if total > 0 and (info.get("up", 0) + info.get("down", 0)) >= total:
                    is_ended = True
                exp = info.get("expiryTime") or 0
                if exp > 0 and exp < now_ms:
                    is_ended = True
        if is_ended:
            ended.append(svc)
    return ended


@router.message(F.text == "🗑 حذف سرویس‌های منقضی")
async def cleanup_expired_start(msg: Message, state: FSMContext):
    if not await is_admin(msg.from_user.id, "plans"):
        return
    wait_msg = await msg.answer("⏳ در حال بررسی وضعیت واقعی سرویس‌ها با پنل، چند لحظه صبر کن...")
    async with AsyncSessionLocal() as db:
        expired = await _find_truly_expired_services(db)
    try:
        await wait_msg.delete()
    except Exception:
        pass
    if not expired:
        await msg.answer("✅ سرویس منقضی‌ای وجود نداره.")
        return
    await state.update_data(expired_ids=[s.id for s in expired])
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text=f"✅ حذف {len(expired)} سرویس منقضی", callback_data="do_cleanup_expired"))
    b.row(InlineKeyboardButton(text="❌ انصراف", callback_data="cancel"))
    await msg.answer(f"⚠️ {len(expired)} سرویس منقضی/تمام‌شده پیدا شد (بر اساس زمان یا حجم مصرفی واقعی). حذف بشن؟", reply_markup=b.as_markup())


@router.callback_query(F.data == "do_cleanup_expired")
async def do_cleanup_expired(cb: CallbackQuery, state: FSMContext):
    if not await is_admin(cb.from_user.id, "plans"):
        return
    await cb.answer("⏳ شروع شد...")
    data = await state.get_data()
    ids = data.get("expired_ids")
    await state.clear()
    await cb.message.edit_text(f"⏳ در حال حذف {len(ids) if ids else ''} سرویس در پس‌زمینه... وقتی تموم شد پیام جدید می‌فرستم (ممکنه چند دقیقه طول بکشه).")
    asyncio.create_task(_run_cleanup_expired(cb.message.chat.id, cb.bot, ids))


async def _run_cleanup_expired(chat_id: int, bot: Bot, ids):
    try:
        async with AsyncSessionLocal() as db:
            if ids:
                services = []
                for sid in ids:
                    svc = await crud.get_service(db, sid)
                    if svc and not svc.panel_removed:
                        services.append(svc)
            else:
                services = await _find_truly_expired_services(db)
            removed, failed = 0, 0
            for svc in services:
                ok = False
                try:
                    ok = await panel.delete_client(svc.inbound_id, svc.panel_uuid, email=svc.panel_email)
                except Exception as e:
                    logger.error(f"delete_client failed for service {svc.id}: {e}")
                    ok = False
                await crud.update_service(db, svc.id, status=ServiceStatus.EXPIRED, panel_removed=ok)
                if ok:
                    removed += 1
                else:
                    failed += 1
        text = f"✅ پاک‌سازی تمام شد.\n{removed} سرویس منقضی از پنل حذف و در دیتابیس غیرفعال شد."
        if failed:
            text += f"\n⚠️ {failed} سرویس در دیتابیس غیرفعال شد ولی حذفشون از پنل ناموفق بود (دفعه‌ی بعد دوباره امتحان می‌شه)."
        await bot.send_message(chat_id, text)
    except Exception as e:
        logger.error(f"_run_cleanup_expired crashed: {e}")
        try:
            await bot.send_message(chat_id, f"❌ خطا در حذف: {type(e).__name__}: {e}")
        except Exception:
            pass


# ---------------- Close referral-acquired services ----------------

class CloseReferralState(StatesGroup):
    count = State()
    select_active = State()


def _fmt_referral_service_line(i, s):
    u = s.user
    uname = f"@{u.username}" if u and u.username else "بدون یوزرنیم"
    fname = u.full_name if u and u.full_name else "-"
    tid = u.telegram_id if u else "-"
    exp = s.expires_at.strftime("%Y-%m-%d") if s.expires_at else "-"
    test_tag = " (تست)" if s.is_test else ""
    return f"{i}. {fname} {uname}\n   🆔 {tid} | 📧 {s.panel_email}{test_tag}\n   📊 {s.traffic_gb}GB | ⏳ {exp}"


@router.message(F.text == "🔒 بستن سرویس‌های زیرمجموعه‌ای")
async def close_referral_start(msg: Message, state: FSMContext):
    if not await is_admin(msg.from_user.id, "plans"):
        return
    await state.set_state(CloseReferralState.count)
    await msg.answer("🔒 چند نفر اول (جدیدترین‌ها) نمایش داده بشه؟ (عدد بزن، یا 0 برای همه)")


@router.message(CloseReferralState.count)
async def close_referral_list(msg: Message, state: FSMContext):
    try:
        n = int(msg.text.strip())
        if n < 0:
            raise ValueError
    except ValueError:
        await msg.answer("❌ یک عدد صحیح (یا 0 برای همه) وارد کن.")
        return
    await state.clear()
    async with AsyncSessionLocal() as db:
        svcs = await crud.get_referral_active_services(db, limit=(n or None))
    if not svcs:
        await msg.answer("سرویس فعالی از طریق زیرمجموعه‌گیری وجود نداره.")
        return
    await state.update_data(referral_svc_ids=[s.id for s in svcs])
    lines = [f"🔒 <b>{len(svcs)} سرویس از کاربران زیرمجموعه‌ای:</b>"]
    for i, s in enumerate(svcs, 1):
        lines.append(_fmt_referral_service_line(i, s))
    text = "\n".join(lines)
    if len(text) > 3500:
        text = text[:3500] + "\n...(لیست طولانی، فقط بخشی نمایش داده شد)"
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text=f"🗑 بستن همه ({len(svcs)}) یکجا", callback_data="close_ref_all"))
    b.row(InlineKeyboardButton(text="🔲 انتخاب تکی", callback_data="close_ref_pick"))
    b.row(InlineKeyboardButton(text="❌ انصراف", callback_data="cancel"))
    await msg.answer(text, parse_mode="HTML", reply_markup=b.as_markup())


@router.callback_query(F.data == "close_ref_all")
async def close_ref_all(cb: CallbackQuery, state: FSMContext):
    if not await is_admin(cb.from_user.id, "plans"):
        return
    await cb.answer("⏳ شروع شد...")
    data = await state.get_data()
    ids = data.get("referral_svc_ids", [])
    await state.clear()
    await cb.message.edit_text(f"⏳ در حال بستن {len(ids)} سرویس در پس‌زمینه... وقتی تموم شد پیام جدید می‌فرستم.")
    asyncio.create_task(_run_close_referral(cb.message.chat.id, cb.bot, ids))


async def _run_close_referral(chat_id: int, bot: Bot, ids):
    try:
        async with AsyncSessionLocal() as db:
            removed, failed = 0, 0
            for sid in ids:
                svc = await crud.get_service(db, sid)
                if not svc or svc.status != ServiceStatus.ACTIVE:
                    continue
                ok = False
                try:
                    ok = await panel.delete_client(svc.inbound_id, svc.panel_uuid, email=svc.panel_email)
                except Exception:
                    ok = False
                await crud.update_service(db, svc.id, status=ServiceStatus.EXPIRED, panel_removed=ok)
                if ok:
                    removed += 1
                else:
                    failed += 1
        text = f"✅ بستن سرویس‌ها تمام شد.\n{removed} سرویس بی‌سروصدا از پنل بسته شد."
        if failed:
            text += f"\n⚠️ {failed} سرویس در دیتابیس غیرفعال شد ولی حذف از پنل ناموفق بود."
        await bot.send_message(chat_id, text)
    except Exception as e:
        logger.error(f"_run_close_referral crashed: {e}")
        try:
            await bot.send_message(chat_id, f"❌ خطا: {type(e).__name__}: {e}")
        except Exception:
            pass


@router.callback_query(F.data == "close_ref_pick")
async def close_ref_pick(cb: CallbackQuery, state: FSMContext):
    if not await is_admin(cb.from_user.id, "plans"):
        return
    data = await state.get_data()
    ids = data.get("referral_svc_ids", [])
    async with AsyncSessionLocal() as db:
        svcs = []
        for sid in ids:
            svc = await crud.get_service(db, sid)
            if svc:
                svcs.append(svc)
    await state.set_state(CloseReferralState.select_active)
    await state.update_data(referral_svc_ids=ids, selected_ref_ids=[])
    await cb.message.edit_text("🔲 سرویس‌هایی که می‌خوای ببندی رو انتخاب کن:", reply_markup=referral_services_select_kb(svcs, []))


@router.callback_query(F.data.startswith("selref:"), CloseReferralState.select_active)
async def toggle_ref_select(cb: CallbackQuery, state: FSMContext):
    sid = int(cb.data.split(":")[1])
    data = await state.get_data()
    selected = set(data.get("selected_ref_ids", []))
    if sid in selected:
        selected.discard(sid)
    else:
        selected.add(sid)
    await state.update_data(selected_ref_ids=list(selected))
    ids = data.get("referral_svc_ids", [])
    async with AsyncSessionLocal() as db:
        svcs = []
        for i in ids:
            svc = await crud.get_service(db, i)
            if svc:
                svcs.append(svc)
    await cb.message.edit_reply_markup(reply_markup=referral_services_select_kb(svcs, selected))


@router.callback_query(F.data == "close_ref_selected", CloseReferralState.select_active)
async def close_ref_selected(cb: CallbackQuery, state: FSMContext):
    if not await is_admin(cb.from_user.id, "plans"):
        return
    data = await state.get_data()
    selected = data.get("selected_ref_ids", [])
    if not selected:
        await cb.answer("هیچ سرویسی انتخاب نشده!", show_alert=True)
        return
    await cb.answer("⏳ شروع شد...")
    await state.clear()
    await cb.message.edit_text(f"⏳ در حال بستن {len(selected)} سرویس در پس‌زمینه... وقتی تموم شد پیام جدید می‌فرستم.")
    asyncio.create_task(_run_close_referral(cb.message.chat.id, cb.bot, selected))


# ---------------- Backup / Restore ----------------

@router.message(F.text == "💾 بکاپ‌گیری")
async def do_backup(msg: Message, bot: Bot):
    if not await is_admin(msg.from_user.id, "all"):
        return
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    try:
        await bot.send_document(
            msg.from_user.id,
            FSInputFile("/opt/vpnbot/vpnbot.db", filename=f"backup_{ts}.db"),
            caption=f"💾 بکاپ دیتابیس - {ts}"
        )
    except Exception as e:
        await msg.answer(f"❌ خطا در گرفتن بکاپ: {e}")


class RestoreState(StatesGroup):
    waiting_file = State()


@router.message(F.text == "♻️ بازیابی بکاپ")
async def restore_start(msg: Message, state: FSMContext):
    if not await is_admin(msg.from_user.id, "all"):
        return
    await state.set_state(RestoreState.waiting_file)
    await msg.answer("♻️ فایل بکاپ (.db) رو همین‌جا ارسال کن:")


@router.message(RestoreState.waiting_file, F.document)
async def restore_apply(msg: Message, state: FSMContext, bot: Bot):
    await state.clear()
    if not msg.document.file_name.endswith(".db"):
        await msg.answer("❌ فایل باید پسوند .db داشته باشه.")
        return
    try:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        import shutil
        shutil.copy("/opt/vpnbot/vpnbot.db", f"/opt/vpnbot/vpnbot_before_restore_{ts}.db")
        file = await bot.get_file(msg.document.file_id)
        await bot.download_file(file.file_path, "/opt/vpnbot/vpnbot.db")
        await msg.answer("✅ بازیابی انجام شد. برای اعمال کامل، ربات را ری‌استارت کنید:\nsystemctl restart vpnbot")
    except Exception as e:
        await msg.answer(f"❌ خطا در بازیابی: {e}")


# ---------------- Bot on/off toggle ----------------

class BotOffState(StatesGroup):
    reason = State()


@router.message(F.text == "🔌 خاموش/روشن ربات")
async def bot_toggle_start(msg: Message, state: FSMContext):
    if not await is_admin(msg.from_user.id, "all"):
        return
    async with AsyncSessionLocal() as db:
        current = await crud.get_setting(db, "bot_enabled", "true")
    if current == "true":
        await state.set_state(BotOffState.reason)
        await msg.answer("🔌 ربات خاموش می‌شود. دلیلش را بنویس (مثلاً «در حال بروزرسانی»):")
    else:
        async with AsyncSessionLocal() as db:
            await crud.set_setting(db, "bot_enabled", "true")
        await msg.answer("🟢 ربات دوباره روشن شد.")


@router.message(BotOffState.reason)
async def bot_off_apply(msg: Message, state: FSMContext):
    await state.clear()
    async with AsyncSessionLocal() as db:
        await crud.set_setting(db, "bot_enabled", "false")
        await crud.set_setting(db, "bot_off_reason", msg.text.strip())
    await msg.answer(f"🔴 ربات خاموش شد.\n📝 دلیل نمایش‌داده‌شده به کاربران: {msg.text.strip()}\n\nبرای روشن کردن دوباره، «🔌 خاموش/روشن ربات» را بزن.")


# ---------------- Bulk-assign plans to a category ----------------

class BulkSelectState(StatesGroup):
    active = State()


@router.callback_query(F.data == "admin_plans_select")
async def start_plan_select(cb: CallbackQuery, state: FSMContext):
    if not await is_admin(cb.from_user.id, "plans"):
        return
    async with AsyncSessionLocal() as db:
        plans = await crud.get_all_plans(db)
    await state.set_state(BulkSelectState.active)
    await state.update_data(selected_plan_ids=[])
    await cb.message.edit_text("🔲 پلن‌هایی که می‌خوای به یه دسته‌بندی اضافه کنی رو انتخاب کن:", reply_markup=admin_plans_select_kb(plans, []))


@router.callback_query(F.data.startswith("selplan:"), BulkSelectState.active)
async def toggle_plan_select(cb: CallbackQuery, state: FSMContext):
    pid = int(cb.data.split(":")[1])
    data = await state.get_data()
    selected = set(data.get("selected_plan_ids", []))
    if pid in selected:
        selected.discard(pid)
    else:
        selected.add(pid)
    await state.update_data(selected_plan_ids=list(selected))
    async with AsyncSessionLocal() as db:
        plans = await crud.get_all_plans(db)
    await cb.message.edit_reply_markup(reply_markup=admin_plans_select_kb(plans, selected))


@router.callback_query(F.data == "bulk_add_cat", BulkSelectState.active)
async def bulk_add_cat_start(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected = data.get("selected_plan_ids", [])
    if not selected:
        await cb.answer("هیچ پلنی انتخاب نشده!", show_alert=True)
        return
    async with AsyncSessionLocal() as db:
        cats = await crud.get_all_categories(db)
    if not cats:
        await cb.answer("هنوز دسته‌بندی‌ای نساختی!", show_alert=True)
        return
    await cb.message.edit_text(f"🗂 {len(selected)} پلن انتخاب شده. به کدام دسته‌بندی اضافه بشن؟", reply_markup=plan_cat_select_kb(cats, prefix="bulkcat"))


@router.callback_query(F.data.startswith("bulkcat:"), BulkSelectState.active)
async def bulk_add_cat_apply(cb: CallbackQuery, state: FSMContext):
    cat_part = cb.data.split(":")[1]
    category_id = None if cat_part == "none" else int(cat_part)
    data = await state.get_data()
    selected = data.get("selected_plan_ids", [])
    await state.clear()
    async with AsyncSessionLocal() as db:
        for pid in selected:
            await crud.update_plan(db, pid, category_id=category_id)
    await cb.message.edit_text(f"✅ {len(selected)} پلن به دسته‌بندی انتخابی اضافه شدن.")


@router.callback_query(F.data == "cancel_select_mode")
async def cancel_select_mode(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    async with AsyncSessionLocal() as db:
        plans = await crud.get_all_plans(db)
    await cb.message.edit_text("📦 مدیریت پلن‌ها", reply_markup=admin_plans_kb(plans))
