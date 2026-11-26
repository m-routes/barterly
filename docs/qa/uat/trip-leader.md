# UAT: trip leader (Tenzin, Dharamshala)

Tenzin leads treks for a hostel, often where the signal is poor. Use an entry-level
Android phone if you can, with the network throttled to "poor 3G" where possible.

Tester · Date · Build · Phone · Network

| # | Step | Expected | Pass | Fail | Notes |
| --- | --- | --- | --- | --- | --- |
| 1 | Sign in on poor signal | It's slow but works; a clear message if a code fails | ☐ | ☐ | |
| 2 | Enter a wrong code once | "That code isn't right…"; nothing else happens | ☐ | ☐ | |
| 3 | Find a "Trip leader" gig and apply | As for the volunteer; the gig shows the trek details | ☐ | ☐ | |
| 4 | Answer an offer after it expired (use a seeded expired one) | A clear "this offer has expired"; no booking | ☐ | ☐ | |
| 5 | On arrival day, open the pass with no signal | The saved pass and the code still work | ☐ | ☐ | |
| 6 | The host checks you in while their tablet is offline | Your trip updates once their tablet syncs | ☐ | ☐ | |
| 7 | Log hours for a long trek day (8 h) | Refused past the agreed daily most, with the reason | ☐ | ☐ | |
| 8 | Message the host from the trip | Messages send and arrive; unread counts update | ☐ | ☐ | |
| 9 | The host cancels the day before (ask the tester playing host) | You're told at once; the reason; it doesn't count against you | ☐ | ☐ | |
| 10 | Check the app works with the largest font and TalkBack on | Every button has a spoken name; nothing clipped | ☐ | ☐ | |

**Result:** ☐ Pass ☐ Fail · Signed off by
