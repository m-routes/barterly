#!/usr/bin/env bash
# Restore drill: recover the database to a point in time on a scratch instance, check
# the data, time every step, then delete the scratch instance.
#
# Production is never touched: Cloud SQL point-in-time recovery always creates a new
# instance (a clone). The drill proves the backups work and measures how long a real
# recovery takes (docs/runbooks/database-restore.md records the results).
#
# Usage: PROJECT_ID=... infra/scripts/restore-drill.sh staging|production [UTC time]
#   UTC time: the recovery point, e.g. 2026-11-23T09:00:00Z (default: 15 minutes ago)
#
# Needs gcloud (Cloud SQL Admin + Secret Manager read), cloud-sql-proxy and psql.
# KEEP=1 leaves the scratch instance running (it costs money until deleted).
set -euo pipefail

ENVIRONMENT="${1:?usage: restore-drill.sh staging|production [UTC time]}"
: "${PROJECT_ID:?set PROJECT_ID}"
REGION="${REGION:-asia-south1}"
case "$ENVIRONMENT" in staging|production) ;; *) echo "unknown environment: $ENVIRONMENT" >&2; exit 2 ;; esac
for tool in gcloud cloud-sql-proxy psql jq; do
  command -v "$tool" >/dev/null || { echo "missing: $tool" >&2; exit 2; }
done

SOURCE="barterly-${ENVIRONMENT}"
STAMP="$(date -u +%Y%m%d%H%M)"
SCRATCH="${SOURCE}-drill-${STAMP}"
POINT="${2:-$(date -u -v-15M +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d '15 minutes ago' +%Y-%m-%dT%H:%M:%SZ)}"
GC=(--project "$PROJECT_ID")
LOG="restore-drill-${ENVIRONMENT}-${STAMP}.log"
PROXY_PID=""

say() { printf '%s  %s\n' "$(date -u +%H:%M:%S)" "$*" | tee -a "$LOG"; }
cleanup() {
  if [[ -n "$PROXY_PID" ]]; then kill "$PROXY_PID" 2>/dev/null || true; fi
  if [[ "${KEEP:-0}" != "1" ]] && gcloud sql instances describe "$SCRATCH" "${GC[@]}" >/dev/null 2>&1; then
    say "Deleting scratch instance $SCRATCH"
    gcloud sql instances delete "$SCRATCH" "${GC[@]}" --quiet
  fi
}
trap cleanup EXIT

say "Restore drill: $SOURCE as of $POINT → $SCRATCH"
gcloud sql instances describe "$SOURCE" "${GC[@]}" \
  --format="value(settings.backupConfiguration.pointInTimeRecoveryEnabled,settings.backupConfiguration.transactionLogRetentionDays)" |
  tee -a "$LOG"
say "Latest backups:"
gcloud sql backups list --instance "$SOURCE" "${GC[@]}" --limit 3 \
  --format="table(windowStartTime,status,type)" | tee -a "$LOG"

T0=$(date +%s)
say "Cloning (point-in-time recovery)..."
gcloud sql instances clone "$SOURCE" "$SCRATCH" "${GC[@]}" --point-in-time "$POINT"
T1=$(date +%s)
say "Clone ready after $(( (T1 - T0) / 60 )) min $(( (T1 - T0) % 60 )) s"

# The app's own credentials work on the clone (users are copied).
URL="$(gcloud secrets versions access latest --secret "database-url-${ENVIRONMENT}" "${GC[@]}")"
USER_PASS="$(sed -E 's#^postgres(ql)?://([^@]+)@.*#\2#' <<<"$URL")"
DB_NAME="$(sed -E 's#^.*/([^/?]+)(\?.*)?$#\1#' <<<"$URL")"
CONNECTION="$(gcloud sql instances describe "$SCRATCH" "${GC[@]}" --format='value(connectionName)')"

cloud-sql-proxy --port 6543 "$CONNECTION" >/dev/null 2>&1 &
PROXY_PID=$!
for _ in $(seq 1 30); do
  psql "postgres://${USER_PASS}@127.0.0.1:6543/${DB_NAME}?sslmode=disable" -qtAc 'select 1' >/dev/null 2>&1 && break
  sleep 2
done

say "Checking the restored data..."
psql "postgres://${USER_PASS}@127.0.0.1:6543/${DB_NAME}?sslmode=disable" -v ON_ERROR_STOP=1 -P pager=off <<'SQL' | tee -a "$LOG"
-- Row counts of the tables that matter most, and the newest write in each.
select 'users' as table, count(*), max(created_at) as newest from accounts_user
union all select 'bookings', count(*), max(created_at) from bookings_booking
union all select 'escrows', count(*), max(created_at) from money_escrow
union all select 'ledger transactions', count(*), max(created_at) from money_ledgertransaction
union all select 'audit log', count(*), max(created_at) from common_auditlog;
-- The ledger came back whole: every transaction has its lines, every line is positive.
select case when count(*) = 0 then 'ledger intact' else 'LEDGER DAMAGED: ' || count(*) || ' problems' end
from (
  select t.id from money_ledgertransaction t
  left join money_ledgerentry e on e.transaction_id = t.id
  group by t.id having count(e.id) = 0
  union all
  select e.transaction_id from money_ledgerentry e where e.amount_paise <= 0
) problems;
-- Migrations applied (the latest few).
select app, name, applied from django_migrations order by applied desc limit 5;
SQL
T2=$(date +%s)
say "Checks done after $(( (T2 - T0) / 60 )) min total."
say "Record in docs/runbooks/database-restore.md: date, environment, point, clone minutes ($(( (T1 - T0) / 60 ))), total minutes ($(( (T2 - T0) / 60 ))), checks OK?"
say "Log: $LOG"
