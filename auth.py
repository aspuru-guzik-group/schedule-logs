import streamlit as st
import streamlit.components.v1 as components
import requests
import json
import time
import base64
import urllib.parse

from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
from cryptography.fernet import Fernet, InvalidToken

COOKIE_NAME = "schedule_auth"
COOKIE_MAX_AGE_DAYS = 3650  # ~10 years


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


# --- Cookie-based persistence ---


def _get_auth_fernet():
    """Derive a Fernet key from the Slack client_secret for cookie encryption."""
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
    """Encrypt user info + expiry into a cookie-safe token."""
    f = _get_auth_fernet()
    data = json.dumps({
        "user": user_info,
        "exp": time.time() + COOKIE_MAX_AGE_DAYS * 86400,
    })
    token = f.encrypt(data.encode()).decode()
    return urllib.parse.quote(token, safe="")


def _verify_auth_token(token):
    """Decrypt and verify a token. Returns user dict or None."""
    try:
        f = _get_auth_fernet()
        raw = urllib.parse.unquote(token)
        data = json.loads(f.decrypt(raw.encode()).decode())
        if data.get("exp", 0) < time.time():
            return None
        return data.get("user")
    except (InvalidToken, json.JSONDecodeError, Exception):
        return None


def _set_auth_cookie(token):
    """Set auth cookie on the parent page via JS."""
    max_age = COOKIE_MAX_AGE_DAYS * 86400
    components.html(
        f"""<script>
        parent.document.cookie = "{COOKIE_NAME}={token}; path=/; max-age={max_age}; SameSite=Lax; Secure";
        </script>""",
        height=0,
    )


def _clear_auth_cookie():
    components.html(
        f"""<script>
        parent.document.cookie = "{COOKIE_NAME}=; path=/; max-age=0; SameSite=Lax; Secure";
        </script>""",
        height=0,
    )


def _read_auth_cookie():
    """Read auth cookie from the request. Returns token string or None."""
    try:
        cookies = st.context.cookies
        return cookies.get(COOKIE_NAME)
    except Exception:
        return None


# --- Main auth flow ---


def require_auth():
    """Require Slack authentication. Returns user dict or shows login and stops."""
    # 1. Already authenticated this session
    if "slack_user" in st.session_state:
        return st.session_state["slack_user"]

    # 2. Check for persistent cookie
    cookie_token = _read_auth_cookie()
    if cookie_token:
        user = _verify_auth_token(cookie_token)
        if user:
            st.session_state["slack_user"] = user
            return user

    config = _get_slack_config()

    # 3. Check for OAuth callback (Slack redirected back with a code)
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

                        # Set cookie and redirect via JS (st.rerun would
                        # kill the page before the browser sets the cookie)
                        auth_token = _create_auth_token(user)
                        max_age = COOKIE_MAX_AGE_DAYS * 86400
                        redirect_uri = _get_redirect_uri()
                        st.markdown("Signing you in...")
                        st.markdown(
                            f'<meta http-equiv="refresh" content="1;url={redirect_uri}">'
                            f"""
                            <script>
                            document.cookie = "{COOKIE_NAME}={auth_token}; path=/; max-age={max_age}; SameSite=Lax; Secure";
                            window.location.replace("{redirect_uri}");
                            </script>
                            """,
                            unsafe_allow_html=True,
                        )
                        st.stop()

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
        st.link_button(
            "Sign in with Slack",
            _get_auth_url(),
            use_container_width=True,
        )
    st.stop()


def logout():
    """Clear auth state and cookie."""
    st.session_state.pop("slack_user", None)
    _clear_auth_cookie()
