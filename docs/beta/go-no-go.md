# Go/no-go review

Before each expansion step, the whole team meets to decide **go** or **no-go**. Each
item below is checked out loud and marked in the meeting notes. A **no-go** names the
items that failed, who fixes each, and when we meet again.

## Expansion steps

| Step | Who | Size |
| --- | --- | --- |
| 0 → Wave 1 | The first properties, by invite | 150 properties; talent by invite |
| Wave 1 → Wave 2 | More properties in the same regions | Up to 500 properties |
| Wave 2 → Wave 3 | New regions | Up to 1,500 properties |
| Wave 3 → Open | Anyone can sign up (`closed_beta` off) | – |

Run each wave for **at least four weeks**, so the 28-day KPIs mean something.

## Who

Founders (decide), Ops lead, Trust lead, Support lead, Engineering lead, Finance. If any
one of them says no-go on their own area, it's no-go.

## The checklist

### Marketplace (back office → Beta KPIs, 28-day window)

- [ ] Applications per gig **≥ 8**.
- [ ] Gigs filled within 14 days **≥ 70%**.
- [ ] No-shows **under 5%**.
- [ ] Stays completed **≥ 85%**.
- [ ] Disputes **under 3 per 100** stays started.
- [ ] Average rating **≥ 4.3**, for hosts and for talent separately.
- [ ] Host churn **under 20%**.
- [ ] Each KPI is based on enough to trust: at least 50 mature gigs and 50 stays.

### Safety and trust

- [ ] The weekly review is up to date: nothing overdue on the review page.
- [ ] No open safety incident, and none in the wave without a written follow-up.
- [ ] No pattern from the weekly reviews left without an owner.
- [ ] Verification queue: nothing waiting over 48 hours.

### Support

- [ ] Over the last 4 weeks, **95%** of first answers within SLA (inbox → past SLA).
- [ ] Nothing past its SLA today.
- [ ] Top 5 request topics written down, each with a fix shipped or planned.
- [ ] Canned replies reviewed for anything new.

### Money

- [ ] Reconciliation clean every day for the last 2 weeks (no `reconciliation_mismatch`).
- [ ] No payout stuck over 24 hours.
- [ ] The beta stipend limit (`BETA_MAX_STIPEND_RUPEES`) reviewed. Raise it only on a
      clean month.

### Reliability

- [ ] SLOs met over the last 28 days ([slo.md](../slo.md)), or error budget left.
- [ ] No open P1 or P2 incident.
- [ ] The restore drill has run this quarter ([runbook](../runbooks/database-restore.md)).
- [ ] Load: the next wave's expected traffic is within tested capacity.

### Operations for the next wave

- [ ] Invite codes made for the next cohort; the onboarding tracker shows the current
      wave at least **80%** at "first gig live".
- [ ] Support staffing for the next wave's size agreed.
- [ ] Beta limits for the next wave agreed (live gigs per host, stipend). Settings
      changed, or the flag turned off for Open.

## Notes template

```
Go/no-go: <from> → <to>, <date>
Present: …
KPIs (28 days to <date>): applications/gig …, fill …, no-show …, completion …,
  disputes … per 100, rating hosts … talent …, churn …
Failed items: …
Decision: GO / NO-GO
Actions: <item> — <owner> — <date>
Next review: <date>
```
