"""Per-subgroup Google Drive OAuth connection management."""

import hashlib
import hmac
import json
import secrets
import time

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from runtime_config import (
    get_google_oauth_client,
    get_group_runtime_config,
    save_google_oauth_client,
    save_group_runtime_config,
)


OAUTH_SCOPES = (
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/presentations",
    "https://www.googleapis.com/auth/spreadsheets",
)
STATE_PREFIX = "schedule-drive:"
STATE_MAX_AGE_SECONDS = 15 * 60


class GoogleDriveOAuthError(RuntimeError):
    pass


def redirect_uri_from_app_url(app_url):
    return str(app_url).strip().rstrip("/")


def parse_oauth_client_json(value, redirect_uri=None):
    try:
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        data = json.loads(value) if isinstance(value, str) else value
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid Google OAuth client JSON: {exc}") from exc

    if not isinstance(data, dict) or not isinstance(data.get("web"), dict):
        raise ValueError("Upload a Google OAuth client JSON with application type Web")
    web = data["web"]
    required = ("client_id", "client_secret", "auth_uri", "token_uri")
    missing = [field for field in required if not web.get(field)]
    if missing:
        raise ValueError(
            "Google OAuth client JSON is missing: " + ", ".join(missing)
        )
    if redirect_uri and redirect_uri not in web.get("redirect_uris", []):
        raise ValueError(
            "Add this exact Authorized redirect URI in Google Cloud, then "
            f"download the client JSON again: {redirect_uri}"
        )
    return {"web": dict(web)}


def save_oauth_client(value, redirect_uri, path=None):
    client = parse_oauth_client_json(value, redirect_uri=redirect_uri)
    return save_google_oauth_client(client, path)


def has_oauth_client(path=None):
    return bool(get_google_oauth_client(path).get("web", {}).get("client_id"))


def is_drive_oauth_state(state):
    return isinstance(state, str) and state.startswith(STATE_PREFIX)


def _state_group_slug(state):
    if not is_drive_oauth_state(state):
        raise GoogleDriveOAuthError("Invalid Google Drive connection state")
    remainder = state[len(STATE_PREFIX) :]
    group_slug, separator, nonce = remainder.partition(":")
    if not separator or not group_slug or not nonce:
        raise GoogleDriveOAuthError("Invalid Google Drive connection state")
    return group_slug


def _state_digest(state):
    return hashlib.sha256(state.encode("utf-8")).hexdigest()


def create_authorization_url(group_slug, redirect_uri, path=None, now=None):
    client = get_google_oauth_client(path)
    if not client.get("web", {}).get("client_id"):
        raise GoogleDriveOAuthError("Google OAuth has not been configured yet")

    state = f"{STATE_PREFIX}{group_slug}:{secrets.token_urlsafe(32)}"
    flow = Flow.from_client_config(
        client,
        scopes=OAUTH_SCOPES,
        redirect_uri=redirect_uri,
        state=state,
    )
    authorization_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    code_verifier = flow.code_verifier
    if not isinstance(code_verifier, str) or not code_verifier:
        raise GoogleDriveOAuthError(
            "Google Drive connection security could not be initialized. Start again."
        )
    save_group_runtime_config(
        group_slug,
        {
            "drive_oauth_pending": {
                "state_digest": _state_digest(state),
                "code_verifier": code_verifier,
                "created_at": int(now if now is not None else time.time()),
            }
        },
        path,
    )
    return authorization_url


def get_connection(group_slug, path=None):
    return dict(get_group_runtime_config(group_slug, path).get("drive_oauth", {}))


def has_connection(group_slug, path=None):
    connection = get_connection(group_slug, path)
    client_id = get_google_oauth_client(path).get("web", {}).get("client_id")
    return bool(
        connection.get("refresh_token")
        and client_id
        and connection.get("client_id") == client_id
    )


def get_user_credentials(group_slug, path=None):
    client = get_google_oauth_client(path).get("web", {})
    connection = get_connection(group_slug, path)
    if not client.get("client_id") or not connection.get("refresh_token"):
        raise GoogleDriveOAuthError(
            "Connect the subgroup lead's Google Drive account in Admin Settings."
        )
    if connection.get("client_id") != client["client_id"]:
        raise GoogleDriveOAuthError(
            "The Google OAuth application changed. Reconnect the subgroup "
            "lead's Google Drive account in Admin Settings."
        )
    return Credentials(
        token=None,
        refresh_token=connection["refresh_token"],
        token_uri=client["token_uri"],
        client_id=client["client_id"],
        client_secret=client["client_secret"],
        scopes=OAUTH_SCOPES,
    )


def finish_connection(code, state, redirect_uri, path=None, now=None):
    group_slug = _state_group_slug(state)
    runtime = get_group_runtime_config(group_slug, path)
    pending = runtime.get("drive_oauth_pending", {})
    expected_digest = pending.get("state_digest", "")
    created_at = pending.get("created_at", 0)
    current_time = int(now if now is not None else time.time())
    if not expected_digest or not hmac.compare_digest(
        expected_digest, _state_digest(state)
    ):
        raise GoogleDriveOAuthError(
            "This Google Drive connection link is invalid or was already used."
        )
    if current_time - int(created_at) > STATE_MAX_AGE_SECONDS:
        save_group_runtime_config(
            group_slug, {"drive_oauth_pending": {}}, path
        )
        raise GoogleDriveOAuthError(
            "This Google Drive connection link expired. Start the connection again."
        )
    code_verifier = pending.get("code_verifier")
    if not isinstance(code_verifier, str) or not code_verifier:
        save_group_runtime_config(
            group_slug, {"drive_oauth_pending": {}}, path
        )
        raise GoogleDriveOAuthError(
            "This Google Drive connection link was created before the latest "
            "update. Start the connection again."
        )

    client = get_google_oauth_client(path)
    if not client.get("web", {}).get("client_id"):
        raise GoogleDriveOAuthError("Google OAuth has not been configured yet")

    save_group_runtime_config(group_slug, {"drive_oauth_pending": {}}, path)
    try:
        flow = Flow.from_client_config(
            client,
            scopes=OAUTH_SCOPES,
            redirect_uri=redirect_uri,
            state=state,
            code_verifier=code_verifier,
            autogenerate_code_verifier=False,
        )
        flow.fetch_token(code=code)
    except Exception as exc:
        raise GoogleDriveOAuthError(
            "Google did not complete the Drive connection. Start again."
        ) from exc

    refresh_token = flow.credentials.refresh_token
    if not refresh_token:
        refresh_token = runtime.get("drive_oauth", {}).get("refresh_token")
    if not refresh_token:
        raise GoogleDriveOAuthError(
            "Google did not return long-term access. Reconnect and approve access."
        )

    try:
        drive = build("drive", "v3", credentials=flow.credentials)
        account = (
            drive.about()
            .get(fields="user(displayName,emailAddress)")
            .execute()
            .get("user", {})
        )
    except Exception as exc:
        raise GoogleDriveOAuthError(
            "The connected account could not access Google Drive."
        ) from exc

    connection = {
        "refresh_token": refresh_token,
        "client_id": client["web"]["client_id"],
        "email": account.get("emailAddress", ""),
        "display_name": account.get("displayName", ""),
        "connected_at": current_time,
    }
    save_group_runtime_config(
        group_slug,
        {"drive_oauth": connection, "drive_oauth_pending": {}},
        path,
    )
    return group_slug, dict(connection)


def disconnect(group_slug, path=None):
    save_group_runtime_config(
        group_slug,
        {"drive_oauth": {}, "drive_oauth_pending": {}},
        path,
    )
