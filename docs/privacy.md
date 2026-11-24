# Privacy

`apps/privacy` (backend); `/legal/*`, `/grievance`, **Console → Privacy** and
`/account/privacy` (web); Profile → **Privacy and your data** and the join and consent
screens (mobile).

> **Everything here needs a lawyer's review before launch.** The legal pages are
> marked as drafts on the site. Settings that hold legal choices are marked
> `LEGAL REVIEW NEEDED` in `config/settings/base.py`. The open questions are at the end of
> this document.

## Consent

Purposes: `terms`, `privacy` (required to use Barterly), and the optional `location`,
`social` and `marketing`.

- **Explicit and separate.** At sign-up (the role step, `POST /api/v1/me/role/`) the
  person ticks "I am 18 or older", the terms and the privacy policy, each separately
  with nothing pre-ticked. The client sends the version of each text it showed. The API
  records the two consents as two rows, each with its version, and audits the 18+
  declaration.
- **Versions.** `PRIVACY_DOCUMENT_VERSIONS` (settings) holds the current version of each
  document. The web keeps `LEGAL_VERSION` (`web/src/lib/legal/documents.ts`) and the app
  keeps `legalVersion` (`mobile/lib/src/privacy/legal.dart`), next to the texts they
  show. A version that isn't current is refused with 409 `document_changed`. **To
  change a text, bump all three together.**
- **Re-consent.** `GET /api/v1/me/` returns `needs_consent` when the terms or the privacy
  policy were never accepted, were withdrawn, or have a newer version. Web and mobile then
  show the consent page before anything else.
- **Withdrawal is as easy as giving.** `POST /api/v1/privacy/consents/` with
  `granted: false` is the same call, one click (web) or one switch (mobile). The required
  two can't be withdrawn on their own (409 `consent_required`); deleting the account
  withdraws them.
- **Records.** `ConsentRecord` rows are append-only (the ORM refuses updates). The newest
  row per purpose is the current choice. Every change also writes an audit entry
  (`privacy.consent_given` / `privacy.consent_withdrawn`) with the IP and request id.
- **Enforcement.**
  - `location`: a check-in pass keeps the talent's location only with consent;
    otherwise it is dropped (`apps/attendance/views.py`).
  - `social`: post stats stop being fetched once the talent withdraws
    (`apps/deliverables/services.refresh_all`).
  - `marketing`: there are no marketing messages yet. Anything that sends them must check
    `consents.has_consent(user, "marketing")`.

## Your rights

| Right | API | Web | Mobile |
|---|---|---|---|
| Access and portability | `POST /privacy/exports/`, then `POST /privacy/exports/{id}/link/` | Privacy → Download your data | Download my data (JSON) |
| Correction | profile `PATCH`; `POST /privacy/corrections/` for the rest | Privacy → Correct your data | Ask for a correction |
| Erasure | `POST` / `GET` / `DELETE /privacy/deletion/` | Privacy → Delete your account | Delete my account |
| Withdraw consent | `POST /privacy/consents/` | Privacy → Your consents | Your consents |
| Grievance | `GET /privacy/grievance-officer/` (public) | `/grievance`, footer of every public page | Grievance Officer |

**Export.** One JSON file with every table that links to the person. The sections are
listed in `apps/privacy/services/registry.py`, and secrets and internal keys are left out.
It is written to the media bucket and kept for `PRIVACY_EXPORT_KEEP_HOURS` (24), and
there are at most `PRIVACY_EXPORTS_PER_DAY` (3) a day. Each link is a signed GCS URL
valid for `PRIVACY_EXPORT_URL_SECONDS` (300). Creating an export and fetching each link
are audited.

**The registry test.** `apps/privacy/tests/test_registry.py` fails when any model gains a
foreign key to the user that is neither exported nor listed in `UNEXPORTED_LINKS` with a
reason. A new table can't escape export and erasure unnoticed.

**Corrections.** People edit their profile themselves. For anything else (their phone
number, a name on a signed agreement, a verification result) they file a
`CorrectionRequest`, which staff resolve in the admin (Privacy → Correction requests),
audited.

## Deleting an account and anonymisation

1. `POST /privacy/deletion/ {"confirm": true}`. It is refused (409 `deletion_blocked`,
   with `details.blockers`) while there are active bookings, money held or being paid
   out, pending payouts or an open plan.
2. Deletion is scheduled `PRIVACY_DELETION_GRACE_DAYS` (7) ahead, and the person can
   cancel until then.
3. The `privacy_deletions` job (daily, 04:30 IST) runs `erasure.anonymise()`. If
   something blocks it by then, it is postponed a day and audited.

What happens to each kind of record:

| Record | What happens |
|---|---|
| User row | Kept (others point at it). Phone becomes `del-<random>`, email removed, password unusable, `is_active` off, refresh tokens blacklisted. The same phone can sign up again as a new account. |
| Profiles | Name becomes "Deleted member". Bio, DOB, emergency contact, city, handle, skills, business contact, address, GSTIN and website are removed; the profile is soft-deleted. |
| Uploads | Files and resized copies are deleted from the bucket; the rows are soft-deleted. |
| Properties, gigs | Address, directions, pincode and exact location are removed. Open gigs are closed (audited). |
| Applications, notes, interviews | Pitch, answers, attachments, interview links and notes are removed. Status history stays. |
| Chat | Their messages become "Message removed: the sender deleted their account." Masked-contact originals and report notes are removed. |
| Devices, settings, saved searches, scores | Deleted. |
| Notifications | Titles, bodies and links are removed; the retention job deletes the rows later. |
| **Payments and ledger** | **Kept unchanged.** Ledger, escrow and payouts hold amounts, gateway references and the anonymous user id, not names. Payout accounts are deactivated (the display was already masked). |
| **Invoices** | **Kept** (GST law). The buyer details a tax invoice must show stay; only the email is removed. |
| **Agreements** | **Kept.** Versions, terms and PDFs stay. Signatures keep the document hash, provider reference, consent text and time; the signer's phone is masked to its last four, and IP, user agent, device and OTP uid are removed. The DB trigger allows exactly these columns, only inside the erasure transaction (`barterly.erasure`, migration `agreements/0003_signature_erasure.py`). |
| **Disputes** | **Kept.** The app that holds them (`apps.safety`, separate branch) registers its own anonymiser with `erasure.register_anonymiser()`. |
| **Audit log** | **Kept.** Phone numbers, emails, names, notes and bodies inside before/after become `[erased]`. This is the only sanctioned rewrite of the log, and it writes `privacy.account_anonymised` itself. |
| Reviews | Published reviews are frozen by a trigger and stay, by "Deleted member". Unpublished drafts lose their text. |
| Verification | Status and the masked last four stay (fraud checks); case details and metadata are removed. |
| Consent records | Kept as proof of consent; they name no one once the user row is anonymous. |

## Retention

`PRIVACY_RETENTION_DAYS` sets the period for each kind. The `privacy_retention` job (daily,
04:00 IST, `infra/terraform/modules/environment/scheduler.tf`) runs
`retention.purge()`. That writes one `privacy.retention_purge` audit entry per kind it
touched, with the count, the period and the cut-off.

| Kind | Default | What is purged |
|---|---|---|
| `notifications` | 180 days | Sent or failed notifications (rows). Queued ones are never purged. |
| `push_devices` | 270 days | Devices not seen since. |
| `chat_leakage_bodies` | 90 days | The original text of messages whose contact details were masked. |
| `gateway_payloads` | 180 days | Razorpay webhook bodies (payments, billing); the event id and outcome stay. |
| `attendance_locations` | 30 days | Location on check-in passes after the pass expires. |
| `verification_references` | 365 days | A referee's name and phone, once the reference check is decided. |
| `job_runs` | 90 days | Scheduled job records. |
| data exports | 24 hours | The export file in the bucket. |

Kept for legal reasons and never purged by the job (`retention.KEPT`): the ledger and
payments, and invoices (8 years); agreements (term plus 3 years); the audit log (8
years); consent records (life of the account plus 8 years). These periods need legal
confirmation.

## KYC data

The ID and selfie check runs at the KYC provider. We receive its reference, the outcome
and the ID's last four characters. Checked on this branch:

- `VerificationDocument.masked_value` is 4 characters at most, and a check constraint
  refuses an upload of any ID document type.
- Webhook deliveries store no payload (`KycWebhookEvent`).
- **Fixed:** the last four are now normalised to letters and digits
  (`kyc.masked_last_four`). Before, a provider value like `"12 34"` was stored as is.
- **Fixed:** the provider's free-text reason (shown to the user and written to the audit
  log) now has anything that looks like an Aadhaar, PAN or other long number masked
  (`kyc.safe_reason`).
- On erasure, case details and metadata are removed; status and the masked four stay.

## Age (18+)

- **Sign-up:** "I am 18 or older" must be ticked at the role step (`confirm_adult`), and
  is audited (`user.declared_adult`).
- **Profile:** `TalentProfile.date_of_birth` must be 18 or more years ago
  (`validate_adult`).
- **A minor found later** (`apps/privacy/services/minors.py`):
  1. `flag()`: an under-18 date of birth from someone who declared 18+, or a case a staff
     member adds in the admin (Privacy → Minor cases). The account is suspended at once
     (a ban through `apps.safety.enforcement.suspend` when that app is installed,
     otherwise `is_active` is turned off). Open applications are withdrawn through the
     lifecycle (so hosts are told), the profile is hidden, the trust team is emailed
     (`TRUST_TEAM_EMAILS`, the case id only, no personal data), a
     `privacy.minor_flagged` event is published, and it is all audited. The profile
     `PATCH` returns 403 `underage`, and the date isn't saved.
  2. The trust team decides in the admin, which needs the `privacy.decide_minor_case`
     permission. **Confirm** runs the same anonymisation as account deletion. **Clear**
     (with the reason in the case note) lifts the suspension and shows the profile again.

## Public pages (web)

`/legal/terms`, `/legal/privacy`, `/legal/community-rules` and `/legal/refunds` each
carry a "Draft for lawyer review" banner. `/grievance` shows the officer's details from
`GRIEVANCE_OFFICER` (settings, via the API). The footer of the landing page, the sign-in
page and every legal page links to all five.

## Open legal questions

1. **Agreement evidence vs erasure.** Masking the signer's phone and dropping IP and
   device weakens the e-sign evidence trail. Is the provider's own audit trail plus the
   document hash enough under the IT Act (s.3A, Second Schedule) and the Evidence Act
   (s.65B), or should these fields be kept until limitation expires?
2. **Retention periods.** Confirm 8 years for payments, invoices and the audit log
   (Income Tax Act s.44AA, CGST Act s.36), agreement term plus 3 years (Limitation Act),
   and each period in `PRIVACY_RETENTION_DAYS`.
3. **Audit-log scrubbing.** Is rewriting personal values inside audit entries
   acceptable, or should the log keep them under legal hold with restricted access?
4. **Location and social consent basis.** Social stats are fetched unless consent is
   *withdrawn* (treated as needed to perform the agreement). Location is stored only
   with consent *given*. Are both bases right under the DPDP Act s.7?
5. **Grace period.** Is a 7-day grace before erasure acceptable, given DPDP Act s.12(3)?
6. **Firebase and processors.** The phone number also sits in Firebase Auth, the KYC
   provider, RazorpayX (contact and fund account) and the e-sign provider. Erasure
   doesn't yet ask them to delete. This needs a process, or API calls once the
   contracts allow it.
7. **Minors.** Is suspending and then purging right? Is any notice to a parent or
   guardian needed (DPDP Act s.9), and should the record of the case be kept, and for
   how long?
8. **Nominee.** DPDP Act s.14 (the right to nominate) has no flow yet.
9. **Consent Managers.** Is registration with a Consent Manager (DPDP Act s.6(7)) needed?
10. **Grievance timelines.** Confirm 24-hour acknowledgement and 15-day resolution (IT
    Rules 2021 r.3(2)) and the officer's name and address.
11. **The drafts.** The terms, privacy policy, community rules and refund policy are all
    first drafts with placeholders.
