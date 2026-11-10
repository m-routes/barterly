# Rollback

Pick the smallest step that fixes the problem.

## 1. Bad code, schema unchanged or compatible → shift traffic back (seconds)

Previous revisions stay deployed, so a rollback is only a traffic change. There's no rebuild and no migration.

```bash
export PROJECT_ID=barterly-prod-123456
infra/scripts/rollback.sh production api          # newest ready revision before the current one
infra/scripts/rollback.sh production web
infra/scripts/rollback.sh production api barterly-api-production-00042-abc   # a specific revision
```

List revisions with:

```bash
gcloud run revisions list --service barterly-api-production --region asia-south1
```

The next deploy from CI moves traffic forward again. To stop that, revert the commit on `main` (staging) or don't push a new tag (production).

## 2. Bad migration → reverse it with the migrate job

All migrations must be reversible (CONTRIBUTING.md). Run the reverse migration with the image that contains the migration, **before** shifting traffic to a revision that expects the old schema:

```bash
gcloud run jobs execute barterly-migrate-production --region asia-south1 --wait \
  --args=migrate,<app_label>,<previous_migration_name>
```

The job's command is `python manage.py`, so `--args` replaces only the `release` argument. Then roll the API back as in step 1.

Because of expand/contract, a release's migrations only add things the previous release ignores. Rolling the code back first and reversing the migration later is normally safe too.

## 3. Data damage → Cloud SQL point-in-time recovery

Production keeps 30 daily backups, plus 7 days of transaction logs for point-in-time recovery. Recovery always creates a **new instance** (a clone), so the damaged one stays untouched until you switch:

```bash
# 1. Clone production as it was just before the incident (UTC). Takes several minutes.
gcloud sql instances clone barterly-production barterly-production-pitr \
  --point-in-time 2026-11-08T10:15:00Z --region asia-south1
# 2. Inspect it, e.g. with the Cloud SQL Auth Proxy, and copy back only the damaged rows if you can.
```

If the whole database must go back in time, point the environment at the clone: set the instance name in Terraform (or import the clone), apply so the `database-url-production` secret and the Cloud Run connector volume reference it, then redeploy. Writes after the recovery point are lost, so use this only for real data loss.

For a full restore from a daily backup instead, which overwrites the target instance:

```bash
gcloud sql backups list --instance barterly-production
gcloud sql backups restore <backup-id> --restore-instance barterly-production
```

## 4. Bad secret or config

Secrets are versioned. Disable the bad version, and the next revision picks up the latest enabled one:

```bash
gcloud secrets versions list database-url-production
gcloud secrets versions disable <bad-version> --secret database-url-production
gcloud run services update barterly-api-production --region asia-south1   # new revision reads `latest`
```

Infrastructure changes: revert the Terraform commit and `terraform apply`. State versions are kept in the versioned state bucket.

## After any rollback

- Write down what was rolled back, when, and why in the incident note.
- Fix forward on `main`. Staging deploys automatically; production needs a new tag and approval.
