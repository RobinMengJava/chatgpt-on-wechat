"""
Ticket API client with automatic login and token caching.

Handles authentication for the Lulu ticket system (JeecgBoot-based Spring Boot).
Token is cached to ~/.cow/ticket_token.json and auto-refreshed on expiry.

Config keys (in config.json):
    ticket_api_base      - API base URL (default: https://wap.luluroad.com)
    ticket_api_user      - Login username
    ticket_api_password  - Login password
"""

import base64
import json
import os
import time
from typing import Optional

from common.log import logger
from config import conf

TOKEN_CACHE_FILE = os.path.expanduser("~/.cow/ticket_token.json")


def _decode_jwt_exp(token: str) -> Optional[int]:
    """Decode JWT payload to get exp timestamp (no signature verification)."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload = parts[1]
        payload += "=" * (4 - len(payload) % 4)
        data = json.loads(base64.b64decode(payload))
        return data.get("exp")
    except Exception:
        return None


class TicketApiClient:
    """HTTP client for Lulu ticket system. Handles login, token caching, and auto-retry."""

    def __init__(self):
        self.base_url = conf().get("ticket_api_base", "https://wap.luluroad.com").rstrip("/")
        self.username = conf().get("ticket_api_user", "")
        self.password = conf().get("ticket_api_password", "")

    # ------------------------------------------------------------------
    # Token cache management
    # ------------------------------------------------------------------

    def _load_cached_token(self) -> Optional[str]:
        """Load token from cache. Returns None if missing or expiring within 5 minutes."""
        try:
            if not os.path.exists(TOKEN_CACHE_FILE):
                return None
            with open(TOKEN_CACHE_FILE, "r") as f:
                data = json.load(f)
            token = data.get("token")
            expires_at = data.get("expires_at", 0)
            if not token:
                return None
            if time.time() >= expires_at - 300:
                return None
            return token
        except Exception as e:
            logger.warning(f"[TicketApiClient] Failed to load cached token: {e}")
            return None

    def _save_token(self, token: str):
        """Persist token and its expiry to cache file."""
        try:
            os.makedirs(os.path.dirname(TOKEN_CACHE_FILE), exist_ok=True)
            exp = _decode_jwt_exp(token)
            expires_at = exp if exp else int(time.time()) + 86400  # fallback: 24h
            with open(TOKEN_CACHE_FILE, "w") as f:
                json.dump({"token": token, "expires_at": expires_at}, f)
        except Exception as e:
            logger.warning(f"[TicketApiClient] Failed to save token: {e}")

    def _clear_token(self):
        """Delete cached token to force re-login on next request."""
        try:
            if os.path.exists(TOKEN_CACHE_FILE):
                os.remove(TOKEN_CACHE_FILE)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def login(self) -> str:
        """Login and return a fresh token. Raises ValueError on failure."""
        if not self.username or not self.password:
            raise ValueError(
                "ticket_api_user and ticket_api_password must be configured in config.json"
            )

        try:
            import requests as _requests
        except ImportError:
            raise RuntimeError("requests library is required. Run: pip install requests")

        url = f"{self.base_url}/sys/login"
        body = {
            "username": self.username,
            "password": self.password,
            "captcha": "",
            "checkKey": int(time.time() * 1000),
        }

        resp = _requests.post(url, json=body, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        if not data.get("success"):
            raise ValueError(f"Login failed: {data.get('message', 'unknown error')}")

        token = data.get("result", {}).get("token")
        if not token:
            raise ValueError("Login response missing token field")

        self._save_token(token)
        logger.info("[TicketApiClient] Login successful, token cached")
        return token

    def get_token(self) -> str:
        """Return a valid token, re-login if cached token is missing or expired."""
        token = self._load_cached_token()
        if not token:
            token = self.login()
        return token

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def post(self, path: str, body: dict) -> dict:
        """
        POST to the ticket API with automatic token injection and 401 retry.

        :param path: API path, e.g. /web/bus/luluOrder/customAmtRefund
        :param body: Request body as dict
        :return: Parsed response JSON
        :raises: requests.HTTPError on non-2xx, ValueError on API-level errors
        """
        try:
            import requests as _requests
        except ImportError:
            raise RuntimeError("requests library is required. Run: pip install requests")

        url = f"{self.base_url}{path}"
        token = self.get_token()
        headers = {
            "Content-Type": "application/json",
            # JeecgBoot uses X-Access-Token header; adjust if your backend differs
            "X-Access-Token": token,
        }

        resp = _requests.post(url, json=body, headers=headers, timeout=30)

        # Token expired mid-session: clear cache, re-login, retry once
        if resp.status_code == 401:
            logger.info("[TicketApiClient] Got 401, re-logging in")
            self._clear_token()
            token = self.login()
            headers["X-Access-Token"] = token
            resp = _requests.post(url, json=body, headers=headers, timeout=30)

        resp.raise_for_status()
        return resp.json()

    def get(self, path: str, params: dict = None) -> dict:
        """
        GET the ticket API with automatic token injection and 401 retry.

        :param path: API path, e.g. /web/bus/luluOrder/queryWxOrder
        :param params: Query string parameters as dict
        :return: Parsed response JSON
        """
        try:
            import requests as _requests
        except ImportError:
            raise RuntimeError("requests library is required. Run: pip install requests")

        url = f"{self.base_url}{path}"
        token = self.get_token()
        headers = {"X-Access-Token": token}

        resp = _requests.get(url, params=params, headers=headers, timeout=30)

        if resp.status_code == 401:
            logger.info("[TicketApiClient] Got 401, re-logging in")
            self._clear_token()
            token = self.login()
            headers["X-Access-Token"] = token
            resp = _requests.get(url, params=params, headers=headers, timeout=30)

        resp.raise_for_status()
        return resp.json()
