"""Persistent admin-managed subgroup configuration."""

import base64
import copy
import hashlib
import hmac
import json
import os
import tempfile
import threading
from pathlib import Path

from group_setup import SERVICE_ACCOUNT_FIELDS


CONFIG_VERSION = 1
PBKDF2_ITERATIONS = 600_000
DEFAULT_ADMIN_PASSWORD_HASHES = {
    "elagente": (
        "pbkdf2_sha256$600000$ZV7L7T4mMwDkDk7PYPTETg$"
        "Bz4NYNooYLWPugbYvj7RZaIPWPX8Kh5_0nDB5Jqwzp8"
    )
}
REQUIRED_INTEGRATION_FIELDS = (
    "organizer_name",
    "folder_id",
    "slides_folder_id",
    "slides_template_id",
    "spreadsheet_id",
    "encryption_key",
    "gcp_service_account",
)

_CONFIG_LOCK = threading.RLock()


def _config_path(path=None):
    if path is not None:
        return Path(path)
    return Path(
        os.environ.get("SCHEDULE_RUNTIME_CONFIG", "/app/data/groups.json")
    )


def _empty_data():
    return {"version": CONFIG_VERSION, "groups": {}}


def load_runtime_data(path=None):
    config_path = _config_path(path)
    if not config_path.exists():
        return _empty_data()
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read runtime configuration: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("groups"), dict):
        raise ValueError("Runtime configuration has an invalid structure")
    return data


def get_group_runtime_config(group_slug, path=None):
    with _CONFIG_LOCK:
        data = load_runtime_data(path)
        return copy.deepcopy(data["groups"].get(group_slug, {}))


def save_group_runtime_config(group_slug, updates, path=None):
    config_path = _config_path(path)
    with _CONFIG_LOCK:
        data = load_runtime_data(config_path)
        current = dict(data["groups"].get(group_slug, {}))
        current.update(copy.deepcopy(updates))
        data["version"] = CONFIG_VERSION
        data["groups"][group_slug] = current

        config_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(config_path.parent, 0o700)
        fd, temp_name = tempfile.mkstemp(
            prefix=f".{config_path.name}.", dir=config_path.parent
        )
        temp_path = Path(temp_name)
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, config_path)
            os.chmod(config_path, 0o600)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise
        return copy.deepcopy(current)


def is_runtime_group_ready(group_slug, path=None):
    config = get_group_runtime_config(group_slug, path)
    if not all(config.get(field) for field in REQUIRED_INTEGRATION_FIELDS):
        return False
    service_account = config["gcp_service_account"]
    return all(service_account.get(field) for field in SERVICE_ACCOUNT_FIELDS)


def _encode(value):
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _decode(value):
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def hash_admin_password(password, salt=None, iterations=PBKDF2_ITERATIONS):
    if not password:
        raise ValueError("Admin password cannot be empty")
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, iterations
    )
    return f"pbkdf2_sha256${iterations}${_encode(salt)}${_encode(digest)}"


def verify_password_hash(password, encoded_hash):
    try:
        algorithm, iterations, salt, expected = encoded_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            _decode(salt),
            int(iterations),
        )
        return hmac.compare_digest(actual, _decode(expected))
    except (TypeError, ValueError):
        return False


def verify_group_admin_password(
    group_slug, candidate, legacy_password="", path=None
):
    if not candidate:
        return False
    runtime_config = get_group_runtime_config(group_slug, path)
    encoded_hash = runtime_config.get("admin_password_hash")
    if not encoded_hash:
        encoded_hash = DEFAULT_ADMIN_PASSWORD_HASHES.get(group_slug)
    if encoded_hash:
        return verify_password_hash(candidate, encoded_hash)
    return bool(legacy_password) and hmac.compare_digest(candidate, legacy_password)


def set_group_admin_password(group_slug, password, path=None):
    return save_group_runtime_config(
        group_slug,
        {"admin_password_hash": hash_admin_password(password)},
        path,
    )
