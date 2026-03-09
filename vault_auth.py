"""Google OAuth 2.0 authentication for Vault PropTech with cookie persistence"""
import json
import os
import requests
import streamlit as st
from urllib.parse import quote, unquote
from base64 import b64encode, b64decode

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
    scope = "openid email profile https://www.googleapis.com/auth/documents https://www.googleapis.com/auth/drive.file"

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

    # Store access token for Google Docs export
    access_token = token_response.json().get("access_token")
    return userinfo_response.json(), access_token


# ── Cookie helpers ──────────────────────────────────────────────────────────

def set_user_cookie(user_info: dict):
    """Inject JS to store the user info as a browser cookie on the parent page."""
    safe_json = json.dumps(user_info, separators=(",", ":"))
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


def inject_cookie_restore_script():
    """
    Inject a <script> element into the PARENT document that reads the cookie.
    Chrome blocks parent.document.cookie reads from iframes, but a script
    injected into the parent runs in the parent context with full cookie access.
    """
    js = f"""
    <script>
    (function() {{
        try {{
            var s = parent.document.createElement('script');
            s.textContent = `
                (function() {{
                    var match = document.cookie.match(/(^|;\\\\s*){_COOKIE_NAME}=([^;]*)/);
                    if (match) {{
                        var val = decodeURIComponent(match[2]);
                        var b64 = btoa(unescape(encodeURIComponent(val)));
                        var url = new URL(window.location.href);
                        if (!url.searchParams.has('vault_restore') && !url.searchParams.has('code')) {{
                            url.searchParams.set('vault_restore', b64);
                            window.location.replace(url.toString());
                        }}
                    }}
                }})();
            `;
            parent.document.head.appendChild(s);
        }} catch(e) {{
            // Fallback: try reading directly (works on Safari)
            var cookies = document.cookie;
            var match = cookies.match(/(^|;\\\\s*){_COOKIE_NAME}=([^;]*)/);
            if (match) {{
                var val = decodeURIComponent(match[2]);
                var b64 = btoa(unescape(encodeURIComponent(val)));
                var url = new URL(parent.window.location.href);
                if (!url.searchParams.has('vault_restore') && !url.searchParams.has('code')) {{
                    url.searchParams.set('vault_restore', b64);
                    parent.window.location.replace(url.toString());
                }}
            }}
        }}
    }})();
    </script>
    """
    st.components.v1.html(js, height=0, width=0)


def _decode_restore_param(b64_value: str) -> dict | None:
    """Decode the base64 vault_restore query param back to user info dict."""
    try:
        decoded = b64decode(b64_value).decode("utf-8")
        user = json.loads(decoded)
        if user.get("email"):
            return user
    except Exception:
        pass
    return None


# ── Main auth flow ──────────────────────────────────────────────────────────

def check_auth():
    """
    Auth flow with cookie persistence:
    1. session_state.user exists → return it
    2. ?vault_restore= in URL → decode user from cookie via JS bridge
    3. ?code= in URL → process OAuth, set cookie, store session
    4. None → inject JS to check cookie and redirect if found
    """
    # ── Handle delayed cookie injection ──
    _skip_cookie_restore = False

    if "set_cookie_data" in st.session_state:
        set_user_cookie(st.session_state.set_cookie_data)
        del st.session_state["set_cookie_data"]

    if "clear_cookie_flag" in st.session_state:
        clear_user_cookie()
        del st.session_state["clear_cookie_flag"]
        _skip_cookie_restore = True

    # 1. Already in session
    if "user" in st.session_state and st.session_state.user is not None:
        return st.session_state.user

    # 2. Restore from cookie via JS bridge (vault_restore query param)
    if not _skip_cookie_restore and "vault_restore" in st.query_params:
        b64_value = st.query_params["vault_restore"]
        user_info = _decode_restore_param(b64_value)
        if user_info:
            st.session_state.user = user_info
            st.query_params.clear()
            st.rerun()

    # 3. OAuth code exchange
    if "code" in st.query_params:
        code = st.query_params["code"]

        client_id, client_secret, redirect_uri = get_auth_config()

        if not client_id or not client_secret:
            st.error("Missing Google OAuth Configuration. Please configure GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.")
            return None

        with st.spinner("Signing you in..."):
            result = get_user_from_code(code, client_id, client_secret, redirect_uri)

        if result:
            user_info, access_token = result
            st.session_state.user = user_info
            st.session_state.user_token = access_token  # For Google Docs export
            st.session_state.set_cookie_data = user_info
            st.query_params.clear()
            st.rerun()

    # 4. No session, no code, no restore → inject JS to check cookie
    if not _skip_cookie_restore:
        inject_cookie_restore_script()

    return None
