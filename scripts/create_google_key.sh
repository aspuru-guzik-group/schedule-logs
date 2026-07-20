#!/usr/bin/env bash

set -euo pipefail

project_id="${PROJECT_ID:-matter-schedule-$(date +%y%m%d)-$(openssl rand -hex 3)}"
service_account_name="matter-schedule"
service_account_email="${service_account_name}@${project_id}.iam.gserviceaccount.com"
key_dir="$(mktemp -d /tmp/matter-schedule-key.XXXXXX)"
key_file="${key_dir}/service-account.json"
trap 'rm -rf "$key_dir"' EXIT

printf 'Creating Google Cloud project %s...\n' "$project_id" >&2
if ! gcloud projects describe "$project_id" >/dev/null 2>&1; then
    gcloud projects create "$project_id" \
        --name="Matter Schedule" \
        --quiet
fi

gcloud services enable \
    iam.googleapis.com \
    sheets.googleapis.com \
    drive.googleapis.com \
    slides.googleapis.com \
    calendar-json.googleapis.com \
    --project="$project_id" \
    --quiet

if ! gcloud iam service-accounts describe "$service_account_email" \
    --project="$project_id" >/dev/null 2>&1; then
    for attempt in 1 2 3 4 5 6; do
        gcloud iam service-accounts create "$service_account_name" \
            --display-name="Matter Schedule" \
            --project="$project_id" \
            --quiet || true
        if gcloud iam service-accounts describe "$service_account_email" \
            --project="$project_id" >/dev/null 2>&1; then
            break
        fi
        if [ "$attempt" -eq 6 ]; then
            printf 'Service-account creation did not become ready.\n' >&2
            exit 1
        fi
        sleep 10
    done
fi

for attempt in 1 2 3 4 5 6; do
    rm -f "$key_file"
    if gcloud iam service-accounts keys create "$key_file" \
        --iam-account="$service_account_email" \
        --project="$project_id" \
        --quiet; then
        break
    fi
    if [ "$attempt" -eq 6 ]; then
        printf 'Google key creation did not become ready.\n' >&2
        exit 1
    fi
    sleep 10
done

printf '\nCopy everything between the JSON markers into the schedule website.\n'
printf '%s\n' '---BEGIN JSON---'
cat "$key_file"
printf '%s\n' '---END JSON---'
