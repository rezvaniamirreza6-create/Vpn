python3 << 'FIXEOF'
BASE = "/opt/vpnbot"

def patch(path, old, new, label):
    full = f"{BASE}/{path}"
    with open(full, "r", encoding="utf-8") as f:
        content = f.read()
    if new.strip() and new in content:
        print(f"⏭️  {label}: قبلاً اعمال شده، رد شد")
        return
    if old in content:
        content = content.replace(old, new)
        with open(full, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"✅ {label}: اعمال شد")
    else:
        print(f"⚠️  {label}: الگو پیدا نشد (شاید قبلاً دستی تغییر کرده)")

# ---------- 1) database/crud.py : برترین‌ها + جستجو + ریست تست ----------
patch("database/crud.py",
old='''async def reset_lottery(db):
    """Clears every participant's lottery number so the next round starts fresh
    with brand-new, non-repeating numbers."""
    await db.execute(update(User).where(User.lottery_number.isnot(None)).values(lottery_number=None))
    await db.commit()''',
new='''async def reset_lottery(db):
    """Clears every participant's lottery number so the next round starts fresh
    with brand-new, non-repeating numbers."""
    await db.execute(update(User).where(User.lottery_number.isnot(None)).values(lottery_number=None))
    await db.commit()


async def get_top_referrers(db, limit=10):
    r = await db.execute(
        select(User.referred_by, func.count(User.id).label("cnt"))
        .where(User.referred_by.isnot(None))
        .group_by(User.referred_by)
        .order_by(func.count(User.id).desc())
        .limit(limit)
    )
    rows = r.all()
    result = []
    for tid, cnt in rows:
        u = await get_user(db, tid)
        result.append((u, tid, cnt))
    return result


async def get_top_buyers(db, limit=10):
    r = await db.execute(
        select(Payment.user_id, func.sum(Payment.amount).label("total"))
        .where(Payment.status == PaymentStatus.PAID)
        .group_by(Payment.user_id)
        .order_by(func.sum(Payment.amount).desc())
        .limit(limit)
    )
    rows = r.all()
    result = []
    for uid, total in rows:
        rr = await db.execute(select(User).where(User.id == uid))
        u = rr.scalar_one_or_none()
        result.append((u, total))
    return result


async def search_user(db, query):
    query = query.strip().lstrip("@")
    if query.isdigit():
        return await get_user(db, int(query))
    r = await db.execute(select(User).where(User.username == query))
    return r.scalar_one_or_none()


async def reset_all_tests(db):
    r = await db.execute(update(User).where(User.has_used_test == True).values(has_used_test=False))
    await db.commit()
    return r.rowcount''',
label="crud.py -> برترین معرف‌ها/خریداران، جستجوی کاربر، ریست تست")

# ---------- 2) bot/keyboards.py : دکمه‌های منوی جدید ----------
patch("bot/keyboards.py",
old='''    ("🎫 کد تخفیف", "discount"),
    ("🚫 بن کاربر", "ban"),''',
new='''    ("🎫 کد تخفیف", "discount"),
    ("📈 برترین معرف‌ها", "stats"),
    ("💎 برترین خریداران", "stats"),
    ("🔍 جستجوی کاربر", "user_manage"),
    ("♻️ ریست تست رایگان", "settings"),
    ("🚫 بن کاربر", "ban"),''',
label="keyboards.py -> دکمه‌های جدید در منوی ادمین")

# ---------- 3) bot/handlers/admin.py ----------
patch("bot/handlers/admin.py",
old='''from database.db import AsyncSessionLocal, TransactionType, UserStatus, PaymentStatus, PaymentMethod''',
new='''from database.db import AsyncSessionLocal, TransactionType, UserStatus, PaymentStatus, PaymentMethod, ServiceStatus''',
label="admin.py -> ایمپورت ServiceStatus")

patch("bot/handlers/admin.py",
old='''    "discount": "🎫 کد تخفیف", "all": "🔑 همه",
}''',
new='''    "discount": "🎫 کد تخفیف", "user_manage": "🔍 جستجو/مدیریت کاربر", "all": "🔑 همه",
}''',
label="admin.py -> پرمیشن user_manage")

patch("bot/handlers/admin.py",
old='''@router.callback_query(F.data.startswith("del_discount:"))
async def del_discount(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id, "discount"):
        return
    did = int(cb.data.split(":")[1])
    async with AsyncSessionLocal() as db:
        await crud.delete_discount(db, did)
    await cb.message.edit_text("🗑 کد تخفیف حذف شد.")''',
new='''@router.callback_query(F.data.startswith("del_discount:"))
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
    text = (
        f"👤 <b>{user.full_name or '-'}</b>\n"
        f"🆔 <code>{user.telegram_id}</code>\n"
        f"👤 یوزرنیم: @{user.username or '-'}\n"
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
    return text, b.as_markup()


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
    async with AsyncSessionLocal() as db:
        svc = await crud.get_service(db, svc_id)
        if svc:
            try:
                await panel.delete_client(svc.inbound_id, svc.panel_uuid)
            except Exception:
                pass
            await crud.update_service(db, svc_id, status=ServiceStatus.EXPIRED)
    await cb.answer("سرویس غیرفعال شد.", show_alert=True)
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


@router.callback_query(F.data == "cancel")
async def cancel_action(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.edit_text("❌ لغو شد.")''',
label="admin.py -> برترین معرف‌ها/خریداران + جستجوی کاربر + ریست تست")

print("\n=== پایان پچ فایل‌های پایتون (بچ ۳) ===\n")
FIXEOF

echo "🔎 بررسی سینتکس فایل‌ها..."
for f in bot/keyboards.py bot/handlers/admin.py database/crud.py; do
  python3 -c "import ast; ast.parse(open('/opt/vpnbot/$f').read())" && echo "✅ $f سالم است" || echo "❌ خطای سینتکس در $f !!"
done

echo "🧹 پاک‌کردن __pycache__..."
find /opt/vpnbot -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null

echo "🔄 ری‌استارت سرویس..."
systemctl restart vpnbot
sleep 2
journalctl -u vpnbot -n 15 --no-pager
