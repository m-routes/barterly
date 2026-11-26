# Service level objectives

These are the launch targets. Terraform defines the SLO in Cloud Monitoring
(`modules/environment/monitoring.tf`, `google_monitoring_slo.api_availability`), so
the budget is measured, not estimated.

## Availability: 99.5%

| | |
| --- | --- |
| **SLI** | Share of API requests that don't end in a 5xx, counted by Cloud Run (`run.googleapis.com/request_count`, `response_code_class != 5xx`) |
| **Objective** | 99.5% over a rolling 28 days |
| **Error budget** | 0.5% of requests. At steady traffic that's about 3 h 22 min of total outage per 28 days, or proportionally more partial failure. |
| **Excluded** | 4xx responses (the client's mistake or a refusal working as designed), and planned maintenance announced 48 hours ahead. |

The web app's availability follows the API's, because every signed-in page calls it.
The web's own uptime check and 5xx alert catch failures of the Next.js layer itself.

### Why 99.5% and not higher

There is one region, one Cloud SQL instance (regional HA in production), and
providers we don't control: Firebase OTP, Razorpay and RazorpayX. 99.9% would allow 40
minutes a month, which is less than a single Cloud SQL failover plus a provider blip.
Raise the target once we have three months of data showing we beat it comfortably.

## Latency (watched, not yet an SLO)

The alert fires at a p95 above 1.5 s for 10 minutes. The performance work targets a p95
under 300 ms for feed and search. Make latency an SLO once a month of production data
shows a stable baseline.

## Burn-rate alerts

These follow the SRE workbook's multi-window alerts, sent to `alert_emails`:

| Alert | Fires when | Budget spent if it continues | Response |
| --- | --- | --- | --- |
| Fast burn | 14.4× the sustainable rate over 1 hour | 2% per hour, all of it in about 2 days | Now: roll back first (bad-deploy runbook) |
| Slow burn | 6× over 6 hours | 5% per 6 hours | Same working day |

## Error budget policy

Count the budget left over the current 28 days (dashboard, SLO panel).

- **More than 50% left:** ship as normal.
- **25–50% left:** releases need the on-call engineer's OK, and risky features ship
  behind a feature flag ([operations.md](operations.md#feature-flags)).
- **Less than 25% left:** only fixes for reliability, security or data correctness ship,
  until the budget recovers.
- **Spent:** freeze feature releases. Write a short review of what spent it, and what
  will stop it recurring, before releases resume.

The person on call makes the call. Disagreements go to whoever owns engineering.
