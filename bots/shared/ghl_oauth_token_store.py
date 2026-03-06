"""
Shared GoHighLevel OAuth token storage and tenant client resolution.

Stores OAuth credentials keyed by GHL location ID so bot traffic can be routed
to the correct customer sub-account at runtime.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import httpx

from bots.shared.cache_service import get_cache_service
from bots.shared.config import settings
from bots.shared.ghl_client import GHLClient
from bots.shared.logger import get_logger

logger = get_logger(__name__)

_TOKEN_URL = os.getenv("GHL_OAUTH_TOKEN_URL", "https://services.leadconnectorhq.com/oauth/token")
_TOKEN_KEY_PREFIX = "ghl:oauth:location"
_LOCATION_SET_KEY = "ghl:oauth:locations"
_TOKEN_CACHE_TTL_SECONDS = 60 * 60 * 24 * 180  # 180 days
_REFRESH_SKEW_SECONDS = 120


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    if not isinstance(ts, str) or not ts.strip():
        return None
    try:
        parsed = datetime.fromisoformat(ts)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return None


def _oauth_setting(name: str, env_var: str, default: Optional[str] = None) -> Optional[str]:
    value = getattr(settings, name, None)
    if value in (None, ""):
        value = os.getenv(env_var, default)
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return default
    return value


def _oauth_user_type() -> str:
    raw_type = (_oauth_setting("ghl_oauth_user_type", "GHL_OAUTH_USER_TYPE", "Company") or "Company").strip().lower()
    if raw_type == "location":
        return "Location"
    return "Company"


class GHLOAuthTokenStore:
    """Persists GHL OAuth credentials by location and refreshes as needed."""

    def __init__(self):
        self.cache = get_cache_service()

    @staticmethod
    def _key(location_id: str) -> str:
        return f"{_TOKEN_KEY_PREFIX}:{location_id}"

    async def store_tokens(
        self,
        location_id: str,
        access_token: str,
        refresh_token: Optional[str] = None,
        expires_in: Optional[Any] = None,
        token_payload: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Store or update OAuth tokens for a location."""
        if not isinstance(location_id, str) or not location_id.strip():
            return False
        if not isinstance(access_token, str) or not access_token.strip():
            return False

        location_id = location_id.strip()
        existing = await self.get_tokens(location_id)
        effective_refresh = (
            refresh_token.strip()
            if isinstance(refresh_token, str) and refresh_token.strip()
            else (existing or {}).get("refresh_token")
        )

        expiry: Optional[datetime] = None
        try:
            if expires_in is not None and str(expires_in).strip():
                expiry = _utcnow() + timedelta(seconds=max(0, int(expires_in)))
        except (ValueError, TypeError):
            expiry = None

        payload = {
            "location_id": location_id,
            "access_token": access_token.strip(),
            "refresh_token": effective_refresh,
            "expires_at": _isoformat(expiry) if expiry else (existing or {}).get("expires_at"),
            "updated_at": _isoformat(_utcnow()),
            "token_type": (
                token_payload.get("token_type")
                if isinstance(token_payload, dict)
                else (existing or {}).get("token_type")
            ),
            "scope": (
                token_payload.get("scope")
                if isinstance(token_payload, dict)
                else (existing or {}).get("scope")
            ),
        }

        ok = await self.cache.set(self._key(location_id), payload, ttl=_TOKEN_CACHE_TTL_SECONDS)
        await self.cache.sadd(_LOCATION_SET_KEY, location_id, ttl=_TOKEN_CACHE_TTL_SECONDS)
        return bool(ok)

    async def get_tokens(self, location_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve stored OAuth tokens for a location."""
        if not isinstance(location_id, str) or not location_id.strip():
            return None
        payload = await self.cache.get(self._key(location_id.strip()))
        if not isinstance(payload, dict):
            return None
        return payload

    async def build_client(
        self,
        location_id: str,
        fallback_client: Optional[GHLClient] = None,
    ) -> Optional[GHLClient]:
        """Return a location-scoped GHL client, preferring OAuth tokens."""
        token = await self.get_access_token(location_id)
        if token:
            try:
                return GHLClient(api_key=token, location_id=location_id)
            except Exception as exc:
                logger.warning(f"Failed to build OAuth GHL client for location {location_id}: {exc}")

        if fallback_client is not None:
            return fallback_client

        fallback_api_key = settings.ghl_api_key or ""
        fallback_location = location_id or settings.ghl_location_id
        if fallback_api_key and fallback_location:
            try:
                return GHLClient(api_key=fallback_api_key, location_id=fallback_location)
            except Exception as exc:
                logger.warning(f"Failed to build fallback GHL client for location {location_id}: {exc}")
        return None

    async def get_access_token(self, location_id: str) -> Optional[str]:
        """Return valid access token for a location, refreshing when needed."""
        tokens = await self.get_tokens(location_id)
        if not tokens:
            return None

        access_token = tokens.get("access_token")
        if not isinstance(access_token, str) or not access_token.strip():
            return None

        expires_at = _parse_iso(tokens.get("expires_at"))
        if not expires_at:
            return access_token.strip()

        if expires_at - timedelta(seconds=_REFRESH_SKEW_SECONDS) > _utcnow():
            return access_token.strip()

        refreshed = await self.refresh_tokens(location_id, current=tokens)
        if refreshed and isinstance(refreshed.get("access_token"), str):
            return refreshed["access_token"].strip()
        return None

    async def refresh_tokens(
        self,
        location_id: str,
        current: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Refresh OAuth tokens for a location via GHL refresh_token grant."""
        current = current or await self.get_tokens(location_id)
        if not current:
            return None

        refresh_token = current.get("refresh_token")
        if not isinstance(refresh_token, str) or not refresh_token.strip():
            return None

        client_id = _oauth_setting("ghl_oauth_client_id", "GHL_OAUTH_CLIENT_ID")
        client_secret = _oauth_setting("ghl_oauth_client_secret", "GHL_OAUTH_CLIENT_SECRET")
        if not client_id or not client_secret:
            logger.warning("Cannot refresh GHL OAuth token: missing client credentials")
            return None

        payload = {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token.strip(),
            "user_type": _oauth_user_type(),
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    _TOKEN_URL,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    data=payload,
                )
                response.raise_for_status()
                body = response.json()
        except Exception as exc:
            logger.warning(f"Failed to refresh GHL OAuth token for location {location_id}: {exc}")
            return None

        new_access_token = body.get("access_token")
        if not isinstance(new_access_token, str) or not new_access_token.strip():
            return None

        await self.store_tokens(
            location_id=location_id,
            access_token=new_access_token,
            refresh_token=body.get("refresh_token") or refresh_token,
            expires_in=body.get("expires_in"),
            token_payload=body,
        )
        return await self.get_tokens(location_id)


_store_singleton: Optional[GHLOAuthTokenStore] = None


def get_ghl_oauth_token_store() -> GHLOAuthTokenStore:
    """Return process singleton token store."""
    global _store_singleton
    if _store_singleton is None:
        _store_singleton = GHLOAuthTokenStore()
    return _store_singleton
