from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func, and_, delete
from sqlalchemy.orm import selectinload
from datetime import datetime, timedelta
from typing import Optional, List
import json, random
from database.db import (
    User, Plan, Service, Payment, DiscountCode, BotSetting,
    Category, AdminUser, ForceJoin,
    ServiceStatus, TransactionType, UserStatus, PaymentMethod, PaymentStatus
)


async def get_setting(db, key, default=""):
    r = await db.execute(select(BotSetting).where(BotSetting.key == key))
    s = r.scalar_one_or_none()
    return s.value if s else default


async def set_setting(db, key, value):
    r = await db.execute(select(BotSetting).where(BotSetting.key == key))
    s = r.scalar_one_or_none()
    if s:
        s.value = value
    else:
        db.add(BotSetting(key=key, value=value))
    await db.commit()


async def get_admin(db, telegram_id):
    r = await db.execute(select(AdminUser).where(and_(AdminUser.telegram_id == telegram_id, AdminUser.is_active == True)))
    return r.scalar_one_or_none()


async def add_admin(db, telegram_id, full_name, permissions, added_by):
    r = await db.execute(select(AdminUser).where(AdminUser.telegram_id == telegram_id))
    a = r.scalar_one_or_none()
    if a:
        a.full_name = full_name
        a.permissions = json.dumps(permissions)
        a.added_by = added_by
        a.is_active = True
    else:
        a = AdminUser(telegram_id=telegram_id, full_name=full_name, permissions=json.dumps(permissions), added_by=added_by)
        db.add(a)
    await db.commit()
    return a


async def get_all_admins(db):
    r = await db.execute(select(AdminUser).where(AdminUser.is_active == True))
    return r.scalars().all()


async def remove_admin(db, telegram_id):
    await db.execute(update(AdminUser).where(AdminUser.telegram_id == telegram_id).values(is_active=False))
    await db.commit()


def admin_has_perm(admin, perm):
    if admin is None:
        return False
    perms = json.loads(admin.permissions or "[]")
    return perm in perms or "all" in perms


async def get_or_create_user(db, telegram_id, username=None, full_name="", referred_by=None):
    r = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = r.scalar_one_or_none()
    is_new = False
    if not user:
        user = User(telegram_id=telegram_id, username=username, full_name=full_name, referred_by=referred_by)
        db.add(user)
        await db.commit()
        await db.refresh(user)
        is_new = True
    return user, is_new


async def get_user(db, telegram_id):
    r = await db.execute(select(User).where(User.telegram_id == telegram_id))
    return r.scalar_one_or_none()


async def update_wallet(db, user, amount, desc, t_type):
    user.wallet = round(user.wallet + amount, 2)
    await db.commit()


async def ban_user(db, tid):
    await db.execute(update(User).where(User.telegram_id == tid).values(status=UserStatus.BANNED))
    await db.commit()


async def unban_user(db, tid):
    await db.execute(update(User).where(User.telegram_id == tid).values(status=UserStatus.ACTIVE))
    await db.commit()


async def get_user_count(db):
    r = await db.execute(select(func.count()).select_from(User))
    return r.scalar()


async def count_referrals(db, telegram_id):
    r = await db.execute(select(func.count()).select_from(User).where(User.referred_by == telegram_id))
    return r.scalar()


async def get_all_active_users(db):
    r = await db.execute(select(User).where(User.status == UserStatus.ACTIVE))
    return r.scalars().all()


async def get_active_categories(db):
    r = await db.execute(select(Category).where(Category.is_active == True).order_by(Category.sort_order))
    return r.scalars().all()


async def get_all_categories(db):
    r = await db.execute(select(Category).order_by(Category.sort_order))
    return r.scalars().all()


async def get_category(db, cat_id):
    r = await db.execute(select(Category).where(Category.id == cat_id))
    return r.scalar_one_or_none()


async def create_category(db, name, icon="📦", sort_order=0):
    c = Category(name=name, icon=icon, sort_order=sort_order)
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c


async def update_category(db, cat_id, **kw):
    await db.execute(update(Category).where(Category.id == cat_id).values(**kw))
    await db.commit()


async def delete_category(db, cat_id):
    await db.execute(update(Plan).where(Plan.category_id == cat_id).values(category_id=None))
    await db.execute(delete(Category).where(Category.id == cat_id))
    await db.commit()


async def get_active_plans(db, category_id=None):
    q = select(Plan).where(Plan.is_active == True)
    if category_id:
        q = q.where(Plan.category_id == category_id)
    r = await db.execute(q.order_by(Plan.sort_order, Plan.price))
    return r.scalars().all()


async def get_all_plans(db):
    r = await db.execute(select(Plan).order_by(Plan.sort_order))
    return r.scalars().all()


async def get_plan(db, plan_id):
    r = await db.execute(select(Plan).where(Plan.id == plan_id))
    return r.scalar_one_or_none()


async def create_plan(db, name, traffic_gb, days, price, category_id=None, inbound_id=None, sort_order=0, max_users=1):
    p = Plan(name=name, traffic_gb=traffic_gb, days=days, price=price, max_users=max_users,
              category_id=category_id, inbound_id=inbound_id, sort_order=sort_order)
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p


async def update_plan(db, plan_id, **kw):
    await db.execute(update(Plan).where(Plan.id == plan_id).values(**kw))
    await db.commit()


async def delete_plan(db, plan_id):
    await db.execute(delete(Plan).where(Plan.id == plan_id))
    await db.commit()


async def get_discount(db, code):
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
        await db.commit()


async def create_service(db, user_id, plan_id, uuid, email, inbound_id, traffic_gb, days, is_test=False, sub_link=None, vless_link=None, max_users=1):
    expires_at = datetime.utcnow() + timedelta(days=days)
    s = Service(user_id=user_id, plan_id=plan_id, panel_uuid=uuid, panel_email=email,
                inbound_id=inbound_id, traffic_gb=traffic_gb, days=days, max_users=max_users,
                expires_at=expires_at, is_test=is_test, sub_link=sub_link, vless_link=vless_link)
    db.add(s)
    await db.commit()
    await db.refresh(s)
    return s


async def get_user_services(db, user_id):
    r = await db.execute(select(Service).where(and_(Service.user_id == user_id, Service.status == ServiceStatus.ACTIVE)).order_by(Service.created_at.desc()))
    return r.scalars().all()


async def get_service(db, svc_id):
    r = await db.execute(select(Service).where(Service.id == svc_id))
    return r.scalar_one_or_none()


async def get_service_count(db):
    r = await db.execute(select(func.count()).select_from(Service).where(Service.status == ServiceStatus.ACTIVE))
    return r.scalar()


async def update_service(db, svc_id, **kw):
    await db.execute(update(Service).where(Service.id == svc_id).values(**kw))
    await db.commit()


async def create_payment(db, user_id, amount, method, plan_id=None):
    p = Payment(user_id=user_id, amount=amount, method=method, plan_id=plan_id)
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p


async def get_payment(db, pay_id):
    r = await db.execute(select(Payment).options(selectinload(Payment.user)).where(Payment.id == pay_id))
    return r.scalar_one_or_none()


async def get_pending_card_payments(db):
    r = await db.execute(select(Payment).options(selectinload(Payment.user)).where(and_(
        Payment.method == PaymentMethod.CARD, Payment.status == PaymentStatus.PENDING,
        Payment.receipt_file_id.isnot(None))).order_by(Payment.created_at.desc()))
    return r.scalars().all()


async def get_active_force_joins(db):
    r = await db.execute(select(ForceJoin).where(ForceJoin.is_active == True))
    return r.scalars().all()


async def get_all_force_joins(db):
    r = await db.execute(select(ForceJoin))
    return r.scalars().all()


async def add_force_join(db, channel_id, channel_name, invite_link=None):
    fj = ForceJoin(channel_id=channel_id, channel_name=channel_name, invite_link=invite_link)
    db.add(fj)
    await db.commit()
    return fj


async def remove_force_join(db, fj_id):
    await db.execute(delete(ForceJoin).where(ForceJoin.id == fj_id))
    await db.commit()


async def get_or_create_lottery_number(db, user):
    if user.lottery_number:
        return user.lottery_number
    while True:
        num = random.randint(10000, 99999)
        r = await db.execute(select(User).where(User.lottery_number == num))
        if not r.scalar_one_or_none():
            break
    user.lottery_number = num
    await db.commit()
    return num


async def get_lottery_participants_count(db):
    r = await db.execute(select(func.count()).select_from(User).where(User.lottery_number.isnot(None)))
    return r.scalar()


async def draw_lottery(db, count=1):
    r = await db.execute(select(User).where(User.lottery_number.isnot(None)))
    parts = r.scalars().all()
    if not parts:
        return []
    return random.sample(parts, min(count, len(parts)))


async def reset_lottery(db):
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
    return r.rowcount


async def get_admins_with_perm(db, perm):
    r = await db.execute(select(AdminUser).where(AdminUser.is_active == True))
    admins = r.scalars().all()
    result = []
    for a in admins:
        perms = json.loads(a.permissions or "[]")
        if perm in perms or "all" in perms:
            result.append(a.telegram_id)
    return result


async def email_exists(db, email):
    r = await db.execute(select(Service).where(Service.panel_email == email))
    return r.scalar_one_or_none() is not None


async def set_user_phone(db, telegram_id, phone):
    await db.execute(update(User).where(User.telegram_id == telegram_id).values(phone=phone))
    await db.commit()


async def set_phone_exempt(db, telegram_id, exempt):
    await db.execute(update(User).where(User.telegram_id == telegram_id).values(phone_exempt=exempt))
    await db.commit()


async def get_expired_active_services(db):
    now = datetime.utcnow()
    r = await db.execute(
        select(Service).where(
            Service.status == ServiceStatus.ACTIVE,
            Service.expires_at.isnot(None),
            Service.expires_at < now,
        )
    )
    return r.scalars().all()


async def get_all_active_services_full(db):
    r = await db.execute(select(Service).where(Service.status == ServiceStatus.ACTIVE))
    return r.scalars().all()


async def get_services_pending_panel_removal(db):
    """Every service not yet confirmed removed from the panel: still-active
    ones (checked for real expiry separately) plus ones we already marked
    expired locally in the past but never actually got deleted server-side
    (e.g. because of an earlier bug)."""
    r = await db.execute(select(Service).where(Service.panel_removed == False))
    return r.scalars().all()


async def get_referral_active_services(db, limit=None):
    q = (
        select(Service)
        .join(User, Service.user_id == User.id)
        .where(Service.status == ServiceStatus.ACTIVE, User.referred_by.isnot(None))
        .options(selectinload(Service.user))
        .order_by(Service.created_at.desc())
    )
    if limit:
        q = q.limit(limit)
    r = await db.execute(q)
    return r.scalars().all()
