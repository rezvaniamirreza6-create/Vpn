import aiohttp
import uuid
import time
import json
import logging
from typing import Optional
from config import config

logger = logging.getLogger(__name__)


class ThreeXUIPanel:
    def __init__(self):
        base = config.PANEL_URL.rstrip("/")
        path = config.PANEL_PATH.strip("/") if config.PANEL_PATH else ""
        self.base_url = f"{base}/{path}" if path else base
        self.username = config.PANEL_USERNAME
        self.password = config.PANEL_PASSWORD
        self._session: Optional[aiohttp.ClientSession] = None
        self._logged_in = False

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(ssl=False)
            self._session = aiohttp.ClientSession(connector=connector)
        return self._session

    async def login(self) -> bool:
        session = await self._get_session()
        try:
            # Step 1: Get CSRF token
            async with session.get(
                f"{self.base_url}/csrf-token",
                timeout=aiohttp.ClientTimeout(total=15),
                ssl=False
            ) as resp:
                if resp.status != 200:
                    logger.error(f"CSRF token failed: {resp.status}")
                    return False
                data = await resp.json(content_type=None)
                csrf_token = data.get("obj", "")
                logger.info(f"Got CSRF token: {csrf_token[:10]}...")

            # Step 2: Login with CSRF token
            async with session.post(
                f"{self.base_url}/login",
                data={"username": self.username, "password": self.password},
                headers={"X-CSRF-Token": csrf_token},
                timeout=aiohttp.ClientTimeout(total=15),
                ssl=False
            ) as resp:
                data = await resp.json(content_type=None)
                if data.get("success"):
                    self._logged_in = True
                    logger.info("Panel login successful!")
                    return True
                logger.error(f"Login failed: {data}")
                return False

        except Exception as e:
            logger.error(f"Login error: {e}")
            return False

    async def _request(self, method: str, endpoint: str, **kwargs) -> Optional[dict]:
        if not self._logged_in:
            if not await self.login():
                return None
        session = await self._get_session()
        url = f"{self.base_url}{endpoint}"
        try:
            async with session.request(
                method, url, ssl=False,
                timeout=aiohttp.ClientTimeout(total=30),
                **kwargs
            ) as resp:
                if resp.status == 401 or resp.status == 403:
                    self._logged_in = False
                    if not await self.login():
                        return None
                    async with session.request(
                        method, url, ssl=False,
                        timeout=aiohttp.ClientTimeout(total=30),
                        **kwargs
                    ) as resp2:
                        return await resp2.json(content_type=None)
                return await resp.json(content_type=None)
        except Exception as e:
            logger.error(f"Request error [{endpoint}]: {e}")
            return None

    async def add_client(self, inbound_id: int, email: str, traffic_gb: int, days: int) -> Optional[dict]:
        client_uuid = str(uuid.uuid4())
        traffic_bytes = traffic_gb * 1024 ** 3
        expire_ms = int((time.time() + days * 86400) * 1000)

        settings = json.dumps({"clients": [{
            "id": client_uuid,
            "email": email,
            "totalGB": traffic_bytes,
            "expiryTime": expire_ms,
            "enable": True,
            "subId": email,
            "tgId": "",
            "reset": 0
        }]})

        result = await self._request(
            "POST", "/panel/api/inbounds/addClient",
            data={"id": inbound_id, "settings": settings}
        )
        if result and result.get("success"):
            logger.info(f"Client added: {email}")
            return {"uuid": client_uuid, "email": email}
        logger.error(f"add_client failed: {result}")
        return None

    async def get_client_traffic(self, email: str) -> Optional[dict]:
        data = await self._request("GET", f"/panel/api/inbounds/getClientTraffics/{email}")
        if data and data.get("success"):
            return data.get("obj")
        return None

    async def delete_client(self, inbound_id: int, client_uuid: str) -> bool:
        data = await self._request(
            "POST", f"/panel/api/inbounds/{inbound_id}/delClient/{client_uuid}"
        )
        return bool(data and data.get("success"))

    def get_subscription_url(self, email: str) -> str:
        base = config.PANEL_URL.rstrip("/")
        path = config.PANEL_PATH.strip("/") if config.PANEL_PATH else ""
        if path:
            return f"{base}/{path}/sub/{email}"
        return f"{base}/sub/{email}"

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()


panel = ThreeXUIPanel()
