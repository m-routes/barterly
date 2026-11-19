# Money: the ledger and escrow

`apps/money` holds the stipend for paid and hybrid bookings from the host's payment to
the talent's payout. Treat it as the highest-risk module: every change here needs tests
that show the ledger still balances.

> **LEGAL REVIEW NEEDED.** The fund flow (the host pays into the platform's Razorpay
> account; payouts go to talent through Razorpay Route linked accounts) must be the
> structure your lawyer approves. Only `apps/money/gateway/route.py` would change.
>
> **CA REVIEW NEEDED.** The commission, GST, TDS and gateway-fee settings below are
> placeholders for your chartered accountant to confirm.

## Rules

- **Integers only.** Amounts are whole paise in `BigIntegerField`s. Rates are basis
  points (800 = 8%). `ledger.share()` rounds half up in integer arithmetic. Rupee strings
  from agreement terms are parsed with `Decimal`, never a float. `check_paise()` refuses
  floats, Decimals and bools.
- **Double entry.** Money moves only through `ledger.post(kind, key, lines)`. It writes
  one `LedgerTransaction` and its `LedgerEntry` lines in one database transaction. Each
  line debits one account and credits another for the same amount, so every movement
  balances by construction. `ledger.is_balanced()` checks the whole book.
- **Idempotent.** Each movement has an idempotency key (`captured:<payment>`,
  `release:<escrow>`, `payout:<escrow>:<transfer>`, `refund:<refund>`, ...). Posting
  the same movement again returns the first one. Posting a different movement under a
  used key is an error, never an overwrite.
- **Append-only.** Database triggers (migration `money.0002`) refuse UPDATE and DELETE on
  the ledger tables, whoever runs them. A mistake is corrected by a reversing movement.
- **Audited.** Every escrow change, webhook effect, admin decision and kill-switch flip
  writes an `AuditLog` entry (`money.*`).

## Accounts

| Code | Kind | Holds |
|---|---|---|
| `gateway:clearing` | asset | Money at the gateway |
| `escrow:held` | liability | Stipends held for bookings |
| `talent:payable` | liability | Released to talent, transfer not yet made |
| `revenue:commission` | revenue | Barterly's commission |
| `revenue:fee_recovery` | revenue | The gateway fee the host pays |
| `tax:gst_output` | liability | GST collected (on the commission and on the fee recovery) |
| `tax:gst_input` | asset | GST the gateway charged us on its fee |
| `tax:tds_payable` | liability | TDS withheld from talent |
| `expense:gateway_fees` | expense | The gateway's fee |
| `equity:adjustments` | equity | Manual corrections |

## The flow

1. **Quote.** The stipend comes from the agreement in force. Weekly and monthly stipends
   are prorated by day (`amount x days / 7` or `/ 30`, rounded half up). The host pays
   stipend + gateway fee (`ESCROW_GATEWAY_FEE_BPS`) + GST on that fee.
2. **Funding.** `POST /bookings/<id>/escrow/fund/` (host, confirmed booking) creates a
   Razorpay order. When `payment.captured` arrives with the exact total, the escrow is
   `held`:
   - Dr gateway / Cr escrow (stipend)
   - Dr gateway / Cr fee recovery (fee)
   - Dr gateway / Cr GST output (GST on the fee)
   - Dr gateway fees / Cr gateway, and Dr GST input / Cr gateway (what the gateway charged)
3. **Check-in.** A paid or hybrid booking can't check in until its escrow is held
   (`bookings.lifecycle._stipend_funded`).
4. **Deliverables.** The talent hands in work (`POST /bookings/<id>/deliverables/`). The
   host approves it, which releases the escrow, or asks for changes with a note
   (`POST /deliverables/<id>/review/`).
5. **Release.** This happens on approval, or through the `escrow_auto_release` job when
   the latest submission has had no answer for `ESCROW_AUTO_RELEASE_HOURS` (72). An
   approval that couldn't release at the time (because of the kill switch, say) is
   retried by the same job. The released amount is split as follows:
   - commission: `ESCROW_COMMISSION_BPS` (800)
   - GST on the commission: `ESCROW_GST_BPS` (1800)
   - TDS (`ESCROW_TDS_*`): 1% with PAN, 20% without, above a per-release threshold
   - the remainder goes to talent payable

   Each part is one line out of `escrow:held`.
6. **Payout.** A Route transfer to the talent's `PayoutAccount` (Dr talent payable /
   Cr gateway). With no active account it waits (`waiting_for_account`). The escrow is
   marked `sending` in its own commit before the call, so a crash can't send twice. A
   stuck `sending` is left for a person, who can check it against the reconciliation.
   `transfer.processed` marks it settled (`paid_out`). `transfer.failed` reverses the
   ledger line, and `escrow_retry_payouts` sends it again.
7. **Refunds.** Cancelling a funded booking before any release refunds the stipend; the
   gateway fee isn't refunded. If the refund can't run then, an audit entry
   (`money.refund_needed`) is left instead of blocking the cancellation. The ledger
   records the refund (Dr escrow / Cr gateway) when `refund.processed` arrives. A payment
   that is captured after its booking ended is refunded automatically.
8. **Disputes.** `booking.disputed` freezes the escrow. Neither approval nor auto-release
   can release it. A finance admin decides with
   `POST /admin/money/escrows/<booking>/decide/`:
   - `release`
   - `refund`
   - `split` with `talent_paise`: the rest is refunded first, then the talent's share is
     released and paid out as usual

   A note is required, and the decision is audited.

## Webhooks

`POST /api/v1/money/webhooks/razorpay/` is a separate Razorpay webhook with its own
secret, `RAZORPAY_ESCROW_WEBHOOK_SECRET`.

- **Verification.** `X-Razorpay-Signature` (HMAC-SHA256 of the body) is checked first.
  `X-Razorpay-Event-Id` is stored in `GatewayEvent` (unique) in the same transaction as
  the event's effects, so a redelivered event changes nothing.
- **Events handled:**
  - `payment.captured`, `payment.failed`
  - `refund.processed`, `refund.failed`
  - `transfer.processed`/`transfer.settled`, `transfer.failed`
- **Raised as an alert, never guessed at:**
  - a wrong amount
  - a second payment
  - a refund Barterly didn't make
  - a failed refund

## Reconciliation

The `escrow_reconcile` job runs daily at 02:30 IST. It compares yesterday's ledger
totals (captured, fees, refunded, transferred) with the gateway's report
(`day_totals`) and checks the trial balance. It stores a `ReconciliationRun` (re-running
a day replaces it).

Any difference raises an alert in three ways:
- an error log line, which Sentry picks up
- a `money.alert` audit entry
- an email to `ESCROW_ALERT_EMAILS`

Finance sees recent runs at `GET /admin/money/reconciliation/`.

A transfer that fails on a later day than it was made shows as a difference on both
days. Check those by hand.

## The kill switch

The switch is on when either of these is set:
- `ESCROW_PAUSED=true`, for a deploy-time stop
- the `EscrowControl` row, set in admin or through `PUT /admin/money/kill-switch/` with a
  reason (needs `money.toggle_kill_switch`)

While it is on:
- new funding (503), releases, refunds and payouts stop
- approvals still record, and their release is retried later
- payouts wait as `paused`
- webhooks are still recorded

Turning it off lets the hourly and 20-minute jobs catch up.

## Settings

| Setting | Default | |
|---|---|---|
| `ESCROW_GATEWAY` | Razorpay Route | Fake in tests |
| `RAZORPAY_ESCROW_WEBHOOK_SECRET` | | Secret Manager |
| `ESCROW_COMMISSION_BPS` | 800 | CA review |
| `ESCROW_GST_BPS` | 1800 | CA review |
| `ESCROW_GATEWAY_FEE_BPS` | 200 | Match the Razorpay contract |
| `ESCROW_TDS_ENABLED`, `_BPS`, `_NO_PAN_BPS`, `_THRESHOLD_PAISE` | on, 100, 2000, 0 | CA review |
| `ESCROW_AUTO_RELEASE_HOURS` | 72 | |
| `ESCROW_PAUSED` | false | The kill switch |
| `ESCROW_ALERT_EMAILS` | | Comma-separated |

## Not built yet

- The host's funding screen and the talent's submission screen. The API is ready for
  both.
- Onboarding talent to Route linked accounts (`PayoutAccount` rows), which depends on
  the KYC provider decision.
