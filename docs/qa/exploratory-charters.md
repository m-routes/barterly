# Exploratory testing charters

Each charter is a 60–90 minute session for one person. Write down what you tried,
what surprised you and every bug, with the time (IST), the device and the build.
These are for the things scripts miss. Pick charters that touch what changed since
the last round.

Format: **Explore** <area> **with** <resources> **to discover** <information>.

| # | Charter | Persona | Why it matters |
| --- | --- | --- | --- |
| 1 | Explore **applying and hiring** with two talents applying to the last open slot at the same moment, to discover how the race is settled and what the loser sees | volunteer ×2, hostel owner | Slots are scarce in peak season |
| 2 | Explore **money** with a funded stay that's cancelled, disputed or cut short at every stage, to discover whether the escrow, ledger and wallet always agree | café owner, creator, admin | Money must never be lost or doubled |
| 3 | Explore **poor networks** with an entry-level Android phone on throttled 3G, losing signal mid-action (apply, sign, hand in, check in), to discover where work is lost or duplicated | trip leader | Hill stations and treks have patchy signal |
| 4 | Explore **dates and time zones** around midnight IST, month ends, and stays crossing a year, to discover off-by-one days in check-in windows, deadlines and reminders | any | India-only times, but servers run in UTC |
| 5 | Explore **sign-in** with wrong codes, expired codes, a changed SIM, two devices and a reinstall, to discover lockouts, confusing messages or sessions that won't end | any | Phone OTP is the only way in |
| 6 | Explore **agreements** with changes proposed by each side, versions signed out of order and a cancellation mid-signing, to discover whether the signed terms are always the ones in force | host, talent | The agreement is the legal record |
| 7 | Explore **privacy** by trying to see another person's address, phone, emergency contact or files (changed ids, old links, shared screenshots), to discover any leak | two talents, two hosts | Homestays are often the host's home |
| 8 | Explore **the back office** with each staff role, to discover anything a role can see or do that it shouldn't (or can't that it should) | admin roles | Least privilege, audited actions |
| 9 | Explore **accessibility** with TalkBack or VoiceOver, keyboard only on the web, the largest text and 200% zoom, to discover anything unreachable or unreadable | any | Not everyone taps and reads like the designer |
| 10 | Explore **notifications** with quiet hours, the app closed, notifications switched off and email only, to discover missed, duplicated or badly timed messages | host, talent | People act on them: offers expire in 48 h |
| 11 | Explore **reviews** with abusive text, phone numbers in reviews, retaliation after a dispute, and reports, to discover how moderation and the double-blind rule hold up | host, talent, admin (Trust) | Trust in reputation is the product |
| 12 | Explore **search and discovery** with odd inputs (Hindi, emoji, long text, typos, far-away places), to discover irrelevant results, crashes or slow pages | volunteer | First impressions |

## After a session

- File bugs with the label `exploratory` and the charter number.
- Note new scripted checks worth adding (to `web/e2e-acceptance`,
  `mobile/integration_test` or a UAT script) at the end of your session notes.
- Track how many sessions each charter has had, so none goes untested between releases.
