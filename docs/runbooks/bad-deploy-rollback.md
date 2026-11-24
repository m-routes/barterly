# Bad deploy: roll back

**You'll notice it from:** an error-rate, latency or uptime alert, or a fast SLO burn,
shortly after a deploy. Sentry also shows new issues tagged with the new release (the
commit SHA).

**Severity:** depends on the impact; roll back first and work out the severity
afterwards.

**Rule: if a deploy went out in the last hour and something broke, roll back first,
then investigate.** Rolling back takes seconds and can be undone.

## First five minutes

1. **What changed?** Find the serving revision and the commit it came from:
   ```bash
   gcloud run services describe barterly-api-production --region asia-south1 \
     --format="value(status.traffic[0].revisionName)"
   ```
   In Sentry, filter by release to see errors that started with it.
2. **Roll the traffic back** to the previous revision (no rebuild, no migration):
   ```bash
   export PROJECT_ID=project-19c38b75-2d9e-4394-ae1
   infra/scripts/rollback.sh production api
   infra/scripts/rollback.sh production web     # if the web changed too
   ```
3. **Watch the dashboard for 5 minutes.** The error rate should fall back to normal
   straight away.

## When it's not that simple

| Situation | Do this |
| --- | --- |
| The release had a migration | Usually just roll back the code: under expand/contract, the old code works with the new schema. Only reverse the migration if the old code truly can't run with it (`infra/ROLLBACK.md` §2). |
| A feature in the release is the problem, the rest is fine | Turn off its feature flag (if it has one) instead of rolling back |
| A bad secret or config | Disable that secret version and restart (`infra/ROLLBACK.md` §4) |
| The deploy corrupted data | Roll back first, then [database-restore.md](database-restore.md) |
| The next deploy would bring the bug back | Revert the commit on `main`; don't tag a new production release until the fix is in |
| Mobile app release | Halt the staged rollout in the Play Console and App Store Connect. Users who already have the build keep it, so a fix-forward release is the real fix. Use a feature flag to switch off the broken path server-side meanwhile. |

## Afterwards

- **Fix forward:**
  1. Merge the fix to `main`. Staging deploys automatically.
  2. Check it on staging.
  3. Tag a release and approve the production deploy.
- **Review:** say why tests, staging or the canary candidate URL didn't catch it.
