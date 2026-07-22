python3 << 'FIXEOF'
import re

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

# ---------- 1) database/db.py : اضافه کردن expires_at به DiscountCode ----------
patch("database/db.py",
old='''class DiscountCode(Base):
    __tablename__ = "discount_codes"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    percent: Mapped[int] = mapped_column(Integer, nullable=False)
    max_uses: Mapped[int] = mapped_column(Integer, default=1)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)''',
new='''class DiscountCode(Base):
    __tablename__ = "discount_codes"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    percent: Mapped[int] = mapped_column(Integer, nullable=False)
    max_uses: Mapped[int] = mapped_column(Integer, default=1)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)''',
label="db.py -> ستون expires_at")

# ---------- 2) database/crud.py : تابع‌های کد تخفیف ----------
patch("database/crud.py",
old='''async def get_discount(db, code):
    r = await db.execute(select(DiscountCode).where(and_(DiscountCode.code == code.upper(), DiscountCode.is_active == True)))
    return r.scalar_one_or_none()


async def use_discount(db, code):
    code.used_count += 1
    if code.used_count >= code.max_uses:
        code.is_active = False
    await db.commit()''',
new='''async def get_discount(db, code):
    r = await db.execute(select(DiscountCode).where(and_(DiscountCode.code == code.upper(), DiscountCode.is_active == True)))
    dc = r.scalar_one_or_none()
    if dc and dc.expires_at and dc.expires_at < datetime.utcnow():
        dc.is_active = False
        await db.commit()
        return None
    return dc


async def use_discount(db, code):
    code.used_count += 1
    if code.used_count >= code.max_uses:
        code.is_active = False
    await db.commit()


async def create_discount(db, code, percent, max_uses=1, expires_at=None):
    dc = DiscountCode(code=code.upper(), percent=percent, max_uses=max_uses, expires_at=expires_at)
    db.add(dc)
    await db.commit()
    await db.refresh(dc)
    return dc


async def get_all_discounts(db):
    r = await db.execute(select(DiscountCode).order_by(DiscountCode.id.desc()))
    return r.scalars().all()


async def delete_discount(db, discount_id):
    r = await db.execute(select(DiscountCode).where(DiscountCode.id == discount_id))
    dc = r.scalar_one_or_none()
    if dc:
        await db.delete(dc)
        await db.commit()''',
label="crud.py -> توابع کد تخفیف")

# ---------- 3) bot/keyboards.py : منوی ادمین پرمیشن‌محور + دکمه‌های جدید ----------
patch("bot/keyboards.py",
old='''def admin_menu_kb():
    b = ReplyKeyboardBuilder()
    b.row(KeyboardButton(text="📊 آمار ربات"), KeyboardButton(text="📢 پیام همگانی"))
    b.row(KeyboardButton(text="📦 مدیریت پلن‌ها"), KeyboardButton(text="🗂 دسته‌بندی‌ها"))
    b.row(KeyboardButton(text="💳 تایید پرداخت‌ها"), KeyboardButton(text="🏆 قرعه‌کشی"))
    b.row(KeyboardButton(text="👥 مدیریت ادمین‌ها"), KeyboardButton(text="🚫 بن کاربر"))
    b.row(KeyboardButton(text="⚙️ تنظیمات"), KeyboardButton(text="💰 کسر/افزایش موجودی"))
    b.row(KeyboardButton(text="📢 کانال‌های اجباری"))
    b.row(KeyboardButton(text="🔙 منوی اصلی"))
    return b.as_markup(resize_keyboard=True)''',
new='''ADMIN_MENU_BUTTONS = [
    ("📊 آمار ربات", "stats"),
    ("📢 پیام همگانی", "broadcast"),
    ("📦 مدیریت پلن‌ها", "plans"),
    ("🗂 دسته‌بندی‌ها", "plans"),
    ("💳 تایید پرداخت‌ها", "payment"),
    ("🏆 قرعه‌کشی", "lottery"),
    ("👥 مدیریت ادمین‌ها", "all"),
    ("🎫 کد تخفیف", "discount"),
    ("🚫 بن کاربر", "ban"),
    ("⚙️ تنظیمات", "settings"),
    ("💰 کسر/افزایش موجودی", "wallet"),
    ("📢 کانال‌های اجباری", "settings"),
]


def admin_menu_kb(perms=None):
    b = ReplyKeyboardBuilder()
    is_owner = perms is None
    allowed = set(perms or [])
    for text, perm in ADMIN_MENU_BUTTONS:
        if is_owner or perm in allowed or "all" in allowed:
            b.row(KeyboardButton(text=text))
    b.row(KeyboardButton(text="🔙 منوی اصلی"))
    return b.as_markup(resize_keyboard=True)


def plan_cat_select_kb(cats, prefix="pcat"):
    b = InlineKeyboardBuilder()
    for c in cats:
        b.row(InlineKeyboardButton(text=f"{c.icon} {c.name}", callback_data=f"{prefix}:{c.id}"))
    b.row(InlineKeyboardButton(text="🚫 بدون دسته‌بندی", callback_data=f"{prefix}:none"))
    return b.as_markup()''',
label="keyboards.py -> منوی ادمین پرمیشن‌محور")

patch("bot/keyboards.py",
old='''        (\"💳 کارت بانکی\", \"set_card\"), (\"🤖 نام ربات\", \"set_botname\"),''',
new='''        (\"💳 شماره کارت\", \"set_card\"), (\"👤 نام صاحب کارت\", \"set_card_holder\"), (\"🤖 نام ربات\", \"set_botname\"),''',
label="keyboards.py -> دکمه نام صاحب کارت")

# ---------- 4) bot/handlers/user.py : منوی ادمین بر اساس پرمیشن ----------
patch("bot/handlers/user.py",
old='''async def is_admin_user(user_id):
    if user_id in config.ADMIN_IDS:
        return True
    async with AsyncSessionLocal() as db:
        a = await crud.get_admin(db, user_id)
        return a is not None''',
new='''async def is_admin_user(user_id):
    if user_id in config.ADMIN_IDS:
        return True
    async with AsyncSessionLocal() as db:
        a = await crud.get_admin(db, user_id)
        return a is not None


async def get_admin_perms(user_id):
    import json
    if user_id in config.ADMIN_IDS:
        return None
    async with AsyncSessionLocal() as db:
        a = await crud.get_admin(db, user_id)
    if not a:
        return []
    return json.loads(a.permissions or "[]")''',
label="user.py -> get_admin_perms")

patch("bot/handlers/user.py",
old='''    if is_admin:
        from bot.keyboards import admin_menu_kb
        await msg.answer(welcome, reply_markup=admin_menu_kb())
    else:''',
new='''    if is_admin:
        from bot.keyboards import admin_menu_kb
        perms = await get_admin_perms(msg.from_user.id)
        await msg.answer(welcome, reply_markup=admin_menu_kb(perms))
    else:''',
label="user.py -> استفاده از منوی پرمیشن‌محور در /start")

# ---------- 5) bot/handlers/admin.py ----------
patch("bot/handlers/admin.py",
old='''import json
import logging''',
new='''import json
import logging
from datetime import datetime, timedelta''',
label="admin.py -> ایمپورت datetime")

patch("bot/handlers/admin.py",
old='''PERM_NAMES = {
    "payment": "✅ تایید پرداخت", "broadcast": "📢 پیام همگانی",
    "plans": "📦 مدیریت پلن‌ها", "stats": "📊 آمار", "lottery": "🏆 قرعه‌کشی",
    "ban": "🚫 بن کاربر", "settings": "⚙️ تنظیمات", "all": "🔑 همه",
}''',
new='''PERM_NAMES = {
    "payment": "✅ تایید پرداخت", "broadcast": "📢 پیام همگانی",
    "plans": "📦 مدیریت پلن‌ها", "stats": "📊 آمار", "lottery": "🏆 قرعه‌کشی",
    "ban": "🚫 بن کاربر", "settings": "⚙️ تنظیمات", "wallet": "💰 کسر/افزایش موجودی",
    "discount": "🎫 کد تخفیف", "all": "🔑 همه",
}''',
label="admin.py -> پرمیشن‌های wallet و discount")

patch("bot/handlers/admin.py",
old='''from bot.keyboards import (
    admin_menu_kb, admin_plans_kb, admin_plan_detail_kb, admin_cats_kb,
    admin_cat_detail_kb, admin_settings_kb, lottery_admin_kb, admin_admins_kb,
    back_kb, payment_confirm_kb, main_menu_kb
)''',
new='''from bot.keyboards import (
    admin_menu_kb, admin_plans_kb, admin_plan_detail_kb, admin_cats_kb,
    admin_cat_detail_kb, admin_settings_kb, lottery_admin_kb, admin_admins_kb,
    back_kb, payment_confirm_kb, main_menu_kb, plan_cat_select_kb
)''',
label="admin.py -> ایمپورت plan_cat_select_kb")

patch("bot/handlers/admin.py",
old='''@router.message(F.text == "💰 کسر/افزایش موجودی")
async def adjust_start(msg: Message, state: FSMContext):
    if not await is_admin(msg.from_user.id):
        return''',
new='''@router.message(F.text == "💰 کسر/افزایش موجودی")
async def adjust_start(msg: Message, state: FSMContext):
    if not await is_admin(msg.from_user.id, "wallet"):
        return''',
label="admin.py -> پرمیشن wallet روی adjust_start")

patch("bot/handlers/admin.py",
old='''@router.message(F.text == "👥 مدیریت ادمین‌ها")
async def manage_admins(msg: Message):
    if msg.from_user.id not in config.ADMIN_IDS:
        return''',
new='''@router.message(F.text == "👥 مدیریت ادمین‌ها")
async def manage_admins(msg: Message):
    if not await is_admin(msg.from_user.id, "all"):
        return''',
label="admin.py -> دسترسی مدیریت ادمین‌ها (manage_admins)")

patch("bot/handlers/admin.py",
old='''@router.callback_query(F.data == "add_admin")
async def add_admin_start(cb: CallbackQuery, state: FSMContext):
    if cb.from_user.id not in config.ADMIN_IDS:
        return''',
new='''@router.callback_query(F.data == "add_admin")
async def add_admin_start(cb: CallbackQuery, state: FSMContext):
    if not await is_admin(cb.from_user.id, "all"):
        return''',
label="admin.py -> دسترسی افزودن ادمین")

patch("bot/handlers/admin.py",
old='''@router.callback_query(F.data.startswith("admin_detail:"))
async def admin_detail(cb: CallbackQuery):
    if cb.from_user.id not in config.ADMIN_IDS:
        return''',
new='''@router.callback_query(F.data.startswith("admin_detail:"))
async def admin_detail(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id, "all"):
        return''',
label="admin.py -> دسترسی جزئیات ادمین")

patch("bot/handlers/admin.py",
old='''@router.callback_query(F.data.startswith("del_admin:"))
async def del_admin(cb: CallbackQuery):
    if cb.from_user.id not in config.ADMIN_IDS:
        return''',
new='''@router.callback_query(F.data.startswith("del_admin:"))
async def del_admin(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id, "all"):
        return''',
label="admin.py -> دسترسی حذف ادمین")

patch("bot/handlers/admin.py",
old='''SETTING_MAP = {
    "set_card": ("card_number", "💳 شماره کارت:"),
    "set_botname": ("bot_name", "🤖 نام ربات:"),''',
new='''SETTING_MAP = {
    "set_card": ("card_number", "💳 شماره کارت:"),
    "set_card_holder": ("card_holder", "👤 نام صاحب کارت (دقیقاً مطابق کارت بانکی):"),
    "set_botname": ("bot_name", "🤖 نام ربات:"),''',
label="admin.py -> فیلد نام صاحب کارت در SETTING_MAP")

# ---------- 6) دسته‌بندی در فرآیند ساخت پلن ----------
patch("bot/handlers/admin.py",
old='''@router.message(PlanState.max_users)
async def plan_max_users(msg: Message, state: FSMContext):
    try:
        max_users = int(msg.text.strip())
        if max_users < 0:
            raise ValueError
    except ValueError:
        await msg.answer("❌ عدد صحیح و غیرمنفی وارد کنید (مثلاً 1 یا 5 یا 0 برای نامحدود).")
        return
    data = await state.get_data()
    await state.clear()
    async with AsyncSessionLocal() as db:
        plan = await crud.create_plan(db, data["name"], data["traffic"], data["days"], data["price"], max_users=max_users)
    users_text = "نامحدود" if max_users == 0 else f"{max_users} کاربر"
    await msg.answer(f"✅ پلن «{plan.name}» ساخته شد!\\n👥 {users_text}")''',
new='''@router.message(PlanState.max_users)
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
        data = await state.get_data()
        await state.clear()
        async with AsyncSessionLocal() as db:
            plan = await crud.create_plan(db, data["name"], data["traffic"], data["days"], data["price"], max_users=max_users)
        await msg.answer(f"✅ پلن «{plan.name}» ساخته شد!\\n(دسته‌بندی‌ای وجود نداشت، بدون دسته ساخته شد)")
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
    await cb.message.edit_text(f"✅ پلن «{plan.name}» ساخته شد!\\n👥 {users_text}")''',
label="admin.py -> مرحله انتخاب دسته‌بندی در ساخت پلن")

patch("bot/handlers/admin.py",
old='''    b = InlineKeyboardBuilder()
    for label, field in [("نام", "name"), ("حجم", "traffic_gb"), ("روز", "days"), ("قیمت", "price"), ("تعداد کاربر", "max_users")]:
        b.row(InlineKeyboardButton(text=label, callback_data=f"ef:{field}"))
    b.row(InlineKeyboardButton(text="فعال/غیرفعال", callback_data="ef:toggle"))
    await cb.message.edit_text("✏️ فیلد:", reply_markup=b.as_markup())''',
new='''    b = InlineKeyboardBuilder()
    for label, field in [("نام", "name"), ("حجم", "traffic_gb"), ("روز", "days"), ("قیمت", "price"), ("تعداد کاربر", "max_users")]:
        b.row(InlineKeyboardButton(text=label, callback_data=f"ef:{field}"))
    b.row(InlineKeyboardButton(text="🗂 دسته‌بندی", callback_data="ef:category_id"))
    b.row(InlineKeyboardButton(text="فعال/غیرفعال", callback_data="ef:toggle"))
    await cb.message.edit_text("✏️ فیلد:", reply_markup=b.as_markup())''',
label="admin.py -> دکمه دسته‌بندی در ویرایش پلن")

patch("bot/handlers/admin.py",
old='''    if field == "toggle":
        async with AsyncSessionLocal() as db:
            plan = await crud.get_plan(db, data["plan_id"])
            await crud.update_plan(db, data["plan_id"], is_active=not plan.is_active)
        await state.clear()
        await cb.message.edit_text("✅ وضعیت تغییر کرد.")
        return
    await state.update_data(edit_field=field)''',
new='''    if field == "toggle":
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
    await state.update_data(edit_field=field)''',
label="admin.py -> هندل کردن انتخاب دسته‌بندی در ویرایش")

patch("bot/handlers/admin.py",
old='''    await state.set_state(PlanState.edit_value)
    await cb.message.edit_text(f"مقدار جدید:")''',
new='''    await state.set_state(PlanState.edit_value)
    await cb.message.edit_text(f"مقدار جدید:")


@router.callback_query(F.data.startswith("efcat:"))
async def edit_plan_category(cb: CallbackQuery, state: FSMContext):
    cat_part = cb.data.split(":")[1]
    category_id = None if cat_part == "none" else int(cat_part)
    data = await state.get_data()
    await state.clear()
    async with AsyncSessionLocal() as db:
        await crud.update_plan(db, data["plan_id"], category_id=category_id)
    await cb.message.edit_text("✅ دسته‌بندی پلن بروزرسانی شد.")''',
label="admin.py -> هندلر ذخیره دسته‌بندی جدید پلن")

# ---------- 7) فلوی کامل ساخت کد تخفیف ----------
patch("bot/handlers/admin.py",
old='''@router.callback_query(F.data.startswith("del_admin:"))
async def del_admin(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id, "all"):
        return
    tid = int(cb.data.split(":")[1])
    async with AsyncSessionLocal() as db:
        await crud.remove_admin(db, tid)
    await cb.message.edit_text("🗑 حذف شد.")''',
new='''@router.callback_query(F.data.startswith("del_admin:"))
async def del_admin(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id, "all"):
        return
    tid = int(cb.data.split(":")[1])
    async with AsyncSessionLocal() as db:
        await crud.remove_admin(db, tid)
    await cb.message.edit_text("🗑 حذف شد.")


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
    await msg.answer(f"✅ کد تخفیف ساخته شد!\\n\\n🏷 کد: {dc.code}\\n📊 درصد: {dc.percent}%\\n👥 ظرفیت: {dc.max_uses} نفر\\n{exp_text}")


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
    await cb.message.edit_text(f"🏷 {dc.code}\\n📊 {dc.percent}% تخفیف\\n👥 استفاده: {dc.used_count}/{dc.max_uses}\\n⏳ انقضا: {exp_text}\\n{status}", reply_markup=b.as_markup())


@router.callback_query(F.data.startswith("del_discount:"))
async def del_discount(cb: CallbackQuery):
    if not await is_admin(cb.from_user.id, "discount"):
        return
    did = int(cb.data.split(":")[1])
    async with AsyncSessionLocal() as db:
        await crud.delete_discount(db, did)
    await cb.message.edit_text("🗑 کد تخفیف حذف شد.")''',
label="admin.py -> فلوی کامل ساخت/نمایش/حذف کد تخفیف")

print("\\n=== پایان پچ فایل‌های پایتون ===\\n")
FIXEOF

echo "🗄  اضافه کردن ستون expires_at به دیتابیس (اگر از قبل نباشد)..."
python3 << 'DBFIX'
import sqlite3
con = sqlite3.connect("/opt/vpnbot/vpnbot.db")
cur = con.cursor()
cur.execute("PRAGMA table_info(discount_codes)")
cols = [r[1] for r in cur.fetchall()]
if "expires_at" not in cols:
    cur.execute("ALTER TABLE discount_codes ADD COLUMN expires_at DATETIME")
    con.commit()
    print("✅ ستون expires_at به دیتابیس اضافه شد")
else:
    print("⏭️  ستون expires_at از قبل وجود دارد")
con.close()
DBFIX

echo "🔎 بررسی سینتکس فایل‌ها..."
for f in bot/keyboards.py bot/handlers/admin.py bot/handlers/user.py database/crud.py database/db.py; do
  python3 -c "import ast; ast.parse(open('/opt/vpnbot/$f').read())" && echo "✅ $f سالم است" || echo "❌ خطای سینتکس در $f !!"
done

echo "🧹 پاک‌کردن __pycache__..."
find /opt/vpnbot -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null

echo "🔄 ری‌استارت سرویس..."
systemctl restart vpnbot
sleep 2
journalctl -u vpnbot -n 15 --no-pager
