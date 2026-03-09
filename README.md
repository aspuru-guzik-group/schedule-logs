# MatterLab Group Meetings

Unified schedule app for all MatterLab subgroup meetings at `schedule.matter.toronto.edu`.

## Setup

### 1. Create a GCP service account

Each subgroup needs its own Google Cloud service account to access Sheets, Drive, and Slides.

1. Go to [console.cloud.google.com](https://console.cloud.google.com/)
2. Create a new project (or use an existing one) — the `project_id` in your secrets comes from here
3. Enable these APIs for the project (search each in the top bar and click **Enable**):
   - [Google Sheets API](https://console.cloud.google.com/apis/library/sheets.googleapis.com)
   - [Google Drive API](https://console.cloud.google.com/apis/library/drive.googleapis.com)
   - [Google Slides API](https://console.cloud.google.com/apis/library/slides.googleapis.com)
4. Go to [IAM & Admin > Service Accounts](https://console.cloud.google.com/iam-admin/serviceaccounts)
5. Click **Create Service Account**, give it a name (e.g. `schedule-ml`), click **Done**
6. Click the new service account, go to the **Keys** tab
7. Click **Add Key > Create new key > JSON** — a `.json` file downloads

That JSON file contains everything you need for the `[groupslug.gcp_service_account]` section:

| JSON field | Secrets field |
|-----------|---------------|
| `type` | `type` (always `"service_account"`) |
| `project_id` | `project_id` |
| `private_key_id` | `private_key_id` |
| `private_key` | `private_key` (the long `-----BEGIN PRIVATE KEY-----...` string) |
| `client_email` | `client_email` (e.g. `schedule-ml@myproject.iam.gserviceaccount.com`) |
| `client_id` | `client_id` |
| `auth_uri` | `auth_uri` |
| `token_uri` | `token_uri` |
| `auth_provider_x509_cert_url` | `auth_provider_x509_cert_url` |
| `client_x509_cert_url` | `client_x509_cert_url` |

Copy each value from the JSON into your `secrets/groupslug.toml` under `[groupslug.gcp_service_account]`.

### 2. Create a Google Sheet

Create a new Google Sheet and share it with the service account's `client_email` as **Editor**.

The `spreadsheet_id` is the long string in the Sheet URL:
```
https://docs.google.com/spreadsheets/d/THIS_IS_THE_SPREADSHEET_ID/edit
```

Add these tabs (exact names):

| Tab | Columns |
|-----|---------|
| `Schedule` | `Date`, `Presenter` (or `Presenter 1`, `Presenter 2` for ML) |
| `Participants` | `Name`, `Email` |
| `Materials` | `Date`, `Title`, `Description`, `PDF_Name`, `PDF_Link` |
| `Slides` | `Date`, `Presentation_ID`, `Presentation_Link` |

### 3. Create Google Drive folders

Create two folders in Google Drive and share both with the service account `client_email` as **Editor**:

- **Materials folder** — for uploaded PDFs → this is `folder_id`
- **Slides folder** — for generated slide decks → this is `slides_folder_id`

The folder ID is in the URL:
```
https://drive.google.com/drive/folders/THIS_IS_THE_FOLDER_ID
```

### 4. Create a Slides template

Create a Google Slides presentation to use as a template. Add these placeholders in the slides:

- `{{DATE}}` — replaced with the meeting date
- `{{PRESENTER}}` — for 1-presenter groups
- `{{PRESENTER1}}`, `{{PRESENTER2}}` — for ML (2-presenter) group

Share it with the service account `client_email` as **Viewer**. The `slides_template_id` is in the URL:
```
https://docs.google.com/presentation/d/THIS_IS_THE_TEMPLATE_ID/edit
```

### 5. Create your secrets file

Each subgroup has its own file in `secrets/`. Copy the example and fill it in:

```bash
cp secrets/group.toml.example secrets/ml.toml   # or quantum.toml, general.toml, etc.
```

The `[section]` name must match the filename: `[ml]`, `[quantum]`, `[general]`, `[drugdiscovery]`, `[handson]`.

The remaining fields:

| Field | What it is |
|-------|-----------|
| `admin_password` | Password to access the admin panel (you pick this) |
| `organizer_name` | Name shown in confirmation emails (e.g. "Luis Mantilla") |
| `zoom_link` | Zoom meeting URL for this subgroup |
| `encryption_key` | Any secret string used to encrypt confirmation links (you pick this) |

**No email passwords are stored in secrets.** Admins enter their email credentials in the app each session when sending confirmation emails.

### 6. Deploy

Build on the cluster (avoids ARM/x86 mismatch from Mac):

```bash
# On the cluster
git clone <repo-url> ~/schedule-logs
cd ~/schedule-logs

# Copy secrets from your local machine:
#   scp -r secrets/ user@schedule.matter.toronto.edu:~/schedule-logs/secrets/

docker-compose up -d --build
```

### 7. Redeploy

```bash
# After code changes:
git pull && docker-compose down && docker-compose up -d --build

# After secrets-only changes (no rebuild needed):
docker-compose restart
```

## Local dev

```bash
pip install -r requirements.txt
# Put secrets in secrets/ as above, then:
cat secrets/*.toml > .streamlit/secrets.toml
streamlit run app.py
```

## Sending confirmation emails

When you click **Send Confirmation Emails** in the admin panel, the app asks for your email and password. It auto-detects the provider from your email domain:

| Domain | Provider | What to enter |
|--------|----------|---------------|
| `cs.toronto.edu` | UofT CS | Your CS lab password |
| `utoronto.ca` / `mail.utoronto.ca` | UofT Outlook | Your UTORid password |
| `gmail.com` | Gmail | A **Gmail App Password** (see below) |

Credentials are kept in memory for the session only — never saved to disk or sheets.

### Gmail App Password setup

Gmail blocks regular password login. You need a one-time App Password:

1. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
2. You may need to enable 2-Step Verification first at [myaccount.google.com/signinoptions/two-step-verification](https://myaccount.google.com/signinoptions/two-step-verification)
3. On the App Passwords page, type a name (e.g. "MatterLab Schedule") and click **Create**
4. Google shows a 16-character password like `abcd efgh ijkl mnop` — copy it
5. Paste that into the **App Password** field in the send dialog

You only need to generate this once. Save it somewhere safe (e.g. a password manager) — Google won't show it again.

## Admin panel

Each group's admin logs in via the sidebar password. From there you can manage participants, edit schedules, and update Drive folder IDs / GCP service account JSON.
