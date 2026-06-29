import logging
import io
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from database.db import AsyncSessionLocal, TransactionType, PaymentMethod, PaymentStatus, UserStatus
from database import crud
from panels.sanei import panel
from bot.keyboards import (
    main_menu_kb, categories_kb, plans_kb, confirm_plan_kb,
    wallet_kb, charge_amounts_kb, service_detail_kb, back_kb,
    force_join_kb, renew_kb
)
from config import config

logger = logging.getLogger(__name__)
router = Router()

PERMISSIONS = [
    "payment", "broadcast", "plans", "stats", "lottery", "ban", "settings", "all"
]

PERM_NAMES = {
    "payment": "تایید پرداخت",
    "broadcast": "پیام همگانی",
    "plans": "مدیریت پلن‌ها",
    "stats": "آمار",
    "lottery": "قرعه‌کشی",
    "ban": "بن کاربر",
    "settings": "تنظیمات",
    "all": "همه دسترسی‌ها",
}


class BuyState(StatesGroup):
    waiting_discount = State()


class ChargeState(StatesGroup):
    waiting_custom_amount = State()
    waiting_receipt = State()


class RenameState(StatesGroup):
    waiting_name = State()


async def check_force_join(bot: Bot, user_id: int) -> list:
    async with AsyncSessionLocal() as db:
        enabled = await crud.get_setting(db, "force_join_enabled", "false")
        if enabled != "true":
            return []
        channels = await crud.get_active_force_joins(db)
    not_joined = []
    for ch in channels:
        try:
            member = await bot.get_chat_member(ch.channel_id, user_id)
            if member.status in ("left", "kicked"):
                not_joined.append(ch)
        except Exception:
            not_joined.append(ch)
    return not_joined


async def is_admin_user(user_id: int) -> bool:
    if user_id in config.ADMIN_IDS:
        return True
    async with AsyncSessionLocal() as db:
        admin = await crud.get_admin(db, user_id)
        return admin is not None and admin.is_active


# ─── /start ──────────────────────────────────────────────────────────────────

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
        user, is_new = await crud.get_or_create_user(
            db, msg.from_user.id,
            username=msg.from_user.username,
            full_name=msg.from_user.full_name,
            referred_by=ref_id if ref_id and ref_id != msg.from_user.id else None
        )
        if user.status == UserStatus.BANNED:
            await msg.answer("⛔️ حساب شما مسدود شده است.")
            return
        if is_new and ref_id and ref_id != msg.from_user.id:
            referrer = await crud.get_user(db, ref_id)
            if referrer:
                reward = int(await crud.get_setting(db, "referral_reward", "50000"))
                await crud.update_wallet(db, referrer, reward,
                    f"پاداش دعوت {msg.from_user.full_name}", TransactionType.REFERRAL)
                try:
                    await msg.bot.send_message(ref_id,
                        f"🎊 یک نفر با لینک دعوت شما وارد ربات شد!\n"
                        f"💰 {reward:,} تومان به کیف پول شما اضافه شد.")
                except Exception:
                    pass
        settings = await crud.get_all_settings(db)

    not_joined = await check_force_join(msg.bot, msg.from_user.id)
    if not_joined:
        await msg.answer(
            "📢 برای استفاده از ربات ابتدا در کانال‌های زیر عضو شوید:",
            reply_markup=force_join_kb(not_joined)
        )
        return

    bot_name = settings.get("bot_name", "فروشگاه VPN")
    welcome = settings.get("welcome_text", "👋 سلام {name} عزیز!\n\n🌐 به {bot_name} خوش آمدید.\n\nاز منوی زیر گزینه مورد نظر را انتخاب کنید 👇")
    welcome = welcome.replace("{name}", msg.from_user.first_name or "کاربر")
    welcome = welcome.replace("{bot_name}", bot_name)

    is_admin = await is_admin_user(msg.from_user.id)
    if is_admin:
        from bot.handlers.admin import admin_menu_kb
        await msg.answer(welcome, reply_markup=admin_menu_kb())
    else:
        await msg.answer(welcome, reply_markup=main_menu_kb(settings))


@router.callback_query(F.data == "check_join")
async def check_join_cb(cb: CallbackQuery):
    not_joined = await check_force_join(cb.bot, cb.from_user.id)
    if not_joined:
        await cb.answer("❌ هنوز در همه کانال‌ها عضو نشدید!", show_alert=True)
        return
    await cb.message.delete()
    async with AsyncSessionLocal() as db:
        settings = await crud.get_all_settings(db)
    bot_name = settings.get("bot_name", "فروشگاه VPN")
    welcome = settings.get("welcome_text", "👋 خوش آمدید!")
    welcome = welcome.replace("{name}", cb.from_user.first_name or "کاربر")
    welcome = welcome.replace("{bot_name}", bot_name)
    await cb.message.answer(welcome, reply_markup=main_menu_kb(settings))


# ─── BUY ─────────────────────────────────────────────────────────────────────

@router.message(F.text.startswith("🛒"))
async def buy_service(msg: Message):
    async with AsyncSessionLocal() as db:
        cats = await crud.get_active_categories(db)
        settings = await crud.get_all_settings(db)
    buy_text = settings.get("buy_text", "🛒 خرید اشتراک\n\nلطفاً پروتکل مورد نظر را انتخاب کنید:")
    if cats:
        await msg.answer(buy_text, reply_markup=categories_kb(cats))
    else:
        async with AsyncSessionLocal() as db:
            plans = await crud.get_active_plans(db)
        if not plans:
            await msg.answer("❌ در حال حاضر پلنی فعال نیست.")
            return
        await msg.answer(buy_text, reply_markup=plans_kb(plans))


@router.callback_query(F.data.startswith("cat:"))
async def select_category(cb: CallbackQuery):
    cat_id = int(cb.data.split(":")[1])
    async with AsyncSessionLocal() as db:
        plans = await crud.get_active_plans(db, category_id=cat_id)
        cat = await crud.get_category(db, cat_id)
    if not plans:
        await cb.answer("❌ پلنی در این دسته‌بندی وجود ندارد.", show_alert=True)
        return
    await cb.message.edit_text(
        f"{cat.icon} <b>{cat.name}</b>\n\nیک پلن انتخاب کنید:",
        reply_markup=plans_kb(plans, back_cat_id=cat_id),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "buy_back")
async def buy_back(cb: CallbackQuery):
    async with AsyncSessionLocal() as db:
        cats = await crud.get_active_categories(db)
        settings = await crud.get_all_settings(db)
    buy_text = settings.get("buy_text", "🛒 خرید اشتراک")
    await cb.message.edit_text(buy_text, reply_markup=categories_kb(cats))


@router.callback_query(F.data.startswith("plan:"))
async def select_plan(cb: CallbackQuery):
    plan_id = int(cb.data.split(":")[1])
    async with AsyncSessionLocal() as db:
        plan = await crud.get_plan(db, plan_id)
        user = await crud.get_user(db, cb.from_user.id)
        if not user:
            user, _ = await crud.get_or_create_user(db, cb.from_user.id,
                cb.from_user.username, cb.from_user.full_name)
    if not plan:
        await cb.answer("❌ پلن یافت نشد!", show_alert=True)
        return
    wallet_ok = user.wallet >= plan.price
    await cb.message.edit_text(
        f"📦 <b>{plan.name}</b>\n\n"
        f"🔹 حجم: {plan.traffic_gb} GB\n"
        f"📅 مدت: {plan.days} روز\n"
        f"💰 قیمت: <b>{int(plan.price):,} تومان</b>\n"
        f"👛 کیف پول شما: <b>{int(user.wallet):,} تومان</b>\n\n"
        f"{'✅ موجودی کافی است' if wallet_ok else '❌ موجودی ناکافی - لطفاً کیف پول را شارژ کنید'}",
        reply_markup=confirm_plan_kb(plan_id, plan.price),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("add_discount:"))
async def ask_discount(cb: CallbackQuery, state: FSMContext):
    plan_id = int(cb.data.split(":")[1])
    await state.set_state(BuyState.waiting_discount)
    await state.update_data(plan_id=plan_id)
    await cb.message.edit_text("🏷 کد تخفیف خود را وارد کنید:", reply_markup=back_kb("cancel"))


@router.message(BuyState.waiting_discount)
async def apply_discount(msg: Message, state: FSMContext):
    data = await state.get_data()
    code = msg.text.strip().upper()
    async with AsyncSessionLocal() as db:
        plan = await crud.get_plan(db, data["plan_id"])
        dc = await crud.get_discount(db, code)
    if not dc:
        await msg.answer("❌ کد تخفیف نامعتبر یا منقضی شده است.")
        return
    final = plan.price * (1 - dc.percent / 100)
    await state.clear()
    await msg.answer(
        f"✅ کد <b>{code}</b> اعمال شد!\n"
        f"تخفیف: {dc.percent}%\n"
        f"💰 قیمت نهایی: <b>{int(final):,} تومان</b>",
        reply_markup=confirm_plan_kb(data["plan_id"], final, code),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("confirm_buy:"))
async def confirm_buy(cb: CallbackQuery, state: FSMContext):
    parts = cb.data.split(":")
    plan_id = int(parts[1])
    discount_code = parts[2] if len(parts) > 2 else ""

    async with AsyncSessionLocal() as db:
        plan = await crud.get_plan(db, plan_id)
        user = await crud.get_user(db, cb.from_user.id)
        if not user:
            user, _ = await crud.get_or_create_user(db, cb.from_user.id,
                cb.from_user.username, cb.from_user.full_name)
        final_price = plan.price
        dc = None
        if discount_code:
            dc = await crud.get_discount(db, discount_code)
            if dc:
                final_price = plan.price * (1 - dc.percent / 100)

        auto_send = await crud.get_setting(db, "auto_config_send", "true")

        if user.wallet < final_price:
            # کیف پول کافی نیست - نمایش روش پرداخت
            card = await crud.get_setting(db, "card_number", "")
            zarinpal = await crud.get_setting(db, "zarinpal_merchant", "")
            pay = await crud.create_payment(db, user.id, final_price, PaymentMethod.CARD, plan_id=plan_id)
            await cb.message.edit_text(
                f"❌ موجودی کافی نیست!\n\n"
                f"💰 موجودی شما: {int(user.wallet):,} تومان\n"
                f"💵 مبلغ لازم: {int(final_price):,} تومان\n\n"
                f"لطفاً کیف پول خود را شارژ کنید یا مستقیم پرداخت کنید:",
                reply_markup=wallet_kb(has_zarinpal=bool(zarinpal), has_card=bool(card))
            )
            return

        # پرداخت از کیف پول
        inbound_id = int(plan.inbound_id or await crud.get_setting(db, "inbound_id", "1"))
        panel_url = await crud.get_setting(db, "panel_url", "")
        panel_path = await crud.get_setting(db, "panel_path", "")

        if auto_send == "true":
            # ارسال خودکار
            import random, string
            email = f"u{cb.from_user.id}{''.join(random.choices(string.ascii_lowercase, k=4))}"
            result = await panel.add_client(inbound_id, email, plan.traffic_gb, plan.days)
            if not result:
                await cb.answer("❌ خطا در اتصال به پنل. با پشتیبانی تماس بگیرید.", show_alert=True)
                return
            sub_link = panel.get_subscription_url(panel_url, panel_path, email)
            vless_link = f"vless://{result['uuid']}@{panel_url.replace('https://', '').replace('http://', '').split(':')[0]}?type=ws&security=tls&host={panel_url.replace('https://', '').replace('http://', '').split(':')[0]}&path=%2F#{email}"
            svc = await crud.create_service(
                db, user.id, plan_id, result["uuid"], email,
                inbound_id, plan.traffic_gb, plan.days,
                sub_link=sub_link, vless_link=vless_link
            )
            await crud.update_wallet(db, user, -final_price, f"خرید {plan.name}", TransactionType.PURCHASE)
            if dc:
                await crud.use_discount(db, dc)

            await cb.message.edit_text(
                f"🎉 <b>خرید موفق!</b>\n\n"
                f"📦 پلن: {plan.name}\n"
                f"📊 حجم: {plan.traffic_gb} GB | 📅 مدت: {plan.days} روز\n"
                f"💰 پرداخت: {int(final_price):,} تومان\n\n"
                f"🔗 <b>لینک سابسکریپشن:</b>\n<code>{sub_link}</code>",
                parse_mode="HTML"
            )
            # ارسال QR code
            try:
                import qrcode
                qr = qrcode.make(sub_link)
                buf = io.BytesIO()
                qr.save(buf, format="PNG")
                buf.seek(0)
                await cb.message.answer_photo(
                    BufferedInputFile(buf.read(), "qr.png"),
                    caption="📷 QR Code سرویس شما"
                )
            except Exception:
                pass
        else:
            # ارسال دستی
            pay = await crud.create_payment(db, user.id, final_price, PaymentMethod.CARD, plan_id=plan_id)
            await crud.update_wallet(db, user, -final_price, f"خرید {plan.name}", TransactionType.PURCHASE)
            if dc:
                await crud.use_discount(db, dc)
            await cb.message.edit_text(
                f"✅ سفارش شما ثبت شد!\n\n"
                f"📦 پلن: {plan.name}\n"
                f"💰 مبلغ: {int(final_price):,} تومان\n\n"
                f"⏳ سرویس شما پس از بررسی توسط پشتیبانی ارسال می‌شود.\n"
                f"به بخش <b>سرویس‌های من</b> مراجعه کنید.",
                parse_mode="HTML"
            )
            # نوتیف به ادمین‌ها
            for admin_id in config.ADMIN_IDS:
                try:
                    await cb.bot.send_message(
                        admin_id,
                        f"🛒 <b>سفارش جدید</b>\n\n"
                        f"👤 {cb.from_user.full_name} (@{cb.from_user.username or '-'})\n"
                        f"🆔 <code>{cb.from_user.id}</code>\n"
                        f"📦 {plan.name} | {int(final_price):,} تومان",
                        parse_mode="HTML"
                    )
                except Exception:
                    pass

    await state.clear()


@router.callback_query(F.data == "cancel")
async def cancel_cb(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await cb.message.delete()
    except Exception:
        pass


# ─── FREE TEST ────────────────────────────────────────────────────────────────

@router.message(F.text.startswith("🎁"))
async def free_test(msg: Message):
    async with AsyncSessionLocal() as db:
        enabled = await crud.get_setting(db, "free_test_enabled", "true")
        if enabled != "true":
            await msg.answer("❌ تست رایگان در حال حاضر فعال نیست.")
            return
        user = await crud.get_user(db, msg.from_user.id)
        if not user:
            user, _ = await crud.get_or_create_user(db, msg.from_user.id,
                msg.from_user.username, msg.from_user.full_name)
        if user.has_used_test:
            await msg.answer("⚠️ شما قبلاً از تست رایگان استفاده کرده‌اید.")
            return
        traffic_mb = int(await crud.get_setting(db, "free_test_traffic_mb", "500"))
        days = int(await crud.get_setting(db, "free_test_days", "1"))
        inbound_id = int(await crud.get_setting(db, "inbound_id", "1"))
        panel_url = await crud.get_setting(db, "panel_url", "")
        panel_path = await crud.get_setting(db, "panel_path", "")

    traffic_gb = max(1, traffic_mb // 1024) if traffic_mb >= 1024 else 1
    traffic_bytes_actual = traffic_mb * 1024 * 1024

    await msg.answer("⏳ در حال ساخت سرویس تست...")

    import random, string
    email = f"test{msg.from_user.id}{''.join(random.choices(string.ascii_lowercase, k=4))}"

    result = await panel.add_client(inbound_id, email, traffic_gb, days)
    if not result:
        await msg.answer("❌ خطا در ساخت سرویس. لطفاً بعداً امتحان کنید.")
        return

    async with AsyncSessionLocal() as db:
        sub_link = panel.get_subscription_url(panel_url, panel_path, email)
        svc = await crud.create_service(
            db, user.id, None, result["uuid"], email,
            inbound_id, traffic_gb, days, is_test=True, sub_link=sub_link
        )
        user.has_used_test = True
        await db.commit()

    await msg.answer(
        f"🎁 <b>سرویس تست رایگان آماده شد!</b>\n\n"
        f"📊 حجم: {traffic_mb} مگابایت\n"
        f"📅 مدت: {days} روز\n\n"
        f"🔗 <b>لینک سابسکریپشن:</b>\n<code>{sub_link}</code>\n\n"
        f"این لینک را در v2rayNG یا Hiddify وارد کنید.",
        parse_mode="HTML"
    )


# ─── MY SERVICES ─────────────────────────────────────────────────────────────

@router.message(F.text.startswith("📦"))
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
        text = "📦 شما هنوز سرویس فعالی ندارید.\n\nاز «🛒 خرید اشتراک» اقدام کنید."
        if is_cb:
            await msg.edit_text(text)
        else:
            await msg.answer(text)
        return

    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    buttons = []
    for svc in services:
        icon = "🎁" if svc.is_test else "📦"
        name = svc.service_name or f"{icon} {svc.traffic_gb}GB/{svc.days}روز"
        buttons.append([InlineKeyboardButton(text=name, callback_data=f"svc:{svc.id}")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    text = f"📦 <b>سرویس‌های شما ({len(services)} عدد)</b>\nروی هر سرویس کلیک کنید:"
    if is_cb:
        await msg.edit_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await msg.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("svc:"))
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
    name = svc.service_name or svc.panel_email
    await cb.message.edit_text(
        f"📦 <b>{name}</b>\n\n"
        f"📊 حجم کل: {svc.traffic_gb} GB\n"
        f"📉 مصرف شده: {used} GB\n"
        f"📈 باقی‌مانده: {remaining} GB\n"
        f"📅 انقضا: {expires}\n"
        f"{'🎁 تست رایگان' if svc.is_test else '💎 سرویس اصلی'}",
        reply_markup=service_detail_kb(svc.id),
        parse_mode="HTML"
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
        f"🔗 <b>لینک سابسکریپشن:</b>\n<code>{svc.sub_link}</code>\n\n"
        f"در v2rayNG / Hiddify / Nekoray وارد کنید.",
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("vless_link:"))
async def send_vless_link(cb: CallbackQuery):
    svc_id = int(cb.data.split(":")[1])
    async with AsyncSessionLocal() as db:
        svc = await crud.get_service(db, svc_id)
    if not svc:
        await cb.answer("سرویس یافت نشد!", show_alert=True)
        return
    link = svc.vless_link or svc.sub_link or "لینک موجود نیست"
    await cb.message.answer(
        f"📋 <b>کانفیگ VLESS:</b>\n<code>{link}</code>",
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("qr_code:"))
async def send_qr(cb: CallbackQuery):
    svc_id = int(cb.data.split(":")[1])
    async with AsyncSessionLocal() as db:
        svc = await crud.get_service(db, svc_id)
    if not svc or not svc.sub_link:
        await cb.answer("لینک موجود نیست!", show_alert=True)
        return
    try:
        import qrcode
        qr = qrcode.make(svc.sub_link)
        buf = io.BytesIO()
        qr.save(buf, format="PNG")
        buf.seek(0)
        await cb.message.answer_photo(
            BufferedInputFile(buf.read(), "qr.png"),
            caption="📷 QR Code سرویس شما"
        )
    except ImportError:
        await cb.answer("کتابخانه QR نصب نیست.", show_alert=True)


@router.callback_query(F.data.startswith("rename_svc:"))
async def rename_svc(cb: CallbackQuery, state: FSMContext):
    svc_id = int(cb.data.split(":")[1])
    await state.set_state(RenameState.waiting_name)
    await state.update_data(svc_id=svc_id)
    await cb.message.answer("✏️ نام جدید برای سرویس خود وارد کنید:", reply_markup=back_kb("cancel"))


@router.message(RenameState.waiting_name)
async def do_rename(msg: Message, state: FSMContext):
    data = await state.get_data()
    svc_id = data["svc_id"]
    new_name = msg.text.strip()[:64]
    async with AsyncSessionLocal() as db:
        await crud.update_service(db, svc_id, service_name=new_name)
    await state.clear()
    await msg.answer(f"✅ نام سرویس به «{new_name}» تغییر یافت.")


@router.callback_query(F.data.startswith("refresh_svc:"))
async def refresh_svc(cb: CallbackQuery):
    await svc_detail(cb)


# ─── WALLET ──────────────────────────────────────────────────────────────────

@router.message(F.text.startswith("💰"))
async def wallet_menu(msg: Message):
    async with AsyncSessionLocal() as db:
        user = await crud.get_user(db, msg.from_user.id)
        if not user:
            user, _ = await crud.get_or_create_user(db, msg.from_user.id,
                msg.from_user.username, msg.from_user.full_name)
        card = await crud.get_setting(db, "card_number", "")
        zarinpal = await crud.get_setting(db, "zarinpal_merchant", "")
    await msg.answer(
        f"💰 <b>کیف پول</b>\n\n💵 موجودی: <b>{int(user.wallet):,} تومان</b>\n\nروش شارژ انتخاب کنید:",
        reply_markup=wallet_kb(has_zarinpal=bool(zarinpal), has_card=bool(card)),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("charge:"))
async def charge_start(cb: CallbackQuery, state: FSMContext):
    method = cb.data.split(":")[1]
    await state.update_data(method=method)
    await cb.message.edit_text("💰 مبلغ شارژ را انتخاب کنید:", reply_markup=charge_amounts_kb())


@router.callback_query(F.data.startswith("charge_amount:"))
async def charge_amount(cb: CallbackQuery, state: FSMContext):
    val = cb.data.split(":")[1]
    data = await state.get_data()
    method = data.get("method", "card")
    if val == "custom":
        await state.set_state(ChargeState.waiting_custom_amount)
        await cb.message.edit_text("💰 مبلغ دلخواه را به تومان وارد کنید:", reply_markup=back_kb("cancel"))
        return
    await _process_charge(cb, state, int(val), method)


@router.message(ChargeState.waiting_custom_amount)
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
    await _process_charge_msg(msg, state, amount, data.get("method", "card"))


async def _process_charge(cb: CallbackQuery, state: FSMContext, amount: int, method: str):
    if method == "card":
        await state.update_data(amount=amount)
        await state.set_state(ChargeState.waiting_receipt)
        async with AsyncSessionLocal() as db:
            card = await crud.get_setting(db, "card_number", "")
            holder = await crud.get_setting(db, "card_holder", "")
        await cb.message.edit_text(
            f"🏦 <b>کارت به کارت</b>\n\n"
            f"💰 مبلغ: <b>{amount:,} تومان</b>\n\n"
            f"واریز به:\n<code>{card}</code>\nبه نام: {holder}\n\n"
            f"✅ پس از واریز، تصویر رسید را ارسال کنید:",
            parse_mode="HTML", reply_markup=back_kb("cancel")
        )


async def _process_charge_msg(msg: Message, state: FSMContext, amount: int, method: str):
    if method == "card":
        await state.update_data(amount=amount)
        await state.set_state(ChargeState.waiting_receipt)
        async with AsyncSessionLocal() as db:
            card = await crud.get_setting(db, "card_number", "")
            holder = await crud.get_setting(db, "card_holder", "")
        await msg.answer(
            f"🏦 <b>کارت به کارت</b>\n\n💰 مبلغ: <b>{amount:,} تومان</b>\n\n"
            f"واریز به:\n<code>{card}</code>\nبه نام: {holder}\n\n"
            f"✅ تصویر رسید را ارسال کنید:",
            parse_mode="HTML", reply_markup=back_kb("cancel")
        )


@router.message(ChargeState.waiting_receipt, F.photo)
async def receipt_received(msg: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    amount = data["amount"]
    file_id = msg.photo[-1].file_id
    async with AsyncSessionLocal() as db:
        user = await crud.get_user(db, msg.from_user.id)
        if not user:
            user, _ = await crud.get_or_create_user(db, msg.from_user.id,
                msg.from_user.username, msg.from_user.full_name)
        pay = await crud.create_payment(db, user.id, amount, PaymentMethod.CARD)
        pay.receipt_file_id = file_id
        await db.commit()
        pay_id = pay.id
    await state.clear()
    await msg.answer("✅ رسید دریافت شد. پس از تأیید ادمین، کیف پول شما شارژ می‌شود.")
    from bot.keyboards import payment_confirm_kb
    for admin_id in config.ADMIN_IDS:
        try:
            await bot.send_photo(
                admin_id, file_id,
                caption=(
                    f"💳 <b>درخواست شارژ</b>\n\n"
                    f"👤 {msg.from_user.full_name} (@{msg.from_user.username or '-'})\n"
                    f"🆔 <code>{msg.from_user.id}</code>\n"
                    f"💰 {amount:,} تومان"
                ),
                reply_markup=payment_confirm_kb(pay_id, msg.from_user.id),
                parse_mode="HTML"
            )
        except Exception:
            pass


# ─── REFERRAL ────────────────────────────────────────────────────────────────

@router.message(F.text.startswith("👥"))
async def referral_menu(msg: Message):
    async with AsyncSessionLocal() as db:
        user = await crud.get_user(db, msg.from_user.id)
        if not user:
            user, _ = await crud.get_or_create_user(db, msg.from_user.id,
                msg.from_user.username, msg.from_user.full_name)
        ref_count = await crud.count_referrals(db, msg.from_user.id)
        reward = int(await crud.get_setting(db, "referral_reward", "50000"))
    bot_me = await msg.bot.get_me()
    ref_link = f"https://t.me/{bot_me.username}?start=ref_{msg.from_user.id}"
    await msg.answer(
        f"👥 <b>شارژ رایگان با دعوت دوستان</b>\n\n"
        f"به ازای هر دوست که با لینک شما وارد ربات شود،\n"
        f"💰 <b>{reward:,} تومان</b> به کیف پول شما اضافه می‌شود!\n\n"
        f"👤 دعوت‌های موفق: <b>{ref_count} نفر</b>\n"
        f"💵 موجودی شما: <b>{int(user.wallet):,} تومان</b>\n\n"
        f"🔗 <b>لینک اختصاصی:</b>\n<code>{ref_link}</code>",
        parse_mode="HTML"
    )


# ─── LOTTERY ─────────────────────────────────────────────────────────────────

@router.message(F.text.startswith("🏆"))
async def lottery_menu(msg: Message):
    async with AsyncSessionLocal() as db:
        user = await crud.get_user(db, msg.from_user.id)
        if not user:
            user, _ = await crud.get_or_create_user(db, msg.from_user.id,
                msg.from_user.username, msg.from_user.full_name)
        num = await crud.get_or_create_lottery_number(db, user)
        is_active = await crud.get_setting(db, "lottery_active", "false")
        participants = await crud.get_lottery_participants_count(db)
    status = "🟢 مسابقه فعال است" if is_active == "true" else "🔴 مسابقه‌ای در حال برگزاری نیست"
    await msg.answer(
        f"🏆 <b>مسابقه و قرعه‌کشی</b>\n\n"
        f"{status}\n\n"
        f"👥 شرکت‌کنندگان: <b>{participants} نفر</b>\n\n"
        f"🎫 <b>شماره شانس شما:</b>\n\n"
        f"┌──────────────┐\n"
        f"│  <b>  {num}  </b>│\n"
        f"└──────────────┘\n\n"
        f"این شماره منحصربه‌فرد شماست 🍀\n"
        f"منتظر اعلام نتیجه باشید!",
        parse_mode="HTML"
    )


# ─── SUPPORT & GUIDE ─────────────────────────────────────────────────────────

@router.message(F.text.startswith("📞"))
async def support_menu(msg: Message):
    async with AsyncSessionLocal() as db:
        support = await crud.get_setting(db, "support_username", "")
        bot_name = await crud.get_setting(db, "bot_name", "VPN")
    s = f"@{support}" if support else "از طریق ربات"
    await msg.answer(
        f"📞 <b>پشتیبانی {bot_name}</b>\n\n"
        f"برای ارتباط با پشتیبانی:\n{s}\n\n"
        f"⏰ ساعات پاسخگویی: ۹ صبح تا ۱۲ شب",
        parse_mode="HTML"
    )


@router.message(F.text.startswith("📖"))
async def guide_menu(msg: Message):
    await msg.answer(
        "📖 <b>آموزش اتصال</b>\n\n"
        "1️⃣ <b>اندروید:</b> v2rayNG یا Hiddify\n"
        "2️⃣ <b>iOS:</b> Streisand یا Shadowrocket\n"
        "3️⃣ <b>ویندوز:</b> Hiddify یا v2rayN\n"
        "4️⃣ <b>مک:</b> FoXray\n\n"
        "📌 پس از دریافت سرویس:\n"
        "• لینک سابسکریپشن را کپی کنید\n"
        "• در اپلیکیشن وارد کنید\n"
        "• اتصال را شروع کنید ✅",
        parse_mode="HTML"
    )
