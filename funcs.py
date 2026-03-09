import datetime

from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
from cryptography.fernet import Fernet
import base64
import streamlit as st

from config import DAY_MAP


def get_next_day_of_week(after_date, day_name):
    """Get the next occurrence of a given day of the week after after_date."""
    target = DAY_MAP[day_name.lower()]
    days_ahead = target - after_date.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    return after_date + datetime.timedelta(days=days_ahead)


def get_next_wednesday(after_date):
    return get_next_day_of_week(after_date, "wednesday")


def highlight_empty(val):
    return "background-color: goldenrod" if val in ["EMPTY", "", " "] else ""


def highlight_random(val):
    if not isinstance(val, str):
        return ""
    color = "background-color: darkblue" if val.startswith("[P]") else ""
    color = "background-color: darkred" if val.startswith("[C]") else color
    color = "background-color: darkblue" if val.startswith("[R]") else color
    return color


def get_fernet(group_slug=None):
    """Get a Fernet cipher. Uses group-specific encryption key if group_slug provided."""
    if group_slug:
        encryption_key_str = st.secrets[group_slug]["encryption_key"]
    else:
        encryption_key_str = st.secrets["encryption_key"]["value"]
    encryption_key_bytes = encryption_key_str.encode("utf-8")
    salt = f"{group_slug or 'mlatml'}_salt".encode()
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100000,
        backend=default_backend(),
    )
    derived_key = base64.urlsafe_b64encode(kdf.derive(encryption_key_bytes))
    return Fernet(derived_key)


def encrypt_name(name: str, group_slug: str = None) -> str:
    f = get_fernet(group_slug)
    encrypted = f.encrypt(name.encode("utf-8"))
    return encrypted.decode("utf-8")


def decrypt_name(encrypted_name: str, group_slug: str = None) -> str:
    f = get_fernet(group_slug)
    decrypted = f.decrypt(encrypted_name.encode("utf-8"))
    return decrypted.decode("utf-8")
