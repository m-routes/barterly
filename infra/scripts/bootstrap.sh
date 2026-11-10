#!/usr/bin/env bash
# One-time project bootstrap: enable the APIs Terraform needs and create the
# Terraform state bucket. Safe to re-run.
#
# Usage: PROJECT_ID=barterly-prod-123456 infra/scripts/bootstrap.sh
set -euo pipefail

: "${PROJECT_ID:?set PROJECT_ID}"
REGION="${REGION:-asia-south1}"
STATE_BUCKET="${STATE_BUCKET:-${PROJECT_ID}-tfstate}"

gcloud services enable \
  cloudresourcemanager.googleapis.com \
  serviceusage.googleapis.com \
  iam.googleapis.com \
  storage.googleapis.com \
  --project "$PROJECT_ID"

if ! gcloud storage buckets describe "gs://${STATE_BUCKET}" --project "$PROJECT_ID" >/dev/null 2>&1; then
  gcloud storage buckets create "gs://${STATE_BUCKET}" \
    --project "$PROJECT_ID" \
    --location "$REGION" \
    --uniform-bucket-level-access \
    --public-access-prevention
fi
gcloud storage buckets update "gs://${STATE_BUCKET}" --versioning

echo "State bucket: ${STATE_BUCKET}"
