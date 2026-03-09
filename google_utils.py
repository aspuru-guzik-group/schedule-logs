import streamlit as st
import datetime as dt
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaInMemoryUpload
from email.mime.text import MIMEText
import smtplib
import time
import json

from funcs import encrypt_name, decrypt_name

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/presentations",
    "https://www.googleapis.com/auth/spreadsheets",
]

###############################################################################
# Google Sheets & Drive Utilities
###############################################################################


def get_gspread_client():
    service_account_info = dict(st.secrets["gcp_service_account"])
    credentials = Credentials.from_service_account_info(
        service_account_info, scopes=SCOPES
    )
    return gspread.authorize(credentials)


def get_sheet(sheet_name, group_slug):
    client = get_gspread_client()
    spreadsheet_id = st.secrets[group_slug]["spreadsheet_id"]
    return client.open_by_key(spreadsheet_id).worksheet(sheet_name)


def get_schedule_df(group_slug):
    ws = get_sheet("Schedule", group_slug)
    import pandas as pd

    data = ws.get_all_records()
    df = pd.DataFrame(data)
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.date
    return df


def save_schedule_df(df, group_slug):
    ws = get_sheet("Schedule", group_slug)
    ws.clear()
    ws.update([df.columns.values.tolist()] + df.astype(str).values.tolist())


def get_participants_list(group_slug):
    ws = get_sheet("Participants", group_slug)
    data = ws.get_all_records()
    return [
        {"Name": row.get("Name"), "Email": row.get("Email", "")}
        for row in data
        if row.get("Name")
    ]


def save_participants_list(participants, group_slug):
    ws = get_sheet("Participants", group_slug)
    data = [["Name", "Email"]] + [
        [p["Name"], p.get("Email", "")] for p in participants
    ]
    ws.clear()
    ws.update(data)


def get_drive_service():
    service_account_info = dict(st.secrets["gcp_service_account"])
    credentials = Credentials.from_service_account_info(
        service_account_info, scopes=SCOPES
    )
    return build("drive", "v3", credentials=credentials)


def upload_file_to_drive(file_name, file_bytes, mime_type, parent_folder_id=None):
    drive_service = get_drive_service()
    media = MediaInMemoryUpload(file_bytes, mimetype=mime_type)
    file_metadata = {"name": file_name}
    if parent_folder_id:
        file_metadata["parents"] = [parent_folder_id]
    uploaded_file = (
        drive_service.files()
        .create(body=file_metadata, media_body=media, fields="id, webViewLink")
        .execute()
    )
    return uploaded_file.get("id"), uploaded_file.get("webViewLink")


def add_material(date_str, title, description, pdf_name, pdf_link, group_slug):
    ws = get_sheet("Materials", group_slug)
    new_row = [date_str, title, description, pdf_name, pdf_link]
    ws.append_row(new_row)


def delete_material_row(row_index, group_slug):
    ws = get_sheet("Materials", group_slug)
    ws.delete_rows(row_index)


###############################################################################
# Slides Utilities
###############################################################################


def get_slides_service():
    credentials = Credentials.from_service_account_info(
        dict(st.secrets["gcp_service_account"]), scopes=SCOPES
    )
    return build("slides", "v1", credentials=credentials)


def generate_presentation(date, presenters, template_id, folder_id, meeting_title):
    """Generate a presentation from template.

    Args:
        date: date string in YYYY-MM-DD format
        presenters: list of presenter names (1 or 2)
        template_id: Google Slides template file ID
        folder_id: destination folder ID
        meeting_title: title for the presentation
    """
    drive_service = get_drive_service()
    slides_service = get_slides_service()

    copy_body = {"name": f"{date} {meeting_title}"}
    copied_file = (
        drive_service.files().copy(fileId=template_id, body=copy_body).execute()
    )
    presentation_id = copied_file.get("id")

    if folder_id:
        file = (
            drive_service.files()
            .get(fileId=presentation_id, fields="parents")
            .execute()
        )
        previous_parents = ",".join(file.get("parents"))
        drive_service.files().update(
            fileId=presentation_id,
            addParents=folder_id,
            removeParents=previous_parents,
            fields="id, parents",
        ).execute()

    permission_body = {"type": "anyone", "role": "writer"}
    drive_service.permissions().create(
        fileId=presentation_id, body=permission_body
    ).execute()

    requests = [
        {
            "replaceAllText": {
                "containsText": {"text": "{{DATE}}", "matchCase": True},
                "replaceText": datetime.strptime(date, "%Y-%m-%d").strftime(
                    "%b %d %Y"
                ),
            }
        },
    ]

    if len(presenters) == 1:
        requests.append(
            {
                "replaceAllText": {
                    "containsText": {"text": "{{PRESENTER}}", "matchCase": True},
                    "replaceText": presenters[0],
                }
            }
        )
    else:
        for i, presenter in enumerate(presenters):
            requests.append(
                {
                    "replaceAllText": {
                        "containsText": {
                            "text": "{{" + f"PRESENTER{i+1}" + "}}",
                            "matchCase": True,
                        },
                        "replaceText": presenter,
                    }
                }
            )

    body = {"requests": requests}
    slides_service.presentations().batchUpdate(
        presentationId=presentation_id, body=body
    ).execute()

    presentation_url = f"https://docs.google.com/presentation/d/{presentation_id}/edit"
    return presentation_id, presentation_url


def get_all_slides(group_slug):
    try:
        ws = get_sheet("Slides", group_slug)
        records = ws.get_all_records()
        return records
    except Exception:
        return []


def find_slide(date_str, group_slug):
    slides_data = get_all_slides(group_slug)
    for slide in slides_data:
        if slide.get("Date") == date_str:
            return slide
    return None


def add_slide_entry(date_str, presentation_id, presentation_link, group_slug):
    try:
        ws = get_sheet("Slides", group_slug)
        new_row = [date_str, presentation_id, presentation_link]
        ws.append_row(new_row)
    except Exception as e:
        st.error(f"Error adding slide entry: {e}")


###############################################################################
# Admin Settings (stored in group's Google Sheet "Settings" tab)
###############################################################################


def get_group_settings(group_slug):
    """Get admin-configurable settings. Sheet overrides take precedence over secrets.toml."""
    group_secrets = st.secrets.get(group_slug, {})
    settings = {
        "sender_email": group_secrets.get("sender_email", ""),
        "smtp_password": group_secrets.get("smtp_password", ""),
        "smtp_server": group_secrets.get("smtp_server", ""),
        "smtp_port": int(group_secrets.get("smtp_port", 587)),
        "organizer_name": group_secrets.get("organizer_name", ""),
        "folder_id": group_secrets.get("folder_id", ""),
        "slides_folder_id": group_secrets.get("slides_folder_id", ""),
        "slides_template_id": group_secrets.get("slides_template_id", ""),
        "zoom_link": group_secrets.get("zoom_link", ""),
        "encryption_key": group_secrets.get("encryption_key", ""),
    }
    try:
        ws = get_sheet("Settings", group_slug)
        records = ws.get_all_records()
        overrides = {str(r["Key"]): str(r["Value"]) for r in records if r.get("Key")}
        for key in [
            "sender_email",
            "smtp_server",
            "organizer_name",
            "folder_id",
            "slides_folder_id",
            "slides_template_id",
            "zoom_link",
        ]:
            if key in overrides and overrides[key]:
                settings[key] = overrides[key]
        if "smtp_port" in overrides and overrides["smtp_port"]:
            settings["smtp_port"] = int(overrides["smtp_port"])
        if "smtp_password" in overrides and overrides["smtp_password"]:
            try:
                settings["smtp_password"] = decrypt_name(
                    overrides["smtp_password"], group_slug
                )
            except Exception:
                pass  # Use default from secrets
        if "encryption_key" in overrides and overrides["encryption_key"]:
            settings["encryption_key"] = overrides["encryption_key"]
    except Exception:
        pass  # Settings sheet doesn't exist yet, use defaults
    return settings


def save_group_settings(group_slug, settings_dict):
    """Save admin settings to the Settings sheet. SMTP password is encrypted."""
    try:
        ws = get_sheet("Settings", group_slug)
    except gspread.exceptions.WorksheetNotFound:
        client = get_gspread_client()
        spreadsheet_id = st.secrets[group_slug]["spreadsheet_id"]
        spreadsheet = client.open_by_key(spreadsheet_id)
        ws = spreadsheet.add_worksheet(title="Settings", rows=20, cols=2)

    data = [["Key", "Value"]]
    for key, value in settings_dict.items():
        if key == "smtp_password" and value:
            value = encrypt_name(value, group_slug)
        data.append([key, str(value)])
    ws.clear()
    ws.update(data)


###############################################################################
# GCP Service Account Management (stored in group's "GCPConfig" sheet)
###############################################################################


def get_gcp_config(group_slug):
    """Get GCP service account config from Sheet override, falling back to secrets.toml."""
    try:
        ws = get_sheet("GCPConfig", group_slug)
        records = ws.get_all_records()
        config = {str(r["Key"]): str(r["Value"]) for r in records if r.get("Key")}
        if config:
            return config
    except Exception:
        pass
    return None


def save_gcp_config(group_slug, gcp_json_str):
    """Save GCP service account JSON to the GCPConfig sheet (encrypted key fields)."""
    try:
        ws = get_sheet("GCPConfig", group_slug)
    except gspread.exceptions.WorksheetNotFound:
        client = get_gspread_client()
        spreadsheet_id = st.secrets[group_slug]["spreadsheet_id"]
        spreadsheet = client.open_by_key(spreadsheet_id)
        ws = spreadsheet.add_worksheet(title="GCPConfig", rows=20, cols=2)

    try:
        gcp_data = json.loads(gcp_json_str)
    except json.JSONDecodeError:
        raise ValueError("Invalid JSON for GCP service account")

    data = [["Key", "Value"]]
    for key, value in gcp_data.items():
        # Encrypt the private key
        if key == "private_key":
            value = encrypt_name(str(value), group_slug)
        data.append([key, str(value)])
    ws.clear()
    ws.update(data)


###############################################################################
# SMTP / Email Utilities
###############################################################################


def get_smtp_connection(group_slug):
    settings = get_group_settings(group_slug)
    server = smtplib.SMTP(settings["smtp_server"], settings["smtp_port"])
    server.starttls()
    server.login(settings["sender_email"], settings["smtp_password"])
    return server


def send_email_via_smtp(smtp_conn, sender, to, subject, message_text):
    message = MIMEText(message_text, "html")
    message["To"] = to
    message["From"] = sender
    message["Subject"] = subject
    smtp_conn.sendmail(sender, to, message.as_string())


@st.dialog("Send Confirmation Emails")
def recipients_dialog(
    pending_options,
    pending_mapping,
    participant_emails,
    app_url,
    organizer,
    sender,
    email_subject,
    group_slug,
    group_name,
):
    selected = st.multiselect(
        "Select recipients to send emails to:",
        options=pending_options,
        default=pending_options,
        key="selected_recipients",
    )
    if st.button("Confirm Selection"):
        confirmations_sent = 0
        error_msgs = []
        try:
            smtp_conn = get_smtp_connection(group_slug)
        except Exception as e:
            st.error(f"Error initializing SMTP connection: {e}")
            return

        for option in selected:
            entry = pending_mapping[option]
            to_email = participant_emails.get(entry["clean_name"], "")
            if not to_email:
                error_msgs.append(f"No email found for {entry['clean_name']}.")
                continue

            encrypted_name = encrypt_name(entry["pending_name"], group_slug)
            confirmation_link = (
                f"{app_url}/?group={group_slug}&confirmation=1"
                f"&date={entry['date']}"
                f"&role={entry['role'].replace(' ', '_')}"
                f"&name={encrypted_name}"
            )
            try:
                formatted_date = dt.datetime.strptime(
                    entry["date"], "%Y-%m-%d"
                ).strftime("%B %d, %Y")
            except Exception:
                formatted_date = entry["date"]

            with open("email_template.txt", "r") as template_file:
                email_template = template_file.read()
            email_message_text = email_template.format(
                name_presenter=entry["clean_name"],
                date=formatted_date,
                confirmation_link=confirmation_link,
                name_organizer=organizer,
                group_name=group_name,
            )
            try:
                send_email_via_smtp(
                    smtp_conn, sender, to_email, email_subject, email_message_text
                )
                confirmations_sent += 1
            except Exception as e:
                error_msgs.append(f"Error sending email to {to_email}: {e}")

        try:
            smtp_conn.quit()
        except Exception:
            pass

        st.success(f"Confirmation emails sent to {confirmations_sent} recipients.")
        if error_msgs:
            st.write("Errors encountered:")
            for err in error_msgs:
                st.write(err)

        with st.spinner("Redirecting to the dashboard..."):
            time.sleep(3)
            st.rerun()


def send_confirmation_emails(group_slug, group_config):
    from config import get_presenter_cols

    df = get_schedule_df(group_slug)
    participants = get_participants_list(group_slug)
    presenter_cols = get_presenter_cols(group_config)

    participant_emails = {}
    for p in participants:
        name = p["Name"].strip()
        email = p.get("Email", "").strip()
        if email:
            participant_emails[name] = email

    pending_entries = []
    for idx, row in df.iterrows():
        meeting_date = row.get("Date")
        meeting_date_str = (
            meeting_date.strftime("%Y-%m-%d")
            if isinstance(meeting_date, dt.date)
            else str(meeting_date)
        )
        for role in presenter_cols:
            cell_val = row.get(role, "")
            if isinstance(cell_val, str) and cell_val.strip().startswith("[P]"):
                pending_entries.append(
                    {
                        "date": meeting_date_str,
                        "role": role,
                        "pending_name": cell_val.strip(),
                        "clean_name": cell_val.replace("[P]", "").strip(),
                    }
                )

    if not pending_entries:
        st.info("No pending confirmation entries found.")
        return

    pending_mapping = {}
    pending_options = []
    for entry in pending_entries:
        to_email = participant_emails.get(entry["clean_name"], "No Email")
        display = f"{entry['clean_name']} ({to_email}) on {entry['date']}"
        pending_options.append(display)
        pending_mapping[display] = entry

    settings = get_group_settings(group_slug)
    sender = settings["sender_email"]
    organizer = settings["organizer_name"]
    app_url = st.secrets.get("app_url", "")
    email_subject = group_config["email_subject"]

    recipients_dialog(
        pending_options,
        pending_mapping,
        participant_emails,
        app_url,
        organizer,
        sender,
        email_subject,
        group_slug,
        group_config["display_name"],
    )
    st.stop()
