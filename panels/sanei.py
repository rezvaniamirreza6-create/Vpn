import aiohttp
import uuid
import time
import logging
from typing import Optional, Dict, Any, List
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
        # 3x-ui login endpoint - try both paths
        for login_path in ["/login", "/panel/login"]:
            try:
                async with session.post(
                    f"{self.base_url}{login_path}",
                    data={"username": self.username, "password": self.password},
                    timeout=aiohttp.ClientTimeout(total=15),
                    ssl=False
                ) as resp:
                    text = await resp.text()
                    try:
                        data = await resp.json(content_type=None)
                        if data.get("success"):
                            self._logged_in = True
                            logger.info(f"Panel login OK via {login_path}")
                            return True
                    except Exception:
                        if resp.status == 200:
                            self._logged_in = True
                            return True
            except Exception as e:
                logger.warning(f"Login attempt {login_path} failed: {e}")
                continue
        logger.error(f"All login attempts failed for {self.base_url}")
        return False

    async def _request(self, method: str, endpoint: str, **kwargs) -> Optional[Dict]:
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
                if resp.status == 401:
                    self._logged_in = False
                    if not await self.login():
                        return None
                    async with session.request(method, url, ssl=False, **kwargs) as resp2:
                        return await resp2.json(content_type=None)
                return await resp.json(content_type=None)
        except aiohttp.ClientConnectorError:
            logger.error(f"Cannot connect to panel at {self.base_url}")
            return None
        except Exception as e:
            logger.error(f"Panel request error [{endpoint}]: {e}")
            return None

    async def add_client(self, inbound_id: int, email: str, traffic_gb: int, days: int) -> Optional[Dict]:
        client_uuid = str(uuid.uuid4())
        traffic_bytes = traffic_gb * 1024 ** 3
        expire_ms = int((time.time() + days * 86400) * 1000)

        import json
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

        # Try both API paths
        for api_path in ["/panel/api/inbounds/addClient", "/xui/API/inbounds/addClient"]:
            result = await self._request(
                "POST", api_path,
                data={"id": inbound_id, "settings": settings}
            )
            if result and result.get("success"):
                logger.info(f"Client added OK via {api_path}")
                return {"uuid": client_uuid, "email": email}

        logger.error(f"add_client failed for inbound {inbound_id}")
        return None

    async def get_client_traffic(self, email: str) -> Optional[Dict]:
        for api_path in [
            f"/panel/api/inbounds/getClientTraffics/{email}",
            f"/xui/API/inbounds/getClientTraffics/{email}"
        ]:
            data = await self._request("GET", api_path)
            if data and data.get("success"):
                return data.get("obj")
        return None

    async def delete_client(self, inbound_id: int, client_uuid: str) -> bool:
        for api_path in [
            f"/panel/api/inbounds/{inbound_id}/delClient/{client_uuid}",
            f"/xui/API/inbounds/{inbound_id}/delClient/{client_uuid}"
        ]:
            data = await self._request("POST", api_path)
            if data and data.get("success"):
                return True
        return False

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
