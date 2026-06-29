import aiohttp
import uuid
import time
import json
import logging
from typing import Optional
from database.db import AsyncSessionLocal
from database.crud import get_setting

logger = logging.getLogger(__name__)


class ThreeXUIPanel:
    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self._logged_in = False
        self._csrf: str = ""
        self._base_url: str = ""

    async def _load_config(self):
        async with AsyncSessionLocal() as db:
            url = await get_setting(db, "panel_url", "")
            path = await get_setting(db, "panel_path", "")
            self.username = await get_setting(db, "panel_username", "")
            self.password = await get_setting(db, "panel_password", "")
        base = url.rstrip("/")
        p = path.strip("/")
        self._base_url = f"{base}/{p}" if p else base

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(ssl=False)
            self._session = aiohttp.ClientSession(
                connector=connector,
                cookie_jar=aiohttp.CookieJar(unsafe=True)
            )
        return self._session

    async def _get_csrf(self) -> str:
        session = await self._get_session()
        async with session.get(
            f"{self._base_url}/csrf-token",
            ssl=False, timeout=aiohttp.ClientTimeout(total=15)
        ) as r:
            data = await r.json(content_type=None)
            return data.get("obj", "")

    async def login(self) -> bool:
        await self._load_config()
        if not self._base_url:
            logger.error("Panel URL not configured")
            return False
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None
        self._logged_in = False
        session = await self._get_session()
        try:
            csrf = await self._get_csrf()
            async with session.post(
                f"{self._base_url}/login",
                data={"username": self.username, "password": self.password},
                headers={"X-CSRF-Token": csrf},
                ssl=False, timeout=aiohttp.ClientTimeout(total=15)
            ) as r:
                data = await r.json(content_type=None)
                if data.get("success"):
                    self._logged_in = True
                    self._csrf = await self._get_csrf()
                    logger.info("Panel login successful!")
                    return True
                logger.error(f"Login failed: {data}")
                return False
        except Exception as e:
            logger.error(f"Login error: {type(e).__name__}: {e}")
            return False

    async def _request(self, method: str, endpoint: str, **kwargs) -> Optional[dict]:
        if not self._logged_in:
            if not await self.login():
                return None
        session = await self._get_session()
        url = f"{self._base_url}{endpoint}"
        headers = kwargs.pop("headers", {})
        headers["X-CSRF-Token"] = self._csrf
        try:
            async with session.request(
                method, url, ssl=False, headers=headers,
                timeout=aiohttp.ClientTimeout(total=30), **kwargs
            ) as r:
                if r.status in (401, 403):
                    self._logged_in = False
                    if not await self.login():
                        return None
                    headers["X-CSRF-Token"] = self._csrf
                    session = await self._get_session()
                    async with session.request(method, url, ssl=False, headers=headers, **kwargs) as r2:
                        return await r2.json(content_type=None)
                return await r.json(content_type=None)
        except Exception as e:
            logger.error(f"Request error [{endpoint}]: {type(e).__name__}: {e}")
            return None

    async def add_client(self, inbound_id: int, email: str, traffic_gb: int, days: int) -> Optional[dict]:
        client_uuid = str(uuid.uuid4())
        payload = {
            "inboundIds": [inbound_id],
            "client": {
                "id": client_uuid,
                "email": email,
                "totalGB": traffic_gb * 1024 ** 3,
                "expiryTime": int((time.time() + days * 86400) * 1000),
                "enable": True,
                "subId": email,
                "tgId": 0,
                "reset": 0
            }
        }
        result = await self._request("POST", "/panel/api/clients/add", json=payload)
        if result and result.get("success"):
            logger.info(f"Client added: {email}")
            return {"uuid": client_uuid, "email": email}
        logger.error(f"add_client failed: {result}")
        return None

    async def get_client_traffic(self, email: str) -> Optional[dict]:
        data = await self._request("GET", f"/panel/api/clients/get/{email}")
        if data and data.get("success"):
            obj = data.get("obj", {})
            if isinstance(obj, list) and obj:
                obj = obj[0]
            return {"up": obj.get("up", 0), "down": obj.get("down", 0),
                    "total": obj.get("total", 0), "expiryTime": obj.get("expiryTime", 0)}
        return None

    async def delete_client(self, inbound_id: int, client_uuid: str) -> bool:
        data = await self._request("POST", f"/panel/api/clients/del/{client_uuid}")
        return bool(data and data.get("success"))

    def get_subscription_url(self, base_url: str, panel_path: str, email: str) -> str:
        base = base_url.rstrip("/")
        path = panel_path.strip("/")
        if path:
            return f"{base}/{path}/sub/{email}"
        return f"{base}/sub/{email}"

    async def get_inbounds(self) -> list:
        data = await self._request("GET", "/panel/api/inbounds/list")
        if data and data.get("success"):
            return data.get("obj", [])
        return []

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()


panel = ThreeXUIPanel()
