# Safety incident

**You'll notice it from:**
- an SOS alert (it pages the safety team directly, alongside the person's emergency
  contact);
- a report of threats, harassment or assault;
- a reported unsafe gig or host;
- a call or message from the police.

**Severity:** SEV1 while anyone may be in danger. **People come first, then the
platform.**

The safety team's full playbook, with response times and escalation, is
`docs/safety.md` on the trust and safety branch (`feat/safety`). This page covers the
engineering side: what the systems do, the switches, and keeping evidence.

## Someone may be in danger now

1. **If there's any risk to life,** the person or their contact should call **112**
   (India emergency). We say so in every reply, and staff call 112 themselves if they
   can't reach the person.
2. **Acknowledge the SOS** in the back office (Safety → SOS alerts), so the team knows
   who has it. Acknowledging is audited.
3. **Read what the alert carries:**
   - the last known location and how old it is;
   - the booking (host, property address, dates);
   - the emergency contact.

   If a live share is active, its viewer link shows movement.
4. **Contact the person,** then the emergency contact, then the host, in that order.
   Don't share the person's location with the host unless the person asks, or there's
   a danger to life.

## Protect the person and others

- **Suspend the other account** if they're the threat (Safety → Enforcement). A
  suspension ends their sessions and hides their gigs and profile. It's audited.
- **Block further contact:** a suspension stops chat. Make sure any future bookings
  with the same person are cancelled.
- **Other guests at the same host:** check for active bookings there (back office →
  Bookings, filtered by property) and contact those guests.

## Systems and switches

| If | Then |
| --- | --- |
| SOS alerts aren't arriving (pager quiet, but people say they pressed SOS) | SEV1. Check the API ([database-outage](database-outage.md), [bad-deploy-rollback](bad-deploy-rollback.md)) and the notification queue ([otp-provider-outage](otp-provider-outage.md)). **SOS is never behind a feature flag.** |
| Live sharing is broken or leaking | Turn off `sos_live_sharing` (Feature flags; a reason is required). The app then tells the person to call their emergency contact directly. Active shares expire on their own. |
| Automated gig checks are misfiring (blocking good gigs, or passing bad ones) | Turn off `ai_safety_checks`: new gigs go to human review instead. |

## Keep evidence

Don't delete anything; take copies instead:
- the chat (Conversation, by booking), reports, check-ins and the location share;
- the audit log for both accounts.

Export them for the police only on a lawful request (a written notice citing the
provision). Log who asked, when, and what was given, in the incident note. Deletion and
retention jobs skip accounts that are under investigation (privacy branch, retention
holds).

## Afterwards

- Write the review (no blame). Did SOS reach the team within the target time in
  `docs/safety.md`? If not, why not?
- Check on the person after 24 hours and after a week.
