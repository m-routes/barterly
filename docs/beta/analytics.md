# Product analytics

Product analytics show how people move through the apps (which screens, where they stop)
so we can fix what's confusing. They are **only collected with consent**.

## Consent

- A new optional purpose, **Product analytics** (`analytics`), sits with location,
  social and marketing in *Privacy and your data* on the web and in the app. Nobody is
  opted in by default.
- The web and the app check the person's consent before sending anything. Without it
  nothing leaves the device, and the server would drop it anyway (`consent: false`).
- Withdrawing stops sending at once and **deletes** everything recorded for that person
  (the `privacy.consent_changed` event). Account deletion deletes it too.
- The privacy policy has a new section 6, "Product analytics". **Legal review needed**,
  and bump `PRIVACY_POLICY_VERSION` when the text is final, so people see the change.

## What's recorded

`backend/apps/analytics/events.py` lists every event and the only properties each may
carry. Anything else is dropped on arrival.

| Event | Properties |
| --- | --- |
| `screen_view` | `screen`: the route with ids removed (`trips/agreement`) |
| `onboarding_step` | `step` |
| `invite_entered` | `ok` (true/false) |
| `gig_builder_step`, `gig_submitted` | step number; gig id |
| `search` | number of filters, number of results |
| `gig_viewed`, `apply_started`, `apply_submitted` | gig id; source; whether it was sent offline |
| `offer_viewed` | application id |
| `help_opened`, `feedback_sent` | screen; kind of request |

Each row also has the platform, the app version, the person's role, and a
**pseudonym**: an HMAC of the user id under `ANALYTICS_PSEUDONYM_KEY` (Secret Manager;
falls back to `SECRET_KEY`). There's no IP address, device id, user agent, location or
free text. Gig and application ids aren't personal, but they can be joined to bookings,
so the table is only read in aggregate on the KPI dashboard.

**Retention:** 395 days (`RETAIN_ANALYTICS_EVENTS_DAYS`), purged by the daily
`privacy_retention` job.

## Adding an event

1. Add it to `EVENTS` in `backend/apps/analytics/events.py`, with a checker for each
   property. Never free text.
2. Add it to `EVENT_NAMES` in `web/src/lib/analytics/events.ts` and `eventNames` in
   `mobile/lib/src/analytics/events.dart`. A backend test fails if the three lists
   differ.
3. Call `track(...)` on the web or `ref.read(analyticsProvider).track(...)` in the app.
