"""Validation and Google resource setup shared by the UI and CLI."""

import json
import re
from datetime import datetime, timezone


SCOPES = (
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/presentations",
    "https://www.googleapis.com/auth/spreadsheets",
)
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
    candidate = str(value).strip()
    for pattern in RESOURCE_PATTERNS[resource_type]:
        match = re.search(pattern, candidate)
        if match:
            return match.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{10,}", candidate):
        return candidate
    raise ValueError(f"Could not find a Google {resource_type} ID in: {value}")


def validate_service_account(service_account):
    if not isinstance(service_account, dict):
        raise ValueError("Service-account JSON must contain an object")
    missing = [
        field for field in SERVICE_ACCOUNT_FIELDS if not service_account.get(field)
    ]
    if service_account.get("type") != "service_account":
        missing.append("type=service_account")
    if missing:
        raise ValueError(
            "Service-account JSON is missing required values: "
            + ", ".join(sorted(set(missing)))
        )
    return dict(service_account)


def parse_service_account_json(value):
    try:
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        data = json.loads(value) if isinstance(value, str) else value
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid service-account JSON: {exc}") from exc
    return validate_service_account(data)


def normalize_resource_values(values):
    normalized = dict(values)
    normalized["spreadsheet_id"] = extract_resource_id(
        values.get("spreadsheet_id", ""), "spreadsheet"
    )
    normalized["folder_id"] = extract_resource_id(
        values.get("folder_id", ""), "folder"
    )
    normalized["slides_folder_id"] = extract_resource_id(
        values.get("slides_folder_id", ""), "folder"
    )
    normalized["slides_template_id"] = extract_resource_id(
        values.get("slides_template_id", ""), "presentation"
    )
    return normalized


def required_slide_placeholders(num_presenters):
    placeholders = {"{{DATE}}"}
    if num_presenters == 1:
        placeholders.add("{{PRESENTER}}")
    else:
        placeholders.update(
            f"{{{{PRESENTER{index + 1}}}}}"
            for index in range(num_presenters)
        )
    return placeholders


def _presentation_text(presentation):
    chunks = []

    def collect(value):
        if isinstance(value, dict):
            text_run = value.get("textRun")
            if isinstance(text_run, dict):
                chunks.append(text_run.get("content", ""))
            for key, child in value.items():
                if key != "textRun":
                    collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    collect(presentation.get("slides", []))
    return "".join(chunks)


def _schedule_headers(num_presenters):
    if num_presenters == 1:
        return ["Date", "Presenter"]
    return ["Date", *[f"Presenter {index + 1}" for index in range(num_presenters)]]


def _migrate_schedule(spreadsheet, worksheet, expected_headers):
    current_headers = worksheet.row_values(1)
    supported_headers = (
        ["Date", "Presenter"],
        ["Date", "Presenter 1", "Presenter 2"],
    )
    if current_headers not in supported_headers:
        raise ValueError(
            f"Schedule headers are {current_headers}; expected {expected_headers}"
        )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
    backup_title = f"Schedule Backup {stamp}"
    spreadsheet.duplicate_sheet(
        source_sheet_id=worksheet.id,
        new_sheet_name=backup_title,
    )

    current_values = worksheet.get_all_values()
    migrated = [expected_headers]
    for row in current_values[1:]:
        padded = row + [""] * (3 - len(row))
        if expected_headers == ["Date", "Presenter 1", "Presenter 2"]:
            migrated.append([padded[0], padded[1] or "EMPTY", "EMPTY"])
        else:
            first = padded[1].strip()
            second = padded[2].strip()
            presenter = first if first not in ("", "EMPTY") else second
            migrated.append([padded[0], presenter or "EMPTY"])

    worksheet.clear()
    worksheet.update(values=migrated, range_name="A1")
    return backup_title


def initialize_google_resources(
    group_config,
    values,
    service_account,
    allow_schedule_migration=False,
):
    """Validate access, create Sheet tabs, and optionally migrate presenter columns."""
    try:
        import gspread
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise RuntimeError("Google API dependencies are unavailable") from exc

    service_account = validate_service_account(service_account)
    values = normalize_resource_values(values)
    credentials = Credentials.from_service_account_info(
        service_account, scopes=SCOPES
    )
    spreadsheet = gspread.authorize(credentials).open_by_key(
        values["spreadsheet_id"]
    )
    messages = [f"Verified Google Sheet: {spreadsheet.title}"]

    drive = build("drive", "v3", credentials=credentials)
    resources = (
        (
            "materials folder",
            values["folder_id"],
            "application/vnd.google-apps.folder",
            "canAddChildren",
        ),
        (
            "slides folder",
            values["slides_folder_id"],
            "application/vnd.google-apps.folder",
            "canAddChildren",
        ),
        (
            "slides template",
            values["slides_template_id"],
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
        messages.append(f"Verified {label}: {metadata['name']}")

    slides = build("slides", "v1", credentials=credentials)
    presentation = (
        slides.presentations()
        .get(presentationId=values["slides_template_id"])
        .execute()
    )
    required_placeholders = required_slide_placeholders(
        group_config["num_presenters"]
    )
    template_text = _presentation_text(presentation)
    missing_placeholders = sorted(
        placeholder
        for placeholder in required_placeholders
        if placeholder not in template_text
    )
    if missing_placeholders:
        raise ValueError(
            "Slides template is missing placeholders: "
            + ", ".join(missing_placeholders)
        )
    messages.append("Verified Slides template placeholders")

    expected = {
        "Schedule": _schedule_headers(group_config["num_presenters"]),
        **SHEET_HEADERS,
    }
    existing = {worksheet.title: worksheet for worksheet in spreadsheet.worksheets()}
    for title, expected_headers in expected.items():
        worksheet = existing.get(title)
        if worksheet is None:
            worksheet = spreadsheet.add_worksheet(title=title, rows=100, cols=8)
            worksheet.update(values=[expected_headers], range_name="A1")
            messages.append(f"Created {title} tab")
            continue

        current_headers = worksheet.row_values(1)
        if not current_headers:
            worksheet.update(values=[expected_headers], range_name="A1")
            messages.append(f"Added headers to {title} tab")
        elif current_headers == expected_headers:
            messages.append(f"Verified {title} tab")
        elif title == "Schedule" and allow_schedule_migration:
            backup_title = _migrate_schedule(
                spreadsheet, worksheet, expected_headers
            )
            messages.append(f"Migrated Schedule tab; backup: {backup_title}")
        else:
            raise ValueError(
                f"{title} headers are {current_headers}; expected {expected_headers}"
            )

    return values, messages
