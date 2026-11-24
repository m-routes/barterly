# Stuck payouts

**You'll notice it from:**
- **Alerts:** "Backlog: payouts stuck", "Scheduled job failed", or "Backlog job not
  reporting".
- **Support:** talent asking where their money is.

**Severity:** SEV2. It's SEV1 if payouts may be going to the wrong account.

`payout_run` runs every 20 minutes. It pays what releases owe, and retries failed
payouts after their back-off. A payout counts as stuck when it has been:
- in `creating` for more than 30 minutes (we never got the provider's answer), or
- in `processing` for more than a day (the bank hasn't confirmed).

## First five minutes

1. Back office → Money → Payouts, filtered by status. Note how many are stuck and
   since when.
2. **Is the payout job running at all?**
   ```bash
   gcloud scheduler jobs describe barterly-<env>-payout-run --location asia-south1
   gcloud logging read 'jsonPayload.ops_event="job_failed" AND jsonPayload.job="payout_run"' --limit 5
   ```
3. **If payouts might be going to the wrong place** (a bug, or account takeovers),
   flip the money kill switch now. Payouts wait; nothing is lost.

## Diagnose

| What you see | Likely cause | Check |
| --- | --- | --- |
| Many in `creating` | RazorpayX API down or rejecting us (credentials, IP allow-list, balance) | RazorpayX dashboard and status page; Sentry for the error |
| Many in `processing` for over a day | The bank or IMPS/NEFT is slow; we missed `payout.processed` | RazorpayX → Payouts → status; webhook delivery log |
| Failed with "insufficient balance" | The RazorpayX account needs topping up | RazorpayX balance; Finance tops it up |
| Payouts `on_hold` | Working as designed: account changed in the last 24 h, or first payout without an ID-verified badge | The talent's account page shows why |
| All jobs failing, or the backlog job silent | Cloud Scheduler can't reach the API (OIDC, the service account, or the API is down) | `gcloud scheduler jobs describe …`, its last attempt status, and the API's health |

## Fix

- **Provider back:** nothing to do. The next `payout_run` retries failed payouts after
  their back-off. To retry one now: back office → Payouts → Retry, or
  `POST /api/v1/admin/money/payouts/<id>/retry/` (Finance; note required; audited).
- **Missed webhook:** redeliver it from the RazorpayX dashboard (idempotent). The
  `payout_validations` job also asks about pending account checks every 10 minutes.
- **Run the job now** (it calls the API like the schedule does, with the API's full
  configuration):
  ```bash
  gcloud scheduler jobs run barterly-<env>-payout-run --location asia-south1
  ```
- **Scheduler itself broken:** call the job endpoint as the scheduler's service account
  while you fix it. This needs Service Account Token Creator on that account:
  ```bash
  API=https://<api host>
  TOKEN="$(gcloud auth print-identity-token \
    --impersonate-service-account=barterly-scheduler-<env>@<project>.iam.gserviceaccount.com \
    --audiences="$API")"
  curl -fsS -X POST -H "Authorization: Bearer $TOKEN" "$API/api/v1/jobs/payout_run/"
  ```
  Jobs take an advisory lock, so a manual run can't overlap a scheduled one.
- **Never** mark a payout paid by hand. Only the provider's webhook or the job may move
  it, so the ledger stays true.

## Afterwards

Reply to everyone who asked. The wallet already shows each payout's status and the
reason for any hold.
