# Closed beta

The beta opens Barterly to 150 invited properties and the talent they and we invite,
then widens step by step. Each step needs a **go** at the
[go/no-go review](go-no-go.md).

| Piece | Where | Doc |
| --- | --- | --- |
| Beta rules: invite codes, live-gig cap, stipend limit | `backend/apps/beta` | this page |
| KPIs and the dashboard | `backend/apps/analytics/kpis.py`, back office → Beta KPIs | [kpis.md](kpis.md) |
| Product analytics (with consent) | `backend/apps/analytics`, `web/src/lib/analytics`, `mobile/lib/src/analytics` | [analytics.md](analytics.md) |
| Help and feedback, the support inbox, timelines | `backend/apps/support`, web `/console/help` and `/account/help`, app Profile → Help and feedback | [support.md](support.md) |
| Weekly dispute and safety review | back office → Weekly dispute and safety review | [weekly-review.md](weekly-review.md) |
| Onboarding the first 150 properties | back office → Beta onboarding tracker | [onboarding/](onboarding/) |
| Go/no-go before each expansion | | [go-no-go.md](go-no-go.md) |

## The rules

All three apply while the **`closed_beta`** feature flag is on (back office → Feature
flags). Turning it off lifts them all at once; nothing else changes.

| Rule | Setting (default) | What people see |
| --- | --- | --- |
| Sign-up needs an invite code | `BETA_INVITE_ROLES` (`vendor,talent`) | An "Invite code" field at the last sign-up step. A missing code is 403 `invite_required`; a wrong, used, expired or other-role code is 400 `invite_invalid` with the reason. |
| A host can have at most N gigs live at once | `BETA_MAX_LIVE_GIGS_PER_VENDOR` (2) | "During the closed beta, each host can have 2 live gigs at a time." The plan's limit applies when it is lower. |
| A booking's stipend can be at most ₹X | `BETA_MAX_STIPEND_RUPEES` (20,000) | Offers (and counter-offers) above it are refused with a clear message. Funding refuses it too, for offers made before the flag. |

`GET /api/v1/beta/` (public) says which rules are on, so the apps show the invite field and
limits up front. The server enforces them regardless.

People who signed up before the flag was turned on keep their accounts; codes are only
asked for at sign-up.

## Invite codes

- **Make them:** back office → *Make invite codes*. One line per property (name and
  town, never a phone number) gives one labelled code each. Choose the cohort
  (`wave-1`, `wave-2`, …), the role and how long they last. Download the cohort as CSV
  to send.
- **Send them** by WhatsApp or SMS from the ops phone, with the
  [guide](onboarding/guide-en.md) ([हिंदी](onboarding/guide-hi.md)).
- **Revoke:** back office → Invite codes → select → *Revoke*.
- Codes are 8 characters without look-alikes (no 0/O, 1/I/L), shown as `ABCD-2345`;
  people can type them in any case, with or without the dash.
- Making, exporting, using and revoking codes are all in the audit log.

Talent invites: hosts can't make codes. Ops make a talent cohort (`talent-wave-1`) with
`max_uses` above 1 when a host or community wants to bring several people.

## Turning it on

1. Make the first cohort's codes and send them.
2. Back office → Feature flags → `closed_beta` → on, with the reason.
3. Check `GET /api/v1/beta/` says `"closed_beta": true`.

Turn it on **before** the apps are public in the stores: while it's off, anyone can sign up.
