from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func, and_, delete, or_
from sqlalchemy.orm import selectinload
from datetime import datetime, timedelta
from typing import Optional, List
import json
import random
from database.db import (
    User, Plan, Service, Transaction, Payment, DiscountCode, BotSetting,
    Category, AdminUser, ForceJoin,
    ServiceStatus, TransactionType, UserStatus, PaymentMethod, PaymentStatus
)


# ─── SETTINGS ────────────────────────────────────────────────────────────────

async def get_setting(db: AsyncSession, key: str, default: str = "") -> str:
    r = await db.execute(select(BotSetting).where(BotSetting.key == key))
    s = r.scalar_one_or_none()
    return s.value if s else default


async def set_setting(db: AsyncSession, key: str, value: str):
    r = await db.execute(select(BotSetting).where(BotSetting.key == key))
    s = r.scalar_one_or_none()
    if s:
        s.value = value
    else:
        db.add(BotSetting(key=key, value=value))
    await db.commit()


async def get_all_settings(db: AsyncSession) -> dict:
    r = await db.execute(select(BotSetting))
    return {s.key: s.value for s in r.scalars().all()}


# ─── ADMIN ───────────────────────────────────────────────────────────────────

async def get_admin(db: AsyncSession, telegram_id: int) -> Optional[AdminUser]:
    r = await db.execute(
        select(AdminUser).where(
            and_(AdminUser.telegram_id == telegram_id, AdminUser.is_active == True)
        )
    )
    return r.scalar_one_or_none()


async def add_admin(db: AsyncSession, telegram_id: int, full_name: str,
                    permissions: list, added_by: int) -> AdminUser:
    admin = AdminUser(
        telegram_id=telegram_id, full_name=full_name,
        permissions=json.dumps(permissions), added_by=added_by
    )
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    return admin


async def get_all_admins(db: AsyncSession) -> List[AdminUser]:
    r = await db.execute(select(AdminUser).where(AdminUser.is_active == True))
    return r.scalars().all()


async def remove_admin(db: AsyncSession, telegram_id: int):
    await db.execute(
        update(AdminUser).where(AdminUser.telegram_id == telegram_id).values(is_active=False)
    )
    await db.commit()


async def update_admin_permissions(db: AsyncSession, telegram_id: int, permissions: list):
    await db.execute(
        update(AdminUser).where(AdminUser.telegram_id == telegram_id)
        .values(permissions=json.dumps(permissions))
    )
    await db.commit()


def admin_has_perm(admin: AdminUser, perm: str) -> bool:
    if admin is None:
        return False
    perms = json.loads(admin.permissions or "[]")
    return perm in perms or "all" in perms


# ─── USER ────────────────────────────────────────────────────────────────────

async def get_or_create_user(db: AsyncSession, telegram_id: int,
                             username: str = None, full_name: str = "",
                             referred_by: int = None):
    r = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = r.scalar_one_or_none()
    is_new = False
    if not user:
        user = User(telegram_id=telegram_id, username=username,
                    full_name=full_name, referred_by=referred_by)
        db.add(user)
        await db.commit()
        await db.refresh(user)
        is_new = True
    else:
        if user.username != username or user.full_name != full_name:
            user.username = username
            user.full_name = full_name
            await db.commit()
    return user, is_new


async def get_user(db: AsyncSession, telegram_id: int) -> Optional[User]:
    r = await db.execute(select(User).where(User.telegram_id == telegram_id))
    return r.scalar_one_or_none()


async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[User]:
    r = await db.execute(select(User).where(User.id == user_id))
    return r.scalar_one_or_none()


async def get_all_active_users(db: AsyncSession) -> List[User]:
    r = await db.execute(select(User).where(User.status == UserStatus.ACTIVE))
    return r.scalars().all()


async def update_wallet(db: AsyncSession, user: User, amount: float, desc: str, t_type: TransactionType):
    user.wallet = round(user.wallet + amount, 2)
    db.add(Transaction(user_id=user.id, amount=amount, type=t_type, description=desc))
    await db.commit()


async def ban_user(db: AsyncSession, tid: int):
    await db.execute(update(User).where(User.telegram_id == tid).values(status=UserStatus.BANNED))
    await db.commit()


async def unban_user(db: AsyncSession, tid: int):
    await db.execute(update(User).where(User.telegram_id == tid).values(status=UserStatus.ACTIVE))
    await db.commit()


async def get_user_count(db: AsyncSession) -> int:
    r = await db.execute(select(func.count()).select_from(User))
    return r.scalar()


async def count_referrals(db: AsyncSession, telegram_id: int) -> int:
    r = await db.execute(select(func.count()).select_from(User).where(User.referred_by == telegram_id))
    return r.scalar()


# ─── CATEGORIES ──────────────────────────────────────────────────────────────

async def get_active_categories(db: AsyncSession) -> List[Category]:
    r = await db.execute(
        select(Category).where(Category.is_active == True).order_by(Category.sort_order, Category.id)
    )
    return r.scalars().all()


async def get_all_categories(db: AsyncSession) -> List[Category]:
    r = await db.execute(select(Category).order_by(Category.sort_order, Category.id))
    return r.scalars().all()


async def get_category(db: AsyncSession, cat_id: int) -> Optional[Category]:
    r = await db.execute(select(Category).where(Category.id == cat_id))
    return r.scalar_one_or_none()


async def create_category(db: AsyncSession, name: str, icon: str = "📦",
                          description: str = "", sort_order: int = 0) -> Category:
    cat = Category(name=name, icon=icon, description=description, sort_order=sort_order)
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    return cat


async def update_category(db: AsyncSession, cat_id: int, **kwargs):
    await db.execute(update(Category).where(Category.id == cat_id).values(**kwargs))
    await db.commit()


async def delete_category(db: AsyncSession, cat_id: int):
    await db.execute(update(Plan).where(Plan.category_id == cat_id).values(category_id=None))
    await db.execute(delete(Category).where(Category.id == cat_id))
    await db.commit()


# ─── PLANS ───────────────────────────────────────────────────────────────────

async def get_active_plans(db: AsyncSession, category_id: int = None) -> List[Plan]:
    q = select(Plan).where(Plan.is_active == True)
    if category_id:
        q = q.where(Plan.category_id == category_id)
    q = q.order_by(Plan.sort_order, Plan.price)
    r = await db.execute(q)
    return r.scalars().all()


async def get_all_plans(db: AsyncSession) -> List[Plan]:
    r = await db.execute(select(Plan).order_by(Plan.category_id, Plan.sort_order, Plan.price))
    return r.scalars().all()


async def get_plan(db: AsyncSession, plan_id: int) -> Optional[Plan]:
    r = await db.execute(select(Plan).where(Plan.id == plan_id))
    return r.scalar_one_or_none()


async def create_plan(db: AsyncSession, name: str, traffic_gb: int, days: int,
                      price: float, category_id: int = None, inbound_id: int = None,
                      sort_order: int = 0) -> Plan:
    plan = Plan(name=name, traffic_gb=traffic_gb, days=days, price=price,
                category_id=category_id, inbound_id=inbound_id, sort_order=sort_order)
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return plan


async def update_plan(db: AsyncSession, plan_id: int, **kwargs):
    await db.execute(update(Plan).where(Plan.id == plan_id).values(**kwargs))
    await db.commit()


async def delete_plan(db: AsyncSession, plan_id: int):
    await db.execute(delete(Plan).where(Plan.id == plan_id))
    await db.commit()


# ─── DISCOUNT CODES ──────────────────────────────────────────────────────────

async def get_discount(db: AsyncSession, code: str) -> Optional[DiscountCode]:
    r = await db.execute(
        select(DiscountCode).where(
            and_(DiscountCode.code == code.upper(), DiscountCode.is_active == True)
        )
    )
    return r.scalar_one_or_none()


async def use_discount(db: AsyncSession, code: DiscountCode):
    code.used_count += 1
    if code.used_count >= code.max_uses:
        code.is_active = False
    await db.commit()


async def create_discount(db: AsyncSession, code: str, percent: int, max_uses: int) -> DiscountCode:
    dc = DiscountCode(code=code.upper(), percent=percent, max_uses=max_uses)
    db.add(dc)
    await db.commit()
    await db.refresh(dc)
    return dc


async def get_all_discounts(db: AsyncSession) -> List[DiscountCode]:
    r = await db.execute(select(DiscountCode).order_by(DiscountCode.created_at.desc()))
    return r.scalars().all()


async def delete_discount(db: AsyncSession, dc_id: int):
    await db.execute(delete(DiscountCode).where(DiscountCode.id == dc_id))
    await db.commit()


# ─── SERVICES ────────────────────────────────────────────────────────────────

async def create_service(db: AsyncSession, user_id: int, plan_id: Optional[int],
                         uuid: str, email: str, inbound_id: int,
                         traffic_gb: int, days: int, is_test: bool = False,
                         sub_link: str = None, vless_link: str = None) -> Service:
    expires_at = datetime.utcnow() + timedelta(days=days)
    svc = Service(
        user_id=user_id, plan_id=plan_id, panel_uuid=uuid,
        panel_email=email, inbound_id=inbound_id,
        traffic_gb=traffic_gb, days=days, expires_at=expires_at,
        is_test=is_test, sub_link=sub_link, vless_link=vless_link
    )
    db.add(svc)
    await db.commit()
    await db.refresh(svc)
    return svc


async def get_user_services(db: AsyncSession, user_id: int) -> List[Service]:
    r = await db.execute(
        select(Service)
        .where(and_(Service.user_id == user_id, Service.status == ServiceStatus.ACTIVE))
        .order_by(Service.created_at.desc())
    )
    return r.scalars().all()


async def get_service(db: AsyncSession, svc_id: int) -> Optional[Service]:
    r = await db.execute(select(Service).where(Service.id == svc_id))
    return r.scalar_one_or_none()


async def get_service_count(db: AsyncSession) -> int:
    r = await db.execute(
        select(func.count()).select_from(Service).where(Service.status == ServiceStatus.ACTIVE)
    )
    return r.scalar()


async def get_services_to_check(db: AsyncSession) -> List[Service]:
    """سرویس‌هایی که هنوز نوتیف 80% نگرفتن"""
    r = await db.execute(
        select(Service)
        .options(selectinload(Service.user))
        .where(and_(
            Service.status == ServiceStatus.ACTIVE,
            Service.notified_80 == False,
        ))
    )
    return r.scalars().all()


async def update_service(db: AsyncSession, svc_id: int, **kwargs):
    await db.execute(update(Service).where(Service.id == svc_id).values(**kwargs))
    await db.commit()


# ─── PAYMENTS ────────────────────────────────────────────────────────────────

async def create_payment(db: AsyncSession, user_id: int, amount: float,
                         method: PaymentMethod, authority: str = None,
                         plan_id: int = None) -> Payment:
    p = Payment(user_id=user_id, amount=amount, method=method,
                authority=authority, plan_id=plan_id)
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p


async def get_payment(db: AsyncSession, pay_id: int) -> Optional[Payment]:
    r = await db.execute(
        select(Payment).options(selectinload(Payment.user)).where(Payment.id == pay_id)
    )
    return r.scalar_one_or_none()


async def get_payment_by_authority(db: AsyncSession, authority: str) -> Optional[Payment]:
    r = await db.execute(select(Payment).where(Payment.authority == authority))
    return r.scalar_one_or_none()


async def get_pending_card_payments(db: AsyncSession) -> List[Payment]:
    r = await db.execute(
        select(Payment)
        .options(selectinload(Payment.user))
        .where(and_(
            Payment.method == PaymentMethod.CARD,
            Payment.status == PaymentStatus.PENDING,
            Payment.receipt_file_id.isnot(None)
        ))
        .order_by(Payment.created_at.desc())
    )
    return r.scalars().all()


# ─── FORCE JOIN ──────────────────────────────────────────────────────────────

async def get_active_force_joins(db: AsyncSession) -> List[ForceJoin]:
    r = await db.execute(select(ForceJoin).where(ForceJoin.is_active == True))
    return r.scalars().all()


async def get_all_force_joins(db: AsyncSession) -> List[ForceJoin]:
    r = await db.execute(select(ForceJoin))
    return r.scalars().all()


async def add_force_join(db: AsyncSession, channel_id: str, channel_name: str,
                         invite_link: str = None) -> ForceJoin:
    fj = ForceJoin(channel_id=channel_id, channel_name=channel_name, invite_link=invite_link)
    db.add(fj)
    await db.commit()
    await db.refresh(fj)
    return fj


async def remove_force_join(db: AsyncSession, fj_id: int):
    await db.execute(delete(ForceJoin).where(ForceJoin.id == fj_id))
    await db.commit()


# ─── LOTTERY ─────────────────────────────────────────────────────────────────

async def get_or_create_lottery_number(db: AsyncSession, user: User) -> int:
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


async def get_lottery_participants_count(db: AsyncSession) -> int:
    r = await db.execute(
        select(func.count()).select_from(User).where(User.lottery_number.isnot(None))
    )
    return r.scalar()


async def draw_lottery(db: AsyncSession, count: int = 1) -> List[User]:
    r = await db.execute(select(User).where(User.lottery_number.isnot(None)))
    all_participants = r.scalars().all()
    if not all_participants:
        return []
    count = min(count, len(all_participants))
    return random.sample(all_participants, count)


# ─── BACKUP ──────────────────────────────────────────────────────────────────

async def get_full_backup(db: AsyncSession) -> dict:
    users = await db.execute(select(User))
    plans = await db.execute(select(Plan))
    categories = await db.execute(select(Category))
    settings = await db.execute(select(BotSetting))
    discounts = await db.execute(select(DiscountCode))

    def to_dict(obj):
        d = {}
        for col in obj.__table__.columns:
            val = getattr(obj, col.name)
            if isinstance(val, datetime):
                val = val.isoformat()
            elif isinstance(val, enum):
                val = val.value
            d[col.name] = val
        return d

    return {
        "version": "2.0",
        "timestamp": datetime.utcnow().isoformat(),
        "users": [to_dict(u) for u in users.scalars().all()],
        "plans": [to_dict(p) for p in plans.scalars().all()],
        "categories": [to_dict(c) for c in categories.scalars().all()],
        "settings": {s.key: s.value for s in settings.scalars().all()},
        "discounts": [to_dict(d) for d in discounts.scalars().all()],
    }
