# Money: the ledger and escrow

`apps/money` holds the stipend for paid and hybrid bookings from the host's payment to
the talent's payout. Treat it as the highest-risk module: every change here needs tests
that show the ledger still balances.

> **LEGAL REVIEW NEEDED.** The fund flow (the host pays into the platform's Razorpay
> account; payouts leave from a RazorpayX account, which must be funded from the gateway
> settlement) must be the structure your lawyer approves. Only the implementations in
> `apps/money/gateway/` would change.
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
  `release:<escrow>`, `payout:<attempt>`, `refund:<refund>`, ...). Posting
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
| `talent:payable` | liability | Released to talent, payout not yet made |
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
6. **Payout.** Made through the payout provider to the talent's verified payout account
   (Dr talent payable / Cr gateway). See [Payouts](#payouts).
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
- **Raised as an alert, never guessed at:**
  - a wrong amount
  - a second payment
  - a refund Barterly didn't make
  - a failed refund

## Reconciliation

The `escrow_reconcile` job runs daily at 02:30 IST. It compares yesterday's ledger
totals (captured, fees, refunded) with the gateway's report (`day_totals`), and the
payouts made (`paid_out`) with the payout provider's (`day_total`), and checks the trial balance. It stores a `ReconciliationRun` (re-running
a day replaces it).

Any difference raises an alert in three ways:
- an error log line, which Sentry picks up
- a `money.alert` audit entry
- an email to `ESCROW_ALERT_EMAILS`

Finance sees recent runs at `GET /admin/money/reconciliation/`.

A payout that fails on a later day than it was made shows as a difference on both
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

## Payouts

**Payout accounts** (`payout_accounts.py`, `PUT /api/v1/payout-account/`):
- A talent links a UPI id or a bank account (number, IFSC, name on the account). The
  shape is checked first.
- The details go to RazorpayX as a contact and a fund account. Only the provider's ids
  and a masked display (`as•••@okicici`, `HDFC0001234 ••••9012`) are stored. The full UPI
  id or account number is never stored, logged or audited.
- The provider validates the account with a ₹1 deposit or account check. The result
  arrives by webhook (`fund_account.validation.*`), or the `payout_validations` job asks
  for it. Payouts need `verified`. A failed check tells the talent why.
- Replacing an account holds payouts for `PAYOUT_ACCOUNT_CHANGE_HOLD_HOURS` (24) and
  sends an "Account security" notification on push, email and SMS. That type can't be
  switched off. The old fund account is deactivated, and the change is audited with the
  masked before and after.

**Payout runs** (`payouts.py`). A run looks at every released escrow whose payout isn't
under way, and for each one pays it, holds it, or leaves it:
- Held: `paused` (kill switch), `waiting_for_account` (no verified account), or
  `on_hold` (account changed in the last 24 hours, or the talent's first payout without
  an active ID-verified badge). The talent is told why.
- Left: a failed attempt still waiting out its back-off, or one that needs an admin.

Runs happen:
- after each release
- every 20 minutes (`payout_run`)
- when the talent asks (`POST /wallet/payout/`, at most once every 10 minutes)
- when an admin starts one (`POST /admin/money/payout-runs/`)

**Attempts.** Each attempt is a `Payout` row, committed as `creating` before the provider
is called, and its id is the provider's idempotency key. A crash mid-call leaves it
`creating`, and the next run resends it with the same key, so nothing is paid twice. The
database allows only one live attempt per escrow.
- The provider accepting the payout posts the ledger line (`payout:<attempt>`).
- `payout.processed` marks it paid, with the bank's UTR.
- `payout.failed`, `payout.rejected` or `payout.reversed` posts the reverse
  (`payout_reversed:<attempt>`) and records the provider's reason.
- A failed attempt is retried after 15 minutes, 1 hour, 4 hours and 12 hours. After the
  fifth attempt it raises an alert and waits for an admin
  (`POST /admin/money/payouts/<id>/retry/` with a note, which is audited).

**Admin.** `GET /admin/money/payout-runs/`, `GET /admin/money/payout-runs/<id>/` (with its
payouts) and `GET /admin/money/payouts/?status=failed&needs_admin=true` give the payout
run screen's data. Finance has `money.run_payouts`.

**Wallet** (`wallet.py`, `GET /api/v1/wallet/`):
- pending: held in escrow, with an estimate of what it would pay after commission, GST
  and TDS
- available: released, not yet paid out
- in transit
- paid out
- TDS this financial year
- why payouts are on hold, if they are

`GET /wallet/history/` lists releases and payout attempts, newest first, filtered by
`kind`, `status`, `start`/`end` (India dates) or `fy`.

**Statements and TDS** for an Indian financial year (`2026-27` = April to March, IST):
- `GET /wallet/statements/<fy>/` (JSON), `.../csv/` and `.../pdf/`: each release with
  gross, commission, GST on the commission, TDS, net, payout status, date and UTR.
- `GET /wallet/tds/<fy>/`, `.../csv/` and `.../pdf/`: TDS by quarter and by release, with
  the deductor (`BILLING_SUPPLIER`, `ESCROW_TDS_TAN`), the section
  (`ESCROW_TDS_SECTION`) and whether PAN is on file.

The TDS record is a summary. The certificate is Form 16A from TRACES. CSV files open
correctly in Excel (with a BOM) and are guarded against formula injection.

## Settings

| Setting | Default | |
|---|---|---|
| `ESCROW_GATEWAY` | Razorpay | Fake in tests |
| `RAZORPAY_ESCROW_WEBHOOK_SECRET` | | Secret Manager |
| `ESCROW_COMMISSION_BPS` | 800 | CA review |
| `ESCROW_GST_BPS` | 1800 | CA review |
| `ESCROW_GATEWAY_FEE_BPS` | 200 | Match the Razorpay contract |
| `ESCROW_TDS_ENABLED`, `_BPS`, `_NO_PAN_BPS`, `_THRESHOLD_PAISE` | on, 100, 2000, 0 | CA review |
| `ESCROW_AUTO_RELEASE_HOURS` | 72 | |
| `ESCROW_PAUSED` | false | The kill switch |
| `ESCROW_ALERT_EMAILS` | | Comma-separated |
| `ESCROW_TDS_SECTION`, `ESCROW_TDS_TAN` | 194-O, placeholder | CA review |
| `PAYOUT_PROVIDER` | RazorpayX | Fake in tests |
| `RAZORPAYX_ACCOUNT_NUMBER`, `RAZORPAYX_WEBHOOK_SECRET` | | Secret Manager |
| `PAYOUT_ACCOUNT_CHANGE_HOLD_HOURS` | 24 | |
| `PAYOUT_MAX_ATTEMPTS` | 5 | Then an admin retries |
| `PAYOUT_ON_DEMAND_EVERY_MINUTES` | 10 | |

## Not built yet

- The host's funding screen, the talent's submission screen, the wallet screens and the
  admin payout run screen. The API is ready for all of them.
- Asking for PAN (`pan_on_file` is only set by an admin for now). That waits on the KYC
  provider decision.
