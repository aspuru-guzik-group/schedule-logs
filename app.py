import streamlit as st
import pandas as pd
import datetime
import time

import funcs as fns
import google_utils as gu
import assign_schedule as assign
from config import GROUPS, get_presenter_cols
from auth import require_auth

###############################################
# PAGE CONFIG
###############################################
st.set_page_config(
    page_title="The Matter Lab Meetings",
    page_icon="logo.png",
    initial_sidebar_state="collapsed",
    layout="centered",
)

###############################################
# AUTHENTICATION (Slack)
###############################################
user = require_auth()

st.markdown(
    """
    <style>
    html, body, [class*="css"] { font-size: 15px !important; }
    tbody, th, td { font-size: 10px !important; }
    div[data-testid="stDataFrame"] .row_heading.level0 { display: none }
    div[data-testid="stDataFrame"] thead tr th:first-child { display: none }
    div[data-testid="stDataFrame"] tbody th { display: none }
    </style>
    """,
    unsafe_allow_html=True,
)

###############################################
# CACHED LOADERS
###############################################


@st.cache_data(ttl=300)
def load_schedule_data(group_slug):
    return gu.get_schedule_df(group_slug)


@st.cache_data(ttl=300)
def load_participants_data(group_slug):
    return gu.get_participants_list(group_slug)


@st.cache_data(ttl=300)
def load_materials_data(group_slug):
    ws = gu.get_sheet("Materials", group_slug)
    return ws.get_all_records()


@st.cache_data(ttl=300)
def load_slides_data(selected_date_str, group_slug):
    return gu.find_slide(selected_date_str, group_slug)


def refresh_main():
    load_schedule_data.clear()
    load_participants_data.clear()
    st.rerun()


def refresh_detail():
    load_schedule_data.clear()
    load_materials_data.clear()
    st.rerun()


###############################################
# QUERY PARAMS
###############################################
params = st.query_params
group_slug = params.get("group", "")

###############################################
# LANDING PAGE
###############################################
if not group_slug or group_slug not in GROUPS:
    _, center, _ = st.columns([1, 2, 1])
    with center:
        st.image("logo.png", width=120)
        st.markdown("## The Matter Lab Group Meetings")
        st.caption("schedule.matter.toronto.edu")
        st.write("")
        st.markdown("**Select a subgroup meeting:**")
        st.write("")
        for slug, grp in GROUPS.items():
            configured = slug in st.secrets
            label = f"{grp['emoji']}  {grp['display_name']}"
            if not configured:
                label += "  (coming soon)"
            if st.button(
                label,
                use_container_width=True,
                disabled=not configured,
                key=f"group_{slug}",
            ):
                st.query_params["group"] = slug
                st.rerun()
    st.stop()

###############################################
# GROUP PAGE SETUP
###############################################
group = GROUPS[group_slug]

if group_slug not in st.secrets:
    _, center, _ = st.columns([1, 2, 1])
    with center:
        st.image("logo.png", width=100)
        st.write("")
        st.warning(
            f"**{group['emoji']} {group['display_name']}** has not been configured yet.\n\n"
            "The admin for this subgroup needs to create a `secrets/<group>.toml` file "
            "and redeploy. See the README for instructions."
        )
        if st.button("Back to Home", use_container_width=True):
            st.query_params.clear()
            st.rerun()
    st.stop()

group_secrets = st.secrets[group_slug]
presenter_cols = get_presenter_cols(group)

# Read settings (Sheet overrides > secrets.toml)
settings = gu.get_group_settings(group_slug)
FOLDER_ID = settings["folder_id"]
SLIDES_FOLDER_ID = settings["slides_folder_id"]
SLIDES_TEMPLATE_ID = settings["slides_template_id"]
ZOOM_LINK = settings.get("zoom_link", group_secrets.get("zoom_link", ""))

# Header
top_container = st.container()
with top_container:
    col1, col2 = st.columns([1, 6])
    with col1:
        st.image("logo.png", width=60)
    with col2:
        st.title(group["short_name"])

st.write("---")


###############################################
# CONFIRMATION VIEW
###############################################
if "confirmation" in params:
    date_str = params.get("date", "")
    role = params.get("role", "").replace("_", " ")
    encrypted_name = params.get("name", "")
    try:
        pending_name = fns.decrypt_name(encrypted_name, group_slug)
    except Exception:
        st.error("Failed to decode the name parameter.")
        st.stop()

    if not date_str or not role or not pending_name:
        st.error("Missing required parameters.")
        st.stop()

    try:
        meeting_date = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
    except Exception:
        st.error("Invalid date format.")
        st.stop()

    def redirect_to_schedule():
        with st.spinner("Redirecting back to the schedule..."):
            time.sleep(3)
            st.query_params.clear()
            st.query_params["group"] = group_slug
            st.rerun()

    with st.spinner("Loading data. Please wait..."):
        df = gu.get_schedule_df(group_slug)
        row_indices = df.index[df["Date"] == meeting_date].tolist()
        if not row_indices:
            st.error("No meeting scheduled for this date.")
            st.stop()
        row_idx = row_indices[0]

    # Check if form has already been used
    form_valid = False
    for col in presenter_cols:
        if col in df.columns:
            val = df.at[row_idx, col]
            if isinstance(val, str) and val.startswith("[P]"):
                form_valid = True
                break

    if not form_valid:
        st.error(
            "This form has already been used, please contact the organizer "
            "if you need to change your response."
        )
        redirect_to_schedule()

    st.subheader("Schedule form")
    duration = group["presentation_duration"]
    clean_name = " ".join(pending_name.split()[1:])

    if group["num_presenters"] == 1:
        st.write(
            f"Dear **{clean_name}**, you have been randomly scheduled to present "
            f"for {duration} minutes on **{meeting_date.strftime('%B %d, %Y')}**."
        )
    else:
        st.write(
            f"Dear **{clean_name}**, you have been randomly scheduled to present "
            f"for {duration} minutes on **{meeting_date.strftime('%B %d, %Y')}** "
            f"as **{role}**. If you either are unable to present on this date "
            f"**or** would like to have {duration * 2} minutes instead, "
            f"choose the 'Reschedule' option."
        )

    st.write("**Please select one of the options below:**")

    confirm_clicked = st.button("Confirm", key="confirm")
    reschedule_clicked = st.button("Reschedule", key="reschedule")
    dont_want_clicked = st.button("Decline", key="dont_want")

    clicked_option = None
    if confirm_clicked:
        clicked_option = "Confirm"
    elif reschedule_clicked:
        clicked_option = "Reschedule"
    elif dont_want_clicked:
        clicked_option = "Decline"

    if clicked_option:
        st.info(f"You clicked: {clicked_option}")

    response_placeholder = st.empty()

    if clicked_option == "Confirm":
        current_value = df.at[row_idx, role]
        if isinstance(current_value, str) and current_value.startswith("[P]"):
            new_value = current_value.replace("[P]", "").strip()
        else:
            new_value = current_value
        df.at[row_idx, role] = new_value
        gu.save_schedule_df(df, group_slug)
        response_placeholder.success(
            "Thank you, your presentation has been confirmed!"
        )
        redirect_to_schedule()

    elif clicked_option == "Reschedule":
        current_value = df.at[row_idx, role]
        if isinstance(current_value, str) and current_value.startswith("[P]"):
            new_value = current_value.replace("[P]", "[R]")
        else:
            new_value = current_value
        df.at[row_idx, role] = new_value
        gu.save_schedule_df(df, group_slug)
        response_placeholder.success("Please contact us for rescheduling.")
        redirect_to_schedule()

    elif clicked_option == "Decline":
        df.at[row_idx, role] = "EMPTY"
        gu.save_schedule_df(df, group_slug)
        response_placeholder.success("Your response has been recorded.")
        redirect_to_schedule()

###############################################
# DETAIL VIEW
###############################################
elif "date" in params:
    try:
        selected_date_str = params.get("date", "")
        selected_date = datetime.datetime.strptime(
            selected_date_str, "%Y-%m-%d"
        ).date()
    except ValueError:
        st.error("Invalid date in URL. Please go back to the schedule.")
        st.stop()

    st.title(group["meeting_title"])

    try:
        df = load_schedule_data(group_slug)
    except FileNotFoundError:
        st.error("Schedule not found!")
        st.stop()

    df.fillna("", inplace=True)
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df = df[df["Date"].notna()]
        df["Date"] = df["Date"].dt.date
    else:
        st.warning("No 'Date' column found.")
        st.stop()

    day_df = df[df["Date"] == selected_date]
    if day_df.empty:
        st.warning("No entries found for this date.")
        st.stop()

    role_cols = [col for col in presenter_cols if col in day_df.columns]
    ps = []
    for idx, row in day_df.iterrows():
        datestr = datetime.datetime.strptime(selected_date_str, "%Y-%m-%d").strftime(
            "%b %d %Y"
        )
        st.write(f"### Schedule for {datestr}")
        for col in role_cols:
            if row[col]:
                ps.append(row[col])
                st.write(f"##### {col}: {row[col]}")

    existing_slide = load_slides_data(selected_date_str, group_slug)
    st.write("")

    col1, col2 = st.columns([0.2, 1])

    with col1:
        if existing_slide:
            st.link_button("View Slides", existing_slide["Presentation_Link"])
        else:
            if ps and st.button("Make Slides", key=f"main_slides_{idx}"):
                try:
                    from googleapiclient.errors import HttpError

                    drive_service = gu.get_drive_service(group_slug)
                    drive_service.files().get(fileId=SLIDES_TEMPLATE_ID).execute()
                except HttpError as e:
                    st.error(f"Template file not found or access denied: {e}")

                presentation_id, presentation_link = gu.generate_presentation(
                    selected_date_str,
                    ps,
                    SLIDES_TEMPLATE_ID,
                    folder_id=SLIDES_FOLDER_ID,
                    meeting_title=group["meeting_title"],
                    group_slug=group_slug,
                )
                if presentation_id and presentation_link:
                    gu.add_slide_entry(
                        selected_date_str,
                        presentation_id,
                        presentation_link,
                        group_slug,
                    )
                    st.success("Slides generated successfully.")
                    load_slides_data.clear()
                    st.rerun()

    with col2:
        if ZOOM_LINK:
            st.link_button("Join Zoom", ZOOM_LINK)

    # Documents
    st.write("---")
    st.subheader("Documents")

    ws = gu.get_sheet("Materials", group_slug)
    all_records = load_materials_data(group_slug)

    target_rows = []
    for idx_r, record in enumerate(all_records, start=2):
        if str(record.get("Date")) == selected_date_str:
            target_rows.append((idx_r, record))

    if target_rows:
        for indx, (row_idx_r, mat) in enumerate(target_rows):
            st.write(f"##### **{indx+1}. {mat['Title']}**")
            if mat.get("Description"):
                st.write(f"Description: {mat['Description']}")
            if mat.get("PDF_Link"):
                drive_link = mat["PDF_Link"]
                href = f'<a href="{drive_link}" target="_blank">View PDF</a>'
                st.markdown(href, unsafe_allow_html=True)
            if st.button(f"Remove document", key=f"remove_{row_idx_r}"):
                ws.delete_rows(row_idx_r)
                refresh_detail()
                st.success(f"Removed material: {mat['Title']}")
                st.rerun()
    else:
        st.write("No documents yet.")

    with st.expander("Add New Document"):
        new_title = st.text_input("Document Title or Link:")
        new_description = st.text_area("Description (optional):")
        pdf_file = st.file_uploader("Upload a PDF (optional):", type=["pdf"])

        if st.button("Upload"):
            if not new_title.strip():
                st.warning("Please enter a valid document title/link.")
            else:
                pdf_name = ""
                drive_link = ""
                if pdf_file is not None:
                    pdf_bytes = pdf_file.read()
                    pdf_name = pdf_file.name
                    _, drive_link = gu.upload_file_to_drive(
                        pdf_name,
                        pdf_bytes,
                        "application/pdf",
                        parent_folder_id=FOLDER_ID,
                        group_slug=group_slug,
                    )
                gu.add_material(
                    selected_date_str,
                    new_title.strip(),
                    new_description.strip(),
                    pdf_name,
                    drive_link,
                    group_slug,
                )
                refresh_detail()
                st.success("Material added successfully.")
                st.rerun()

    st.write("---")
    if st.button("Back to Schedule"):
        st.query_params.clear()
        st.query_params["group"] = group_slug
        st.rerun()

###############################################
# SCHEDULE VIEW
###############################################
else:
    admin_mode = False
    admin_password = st.sidebar.text_input("Admin password:", type="password")
    pw = group_secrets["admin_password"]
    if admin_password == pw:
        admin_mode = True

    try:
        df_full = load_schedule_data(group_slug)
    except FileNotFoundError:
        st.error("Schedule not found!")
        st.stop()

    df_full.fillna("", inplace=True)
    if "Date" in df_full.columns:
        df_full["Date"] = pd.to_datetime(df_full["Date"], errors="coerce").dt.date
    else:
        st.warning("No 'Date' column found.")
        st.stop()

    st.title("Weekly Schedule :calendar:")

    df = df_full.copy()
    schedule_placeholder = st.container()

    st.markdown(
        """**Status:** ⚫ Accepted — 🔵 Pending confirmation — 🔴 Cancelled"""
    )
    col1, col2 = st.columns([0.3, 1])
    with col1:
        hide_past = st.checkbox("Hide past dates", value=True)
        today = datetime.date.today()
        if hide_past:
            df = df[df["Date"] >= today]
        else:
            df = df_full.copy()

    with col2:
        if st.button("Refresh Data"):
            refresh_main()

    with schedule_placeholder:
        search_name = st.text_input("Search by participant name:")
        role_cols = [c for c in presenter_cols if c in df.columns]

        if search_name.strip():
            mask = False
            for c in role_cols:
                mask = mask | df[c].str.contains(search_name, case=False, na=False)
            df = df[mask]

        if df.empty:
            st.write("No matching rows.")
        else:
            if admin_mode:
                st.info(
                    "You are in admin mode. Feel free to edit and save the schedule."
                )

                edited_df = st.data_editor(
                    df,
                    num_rows="fixed",
                    use_container_width=True,
                    column_config={
                        "Date": st.column_config.DateColumn("Date"),
                        "DetailsLink": st.column_config.LinkColumn(
                            label="Info",
                            help="Click to view details for this date",
                            display_text="See Details",
                        ),
                    },
                    hide_index=True,
                    key="schedule_editor",
                )

                col1, col2, col3, col4 = st.columns([0.2, 0.15, 0.32, 0.33])
                message_placeholder = st.empty()

                with col1:
                    if st.button("Save Changes"):
                        # Normalize blank/lowercase "empty" to "EMPTY"
                        for col in presenter_cols:
                            if col in edited_df.columns:
                                edited_df[col] = edited_df[col].apply(
                                    lambda v: "EMPTY" if str(v).strip().lower() in ("", "empty") else str(v).strip()
                                )
                        updated_df = df_full.copy()
                        if "Date" in edited_df.columns:
                            edited_df["Date"] = pd.to_datetime(
                                edited_df["Date"], errors="coerce"
                            ).dt.date
                        updated_df["Date"] = pd.to_datetime(
                            updated_df["Date"], errors="coerce"
                        ).dt.date
                        for idx, row in edited_df.iterrows():
                            mask = updated_df["Date"] == row["Date"]
                            if not mask.any():
                                updated_df.loc[len(updated_df)] = row
                            else:
                                updated_df.loc[mask, updated_df.columns] = row.values
                        gu.save_schedule_df(updated_df, group_slug)
                        message_placeholder.success("Schedule updated and saved!")

                with col2:
                    if st.button("Add Row"):
                        updated_df = df_full.copy()
                        if not updated_df.empty and "Date" in updated_df.columns:
                            last_date = updated_df["Date"].max()
                        else:
                            last_date = datetime.date.today()
                        next_day = fns.get_next_day_of_week(
                            last_date, group["meeting_day"]
                        )
                        new_row = {}
                        for col in updated_df.columns:
                            if col == "Date":
                                new_row[col] = next_day
                            elif "Presenter" in col:
                                new_row[col] = "EMPTY"
                            else:
                                new_row[col] = ""
                        new_row_df = pd.DataFrame([new_row])
                        updated_df = pd.concat(
                            [updated_df, new_row_df], ignore_index=True
                        )
                        if "Date" in updated_df.columns:
                            updated_df["Date"] = updated_df["Date"].astype(str)
                        gu.save_schedule_df(updated_df, group_slug)
                        refresh_main()
                        message_placeholder.success(
                            f"Added new row for date: {next_day}"
                        )
                        st.rerun()

                with col3:
                    if st.button("Send Confirmation Emails"):
                        gu.send_confirmation_emails(group_slug, group)

                with col4:
                    if st.button("Fill empty slots"):
                        filled_df = assign.fill_empty_slots(
                            group_slug, group, seed=0
                        )
                        gu.save_schedule_df(filled_df, group_slug)
                        refresh_main()
                        st.rerun()

                # Delete Row
                if not df.empty:
                    if group["num_presenters"] == 1:
                        row_dict = {
                            f"Date: {row['Date']}, Presenter: {row.get('Presenter', '')}": idx
                            for idx, row in df.iterrows()
                        }
                    else:
                        row_dict = {
                            f"Date: {row['Date']}, Presenters: "
                            f"{row.get('Presenter 1', '')} & {row.get('Presenter 2', '')}": idx
                            for idx, row in df.iterrows()
                        }

                    col_del1, col_del2 = st.columns(
                        [1, 0.2], vertical_alignment="bottom"
                    )

                    with col_del1:
                        selected_label = st.selectbox(
                            "Select a row to delete:",
                            options=list(row_dict.keys()),
                        )

                    with col_del2:
                        if st.button("Delete"):
                            selected_index = row_dict[selected_label]
                            updated_df = df_full.copy()
                            updated_df = updated_df.drop(index=selected_index)
                            if "Date" in updated_df.columns:
                                updated_df["Date"] = updated_df["Date"].astype(str)
                            gu.save_schedule_df(updated_df, group_slug)
                            refresh_main()
                            message_placeholder.success(
                                f"Deleted row at index {selected_index}."
                            )
                            st.rerun()

            else:
                # READ-ONLY view
                df["DetailsLink"] = df["Date"].apply(
                    lambda d: f"?group={group_slug}&date={d.strftime('%Y-%m-%d')}"
                )

                style_cols = [col for col in presenter_cols if col in df.columns]
                styled_df = df.style.map(
                    fns.highlight_empty, subset=style_cols
                ).map(fns.highlight_random, subset=style_cols)

                st.dataframe(
                    styled_df,
                    column_config={
                        "Date": st.column_config.DateColumn("Date"),
                        "DetailsLink": st.column_config.LinkColumn(
                            label="Info",
                            help="Click to view details for this date",
                            display_text="See Details",
                        ),
                    },
                    hide_index=True,
                    use_container_width=True,
                )

    # ----- PARTICIPANT SCORES -----
    st.write("---")
    st.subheader("Participants")

    try:
        valid_participants = load_participants_data(group_slug)
    except Exception as e:
        st.error(f"Error loading participants: {e}")
        st.stop()

    participants_usage = {
        p["Name"]: {"presenter_count": 0} for p in valid_participants
    }

    today = datetime.date.today()
    five_months_ago = today - datetime.timedelta(days=150)

    for col in presenter_cols:
        if col in df_full.columns:
            for idx, row in df_full.iterrows():
                presentation_date = row["Date"]
                person = str(row[col]).strip()
                if not person or person not in participants_usage:
                    continue
                if presentation_date >= five_months_ago:
                    participants_usage[person]["presenter_count"] += 1

    records = []
    for participant in valid_participants:
        name = participant["Name"]
        usage_dict = participants_usage.get(name, {"presenter_count": 0})
        weighted_usage = usage_dict["presenter_count"] * 4
        records.append(
            {
                "Name": name,
                "Presentations": usage_dict["presenter_count"],
                "Points": weighted_usage,
            }
        )

    df_scores = pd.DataFrame(records)

    if not df_scores.empty:
        min_usage = df_scores["Points"].min()
        max_usage = df_scores["Points"].max()

        def calc_normalized_score(x):
            if max_usage == min_usage:
                return 0.0
            return 2 * ((x - min_usage) / (max_usage - min_usage)) - 1

        df_scores["Score"] = df_scores["Points"].apply(calc_normalized_score).round(2)

        def color_for_score(val):
            if val < -0.5:
                return "background-color: red"
            elif val > 0.5:
                return "background-color: green"
            else:
                return "background-color: yellow"

        df_scores.sort_values("Score", ascending=True, inplace=True)

        if search_name.strip():
            df_scores = df_scores[
                df_scores["Name"].str.contains(search_name, case=False, na=False)
            ]

        df_scores.drop(columns=["Points", "Presentations"], inplace=True)

        styled_scores = df_scores.style.map(
            color_for_score, subset=["Score"]
        ).format({"Score": "{:.2f}"})

        if not df_scores.empty:
            column_config = {
                "Name": st.column_config.TextColumn("Name", width="large"),
                "Score": st.column_config.NumberColumn(
                    "Score (over past 5 months)", width="medium"
                ),
            }
            st.dataframe(
                styled_scores,
                use_container_width=True,
                column_config=column_config,
            )
        else:
            st.info("No matching participants.")
    else:
        st.info("No participants found in the schedule.")

    # ----- ADMIN SECTIONS -----
    if admin_mode:
        # Manage Participants
        st.subheader("Manage Participants")
        try:
            participants = load_participants_data(group_slug)
        except Exception as e:
            st.error(f"Error loading participants: {e}")
            st.stop()

        col1, col2 = st.columns([1, 0.2], vertical_alignment="bottom")
        pmessage_placeholder = st.empty()
        with col1:
            new_participant = st.text_input(
                "Add participant:", key="add_input", placeholder="Name"
            )
            new_participant_email = st.text_input(
                "Email:",
                key="email_input",
                placeholder="Email",
                label_visibility="collapsed",
            )
        with col2:
            if st.button("Add"):
                if new_participant and new_participant_email:
                    if not any(p["Name"] == new_participant for p in participants):
                        participants.append(
                            {
                                "Name": new_participant,
                                "Email": new_participant_email,
                            }
                        )
                        gu.save_participants_list(participants, group_slug)
                        refresh_main()
                        st.rerun()
                    else:
                        pmessage_placeholder.warning(
                            f"{new_participant} is already in the list."
                        )
                else:
                    pmessage_placeholder.warning(
                        "Please enter a name and email to add."
                    )

        if participants:
            col1, col2 = st.columns([1, 0.2], vertical_alignment="bottom")
            participant_names = [p["Name"] for p in participants]
            with col1:
                remove_participant = st.selectbox(
                    "Remove participant:",
                    options=participant_names,
                    key="remove_select",
                )
            with col2:
                if st.button("Remove"):
                    participants = [
                        p
                        for p in participants
                        if p["Name"] != remove_participant
                    ]
                    gu.save_participants_list(participants, group_slug)
                    refresh_main()
                    st.rerun()
        else:
            st.info("No participants available to remove.")

        # ----- INTEGRATION SETTINGS -----
        st.write("---")
        st.subheader("Admin Settings")

        with st.expander("General"):
            current_settings = gu.get_group_settings(group_slug)
            new_organizer = st.text_input(
                "Organizer Name:",
                value=current_settings["organizer_name"],
                key="organizer_input",
            )
            if st.button("Save General Settings"):
                current_settings["organizer_name"] = new_organizer
                gu.save_group_settings(group_slug, current_settings)
                st.success("Settings saved!")

        with st.expander("Google Drive / Slides Configuration"):
            new_folder_id = st.text_input(
                "Drive Folder ID:",
                value=current_settings["folder_id"],
                key="folder_id_input",
            )
            new_slides_folder = st.text_input(
                "Slides Folder ID:",
                value=current_settings["slides_folder_id"],
                key="slides_folder_input",
            )
            new_template_id = st.text_input(
                "Slides Template ID:",
                value=current_settings["slides_template_id"],
                key="template_id_input",
            )
            new_zoom = st.text_input(
                "Zoom Link:",
                value=ZOOM_LINK,
                key="zoom_link_input",
            )
            new_enc_key = st.text_input(
                "Encryption Key:",
                value=current_settings.get("encryption_key", ""),
                key="enc_key_input",
                type="password",
            )

            if st.button("Save Integration Settings"):
                # Merge with existing settings
                all_settings = gu.get_group_settings(group_slug)
                all_settings["folder_id"] = new_folder_id
                all_settings["slides_folder_id"] = new_slides_folder
                all_settings["slides_template_id"] = new_template_id
                all_settings["zoom_link"] = new_zoom
                if new_enc_key:
                    all_settings["encryption_key"] = new_enc_key
                gu.save_group_settings(group_slug, all_settings)
                st.success("Integration settings saved!")

        with st.expander("GCP Service Account (JSON)"):
            st.caption(
                "Paste your GCP service account JSON here to override the default. "
                "The private key will be stored encrypted."
            )
            gcp_json = st.text_area(
                "Service Account JSON:",
                height=200,
                key="gcp_json_input",
                placeholder='{"type": "service_account", "project_id": "...", ...}',
            )
            if st.button("Save GCP Config"):
                if gcp_json.strip():
                    try:
                        gu.save_gcp_config(group_slug, gcp_json.strip())
                        st.success("GCP service account saved!")
                    except ValueError as e:
                        st.error(str(e))
                else:
                    st.warning("Please paste a valid JSON.")

    st.markdown("""**Activity:** 🟥 Low — 🟨 Avg. — 🟩 High""")

    st.write("---")
    if st.button("Back to schedules"):
        st.query_params.clear()
        st.rerun()
