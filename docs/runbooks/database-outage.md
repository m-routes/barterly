# Database outage

The database is **Cloud SQL for PostgreSQL 16**. (Neon was replaced on 10 Nov 2026: it
had no India region.)
- **Production:** `barterly-production`, regional HA, so a zone failure triggers an
  automatic failover (usually under 60 seconds).
- **Staging:** `barterly-staging`, zonal.
- **Connections:** the API connects through the Cloud SQL connector built into Cloud
  Run.

**You'll notice it from:**
- **Alerts:** "Database unreachable after retries", "Database connection errors",
  "API is down", or a latency or error-rate alert.
- **Signs:** many 5xx at once across every endpoint.

**Severity:** SEV1 (everything that touches data is down).

## First five minutes

1. **Is Cloud SQL itself unhealthy?**
   ```bash
   gcloud sql instances describe barterly-production --format="value(state,gceZone,failoverReplica)"
   gcloud sql operations list --instance barterly-production --limit 5
   ```
   - An operation like `FAILOVER` or `MAINTENANCE` in progress usually means waiting a
     minute: the API retries connections at start-up (`DB_CONNECT_ATTEMPTS`) and per
     request.
   - Check the Google Cloud status page for Cloud SQL in asia-south1.
2. **Is it us?** A deploy minutes earlier that changed settings or migrations points
   to [bad-deploy-rollback](bad-deploy-rollback.md).
3. **Is it connections?** If the dashboard's "Database connections" panel is at the
   limit (about 100 on db-custom-1-3840), instances are holding too many.

## Diagnose and fix

| What you see | Cause | Fix |
| --- | --- | --- |
| State `RUNNABLE` but connections at the limit | Too many API instances × workers × pool size; or idle-in-transaction connections | Short term: lower `api_max_instances`, or restart the API (a new revision drops connections). Kill long idle sessions in Cloud SQL Studio (`pg_terminate_backend`). Then size `db_tier` for `max_instances × WEB_CONCURRENCY × DB_POOL_MAX_SIZE`. |
| High CPU, slow queries | A missing index or runaway query (often right after a deploy) | Query Insights (Cloud SQL → Query insights) shows the top queries. Roll back the deploy if it introduced one. |
| `FAILOVER` in progress | Zone failure (production) | Wait; it's automatic. Afterwards, check that the API reconnected (errors stop). |
| Instance `FAILED` / `SUSPENDED` | Billing, disk full, or a Google incident | Billing in the console. Disk auto-grows, so check `disk_autoresize`. Otherwise open a Google support case. |
| Wrong password / `password authentication failed` | The database password was rotated without a redeploy | Redeploy (`rotate-secrets.sh <env> restart`) so revisions read the new `database-url` secret. |
| Data is wrong (not unreachable) | Bad migration, bug or mistake | [database-restore.md](database-restore.md) |

## Last resort: recover into a new instance

If the instance can't come back, clone it from point-in-time recovery into a new
instance, then point the environment at that instance. The steps are in
[database-restore.md](database-restore.md#recover-production). The restore drill
measures how long this takes.

## Afterwards

- Confirm the money kill switch is in the state you want. Jobs that failed during the
  outage rerun on their own (they're idempotent).
- Check reconciliation the next morning: webhooks that failed during the outage are
  retried by Razorpay for up to 24 hours.
