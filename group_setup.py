"""Validation and Google resource setup shared by the UI and CLI."""

import json
import re
from datetime import datetime, timezone


SCOPES = (
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/presentations",
    "https://www.googleapis.com/auth/spreadsheets",
)
DEFAULT_SLIDES_TEMPLATE_ID = "1XE_EB95lL4YwN1E7J6BgXpGzkTSpyTV021Fexqns4dw"
DEFAULT_SLIDES_TEMPLATE_URL = (
    "https://docs.google.com/presentation/d/"
    f"{DEFAULT_SLIDES_TEMPLATE_ID}/edit"
)
FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
SPREADSHEET_MIME_TYPE = "application/vnd.google-apps.spreadsheet"
PRESENTATION_MIME_TYPE = "application/vnd.google-apps.presentation"
MANAGED_PROPERTY_GROUP = "matterScheduleGroup"
MANAGED_PROPERTY_ROLE = "matterScheduleRole"
CLOUD_KEY_BEGIN_MARKER = "---BEGIN JSON---"
CLOUD_KEY_END_MARKER = "---END JSON---"
SHARED_DRIVE_REQUIRED_MESSAGE = (
    "Google service accounts have no Drive storage. Use a folder inside a "
    "Shared Drive and grant the service account Content manager access."
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
        if (
            isinstance(value, str)
            and CLOUD_KEY_BEGIN_MARKER in value
            and CLOUD_KEY_END_MARKER in value
        ):
            value = value.split(CLOUD_KEY_BEGIN_MARKER, 1)[1].split(
                CLOUD_KEY_END_MARKER, 1
            )[0]
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


def missing_slide_placeholders(template_text, num_presenters):
    """Return missing tokens, accepting the two-presenter deck for one speaker."""
    required = required_slide_placeholders(num_presenters)
    if (
        num_presenters == 1
        and "{{PRESENTER}}" not in template_text
        and "{{PRESENTER1}}" in template_text
    ):
        required.remove("{{PRESENTER}}")
    return sorted(token for token in required if token not in template_text)


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


def _headers_match_ignoring_whitespace(current_headers, expected_headers):
    return [header.strip() for header in current_headers] == expected_headers


def should_migrate_schedule(
    initial_setup, presenter_mode_changed, migration_confirmed
):
    """Allow supported layouts to migrate automatically during initial setup."""
    return initial_setup or (
        presenter_mode_changed and migration_confirmed
    )


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


def _drive_query_literal(value):
    return str(value).replace("\\", "\\\\").replace("'", "\\'")


def _require_shared_drive_folder(metadata, label):
    if not metadata.get("driveId"):
        raise ValueError(
            f"The {label} is in My Drive. {SHARED_DRIVE_REQUIRED_MESSAGE}"
        )


def _get_workspace_folder(
    drive, workspace_folder_id, require_shared_drive=True
):
    workspace = (
        drive.files()
        .get(
            fileId=workspace_folder_id,
            fields=(
                "id,name,mimeType,trashed,driveId,"
                "capabilities(canAddChildren)"
            ),
            supportsAllDrives=True,
        )
        .execute()
    )
    if workspace.get("trashed"):
        raise ValueError("The workspace folder is in the trash")
    if workspace.get("mimeType") != FOLDER_MIME_TYPE:
        raise ValueError("The workspace location must be a Google Drive folder")
    if require_shared_drive:
        _require_shared_drive_folder(workspace, "workspace folder")
    if not workspace.get("capabilities", {}).get("canAddChildren"):
        raise ValueError(
            "The service account needs Content manager access to the "
            f"workspace folder: {workspace.get('name', workspace_folder_id)}"
        )
    return workspace


def _find_managed_resource(drive, parent_id, group_slug, role, drive_id=None):
    query = (
        f"'{_drive_query_literal(parent_id)}' in parents and trashed = false and "
        "properties has { key='"
        f"{MANAGED_PROPERTY_GROUP}' and value='"
        f"{_drive_query_literal(group_slug)}' }} and properties has {{ key='"
        f"{MANAGED_PROPERTY_ROLE}' and value='{_drive_query_literal(role)}' }}"
    )
    list_args = {
        "q": query,
        "fields": "files(id,name,mimeType)",
        "spaces": "drive",
        "pageSize": 10,
        "supportsAllDrives": True,
        "includeItemsFromAllDrives": True,
    }
    if drive_id:
        list_args.update({"corpora": "drive", "driveId": drive_id})
    else:
        list_args["corpora"] = "user"
    return drive.files().list(**list_args).execute().get("files", [])


def _get_or_create_managed_resource(
    drive,
    parent_id,
    group_slug,
    role,
    name,
    mime_type,
    drive_id=None,
    copy_source_id=None,
):
    existing = _find_managed_resource(
        drive, parent_id, group_slug, role, drive_id
    )
    for resource in existing:
        if resource.get("mimeType") == mime_type:
            return resource, False

    body = {
        "name": name,
        "parents": [parent_id],
        "properties": {
            MANAGED_PROPERTY_GROUP: group_slug,
            MANAGED_PROPERTY_ROLE: role,
        },
    }
    if copy_source_id:
        request = drive.files().copy(
            fileId=copy_source_id,
            body=body,
            fields="id,name,mimeType",
            supportsAllDrives=True,
        )
    else:
        body["mimeType"] = mime_type
        request = drive.files().create(
            body=body,
            fields="id,name,mimeType",
            supportsAllDrives=True,
        )
    return request.execute(), True


def provision_google_resources(
    group_slug,
    group_config,
    workspace_folder,
    service_account,
    source_template="",
    _drive=None,
    allow_my_drive=False,
):
    """Create or reuse all subgroup resources inside one Drive folder."""
    service_account = validate_service_account(service_account)
    workspace_folder_id = extract_resource_id(workspace_folder, "folder")

    if _drive is None:
        try:
            from google.oauth2.service_account import Credentials
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise RuntimeError("Google API dependencies are unavailable") from exc
        credentials = Credentials.from_service_account_info(
            service_account, scopes=SCOPES
        )
        drive = build("drive", "v3", credentials=credentials)
    else:
        drive = _drive

    workspace = _get_workspace_folder(
        drive,
        workspace_folder_id,
        require_shared_drive=not allow_my_drive,
    )

    source_template_id = (
        extract_resource_id(source_template, "presentation")
        if str(source_template).strip()
        else DEFAULT_SLIDES_TEMPLATE_ID
    )
    source = (
        drive.files()
        .get(
            fileId=source_template_id,
            fields="id,name,mimeType,trashed,capabilities(canCopy)",
            supportsAllDrives=True,
        )
        .execute()
    )
    if source.get("trashed") or source.get("mimeType") != PRESENTATION_MIME_TYPE:
        raise ValueError("The source Slides template is unavailable or invalid")
    if not source.get("capabilities", {}).get("canCopy"):
        raise ValueError("The connected Google account cannot copy the Slides template")

    display_name = group_config["display_name"]
    drive_id = workspace.get("driveId")
    specifications = (
        (
            "folder_id",
            "materials",
            f"{display_name} Materials",
            FOLDER_MIME_TYPE,
            None,
        ),
        (
            "slides_folder_id",
            "generated_slides",
            f"{display_name} Generated Slides",
            FOLDER_MIME_TYPE,
            None,
        ),
        (
            "spreadsheet_id",
            "schedule",
            f"{display_name} Schedule",
            SPREADSHEET_MIME_TYPE,
            None,
        ),
        (
            "slides_template_id",
            "slides_template",
            f"{display_name} Slides Template",
            PRESENTATION_MIME_TYPE,
            source_template_id,
        ),
    )

    values = {"workspace_folder_id": workspace_folder_id}
    messages = [f"Verified workspace folder: {workspace['name']}"]
    for key, role, name, mime_type, copy_source_id in specifications:
        resource, created = _get_or_create_managed_resource(
            drive,
            workspace_folder_id,
            group_slug,
            role,
            name,
            mime_type,
            drive_id=drive_id,
            copy_source_id=copy_source_id,
        )
        values[key] = resource["id"]
        action = "Created" if created else "Reused"
        messages.append(f"{action} {resource['name']}")

    return values, messages


def _ensure_service_account_sheet_access(drive, spreadsheet_id, email):
    permissions = (
        drive.permissions()
        .list(
            fileId=spreadsheet_id,
            fields="permissions(id,emailAddress,role,type)",
            supportsAllDrives=True,
        )
        .execute()
        .get("permissions", [])
    )
    if any(
        permission.get("emailAddress", "").lower() == email.lower()
        and permission.get("role") in ("owner", "writer")
        for permission in permissions
    ):
        return False
    (
        drive.permissions()
        .create(
            fileId=spreadsheet_id,
            body={"type": "user", "role": "writer", "emailAddress": email},
            sendNotificationEmail=False,
            supportsAllDrives=True,
        )
        .execute()
    )
    return True


def provision_google_resources_in_my_drive(
    group_slug,
    group_config,
    service_account,
    source_template="",
    _drive=None,
):
    """Create or reuse a complete subgroup workspace in the lead's My Drive."""
    service_account = validate_service_account(service_account)
    if _drive is None:
        raise ValueError("Connect the subgroup lead's Google Drive account first")

    display_name = group_config["display_name"]
    workspace, created = _get_or_create_managed_resource(
        _drive,
        "root",
        group_slug,
        "workspace",
        f"{display_name} Workspace",
        FOLDER_MIME_TYPE,
    )
    values, messages = provision_google_resources(
        group_slug,
        group_config,
        workspace["id"],
        service_account,
        source_template=source_template,
        _drive=_drive,
        allow_my_drive=True,
    )
    messages.insert(
        0,
        f"{'Created' if created else 'Reused'} {workspace['name']}",
    )
    permission_created = _ensure_service_account_sheet_access(
        _drive,
        values["spreadsheet_id"],
        service_account["client_email"],
    )
    messages.append(
        ("Shared" if permission_created else "Verified access to")
        + " the Schedule Sheet for the app"
    )
    return values, messages


def initialize_google_resources(
    group_config,
    values,
    service_account,
    allow_schedule_migration=False,
    allow_my_drive=False,
    _drive=None,
    _slides=None,
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

    drive = _drive or build("drive", "v3", credentials=credentials)
    resources = (
        (
            "materials folder",
            values["folder_id"],
            FOLDER_MIME_TYPE,
            "canAddChildren",
        ),
        (
            "slides folder",
            values["slides_folder_id"],
            FOLDER_MIME_TYPE,
            "canAddChildren",
        ),
        (
            "slides template",
            values["slides_template_id"],
            PRESENTATION_MIME_TYPE,
            "canCopy",
        ),
    )
    for label, resource_id, expected_mime_type, required_capability in resources:
        metadata = (
            drive.files()
            .get(
                fileId=resource_id,
                fields=(
                    "id,name,mimeType,trashed,driveId,"
                    "capabilities(canAddChildren,canCopy,canEdit)"
                ),
                supportsAllDrives=True,
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
        if label in ("materials folder", "slides folder") and not allow_my_drive:
            _require_shared_drive_folder(metadata, label)
        if not metadata.get("capabilities", {}).get(required_capability):
            raise ValueError(
                f"Google access lacks {required_capability} permission for "
                f"the {label}: {metadata['name']}"
            )
        messages.append(f"Verified {label}: {metadata['name']}")

    slides = _slides or build("slides", "v1", credentials=credentials)
    presentation = (
        slides.presentations()
        .get(presentationId=values["slides_template_id"])
        .execute()
    )
    template_text = _presentation_text(presentation)
    missing_placeholders = missing_slide_placeholders(
        template_text, group_config["num_presenters"]
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
        elif _headers_match_ignoring_whitespace(
            current_headers, expected_headers
        ):
            worksheet.update(values=[expected_headers], range_name="A1")
            messages.append(f"Repaired whitespace in {title} headers")
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
