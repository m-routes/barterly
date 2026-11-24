#!/usr/bin/env bash
# Run the acceptance suite (docs/qa/README.md) for one browser project.
#
#   scripts/acceptance.sh local   desktop     # against the local acceptance stack
#   scripts/acceptance.sh staging phone-390   # nightly: against staging
#
# Before each run it resets the hire journey's personas and prepares the starting
# points the other journeys use, because a run consumes them (the host gets
# onboarded, the check-in happens, the booking is cancelled):
#   local:   manage.py in ../backend, with the local stack's environment
#   staging: the same commands as a Cloud Run job execution (needs gcloud auth)
set -euo pipefail

WHERE="${1:?usage: acceptance.sh local|staging desktop|phone-390}"
PROJECT="${2:?usage: acceptance.sh local|staging desktop|phone-390}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
FIXTURES="${ACCEPTANCE_FIXTURES_DIR:-$HERE/acceptance-fixtures}"
mkdir -p "$FIXTURES"

manage() {
  case "$WHERE" in
    local)
      (cd "$HERE/../backend" && "${UV:-uv}" run python manage.py "$@" 2>/dev/null)
      ;;
    staging)
      : "${PROJECT_ID:?set PROJECT_ID}"
      local args
      args="$(IFS=,; echo "$*")"
      gcloud run jobs execute barterly-qa-staging --project "$PROJECT_ID" \
        --region "${REGION:-asia-south1}" --wait --args="$args" >/dev/null
      # The job writes its JSON to the log; the last line is the result.
      gcloud logging read \
        "resource.type=cloud_run_job AND resource.labels.job_name=barterly-qa-staging" \
        --project "$PROJECT_ID" --limit 1 --format 'value(textPayload)'
      ;;
    *) echo "unknown target: $WHERE" >&2; exit 2 ;;
  esac
}

manage seed_staging --reset-journeys >/dev/null
for talent in creator trip_leader; do
  manage prepare_journey --talent "$talent" > "$FIXTURES/$talent.json"
done

cd "$HERE"
ACCEPTANCE_FIXTURES_DIR="$FIXTURES" npx playwright test \
  -c playwright.acceptance.config.ts --project="$PROJECT"
