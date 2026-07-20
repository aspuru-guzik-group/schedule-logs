"""Streamlit admin authentication and self-service group setup UI."""

import secrets

import streamlit as st

import google_utils as gu
import google_drive_oauth
from config import DAY_MAP
from group_setup import (
    DEFAULT_SLIDES_TEMPLATE_URL,
    initialize_google_resources,
    parse_service_account_json,
    provision_google_resources,
    provision_google_resources_in_my_drive,
    should_migrate_schedule,
)
from runtime_config import (
    get_group_runtime_config,
    save_group_runtime_config,
    set_group_admin_password,
    verify_group_admin_password,
)


CLOUD_SHELL_URL = "https://shell.cloud.google.com/?show=terminal"
GOOGLE_DRIVE_URL = "https://drive.google.com/drive/u/0/shared-drives"
GOOGLE_OAUTH_CLIENTS_URL = "https://console.cloud.google.com/auth/clients"
CLOUD_SETUP_COMMAND = (
    "bash <(curl -fsSL https://raw.githubusercontent.com/"
    "aspuru-guzik-group/schedule-logs/main/scripts/create_google_key.sh)"
)


def _admin_session_key(group_slug):
    return f"{group_slug}_admin_authenticated"


def _legacy_admin_password(group_slug):
    return str(st.secrets.get(group_slug, {}).get("admin_password", ""))


def is_admin_authenticated(group_slug):
    return bool(st.session_state.get(_admin_session_key(group_slug)))


def _authenticate(group_slug, password):
    return verify_group_admin_password(
        group_slug,
        password,
        legacy_password=_legacy_admin_password(group_slug),
    )


def render_admin_login(group_slug, container=None, key_prefix="sidebar"):
    container = container or st.sidebar
    session_key = _admin_session_key(group_slug)

    if is_admin_authenticated(group_slug):
        container.success("Admin mode")
        if container.button("Log out", key=f"{key_prefix}_{group_slug}_logout"):
            st.session_state.pop(session_key, None)
            st.rerun()
        return True

    with container.form(f"{key_prefix}_{group_slug}_admin_login"):
        password = st.text_input("Admin password", type="password")
        submitted = st.form_submit_button("Log in")
    if submitted:
        if _authenticate(group_slug, password):
            st.session_state[session_key] = True
            st.rerun()
        container.error("Incorrect admin password")
    return False


def _oauth_redirect_uri():
    return google_drive_oauth.redirect_uri_from_app_url(
        st.secrets.get("app_url", "http://localhost:8501")
    )


def render_google_drive_connection(group_slug):
    """Render the lead-owned Drive connection used for generated files."""
    redirect_uri = _oauth_redirect_uri()
    if not google_drive_oauth.has_oauth_client():
        st.info(
            "One site-wide Google OAuth client is needed once. After this, "
            "subgroup leads only click Connect Google Drive."
        )
        st.link_button(
            "Open Google OAuth clients",
            GOOGLE_OAUTH_CLIENTS_URL,
            width="content",
        )
        st.caption("Create a Web application with this Authorized redirect URI:")
        st.code(redirect_uri, language=None)
        client_file = st.file_uploader(
            "OAuth client JSON",
            type=["json"],
            key=f"{group_slug}_oauth_client_json",
        )
        if st.button(
            "Save OAuth client",
            disabled=client_file is None,
            key=f"{group_slug}_save_oauth_client",
        ):
            try:
                google_drive_oauth.save_oauth_client(
                    client_file.getvalue(), redirect_uri
                )
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.success("Google OAuth client saved")
                st.rerun()
        return False

    connection = google_drive_oauth.get_connection(group_slug)
    connected = google_drive_oauth.has_connection(group_slug)
    if connected:
        account = connection.get("email") or connection.get("display_name")
        st.success(
            "Google Drive connected" + (f" as {account}" if account else "")
        )
    else:
        st.warning(
            "Connect the Google account that owns this subgroup's folders and "
            "Slides template."
        )

    auth_url_key = f"{group_slug}_drive_oauth_url"
    if auth_url_key not in st.session_state:
        try:
            st.session_state[auth_url_key] = (
                google_drive_oauth.create_authorization_url(
                    group_slug, redirect_uri
                )
            )
        except google_drive_oauth.GoogleDriveOAuthError as exc:
            st.error(str(exc))
            return connected

    connect_label = "Reconnect Google Drive" if connected else "Connect Google Drive"
    col_connect, col_disconnect = st.columns([1, 1])
    with col_connect:
        st.link_button(
            connect_label,
            st.session_state[auth_url_key],
            width="content",
        )
    with col_disconnect:
        if connected and st.button(
            "Disconnect",
            key=f"{group_slug}_disconnect_drive",
        ):
            google_drive_oauth.disconnect(group_slug)
            st.session_state.pop(auth_url_key, None)
            st.rerun()
    return connected


def render_setup_checklist(group):
    if group.get("google_drive_oauth_enabled", False):
        st.info(
            "Connect the lead's Google Drive account. The app can create the "
            "subgroup folder, Sheet, folders, and Slides template there."
        )
    else:
        st.info(
            "You only need a Google key and one Shared Drive workspace. "
            "The app creates and connects everything else."
        )


def _render_google_key_inputs(group_slug, current_service_account):
    replacing = not current_service_account
    if current_service_account:
        replacing = st.toggle(
            "Replace Google service account",
            value=False,
            key=f"{group_slug}_replace_service_account",
        )
        if not replacing:
            return None, "", None, False

    st.markdown("#### 1. Google key")
    st.link_button(
        "Open Google Cloud Shell",
        CLOUD_SHELL_URL,
        width="stretch",
    )
    st.code(CLOUD_SETUP_COMMAND, language="bash")
    uploaded_file = st.file_uploader(
        "Upload the generated JSON",
        type=["json"],
        key=f"{group_slug}_quick_key_upload",
    )
    pasted_json = st.text_area(
        "Or paste the generated JSON",
        height=120,
        placeholder='{"type": "service_account", ...}',
        key=f"{group_slug}_quick_key_json",
    )

    parsed = None
    raw_value = uploaded_file.getvalue() if uploaded_file is not None else None
    if raw_value is None and pasted_json.strip():
        raw_value = pasted_json.strip()
    if raw_value:
        try:
            parsed = parse_service_account_json(raw_value)
            st.success("Google key ready")
        except ValueError as exc:
            if uploaded_file is not None or pasted_json.rstrip().endswith("}"):
                st.error(str(exc))

    return uploaded_file, pasted_json, parsed, replacing


def _service_account_from_form(uploaded_file, pasted_json, current_config):
    if uploaded_file is not None:
        return parse_service_account_json(uploaded_file.getvalue())
    if pasted_json.strip():
        return parse_service_account_json(pasted_json.strip())
    existing = current_config.get("gcp_service_account")
    if existing:
        return parse_service_account_json(existing)
    raise ValueError("Upload or paste a Google service-account JSON key")


def render_group_configuration_form(group_slug, group, setup_mode=False):
    runtime = get_group_runtime_config(group_slug)
    setup_draft = runtime.get("setup_draft", {}) if setup_mode else {}
    current = gu.get_group_connection_config(group_slug)
    current.update(runtime)
    if setup_draft:
        current.update(setup_draft)
    current_service_account = current.get("gcp_service_account", {})
    personal_drive_enabled = group.get("google_drive_oauth_enabled", False)
    personal_drive_connected = gu.has_drive_oauth(group_slug)

    if current_service_account.get("client_email"):
        account_label = (
            "Saved setup service account"
            if setup_draft
            else "Current service account"
        )
        st.caption(
            f"{account_label}: `{current_service_account['client_email']}`"
        )

    automatic_setup = False
    setup_method = "Connect existing"
    if setup_mode:
        default_setup_method = setup_draft.get(
            "setup_method", "Create everything"
        )
        if default_setup_method not in ("Create everything", "Connect existing"):
            default_setup_method = "Create everything"
        setup_method = st.segmented_control(
            "Google resources",
            options=["Create everything", "Connect existing"],
            default=default_setup_method,
            selection_mode="single",
            required=True,
            key=f"{group_slug}_setup_method",
        )
        automatic_setup = setup_method == "Create everything"

    (
        uploaded_file,
        pasted_json,
        pending_service_account,
        replacing_service_account,
    ) = _render_google_key_inputs(group_slug, current_service_account)
    if pending_service_account is None and setup_draft:
        pending_service_account = current_service_account
    if automatic_setup and personal_drive_enabled:
        st.markdown("#### 2. Google Drive")
        if personal_drive_connected:
            st.success("The new subgroup workspace will be created in this Drive")
        else:
            st.warning("Connect the lead's Google Drive account above first")
    elif automatic_setup:
        st.markdown("#### 2. Shared Drive workspace")
        st.link_button(
            "Open Shared Drives",
            GOOGLE_DRIVE_URL,
            width="stretch",
        )
        if pending_service_account:
            st.caption("Share the workspace folder with this address:")
            st.code(pending_service_account["client_email"], language=None)
        else:
            st.caption("Paste the Google key above to reveal the sharing address.")
    elif (
        not personal_drive_enabled
        and pending_service_account
        and current.get("workspace_folder_id")
    ):
        st.caption("Share the existing workspace with this address:")
        st.code(pending_service_account["client_email"], language=None)
        st.link_button(
            "Open existing workspace",
            "https://drive.google.com/drive/folders/"
            + str(current["workspace_folder_id"]),
            width="stretch",
        )
    if not automatic_setup and not personal_drive_enabled:
        st.link_button(
            "Open Shared Drives",
            GOOGLE_DRIVE_URL,
            width="content",
        )

    form_key = f"{group_slug}_{'setup' if setup_mode else 'settings'}"
    with st.form(form_key):
        st.markdown("#### Meeting")
        organizer_name = st.text_input(
            "Organizer name",
            value=str(current.get("organizer_name", "")),
        )
        num_presenters = st.segmented_control(
            "Presenters per meeting",
            options=[1, 2],
            default=int(current.get("num_presenters", group["num_presenters"])),
            format_func=lambda value: f"{value} presenter"
            if value == 1
            else f"{value} presenters",
            required=True,
        )
        days = list(DAY_MAP)
        current_meeting_day = str(
            current.get("meeting_day", group["meeting_day"])
        )
        if current_meeting_day not in days:
            current_meeting_day = group["meeting_day"]
        meeting_day = st.selectbox(
            "Meeting day",
            options=days,
            index=days.index(current_meeting_day),
            format_func=str.title,
        )
        presentation_duration = st.number_input(
            "Minutes per presenter",
            min_value=5,
            max_value=180,
            value=int(
                current.get(
                    "presentation_duration", group["presentation_duration"]
                )
            ),
            step=5,
        )
        zoom_link = st.text_input(
            "Zoom link (optional)", value=str(current.get("zoom_link", ""))
        )

        st.markdown("#### Google resources")
        if automatic_setup:
            if personal_drive_enabled:
                workspace_folder = ""
            else:
                workspace_folder = st.text_input(
                    "Workspace folder URL or ID",
                    value=str(current.get("workspace_folder_id", "")),
                )
            source_template = st.text_input(
                "Source Slides template URL or ID (optional)",
                value=str(
                    current.get(
                        "source_template",
                        group.get("default_slides_template_url", ""),
                    )
                ),
                placeholder=DEFAULT_SLIDES_TEMPLATE_URL,
                help="Leave blank to copy the Matter Lab ML template.",
            )
            spreadsheet_id = ""
            folder_id = ""
            slides_folder_id = ""
            slides_template_id = ""
        else:
            workspace_folder = ""
            source_template = ""
            spreadsheet_id = st.text_input(
                "Google Sheet URL or ID",
                value=str(current.get("spreadsheet_id", "")),
            )
            folder_id = st.text_input(
                "Materials folder URL or ID",
                value=str(current.get("folder_id", "")),
                help=(
                    "The connected lead account must be able to add files here."
                    if personal_drive_enabled
                    else "The folder must be inside Shared drives, not My Drive."
                ),
            )
            slides_folder_id = st.text_input(
                "Slides folder URL or ID",
                value=str(current.get("slides_folder_id", "")),
                help=(
                    "The connected lead account must be able to add files here."
                    if personal_drive_enabled
                    else "The folder must be inside Shared drives, not My Drive."
                ),
            )
            slides_template_id = st.text_input(
                "Slides template URL or ID",
                value=str(
                    current.get(
                        "slides_template_id",
                        group.get("default_slides_template_url", ""),
                    )
                ),
            )
        presenter_change = num_presenters != group["num_presenters"]
        migration_confirmed = True
        if not setup_mode:
            migration_confirmed = st.checkbox(
                "Back up and migrate the Schedule tab if presenter columns change",
                value=False,
            )

        submit_label = (
            "Create and connect" if automatic_setup else "Validate and save"
        )
        submitted = st.form_submit_button(submit_label, type="primary")

    if not submitted:
        return False

    try:
        if (
            replacing_service_account
            and uploaded_file is None
            and not pasted_json.strip()
        ):
            raise ValueError("Upload or paste the new Google key")
        service_account = _service_account_from_form(
            uploaded_file, pasted_json, current
        )
        if setup_mode:
            draft = {
                "setup_method": setup_method,
                "organizer_name": organizer_name.strip(),
                "zoom_link": zoom_link.strip(),
                "num_presenters": int(num_presenters),
                "meeting_day": meeting_day,
                "presentation_duration": int(presentation_duration),
                "workspace_folder_id": workspace_folder,
                "source_template": source_template,
                "spreadsheet_id": spreadsheet_id,
                "folder_id": folder_id,
                "slides_folder_id": slides_folder_id,
                "slides_template_id": slides_template_id,
                "gcp_service_account": service_account,
            }
            save_group_runtime_config(group_slug, {"setup_draft": draft})
        if not organizer_name.strip():
            raise ValueError("Organizer name is required")
        if presenter_change and not migration_confirmed:
            raise ValueError("Confirm the Schedule tab backup and migration")
        updated_group = {
            **group,
            "num_presenters": int(num_presenters),
            "meeting_day": meeting_day,
            "presentation_duration": int(presentation_duration),
        }
        with st.spinner("Validating Google access and preparing the Sheet..."):
            provision_messages = []
            if automatic_setup:
                if personal_drive_enabled:
                    if not personal_drive_connected:
                        raise ValueError(
                            "Connect the subgroup lead's Google Drive account first"
                        )
                    drive_service = gu.get_drive_service(group_slug)
                    values, provision_messages = (
                        provision_google_resources_in_my_drive(
                            group_slug,
                            updated_group,
                            service_account,
                            source_template=source_template,
                            _drive=drive_service,
                        )
                    )
                else:
                    values, provision_messages = provision_google_resources(
                        group_slug,
                        updated_group,
                        workspace_folder,
                        service_account,
                        source_template=source_template,
                    )
            else:
                values = {
                    "spreadsheet_id": spreadsheet_id,
                    "folder_id": folder_id,
                    "slides_folder_id": slides_folder_id,
                    "slides_template_id": slides_template_id,
                }
            drive_service = None
            slides_service = None
            if personal_drive_enabled:
                if not personal_drive_connected:
                    raise ValueError(
                        "Connect the subgroup lead's Google Drive account first"
                    )
                drive_service = gu.get_drive_service(group_slug)
                slides_service = gu.get_slides_service(group_slug)
            normalized, messages = initialize_google_resources(
                updated_group,
                values,
                service_account,
                allow_schedule_migration=should_migrate_schedule(
                    setup_mode,
                    presenter_change,
                    migration_confirmed,
                ),
                allow_my_drive=personal_drive_enabled,
                _drive=drive_service,
                _slides=slides_service,
            )
            updates = {
                **normalized,
                "gcp_service_account": service_account,
                "organizer_name": organizer_name.strip(),
                "zoom_link": zoom_link.strip(),
                "num_presenters": int(num_presenters),
                "meeting_day": meeting_day,
                "presentation_duration": int(presentation_duration),
                "encryption_key": current.get("encryption_key")
                or secrets.token_urlsafe(32),
                "setup_draft": {},
            }
            save_group_runtime_config(group_slug, updates)
    except Exception as exc:
        st.error(f"Setup validation failed: {exc}")
        return False

    all_messages = [*provision_messages, *messages]
    st.success(
        "Configuration saved. "
        + " ".join(f"{item}." for item in all_messages)
    )
    st.cache_data.clear()
    return True


def render_change_password(group_slug):
    with st.form(f"{group_slug}_change_admin_password"):
        new_password = st.text_input("New admin password", type="password")
        confirmation = st.text_input("Confirm new password", type="password")
        submitted = st.form_submit_button("Change password")

    if not submitted:
        return False
    if len(new_password) < 8:
        st.error("Admin password must be at least 8 characters")
        return False
    if new_password != confirmation:
        st.error("Passwords do not match")
        return False

    set_group_admin_password(group_slug, new_password)
    st.success("Admin password changed")
    return True


def render_unconfigured_setup_page(group_slug, group):
    _, center, _ = st.columns([0.4, 2, 0.4])
    with center:
        st.image("logo.png", width=90)
        st.title(group["display_name"])
        render_setup_checklist(group)
        st.write("---")
        st.subheader("Admin access")
        if not render_admin_login(
            group_slug, container=st, key_prefix="setup"
        ):
            if st.button("Back to schedules", width="stretch"):
                st.query_params.clear()
                st.rerun()
            return

        st.write("---")
        if group.get("google_drive_oauth_enabled", False):
            st.subheader("Google Drive account")
            render_google_drive_connection(group_slug)
            st.write("---")
        st.subheader("Configuration")
        if render_group_configuration_form(
            group_slug, group, setup_mode=True
        ):
            st.rerun()

        with st.expander("Admin password"):
            render_change_password(group_slug)

        if st.button("Back to schedules", width="stretch"):
            st.query_params.clear()
            st.rerun()
