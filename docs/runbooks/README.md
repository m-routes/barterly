# Runbooks

Each runbook starts with how you'll notice the problem, then gives the first five
minutes, the diagnosis and the fix. Every alert's description links to its runbook
(`infra/terraform/modules/environment/monitoring.tf`).

| Runbook | For |
| --- | --- |
| [payment-mismatch.md](payment-mismatch.md) | The ledger disagrees with Razorpay, or payment webhooks are failing |
| [stuck-payouts.md](stuck-payouts.md) | Payouts not going out, or scheduled jobs failing |
| [otp-provider-outage.md](otp-provider-outage.md) | Sign-in codes not arriving; notifications backing up |
| [database-outage.md](database-outage.md) | Cloud SQL unreachable, slow or out of connections |
| [database-restore.md](database-restore.md) | Restoring data, and the restore drill |
| [bad-deploy-rollback.md](bad-deploy-rollback.md) | A release broke something |
| [safety-incident.md](safety-incident.md) | SOS alerts, threats to someone's safety, abuse |

Related: [../../infra/ROLLBACK.md](../../infra/ROLLBACK.md) (the rollback commands),
[../operations.md](../operations.md) (monitoring, Sentry, feature flags, backups),
[../slo.md](../slo.md) (targets and error budget) and
[../security.md](../security.md) (secret rotation).

## During any incident

1. **Say you've got it.** Acknowledge the alert, so nobody else starts the same thing.
2. **Stop the damage before finding the cause.** Roll back the deploy, turn off the
   feature flag, or flip the money kill switch. Each of these is fast and reversible.
3. **Keep a timeline.** In the incident note, write what you saw and what you did, with
   times in IST. The review is written from it.
4. **Tell people.**
   - **Users:** if they're affected for more than 15 minutes, put a notice on the
     status channels.
   - **Money:** if money or safety is involved, tell the founders straight away.
5. **Afterwards:** write a short review within 3 working days covering what happened,
   why, and what changes so it doesn't recur. No blame.

## Severity

| Level | Example | Response |
| --- | --- | --- |
| SEV1 | Money moving wrongly; SOS not working; everyone down; data exposed | Everyone available, now, at any hour |
| SEV2 | Sign-in down; payouts stuck for hours; one major feature down | On call now; others in working hours |
| SEV3 | Degraded but working; a backlog clearing slowly | Next working day |

A suspected data breach follows the breach runbook on the privacy branch
(`docs/breach-runbook.md`), with its legal notice deadlines.
