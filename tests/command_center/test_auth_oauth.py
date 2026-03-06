import asyncio
import base64
import importlib
import json
import sys
from datetime import datetime

from bots.shared.auth_service import AuthToken, User, UserRole
from tests.command_center.streamlit_stub import install_streamlit_stub


def _import_auth_component(monkeypatch):
    st = install_streamlit_stub(monkeypatch)
    st.query_params = {}
    module_name = "command_center.components.auth_component"
    if module_name in sys.modules:
        del sys.modules[module_name]
    module = importlib.import_module(module_name)
    return module, st


def _sample_user(email: str = "agent@example.com"):
    return User(
        user_id="user_123",
        email=email,
        name="Agent Smith",
        role=UserRole.AGENT,
        created_at=datetime.now(),
    )


def _encode_jwt(payload: dict) -> str:
    header = {"alg": "none", "typ": "JWT"}

    def _b64(value: dict) -> str:
        raw = json.dumps(value, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")

    return f"{_b64(header)}.{_b64(payload)}."


def test_build_ghl_oauth_authorize_url_includes_required_params(monkeypatch):
    module, st = _import_auth_component(monkeypatch)
    monkeypatch.setattr(module.settings, "ghl_oauth_client_id", "client_123")
    monkeypatch.setattr(module.settings, "ghl_oauth_client_secret", "secret_123")
    monkeypatch.setattr(module.settings, "ghl_oauth_redirect_uri", "http://localhost:8501")
    monkeypatch.setattr(module.settings, "ghl_oauth_use_ngrok", False)
    monkeypatch.setattr(module.settings, "ghl_oauth_scopes", "contacts.readonly")

    url = module._build_ghl_oauth_authorize_url()

    assert "response_type=code" in url
    assert "client_id=client_123" in url
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A8501" in url
    assert "scope=contacts.readonly" in url
    assert st.session_state.get(module._GHL_OAUTH_STATE_KEY)


def test_exchange_ghl_oauth_code_uses_v2_payload(monkeypatch):
    module, _ = _import_auth_component(monkeypatch)
    monkeypatch.setattr(module.settings, "ghl_oauth_client_id", "client_123")
    monkeypatch.setattr(module.settings, "ghl_oauth_client_secret", "secret_123")
    monkeypatch.setattr(module.settings, "ghl_oauth_redirect_uri", "http://localhost:8501")
    monkeypatch.setattr(module.settings, "ghl_oauth_use_ngrok", False)
    monkeypatch.setattr(module.settings, "ghl_oauth_user_type", "Location")

    captured = {}

    class _FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"access_token": "ghl_token"}

    class _FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, url, headers=None, json=None, data=None):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            captured["data"] = data
            return _FakeResponse()

    monkeypatch.setattr(module.httpx, "AsyncClient", _FakeAsyncClient)

    payload = asyncio.run(module._exchange_ghl_oauth_code("code_abc"))

    assert payload["access_token"] == "ghl_token"
    assert captured["url"] == module._GHL_OAUTH_TOKEN_URL
    assert captured["headers"]["Content-Type"] == "application/x-www-form-urlencoded"
    assert captured["data"]["grant_type"] == "authorization_code"
    assert captured["data"]["code"] == "code_abc"
    assert captured["data"]["user_type"] == "Location"
    assert captured["json"] is None


def test_consume_ghl_oauth_callback_authenticates_existing_user(monkeypatch):
    module, st = _import_auth_component(monkeypatch)

    monkeypatch.setattr(module.settings, "ghl_oauth_client_id", "client_123")
    monkeypatch.setattr(module.settings, "ghl_oauth_client_secret", "secret_123")
    monkeypatch.setattr(module.settings, "ghl_oauth_redirect_uri", "http://localhost:8501")
    monkeypatch.setattr(module.settings, "ghl_oauth_use_ngrok", False)

    st.session_state[module._GHL_OAUTH_STATE_KEY] = "state_abc"
    st.query_params["code"] = "code_abc"
    st.query_params["state"] = "state_abc"

    async def _fake_exchange(code):
        assert code == "code_abc"
        return {"access_token": "ghl_token", "locationId": "loc_123"}

    async def _fake_userinfo(access_token):
        assert access_token == "ghl_token"
        return {"email": "agent@example.com"}

    user = _sample_user()

    class _FakeAuthService:
        async def get_user_by_email(self, email):
            return user if email == "agent@example.com" else None

        async def create_tokens_for_user(self, current_user):
            if current_user.email != user.email:
                return None
            return AuthToken(access_token="access_123", refresh_token="refresh_123", expires_in=1800)

    monkeypatch.setattr(module, "run_async", lambda coro: asyncio.run(coro))
    monkeypatch.setattr(module, "_exchange_ghl_oauth_code", _fake_exchange)
    monkeypatch.setattr(module, "_fetch_ghl_user_identity", _fake_userinfo)
    monkeypatch.setattr(module, "get_auth_service", lambda: _FakeAuthService())

    authenticated = module._consume_ghl_oauth_callback()

    assert authenticated is user
    assert st.session_state.auth_token == "access_123"
    assert st.session_state.refresh_token == "refresh_123"
    assert "code" not in st.query_params


def test_callback_falls_back_to_user_by_id_when_userinfo_missing_email(monkeypatch):
    module, st = _import_auth_component(monkeypatch)

    monkeypatch.setattr(module.settings, "ghl_oauth_client_id", "client_123")
    monkeypatch.setattr(module.settings, "ghl_oauth_client_secret", "secret_123")
    monkeypatch.setattr(module.settings, "ghl_oauth_redirect_uri", "http://localhost:8501")
    monkeypatch.setattr(module.settings, "ghl_oauth_use_ngrok", False)

    st.session_state[module._GHL_OAUTH_STATE_KEY] = "state_abc"
    st.query_params["code"] = "code_abc"
    st.query_params["state"] = "state_abc"

    async def _fake_exchange(code):
        assert code == "code_abc"
        return {"access_token": "ghl_token", "userId": "user_456"}

    async def _fake_userinfo(access_token):
        assert access_token == "ghl_token"
        return {"name": "No Email Returned"}

    async def _fake_user_by_id(access_token, user_id):
        assert access_token == "ghl_token"
        assert user_id == "user_456"
        return {"email": "agent@example.com"}

    user = _sample_user()

    class _FakeAuthService:
        async def get_user_by_email(self, email):
            return user if email == "agent@example.com" else None

        async def create_tokens_for_user(self, current_user):
            if current_user.email != user.email:
                return None
            return AuthToken(access_token="access_123", refresh_token="refresh_123", expires_in=1800)

    monkeypatch.setattr(module, "run_async", lambda coro: asyncio.run(coro))
    monkeypatch.setattr(module, "_exchange_ghl_oauth_code", _fake_exchange)
    monkeypatch.setattr(module, "_fetch_ghl_user_identity", _fake_userinfo)
    monkeypatch.setattr(module, "_fetch_ghl_user_by_id", _fake_user_by_id)
    monkeypatch.setattr(module, "get_auth_service", lambda: _FakeAuthService())

    authenticated = module._consume_ghl_oauth_callback()

    assert authenticated is user
    assert st.session_state.auth_token == "access_123"
    assert st.session_state.refresh_token == "refresh_123"
    assert "code" not in st.query_params


def test_callback_extracts_email_from_id_token_claims(monkeypatch):
    module, st = _import_auth_component(monkeypatch)

    monkeypatch.setattr(module.settings, "ghl_oauth_client_id", "client_123")
    monkeypatch.setattr(module.settings, "ghl_oauth_client_secret", "secret_123")
    monkeypatch.setattr(module.settings, "ghl_oauth_redirect_uri", "http://localhost:8501")
    monkeypatch.setattr(module.settings, "ghl_oauth_use_ngrok", False)

    st.session_state[module._GHL_OAUTH_STATE_KEY] = "state_abc"
    st.query_params["code"] = "code_abc"
    st.query_params["state"] = "state_abc"

    id_token = _encode_jwt({"email": "agent@example.com", "sub": "usr_999"})

    async def _fake_exchange(code):
        assert code == "code_abc"
        return {"access_token": "opaque_token", "id_token": id_token}

    async def _fake_userinfo(access_token):
        assert access_token == "opaque_token"
        return {"name": "No Email Returned"}

    user = _sample_user()

    class _FakeAuthService:
        async def get_user_by_email(self, email):
            return user if email == "agent@example.com" else None

        async def create_tokens_for_user(self, current_user):
            if current_user.email != user.email:
                return None
            return AuthToken(access_token="access_123", refresh_token="refresh_123", expires_in=1800)

    monkeypatch.setattr(module, "run_async", lambda coro: asyncio.run(coro))
    monkeypatch.setattr(module, "_exchange_ghl_oauth_code", _fake_exchange)
    monkeypatch.setattr(module, "_fetch_ghl_user_identity", _fake_userinfo)
    monkeypatch.setattr(module, "get_auth_service", lambda: _FakeAuthService())

    authenticated = module._consume_ghl_oauth_callback()

    assert authenticated is user
    assert st.session_state.auth_token == "access_123"
    assert st.session_state.refresh_token == "refresh_123"
    assert "code" not in st.query_params


def test_consume_ghl_oauth_callback_auto_creates_user_when_missing(monkeypatch):
    module, st = _import_auth_component(monkeypatch)

    monkeypatch.setattr(module.settings, "ghl_oauth_client_id", "client_123")
    monkeypatch.setattr(module.settings, "ghl_oauth_client_secret", "secret_123")
    monkeypatch.setattr(module.settings, "ghl_oauth_redirect_uri", "http://localhost:8501")
    monkeypatch.setattr(module.settings, "ghl_oauth_use_ngrok", False)
    monkeypatch.setattr(module.settings, "ghl_oauth_auto_create_users", True)
    monkeypatch.setattr(module.settings, "ghl_oauth_default_role", "viewer")

    st.session_state[module._GHL_OAUTH_STATE_KEY] = "state_abc"
    st.query_params["code"] = "code_abc"
    st.query_params["state"] = "state_abc"

    async def _fake_exchange(code):
        assert code == "code_abc"
        return {"access_token": "ghl_token", "locationId": "loc_123"}

    async def _fake_userinfo(access_token):
        assert access_token == "ghl_token"
        return {"email": "new.customer@example.com", "firstName": "New", "lastName": "Customer"}

    created = {"called": False}

    class _FakeAuthService:
        async def get_user_by_email(self, email):
            return None

        async def create_user(self, email, password, name, role, must_change_password=False):
            created["called"] = True
            assert email == "new.customer@example.com"
            assert name == "New Customer"
            assert role == UserRole.VIEWER
            assert must_change_password is False
            assert password
            return User(
                user_id="user_new",
                email=email,
                name=name,
                role=role,
                created_at=datetime.now(),
                is_active=True,
            )

        async def create_tokens_for_user(self, current_user):
            return AuthToken(access_token="access_new", refresh_token="refresh_new", expires_in=1800)

    monkeypatch.setattr(module, "run_async", lambda coro: asyncio.run(coro))
    monkeypatch.setattr(module, "_exchange_ghl_oauth_code", _fake_exchange)
    monkeypatch.setattr(module, "_fetch_ghl_user_identity", _fake_userinfo)
    monkeypatch.setattr(module, "get_auth_service", lambda: _FakeAuthService())

    authenticated = module._consume_ghl_oauth_callback()

    assert created["called"] is True
    assert authenticated is not None
    assert authenticated.email == "new.customer@example.com"
    assert st.session_state.auth_token == "access_new"
    assert st.session_state.refresh_token == "refresh_new"
    assert st.session_state.oauth_location_id == "loc_123"
    assert st.session_state.location_id == "loc_123"
    assert st.session_state.user["location_id"] == "loc_123"
    assert "code" not in st.query_params


def test_callback_uses_surrogate_email_from_claims_when_email_missing(monkeypatch):
    module, st = _import_auth_component(monkeypatch)

    monkeypatch.setattr(module.settings, "ghl_oauth_client_id", "client_123")
    monkeypatch.setattr(module.settings, "ghl_oauth_client_secret", "secret_123")
    monkeypatch.setattr(module.settings, "ghl_oauth_redirect_uri", "http://localhost:8501")
    monkeypatch.setattr(module.settings, "ghl_oauth_use_ngrok", False)
    monkeypatch.setattr(module.settings, "ghl_oauth_auto_create_users", True)
    monkeypatch.setattr(module.settings, "ghl_oauth_allow_surrogate_email", True)

    st.session_state[module._GHL_OAUTH_STATE_KEY] = "state_abc"
    st.query_params["code"] = "code_abc"
    st.query_params["state"] = "state_abc"

    access_token = _encode_jwt({"sub": "usr_789"})

    async def _fake_exchange(code):
        assert code == "code_abc"
        return {"access_token": access_token}

    async def _fake_userinfo(_access_token):
        return {"name": "No Email Returned"}

    created = {"email": None}

    class _FakeAuthService:
        async def get_user_by_email(self, _email):
            return None

        async def create_user(self, email, password, name, role, must_change_password=False):
            created["email"] = email
            assert email == "ghl-sub-usr-789@oauth.highlevel.local"
            assert password
            assert must_change_password is False
            return User(
                user_id="user_surrogate",
                email=email,
                name=name,
                role=role,
                created_at=datetime.now(),
                is_active=True,
            )

        async def create_tokens_for_user(self, current_user):
            return AuthToken(access_token="access_surrogate", refresh_token="refresh_surrogate", expires_in=1800)

    monkeypatch.setattr(module, "run_async", lambda coro: asyncio.run(coro))
    monkeypatch.setattr(module, "_exchange_ghl_oauth_code", _fake_exchange)
    monkeypatch.setattr(module, "_fetch_ghl_user_identity", _fake_userinfo)
    monkeypatch.setattr(module, "get_auth_service", lambda: _FakeAuthService())

    authenticated = module._consume_ghl_oauth_callback()

    assert authenticated is not None
    assert created["email"] == "ghl-sub-usr-789@oauth.highlevel.local"
    assert st.session_state.auth_token == "access_surrogate"
    assert st.session_state.refresh_token == "refresh_surrogate"
    assert "code" not in st.query_params


def test_resolve_redirect_uri_prefers_ngrok_for_localhost(monkeypatch):
    module, _ = _import_auth_component(monkeypatch)
    monkeypatch.setattr(module.settings, "ghl_oauth_redirect_uri", "http://localhost:8501")
    monkeypatch.setattr(module.settings, "ghl_oauth_use_ngrok", True)

    captured = {}

    def _fake_ngrok(port):
        captured["port"] = port
        return "https://abc123.ngrok-free.app"

    monkeypatch.setattr(module, "_fetch_ngrok_redirect_uri", _fake_ngrok)

    redirect_uri = module._resolve_ghl_oauth_redirect_uri()

    assert captured["port"] == 8501
    assert redirect_uri == "https://abc123.ngrok-free.app"
