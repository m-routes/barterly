# Threat model

Three flows carry most of Barterly's risk: money moving from hosts to talent, contact
details unlocking when a booking is confirmed, and SOS. For each one this page lists
what's being protected, who might attack it, the abuse cases, and what stops each
abuse. A gap is marked **Open** and has an owner.

Method: STRIDE per flow, from the code as built (backend `apps/money`, `apps/bookings`,
`apps/safety`; the web BFF; the Flutter app). Review it when one of these flows
changes, and at least once a year alongside the secret-rotation drill
([security.md](security.md)).

## Actors and trust boundaries

| Actor | Trusted with |
| --- | --- |
| Talent, host (vendor) | Their own data and bookings. Phone ownership is proven by Firebase OTP. |
| Back-office staff | Only what their role grants (`apps/backoffice/roles.py`). Being staff alone grants nothing. |
| Razorpay, RazorpayX | Payment and payout state, which reaches us through HMAC-signed webhooks. |
| Cloud Tasks, Cloud Scheduler | Calling job endpoints, with OIDC tokens for our service accounts. |
| Emergency contact | An SOS message, and a live-location link while a share is active. |

The trust boundaries are: browser → web BFF (same origin, httpOnly cookies); app → API
(bearer JWT); API → Postgres, Cloud Storage and Secret Manager (service account);
providers → webhooks.

## 1. Money flow

The host funds escrow through Razorpay. The ledger holds it. Release happens on
approval or after auto-release. RazorpayX then pays the talent's verified account.
Details are in [money.md](money.md).

**Assets:** escrowed funds, payouts, the ledger's integrity, and payout account references.

| # | Abuse case | STRIDE | Controls | Residual |
| --- | --- | --- | --- | --- |
| M1 | A forged `payment.captured` webhook marks an unfunded escrow as held. | Spoofing | HMAC signature check with a per-webhook secret held in Secret Manager. The captured amount must match the quote exactly. The ledger posting is idempotent and keyed by payment id. | Low |
| M2 | A replayed webhook credits the same payment twice. | Tampering | Idempotency keys (`captured:<payment>`). Posting the same movement again returns the first one. Gateway event ids are stored. | Low |
| M3 | A host releases (or a talent self-approves) a deliverable on someone else's booking. | Elevation | Object-level checks: only the booking's host can review. The access-control walker tests every endpoint with a stranger's ids. | Low |
| M4 | An account takeover swaps the payout account to drain pending payouts. | Spoofing | A changed account holds payouts for 24 hours. The talent is notified and the change is audited. A penny-drop validation must pass before payouts resume. The first payout needs an ID-verified badge. | Medium: SIM-swap fraud defeats OTP. **Open:** step-up re-verification on account change (owner: payments). |
| M5 | An insider or compromised staff account pays out, refunds or splits escrow wrongly. | Elevation, Repudiation | Finance role only. Notes are required. Every decision is in `AuditLog`. The kill switch exists. A second person must approve large payouts (finance console branch). The ledger is append-only (DB triggers). | Low |
| M6 | Someone edits ledger rows directly to hide a theft. | Tampering | UPDATE and DELETE triggers on ledger tables. Daily reconciliation against the gateway highlights mismatches. | Low |
| M7 | Payout destination references leak from a database dump or backup. | Information disclosure | `fund_account_id` and `provider_contact_id` are AES-GCM encrypted per field. Bank details live only at RazorpayX; we keep a masked display. | Low |
| M8 | A tampered amount (floats, negatives, huge values) gets through. | Tampering | Integer paise only (`check_paise` refuses anything else). Serializers have min and max values. Request bodies are capped at 1 MB. | Low |
| M9 | Money moves while the gateway or the books look wrong. | DoS on integrity | The kill switch, which needs confirmation and is audited, stops releases and payouts. Reconciliation runs alert on mismatches. | Low |
| M10 | Card testing through the escrow funding endpoint. | Abuse | Funding requires a confirmed booking, so a signed agreement comes first. Razorpay risk checks apply. Per-user throttles apply. | Low |

## 2. Contact-unlock flow

When both sides sign, a booking becomes confirmed. While it is confirmed, checked-in
or delivering, each side sees the other's verified phone number. The talent also sees
the exact address and map pin. Before confirmation and after the stay, both see only
the approximate area (`bookings.confirmation.unlocked_details`,
`properties.services.can_see_exact_location`).

**Assets:** phone numbers, the exact location of homestays (often the host's home),
and the talent's identity.

| # | Abuse case | STRIDE | Controls | Residual |
| --- | --- | --- | --- | --- |
| C1 | Someone harvests phone numbers or addresses by enumerating booking or property ids. | Information disclosure | UUID ids. Bookings are scoped to their parties. The public property page carries no exact location. The walker fails on any stranger read and on any existence oracle (a different answer for real and made-up ids). | Low |
| C2 | A fake application or offer is made only to unlock contacts. | Spoofing | Unlock requires a confirmed booking, which needs both e-signatures. Signing needs OTP re-auth. Strikes, reports and bans apply (T&S). | Medium: a determined fake host can complete signing. Verification badges and reviews make this visible. |
| C3 | Unlocked details are kept after the stay ends. | Information disclosure | Unlock ends when the booking leaves `UNLOCKED_WHILE`. Chat continues inside the app. | Medium: anyone can screenshot. Policy and reports apply. |
| C4 | Staff read exact addresses without a reason. | Elevation | Needs `properties.view_property` (Ops, Trust, Support). Admin views are audited. | Low |
| C5 | A user is harassed off-platform after unlock. | Abuse | Block, report, strikes and bans (T&S). Masked numbers are a possible future change. | **Open:** number masking (owner: trust and safety). |
| C6 | Location leaks through photo EXIF data. | Information disclosure | Uploads are processed server-side before serving. **Open:** confirm EXIF stripping on every image type (owner: media). | Low to medium |

## 3. SOS flow

One tap sends the person's last known location and their booking to their emergency
contact and to the safety team. A live location share (time-limited, with consent, and
an indicator shown while it runs) gives a viewer link to the contact. This lives in
`apps/safety` on the trust and safety branch; [safety.md](safety.md) has the playbook.

**Assets:** the person's safety, their live location, and the emergency contact's details.

| # | Abuse case | STRIDE | Controls | Residual |
| --- | --- | --- | --- | --- |
| S1 | A false SOS is used to harass the other party or waste the safety team's time. | Abuse | Alerts are tied to the sender's account and booking. Misuse earns strikes. Every alert is audited and acknowledged by staff. | Low |
| S2 | An SOS fails to send when it matters (no network, no location permission, rate limit). | DoS | The alert is raised even with no location or a stale one. The app queues it and retries. SOS is never throttled like ordinary endpoints. The support pager is a second channel. | Medium: depends on SMS delivery. Checked in the incident drill. |
| S3 | The live-location viewer link leaks, so a stranger can track someone. | Information disclosure | Unguessable token. The share expires (minutes chosen up front) and the person can stop it any time. The viewer sees nothing once it ends. The link is never logged: logs and Sentry are redacted. | Medium: the link works for anyone holding it while active. |
| S4 | Location keeps being collected after the share ends. | Information disclosure | Background location is used only while a share is active. A visible indicator shows while it runs. Server-side expiry ignores late pings. | Low |
| S5 | The emergency contact leaks from the database, logs or crash reports. | Information disclosure | Name and phone are AES-GCM encrypted at rest. Log and Sentry redaction masks phone-shaped values and `emergency*` keys. The profile screen can't be screenshotted on Android and is covered in the app switcher. | Low |
| S6 | Someone triggers an SOS on another person's behalf, or reads their alerts. | Spoofing, Elevation | Alerts are created only for `request.user`. Staff need a Trust role to read them. The walker covers the endpoints. | Low |
| S7 | Staff read live locations without need. | Elevation | Trust role only, and each view is audited. | Low |

## Cross-cutting controls

- **Access control:** `apps/core/tests/test_access_control.py` tests every endpoint in
  the OpenAPI schema. It calls each one anonymously, as each role, as staff with no role,
  and with another user's ids. It fails on any leak, change or existence oracle.
- **Secrets:** all are in Secret Manager. The drill script is
  `infra/scripts/rotate-secrets.sh`.
- **Transport:** HTTPS only, HSTS (preload in production), CSP, no CORS. See
  [security.md](security.md).
- **Detection:** `AuditLog` covers every money and status change. Sentry receives only
  redacted events. The ZAP baseline runs after each staging deploy.

## Open items

| Item | Owner | Why it's open |
| --- | --- | --- |
| Step-up re-verification on payout account change (M4) | Payments | Needs a fresh OTP flow in the app and on the web. |
| Number masking for unlocked contacts (C5) | Trust and safety | Needs a telephony provider. |
| Confirm EXIF stripping for every upload type (C6) | Media | Not yet tested end to end. |
| A real malware scanner for uploads | Platform | Only the interface exists (`apps/media/scanning.py`); `MEDIA_REQUIRE_SCAN` is off. See security.md. |
| Inline scripts allowed by the web CSP | Web | Prerendered pages need them. See security.md, "Web CSP". |
