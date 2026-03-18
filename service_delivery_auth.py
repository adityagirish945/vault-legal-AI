"""
Service Delivery Phone Authentication via Firebase REST API.

Flow:
1. sendOtp(phone_number, recaptcha_token) -> session_info
2. verifyOtp(session_info, otp_code)      -> id_token, uid, phone_number

DEV MODE: Set DEV_MODE=true in .env to bypass Firebase (use OTP: 123456)
"""
import os
import requests
import streamlit as st


def _get_firebase_web_api_key() -> str:
    """Get Firebase Web API key from secrets or env."""
    try:
        key = st.secrets.get("FIREBASE_WEB_API_KEY", os.getenv("FIREBASE_WEB_API_KEY", ""))
    except (AttributeError, Exception):
        key = os.getenv("FIREBASE_WEB_API_KEY", "")
    if not key:
        raise ValueError("FIREBASE_WEB_API_KEY not configured.")
    return key


def _is_dev_mode() -> bool:
    """Check if running in development mode (bypass Firebase)."""
    try:
        return st.secrets.get("DEV_MODE", os.getenv("DEV_MODE", "")).lower() == "true"
    except (AttributeError, Exception):
        return os.getenv("DEV_MODE", "").lower() == "true"


def send_otp(phone_number: str, recaptcha_token: str) -> dict:
    """
    Send OTP via Firebase Phone Auth (REST API).

    Args:
        phone_number: E.164 format, e.g. '+919876543210'
        recaptcha_token: reCAPTCHA v2 response token from the client

    Returns:
        dict with 'sessionInfo' on success, or 'error' key on failure.
    """
    # DEV MODE: Bypass Firebase, return mock session (OTP will be 123456)
    if _is_dev_mode():
        return {"sessionInfo": f"DEV_SESSION_{phone_number}"}
    
    api_key = _get_firebase_web_api_key()
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:sendVerificationCode?key={api_key}"
    payload = {
        "phoneNumber": phone_number,
        "recaptchaToken": recaptcha_token,
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        data = resp.json()
        if not resp.ok or "sessionInfo" not in data:
            error_msg = data.get("error", {}).get("message", "Unknown error sending OTP.")
            return {"error": error_msg}
        return {"sessionInfo": data["sessionInfo"]}
    except Exception as e:
        return {"error": str(e)}


def verify_otp(session_info: str, otp_code: str) -> dict:
    """
    Verify the OTP code returned by Firebase.

    Args:
        session_info: The sessionInfo returned from send_otp()
        otp_code: 6-digit OTP entered by user

    Returns:
        dict with 'idToken', 'localId' (uid), 'phoneNumber' on success,
        or 'error' key on failure.
    """
    # DEV MODE: Accept OTP 123456 for any phone number
    if _is_dev_mode() and session_info.startswith("DEV_SESSION_"):
        if otp_code == "123456":
            phone = session_info.replace("DEV_SESSION_", "")
            return {
                "idToken": f"DEV_TOKEN_{phone}",
                "localId": f"dev_user_{phone}",
                "phoneNumber": phone,
            }
        else:
            return {"error": "Invalid OTP. Use 123456 in dev mode."}
    
    api_key = _get_firebase_web_api_key()
    url = f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPhoneNumber?key={api_key}"
    payload = {
        "sessionInfo": session_info,
        "code": otp_code,
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        data = resp.json()
        if not resp.ok or "idToken" not in data:
            error_msg = data.get("error", {}).get("message", "Invalid OTP. Please try again.")
            return {"error": error_msg}
        return {
            "idToken": data["idToken"],
            "localId": data.get("localId", ""),
            "phoneNumber": data.get("phoneNumber", ""),
        }
    except Exception as e:
        return {"error": str(e)}
