from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func, and_, delete
from sqlalchemy.orm import selectinload
from datetime import datetime, timedelta
from typing import Optional, List
from database.db import (
    User, Plan, Service, Transaction, Payment, DiscountCode, BotSetting,
    ServiceStatus, TransactionType, UserStatus, PaymentMethod, PaymentStatus
)
import random


# ─── SETTINGS ───────────────────────────────────────────────────────────────

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


# ─── USER ───────────────────────────────────────────────────────────────────

async def get_or_create_user(db: AsyncSession, telegram_id: int,
                             username: str = None, full_name: str = "",
                             referred_by: int = None) -> tuple:
    """Returns (user, is_new)"""
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


# ─── PLANS ──────────────────────────────────────────────────────────────────

async def get_active_plans(db: AsyncSession) -> List[Plan]:
    r = await db.execute(
        select(Plan).where(Plan.is_active == True).order_by(Plan.sort_order, Plan.price)
    )
    return r.scalars().all()


async def get_plan(db: AsyncSession, plan_id: int) -> Optional[Plan]:
    r = await db.execute(select(Plan).where(Plan.id == plan_id))
    return r.scalar_one_or_none()


async def create_plan(db: AsyncSession, name: str, traffic_gb: int, days: int, price: float) -> Plan:
    plan = Plan(name=name, traffic_gb=traffic_gb, days=days, price=price)
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return plan


async def disable_plan(db: AsyncSession, plan_id: int):
    await db.execute(update(Plan).where(Plan.id == plan_id).values(is_active=False))
    await db.commit()


# ─── DISCOUNT CODES ─────────────────────────────────────────────────────────

async def get_discount(db: AsyncSession, code: str) -> Optional[DiscountCode]:
    r = await db.execute(
        select(DiscountCode).where(
            and_(DiscountCode.code == code.upper(),
                 DiscountCode.is_active == True)
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


# ─── SERVICES ───────────────────────────────────────────────────────────────

async def create_service(db: AsyncSession, user_id: int, plan_id: Optional[int],
                         uuid: str, email: str, inbound_id: int,
                         traffic_gb: int, days: int, is_test: bool = False,
                         sub_link: str = None) -> Service:
    expires_at = datetime.utcnow() + timedelta(days=days)
    svc = Service(
        user_id=user_id, plan_id=plan_id, panel_uuid=uuid,
        panel_email=email, inbound_id=inbound_id,
        traffic_gb=traffic_gb, days=days, expires_at=expires_at,
        is_test=is_test, sub_link=sub_link
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


# ─── PAYMENTS ───────────────────────────────────────────────────────────────

async def create_payment(db: AsyncSession, user_id: int, amount: float,
                         method: PaymentMethod, authority: str = None) -> Payment:
    p = Payment(user_id=user_id, amount=amount, method=method, authority=authority)
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p


async def get_payment_by_authority(db: AsyncSession, authority: str) -> Optional[Payment]:
    r = await db.execute(select(Payment).where(Payment.authority == authority))
    return r.scalar_one_or_none()


async def get_pending_card_payments(db: AsyncSession) -> List[Payment]:
    r = await db.execute(
        select(Payment)
        .options(selectinload(Payment.user))
        .where(and_(
            Payment.method == PaymentMethod.CARD,
            Payment.status == PaymentStatus.PENDING
        ))
        .order_by(Payment.created_at.desc())
    )
    return r.scalars().all()


# ─── LOTTERY ────────────────────────────────────────────────────────────────

async def get_or_create_lottery_number(db: AsyncSession, user: User) -> int:
    """به کاربر شماره قرعه‌کشی منحصر‌به‌فرد بده"""
    if user.lottery_number:
        return user.lottery_number
    # شماره رندوم بین 1000 و 9999
    while True:
        num = random.randint(1000, 9999)
        r = await db.execute(select(User).where(User.lottery_number == num))
        if not r.scalar_one_or_none():
            break
    user.lottery_number = num
    await db.commit()
    return num


async def draw_lottery(db: AsyncSession, count: int = 1) -> List[User]:
    """قرعه‌کشی: برنده‌های رندوم از کاربرانی که شماره دارند"""
    r = await db.execute(select(User).where(User.lottery_number.isnot(None)))
    all_participants = r.scalars().all()
    if not all_participants:
        return []
    count = min(count, len(all_participants))
    return random.sample(all_participants, count)
