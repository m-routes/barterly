#!/usr/bin/env bash
# Generate and store the Django secret key for an environment in Secret Manager.
# DATABASE_URL is written by Terraform (modules/environment/database.tf). Values are piped straight into
# Secret Manager and never printed or written to disk.
#
# Usage: PROJECT_ID=... infra/scripts/set-secrets.sh staging|production
set -euo pipefail

ENVIRONMENT="${1:?usage: set-secrets.sh staging|production}"
: "${PROJECT_ID:?set PROJECT_ID}"
case "$ENVIRONMENT" in staging|production) ;; *) echo "unknown environment: $ENVIRONMENT" >&2; exit 2 ;; esac

SECRET="django-secret-key-${ENVIRONMENT}"
if gcloud secrets versions list "$SECRET" --project "$PROJECT_ID" --filter="state=ENABLED" --format="value(name)" | grep -q .; then
  echo "${SECRET} already has an enabled version; rotate with ROTATE=1" >&2
  [[ "${ROTATE:-0}" == "1" ]] || exit 0
fi

openssl rand -base64 64 | tr -d '\n' |
  gcloud secrets versions add "$SECRET" --project "$PROJECT_ID" --data-file=-
echo "Added a new version of ${SECRET}"
