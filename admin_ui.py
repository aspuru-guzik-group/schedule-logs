"""Streamlit admin authentication and self-service group setup UI."""

import secrets

import streamlit as st

import google_utils as gu
from config import DAY_MAP
from group_setup import initialize_google_resources, parse_service_account_json
from runtime_config import (
    get_group_runtime_config,
    save_group_runtime_config,
    set_group_admin_password,
    verify_group_admin_password,
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


def render_setup_checklist():
    st.subheader("Setup checklist")
    st.markdown(
        """
1. Create a Google Cloud service account and download its JSON key. Enable the
   Google Sheets, Drive, and Slides APIs.
2. Create a blank Google Sheet and share it with the service account's
   `client_email` as **Editor**. The required tabs are created automatically.
3. Create a Drive folder for materials and another for generated slides. Share
   both as **Editor** with the service account.
4. Create a Google Slides template containing `{{DATE}}`. Use `{{PRESENTER}}`
   in one-presenter mode, or `{{PRESENTER1}}` and `{{PRESENTER2}}` in
   two-presenter mode. Share it as **Viewer** or **Editor**.
5. Upload the JSON key and enter the four Google URLs below. Validation must pass
   before the subgroup becomes available.
"""
    )


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
    current = gu.get_group_connection_config(group_slug)
    current.update(runtime)
    current_service_account = current.get("gcp_service_account", {})

    if current_service_account.get("client_email"):
        st.caption(
            f"Current service account: `{current_service_account['client_email']}`"
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
            default=group["num_presenters"],
            format_func=lambda value: f"{value} presenter"
            if value == 1
            else f"{value} presenters",
            required=True,
        )
        days = list(DAY_MAP)
        meeting_day = st.selectbox(
            "Meeting day",
            options=days,
            index=days.index(group["meeting_day"]),
            format_func=str.title,
        )
        presentation_duration = st.number_input(
            "Minutes per presenter",
            min_value=5,
            max_value=180,
            value=int(group["presentation_duration"]),
            step=5,
        )
        zoom_link = st.text_input(
            "Zoom link (optional)", value=str(current.get("zoom_link", ""))
        )

        st.markdown("#### Google resources")
        spreadsheet_id = st.text_input(
            "Google Sheet URL or ID",
            value=str(current.get("spreadsheet_id", "")),
        )
        folder_id = st.text_input(
            "Materials folder URL or ID",
            value=str(current.get("folder_id", "")),
        )
        slides_folder_id = st.text_input(
            "Slides folder URL or ID",
            value=str(current.get("slides_folder_id", "")),
        )
        slides_template_id = st.text_input(
            "Slides template URL or ID",
            value=str(current.get("slides_template_id", "")),
        )
        uploaded_file = st.file_uploader(
            "Service-account JSON key",
            type=["json"],
            help="Upload only when setting up or replacing the service account.",
        )
        pasted_json = st.text_area(
            "Or paste service-account JSON",
            height=120,
            placeholder='{"type": "service_account", ...}',
        )

        presenter_change = num_presenters != group["num_presenters"]
        migration_confirmed = True
        if not setup_mode:
            migration_confirmed = st.checkbox(
                "Back up and migrate the Schedule tab if presenter columns change",
                value=False,
            )

        submitted = st.form_submit_button(
            "Validate and save", type="primary"
        )

    if not submitted:
        return False

    if not organizer_name.strip():
        st.error("Organizer name is required")
        return False
    if presenter_change and not migration_confirmed:
        st.error("Confirm the Schedule tab backup and migration")
        return False

    try:
        service_account = _service_account_from_form(
            uploaded_file, pasted_json, current
        )
        values = {
            "spreadsheet_id": spreadsheet_id,
            "folder_id": folder_id,
            "slides_folder_id": slides_folder_id,
            "slides_template_id": slides_template_id,
        }
        updated_group = {
            **group,
            "num_presenters": int(num_presenters),
            "meeting_day": meeting_day,
            "presentation_duration": int(presentation_duration),
        }
        with st.spinner("Validating Google access and preparing the Sheet..."):
            normalized, messages = initialize_google_resources(
                updated_group,
                values,
                service_account,
                allow_schedule_migration=presenter_change
                and migration_confirmed,
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
            }
            save_group_runtime_config(group_slug, updates)
    except Exception as exc:
        st.error(f"Setup validation failed: {exc}")
        return False

    st.success("Configuration saved. " + " ".join(f"{item}." for item in messages))
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
        render_setup_checklist()
        st.write("---")
        st.subheader("Admin access")
        if not render_admin_login(
            group_slug, container=st, key_prefix="setup"
        ):
            if st.button("Back to schedules", use_container_width=True):
                st.query_params.clear()
                st.rerun()
            return

        st.write("---")
        st.subheader("Configuration")
        if render_group_configuration_form(
            group_slug, group, setup_mode=True
        ):
            st.rerun()

        with st.expander("Admin password"):
            render_change_password(group_slug)

        if st.button("Back to schedules", use_container_width=True):
            st.query_params.clear()
            st.rerun()
