# Database restore and the restore drill

## What we can recover

| | Production | Staging |
| --- | --- | --- |
| Point-in-time recovery | Any second in the last **7 days** | 7 days |
| Daily backups | 02:00 IST, last **30** kept | last 7 kept |
| Recovery always lands in | A **new instance** (a clone): the damaged one is untouched until you switch | same |

These settings are from Terraform (`modules/environment/database.tf`). On 23 Nov 2026
I checked them against the live instances, and every automated backup in the last
three days on both had succeeded.

## Recover production

1. **Pick the point.** This is the last moment before the damage, in UTC. The audit log
   (`common_auditlog`) and Cloud Logging usually show it.
2. **Stop writes making it worse.** Turn on the money kill switch, and turn off the
   feature flags involved. For a severe case, scale the API to zero:
   `gcloud run services update barterly-api-production --max-instances 0`.
3. **Clone:**
   ```bash
   gcloud sql instances clone barterly-production barterly-production-pitr-<yyyymmdd> \
     --point-in-time 2026-11-23T09:00:00Z
   ```
4. **Decide what to restore:**
   - **A few rows damaged:** connect to the clone (Cloud SQL Auth Proxy) and copy back
     only those rows with a reviewed script. Keep production running. This is usually
     right.
   - **Everything must go back:**
     1. Point the environment at the clone: import it into Terraform as the instance,
        apply (this updates `database-url-production` and the connector), and
        redeploy.
     2. Writes after the recovery point are lost. List them from the old instance
        first, for example new bookings and payments.
     3. Reconcile the payments with Razorpay afterwards; see
        [payment-mismatch](payment-mismatch.md).
5. **Keep the damaged instance** until the review is done, then delete it.

The rollback commands are also in [infra/ROLLBACK.md](../../infra/ROLLBACK.md#3-data-damage--cloud-sql-point-in-time-recovery).

## The restore drill

The drill proves backups restore, and measures how long it takes. Run it **every
quarter** and after any change to `database.tf`: staging first, then production.

```bash
export PROJECT_ID=project-19c38b75-2d9e-4394-ae1
infra/scripts/restore-drill.sh staging                 # recovery point: 15 minutes ago
infra/scripts/restore-drill.sh production 2026-11-23T09:00:00Z
```

What it does:
1. Clones the instance to `barterly-<env>-drill-<timestamp>` from point-in-time
   recovery. Production itself is never touched.
2. Connects with the app's own credentials through `cloud-sql-proxy`.
3. Checks the restored data:
   - row counts and the newest write in users, bookings, escrows, ledger and audit log,
     where the newest write should be just before the recovery point;
   - that every ledger transaction has its lines;
   - the latest migrations.
4. Prints how long the clone and the whole drill took, and writes a log file.
5. Deletes the scratch instance (`KEEP=1` keeps it).

It needs gcloud with Cloud SQL Admin and Secret Manager access, plus `cloud-sql-proxy`,
`psql` and `jq`. A person runs it: it reads the database password from Secret Manager,
and the scratch instance is billed while it exists (production's tier, for about 15–30
minutes).

### Results

Add a row after each drill. The clone time is the core of the real recovery time; add
about 15 minutes for repointing the environment and redeploying.

| Date | Env | Recovery point | Clone | Total | Checks | Who | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| | staging | | | | | | First drill: not run yet |
