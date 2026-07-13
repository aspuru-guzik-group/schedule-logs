#!/usr/bin/env python3
"""Create subgroup secrets and initialize their Google resources."""

import argparse
import getpass
import json
import os
import re
import secrets
import sys
from pathlib import Path

from config import GROUPS, get_presenter_cols

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 and earlier can still run `create`.
    tomllib = None


SERVICE_ACCOUNT_FIELDS = (
    "type",
    "project_id",
    "private_key_id",
    "private_key",
    "client_email",
    "client_id",
    "auth_uri",
    "token_uri",
    "auth_provider_x509_cert_url",
    "client_x509_cert_url",
)

RESOURCE_PATTERNS = {
    "spreadsheet": (r"/spreadsheets/d/([^/?#]+)",),
    "folder": (r"/folders/([^/?#]+)",),
    "presentation": (r"/presentation/d/([^/?#]+)",),
}

SHEET_HEADERS = {
    "Participants": ["Name", "Email"],
    "Materials": ["Date", "Title", "Description", "PDF_Name", "PDF_Link"],
    "Slides": ["Date", "Presentation_ID", "Presentation_Link"],
    "Settings": ["Key", "Value"],
}


def extract_resource_id(value, resource_type):
    """Return a raw Google resource ID from either an ID or a full URL."""
    candidate = value.strip()
    for pattern in RESOURCE_PATTERNS[resource_type]:
        match = re.search(pattern, candidate)
        if match:
            return match.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{10,}", candidate):
        return candidate
    raise ValueError(f"Could not find a Google {resource_type} ID in: {value}")


def load_service_account(path):
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read service-account JSON: {exc}") from exc

    missing = [field for field in SERVICE_ACCOUNT_FIELDS if not data.get(field)]
    if data.get("type") != "service_account":
        missing.append("type=service_account")
    if missing:
        raise ValueError(
            "Service-account JSON is missing required values: "
            + ", ".join(sorted(set(missing)))
        )
    return data


def _toml_string(value):
    return json.dumps(str(value), ensure_ascii=False)


def render_secret(slug, values, service_account):
    group_keys = (
        "admin_password",
        "organizer_name",
        "folder_id",
        "slides_folder_id",
        "slides_template_id",
        "zoom_link",
        "spreadsheet_id",
        "encryption_key",
    )
    lines = [f"[{slug}]"]
    lines.extend(f"{key} = {_toml_string(values[key])}" for key in group_keys)
    lines.extend(("", f"[{slug}.gcp_service_account]"))
    for key in SERVICE_ACCOUNT_FIELDS:
        lines.append(f"{key} = {_toml_string(service_account[key])}")
    lines.append(
        "universe_domain = "
        + _toml_string(service_account.get("universe_domain", "googleapis.com"))
    )
    return "\n".join(lines) + "\n"


def write_secret(path, content, force=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        raise FileExistsError(f"{path} already exists; use --force to replace it")

    temp_path = path.with_name(f".{path.name}.tmp")
    fd = os.open(temp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(temp_path, path)
        os.chmod(path, 0o600)
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise


def prompt_required(label, secret=False):
    prompt = getpass.getpass if secret else input
    while True:
        value = prompt(f"{label}: ").strip()
        if value:
            return value
        print("A value is required.")


def confirm_admin_password():
    while True:
        password = prompt_required("Admin password", secret=True)
        if getpass.getpass("Confirm admin password: ") == password:
            return password
        print("Passwords did not match.")


def create_secret(args):
    service_account_path = args.service_account
    if service_account_path is None:
        service_account_path = Path(prompt_required("Service-account JSON path"))
    service_account = load_service_account(service_account_path.expanduser())

    print(f"Service account: {service_account['client_email']}")
    print("Share the Sheet and both folders as Editor with this address.")
    print("Share the Slides template as Viewer or Editor.")

    values = {
        "admin_password": confirm_admin_password(),
        "organizer_name": prompt_required("Organizer name"),
        "folder_id": extract_resource_id(
            prompt_required("Materials folder URL or ID"), "folder"
        ),
        "slides_folder_id": extract_resource_id(
            prompt_required("Slides folder URL or ID"), "folder"
        ),
        "slides_template_id": extract_resource_id(
            prompt_required("Slides template URL or ID"), "presentation"
        ),
        "zoom_link": input("Zoom link (optional): ").strip(),
        "spreadsheet_id": extract_resource_id(
            prompt_required("Google Sheet URL or ID"), "spreadsheet"
        ),
        "encryption_key": secrets.token_urlsafe(32),
    }

    output = args.output or Path(__file__).parent / "secrets" / f"{args.slug}.toml"
    write_secret(output, render_secret(args.slug, values, service_account), args.force)
    print(f"Wrote {output} with mode 0600.")
    print("Next: docker-compose restart")
    print(
        f"Then: docker-compose exec -T schedule python setup_group.py "
        f"initialize {args.slug}"
    )


def _load_group_secret(slug, secrets_dir):
    if tomllib is None:
        raise RuntimeError(
            "Python 3.11 or newer is required to initialize a subgroup."
        )
    path = secrets_dir / f"{slug}.toml"
    try:
        data = tomllib.loads(path.read_text())
        return data[slug]
    except (OSError, tomllib.TOMLDecodeError, KeyError) as exc:
        raise ValueError(f"Could not load {path}: {exc}") from exc


def initialize_group(args):
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError(
            "Google dependencies are unavailable. Run this command inside the "
            "scheduler container with docker-compose exec."
        ) from exc

    group_secret = _load_group_secret(args.slug, args.secrets_dir)
    credentials = Credentials.from_service_account_info(
        group_secret["gcp_service_account"],
        scopes=[
            "https://www.googleapis.com/auth/drive",
            "https://www.googleapis.com/auth/presentations",
            "https://www.googleapis.com/auth/spreadsheets",
        ],
    )
    spreadsheet = gspread.authorize(credentials).open_by_key(
        group_secret["spreadsheet_id"]
    )

    headers = {
        "Schedule": ["Date", *get_presenter_cols(GROUPS[args.slug])],
        **SHEET_HEADERS,
    }
    existing = {worksheet.title: worksheet for worksheet in spreadsheet.worksheets()}
    for title, expected_headers in headers.items():
        worksheet = existing.get(title)
        if worksheet is None:
            worksheet = spreadsheet.add_worksheet(title=title, rows=100, cols=8)
            worksheet.update(values=[expected_headers], range_name="A1")
            print(f"Created {title} tab.")
            continue

        current_headers = worksheet.row_values(1)
        if not current_headers:
            worksheet.update(values=[expected_headers], range_name="A1")
            print(f"Added headers to {title} tab.")
        elif current_headers != expected_headers:
            raise ValueError(
                f"{title} headers are {current_headers}; expected {expected_headers}"
            )
        else:
            print(f"Verified {title} tab.")

    drive = build("drive", "v3", credentials=credentials)
    resources = (
        (
            "materials folder",
            group_secret["folder_id"],
            "application/vnd.google-apps.folder",
            "canAddChildren",
        ),
        (
            "slides folder",
            group_secret["slides_folder_id"],
            "application/vnd.google-apps.folder",
            "canAddChildren",
        ),
        (
            "slides template",
            group_secret["slides_template_id"],
            "application/vnd.google-apps.presentation",
            "canCopy",
        ),
    )
    for label, resource_id, expected_mime_type, required_capability in resources:
        metadata = (
            drive.files()
            .get(
                fileId=resource_id,
                fields=(
                    "id,name,mimeType,trashed,"
                    "capabilities(canAddChildren,canCopy,canEdit)"
                ),
            )
            .execute()
        )
        if metadata.get("trashed"):
            raise ValueError(f"The {label} is in the trash: {metadata['name']}")
        if metadata.get("mimeType") != expected_mime_type:
            raise ValueError(
                f"The {label} has type {metadata.get('mimeType')}; "
                f"expected {expected_mime_type}"
            )
        if not metadata.get("capabilities", {}).get(required_capability):
            raise ValueError(
                f"The service account lacks {required_capability} access to "
                f"the {label}: {metadata['name']}"
            )
        print(f"Verified {label}: {metadata['name']}")

    slides = build("slides", "v1", credentials=credentials)
    presentation = (
        slides.presentations()
        .get(presentationId=group_secret["slides_template_id"])
        .execute()
    )
    template_text = []

    def collect_text(value):
        if isinstance(value, dict):
            text_run = value.get("textRun")
            if isinstance(text_run, dict):
                template_text.append(text_run.get("content", ""))
            for key, child in value.items():
                if key != "textRun":
                    collect_text(child)
        elif isinstance(value, list):
            for child in value:
                collect_text(child)

    collect_text(presentation.get("slides", []))
    required_placeholders = {"{{DATE}}"}
    required_placeholders.update(
        f"{{{{PRESENTER{i + 1}}}}}"
        for i in range(GROUPS[args.slug]["num_presenters"])
    )
    missing_placeholders = sorted(
        placeholder
        for placeholder in required_placeholders
        if placeholder not in "".join(template_text)
    )
    if missing_placeholders:
        raise ValueError(
            "Slides template is missing placeholders: "
            + ", ".join(missing_placeholders)
        )
    print("Verified Slides template placeholders.")

    print(f"{GROUPS[args.slug]['display_name']} is ready.")


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="write a secure subgroup secret")
    create.add_argument("slug", choices=GROUPS)
    create.add_argument("--service-account", type=Path)
    create.add_argument("--output", type=Path)
    create.add_argument("--force", action="store_true")
    create.set_defaults(func=create_secret)

    initialize = subparsers.add_parser(
        "initialize", help="create Sheet tabs and verify Google resources"
    )
    initialize.add_argument("slug", choices=GROUPS)
    initialize.add_argument(
        "--secrets-dir", type=Path, default=Path(__file__).parent / "secrets"
    )
    initialize.set_defaults(func=initialize_group)
    return parser


def main():
    args = build_parser().parse_args()
    try:
        args.func(args)
    except (FileExistsError, RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
