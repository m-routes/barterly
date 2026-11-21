#!/usr/bin/env bash
# Rotate an environment's secrets (the yearly drill, and after any suspected leak).
# Run by a person with Secret Manager admin on the project; values are generated and
# piped straight into Secret Manager, never printed or written to disk.
#
# Usage: PROJECT_ID=... infra/scripts/rotate-secrets.sh staging|production <step>
#
# Steps, in drill order (docs/security.md, "Secret rotation drill"):
#   audit          list every secret, its newest version's age, and who can read it
#   field-keys     put a new field-encryption key first (old keys kept for reading)
#   reencrypt      after a deploy picks up the new key: re-encrypt rows with it
#   drop-old-keys  once `reencrypt --check` is clean: keep only the newest key
#   django-key     new DJANGO_SECRET_KEY (signs everyone out: API tokens are HS256)
#   attendance-key new pass-signing key (copy the old public key first, see below)
#   restart        roll the API onto a new revision so it reads the new versions
#
# Provider-issued secrets (Razorpay keys and webhook secrets, Sentry DSN, SMTP password,
# KYC webhook secret, YouTube/Instagram tokens) are rotated in the provider's dashboard;
# then add the new value with `gcloud secrets versions add <name> --data-file=-` and run
# `restart`. Disable (don't destroy) old versions for a week, then destroy them.
set -euo pipefail

ENVIRONMENT="${1:?usage: rotate-secrets.sh staging|production <step>}"
STEP="${2:?usage: rotate-secrets.sh staging|production <step>}"
: "${PROJECT_ID:?set PROJECT_ID}"
REGION="${REGION:-asia-south1}"
case "$ENVIRONMENT" in staging|production) ;; *) echo "unknown environment: $ENVIRONMENT" >&2; exit 2 ;; esac
GC=(--project "$PROJECT_ID")
API_SERVICE="barterly-api-${ENVIRONMENT}"
MIGRATE_JOB="barterly-migrate-${ENVIRONMENT}"
FIELD_KEYS="field-encryption-keys-${ENVIRONMENT}"

latest() { gcloud secrets versions access latest --secret "$1" "${GC[@]}"; }
add_version() { gcloud secrets versions add "$1" "${GC[@]}" --data-file=- >/dev/null && echo "Added a new version of $1"; }
confirm() {
  read -r -p "$1 Type the environment name to continue: " answer
  [[ "$answer" == "$ENVIRONMENT" ]] || { echo "Stopped." >&2; exit 1; }
}
run_job() {
  gcloud run jobs execute "$MIGRATE_JOB" "${GC[@]}" --region "$REGION" --wait \
    --args="manage.py,$*"
}

case "$STEP" in
  audit)
    for secret in $(gcloud secrets list "${GC[@]}" --filter="name~-${ENVIRONMENT}\$" --format="value(name)"); do
      created="$(gcloud secrets versions list "$secret" "${GC[@]}" --filter="state=ENABLED" \
        --sort-by=~createTime --limit=1 --format="value(createTime.date('%Y-%m-%d'))")"
      readers="$(gcloud secrets get-iam-policy "$secret" "${GC[@]}" \
        --flatten="bindings[].members" --format="value(bindings.members)" | paste -sd, -)"
      printf '%-45s newest=%-10s readers=%s\n' "$secret" "${created:-none}" "${readers:-none}"
    done
    ;;
  field-keys)
    confirm "Adds a new field-encryption key in front of the current ones."
    current="$(latest "$FIELD_KEYS" 2>/dev/null || true)"
    kid="k$(date -u +%Y%m%d%H%M)"
    new="${kid}:$(openssl rand -base64 32 | tr -d '\n')"
    printf '%s' "${new}${current:+,${current}}" | add_version "$FIELD_KEYS"
    echo "Next: deploy (or '$0 $ENVIRONMENT restart'), then '$0 $ENVIRONMENT reencrypt'."
    ;;
  reencrypt)
    run_job reencrypt_fields
    run_job reencrypt_fields,--check
    echo "All values are under the newest key. Next: '$0 $ENVIRONMENT drop-old-keys'."
    ;;
  drop-old-keys)
    confirm "Keeps only the newest field-encryption key. Run reencrypt first."
    run_job reencrypt_fields,--check
    latest "$FIELD_KEYS" | cut -d, -f1 | tr -d '\n' | add_version "$FIELD_KEYS"
    echo "Restart the API and migrate job so they stop holding the old key."
    ;;
  django-key)
    confirm "A new DJANGO_SECRET_KEY signs every user out of the app and the web."
    openssl rand -base64 64 | tr -d '\n' | add_version "django-secret-key-${ENVIRONMENT}"
    ;;
  attendance-key)
    echo "Before this: put the current public key in ATTENDANCE_PREVIOUS_PUBLIC_KEYS (docs/attendance.md)."
    confirm "Rotates the check-in pass signing key."
    openssl rand -base64 32 | tr -d '\n' | add_version "attendance-signing-key-${ENVIRONMENT}"
    ;;
  restart)
    # A new revision re-reads every "latest" secret version.
    gcloud run services update "$API_SERVICE" "${GC[@]}" --region "$REGION" \
      --update-labels "secrets-rotated=$(date -u +%Y%m%d%H%M)"
    gcloud run jobs update "$MIGRATE_JOB" "${GC[@]}" --region "$REGION" \
      --update-labels "secrets-rotated=$(date -u +%Y%m%d%H%M)"
    ;;
  *) echo "unknown step: $STEP" >&2; exit 2 ;;
esac
