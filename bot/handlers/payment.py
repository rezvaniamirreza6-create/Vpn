"""
Payment handler - Zarinpal callback webhook + aiogram router
"""
import logging
from aiogram import Router
from aiohttp import web
from payments.zarinpal import verify_zarinpal_payment
from database.db import AsyncSessionLocal, TransactionType, PaymentStatus
from database import crud

logger = logging.getLogger(__name__)

# Empty router - required by main.py include_router
# Zarinpal callback is handled via aiohttp web server (see main.py if webhook needed)
router = Router()


async def zarinpal_callback(request: web.Request) -> web.Response:
    """GET /payment/zarinpal?Authority=...&Status=OK"""
    authority = request.rel_url.query.get("Authority", "")
    status = request.rel_url.query.get("Status", "")

    if status != "OK" or not authority:
        return web.Response(text="پرداخت لغو شد.", content_type="text/html")

    async with AsyncSessionLocal() as db:
        pay = await crud.get_payment_by_authority(db, authority)
        if not pay or pay.status != PaymentStatus.PENDING:
            return web.Response(text="پرداخت قبلاً پردازش شده.", content_type="text/html")

        ok, ref_id = await verify_zarinpal_payment(authority, int(pay.amount))
        if ok:
            pay.status = PaymentStatus.PAID
            pay.ref_id = ref_id
            from sqlalchemy import select
            from database.db import User
            r = await db.execute(select(User).where(User.id == pay.user_id))
            user = r.scalar_one_or_none()
            if user:
                await crud.update_wallet(
                    db, user, pay.amount,
                    f"شارژ زرین‌پال (ref: {ref_id})",
                    TransactionType.DEPOSIT
                )
            await db.commit()
            return web.Response(
                text=f"<html><body>✅ پرداخت موفق! کیف پول شارژ شد.<br>کد پیگیری: {ref_id}</body></html>",
                content_type="text/html"
            )
        else:
            pay.status = PaymentStatus.REJECTED
            await db.commit()
            return web.Response(text="❌ پرداخت تایید نشد.", content_type="text/html")
