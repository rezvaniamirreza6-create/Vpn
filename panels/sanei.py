import aiohttp
import uuid
import time
import json
import base64
import logging
from urllib.parse import urlencode, quote, urlparse
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
        self._csrf = ""
        self.sub_port = config.SUB_PORT
        self.sub_path = config.SUB_PATH
        self.sub_https = True
        self._delete_pattern_idx = None

    async def reload_settings(self, db):
        from database import crud
        url = await crud.get_setting(db, "panel_url", config.PANEL_URL)
        username = await crud.get_setting(db, "panel_username", config.PANEL_USERNAME)
        password = await crud.get_setting(db, "panel_password", config.PANEL_PASSWORD)
        path = await crud.get_setting(db, "panel_path", config.PANEL_PATH)

        base = url.rstrip("/")
        path = path.strip("/") if path else ""
        new_base_url = f"{base}/{path}" if path else base

        if new_base_url != self.base_url or username != self.username or password != self.password:
            self.base_url = new_base_url
            self.username = username
            self.password = password
            self._logged_in = False
            if self._session and not self._session.closed:
                await self._session.close()
            self._session = None
            logger.info(f"Panel settings reloaded: {self.base_url}")

        self.sub_port = await crud.get_setting(db, "sub_port", config.SUB_PORT)
        self.sub_path = await crud.get_setting(db, "sub_path", config.SUB_PATH)
        self.sub_https = (await crud.get_setting(db, "sub_https", "true")) == "true"

    async def _get_session(self):
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(ssl=False)
            self._session = aiohttp.ClientSession(connector=connector, cookie_jar=aiohttp.CookieJar(unsafe=True))
        return self._session

    async def _get_csrf(self):
        session = await self._get_session()
        async with session.get(f"{self.base_url}/csrf-token", ssl=False, timeout=aiohttp.ClientTimeout(total=15)) as r:
            data = await r.json(content_type=None)
            return data.get("obj", "")

    async def login(self, retries: int = 2) -> bool:
        for attempt in range(retries + 1):
            if self._session and not self._session.closed:
                await self._session.close()
            self._session = None
            self._logged_in = False
            session = await self._get_session()
            try:
                csrf = await self._get_csrf()
                async with session.post(
                    f"{self.base_url}/login",
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
                logger.warning(f"Login attempt {attempt+1}/{retries+1} failed: {type(e).__name__}: {e}")
        logger.error("Login failed after retries")
        return False

    async def _request(self, method, endpoint, retries: int = 2, **kwargs):
        if not self._logged_in:
            if not await self.login():
                return None
        session = await self._get_session()
        url = f"{self.base_url}{endpoint}"
        headers = kwargs.pop("headers", {})
        headers["X-CSRF-Token"] = self._csrf
        last_error = None
        for attempt in range(retries + 1):
            if not self._logged_in:
                if not await self.login():
                    last_error = RuntimeError("re-login failed during retry")
                    continue
                headers["X-CSRF-Token"] = self._csrf
                session = await self._get_session()
            try:
                async with session.request(method, url, ssl=False, headers=headers, timeout=aiohttp.ClientTimeout(total=20), **kwargs) as r:
                    if r.status in (401, 403):
                        self._logged_in = False
                        if not await self.login():
                            return None
                        headers["X-CSRF-Token"] = self._csrf
                        session = await self._get_session()
                        async with session.request(method, url, ssl=False, headers=headers, **kwargs) as r2:
                            data = await r2.json(content_type=None)
                    else:
                        data = await r.json(content_type=None)

                    if data is None:
                        raise ValueError(f"Empty/invalid response body (status={r.status})")
                    return data
            except Exception as e:
                last_error = e
                logger.warning(f"Request attempt {attempt+1}/{retries+1} failed [{endpoint}]: {type(e).__name__}: {e}")
                self._logged_in = False
                session = await self._get_session()
        logger.error(f"Request error [{endpoint}]: {type(last_error).__name__}: {last_error}")
        return None

    async def add_client(self, inbound_id: int, email: str, traffic_gb: int, days: int, limit_ip: int = 1, sub_id: str = None) -> Optional[dict]:
        client_uuid = str(uuid.uuid4())
        payload = {
            "inboundIds": [inbound_id],
            "client": {
                "id": client_uuid,
                "email": email,
                "totalGB": int(traffic_gb * 1024 ** 3),
                "expiryTime": int((time.time() + days * 86400) * 1000),
                "enable": True,
                "subId": sub_id or email,
                "tgId": 0,
                "reset": 0,
                "limitIp": max(0, limit_ip)
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
            return {
                "up": obj.get("up", 0),
                "down": obj.get("down", 0),
                "total": obj.get("total", 0),
                "enable": obj.get("enable", True),
                "expiryTime": obj.get("expiryTime", 0),
            }
        return None

    async def delete_client(self, inbound_id: int, client_uuid: str, email: str = None) -> bool:
        candidates = [
            ("POST", f"/panel/api/inbounds/{inbound_id}/delClient/{client_uuid}", None),
        ]
        if email:
            candidates += [
                ("POST", f"/panel/api/clients/del/{email}", None),
                ("POST", "/panel/api/clients/del", {"email": email}),
            ]
        candidates += [
            ("POST", f"/panel/api/clients/del/{client_uuid}", None),
            ("POST", "/panel/api/clients/del", {"id": client_uuid}),
            ("POST", f"/panel/api/inbounds/delClient/{client_uuid}", None),
        ]
        # If we already discovered which pattern this panel accepts, try
        # that one first (single attempt, fast) before falling back.
        if self._delete_pattern_idx is not None and self._delete_pattern_idx < len(candidates):
            method, endpoint, body = candidates[self._delete_pattern_idx]
            kwargs = {"json": body} if body else {}
            data = await self._request(method, endpoint, retries=1, **kwargs)
            if data and data.get("success"):
                return True
        last_data = None
        for idx, (method, endpoint, body) in enumerate(candidates):
            kwargs = {"json": body} if body else {}
            data = await self._request(method, endpoint, retries=0, **kwargs)
            last_data = data
            if data and data.get("success"):
                self._delete_pattern_idx = idx
                logger.info(f"delete_client: working pattern found -> {method} {endpoint} body={body}")
                return True
        logger.error(f"delete_client failed for uuid={client_uuid} email={email} inbound={inbound_id}. Last response: {last_data}")
        return False

    async def get_inbound(self, inbound_id: int) -> Optional[dict]:
        data = await self._request("GET", f"/panel/api/inbounds/get/{inbound_id}")
        if data and data.get("success"):
            return data.get("obj")
        logger.error(f"get_inbound failed: {data}")
        return None

    def _host(self) -> str:
        if config.CONFIG_HOST:
            return config.CONFIG_HOST
        try:
            return urlparse(config.PANEL_URL).hostname or config.PANEL_URL
        except Exception:
            return config.PANEL_URL

    @staticmethod
    def _maybe_json(val):
        if isinstance(val, (dict, list)):
            return val
        if not val:
            return {}
        try:
            return json.loads(val)
        except Exception:
            return {}

    def build_client_link(self, inbound: dict, client_uuid: str, email: str) -> str:
        try:
            protocol = (inbound.get("protocol") or "").lower()
            port = inbound.get("port")
            host = self._host()
            inbound_name = (inbound.get("remark") or "").strip()
            tag_text = f"{inbound_name} - {email}" if inbound_name else email
            remark = quote(tag_text)
            stream = self._maybe_json(inbound.get("streamSettings"))
            network = stream.get("network", "tcp")
            security = stream.get("security", "none")

            params = {"type": network, "security": security}
            sni = host

            if security == "tls":
                tls = stream.get("tlsSettings", {}) or {}
                sni = tls.get("serverName") or host
                params["sni"] = sni
                settings_inner = tls.get("settings", {}) or {}
                fp = settings_inner.get("fingerprint") or tls.get("fingerprint")
                if fp:
                    params["fp"] = fp
                alpn = tls.get("alpn")
                if alpn:
                    params["alpn"] = ",".join(alpn) if isinstance(alpn, list) else alpn
            elif security == "reality":
                rs = stream.get("realitySettings", {}) or {}
                settings_inner = rs.get("settings", {}) or {}
                sni_list = rs.get("serverNames") or []
                sni = sni_list[0] if sni_list else host
                params["sni"] = sni
                pbk = settings_inner.get("publicKey", "")
                if pbk:
                    params["pbk"] = pbk
                params["fp"] = settings_inner.get("fingerprint", "chrome")
                sid_list = rs.get("shortIds") or []
                if sid_list:
                    params["sid"] = sid_list[0]
                spx = settings_inner.get("spiderX", "")
                if spx:
                    params["spx"] = spx

            if network == "ws":
                ws = stream.get("wsSettings", {}) or {}
                params["path"] = ws.get("path", "/")
                ws_host = (ws.get("headers") or {}).get("Host", "")
                if ws_host:
                    params["host"] = ws_host
            elif network == "grpc":
                grpc = stream.get("grpcSettings", {}) or {}
                params["serviceName"] = grpc.get("serviceName", "")
                params["mode"] = "multi" if grpc.get("multiMode") else "gun"
            elif network in ("h2", "http"):
                h2 = stream.get("httpSettings", {}) or {}
                params["path"] = h2.get("path", "/")
                h2_host = h2.get("host") or []
                if h2_host:
                    params["host"] = h2_host[0] if isinstance(h2_host, list) else h2_host

            if protocol == "vless":
                flow = ""
                try:
                    settings_obj = self._maybe_json(inbound.get("settings"))
                    for c in settings_obj.get("clients", []):
                        if c.get("id") == client_uuid or c.get("email") == email:
                            flow = c.get("flow", "")
                            break
                except Exception:
                    pass
                if flow:
                    params["flow"] = flow
                qs = urlencode({k: v for k, v in params.items() if v not in (None, "")})
                return f"vless://{client_uuid}@{host}:{port}?{qs}#{remark}"

            if protocol == "trojan":
                qs = urlencode({k: v for k, v in params.items() if v not in (None, "")})
                return f"trojan://{client_uuid}@{host}:{port}?{qs}#{remark}"

            if protocol == "vmess":
                vmess_obj = {
                    "v": "2", "ps": tag_text, "add": host, "port": str(port),
                    "id": client_uuid, "aid": "0", "scy": "auto", "net": network,
                    "type": "none", "host": params.get("host", ""), "path": params.get("path", "/"),
                    "tls": "tls" if security in ("tls", "reality") else "", "sni": sni
                }
                b64 = base64.b64encode(json.dumps(vmess_obj).encode()).decode()
                return f"vmess://{b64}"

            return ""
        except Exception as e:
            logger.error(f"build_client_link error: {type(e).__name__}: {e}")
            return ""

    async def get_client_config_link(self, inbound_id: int, client_uuid: str, email: str) -> str:
        inbound = await self.get_inbound(inbound_id)
        if not inbound:
            return ""
        return self.build_client_link(inbound, client_uuid, email)

    def get_subscription_url(self, email: str) -> str:
        host = self._host()
        port_part = f":{self.sub_port}" if self.sub_port else ""
        path_part = self.sub_path.strip("/") if self.sub_path else "sub"
        scheme = "https" if getattr(self, "sub_https", True) else "http"
        return f"{scheme}://{host}{port_part}/{path_part}/{email}"

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()


panel = ThreeXUIPanel()
