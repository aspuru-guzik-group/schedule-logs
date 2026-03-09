# MatterLab Group Meetings

Unified Streamlit app for managing subgroup meeting schedules at MatterLab. Hosts schedules for General, Quantum (QC@ML), Machine Learning (ML@ML), Drug Discovery, and Hands-on subgroups on a single page at `schedule.matter.toronto.edu`.

## Architecture

- **Landing page** — picker to select a subgroup
- **Per-group schedule** — each group has its own Google Sheet, presenter logic, admin panel
- **ML subgroup** has 2 presenters per week (Wednesdays); all other groups have 1 presenter per week
- **Admin panel** (sidebar password) lets each group's admin manage participants, edit schedules, send confirmation emails, and configure SMTP / Google Drive / GCP settings without touching config files

## Prerequisites

Each subgroup needs:

1. **A Google Sheet** with these tabs: `Schedule`, `Participants`, `Materials`, `Slides` (the app will create `Settings` and `GCPConfig` tabs automatically when admins save settings from the panel)
2. **A GCP service account** with access to Google Sheets, Drive, and Slides APIs — shared across groups or per-group
3. **SMTP credentials** for sending confirmation emails (e.g. UofT CS Lab email)
4. **A Google Slides template** with placeholders (`{{DATE}}`, `{{PRESENTER}}` for 1-presenter groups, `{{PRESENTER1}}`/`{{PRESENTER2}}` for ML)
5. **Google Drive folders** for storing uploaded materials and generated slides

## Onboarding a new subgroup admin

### 1. Create the Google Sheet

Create a new Google Sheet and share it with the GCP service account email (e.g. `streamlit@matterlab-447719.iam.gserviceaccount.com`) with **Editor** access. Add these tabs:

| Tab | Columns |
|-----|---------|
| `Schedule` | `Date`, `Presenter` (or `Date`, `Presenter 1`, `Presenter 2` for ML) |
| `Participants` | `Name`, `Email` |
| `Materials` | `Date`, `Title`, `Description`, `PDF_Name`, `PDF_Link` |
| `Slides` | `Date`, `Presentation_ID`, `Presentation_Link` |

### 2. Create Google Drive folders

- One folder for uploaded materials (PDFs, etc.)
- One folder for generated slide decks

Share both with the service account email with **Editor** access. Copy the folder IDs from the URLs.

### 3. Create a Slides template

Create a Google Slides presentation to use as a template. Use these placeholders in the slides:
- `{{DATE}}` — replaced with the meeting date
- `{{PRESENTER}}` — replaced with the presenter name (for 1-presenter groups)
- `{{PRESENTER1}}`, `{{PRESENTER2}}` — for ML (2-presenter) group

Copy the template's file ID from the URL.

### 4. Add secrets

Add a new section to `.streamlit/secrets.toml` for your group. The section name must match the group slug in `config.py` (e.g. `[quantum]`, `[ml]`, `[general]`, `[drugdiscovery]`, `[handson]`):

```toml
[yourgroup]
admin_password = "your-admin-password"
sender_email = "you@cs.toronto.edu"
smtp_password = "your-smtp-password"
smtp_server = "smtp.cs.toronto.edu"
smtp_port = 587
organizer_name = "Your Name"
folder_id = "google-drive-folder-id"
slides_folder_id = "google-drive-slides-folder-id"
slides_template_id = "google-slides-template-id"
zoom_link = "https://utoronto.zoom.us/j/..."
spreadsheet_id = "google-sheet-id"
encryption_key = "any-secret-string-for-encryption"
```

See `secrets.toml.template` for the full file structure.

### 5. (Optional) Configure from admin panel

Once the app is running, you can update SMTP settings, Drive folder IDs, Slides template, Zoom link, and even the GCP service account JSON from the admin panel — no redeployment needed. Log in with the admin password in the sidebar.

## Local development

```bash
# Install dependencies
pip install -r requirements.txt

# Create secrets file from template
cp secrets.toml.template .streamlit/secrets.toml
# Edit .streamlit/secrets.toml with your values

# Run the app
streamlit run app.py
```

## Deployment

The app runs as a Docker container on `schedule.matter.toronto.edu`, listening on port 3000.

### First-time setup

**On your local machine:**

```bash
# 1. Clone the repo and set up secrets
git clone <repo-url>
cp secrets.toml.template .streamlit/secrets.toml
# Edit .streamlit/secrets.toml with all group secrets
```

**On the cluster (`schedule.matter.toronto.edu`):**

```bash
# 2. Clone the repo
git clone <repo-url> ~/schedule-logs
cd ~/schedule-logs

# 3. Copy your secrets file to the server
#    (from your local machine)
scp .streamlit/secrets.toml user@schedule.matter.toronto.edu:~/schedule-logs/.streamlit/secrets.toml

# 4. Build and start the container on the cluster
docker compose up -d --build
```

Build directly on the cluster — it avoids architecture mismatches (ARM Mac vs x86 server) and keeps the workflow simple: push code, pull on server, build there.

### Redeploying after code changes

**On your local machine:**

```bash
# 1. Make changes and push
git add -A && git commit -m "your changes" && git push
```

**On the cluster:**

```bash
# 2. Pull and rebuild
cd ~/schedule-logs
git pull
docker compose up -d --build
```

If you only changed secrets (not code):

```bash
# Just restart — the secrets.toml is mounted as a volume, no rebuild needed
docker compose restart
```

### Redeploying after adding a new subgroup

1. Add the group config to `config.py` (if not already there)
2. Add the group's secrets section to `.streamlit/secrets.toml` on the cluster
3. Redeploy:

```bash
cd ~/schedule-logs
git pull
docker compose up -d --build
```

### Useful commands

```bash
# View logs
docker compose logs -f

# Stop the app
docker compose down

# Rebuild from scratch (e.g. after dependency changes)
docker compose build --no-cache && docker compose up -d

# Check container status
docker compose ps
```
