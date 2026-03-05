"""
Authentication component for Streamlit dashboard.

Provides login/logout functionality and session management.
"""
import secrets
from typing import Optional

import streamlit as st

from bots.shared.auth_service import User, UserRole, get_auth_service
from bots.shared.logger import get_logger
from command_center.async_runtime import run_async

logger = get_logger(__name__)

_AUTH_QUERY_PARAM = "sid"
_AUTH_SESSION_ID_KEY = "auth_session_id"
_AUTH_SESSION_CACHE_PREFIX = "auth:streamlit:session"
_AUTH_SESSION_TTL_SECONDS = 7 * 24 * 60 * 60


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


def _persist_auth_session(auth_token: str, refresh_token: str) -> None:
    """Persist auth tokens server-side and keep only opaque session id in URL."""
    try:
        auth_service = get_auth_service()
        session_id = st.session_state.get(_AUTH_SESSION_ID_KEY)
        if not session_id:
            session_id = secrets.token_urlsafe(24)
            st.session_state[_AUTH_SESSION_ID_KEY] = session_id

        payload = {
            "auth_token": auth_token,
            "refresh_token": refresh_token,
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
        _write_query_param(_AUTH_QUERY_PARAM, session_id)
        # Sliding TTL so active sessions persist while in use.
        _persist_auth_session(auth_token, refresh_token)
        return True
    except Exception as exc:
        logger.warning(f"Failed to restore Streamlit auth session: {exc}")
        return False


def _set_authenticated_state(user: User, auth_token: str, refresh_token: str) -> None:
    st.session_state.auth_token = auth_token
    st.session_state.refresh_token = refresh_token
    st.session_state.user = {
        'user_id': user.user_id,
        'email': user.email,
        'name': user.name,
        'role': user.role.value
    }
    st.session_state.must_change_password = user.must_change_password
    _persist_auth_session(auth_token, refresh_token)


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


def render_login_form() -> Optional[User]:
    """
    Render login form and handle authentication.
    
    Returns:
        Authenticated user if login successful, None otherwise
    """
    st.markdown("""
    <div style="max-width: 400px; margin: 0 auto; padding: 2rem; 
                background: white; border-radius: 10px; 
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);">
    """, unsafe_allow_html=True)
    
    st.markdown("### 🏠 Jorge's Real Estate AI")
    st.markdown("**Dashboard Login**")
    
    with st.form("login_form"):
        email = st.text_input("Email", placeholder="jorge@realestate.ai")
        password = st.text_input("Password", type="password", placeholder="Enter your password")
        submit = st.form_submit_button("Login", use_container_width=True)
        
        if submit:
            if not email or not password:
                st.error("Please enter both email and password")
                return None
            
            try:
                # Authenticate user
                auth_service = get_auth_service()
                tokens = run_async(auth_service.authenticate(email, password))
                
                if tokens:
                    # Get user info
                    user = run_async(auth_service.validate_token(tokens.access_token))
                    if user:
                        # Store in session (and persist across browser refreshes)
                        _set_authenticated_state(user, tokens.access_token, tokens.refresh_token)
                        
                        st.success(f"Welcome, {user.name}!")
                        st.rerun()
                        return user
                
                st.error("Invalid email or password")
                return None
                
            except Exception as e:
                logger.exception(f"Login error: {e}")
                st.error("Login failed. Please try again.")
                return None
    
    # Security guidance
    st.markdown("---")
    st.info("""
    Use your assigned dashboard credentials.

    If this is your first login, contact your administrator for secure account setup.
    """)
    
    st.markdown("</div>", unsafe_allow_html=True)
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
                'role': user.role.value
            }
            st.session_state.must_change_password = user.must_change_password
            if 'refresh_token' in st.session_state:
                _persist_auth_session(st.session_state.auth_token, st.session_state.refresh_token)
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
    st.sidebar.markdown("### 👤 User")
    
    # User info
    role_emoji = {
        'admin': '👑',
        'agent': '🏡', 
        'viewer': '👁️'
    }
    
    emoji = role_emoji.get(user.role.value, '👤')
    st.sidebar.markdown(f"**{emoji} {user.name}**")
    st.sidebar.markdown(f"*{user.role.value.title()}*")
    
    # Logout button
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
        st.error(f"🚫 Access Denied: You need {action} permission for {resource}")
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
        'admin': '👑 Admin',
        'agent': '🏡 Agent', 
        'viewer': '👁️ Viewer'
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
    st.markdown("### 👥 User Management")
    
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
                    st.write(f"📧 {user.email}")
                with col2:
                    render_role_badge(user)
                with col3:
                    status = "✅ Active" if user.is_active else "❌ Inactive"
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
                    format_func=lambda x: {'agent': '🏡 Agent', 'viewer': '👁️ Viewer', 'admin': '👑 Admin'}[x]
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
