#!/usr/bin/env bash
# Run the talent-side acceptance journeys on a device or emulator (docs/qa/README.md).
#
#   tool/acceptance.sh local   emulator-5554     # against the local acceptance stack
#   tool/acceptance.sh staging emulator-5554     # nightly: against staging
#
# Prepares the journeys' starting points first (`prepare_journey`), because a run
# consumes them. Locally the emulator reaches the host's API at 10.0.2.2.
set -euo pipefail

WHERE="${1:?usage: acceptance.sh local|staging <device id>}"
DEVICE="${2:?usage: acceptance.sh local|staging <device id>}"
TALENT="${ACCEPTANCE_TALENT:-volunteer}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
PHONE="$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))[sys.argv[2]]['phone'])" \
  "$HERE/../backend/apps/qa/personas.json" "$TALENT")"

case "$WHERE" in
  local)
    API_URL="${ACCEPTANCE_API_URL:-http://10.0.2.2:8011}"
    FIXTURES="$(cd "$HERE/../backend" && "${UV:-uv}" run python manage.py \
      prepare_journey --talent "$TALENT" 2>/dev/null)"
    DEFINES=(--dart-define=ACCEPTANCE_LOCAL=true)
    ;;
  staging)
    : "${PROJECT_ID:?set PROJECT_ID}" "${STAGING_API_URL:?set STAGING_API_URL}"
    : "${E2E_OTP_CODE:?set E2E_OTP_CODE}"
    API_URL="$STAGING_API_URL"
    gcloud run jobs execute barterly-qa-staging --project "$PROJECT_ID" \
      --region "${REGION:-asia-south1}" --wait \
      --args="prepare_journey,--talent,$TALENT" >/dev/null
    FIXTURES="$(gcloud logging read \
      "resource.type=cloud_run_job AND resource.labels.job_name=barterly-qa-staging" \
      --project "$PROJECT_ID" --limit 1 --format 'value(textPayload)')"
    DEFINES=(
      --dart-define-from-file=env/staging.json
      --dart-define-from-file=env/firebase-keys.json
      "--dart-define=ACCEPTANCE_OTP_CODE=$E2E_OTP_CODE"
    )
    ;;
  *) echo "unknown target: $WHERE" >&2; exit 2 ;;
esac

cd "$HERE"
flutter test integration_test -d "$DEVICE" \
  "${DEFINES[@]}" \
  "--dart-define=ACCEPTANCE_API_URL=$API_URL" \
  "--dart-define=ACCEPTANCE_TALENT_PHONE=$PHONE" \
  "--dart-define=ACCEPTANCE_FIXTURES=$(printf '%s' "$FIXTURES" | base64 | tr -d '\n')"
