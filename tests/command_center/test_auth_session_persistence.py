import importlib
import sys
from datetime import datetime
from types import SimpleNamespace

from bots.shared.auth_service import User, UserRole
from tests.command_center.streamlit_stub import install_streamlit_stub


class _FakeCache:
    def __init__(self, initial=None):
        self.store = dict(initial or {})

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ttl=300):
        self.store[key] = value
        return True

    async def delete(self, key):
        self.store.pop(key, None)
        return True


def _import_auth_component(monkeypatch):
    st = install_streamlit_stub(monkeypatch)
    st.query_params = {}
    module_name = "command_center.components.auth_component"
    if module_name in sys.modules:
        del sys.modules[module_name]
    module = importlib.import_module(module_name)
    return module, st


def _sample_user():
    return User(
        user_id="user_123",
        email="agent@example.com",
        name="Agent Smith",
        role=UserRole.AGENT,
        created_at=datetime.now(),
    )


def test_restore_auth_session_from_query_sid(monkeypatch):
    module, st = _import_auth_component(monkeypatch)
    sid = "session_abc"
    cache = _FakeCache(
        {
            module._auth_session_cache_key(sid): {
                "auth_token": "access_1",
                "refresh_token": "refresh_1",
            }
        }
    )
    fake_auth_service = SimpleNamespace(cache_service=cache)
    monkeypatch.setattr(module, "get_auth_service", lambda: fake_auth_service)
    st.query_params[module._AUTH_QUERY_PARAM] = sid

    restored = module._restore_auth_session()

    assert restored is True
    assert st.session_state.auth_token == "access_1"
    assert st.session_state.refresh_token == "refresh_1"
    assert st.session_state[module._AUTH_SESSION_ID_KEY] == sid


def test_check_authentication_restores_from_persisted_session(monkeypatch):
    module, st = _import_auth_component(monkeypatch)
    sid = "session_xyz"
    user = _sample_user()
    cache = _FakeCache(
        {
            module._auth_session_cache_key(sid): {
                "auth_token": "access_2",
                "refresh_token": "refresh_2",
            }
        }
    )

    class _FakeAuthService:
        cache_service = cache

        async def validate_token(self, token):
            return user if token == "access_2" else None

        async def refresh_token(self, refresh_token):
            return None

    monkeypatch.setattr(module, "get_auth_service", lambda: _FakeAuthService())
    st.query_params[module._AUTH_QUERY_PARAM] = sid

    authenticated_user = module.check_authentication()

    assert authenticated_user is not None
    assert authenticated_user.email == user.email
    assert st.session_state.user["email"] == user.email
    assert st.session_state.auth_token == "access_2"
    assert st.session_state.refresh_token == "refresh_2"


def test_clear_session_clears_persisted_session_and_query_param(monkeypatch):
    module, st = _import_auth_component(monkeypatch)
    sid = "session_clear"
    cache_key = module._auth_session_cache_key(sid)
    cache = _FakeCache({cache_key: {"auth_token": "a", "refresh_token": "r"}})
    fake_auth_service = SimpleNamespace(cache_service=cache)
    monkeypatch.setattr(module, "get_auth_service", lambda: fake_auth_service)

    st.session_state[module._AUTH_SESSION_ID_KEY] = sid
    st.session_state.auth_token = "a"
    st.session_state.refresh_token = "r"
    st.session_state.user = {"email": "agent@example.com"}
    st.query_params[module._AUTH_QUERY_PARAM] = sid

    module.clear_session()

    assert "auth_token" not in st.session_state
    assert "refresh_token" not in st.session_state
    assert "user" not in st.session_state
    assert module._AUTH_SESSION_ID_KEY not in st.session_state
    assert module._AUTH_QUERY_PARAM not in st.query_params
    assert cache_key not in cache.store
