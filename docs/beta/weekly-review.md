# Weekly dispute and safety review

During the beta, **every** dispute and safety report gets looked at by a person each
week, whatever its outcome in the moment. The point is to spot patterns early: a host
who keeps getting reported, a kind of gig that ends in disputes, a gap in the rules.

## What's in it

Back office → **Weekly dispute and safety review** (Trust and Ops roles). For the chosen
week (Monday to Sunday, IST):

- every booking moved to **disputed**, with the reason given;
- every **reported chat message**;
- every **reported review**.

Each row links to the record. Mark it reviewed with an outcome, plus notes for anything
but "no action":

- *Looked at: no action needed*;
- *Action taken* (warning, suspension, refund, rule change…);
- *Escalated* (founders, legal or police).

## When

**Every Monday, 11am IST, 45 minutes:** Trust lead (chairs), Ops lead, a founder, and
Support. Review last week's list top to bottom, record each outcome, and note patterns
in the meeting notes. Anything urgent is handled when it happens, not held for Monday.

## If it slips

Items from earlier weeks without a review show at the top of the page. The `ops_backlog`
job counts them (`safety_reviews_overdue`), and an alert fires if any stay unreviewed
([runbook](../runbooks/safety-incident.md)). The go/no-go review checks that nothing is
overdue.
