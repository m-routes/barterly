# UAT scripts

One script per persona. Each is something a real person in that role does in their
first weeks on Barterly. Run them on staging, signed in as the persona (the phone
numbers are in `backend/apps/qa/personas.json`, and the code is the Firebase test code).
Run `manage.py seed_staging` first, so there is data to find.

**How to mark a step**
- **Pass:** it worked, and it was clear what to do.
- **Fail:** it didn't work, *or* you had to guess. Write what you saw in Notes, with a
  screenshot, the time (IST) and the device.

A script passes when every step does. Any failure becomes an issue with the label
`uat` and the step number.

| Script | Persona | Where | About |
| --- | --- | --- | --- |
| [hostel-owner.md](hostel-owner.md) | Meera, Riverbend Hostel | Web console | Volunteers for a 40-bed hostel |
| [cafe-owner.md](cafe-owner.md) | Arjun, Saltwater Café | Web console, phone browser | Paid content, escrow, payouts |
| [volunteer.md](volunteer.md) | Rohan | Android app | Work-for-stay, first trip |
| [creator.md](creator.md) | Ananya | Android or iOS app | Reels for stays, deliverables, wallet |
| [trip-leader.md](trip-leader.md) | Tenzin | Android app, on poor signal | Treks, offline check-in, safety |
| [admin.md](admin.md) | Barterly Ops | Back office (Django admin) | Approvals, verification, money, flags |

**Steps that need work not merged yet:** mark them N/A until it lands, and note which
branch it's on:
- funding escrow from the web (café owner, step 3): the finance console branch;
- feature flags (admin, step 11): the operations branch;
- SOS and reports: the trust and safety branch, which has its own playbook.

**Before you start:** write your name, the date, the build (web footer, or the app's
Profile → About) and the device at the top of your copy.
