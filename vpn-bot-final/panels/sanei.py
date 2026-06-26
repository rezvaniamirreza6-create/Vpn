import aiohttp
import uuid
import time
import logging
from typing import Optional, Dict, Any, List
from config import config

logger = logging.getLogger(__name__)


class ThreeXUIPanel:
    """
    3X-UI (Sanaei) Panel API - بدون SSL (http)
    verify_ssl=False و connector بدون تایید SSL
    """

    def __init__(self):
        base = config.PANEL_URL.rstrip("/")
        path = config.PANEL_PATH.strip("/")
        self.base_url = f"{base}/{path}" if path else base
        self.username = config.PANEL_USERNAME
        self.password = config.PANEL_PASSWORD
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(ssl=False)  # ← بدون SSL
            self._session = aiohttp.ClientSession(connector=connector)
        return self._session

    async def login(self) -> bool:
        session = await self._get_session()
        try:
            async with session.post(
                f"{self.base_url}/login",
                json={"username": self.username, "password": self.password},
                ssl=False
            ) as resp:
                data = await resp.json()
                if data.get("success"):
                    logger.info("Panel login successful")
                    return True
                logger.error(f"Panel login failed: {data}")
                return False
        except Exception as e:
            logger.error(f"Panel login error: {e}")
            return False

    async def _request(self, method: str, endpoint: str, **kwargs) -> Optional[Dict]:
        session = await self._get_session()
        url = f"{self.base_url}{endpoint}"
        try:
            async with session.request(method, url, ssl=False, **kwargs) as resp:
                if resp.status == 401:
                    if not await self.login():
                        return None
                    async with session.request(method, url, ssl=False, **kwargs) as resp2:
                        return await resp2.json()
                return await resp.json()
        except aiohttp.ClientConnectorError:
            logger.error(f"Cannot connect to panel at {self.base_url}. آیا پنل روشن است؟")
            return None
        except Exception as e:
            logger.error(f"Panel request error [{endpoint}]: {e}")
            return None

    async def get_inbounds(self) -> List[Dict]:
        data = await self._request("GET", "/panel/api/inbounds/list")
        if data and data.get("success"):
            return data.get("obj", [])
        return []

    async def add_client(self, inbound_id: int, email: str, traffic_gb: int, days: int) -> Optional[Dict]:
        """افزودن کلاینت جدید به inbound"""
        client_uuid = str(uuid.uuid4())
        traffic_bytes = traffic_gb * 1024 ** 3
        expire_ms = int((time.time() + days * 86400) * 1000)

        payload = {
            "id": inbound_id,
            "settings": (
                '{"clients":[{'
                f'"id":"{client_uuid}",'
                f'"email":"{email}",'
                f'"totalGB":{traffic_bytes},'
                f'"expiryTime":{expire_ms},'
                '"enable":true,'
                f'"subId":"{email}",'
                '"tgId":"","reset":0'
                '}]}'
            )
        }

        result = await self._request("POST", "/panel/api/inbounds/addClient", data=payload)
        if result and result.get("success"):
            return {"uuid": client_uuid, "email": email}
        logger.error(f"Add client failed: {result}")
        return None

    async def get_client_traffic(self, email: str) -> Optional[Dict]:
        data = await self._request("GET", f"/panel/api/inbounds/getClientTraffics/{email}")
        if data and data.get("success"):
            return data.get("obj")
        return None

    async def disable_client(self, inbound_id: int, client_uuid: str) -> bool:
        data = await self._request("POST", f"/panel/api/inbounds/{inbound_id}/disableClient/{client_uuid}")
        return bool(data and data.get("success"))

    async def enable_client(self, inbound_id: int, client_uuid: str) -> bool:
        data = await self._request("POST", f"/panel/api/inbounds/{inbound_id}/enableClient/{client_uuid}")
        return bool(data and data.get("success"))

    async def delete_client(self, inbound_id: int, client_uuid: str) -> bool:
        data = await self._request("POST", f"/panel/api/inbounds/{inbound_id}/delClient/{client_uuid}")
        return bool(data and data.get("success"))

    async def reset_client_traffic(self, inbound_id: int, email: str) -> bool:
        data = await self._request("POST", f"/panel/api/inbounds/{inbound_id}/resetClientTraffic/{email}")
        return bool(data and data.get("success"))

    def get_subscription_url(self, email: str) -> str:
        """لینک سابسکریپشن برای کاربر"""
        base = config.PANEL_URL.rstrip("/")
        path = config.PANEL_PATH.strip("/")
        if path:
            return f"{base}/{path}/sub/{email}"
        return f"{base}/sub/{email}"

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()


panel = ThreeXUIPanel()
