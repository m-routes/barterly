#!/usr/bin/env bash
# Deploy one image tag to an environment. Used by .github/workflows/deploy.yml and
# runnable by hand. Order:
#   1. API: create a new revision with no traffic, tagged `candidate`.
#   2. Migrate job: point at the new image and run `manage.py release` (migrate +
#      collectstatic). The old revision keeps serving meanwhile, so migrations must be
#      backwards compatible (expand/contract; see infra/ROLLBACK.md).
#   3. Smoke-test the candidate URL, then move 100% of traffic to it.
#   4. Web: same candidate -> smoke test -> traffic flow.
#
# Usage: PROJECT_ID=... PROJECT_NUMBER=... infra/scripts/deploy.sh staging|production <image-tag>
set -euo pipefail

ENVIRONMENT="${1:?usage: deploy.sh staging|production <image-tag>}"
TAG="${2:?usage: deploy.sh staging|production <image-tag>}"
: "${PROJECT_ID:?set PROJECT_ID}"
: "${PROJECT_NUMBER:?set PROJECT_NUMBER}"
REGION="${REGION:-asia-south1}"
REPOSITORY="${REPOSITORY:-barterly}"
case "$ENVIRONMENT" in staging|production) ;; *) echo "unknown environment: $ENVIRONMENT" >&2; exit 2 ;; esac

REGISTRY="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}"
API_IMAGE="${REGISTRY}/api:${TAG}"
WEB_IMAGE="${REGISTRY}/web:${TAG}"
API_SERVICE="barterly-api-${ENVIRONMENT}"
WEB_SERVICE="barterly-web-${ENVIRONMENT}"
MIGRATE_JOB="barterly-migrate-${ENVIRONMENT}"
GC=(--project "$PROJECT_ID" --region "$REGION" --quiet)

candidate_url() { echo "https://candidate---${1}-${PROJECT_NUMBER}.${REGION}.run.app"; }

smoke() {
  local url="$1" attempt
  for attempt in 1 2 3 4 5 6; do
    if curl --fail --silent --show-error --max-time 20 "$url" >/dev/null; then
      echo "Smoke test passed: $url"
      return 0
    fi
    echo "Smoke test attempt ${attempt} failed: $url" >&2
    sleep $((attempt * 5))
  done
  return 1
}

deploy_candidate() {
  local service="$1" image="$2"
  gcloud run deploy "$service" "${GC[@]}" --image "$image" --no-traffic --tag candidate >&2
  gcloud run services describe "$service" "${GC[@]}" --format 'value(status.latestCreatedRevisionName)'
}

promote() {
  local service="$1" revision="$2"
  gcloud run services update-traffic "$service" "${GC[@]}" --to-revisions "${revision}=100"
  echo "${service}: 100% traffic on ${revision}"
}

echo "Deploying ${TAG} to ${ENVIRONMENT}"

API_REVISION="$(deploy_candidate "$API_SERVICE" "$API_IMAGE")"
echo "API candidate revision: ${API_REVISION}"

gcloud run jobs update "$MIGRATE_JOB" "${GC[@]}" --image "$API_IMAGE"
gcloud run jobs execute "$MIGRATE_JOB" "${GC[@]}" --wait

smoke "$(candidate_url "$API_SERVICE")/api/v1/health/"
promote "$API_SERVICE" "$API_REVISION"

WEB_REVISION="$(deploy_candidate "$WEB_SERVICE" "$WEB_IMAGE")"
smoke "$(candidate_url "$WEB_SERVICE")/"
promote "$WEB_SERVICE" "$WEB_REVISION"

echo "Deployed ${TAG} to ${ENVIRONMENT}"
