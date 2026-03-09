# MatterLab Group Meetings

Unified schedule app for all MatterLab subgroup meetings at `schedule.matter.toronto.edu`.

## Setup

### 1. Create a Google Sheet

Create a sheet with these tabs (share it with the GCP service account email as Editor):

| Tab | Columns |
|-----|---------|
| `Schedule` | `Date`, `Presenter` (or `Presenter 1`, `Presenter 2` for ML) |
| `Participants` | `Name`, `Email` |
| `Materials` | `Date`, `Title`, `Description`, `PDF_Name`, `PDF_Link` |
| `Slides` | `Date`, `Presentation_ID`, `Presentation_Link` |

### 2. Create your secrets file

Each subgroup has its own file in `secrets/`. Copy the example and fill it in:

```bash
cp secrets/group.toml.example secrets/ml.toml   # or quantum.toml, general.toml, etc.
```

The `[section]` name must match the filename: `[ml]`, `[quantum]`, `[general]`, `[drugdiscovery]`, `[handson]`.

The shared GCP service account goes in `secrets/shared.toml` (copy from `secrets/shared.toml.example`).

**No email passwords are stored in secrets.** Admins enter their email credentials in the app each session when sending confirmation emails.

### 3. Deploy

Build on the cluster (avoids ARM/x86 mismatch from Mac):

```bash
# On the cluster
git clone <repo-url> ~/schedule-logs
cd ~/schedule-logs

# Copy secrets from your local machine:
#   scp -r secrets/ user@schedule.matter.toronto.edu:~/schedule-logs/secrets/

docker-compose up -d --build
```

### 4. Redeploy

```bash
# After code changes:
git pull && docker-compose up -d --build

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
