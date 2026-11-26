# Payment mismatch

**You'll notice it from:**
- **Alerts:** "Ledger and gateway don't match" (the daily `escrow_reconcile` job at
  02:30 IST), "Webhook signature or format rejected", or "Signed webhook couldn't be
  applied".
- **Support:** a host says they paid but the booking shows unfunded.

**Severity:** SEV1 if money moved wrongly or may still be moving; otherwise SEV2.

## First five minutes

1. **Is money still going wrong?** If you aren't sure, turn on the money kill switch.
   It pauses escrow funding and payouts and keeps everything else running:
   - Back office: Money → Escrow control, or
   - `POST /api/v1/admin/money/kill-switch/` (Finance role; needs a reason; audited).
2. **If only new funding is the problem**, turn off the `escrow_funding` feature flag
   instead (Feature flags in the back office). Releases and payouts keep going.

## Diagnose

| What you see | Likely cause | Check |
| --- | --- | --- |
| Many `webhook_rejected` with `provider=razorpay`, all at once | A webhook secret was rotated in the Razorpay dashboard but not in Secret Manager, or the reverse | Razorpay dashboard → Webhooks → recent deliveries (signature failures) |
| Scattered `webhook_rejected` from unknown IPs | Someone probing the endpoint | Nothing to fix: the signature check is doing its job |
| `webhook_failed` | A signed event couldn't be applied (a bug, or the database) | Sentry for the exception; Razorpay retries the event for up to 24 hours |
| Reconciliation: `captured` differs | A payment captured with no webhook received, or the webhook rejected | Razorpay payments for that day vs ledger `escrow_funded` (back office: Reconciliation, mismatches highlighted) |
| Reconciliation: `refunded` or `paid_out` differs | A refund or payout webhook missed | Razorpay refunds; RazorpayX payouts for the day |
| Reconciliation: `trial_balance` | The ledger doesn't balance. This should be impossible. | **SEV1.** Don't post anything. Escalate. |
| `gateway` / `payout_provider` errors | The provider's reports API was down at 02:30 | Rerun the job (below) |

## Fix

- **Secret mismatch:** put the dashboard's current secret into Secret Manager
  (`razorpay-webhook-secret-<env>` or `razorpay-escrow-webhook-secret-<env>`), then
  `infra/scripts/rotate-secrets.sh <env> restart`. Then redeliver the failed events
  from the Razorpay dashboard. They're idempotent: anything already applied answers
  "duplicate".
- **Missed webhook:** redeliver it from the dashboard. If it's gone, the fix is a
  reversing or corrective movement, never an edit; ledger tables refuse UPDATE and
  DELETE. Finance decides the movement, and an engineer posts it with
  `ledger.post(kind, key, lines)` from a reviewed one-off script, with the incident in
  the memo.
- **Rerun reconciliation** (it re-checks yesterday's totals, and updates that day's
  report in the back office):
  ```bash
  gcloud scheduler jobs run barterly-<env>-escrow-reconcile --location asia-south1
  ```
- **When the numbers match again:** turn the kill switch or flag back on, with a reason.

## Afterwards

- List every booking whose money was affected, and confirm each with Finance.
- If a host was charged twice or a talent paid wrongly, Finance contacts them.
  Refunds and corrections go through the normal admin decisions, so they're audited.
