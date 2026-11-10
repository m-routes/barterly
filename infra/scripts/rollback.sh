#!/usr/bin/env bash
# Move all traffic of a service back to an earlier revision. No rebuild, no migration.
# Without a revision argument, picks the newest ready revision older than the one
# currently serving.
#
# Usage: PROJECT_ID=... infra/scripts/rollback.sh staging|production api|web [revision]
set -euo pipefail

ENVIRONMENT="${1:?usage: rollback.sh staging|production api|web [revision]}"
COMPONENT="${2:?usage: rollback.sh staging|production api|web [revision]}"
TARGET="${3:-}"
: "${PROJECT_ID:?set PROJECT_ID}"
REGION="${REGION:-asia-south1}"
case "$ENVIRONMENT" in staging|production) ;; *) echo "unknown environment: $ENVIRONMENT" >&2; exit 2 ;; esac
case "$COMPONENT" in api|web) ;; *) echo "unknown component: $COMPONENT" >&2; exit 2 ;; esac

SERVICE="barterly-${COMPONENT}-${ENVIRONMENT}"
GC=(--project "$PROJECT_ID" --region "$REGION" --quiet)

CURRENT="$(gcloud run services describe "$SERVICE" "${GC[@]}" --format json |
  jq -r '[.status.traffic[] | select(.percent == 100)][0].revisionName // empty')"

if [[ -z "$TARGET" ]]; then
  TARGET="$(gcloud run revisions list --service "$SERVICE" "${GC[@]}" \
      --sort-by '~metadata.creationTimestamp' --format json |
    jq -r --arg cur "$CURRENT" '
      [.[] | select(any(.status.conditions[]; .type == "Ready" and .status == "True"))
           | .metadata.name] as $ready
      | ($ready | index($cur)) as $i
      | if $i == null then empty else $ready[$i + 1] // empty end')"
fi

if [[ -z "$TARGET" ]]; then
  echo "No earlier ready revision found for ${SERVICE} (serving: ${CURRENT:-unknown})" >&2
  exit 1
fi

echo "${SERVICE}: moving traffic ${CURRENT:-?} -> ${TARGET}"
gcloud run services update-traffic "$SERVICE" "${GC[@]}" --to-revisions "${TARGET}=100"
