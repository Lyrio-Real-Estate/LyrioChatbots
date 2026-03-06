import asyncio
import importlib
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


def test_build_ghl_oauth_authorize_url_includes_required_params(monkeypatch):
    module, st = _import_auth_component(monkeypatch)
    monkeypatch.setattr(module.settings, "ghl_oauth_client_id", "client_123")
    monkeypatch.setattr(module.settings, "ghl_oauth_client_secret", "secret_123")
    monkeypatch.setattr(module.settings, "ghl_oauth_redirect_uri", "http://localhost:8501")
    monkeypatch.setattr(module.settings, "ghl_oauth_scopes", "contacts.readonly")

    url = module._build_ghl_oauth_authorize_url()

    assert "response_type=code" in url
    assert "client_id=client_123" in url
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A8501" in url
    assert "scope=contacts.readonly" in url
    assert st.session_state.get(module._GHL_OAUTH_STATE_KEY)


def test_consume_ghl_oauth_callback_authenticates_existing_user(monkeypatch):
    module, st = _import_auth_component(monkeypatch)

    monkeypatch.setattr(module.settings, "ghl_oauth_client_id", "client_123")
    monkeypatch.setattr(module.settings, "ghl_oauth_client_secret", "secret_123")
    monkeypatch.setattr(module.settings, "ghl_oauth_redirect_uri", "http://localhost:8501")

    st.session_state[module._GHL_OAUTH_STATE_KEY] = "state_abc"
    st.query_params["code"] = "code_abc"
    st.query_params["state"] = "state_abc"

    async def _fake_exchange(code):
        assert code == "code_abc"
        return {"access_token": "ghl_token"}

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
