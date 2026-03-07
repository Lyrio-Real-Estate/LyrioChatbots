"""
Authentication component for Streamlit dashboard.

Provides login/logout functionality and session management.
"""
import base64
import html
import json
import os
import re
import secrets
from typing import Any, Dict, Optional
from urllib.parse import urlparse
from urllib.parse import urlencode

import httpx
import streamlit as st

from bots.shared.auth_service import User, UserRole, get_auth_service
from bots.shared.config import settings
from bots.shared.ghl_oauth_token_store import get_ghl_oauth_token_store
from bots.shared.logger import get_logger
from command_center.async_runtime import run_async

logger = get_logger(__name__)

_AUTH_QUERY_PARAM = "sid"
_AUTH_SESSION_ID_KEY = "auth_session_id"
_AUTH_SESSION_CACHE_PREFIX = "auth:streamlit:session"
_AUTH_SESSION_TTL_SECONDS = 7 * 24 * 60 * 60

_GHL_OAUTH_STATE_KEY = "ghl_oauth_state"
_GHL_OAUTH_AUTHORIZE_URL = os.getenv("GHL_OAUTH_AUTHORIZE_URL", "https://marketplace.gohighlevel.com/oauth/chooselocation")
_GHL_OAUTH_TOKEN_URL = os.getenv("GHL_OAUTH_TOKEN_URL", "https://services.leadconnectorhq.com/oauth/token")
_GHL_API_BASE_URL = os.getenv("GHL_API_BASE_URL", "https://services.leadconnectorhq.com").rstrip("/")
_GHL_OAUTH_USERINFO_URLS = [
    os.getenv("GHL_OAUTH_USERINFO_URL", "https://services.leadconnectorhq.com/oauth/userinfo"),
    "https://services.leadconnectorhq.com/users/me",
]
_GHL_NGROK_TUNNELS_API = os.getenv("GHL_OAUTH_NGROK_API_URL", "http://127.0.0.1:4040/api/tunnels")
_EMAIL_PATTERN = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)


def _oauth_setting(name: str, env_var: str, default: Optional[str] = None) -> Optional[str]:
    """
    Read OAuth config from Settings with env var fallback.

    This avoids hard failures when optional settings fields are missing on older
    Settings objects.
    """
    value = getattr(settings, name, None)
    if value in (None, ""):
        value = os.getenv(env_var, default)
    if isinstance(value, str):
        value = value.strip()
        if not value:
            return default
    return value


def _oauth_bool_setting(name: str, env_var: str, default: bool = False) -> bool:
    """Read a boolean OAuth setting with tolerant parsing."""
    value = _oauth_setting(name, env_var, str(default).lower())
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _ghl_oauth_auto_create_enabled() -> bool:
    # Enabled by default so first-time GHL users can self-provision.
    return _oauth_bool_setting("ghl_oauth_auto_create_users", "GHL_OAUTH_AUTO_CREATE_USERS", default=True)


def _ghl_oauth_allow_surrogate_email() -> bool:
    # Some GHL OAuth install contexts don't expose installer email reliably.
    return _oauth_bool_setting("ghl_oauth_allow_surrogate_email", "GHL_OAUTH_ALLOW_SURROGATE_EMAIL", default=True)


def _ghl_oauth_default_role() -> UserRole:
    raw_role = (_oauth_setting("ghl_oauth_default_role", "GHL_OAUTH_DEFAULT_ROLE", "viewer") or "viewer").strip().lower()
    role_map = {
        "viewer": UserRole.VIEWER,
        "agent": UserRole.AGENT,
        "admin": UserRole.ADMIN,
    }
    role = role_map.get(raw_role)
    if role is None:
        logger.warning(f"Invalid GHL_OAUTH_DEFAULT_ROLE '{raw_role}', defaulting to viewer")
        return UserRole.VIEWER
    return role


def _ghl_oauth_user_type() -> str:
    """OAuth v2 requires user_type in token exchange payloads."""
    raw_type = (_oauth_setting("ghl_oauth_user_type", "GHL_OAUTH_USER_TYPE", "Company") or "Company").strip().lower()
    if raw_type == "company":
        return "Company"
    if raw_type == "location":
        return "Location"
    logger.warning(f"Invalid GHL_OAUTH_USER_TYPE '{raw_type}', defaulting to Company")
    return "Company"


def _display_name_from_email(email: str) -> str:
    local = (email.split("@", 1)[0] if "@" in email else email).strip()
    if not local:
        return "GHL User"
    parts = [part for part in local.replace("_", " ").replace("-", " ").replace(".", " ").split(" ") if part]
    if not parts:
        return "GHL User"
    return " ".join(part.capitalize() for part in parts[:4])


def _extract_display_name(payload: Any) -> Optional[str]:
    """Best-effort display-name extraction from nested OAuth user payload."""
    if isinstance(payload, dict):
        first_name = payload.get("firstName") or payload.get("first_name")
        last_name = payload.get("lastName") or payload.get("last_name")
        if isinstance(first_name, str) and first_name.strip():
            joined = first_name.strip()
            if isinstance(last_name, str) and last_name.strip():
                joined = f"{joined} {last_name.strip()}"
            return joined[:255]

        for key in ("name", "fullName", "full_name", "userName", "displayName"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:255]

        for value in payload.values():
            found = _extract_display_name(value)
            if found:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = _extract_display_name(item)
            if found:
                return found
    return None


def _ghl_oauth_enabled() -> bool:
    return bool(
        _oauth_setting("ghl_oauth_client_id", "GHL_OAUTH_CLIENT_ID")
        and _oauth_setting("ghl_oauth_client_secret", "GHL_OAUTH_CLIENT_SECRET")
        and _resolve_ghl_oauth_redirect_uri()
    )


def _build_ghl_oauth_authorize_url() -> str:
    client_id = _oauth_setting("ghl_oauth_client_id", "GHL_OAUTH_CLIENT_ID")
    redirect_uri = _resolve_ghl_oauth_redirect_uri()
    scopes = _oauth_setting(
        "ghl_oauth_scopes",
        "GHL_OAUTH_SCOPES",
        "contacts.readonly contacts.write conversations.readonly conversations.write",
    )
    if not client_id or not redirect_uri:
        raise ValueError("GoHighLevel OAuth is not configured.")

    state = secrets.token_urlsafe(24)
    st.session_state[_GHL_OAUTH_STATE_KEY] = state
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": scopes or "",
        "state": state,
    }
    return f"{_GHL_OAUTH_AUTHORIZE_URL}?{urlencode(params)}"


async def _exchange_ghl_oauth_code(code: str) -> Optional[Dict[str, Any]]:
    client_id = _oauth_setting("ghl_oauth_client_id", "GHL_OAUTH_CLIENT_ID")
    client_secret = _oauth_setting("ghl_oauth_client_secret", "GHL_OAUTH_CLIENT_SECRET")
    redirect_uri = _resolve_ghl_oauth_redirect_uri()
    if not client_id or not client_secret or not redirect_uri:
        raise ValueError("GoHighLevel OAuth is not configured.")

    def _extract_error_message(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except Exception:
            payload = None

        candidates: list[str] = []
        if isinstance(payload, dict):
            for key in ("error_description", "error", "message", "msg", "detail"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    candidates.append(value.strip())
            if not candidates:
                candidates.append(json.dumps(payload)[:300])
        else:
            raw_text = (response.text or "").strip()
            if raw_text:
                candidates.append(raw_text[:300])

        return candidates[0] if candidates else "Unknown error"

    preferred_user_type = _ghl_oauth_user_type()
    alternate_user_type = "Location" if preferred_user_type == "Company" else "Company"
    user_type_candidates = [preferred_user_type, alternate_user_type]

    async with httpx.AsyncClient(timeout=20.0) as client:
        last_error: Optional[Exception] = None
        for attempt_idx, user_type in enumerate(user_type_candidates):
            data = {
                "grant_type": "authorization_code",
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "code": code,
                "user_type": user_type,
            }

            response = await client.post(
                _GHL_OAUTH_TOKEN_URL,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                data=data,
            )

            try:
                response.raise_for_status()
                if attempt_idx > 0:
                    logger.warning(
                        f"GHL OAuth token exchange succeeded after retry with user_type={user_type} "
                        f"(configured={preferred_user_type})"
                    )
                return response.json()
            except httpx.HTTPStatusError as err:
                last_error = err
                status = err.response.status_code if err.response else response.status_code
                message = _extract_error_message(err.response or response)
                message_lower = message.lower()

                user_type_rejected = "user_type" in message_lower and "invalid" in message_lower
                can_retry_user_type = attempt_idx == 0 and status == 400 and user_type_rejected
                if can_retry_user_type:
                    logger.warning(
                        f"GHL OAuth token exchange rejected user_type={user_type}; "
                        f"retrying with user_type={alternate_user_type}. message={message}"
                    )
                    continue

                raise RuntimeError(
                    f"GHL OAuth token exchange failed ({status}). {message}"
                ) from err

        if isinstance(last_error, Exception):
            raise last_error
        raise RuntimeError("GHL OAuth token exchange failed with unknown error.")


def _should_use_ngrok_redirect(configured_redirect_uri: Optional[str]) -> bool:
    if not configured_redirect_uri:
        return True
    parsed = urlparse(configured_redirect_uri)
    host = (parsed.hostname or "").lower()
    if host in {"localhost", "127.0.0.1", "0.0.0.0"}:
        return _oauth_bool_setting("ghl_oauth_use_ngrok", "GHL_OAUTH_USE_NGROK", default=True)
    return False


def _ngrok_tunnels_api_url() -> str:
    return _oauth_setting("ghl_oauth_ngrok_api_url", "GHL_OAUTH_NGROK_API_URL", _GHL_NGROK_TUNNELS_API) or _GHL_NGROK_TUNNELS_API


def _redirect_port(redirect_uri: Optional[str]) -> int:
    if not redirect_uri:
        return 8501
    try:
        parsed = urlparse(redirect_uri)
        if parsed.port:
            return int(parsed.port)
    except Exception:
        pass
    return 8501


def _fetch_ngrok_redirect_uri(expected_port: int) -> Optional[str]:
    try:
        response = httpx.get(_ngrok_tunnels_api_url(), timeout=2.0)
        response.raise_for_status()
        payload = response.json()
        tunnels = payload.get("tunnels", []) if isinstance(payload, dict) else []

        def _is_expected_port(public_url: str, config_addr: Any) -> bool:
            addr = str(config_addr or "")
            if f":{expected_port}" in addr:
                return True
            if public_url:
                return expected_port == 8501
            return False

        for tunnel in tunnels:
            if not isinstance(tunnel, dict):
                continue
            public_url = str(tunnel.get("public_url") or "").strip()
            if not public_url.startswith("https://"):
                continue
            config = tunnel.get("config", {}) if isinstance(tunnel.get("config"), dict) else {}
            if _is_expected_port(public_url, config.get("addr")):
                return public_url.rstrip("/")
    except Exception:
        return None
    return None


def _resolve_ghl_oauth_redirect_uri() -> Optional[str]:
    configured = _oauth_setting("ghl_oauth_redirect_uri", "GHL_OAUTH_REDIRECT_URI")
    if not _should_use_ngrok_redirect(configured):
        return configured

    ngrok_redirect = _fetch_ngrok_redirect_uri(_redirect_port(configured))
    if ngrok_redirect:
        return ngrok_redirect
    return configured


async def _fetch_ghl_user_identity(access_token: str) -> Optional[Dict[str, Any]]:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Version": "2021-07-28",
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        for endpoint in _GHL_OAUTH_USERINFO_URLS:
            try:
                response = await client.get(endpoint, headers=headers)
                if response.status_code >= 400:
                    continue
                payload = response.json()
                if isinstance(payload, dict):
                    return payload
            except Exception:
                continue
    return None


async def _fetch_ghl_user_by_id(access_token: str, user_id: str) -> Optional[Dict[str, Any]]:
    """Fallback identity lookup using official users endpoint."""
    if not user_id:
        return None

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Version": "2021-07-28",
        "Accept": "application/json",
    }
    endpoint = f"{_GHL_API_BASE_URL}/users/{user_id}"
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.get(endpoint, headers=headers)
        if response.status_code >= 400:
            return None
        payload = response.json()
        return payload if isinstance(payload, dict) else None


def _extract_email(payload: Any) -> Optional[str]:
    if isinstance(payload, dict):
        for key in ("email", "userEmail", "primaryEmail", "emailAddress", "email_address"):
            value = payload.get(key)
            normalized = _normalize_email(value)
            if normalized:
                return normalized
        for key, value in payload.items():
            if "email" in str(key).lower():
                normalized = _normalize_email(value)
                if normalized:
                    return normalized
        for value in payload.values():
            found = _extract_email(value)
            if found:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = _extract_email(item)
            if found:
                return found
    elif isinstance(payload, str):
        return _normalize_email(payload)
    return None


def _normalize_email(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate:
        return None
    if _EMAIL_PATTERN.fullmatch(candidate):
        return candidate.lower()

    match = _EMAIL_PATTERN.search(candidate)
    if match:
        return match.group(0).lower()
    return None


def _decode_unverified_jwt_claims(token: Any) -> Optional[Dict[str, Any]]:
    """Decode JWT claims without signature verification for identity fallback only."""
    if not isinstance(token, str) or "." not in token:
        return None
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return None
        payload_b64 = parts[1]
        padding = "=" * (-len(payload_b64) % 4)
        decoded = base64.urlsafe_b64decode(payload_b64 + padding)
        claims = json.loads(decoded.decode("utf-8"))
        return claims if isinstance(claims, dict) else None
    except Exception:
        return None


def _normalize_identity_value(value: Any) -> Optional[str]:
    if isinstance(value, (str, int)):
        text = str(value).strip()
        if text and text.lower() not in {"null", "none"}:
            return text
    return None


def _extract_surrogate_principal(payload: Any) -> Optional[str]:
    candidates = []

    def _walk(node: Any, parent_key: str = "") -> None:
        if isinstance(node, dict):
            for raw_key, raw_value in node.items():
                key = str(raw_key).strip().lower()
                value = _normalize_identity_value(raw_value)
                if value:
                    if key in {"userid", "user_id"}:
                        candidates.append((100, f"user-{value}"))
                    elif key in {"locationid", "location_id"}:
                        candidates.append((95, f"location-{value}"))
                    elif key in {"companyid", "company_id"}:
                        candidates.append((90, f"company-{value}"))
                    elif key in {"sub", "subject"}:
                        candidates.append((85, f"sub-{value}"))
                    elif key == "id":
                        if "user" in parent_key:
                            candidates.append((80, f"user-{value}"))
                        elif "location" in parent_key:
                            candidates.append((75, f"location-{value}"))
                        elif "company" in parent_key:
                            candidates.append((70, f"company-{value}"))
                        else:
                            candidates.append((20, f"id-{value}"))
                    elif key.endswith("id"):
                        if "user" in key:
                            candidates.append((65, f"user-{value}"))
                        elif "location" in key:
                            candidates.append((60, f"location-{value}"))
                        elif "company" in key:
                            candidates.append((55, f"company-{value}"))
                        else:
                            candidates.append((10, f"id-{value}"))
                _walk(raw_value, parent_key=key)
        elif isinstance(node, list):
            for item in node:
                _walk(item, parent_key=parent_key)

    _walk(payload)
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _surrogate_email_from_payloads(*payloads: Any) -> Optional[str]:
    for payload in payloads:
        principal = _extract_surrogate_principal(payload)
        if principal:
            safe_principal = re.sub(r"[^a-zA-Z0-9-]", "-", principal).strip("-").lower()
            if safe_principal:
                return f"ghl-{safe_principal[:180]}@oauth.highlevel.local"
    return None


def _extract_location_id_from_payload(payload: Any) -> Optional[str]:
    candidates = []

    def _walk(node: Any, parent_key: str = "") -> None:
        if isinstance(node, dict):
            for raw_key, raw_value in node.items():
                key = str(raw_key).strip().lower()
                value = _normalize_identity_value(raw_value)
                if value:
                    if key in {"locationid", "location_id"}:
                        candidates.append((100, value))
                    elif key == "id" and "location" in parent_key:
                        candidates.append((80, value))
                    elif key.endswith("id") and "location" in key:
                        candidates.append((70, value))
                _walk(raw_value, parent_key=key)
        elif isinstance(node, list):
            for item in node:
                _walk(item, parent_key=parent_key)

    _walk(payload)
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _resolve_oauth_location_id(*payloads: Any) -> Optional[str]:
    for payload in payloads:
        found = _extract_location_id_from_payload(payload)
        if found:
            return found
    return None


def _debug_payload_keys(payload: Any) -> str:
    if isinstance(payload, dict):
        keys = [str(key) for key in payload.keys()]
        return ", ".join(sorted(keys)[:20])
    return type(payload).__name__


def _try_recover_existing_authenticated_user() -> Optional[User]:
    """
    Best-effort recovery of an already-authenticated dashboard user.

    Used when an OAuth callback code is stale/invalid but the user already has
    a valid local dashboard session.
    """
    try:
        _restore_auth_session()
    except Exception as restore_error:
        logger.warning(f"Failed to restore auth session during OAuth recovery: {restore_error}")

    auth_token = st.session_state.get("auth_token")
    if not auth_token:
        return None

    try:
        auth_service = get_auth_service()
        user = run_async(auth_service.validate_token(auth_token))
        if not user or not user.is_active:
            return None
        st.session_state.user = {
            "user_id": user.user_id,
            "email": user.email,
            "name": user.name,
            "role": user.role.value,
            "location_id": st.session_state.get("oauth_location_id"),
        }
        st.session_state.must_change_password = user.must_change_password
        return user
    except Exception as validate_error:
        logger.warning(f"Failed validating existing session during OAuth recovery: {validate_error}")
        return None


def _consume_ghl_oauth_callback() -> Optional[User]:
    code = _read_query_param("code")
    if not code:
        return None

    if not _ghl_oauth_enabled():
        st.error("GoHighLevel OAuth is not configured for this dashboard.")
        _write_query_param("code", None)
        _write_query_param("state", None)
        _write_query_param("error", None)
        return None

    error = _read_query_param("error")
    if error:
        st.error(f"GoHighLevel OAuth error: {error}")
        _write_query_param("code", None)
        _write_query_param("error", None)
        _write_query_param("state", None)
        return None

    expected_state = st.session_state.get(_GHL_OAUTH_STATE_KEY)
    callback_state = _read_query_param("state")
    if expected_state and callback_state != expected_state:
        st.error("Invalid OAuth state. Please try GoHighLevel login again.")
        _write_query_param("code", None)
        _write_query_param("state", None)
        return None

    try:
        auth_service = get_auth_service()
        token_payload = run_async(_exchange_ghl_oauth_code(code))
        if not token_payload:
            st.error("Unable to complete GoHighLevel OAuth token exchange.")
            return None

        ghl_access_token = token_payload.get("access_token")
        if not ghl_access_token:
            st.error("OAuth completed but access token was missing from GoHighLevel response.")
            return None

        identity = run_async(_fetch_ghl_user_identity(ghl_access_token))
        email = _extract_email(identity)
        if not email:
            user_id = token_payload.get("userId") or token_payload.get("user_id")
            if user_id:
                identity_by_id = run_async(_fetch_ghl_user_by_id(ghl_access_token, str(user_id)))
                if identity_by_id:
                    identity = identity_by_id
                    email = _extract_email(identity_by_id)

        id_token_claims = _decode_unverified_jwt_claims(token_payload.get("id_token"))
        access_token_claims = _decode_unverified_jwt_claims(token_payload.get("access_token"))
        if not email:
            email = _extract_email(id_token_claims) or _extract_email(access_token_claims)

        if not email:
            email = _extract_email(token_payload)

        if not email and _ghl_oauth_allow_surrogate_email():
            email = _surrogate_email_from_payloads(
                identity,
                id_token_claims,
                access_token_claims,
                token_payload,
            )
            if email:
                logger.warning(f"GHL OAuth email missing; using surrogate identity email: {email}")

        if not email:
            logger.warning(
                "GHL OAuth email missing after fallback attempts. "
                f"identity_keys=[{_debug_payload_keys(identity)}] "
                f"token_keys=[{_debug_payload_keys(token_payload)}] "
                f"id_token_claim_keys=[{_debug_payload_keys(id_token_claims)}] "
                f"access_token_claim_keys=[{_debug_payload_keys(access_token_claims)}]"
            )
            st.error("Unable to determine your email from GoHighLevel OAuth profile.")
            return None

        user = run_async(auth_service.get_user_by_email(email))
        if not user:
            if not _ghl_oauth_auto_create_enabled():
                st.error("No active dashboard account found for this GoHighLevel user.")
                return None

            display_name = _extract_display_name(identity) or _display_name_from_email(email)
            user_role = _ghl_oauth_default_role()
            temp_password = secrets.token_urlsafe(24)

            try:
                user = run_async(
                    auth_service.create_user(
                        email=email,
                        password=temp_password,
                        name=display_name,
                        role=user_role,
                        must_change_password=False,
                    )
                )
                logger.info(f"Auto-provisioned dashboard user from GHL OAuth: {email} ({user_role.value})")
            except ValueError:
                # Handle race where another request created the user concurrently.
                user = run_async(auth_service.get_user_by_email(email))
            except Exception:
                logger.exception(f"Failed auto-provisioning dashboard user for GHL OAuth email: {email}")
                st.error("Unable to create a dashboard account from your GoHighLevel profile.")
                return None

        if not user or not user.is_active:
            st.error("Your dashboard account is inactive. Contact your administrator.")
            return None

        tokens = run_async(auth_service.create_tokens_for_user(user))
        if not tokens:
            st.error("Failed to create dashboard session after OAuth login.")
            return None

        oauth_location_id = _resolve_oauth_location_id(
            identity,
            id_token_claims,
            access_token_claims,
            token_payload,
        )
        if oauth_location_id:
            try:
                token_store = get_ghl_oauth_token_store()
                run_async(
                    token_store.store_tokens(
                        location_id=oauth_location_id,
                        access_token=ghl_access_token,
                        refresh_token=token_payload.get("refresh_token"),
                        expires_in=token_payload.get("expires_in"),
                        token_payload=token_payload,
                    )
                )
            except Exception as store_error:
                logger.warning(f"Failed to persist GHL OAuth tokens for {oauth_location_id}: {store_error}")
        _set_authenticated_state(
            user,
            tokens.access_token,
            tokens.refresh_token,
            oauth_location_id=oauth_location_id,
        )
        st.success(f"Welcome, {user.name}!")
        _write_query_param("code", None)
        _write_query_param("state", None)
        _write_query_param("error", None)
        st.rerun()
        return user
    except Exception as e:
        logger.exception(f"GHL OAuth callback error: {e}")
        error_text = str(e).lower()
        invalid_grant = (
            "invalid grant" in error_text
            or "authorization code is invalid" in error_text
            or "invalid_grant" in error_text
        )
        if invalid_grant:
            recovered_user = _try_recover_existing_authenticated_user()
            if recovered_user:
                logger.info("Ignored stale OAuth callback code because a valid dashboard session already exists.")
                _write_query_param("code", None)
                _write_query_param("state", None)
                _write_query_param("error", None)
                st.rerun()
                return recovered_user
        st.error(f"GoHighLevel OAuth login failed. {e}")
        _write_query_param("code", None)
        _write_query_param("state", None)
        _write_query_param("error", None)
        return None


def _auth_session_cache_key(session_id: str) -> str:
    return f"{_AUTH_SESSION_CACHE_PREFIX}:{session_id}"


def _read_query_param(name: str) -> Optional[str]:
    """Read one query param value across Streamlit versions."""
    try:
        query_params = getattr(st, "query_params", None)
        if query_params is not None:
            value = query_params.get(name)
            if isinstance(value, list):
                return str(value[0]) if value else None
            return str(value) if value is not None else None
    except Exception:
        pass

    try:
        params = st.experimental_get_query_params()
        value = params.get(name)
        if isinstance(value, list):
            return str(value[0]) if value else None
        return str(value) if value is not None else None
    except Exception:
        return None


def _write_query_param(name: str, value: Optional[str]) -> None:
    """Write/remove one query param value across Streamlit versions."""
    try:
        query_params = getattr(st, "query_params", None)
        if query_params is not None:
            if value:
                query_params[name] = value
            elif name in query_params:
                del query_params[name]
            return
    except Exception:
        pass

    try:
        params = st.experimental_get_query_params()
        if value:
            params[name] = value
        else:
            params.pop(name, None)
        st.experimental_set_query_params(**params)
    except Exception:
        return


def _persist_auth_session(auth_token: str, refresh_token: str, oauth_location_id: Optional[str] = None) -> None:
    """Persist auth tokens server-side and keep only opaque session id in URL."""
    try:
        auth_service = get_auth_service()
        session_id = st.session_state.get(_AUTH_SESSION_ID_KEY)
        if not session_id:
            session_id = secrets.token_urlsafe(24)
            st.session_state[_AUTH_SESSION_ID_KEY] = session_id

        location_id = oauth_location_id or st.session_state.get("oauth_location_id")
        payload = {
            "auth_token": auth_token,
            "refresh_token": refresh_token,
            "oauth_location_id": location_id,
        }
        run_async(
            auth_service.cache_service.set(
                _auth_session_cache_key(session_id),
                payload,
                ttl=_AUTH_SESSION_TTL_SECONDS,
            )
        )
        _write_query_param(_AUTH_QUERY_PARAM, session_id)
    except Exception as exc:
        logger.warning(f"Failed to persist Streamlit auth session: {exc}")


def _restore_auth_session() -> bool:
    """Restore auth tokens from persisted Streamlit session when available."""
    if "auth_token" in st.session_state and "refresh_token" in st.session_state:
        return True

    session_id = st.session_state.get(_AUTH_SESSION_ID_KEY) or _read_query_param(_AUTH_QUERY_PARAM)
    if not session_id:
        return False

    try:
        auth_service = get_auth_service()
        payload = run_async(auth_service.cache_service.get(_auth_session_cache_key(session_id)))
        if not isinstance(payload, dict):
            st.session_state.pop(_AUTH_SESSION_ID_KEY, None)
            _write_query_param(_AUTH_QUERY_PARAM, None)
            return False

        auth_token = payload.get("auth_token")
        refresh_token = payload.get("refresh_token")
        if not auth_token or not refresh_token:
            st.session_state.pop(_AUTH_SESSION_ID_KEY, None)
            _write_query_param(_AUTH_QUERY_PARAM, None)
            return False

        st.session_state[_AUTH_SESSION_ID_KEY] = session_id
        st.session_state.auth_token = auth_token
        st.session_state.refresh_token = refresh_token
        restored_location_id = payload.get("oauth_location_id")
        if isinstance(restored_location_id, str) and restored_location_id.strip():
            st.session_state.oauth_location_id = restored_location_id.strip()
            st.session_state.location_id = restored_location_id.strip()
        _write_query_param(_AUTH_QUERY_PARAM, session_id)
        # Sliding TTL so active sessions persist while in use.
        _persist_auth_session(auth_token, refresh_token, oauth_location_id=st.session_state.get("oauth_location_id"))
        return True
    except Exception as exc:
        logger.warning(f"Failed to restore Streamlit auth session: {exc}")
        return False


def _set_authenticated_state(
    user: User,
    auth_token: str,
    refresh_token: str,
    oauth_location_id: Optional[str] = None,
) -> None:
    location_id = (
        oauth_location_id.strip()
        if isinstance(oauth_location_id, str) and oauth_location_id.strip()
        else st.session_state.get("oauth_location_id")
    )
    if location_id:
        st.session_state.oauth_location_id = location_id
        st.session_state.location_id = location_id

    st.session_state.auth_token = auth_token
    st.session_state.refresh_token = refresh_token
    st.session_state.user = {
        'user_id': user.user_id,
        'email': user.email,
        'name': user.name,
        'role': user.role.value,
        'location_id': location_id,
    }
    st.session_state.must_change_password = user.must_change_password
    _persist_auth_session(auth_token, refresh_token, oauth_location_id=location_id)


def _clear_persisted_auth_session() -> None:
    session_id = st.session_state.get(_AUTH_SESSION_ID_KEY) or _read_query_param(_AUTH_QUERY_PARAM)
    try:
        if session_id:
            auth_service = get_auth_service()
            run_async(auth_service.cache_service.delete(_auth_session_cache_key(session_id)))
    except Exception as exc:
        logger.warning(f"Failed to clear persisted auth session: {exc}")
    _write_query_param(_AUTH_QUERY_PARAM, None)
    st.session_state.pop(_AUTH_SESSION_ID_KEY, None)
    st.session_state.pop("oauth_location_id", None)
    st.session_state.pop("location_id", None)


def _render_oauth_setup_screen(authorize_url: str) -> None:
    dashboard_title = (os.getenv("DASHBOARD_TITLE") or os.getenv("APP_NAME") or "Lyrio AI Dashboard").strip() or "Lyrio AI Dashboard"
    safe_title = html.escape(dashboard_title)
    safe_authorize_url = html.escape(authorize_url, quote=True)
    raw_theme = (
        st.session_state.get("ui_theme")
        or _read_query_param("theme")
        or os.getenv("DASHBOARD_THEME", "dark")
    )
    theme_mode = str(raw_theme or "").strip().lower()
    is_light = theme_mode == "light"

    if is_light:
        app_bg = "#f3f6fb"
        title_color = "#0f172a"
        subtitle_color = "#334155"
        list_color = "#1e293b"
        divider_color = "rgba(148, 163, 184, 0.45)"
        callout_border = "rgba(59, 130, 246, 0.35)"
        callout_bg = "rgba(59, 130, 246, 0.12)"
        callout_text = "#1e3a8a"
        link_text = "#0f172a"
        link_border = "rgba(148, 163, 184, 0.55)"
        link_bg = "rgba(255, 255, 255, 0.92)"
        link_hover_bg = "rgba(241, 245, 249, 0.98)"
        caption_color = "#475569"
    else:
        app_bg = "#030712"
        title_color = "#f8fafc"
        subtitle_color = "rgba(241, 245, 249, 0.88)"
        list_color = "rgba(241, 245, 249, 0.94)"
        divider_color = "rgba(148, 163, 184, 0.24)"
        callout_border = "rgba(59, 130, 246, 0.45)"
        callout_bg = "rgba(30, 58, 138, 0.35)"
        callout_text = "#dbeafe"
        link_text = "#e2e8f0"
        link_border = "rgba(148, 163, 184, 0.35)"
        link_bg = "rgba(15, 23, 42, 0.55)"
        link_hover_bg = "rgba(30, 41, 59, 0.9)"
        caption_color = "#94a3b8"

    auth_css = """
    <style>
    /* Hide Streamlit chrome on auth/setup screens. */
    header[data-testid="stHeader"] {
        display: none !important;
    }
    [data-testid="stToolbar"] {
        display: none !important;
    }
    [data-testid="stDecoration"] {
        display: none !important;
    }
    [data-testid="stAppViewContainer"] {
        margin-top: 0 !important;
        background: __APP_BG__ !important;
    }
    [data-testid="stMain"] {
        background: __APP_BG__ !important;
    }

    .oauth-setup-shell {
        max-width: 1200px;
        margin: 2.5rem auto 0 auto;
        padding: 0 1rem 1rem 1rem;
    }
    .oauth-setup-title {
        margin: 0;
        font-size: clamp(2rem, 4vw, 3.6rem);
        font-weight: 700;
        line-height: 1.15;
        letter-spacing: -0.02em;
        color: __TITLE_COLOR__;
    }
    .oauth-setup-subtitle {
        margin: 0.8rem 0 1.6rem 0;
        font-size: 1.25rem;
        color: __SUBTITLE_COLOR__;
    }
    .oauth-setup-list {
        margin: 0 0 2.1rem 0;
        padding-left: 1.4rem;
        color: __LIST_COLOR__;
        font-size: 1.18rem;
        line-height: 1.75;
    }
    .oauth-divider {
        border: 0;
        border-top: 1px solid __DIVIDER_COLOR__;
        margin: 2.2rem 0 1.8rem 0;
    }
    .oauth-callout {
        border: 1px solid __CALLOUT_BORDER__;
        background: __CALLOUT_BG__;
        border-radius: 0.7rem;
        color: __CALLOUT_TEXT__;
        padding: 0.95rem 1rem;
        margin-bottom: 1rem;
        font-size: 1.02rem;
        font-weight: 500;
    }
    .oauth-connect-link {
        appearance: none;
        -webkit-appearance: none;
        display: block;
        width: 100%;
        text-align: center;
        text-decoration: none;
        color: __LINK_TEXT__;
        border: 1px solid __LINK_BORDER__;
        border-radius: 0.65rem;
        padding: 0.78rem 1rem;
        font-size: 1.08rem;
        font-weight: 600;
        transition: border-color 0.2s ease, background 0.2s ease, transform 0.1s ease;
        background: __LINK_BG__;
        cursor: pointer;
    }
    .oauth-connect-form {
        margin: 0;
    }
    .oauth-connect-link:hover {
        border-color: rgba(96, 165, 250, 0.9);
        background: __LINK_HOVER_BG__;
        transform: translateY(-1px);
    }
    .oauth-connect-link:active {
        transform: translateY(0);
    }
    .stCaption {
        color: __CAPTION_COLOR__ !important;
    }
    @media (max-width: 768px) {
        .oauth-setup-shell {
            margin-top: 1.5rem;
            padding: 0 0.3rem;
        }
        .oauth-setup-subtitle {
            font-size: 1.02rem;
        }
        .oauth-setup-list {
            font-size: 1rem;
            line-height: 1.6;
        }
    }
    </style>
    """
    auth_css = (
        auth_css
        .replace("__APP_BG__", app_bg)
        .replace("__TITLE_COLOR__", title_color)
        .replace("__SUBTITLE_COLOR__", subtitle_color)
        .replace("__LIST_COLOR__", list_color)
        .replace("__DIVIDER_COLOR__", divider_color)
        .replace("__CALLOUT_BORDER__", callout_border)
        .replace("__CALLOUT_BG__", callout_bg)
        .replace("__CALLOUT_TEXT__", callout_text)
        .replace("__LINK_TEXT__", link_text)
        .replace("__LINK_BORDER__", link_border)
        .replace("__LINK_BG__", link_bg)
        .replace("__LINK_HOVER_BG__", link_hover_bg)
        .replace("__CAPTION_COLOR__", caption_color)
    )
    st.markdown(auth_css, unsafe_allow_html=True)

    st.markdown(
        f"""
        <section class="oauth-setup-shell">
            <h1 class="oauth-setup-title">Welcome to {safe_title}</h1>
            <p class="oauth-setup-subtitle">Complete setup to unlock your workspace.</p>
            <ol class="oauth-setup-list">
                <li>Connect GoHighLevel</li>
                <li>Save Profile Information</li>
            </ol>
            <hr class="oauth-divider" />
            <div class="oauth-callout">Connect your GoHighLevel account to continue.</div>
            <a class="oauth-connect-link" href="{safe_authorize_url}" target="_blank" rel="noopener noreferrer">Connect GoHighLevel</a>
        </section>
        """,
        unsafe_allow_html=True,
    )

    if _ghl_oauth_auto_create_enabled():
        st.caption("OAuth account creation is enabled. Your dashboard user is created automatically after successful GoHighLevel login.")
    else:
        st.caption("OAuth login requires a matching dashboard user email.")


def _render_oauth_only_configuration_hint() -> None:
    st.error("GoHighLevel OAuth login is required, but OAuth is not configured.")
    st.info(
        "Set `GHL_OAUTH_CLIENT_ID`, `GHL_OAUTH_CLIENT_SECRET`, and `GHL_OAUTH_REDIRECT_URI`, then restart the dashboard."
    )


def render_login_form() -> Optional[User]:
    """
    Render login form and handle authentication.

    Returns:
        Authenticated user if login successful, None otherwise
    """
    oauth_user = _consume_ghl_oauth_callback()
    if oauth_user:
        return oauth_user

    if not _ghl_oauth_enabled():
        _render_oauth_only_configuration_hint()
        return None

    authorize_url = _build_ghl_oauth_authorize_url()
    _render_oauth_setup_screen(authorize_url)
    return None


def check_authentication() -> Optional[User]:
    """
    Check if user is authenticated via session.
    
    Returns:
        Authenticated user if session is valid, None otherwise
    """
    if 'auth_token' not in st.session_state:
        _restore_auth_session()

    if 'auth_token' not in st.session_state:
        return None
    
    try:
        auth_service = get_auth_service()
        user = run_async(auth_service.validate_token(st.session_state.auth_token))
        
        if user:
            # Update session user info
            st.session_state.user = {
                'user_id': user.user_id,
                'email': user.email,
                'name': user.name,
                'role': user.role.value,
                'location_id': st.session_state.get("oauth_location_id"),
            }
            st.session_state.must_change_password = user.must_change_password
            if 'refresh_token' in st.session_state:
                _persist_auth_session(
                    st.session_state.auth_token,
                    st.session_state.refresh_token,
                    oauth_location_id=st.session_state.get("oauth_location_id"),
                )
            return user
        else:
            # Token expired or invalid, try refresh
            if 'refresh_token' in st.session_state:
                tokens = run_async(auth_service.refresh_token(st.session_state.refresh_token))
                if tokens:
                    user = run_async(auth_service.validate_token(tokens.access_token))
                    if user:
                        # Update session with new tokens and persistence
                        _set_authenticated_state(user, tokens.access_token, tokens.refresh_token)
                        return user
            
            # Clear invalid session
            clear_session()
            return None
            
    except Exception as e:
        logger.exception(f"Authentication check error: {e}")
        clear_session()
        return None


def clear_session() -> None:
    """Clear authentication session."""
    _clear_persisted_auth_session()
    keys_to_remove = ['auth_token', 'refresh_token', 'user', 'must_change_password', _AUTH_SESSION_ID_KEY]
    for key in keys_to_remove:
        if key in st.session_state:
            del st.session_state[key]


def render_password_change_form(user: User) -> bool:
    """Render password change form for first-login enforcement."""
    st.warning("Password change required before continuing.")
    with st.form("change_password_form"):
        new_password = st.text_input("New Password", type="password")
        confirm_password = st.text_input("Confirm Password", type="password")
        submit = st.form_submit_button("Change Password", use_container_width=True)

        if submit:
            if not new_password or len(new_password) < 8:
                st.error("Password must be at least 8 characters.")
                return False
            if new_password != confirm_password:
                st.error("Passwords do not match.")
                return False
            auth_service = get_auth_service()
            success = run_async(auth_service.change_password(user.user_id, new_password))
            if success:
                st.session_state.must_change_password = False
                st.success("Password updated. Please continue.")
                st.rerun()
                return True
            st.error("Failed to update password.")
            return False
    return False


def render_user_menu(user: User) -> None:
    """
    Render user menu in sidebar.
    
    Args:
        user: Authenticated user
    """
    st.sidebar.markdown("---")
    if st.sidebar.button("Logout", use_container_width=True):
        clear_session()
        st.rerun()


def check_permission(user: User, resource: str, action: str) -> bool:
    """
    Check if user has permission for resource/action.
    
    Args:
        user: User to check
        resource: Resource name
        action: Action name
        
    Returns:
        True if user has permission, False otherwise
    """
    try:
        auth_service = get_auth_service()
        return run_async(auth_service.check_permission(user, resource, action))
    except Exception as e:
        logger.exception(f"Permission check error: {e}")
        return False


def require_permission(user: User, resource: str, action: str) -> bool:
    """
    Require permission and show error if not authorized.
    
    Args:
        user: User to check
        resource: Resource name
        action: Action name
        
    Returns:
        True if user has permission, False otherwise (also shows error)
    """
    has_permission = check_permission(user, resource, action)
    
    if not has_permission:
        st.error(f"Access denied: You need {action} permission for {resource}")
        st.info("Contact your administrator to request access.")
        return False
    
    return True


def render_role_badge(user: User) -> None:
    """Render role badge for user."""
    role_colors = {
        'admin': '#dc3545',    # Red
        'agent': '#28a745',    # Green
        'viewer': '#6c757d'    # Gray
    }
    
    role_labels = {
        'admin': 'Admin',
        'agent': 'Agent',
        'viewer': 'Viewer'
    }
    
    color = role_colors.get(user.role.value, '#6c757d')
    label = role_labels.get(user.role.value, user.role.value.title())
    
    st.markdown(f"""
    <span style="
        background-color: {color};
        color: white;
        padding: 0.25rem 0.5rem;
        border-radius: 0.25rem;
        font-size: 0.75rem;
        font-weight: bold;
    ">{label}</span>
    """, unsafe_allow_html=True)


def create_user_management_interface() -> None:
    """Create user management interface for admins."""
    st.markdown("### User Management")
    
    # List existing users
    try:
        auth_service = get_auth_service()
        users = run_async(auth_service.list_users())
        
        if users:
            st.markdown("#### Existing Users")
            for user in users:
                col1, col2, col3 = st.columns([3, 2, 2])
                with col1:
                    st.write(f"**{user.name}**")
                    st.write(user.email)
                with col2:
                    render_role_badge(user)
                with col3:
                    status = "Active" if user.is_active else "Inactive"
                    st.write(status)
                st.markdown("---")
        
        # Create new user form
        st.markdown("#### Add New User")
        with st.form("create_user_form"):
            col1, col2 = st.columns(2)
            with col1:
                new_email = st.text_input("Email")
                new_name = st.text_input("Name")
            with col2:
                new_role = st.selectbox(
                    "Role", 
                    options=['agent', 'viewer', 'admin'],
                    format_func=lambda x: {'agent': 'Agent', 'viewer': 'Viewer', 'admin': 'Admin'}[x]
                )
                new_password = st.text_input("Password", type="password")
            
            if st.form_submit_button("Create User"):
                if new_email and new_name and new_password:
                    try:
                        role = UserRole(new_role)
                        user = run_async(auth_service.create_user(
                            email=new_email,
                            password=new_password,
                            name=new_name,
                            role=role
                        ))
                        st.success(f"User {user.name} created successfully!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error creating user: {str(e)}")
                else:
                    st.error("Please fill in all fields")
    
    except Exception as e:
        st.error(f"Error loading user management: {str(e)}")
