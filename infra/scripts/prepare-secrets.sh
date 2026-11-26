#!/usr/bin/env bash
# Get an environment's secrets ready before the Terraform apply that wires them into
# Cloud Run. A secret that the API or web reads but that has no version stops the new
# revision starting, so values must exist first.
#
# Usage: PROJECT_ID=... infra/scripts/prepare-secrets.sh staging|production
#
# 1. The secret containers must exist. If they don't, create only them first:
#      terraform apply \
#        -target='module.environment.google_secret_manager_secret.this' \
#        -target='module.environment.google_secret_manager_secret.qa_admin_password'
# 2. Generates what can be generated (set-secrets.sh): the Django key, the check-in pass
#    signing key and the field-encryption keys. Existing values are left alone. On
#    staging, also the QA admin password the acceptance suite signs in with.
# 3. Asks whether to store the Razorpay and RazorpayX values now (set-razorpay-secrets.sh
#    reads them from the terminal without echoing). Skip it and keep
#    razorpay_enabled = false until you have them.
# 4. Prints every secret with whether it has a value, and the *_enabled settings that
#    may now be true in terraform.tfvars.
#
# Values are piped straight into Secret Manager; nothing is printed or written to disk.
set -euo pipefail

ENVIRONMENT="${1:?usage: prepare-secrets.sh staging|production}"
: "${PROJECT_ID:?set PROJECT_ID}"
case "$ENVIRONMENT" in staging|production) ;; *) echo "unknown environment: $ENVIRONMENT" >&2; exit 2 ;; esac
HERE="$(cd "$(dirname "$0")" && pwd)"

# name → the tfvars setting that wires it ("always": wired whatever the settings).
SECRETS=(
  "django-secret-key:always"
  "database-url:always"
  "attendance-signing-key:always"
  "field-encryption-keys:always"
  "razorpay-key-id:razorpay_enabled"
  "razorpay-key-secret:razorpay_enabled"
  "razorpay-webhook-secret:razorpay_enabled"
  "razorpay-escrow-webhook-secret:razorpay_enabled"
  "razorpayx-webhook-secret:razorpay_enabled"
  "razorpayx-account-number:razorpay_enabled"
  "sentry-dsn:sentry_enabled"
  "email-host-password:email_enabled"
  "kyc-webhook-secret:kyc_webhook_enabled"
  "youtube-api-key:youtube_stats_enabled"
  "instagram-graph-token:instagram_stats_enabled"
  "media-cdn-key:media_cdn_signing_enabled"
)

exists() { gcloud secrets describe "$1" --project "$PROJECT_ID" >/dev/null 2>&1; }
has_value() {
  gcloud secrets versions list "$1" --project "$PROJECT_ID" --filter="state=ENABLED" \
    --format="value(name)" 2>/dev/null | grep -q .
}

missing=()
for entry in "${SECRETS[@]}"; do
  name="${entry%%:*}-${ENVIRONMENT}"
  exists "$name" || missing+=("$name")
done
if ((${#missing[@]})); then
  echo "These secret containers don't exist yet: ${missing[*]}" >&2
  echo "Create them first, from infra/terraform/envs/${ENVIRONMENT}:" >&2
  echo "  terraform apply -target='module.environment.google_secret_manager_secret.this' \\" >&2
  echo "    -target='module.environment.google_secret_manager_secret.qa_admin_password'" >&2
  exit 1
fi

echo "== Generated secrets"
"$HERE/set-secrets.sh" "$ENVIRONMENT"
QA="qa-admin-password-${ENVIRONMENT}"
if [[ "$ENVIRONMENT" == "staging" ]] && exists "$QA" && ! has_value "$QA"; then
  openssl rand -base64 24 | tr -d '\n' |
    gcloud secrets versions add "$QA" --project "$PROJECT_ID" --data-file=-
  echo "Added the first version of ${QA}. Copy it into the GitHub secret E2E_ADMIN_PASSWORD:"
  echo "  gcloud secrets versions access latest --secret ${QA} --project ${PROJECT_ID}"
fi

echo
if has_value "razorpay-key-id-${ENVIRONMENT}"; then
  echo "== Razorpay: values already stored (re-run set-razorpay-secrets.sh to change them)."
else
  read -r -p "Store the Razorpay and RazorpayX values now? [y/N] " answer
  if [[ "$answer" =~ ^[Yy]$ ]]; then
    "$HERE/set-razorpay-secrets.sh" "$ENVIRONMENT"
  else
    echo "Skipped: keep razorpay_enabled = false for ${ENVIRONMENT}."
  fi
fi

echo
echo "== Secrets for ${ENVIRONMENT}"
blocked=0
empty_settings=" "
for entry in "${SECRETS[@]}"; do
  name="${entry%%:*}-${ENVIRONMENT}"
  setting="${entry#*:}"
  if has_value "$name"; then
    state="has a value"
  else
    state="EMPTY"
    if [[ "$setting" == "always" ]]; then blocked=1; else empty_settings+="${setting} "; fi
  fi
  printf '  %-42s %-12s %s\n' "$name" "$state" "$setting"
done

echo
echo "Settings that may be true in terraform.tfvars (every secret they wire has a value):"
seen=" "
for entry in "${SECRETS[@]}"; do
  setting="${entry#*:}"
  [[ "$setting" == "always" || "$seen" == *" ${setting} "* ]] && continue
  seen+="${setting} "
  [[ "$empty_settings" == *" ${setting} "* ]] || echo "  ${setting} = true"
done
if ((blocked)); then
  echo "A secret wired in every case is still EMPTY: don't apply yet." >&2
  exit 1
fi
echo "Ready: run terraform plan, then apply."
