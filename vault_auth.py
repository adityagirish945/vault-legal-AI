"""Google OAuth 2.0 authentication for Vault PropTech with cookie persistence"""
import json
import os
import requests
import streamlit as st
from http.cookies import SimpleCookie
from urllib.parse import quote

# ── Fixed redirect URI — must match Google Cloud Console EXACTLY ──
_DEFAULT_REDIRECT = "https://vault-legal-ai-v1.streamlit.app/"
_COOKIE_NAME = "vault_user"
_COOKIE_MAX_AGE = 60 * 60 * 24 * 7  # 7 days


def _normalize_uri(uri: str) -> str:
    """Strip whitespace and ensure trailing slash for consistency."""
    uri = uri.strip()
    if not uri.endswith("/"):
        uri += "/"
    return uri


def get_auth_config():
    """Retrieve Google OAuth credentials from secrets or env."""
    try:
        client_id = st.secrets.get("GOOGLE_CLIENT_ID", os.getenv("GOOGLE_CLIENT_ID"))
        client_secret = st.secrets.get("GOOGLE_CLIENT_SECRET", os.getenv("GOOGLE_CLIENT_SECRET"))
        redirect_uri = st.secrets.get("GOOGLE_REDIRECT_URI", os.getenv("GOOGLE_REDIRECT_URI", _DEFAULT_REDIRECT))
    except (ImportError, AttributeError):
        client_id = os.getenv("GOOGLE_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", _DEFAULT_REDIRECT)

    return client_id, client_secret, _normalize_uri(redirect_uri)


def get_login_url(client_id, redirect_uri):
    """Generate the Google OAuth login URL."""
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth"
    scope = "openid email profile"

    return (
        f"{auth_url}"
        f"?response_type=code"
        f"&client_id={client_id}"
        f"&redirect_uri={quote(redirect_uri, safe='')}"
        f"&scope={quote(scope)}"
        f"&access_type=offline"
        f"&prompt=consent"
    )


def get_user_from_code(code, client_id, client_secret, redirect_uri):
    """Exchange the authorization code for user info."""
    token_url = "https://oauth2.googleapis.com/token"

    payload = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }

    token_response = requests.post(token_url, data=payload, timeout=15)
    if not token_response.ok:
        st.error(f"Token exchange failed ({token_response.status_code}): {token_response.text}")
        return None

    access_token = token_response.json().get("access_token")
    if not access_token:
        st.error("No access_token in response from Google.")
        return None

    userinfo_url = "https://www.googleapis.com/oauth2/v3/userinfo"
    headers = {"Authorization": f"Bearer {access_token}"}

    userinfo_response = requests.get(userinfo_url, headers=headers, timeout=10)
    if not userinfo_response.ok:
        st.error(f"Failed to get user info: {userinfo_response.text}")
        return None

    return userinfo_response.json()


# ── Cookie helpers ──────────────────────────────────────────────────────────

def _read_cookie_from_headers() -> dict | None:
    """Read the vault_user cookie from the incoming HTTP request headers."""
    try:
        cookie_header = st.context.headers.get("cookie", "")
    except Exception:
        return None

    if not cookie_header:
        return None

    sc = SimpleCookie()
    try:
        sc.load(cookie_header)
    except Exception:
        return None

    morsel = sc.get(_COOKIE_NAME)
    if not morsel:
        return None

    try:
        from urllib.parse import unquote
        raw_value = unquote(morsel.value)
        return json.loads(raw_value)
    except (json.JSONDecodeError, TypeError):
        return None


def set_user_cookie(user_info: dict):
    """Inject JS to store the user info as a browser cookie on the parent page."""
    safe_json = json.dumps(user_info, separators=(",", ":"))
    # Escape for JS string literal
    safe_json_js = safe_json.replace("\\", "\\\\").replace("'", "\\'")
    js = f"""
    <script>
    try {{
        parent.document.cookie = "{_COOKIE_NAME}=" + encodeURIComponent('{safe_json_js}') + ";path=/;max-age={_COOKIE_MAX_AGE};SameSite=Lax";
    }} catch(e) {{
        document.cookie = "{_COOKIE_NAME}=" + encodeURIComponent('{safe_json_js}') + ";path=/;max-age={_COOKIE_MAX_AGE};SameSite=Lax";
    }}
    </script>
    """
    st.components.v1.html(js, height=0, width=0)


def clear_user_cookie():
    """Inject JS to delete the user cookie from the browser."""
    js = f"""
    <script>
    try {{
        parent.document.cookie = "{_COOKIE_NAME}=;path=/;max-age=0;SameSite=Lax";
    }} catch(e) {{
        document.cookie = "{_COOKIE_NAME}=;path=/;max-age=0;SameSite=Lax";
    }}
    </script>
    """
    st.components.v1.html(js, height=0, width=0)


# ── Main auth flow ──────────────────────────────────────────────────────────

def check_auth():
    """
    Auth flow with cookie persistence:
    1. session_state.user exists → return it
    2. Cookie 'vault_user' in request → restore to session_state
    3. ?code= in URL → process OAuth, set cookie, store session
    4. None of the above → return None (show login)
    """
    # ── Handle delayed cookie injection ──
    _skip_cookie_restore = False

    if "set_cookie_data" in st.session_state:
        set_user_cookie(st.session_state.set_cookie_data)
        del st.session_state["set_cookie_data"]

    if "clear_cookie_flag" in st.session_state:
        clear_user_cookie()
        del st.session_state["clear_cookie_flag"]
        _skip_cookie_restore = True  # Don't re-read stale cookie from headers

    # 1. Already in session
    if "user" in st.session_state and st.session_state.user is not None:
        return st.session_state.user

    # 2. Restore from cookie (skip if we just cleared it)
    if not _skip_cookie_restore:
        cookie_user = _read_cookie_from_headers()
        if cookie_user and cookie_user.get("email"):
            st.session_state.user = cookie_user
            return cookie_user

    # 3. OAuth code exchange
    if "code" in st.query_params:
        code = st.query_params["code"]

        client_id, client_secret, redirect_uri = get_auth_config()

        if not client_id or not client_secret:
            st.error("Missing Google OAuth Configuration. Please configure GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.")
            return None

        with st.spinner("Signing you in..."):
            user_info = get_user_from_code(code, client_id, client_secret, redirect_uri)

        if user_info:
            st.session_state.user = user_info
            # Schedule cookie to be set on next render
            st.session_state.set_cookie_data = user_info
            st.query_params.clear()
            st.rerun()

    return None
