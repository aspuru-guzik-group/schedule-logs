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

### 3. Deploy

Build on the cluster (avoids ARM/x86 mismatch from Mac):

```bash
# On the cluster
git clone <repo-url> ~/schedule-logs
cd ~/schedule-logs

# Copy secrets from your local machine:
#   scp -r secrets/ user@schedule.matter.toronto.edu:~/schedule-logs/secrets/

docker compose up -d --build
```

### 4. Redeploy

```bash
# After code changes:
git pull && docker compose up -d --build

# After secrets-only changes (no rebuild needed):
docker compose restart
```

## Local dev

```bash
pip install -r requirements.txt
# Put secrets in secrets/ as above, then:
cat secrets/*.toml > .streamlit/secrets.toml
streamlit run app.py
```

## Admin panel

Each group's admin logs in via the sidebar password. From there you can also update SMTP credentials, Drive folder IDs, and GCP service account JSON — stored in the group's Google Sheet so no redeployment is needed.
