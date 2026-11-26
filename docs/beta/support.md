# Support

## How people reach us

- **App:** Profile → *Help and feedback*.
- **Web:** console → *Help* (hosts), or `/account/help` (anyone signed in).

They choose what it's about, give it a title and write. Each request gets a reference
(`S-1A2B3C4D`) and a thread; our replies arrive as a notification ("Support replied")
and in the thread. Writing back on a resolved request reopens it.

## SLAs

During the beta, support is staffed **8am to 10pm IST, every day**.

| What it's about | Priority | First answer | Resolved within |
| --- | --- | --- | --- |
| A safety concern, Money or payments | Urgent | 2 hours | 24 hours |
| Help with something, Something isn't working | Normal | 24 hours | 72 hours |
| Feedback or an idea | Low | 72 hours | (no target) |

The clocks run from when the request arrives, around the clock; the staffed hours are
why urgent targets are 2 hours, not 30 minutes. The hours are settings
(`SUPPORT_SLA_*_HOURS`).

**Safety requests:** answer with the "Safety: are you safe right now?" reply, then
follow [the safety incident runbook](../runbooks/safety-incident.md). Never wait for
the SLA.

## The inbox

Back office → **Support inbox** (Support, Ops and Trust roles).

- Past-SLA requests come first, then urgent ones, then by when an answer is due.
- Open a request to read the thread, assign it to yourself, answer, add an internal
  note (never shown to the person), or mark it resolved. Answering moves it to
  *waiting for the person* unless you choose another status.
- **Canned replies** are listed beside the thread; clicking one fills the answer box in
  the person's language (English or Hindi, from their notification settings). Edit
  them in the admin under Support → Canned responses. Six starters come with the
  migration.
- Every answer, note, assignment and status change is in the audit log.

**Monitoring:** the `ops_backlog` job counts requests past their SLA every 5 minutes
(`support_overdue`); an alert fires when any are overdue for 15 minutes
([runbook](../runbooks/support-backlog.md)).

**Email:** there's no email intake yet. If someone writes to support@barterly.in, reply
asking them to use Help and feedback, so the request gets an SLA and a timeline entry.

## A person's timeline

Back office → **Find a person (timeline)**, or the phone number on any request or in the
onboarding tracker. It shows everything in one list, newest first:

- what they did, and what was done to their account (the audit log);
- booking status changes and applications;
- support messages, notifications sent, consent changes, and reports made or received.

At the side it shows their role, badges, invite code and cohort, consents and open
requests. Tick boxes narrow the list. **Opening a timeline is audited**, because it shows
a lot about one person. Open one only to help with a request or a case.
