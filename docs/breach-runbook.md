# Personal data breach runbook

What to do when personal data may have been exposed, changed, lost or made unavailable
(a "personal data breach" under the DPDP Act, 2023 s.2(u)), or when a cyber security
incident CERT-In lists happens.

> **Draft for lawyer review.** Timelines below are from the CERT-In Directions of
> 28 April 2022 (under IT Act s.70B(6)) and the DPDP Act, 2023 s.8(6) with the DPDP Rules,
> 2025. Confirm them, and the contact addresses, before relying on this.

## Clocks start when anyone at Barterly becomes aware

| Deadline | What | Who sends it |
|---|---|---|
| **6 hours** from noticing | Report the incident to **CERT-In** (incident@cert-in.org.in, form on cert-in.org.in) if it is a reportable cyber incident: unauthorised access to systems or data, data breach or leak, compromise of accounts, malicious code, attacks on servers or apps, and the rest of CERT-In's Annexure I list. Report what is known; send the rest later. | Incident lead |
| **Without delay** | Tell the **Data Protection Board of India** of the personal data breach: what happened, the nature, extent, timing and location, and the likely impact. | Grievance Officer / DPO |
| **Without delay** | Tell **each affected person**: what happened, the likely consequences, what we are doing, what they can do to protect themselves, and who to contact. | Grievance Officer / DPO |
| **72 hours** from becoming aware (or longer if the Board allows) | Send the Board the **detailed report**: facts and circumstances, the cause, mitigation, the people responsible if known, remedial measures, and the notices sent to affected people. | Grievance Officer / DPO with the incident lead |
| As agreed | Tell **Razorpay / RazorpayX**, the **KYC provider**, the **e-sign provider** and **Google Cloud** if their data or credentials are involved, and check our contracts for their notice periods. | Incident lead |
| 180 days | Keep the logs for CERT-In: in India, for 180 days (Cloud Logging retention, `infra/`). | Engineering |

When in doubt, report. A late report is a breach of the law on its own (DPDP Act
Schedule: up to ₹200 crore for failing to notify).

## Roles

Name one person for each role per incident, in the incident channel, in the first 15
minutes. A person may hold two roles, but the incident lead and the communications lead
should be different people.

| Role | Who (fill in) | Does |
|---|---|---|
| **Incident lead** | [Head of engineering], backup [on-call engineer] | Runs the response, makes the containment calls, owns the CERT-In report and the timeline. |
| **Grievance Officer / DPO** | [Name, from `GRIEVANCE_OFFICER`] | Owns the Board notices and the notices to affected people; the point of contact for regulators. |
| **Engineering on-call** | [Rotation] | Contains, preserves evidence, finds the scope from logs and the audit log. |
| **Communications lead** | [Founder / ops] | Notices to affected people, the support script, any public statement. |
| **Legal counsel** | [Firm, contact] | Reviews every notice before it goes; advises on police complaints (IT Act s.43, s.66) and contracts. |
| **Trust and safety** | [Lead] | Watches for misuse of the leaked data (impersonation, harassment), and handles affected users' reports. |

## Steps

### 1. First hour: confirm and contain

1. Open the incident channel and note the **time of discovery** (this starts the clocks).
2. Name the roles (table above).
3. Contain without destroying evidence:
   - Rotate exposed secrets in Secret Manager (`infra/scripts/set-secrets.sh`): Django
     `SECRET_KEY`, the field-encryption key, Razorpay and RazorpayX keys, KYC and webhook
     secrets, the attendance signing key, and the Firebase service account.
   - Revoke sessions if accounts are compromised: blacklist refresh tokens, and force
     sign-out with the Firebase Admin SDK (`revoke_refresh_tokens`).
   - Pause money if payments or payouts are at risk: Admin → Money → Escrow control (the
     kill switch), or set `ESCROW_PAUSED=1`.
   - Lock down storage if the media bucket is exposed: remove public IAM bindings and
     rotate signing service-account keys.
   - Roll back a bad release if one caused it (`infra/ROLLBACK.md`).
4. Preserve evidence: export Cloud Logging, Cloud SQL audit logs and the app's
   `AuditLog` for the window; take a Cloud SQL backup; snapshot the affected
   resources. Don't delete anything.

### 2. Within 6 hours: CERT-In

Send the CERT-In report (template A) with what is known. Note the time sent.

### 3. Scope: who and what

- Which data types (use the inventory in `apps/privacy/services/registry.py` and
  [privacy.md](privacy.md)): phone numbers, names, DOB, emergency contacts, location,
  messages, KYC outcomes (last four only), payout references (masked), invoices.
- Which people: build the list from logs and the audit log, then pull contact details
  (the phone, plus email where held) for the notices. Keep the list in the incident
  folder with restricted access.
- Whether anyone under 18 is involved (there should be no such accounts; see the minor
  cases in the admin).

### 4. Without delay: the Board and the people affected

Send template B to the Board and template C to each affected person (in-app
notification, email or SMS, whichever we hold). Counsel reviews both first.

### 5. Within 72 hours: the detailed report to the Board

Template D. If the facts aren't all known, send what is known and ask the Board for more
time, in writing.

### 6. Afterwards

- A blameless post-mortem within 2 weeks: the timeline, the root cause, what worked, and
  the follow-ups with owners.
- Update this runbook, `docs/security.md` and `docs/threat-model.md` (security branch).
- Keep the incident record (timeline, reports sent, evidence index) for at least 8
  years.

## Templates

Fill in the [brackets]. Keep the language plain. Counsel reviews every notice before it is sent.

### A. CERT-In incident report (6 hours)

> **To:** incident@cert-in.org.in
> **Subject:** Incident report: [Company name], [type of incident], noticed [date time IST]
>
> Organisation: [Company name], [address]. Sector: online marketplace (travel and
> hospitality work exchange).
> Point of contact: [name, designation, phone, email].
> Time of occurrence: [date time IST or "unknown"]. Time noticed: [date time IST].
> Type of incident (Annexure I): [e.g. data breach / unauthorised access to IT systems].
> Systems affected: [e.g. Cloud Run API, Cloud SQL database, media bucket], hosted on Google
> Cloud, region [asia-south1].
> What happened, as known now: [two or three sentences].
> Actions taken: [containment so far].
> Indicators: [IPs, accounts, file hashes, if known].
> We will send updates as we learn more.

### B. Intimation to the Data Protection Board (without delay)

> **To:** Data Protection Board of India [address or portal]
> **Subject:** Intimation of personal data breach: [Company name]
>
> [Company name], a Data Fiduciary, reports a personal data breach that it became aware
> of on [date time IST].
>
> - What happened: [description, including the nature and extent].
> - When and where: [timing; systems and locations].
> - Personal data involved: [categories].
> - People affected: [number, or best estimate].
> - Likely impact on them: [e.g. risk of phishing calls to the leaked phone numbers].
> - What we have done: [containment].
>
> A detailed report will follow within 72 hours. Contact: [Grievance Officer, email,
> phone].

### C. Notice to an affected person (without delay)

> **Subject / title:** Important: your Barterly data was involved in a security incident
>
> Hello [name or "there"],
>
> On [date], we found that [plain description, e.g. "someone without permission accessed
> a copy of part of our database"]. Your [data types, e.g. "phone number and profile
> name"] [were / may have been] included. [Your payment details and ID documents were not
> affected: we never store them.]
>
> **What this could mean for you:** [e.g. you may get calls or messages pretending to be
> Barterly].
>
> **What we've done:** [e.g. closed the gap, reset access keys, told the authorities].
>
> **What you can do:**
> - Barterly will never ask for your OTP, password or bank PIN. Don't share them.
> - [Specific step, e.g. "Sign in again; we signed everyone out."]
> - Report anything suspicious from Profile → Privacy, or to the contact below.
>
> If you have questions, contact our Grievance Officer: [name], [email], [phone].
> You can also complain to the Data Protection Board of India.
>
> We're sorry this happened.
> [Name], [Company name]

Send it in English and in the person's app language where we have a translation; SMS
gets a short form with a link to the full notice.

### D. Detailed report to the Board (72 hours)

> **Subject:** Detailed report: personal data breach intimated on [date]
>
> 1. Updated facts: [what, when, how discovered, timeline].
> 2. Circumstances and cause: [root cause, as found].
> 3. Personal data and people affected: [categories; numbers by type].
> 4. Mitigation: [what was done to contain it and reduce the risk to people].
> 5. Who caused it, if known: [internal / third party / unknown].
> 6. Remedial measures to stop it happening again: [list with dates].
> 7. Notices to affected people: [when, how, how many; attach the notice].
> 8. Contact: [Grievance Officer].

### E. Support script (for anyone answering users)

- Confirm the incident happened, and what data it involved, using the notice wording only.
- Never ask for an OTP or ID.
- Point to Profile → Privacy (to download or delete their data) and to the Grievance
  Officer.
- Log every contact in the incident folder.

## Practise it

Run a tabletop exercise every 6 months: a leaked database backup, a compromised staff
account, an exposed bucket. Time each step against the clocks above.
