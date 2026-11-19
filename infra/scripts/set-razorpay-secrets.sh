#!/usr/bin/env bash
# Store an environment's Razorpay keys in Secret Manager (read from the terminal without
# echoing; never printed or written to disk). Use test-mode keys for staging and live
# keys for production. The webhook secret is the one set on the webhook in the Razorpay
# dashboard (Settings > Webhooks), pointed at <API_URL>/api/v1/billing/webhooks/razorpay/.
# The escrow webhook secret belongs to a second webhook, pointed at
# <API_URL>/api/v1/money/webhooks/razorpay/.
#
# Usage: PROJECT_ID=... infra/scripts/set-razorpay-secrets.sh staging|production
set -euo pipefail

ENVIRONMENT="${1:?usage: set-razorpay-secrets.sh staging|production}"
: "${PROJECT_ID:?set PROJECT_ID}"
case "$ENVIRONMENT" in staging|production) ;; *) echo "unknown environment: $ENVIRONMENT" >&2; exit 2 ;; esac

for name in key-id key-secret webhook-secret escrow-webhook-secret; do
  secret="razorpay-${name}-${ENVIRONMENT}"
  read -r -s -p "Razorpay ${name} for ${ENVIRONMENT}: " value
  echo
  [[ -n "$value" ]] || { echo "skipped ${secret}"; continue; }
  printf '%s' "$value" | gcloud secrets versions add "$secret" --project "$PROJECT_ID" --data-file=-
  echo "Added a new version of ${secret}"
done
