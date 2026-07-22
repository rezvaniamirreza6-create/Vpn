from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy import String, Integer, BigInteger, Float, Boolean, DateTime, Text, ForeignKey, Enum
from datetime import datetime
from typing import Optional, List
import enum, os


class Base(DeclarativeBase):
    pass


class UserStatus(enum.Enum):
    ACTIVE = "active"
    BANNED = "banned"


class ServiceStatus(enum.Enum):
    ACTIVE = "active"
    EXPIRED = "expired"


class TransactionType(enum.Enum):
    DEPOSIT = "deposit"
    PURCHASE = "purchase"
    REFERRAL = "referral"
    ADJUST = "adjust"
    LOTTERY = "lottery"


class PaymentMethod(enum.Enum):
    ZARINPAL = "zarinpal"
    CARD = "card"


class PaymentStatus(enum.Enum):
    PENDING = "pending"
    PAID = "paid"
    REJECTED = "rejected"


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(64))
    full_name: Mapped[str] = mapped_column(String(128), default="")
    wallet: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[UserStatus] = mapped_column(Enum(UserStatus), default=UserStatus.ACTIVE)
    has_used_test: Mapped[bool] = mapped_column(Boolean, default=False)
    referred_by: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    phone_exempt: Mapped[bool] = mapped_column(Boolean, default=False)
    lottery_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    services: Mapped[List["Service"]] = relationship(back_populates="user")
    payments: Mapped[List["Payment"]] = relationship(back_populates="user")


class AdminUser(Base):
    __tablename__ = "admin_users"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(128), default="")
    permissions: Mapped[str] = mapped_column(Text, default="[]")
    added_by: Mapped[int] = mapped_column(BigInteger, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Category(Base):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    icon: Mapped[str] = mapped_column(String(32), default="📦")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    plans: Mapped[List["Plan"]] = relationship(back_populates="category")


class Plan(Base):
    __tablename__ = "plans"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    traffic_gb: Mapped[int] = mapped_column(Integer, nullable=False)
    days: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[float] = mapped_column(Float, nullable=False)
    max_users: Mapped[int] = mapped_column(Integer, default=1)
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id"), nullable=True)
    inbound_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    category: Mapped[Optional["Category"]] = relationship(back_populates="plans")


class DiscountCode(Base):
    __tablename__ = "discount_codes"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    percent: Mapped[int] = mapped_column(Integer, nullable=False)
    max_uses: Mapped[int] = mapped_column(Integer, default=1)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class Service(Base):
    __tablename__ = "services"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    plan_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    panel_uuid: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    panel_email: Mapped[str] = mapped_column(String(128), nullable=False)
    service_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    inbound_id: Mapped[int] = mapped_column(Integer, nullable=False)
    traffic_gb: Mapped[int] = mapped_column(Integer, nullable=False)
    days: Mapped[int] = mapped_column(Integer, nullable=False)
    max_users: Mapped[int] = mapped_column(Integer, default=1)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    status: Mapped[ServiceStatus] = mapped_column(Enum(ServiceStatus), default=ServiceStatus.ACTIVE)
    is_test: Mapped[bool] = mapped_column(Boolean, default=False)
    panel_removed: Mapped[bool] = mapped_column(Boolean, default=False)
    sub_link: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    vless_link: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notified_80: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    user: Mapped["User"] = relationship(back_populates="services")


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    method: Mapped[PaymentMethod] = mapped_column(Enum(PaymentMethod), nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus), default=PaymentStatus.PENDING)
    receipt_file_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    plan_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    user: Mapped["User"] = relationship(back_populates="payments")


class ForceJoin(Base):
    __tablename__ = "force_joins"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    channel_id: Mapped[str] = mapped_column(String(64), nullable=False)
    channel_name: Mapped[str] = mapped_column(String(128), default="")
    invite_link: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class BotSetting(Base):
    __tablename__ = "bot_settings"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)


_raw_url = os.getenv("DATABASE_URL", "sqlite:///vpnbot.db")
if _raw_url.startswith("postgresql://"):
    _DATABASE_URL = _raw_url.replace("postgresql://", "postgresql+asyncpg://", 1)
elif _raw_url.startswith("postgres://"):
    _DATABASE_URL = _raw_url.replace("postgres://", "postgresql+asyncpg://", 1)
elif _raw_url.startswith("sqlite"):
    _DATABASE_URL = _raw_url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
else:
    _DATABASE_URL = _raw_url

engine = create_async_engine(_DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

DEFAULTS = {
    "bot_name": "فروشگاه VPN",
    "card_number": "", "card_holder": "",
    "referral_reward": "50000",
    "free_test_enabled": "true",
    "free_test_traffic_mb": "500",
    "free_test_days": "1",
    "lottery_active": "false",
    "lottery_auto_send": "true",
    "lottery_prize_gb": "10",
    "lottery_prize_days": "30",
    "auto_config_send": "true",
    "zarinpal_merchant": "",
    "inbound_id": "1",
    "support_username": "",
    "force_join_enabled": "false",
    "panel_url": "", "panel_path": "",
    "panel_username": "", "panel_password": "",
    "usage_80_text": "⚠️ هشدار مصرف!\n\nشما {percent}٪ از حجم اشتراک خود را مصرف کرده‌اید.\n\n📊 کل: {total}GB\n📉 مصرف شده: {used}GB\n📈 باقی‌مانده: {remaining}GB\n\nبرای جلوگیری از قطعی، تمدید کنید 👇",
}


async def _migrate_add_columns():
    stmts = [
        "ALTER TABLE plans ADD COLUMN max_users INTEGER DEFAULT 1",
        "ALTER TABLE services ADD COLUMN max_users INTEGER DEFAULT 1",
    ]
    async with engine.begin() as conn:
        for stmt in stmts:
            try:
                from sqlalchemy import text
                await conn.execute(text(stmt))
            except Exception:
                pass


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _migrate_add_columns()
    async with AsyncSessionLocal() as session:
        from sqlalchemy import select
        for k, v in DEFAULTS.items():
            r = await session.execute(select(BotSetting).where(BotSetting.key == k))
            if not r.scalar_one_or_none():
                session.add(BotSetting(key=k, value=v))
        await session.commit()
