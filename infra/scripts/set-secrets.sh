#!/usr/bin/env bash
# Generate and store an environment's own secrets in Secret Manager: the Django secret key
# and the key that signs check-in passes (32 random bytes, base64). DATABASE_URL is
# written by Terraform (modules/environment/database.tf). Values are piped straight into
# Secret Manager and never printed or written to disk.
#
# Usage: PROJECT_ID=... infra/scripts/set-secrets.sh staging|production
# A secret that already has a version is left alone unless ROTATE=1. Rotating the
# attendance key: first copy its public key into ATTENDANCE_PREVIOUS_PUBLIC_KEYS (see
# docs/attendance.md), so passes already handed out still verify.
set -euo pipefail

ENVIRONMENT="${1:?usage: set-secrets.sh staging|production}"
: "${PROJECT_ID:?set PROJECT_ID}"
case "$ENVIRONMENT" in staging|production) ;; *) echo "unknown environment: $ENVIRONMENT" >&2; exit 2 ;; esac

store() {
  local secret="$1" bytes="$2"
  if gcloud secrets versions list "$secret" --project "$PROJECT_ID" --filter="state=ENABLED" --format="value(name)" | grep -q .; then
    if [[ "${ROTATE:-0}" != "1" ]]; then
      echo "${secret} already has an enabled version; rotate with ROTATE=1" >&2
      return 0
    fi
  fi
  openssl rand -base64 "$bytes" | tr -d '\n' |
    gcloud secrets versions add "$secret" --project "$PROJECT_ID" --data-file=-
  echo "Added a new version of ${secret}"
}

store "django-secret-key-${ENVIRONMENT}" 64
store "attendance-signing-key-${ENVIRONMENT}" 32

# Field-encryption keys are "id:base64key" (apps.common.encryption); the first one.
FIELD_KEYS="field-encryption-keys-${ENVIRONMENT}"
if gcloud secrets versions list "$FIELD_KEYS" --project "$PROJECT_ID" --filter="state=ENABLED" --format="value(name)" | grep -q .; then
  echo "${FIELD_KEYS} already has a version; rotate with infra/scripts/rotate-secrets.sh" >&2
else
  printf 'k%s:%s' "$(date -u +%Y%m%d%H%M)" "$(openssl rand -base64 32 | tr -d '\n')" |
    gcloud secrets versions add "$FIELD_KEYS" --project "$PROJECT_ID" --data-file=-
  echo "Added the first version of ${FIELD_KEYS}"
fi
