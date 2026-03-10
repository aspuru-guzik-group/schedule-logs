import streamlit as st
import requests


def _get_slack_config():
    """Read Slack OAuth config from secrets."""
    slack = st.secrets["slack"]
    return {
        "client_id": slack["client_id"],
        "client_secret": slack["client_secret"],
        "team_id": slack["team_id"],
    }


def _get_redirect_uri():
    app_url = st.secrets.get("app_url", "http://localhost:8501")
    return app_url.rstrip("/")


def _get_auth_url():
    config = _get_slack_config()
    redirect_uri = _get_redirect_uri()
    return (
        f"https://slack.com/oauth/v2/authorize?"
        f"client_id={config['client_id']}&"
        f"user_scope=identity.basic,identity.email&"
        f"redirect_uri={redirect_uri}"
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


def require_auth():
    """Require Slack authentication. Returns user dict or shows login and stops."""
    # Already authenticated this session
    if "slack_user" in st.session_state:
        return st.session_state["slack_user"]

    config = _get_slack_config()

    # Check for OAuth callback (Slack redirected back with a code)
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
                        st.query_params.clear()
                        st.rerun()

        st.error("Authentication failed. Please try again.")
        st.stop()

    # Show login page
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
