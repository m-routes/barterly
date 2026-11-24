# UAT: Barterly admin (Ops, Trust, Finance)

Run it in the back office (`<API>/admin/`) with the admin persona, and again with a staff
account that has only one role, to check each role sees only its own work.

Tester · Date · Build · Role(s)

| # | Step | Expected | Pass | Fail | Notes |
| --- | --- | --- | --- | --- | --- |
| 1 | Sign in to the back office | The dashboard lists only the queues your role can use | ☐ | ☐ | |
| 2 | **Gig queue**: open a gig in review | The rules check, the vendor and the history are shown; Approve is off while a rule breaks | ☐ | ☐ | |
| 3 | Send one back with a note; approve another | The vendor gets the note; the approved gig goes live | ☐ | ☐ | |
| 4 | **Verification queue**: open a submitted business check | Documents, masked values, the history | ☐ | ☐ | |
| 5 | Approve one, reject one with a reason, ask for changes on one | Each vendor sees the outcome and the reason; badges update | ☐ | ☐ | |
| 6 | Sign in as a staff account with no role | No queues; API pages for bookings, KYC and media are refused | ☐ | ☐ | |
| 7 | **Money → Reconciliation**: open yesterday's run | Ledger and gateway totals; any mismatch highlighted | ☐ | ☐ | |
| 8 | **Money → Escrow**: decide a disputed (held) escrow as a split | A note is required; the refund and release happen; audited | ☐ | ☐ | |
| 9 | Retry a failed payout | Needs a note; audited; the payout runs | ☐ | ☐ | |
| 10 | Turn the money kill switch on, then off | Needs confirmation and a reason; funding and payouts pause and resume | ☐ | ☐ | |
| 11 | **Feature flags**: turn `escrow_funding` off, then on | Hosts can't fund while it's off (clear message); audited; back within a minute | ☐ | ☐ | |
| 12 | **Audit log**: find today's actions from steps 3–11 | Every one is there with who, when and before/after | ☐ | ☐ | |
| 13 | Review the moderation queue: hide a reported review | It disappears from the profile; the author is told | ☐ | ☐ | |

**Result:** ☐ Pass ☐ Fail · Signed off by
