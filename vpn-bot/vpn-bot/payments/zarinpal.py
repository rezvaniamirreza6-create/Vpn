import aiohttp
import logging
from typing import Optional, Tuple
from config import config

logger = logging.getLogger(__name__)

ZARINPAL_REQUEST_URL = "https://api.zarinpal.com/pg/v4/payment/request.json"
ZARINPAL_VERIFY_URL = "https://api.zarinpal.com/pg/v4/payment/verify.json"
ZARINPAL_GATEWAY = "https://www.zarinpal.com/pg/StartPay/"

ZARINPAL_SANDBOX_REQUEST = "https://sandbox.zarinpal.com/pg/v4/payment/request.json"
ZARINPAL_SANDBOX_VERIFY = "https://sandbox.zarinpal.com/pg/v4/payment/verify.json"
ZARINPAL_SANDBOX_GATEWAY = "https://sandbox.zarinpal.com/pg/StartPay/"


async def create_zarinpal_payment(amount: int, description: str, callback_url: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Returns (authority, payment_url) or (None, error_message)
    amount in Rials (Tomans * 10)
    """
    req_url = ZARINPAL_SANDBOX_REQUEST if config.ZARINPAL_SANDBOX else ZARINPAL_REQUEST_URL
    gateway = ZARINPAL_SANDBOX_GATEWAY if config.ZARINPAL_SANDBOX else ZARINPAL_GATEWAY

    payload = {
        "merchant_id": config.ZARINPAL_MERCHANT,
        "amount": amount * 10,  # Toman to Rial
        "description": description,
        "callback_url": callback_url,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(req_url, json=payload) as resp:
                data = await resp.json()
                errors = data.get("errors", {})
                if not errors or errors == []:
                    authority = data["data"]["authority"]
                    pay_url = f"{gateway}{authority}"
                    return authority, pay_url
                else:
                    logger.error(f"ZarinPal request error: {data}")
                    return None, f"خطا از درگاه: {errors.get('message', 'نامشخص')}"
    except Exception as e:
        logger.error(f"ZarinPal request exception: {e}")
        return None, "خطا در اتصال به درگاه پرداخت"


async def verify_zarinpal_payment(authority: str, amount: int) -> Tuple[bool, Optional[str]]:
    """
    Returns (success, ref_id)
    """
    verify_url = ZARINPAL_SANDBOX_VERIFY if config.ZARINPAL_SANDBOX else ZARINPAL_VERIFY_URL

    payload = {
        "merchant_id": config.ZARINPAL_MERCHANT,
        "amount": amount * 10,
        "authority": authority,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(verify_url, json=payload) as resp:
                data = await resp.json()
                code = data.get("data", {}).get("code")
                if code in (100, 101):
                    ref_id = str(data["data"].get("ref_id", ""))
                    return True, ref_id
                else:
                    logger.error(f"ZarinPal verify failed: {data}")
                    return False, None
    except Exception as e:
        logger.error(f"ZarinPal verify exception: {e}")
        return False, None
