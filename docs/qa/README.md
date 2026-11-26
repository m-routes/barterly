# Regression and acceptance testing

This page covers what runs, where, and how to run it yourself. The suite drives the
real apps against a real API, through the core journeys and the failures people
actually hit. Unit and widget tests stay with each app; this layer proves the pieces
work together.

| Layer | Where | Runs |
| --- | --- | --- |
| Seed data | `backend/apps/qa` (`seed_staging`, `prepare_journey`) | Before each acceptance run; any time on staging |
| Server failure scenarios | `backend/apps/qa/tests/test_failure_scenarios.py` | Every backend CI run |
| Web journeys and failures | `web/e2e-acceptance` (Playwright, desktop and 390 px) | Nightly and on each release candidate, against staging |
| Talent journeys and failures | `mobile/integration_test` (Flutter) | The same, on three Android emulators and one iOS simulator |
| UAT scripts | [uat/](uat/) | By people, before launch and after big changes |
| Exploratory charters | [exploratory-charters.md](exploratory-charters.md) | By people, time-boxed sessions |

A **release candidate** is every build that reaches staging: `.github/workflows/acceptance.yml`
runs after each successful staging deploy. A production tag promotes a commit staging
already ran, so check that its acceptance run is green before you tag.

## The journeys

| Journey | Web (Playwright) | App (Flutter) |
| --- | --- | --- |
| Host onboarding: role, business profile, property pinned on the map | UI | – |
| Post a gig: five-step builder, sent for review | UI | – |
| Admin approval in the back office (gig queue → Approve) | UI | – |
| Talent finds a gig and applies | API, as the talent | UI |
| Host hires (applicant board → offer) | UI | – |
| Talent accepts; both sign (fresh phone code each) | Host: UI. Talent: API | UI |
| Check-in: the talent's pass code, the host's Arrivals screen | UI | Pass screen UI |
| Deliverable handed in | API, as the talent | UI |
| Host approves: the escrow is released and the payout is on its way | UI (Content) | – |
| Check-out, then reviews: double-blind, publish together | API | UI |

The talent's web steps go through the web's own proxy with the talent's session, the
same path the app's calls take. The talent's UI is the app, and the Flutter suite
covers it.

Time splits the journeys. A gig must start in the future, and check-in opens the day
before. So the hire journey posts a gig starting tomorrow and runs through to
check-in. The stay journey (hand-in → release → reviews) starts from a booking that
`prepare_journey` made earlier.

## Failure scenarios

| Scenario | Covered by |
| --- | --- |
| Offline during apply | App: written offline, kept, sent when back online (`failures_test.dart`). Server: a repeat send is refused as `already_applied`. Outbox: a lost answer is recognised as sent (`outbox_test.dart`). |
| Offline check-in | Web: Arrivals offline → "waiting to sync" → synced (`failures.spec.ts`). Server: a check-in synced twice counts once. |
| Payment webhook delay | Server: check-in waits for the money; a payment captured after cancellation is refunded |
| OTP failure | Web: a wrong code is explained and signs nobody in. Server: a bad token is a 401, a provider outage a 503 the app retries. |
| Double tap on pay | Web and server: two taps give one order, and duplicate webhooks give one ledger entry |
| Expired offer | Server: accepting after 48 hours is refused clearly |
| Host cancels late | Web: the cost ("last-minute cancellation") is shown before confirming, and it's recorded. Server: the talent's money comes back; it counts against the host. |

## Personas

They're defined once, in `backend/apps/qa/personas.json`, and shared by the seed, the
Playwright suite and the Flutter suite. Each phone number must also be a **Firebase
test number**.

| Key | Who | Used by |
| --- | --- | --- |
| `hostel_owner` | Meera Shah, Riverbend Hostel, Manali | Seed, stay-side failures, UAT |
| `cafe_owner` | Arjun Dsouza, Saltwater Café, Goa | Seed, stay journey (paid), UAT |
| `onboarding_vendor` | Kavya Iyer, a brand-new homestay | Hire journey (reset before each run) |
| `volunteer` | Rohan Verma | App journeys, UAT |
| `creator` | Ananya Rao | Stay journey, UAT |
| `trip_leader` | Tenzin Norbu | Failure scenarios, UAT |
| `journey_creator` | Isha Kapoor | Hire journey only (reset before each run) |
| `admin` | Barterly Ops (super admin) | Back-office approval, UAT |

A **reset** retires the old account rather than deleting it: it is deactivated and moved
to an archive number. The test number then signs up a brand-new account. Bookings,
money and audit history are never deleted.

## Seed data

```bash
manage.py seed_staging                     # a new batch of realistic data
manage.py seed_staging --reset-journeys    # also: a fresh host to onboard, a free talent
manage.py prepare_journey --talent creator # starting points for one talent
```

`seed_staging` makes the following, all through the app's own services:
- vendors with their business check in every verification state;
- gigs in every status, and applications in every status;
- bookings at every stage: signing, confirmed, checked in, delivering (waiting for
  review, changes asked), completed, reviewed, cancelled late, no-show and disputed;
- paid bookings with escrow funded through the payment webhook path and released.

Signatures and payments go through stand-ins (`apps/qa/providers.py`), labelled
`staging_seed` or prefixed `seed_`, so nothing reaches Razorpay or sends a code. Dates
are moved back after the fact, so a checked-in stay started yesterday rather than next
month. Each run is all-or-nothing, in one transaction.

Production can never be seeded: `config/settings/production.py` forces `ALLOW_SEED = False`.

## Setting up staging (once)

You need to do these; they are changes to the Firebase project and the repository:

1. **Firebase test numbers.** In the Firebase console, go to Authentication → Sign-in
   method → Phone → Phone numbers for testing. Add every phone in `personas.json`, each
   with the same 6-digit code. No SMS is ever sent to them.
2. **Repository secrets:**
   - `E2E_OTP_CODE`: that code.
   - `E2E_ADMIN_PASSWORD`: a long random password.
   - `FIREBASE_KEYS_JSON`: the contents of `mobile/env/firebase-keys.json`.
3. **Secret Manager:** put the same admin password in `qa-admin-password-staging`
   (Terraform creates the container when `qa_enabled = true`, which staging sets).
4. **Repository variables:**
   - `STAGING_WEB_URL` and `STAGING_API_URL`;
   - `GCP_PROJECT_ID`;
   - the four `E2E_FIREBASE_*` values (the public web config: API key, auth domain,
     project id and app id).
5. **Apply Terraform for staging**, so `barterly-qa-staging` exists and the web gets
   `FIREBASE_TEST_NUMBERS_ALLOWED`.
6. **Run `seed_staging`** once:
   `gcloud run jobs execute barterly-qa-staging --wait`.

Test numbers on the web: the login and agreement pages skip reCAPTCHA when the URL
has `?test_numbers=1`, but only where `FIREBASE_TEST_NUMBERS_ALLOWED=1`. With that
switch on, Firebase refuses real numbers, so it only ever applies to the one page load.
Production refuses it whatever the variables say.

## Running it yourself

There's a **local acceptance stack** that needs no Firebase or Razorpay:
- the API in local settings with `LOCAL_ACCEPTANCE_STACK=1` (fake sign-in, in-memory
  files, stand-in payments);
- the web with `LOCAL_FAKE_SIGN_IN=1`;
- the code is always `123456`.

Neither switch exists in deployed settings.

```bash
# API (port 8011) and web (3011), each in its own terminal
cd backend && LOCAL_ACCEPTANCE_STACK=1 SEED_ADMIN_PASSWORD=<pick one> \
  DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,10.0.2.2 uv run python manage.py runserver 0.0.0.0:8011
cd web && npm run build && API_URL=http://localhost:8011 LOCAL_FAKE_SIGN_IN=1 npm run start -- --port 3011
```

```bash
cd web && LOCAL_ACCEPTANCE_STACK=1 SEED_ADMIN_PASSWORD=<same> E2E_ADMIN_PASSWORD=<same> scripts/acceptance.sh local desktop
```

```bash
cd mobile && LOCAL_ACCEPTANCE_STACK=1 tool/acceptance.sh local emulator-5554
```

Run each script with the API's environment, because the scripts run `manage.py`
directly.

When the sign-in throttle (10 per number per hour) gets in the way locally, raise
`THROTTLE_AUTH_EXCHANGE_PHONE`. The nightly run signs each persona in once per device.

## Last verified

On 24 Nov 2026, on the local acceptance stack:
- **Playwright:** 6/6 on desktop and 6/6 at 390 px.
- **Flutter:** 3/3 on a Pixel 6 emulator (API 34).
- **Backend:** 18/18 QA tests.

The staging run, the low/mid/high Android matrix and the iOS simulator run need the
setup above. They haven't run yet.
