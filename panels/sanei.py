"""
3x-ui Panel API using py3xui - the official async SDK
"""
import logging
import uuid
import time
from typing import Optional
from config import config

logger = logging.getLogger(__name__)


class ThreeXUIPanel:
    def __init__(self):
        self.base_url = config.PANEL_URL.rstrip("/")
        path = config.PANEL_PATH.strip("/") if config.PANEL_PATH else ""
        if path:
            self.full_url = f"{self.base_url}/{path}"
        else:
            self.full_url = self.base_url
        self.username = config.PANEL_USERNAME
        self.password = config.PANEL_PASSWORD
        self._api = None

    async def _get_api(self):
        if self._api is None:
            try:
                from py3xui import AsyncApi
                use_https = self.full_url.startswith("https")
                self._api = AsyncApi(
                    self.full_url,
                    self.username,
                    self.password,
                    use_tls_verify=False,
                    logger=logger,
                )
                await self._api.login()
                logger.info(f"Panel login OK: {self.full_url}")
            except Exception as e:
                logger.error(f"Panel login failed: {e}")
                self._api = None
        return self._api

    async def add_client(self, inbound_id: int, email: str, traffic_gb: int, days: int) -> Optional[dict]:
        try:
            api = await self._get_api()
            if not api:
                return None

            from py3xui import Client
            client = Client(
                id=str(uuid.uuid4()),
                email=email,
                enable=True,
                total_gb=traffic_gb * 1024 ** 3,
                expiry_time=int((time.time() + days * 86400) * 1000),
                sub_id=email,
                flow="",
            )
            await api.client.add(inbound_id, [client])
            logger.info(f"Client added: {email}")
            return {"uuid": client.id, "email": email}
        except Exception as e:
            logger.error(f"add_client error: {e}")
            self._api = None  # reset on error
            return None

    async def get_client_traffic(self, email: str) -> Optional[dict]:
        try:
            api = await self._get_api()
            if not api:
                return None
            client = await api.client.get_by_email(email)
            if client:
                return {"up": client.up or 0, "down": client.down or 0}
        except Exception as e:
            logger.error(f"get_client_traffic error: {e}")
        return None

    async def delete_client(self, inbound_id: int, client_uuid: str) -> bool:
        try:
            api = await self._get_api()
            if not api:
                return False
            await api.client.delete(inbound_id, client_uuid)
            return True
        except Exception as e:
            logger.error(f"delete_client error: {e}")
            return False

    def get_subscription_url(self, email: str) -> str:
        base = self.base_url
        path = config.PANEL_PATH.strip("/") if config.PANEL_PATH else ""
        if path:
            return f"{base}/{path}/sub/{email}"
        return f"{base}/sub/{email}"

    async def close(self):
        self._api = None


panel = ThreeXUIPanel()
