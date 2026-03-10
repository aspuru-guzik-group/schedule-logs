import streamlit as st
import requests
import urllib.parse
import json
import time
import base64

from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
from cryptography.fernet import Fernet, InvalidToken
from streamlit_cookies_controller import CookieController

COOKIE_NAME = "schedule_auth"


def _get_slack_config():
    slack = st.secrets["slack"]
    return {
        "client_id": slack["client_id"],
        "client_secret": slack["client_secret"],
        "team_id": slack["team_id"],
    }


def _get_redirect_uri():
    return st.secrets.get("app_url", "http://localhost:8501").rstrip("/")


def _get_auth_url():
    config = _get_slack_config()
    redirect_uri = _get_redirect_uri()
    return (
        f"https://slack.com/oauth/v2/authorize?"
        f"client_id={config['client_id']}&"
        f"user_scope=identity.basic,identity.email&"
        f"redirect_uri={urllib.parse.quote(redirect_uri, safe='')}"
    )


def _exchange_code(code):
    config = _get_slack_config()
    redirect_uri = _get_redirect_uri()
    response = requests.post(
        "https://slack.com/api/oauth.v2.access",
        data={
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "code": code,
            "redirect_uri": redirect_uri,
        },
    )
    data = response.json()
    if not data.get("ok"):
        return None
    return data


def _get_user_identity(token):
    response = requests.get(
        "https://slack.com/api/users.identity",
        headers={"Authorization": f"Bearer {token}"},
    )
    data = response.json()
    if not data.get("ok"):
        return None
    return data


# --- Token encryption ---


def _get_auth_fernet():
    key_material = st.secrets["slack"]["client_secret"].encode()
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"schedule_auth_cookie",
        iterations=100000,
        backend=default_backend(),
    )
    derived_key = base64.urlsafe_b64encode(kdf.derive(key_material))
    return Fernet(derived_key)


def _create_auth_token(user_info):
    f = _get_auth_fernet()
    data = json.dumps({"user": user_info})
    return f.encrypt(data.encode()).decode()


def _verify_auth_token(token):
    try:
        f = _get_auth_fernet()
        data = json.loads(f.decrypt(token.encode()).decode())
        return data.get("user")
    except (InvalidToken, json.JSONDecodeError, Exception):
        return None


# --- Main auth flow ---


def require_auth():
    """Require Slack authentication. Returns user dict or shows login and stops."""
    controller = CookieController(key="auth_cookies")

    # 1. Already authenticated this session
    if "slack_user" in st.session_state:
        return st.session_state["slack_user"]

    # 2. First render: cookie controller needs one cycle to load in the
    #    browser and send values back. Show blank page during that cycle.
    if "auth_ready" not in st.session_state:
        st.session_state["auth_ready"] = True
        st.stop()

    # 3. Check persistent cookie (controller has loaded by now)
    token = controller.get(COOKIE_NAME)
    if token:
        user = _verify_auth_token(token)
        if user:
            st.session_state["slack_user"] = user
            return user

    config = _get_slack_config()

    # 3. Check for OAuth callback
    params = st.query_params
    code = params.get("code")
    if code:
        with st.spinner("Signing in with Slack..."):
            token_data = _exchange_code(code)
            if token_data:
                user_token = token_data.get("authed_user", {}).get("access_token")
                team_id = token_data.get("team", {}).get("id")

                if team_id != config["team_id"]:
                    st.error("You must be a member of the MatterLab Slack workspace.")
                    st.stop()

                if user_token:
                    identity = _get_user_identity(user_token)
                    if identity:
                        user = {
                            "name": identity.get("user", {}).get("name", ""),
                            "email": identity.get("user", {}).get("email", ""),
                            "team": identity.get("team", {}).get("name", ""),
                        }
                        st.session_state["slack_user"] = user

                        # Set persistent cookie
                        auth_token = _create_auth_token(user)
                        controller.set(COOKIE_NAME, auth_token)

                        st.query_params.clear()
                        time.sleep(1)  # Let cookie write complete
                        st.rerun()

        st.error("Authentication failed. Please try again.")
        st.stop()

    # 4. Show login page
    _, center, _ = st.columns([1, 2, 1])
    with center:
        st.image("logo.png", width=120)
        st.markdown("## MatterLab Group Meetings")
        st.caption("schedule.matter.toronto.edu")
        st.write("")
        st.info("Sign in with your MatterLab Slack account to continue.")
        st.write("")
        auth_url = _get_auth_url()
        st.markdown(
            f"""
            <a href="{auth_url}" style="
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: 12px;
                width: 100%;
                padding: 12px 24px;
                background-color: #4A154B;
                color: white;
                text-decoration: none;
                border-radius: 8px;
                font-size: 16px;
                font-weight: 600;
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                transition: background-color 0.2s;
            " onmouseover="this.style.backgroundColor='#611f69'"
              onmouseout="this.style.backgroundColor='#4A154B'">
                <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 123 123">
                    <path d="M25.8 77.6c0 7.1-5.8 12.9-12.9 12.9S0 84.7 0 77.6s5.8-12.9 12.9-12.9h12.9v12.9z" fill="#E01E5A"/>
                    <path d="M32.3 77.6c0-7.1 5.8-12.9 12.9-12.9s12.9 5.8 12.9 12.9v32.3c0 7.1-5.8 12.9-12.9 12.9s-12.9-5.8-12.9-12.9V77.6z" fill="#E01E5A"/>
                    <path d="M45.2 25.8c-7.1 0-12.9-5.8-12.9-12.9S38.1 0 45.2 0s12.9 5.8 12.9 12.9v12.9H45.2z" fill="#36C5F0"/>
                    <path d="M45.2 32.3c7.1 0 12.9 5.8 12.9 12.9s-5.8 12.9-12.9 12.9H12.9C5.8 58.1 0 52.3 0 45.2s5.8-12.9 12.9-12.9h32.3z" fill="#36C5F0"/>
                    <path d="M97.2 45.2c0-7.1 5.8-12.9 12.9-12.9s12.9 5.8 12.9 12.9-5.8 12.9-12.9 12.9H97.2V45.2z" fill="#2EB67D"/>
                    <path d="M90.7 45.2c0 7.1-5.8 12.9-12.9 12.9s-12.9-5.8-12.9-12.9V12.9C64.9 5.8 70.7 0 77.8 0s12.9 5.8 12.9 12.9v32.3z" fill="#2EB67D"/>
                    <path d="M77.8 97.2c7.1 0 12.9 5.8 12.9 12.9s-5.8 12.9-12.9 12.9-12.9-5.8-12.9-12.9V97.2h12.9z" fill="#ECB22E"/>
                    <path d="M77.8 90.7c-7.1 0-12.9-5.8-12.9-12.9s5.8-12.9 12.9-12.9h32.3c7.1 0 12.9 5.8 12.9 12.9s-5.8 12.9-12.9 12.9H77.8z" fill="#ECB22E"/>
                </svg>
                Sign in with Slack
            </a>
            """,
            unsafe_allow_html=True,
        )
    st.stop()
