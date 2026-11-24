# Operations

This page covers how we know Barterly is healthy, what pages us, and the switches we
have when it isn't. The response steps are in the [runbooks](runbooks/README.md), and the
targets are in [slo.md](slo.md).

## Monitoring

Everything is in Terraform (`infra/terraform/modules/environment/monitoring.tf`), per
environment, with the dashboard named **Barterly staging** or **Barterly production**.

| Signal | Source | Alert (defaults) | Runbook |
| --- | --- | --- | --- |
| Error rate (api, web) | Cloud Run `request_count` 5xx share | > 2% over 10 min | [bad-deploy-rollback](runbooks/bad-deploy-rollback.md) |
| Latency (api, web) | Cloud Run `request_latencies` p95 | > 1.5 s for 10 min | [database-outage](runbooks/database-outage.md) |
| Instance count | Cloud Run `container_instance_count` | ≥ 80% of max for 10 min | (capacity: raise max with `db_tier`) |
| Task queue backlog | Cloud Tasks `queue_depth` | > 200 for 15 min | [otp-provider-outage](runbooks/otp-provider-outage.md) |
| Scheduled job failures | ops event `job_failed` | ≥ 3 in an hour | [stuck-payouts](runbooks/stuck-payouts.md) |
| Backlog job silent | ops event `backlog` absent | none for 20 min | [stuck-payouts](runbooks/stuck-payouts.md) |
| Stuck payouts | `backlog.payouts_stuck` | ≥ 1 for 15 min | [stuck-payouts](runbooks/stuck-payouts.md) |
| Stuck notifications | `backlog.notifications_stuck` | > 50 for 15 min | [otp-provider-outage](runbooks/otp-provider-outage.md) |
| Payment webhook rejected | ops event `webhook_rejected` | ≥ 5 in 10 min | [payment-mismatch](runbooks/payment-mismatch.md) |
| Payment webhook failed | ops event `webhook_failed` | any | [payment-mismatch](runbooks/payment-mismatch.md) |
| Reconciliation mismatch | ops event `reconciliation_mismatch` | any | [payment-mismatch](runbooks/payment-mismatch.md) |
| Notification dead letters | ops event `notification_dead_letter` | ≥ 10 in an hour | [otp-provider-outage](runbooks/otp-provider-outage.md) |
| Database connection errors | ops event `db_connection_failed`, request errors, Cloud SQL backends | any / ≥ 5 in 5 min / connections near the limit | [database-outage](runbooks/database-outage.md) |
| API down | Uptime check `/api/v1/health/`, 3 regions | failing from 2+ regions for 2 min | [database-outage](runbooks/database-outage.md) |
| Web down | Uptime check `/`, which must contain "Barterly" | same | [bad-deploy-rollback](runbooks/bad-deploy-rollback.md) |
| Sign-in broken | Synthetic sign-in: **not built yet** (see below) | (none) | [otp-provider-outage](runbooks/otp-provider-outage.md) |
| Availability SLO | Error-budget burn rate | fast 14.4×/1 h, slow 6×/6 h | [slo.md](slo.md) |

**Ops events** are structured log lines the API writes at the moment something goes
wrong (`apps/common/ops.py`). Terraform turns each one into a log-based metric.
- The names are an interface: `apps/common/tests/test_ops.py` fails if one has no
  metric.
- The `ops_backlog` job logs counts of waiting work every five minutes:
  - notifications queued for over 15 minutes;
  - dead letters in the last day;
  - payouts stuck in `creating` for over 30 minutes or in `processing` for over a day;
  - failed job runs.

### Turning alerts on

Alerts are created only when `alert_emails` is set for the environment
(`envs/<env>/terraform.tfvars`). Each address gets an email channel, and it must
confirm the first message. Without addresses, the metrics, uptime checks, dashboard
and SLO still exist. To add Slack or a pager later, add a notification channel next to
the email one in `monitoring.tf`.

### Synthetic sign-in (not built yet)

The API accepts only phone sign-in tokens, so a probe has to sign in the way a person
does. The plan is to use a Firebase **test phone number** with a fixed code (no SMS,
no real person):
- **Steps:** send the code → confirm it → exchange the token at `/api/v1/auth/exchange/`
  → `GET /api/v1/me/`, run every 10 minutes as a Cloud Monitoring synthetic monitor.
- **What it needs first:** a test number and code added in the Firebase console
  (Authentication → Sign-in method → Phone → Phone numbers for testing). That's a
  change to the Firebase project, so it's your call.

Until then, a broken sign-in shows up as failed `/auth/exchange/` requests in the API's
error rate, and as users reporting it.

## Errors: Sentry

| Where | What's set up | Release | Readable stack traces |
| --- | --- | --- | --- |
| API | `config/sentry.py`, off unless `SENTRY_ENABLED` and `SENTRY_DSN` are set | The git SHA, baked into the image (`GIT_SHA` build arg) | Python, natively |
| Web | `src/instrumentation.ts` (server) and `src/instrumentation-client.ts` (browser), off without `SENTRY_DSN` | The same SHA | Source maps uploaded during the deploy build, then deleted from the image |
| Mobile | `lib/src/crash/crash_reporter.dart`, off without `SENTRY_DSN` in `env/<env>.json` | `barterly@<pubspec version>` | `tool/build_release.sh` builds obfuscated and uploads the debug symbols |

Personal data stays out:
- The API redacts every event (`apps/common/redaction.py`).
- The web turns off all of Sentry 11's data collection (`DATA_COLLECTION`) and scrubs
  each event with the same rules (`src/lib/observability/scrub.ts`).
- Mobile has `sendDefaultPii` off.
- Browser events go through `/monitoring`, a same-origin tunnel, so the CSP doesn't
  change.

To turn it on:
1. Create Sentry projects for the API, web and mobile.
2. Put the DSN in the `sentry-dsn-<env>` secret and set `sentry_enabled = true`. The API
   and web share the secret; use separate projects if you want them apart.
3. Add the repository secret `SENTRY_AUTH_TOKEN`, and the variables `SENTRY_ORG` and
   `SENTRY_PROJECT_WEB`. The deploy workflow uses them to upload source maps.
4. Put the mobile DSN in `mobile/env/<env>.json`, and run release builds with
   `SENTRY_AUTH_TOKEN`, `SENTRY_ORG` and `SENTRY_PROJECT` set.

## Feature flags

These are switches for risky features. They take effect within 30 seconds and need no
deploy.

| Flag | Default | When off |
| --- | --- | --- |
| `escrow_funding` | on | New escrow funding gets a 503 with a message. Held money, releases and payouts carry on; the money **kill switch** stops those. |
| `sos_live_sharing` | on | New live-location shares are refused, with a message to call the emergency contact directly. Active shares run until they expire. **SOS alerts are never switched off.** |
| `ai_safety_checks` | on | New gigs skip the automated checks and go to the human review queue. |

How they work:
- **Who:** Ops, Trust and Finance (`flags.toggle_flag`), in the back office (Feature
  flags) or via `POST /api/v1/admin/flags/<key>/` with a reason. Every change is
  audited (`flags.changed`).
- **Clients:** apps read `GET /api/v1/flags/` to hide entry points. The server enforces
  the flag regardless.
- **Code:** `from apps.flags.services import is_enabled`. Add new flags to
  `apps/flags/registry.py`.

`escrow_funding` is enforced on this branch. `sos_live_sharing` and `ai_safety_checks`
are defined here. The SOS and gig-check code that reads them lives on the trust and
safety branch (`feat/safety`), and gets wired in when the branches meet.

## Backups

| | Production | Staging |
| --- | --- | --- |
| Database | Cloud SQL Postgres 16, regional HA | Cloud SQL, zonal |
| Daily backups | 02:00 IST, 30 kept | 02:00 IST, 7 kept |
| Point-in-time recovery | 7 days of transaction logs | 7 days |
| Media | Versioned bucket | Not versioned |

Checked live on 23 Nov 2026: every daily backup in the last three days succeeded, on
both environments. The restore drill, with its measured times, is in
[runbooks/database-restore.md](runbooks/database-restore.md).

## Not done yet

- **The synthetic sign-in probe isn't built.** Decide whether to add a test phone number
  first; the probe (a Cloud Function behind a synthetic monitor) follows from that.
- **The restore drill hasn't been run.** It reads the database password from Secret
  Manager and creates a billable instance, so a person runs it:
  `infra/scripts/restore-drill.sh`.
