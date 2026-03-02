"""Google OAuth 2.0 authentication for Vault PropTech with encoding"""
import os
import requests
import streamlit as st
from urllib.parse import quote

# ── Fixed redirect URI — must match Google Cloud Console EXACTLY ──
_DEFAULT_REDIRECT = "https://vault-legal-ai-v1.streamlit.app/"


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


def check_auth():
    """
    Main auth flow:
    - If already logged in (session_state.user), return user.
    - If ?code=... is in URL, process login, store user, clear URL, return user.
    - If neither, return None.
    """
    if "user" in st.session_state and st.session_state.user is not None:
        return st.session_state.user

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
            st.query_params.clear()
            st.rerun()

    return None
