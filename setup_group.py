#!/usr/bin/env python3
"""Create subgroup secrets and initialize their Google resources."""

import argparse
import getpass
import json
import os
import secrets
import sys
from pathlib import Path

from config import GROUPS, get_group_config
from group_setup import (
    SERVICE_ACCOUNT_FIELDS,
    extract_resource_id,
    initialize_google_resources,
    parse_service_account_json,
)

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 and earlier can still run `create`.
    tomllib = None


def load_service_account(path):
    try:
        return parse_service_account_json(path.read_bytes())
    except OSError as exc:
        raise ValueError(f"Could not read service-account JSON: {exc}") from exc


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
    group_secret = _load_group_secret(args.slug, args.secrets_dir)
    _, messages = initialize_google_resources(
        get_group_config(args.slug),
        group_secret,
        group_secret["gcp_service_account"],
    )
    for message in messages:
        print(f"{message}.")
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
