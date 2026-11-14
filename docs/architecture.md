# Architecture

Barterly is a monorepo with three apps that share one API.

```
.
├── backend/            Django 5 + DRF API and admin console (Python 3.12, uv)
│   ├── config/settings/  base, local, staging, production (+ deployed: shared by the last two)
│   ├── apps/           Django apps; each has services/, tests/, views, serializers
│   │   └── core/       health check, shared factories
│   ├── Dockerfile      gunicorn + uvicorn workers (ASGI), non-root
│   ├── pyproject.toml  dependencies, ruff, pytest, coverage config
│   ├── uv.lock         locked dependencies
│   └── docker-compose.yml  local Postgres 16
├── web/                Next.js (App Router) vendor console, TypeScript strict
│   ├── src/app/        routes and layouts; api/v1/[...path] forwards to the API
│   ├── src/components/ UI kit (fields, buttons, states, toasts) and route guards
│   ├── src/lib/        API client, session, validation; lib/server/ is server-only
│   ├── openapi/        schema.yaml exported from the backend (source of the client types)
│   ├── Dockerfile      Next.js standalone server, non-root
│   └── e2e/            Playwright tests
├── mobile/             Flutter talent app
│   ├── lib/src/        app code: api/, auth/, profile/, shell/, theme/, router.dart
│   ├── env/            per-environment build settings (--dart-define-from-file)
│   ├── test/           unit and widget tests (flutter_test)
│   └── integration_test/  on-device tests
├── infra/              Terraform (GCP, incl. Cloud SQL), deploy/rollback scripts, runbooks
├── docs/               this file and future design notes
└── .github/workflows/  backend.yml, web.yml, mobile.yml, infra.yml, deploy.yml
```

## Runtime

| Concern | Choice |
| --- | --- |
| API | Django 5 + DRF, OpenAPI via drf-spectacular (`/api/schema/`, `/api/docs/`) |
| Database | Cloud SQL for PostgreSQL 16 in asia-south1 (local: Docker Postgres 16), configured by `DATABASE_URL`; Cloud Run reaches it through the Cloud SQL connector socket, with a psycopg pool per worker |
| Hosting | GCP Cloud Run in asia-south1: services `barterly-api-<env>`, `barterly-web-<env>`, job `barterly-migrate-<env>` |
| Secrets | Secret Manager, injected as env vars; nothing secret in git or Terraform state |
| Auth and push | Firebase Auth, FCM |
| Files | Cloud Storage: private media bucket (signed URLs only), public static bucket |
| Maps | OpenStreetMap via Leaflet (web) and flutter_map (mobile) |

Surfaces: the vendor console (web), the talent app (mobile) and the admin console (Django admin plus custom views). Roles: vendor, talent and admin (ops, trust, finance, support).

## Backend conventions

- Business logic goes in `apps/<app>/services/`; views and serializers stay thin. Coverage of services is gated at 85% in CI.
- Every endpoint is annotated with `extend_schema`; the schema is validated in CI with `--fail-on-warn`.
- DRF defaults to `IsAuthenticated`; endpoints opt out explicitly (as the health check does).
- Settings: `config.settings.local` for development and tests; `staging` and `production` for Cloud Run. Deployed settings force `DEBUG=False`, require `DJANGO_SECRET_KEY` and `DJANGO_ALLOWED_HOSTS`, and set secure cookies, SSL redirect and HSTS (1 hour on staging, 1 year with preload on production).
- Database connections go through `apps.core.db.postgresql`, which retries new connections while Cloud SQL restarts (maintenance, failover). Deployed settings use Django's psycopg connection pool.
- `/api/v1/health/` is the health endpoint (Cloud Run reserves some paths ending in `z`).
- Migrations must be reversible. `apps/common/tests/test_migrations.py` unapplies and reapplies every migration in our apps.

### Apps

| App | What it holds |
| --- | --- |
| `core` | Health check, the retrying DB backend, the `release` command |
| `common` | `TimeStampedModel`, `SoftDeleteModel`, `AuditLog` + `log_action()`, the error format, pagination, request-id middleware, JSON logging, permission classes |
| `accounts` | Custom `User` (`AUTH_USER_MODEL = "accounts.User"`), sign-in (OTP token exchange, JWT refresh and logout), audited role and status changes, `/api/v1/me/` |
| `profiles` | `TalentProfile` and `VendorProfile` (one per user, role must match, soft-deleted), curated `Skill` list, `/api/v1/profiles/{vendor,talent}/me/` |
| `media` | `MediaFile` records for uploads to the private bucket, signed upload/read URLs, the `media.process` task (virus scan hook, image resizing) |
| `geo` | Distance helpers (haversine, bounding box), the `Geocoder` interface with Nominatim and a fake, and the database cache of every geocoding answer |
| `properties` | `Property` (location as lat/lng columns, approximate public point) and `PropertyPhoto`, owner CRUD, the public view, submitting a property for verification |
| `gigs` | `Gig` (role template, compensation model, dates, hours, stay, meals, stipend, deliverables, eligibility, screening questions), the business rules, the status machine and review, plan limits, auto-close |
| `discovery` | Gig search for talent (`GET /api/v1/gigs/`): hard filters, the fit score, cursor pages; saved searches and their alert job |
| `applications` | `Application` and its attachments, the apply rules (with every blocking reason), the status table, applicant views for vendors |
| `notifications` | Queued `Notification` rows; delivery arrives in Phase 3 |
| `verification` | Verification cases per check, evidence (provider references and masked numbers only), badges, the KYC provider interface and webhook, re-verification on profile edits, the review API |

### Users and permissions

- `accounts.User`: UUID primary key, `phone` as the login identifier (stored in E.164; local Indian formats like `98765 43210` are accepted and normalised), optional `email` (unique ignoring case when set), `role` in `vendor` / `talent` / `admin` (empty until a new user picks one), `is_active`, `created_at` / `updated_at`. Users have no usable password: they sign in by phone OTP.
- Permission classes in `apps.common.permissions`: `IsVendor`, `IsTalent` and `IsAdminRole` (active user with that role) and `IsOwner` (object-level; set `owner_field` on the view, e.g. `"listing__vendor"`, or `""` when the object is the user). Combine them with `&` and `|`.
- API authentication is `Authorization: Bearer <access JWT>`; the session cookie is accepted only for the Django admin's own use. Basic auth is off.

### Sign-in

1. The app signs in with Firebase phone auth (SMS OTP) and gets a Firebase ID token.
2. `POST /api/v1/auth/exchange/ {"id_token"}` verifies it, fetches or creates the user by phone, and returns `{access, refresh, is_new_user, profile_complete, needs_role, user}`. New users are audit-logged (`user.signed_up`). Disabled users get 403 `account_disabled`; a bad token gets 401 `invalid_sign_in_token`; a Firebase outage gets 503.
3. If `needs_role`, the app calls `POST /api/v1/me/role/ {"role": "vendor"|"talent"}`. This works once (then 409 `role_already_set`) and is audit-logged (`user.role_selected`). Admin roles are granted only in the Django admin.
4. Access tokens last 15 minutes. `POST /api/v1/auth/refresh/ {"refresh"}` returns a new pair and blacklists the old refresh token (30 days). `POST /api/v1/auth/logout/ {"refresh"}` blacklists it (204). Disabled users can't refresh.

The exchange is rate limited per IP (60/hour, counted before verification) and per phone (10/hour, after verification, keyed on a hash). Counters live in the Postgres cache table that the `release` command creates, so they hold across instances. Behind Cloud Run, the client IP is the last `X-Forwarded-For` hop (`TRUSTED_PROXY_COUNT=1`).

The token check sits behind `apps.accounts.auth.verifiers.TokenVerifier` (`verify(token) -> VerifiedIdentity(phone, provider, provider_uid)`). `FirebaseTokenVerifier` is the only one wired up; to change OTP provider, add a verifier and point `AUTH_TOKEN_VERIFIER` (a code setting, not an env var) at it. Tests use `apps.accounts.tests.fakes.FakeTokenVerifier` (tokens look like `fake-otp:+919876543210`) and never call Firebase.

### Profiles

- `GET` / `PATCH /api/v1/profiles/vendor/me/` (vendors) and `/api/v1/profiles/talent/me/` (talent). The first `PATCH` creates the profile (201); later ones are partial updates. `GET` before that is 404 `profile_not_found`. A profile an admin soft-deleted isn't recreated (409 `profile_removed`).
- Every response has `profile_complete` and `missing_fields`. Vendor needs business name, business type, contact name, city, state (from the list of Indian states and UTs) and about; GSTIN and website are optional and validated. Talent needs display name, bio, talent type, at least one skill, languages (ISO 639 codes such as `en`, `hi`), home city, an emergency contact (name and phone, not their own number) and a date of birth showing they are 18 or older (counted in IST).
- Skills are a table admins curate (Django admin -> Skills, seeded with a starter list); clients list them at `GET /api/v1/profiles/skills/` and send slugs. `GET /api/v1/me/` uses the same completeness rule.

### Uploads

Files never get public URLs. The media bucket enforces public access prevention, and the API hands out short-lived signed URLs:

1. `POST /api/v1/media/upload-url/ {kind, content_type, size_bytes, checksum_md5?}` checks the policy and returns a signed `PUT` URL (15 minutes) plus the headers the client must send. The URL is bound to the content type and to sizes up to the declared size (`x-goog-content-length-range`), and to the MD5 when given, so Cloud Storage itself refuses anything else.
2. The client `PUT`s the file.
3. `POST /api/v1/media/confirm/ {media_id}` checks the stored object (type, exact size, MD5, and the file's first bytes against the declared type), records it with its checksum, and runs processing. A failed check deletes the object (422 `upload_rejected`).
4. `GET /api/v1/media/{id}/` (owner or admin) returns the record with 5-minute signed read URLs once the file is `ready`.

| Kind | Types | Max |
| --- | --- | --- |
| `avatar` | jpeg, png, webp | 5 MB |
| `photo` | jpeg, png, webp | 10 MB |
| `video` | mp4 | 100 MB |
| `document` | pdf, jpeg, png | 10 MB |

Users can have 20 unfinished uploads at once and request 120 upload URLs an hour. Status changes (`media.confirmed`, `.ready`, `.rejected`, `.quarantined`) are audit-logged.

Processing is the `media.process` task (`apps.media.services.processing`). It runs the virus scanner, deletes and quarantines infected files, and writes WebP copies of images (`thumb` 320 px, `medium` 1280 px; rotation applied, EXIF dropped). Images Pillow can't read, including decompression bombs, are rejected.

Three interfaces keep the pieces swappable, each named by a code setting:

- `MEDIA_STORAGE_CLASS`: `GCSMediaStorage` signs through IAM `signBlob` on Cloud Run. Tests use `apps.media.tests.fakes.InMemoryMediaStorage`.
- `MEDIA_VIRUS_SCANNER`: `NoopVirusScanner` for now, which marks files `skipped`. Set `MEDIA_REQUIRE_SCAN=1` once a real scanner is in, and only `clean` files are served.
- `TASK_QUEUE_CLASS`: `InlineTaskQueue` runs tasks inside the confirm request. A Cloud Tasks queue would enqueue an HTTP task to an internal endpoint that verifies the task's OIDC token and calls `run_task(name, payload)`. Tasks are idempotent, so retries are safe.

### Properties and location

A vendor can have several properties (`hostel`, `homestay`, `cafe`, `hotel`, `trek_operator`). Each has an address, a map pin, amenities (fixed codes), house rules, a `women_friendly` flag and photos. `verification_status` mirrors the property's verification case, and changes go through the case so they're audit-logged.

**No PostGIS.** Production is Cloud SQL Postgres 16. PostGIS is available there, but GeoDjango would need GDAL and GEOS in the image, CI and every laptop. Location is stored as `latitude`/`longitude` decimal columns with a composite index instead. `Property.objects.within_radius(lat, lng, metres)` filters on a bounding box the index can serve, then on the exact haversine distance computed in SQL, nearest first. Moving to a `PointField` with a GiST index later only changes that one method.

**Exact and approximate location.** The street address and exact pin go only to the owner and admins, and once bookings exist, to guests with a confirmed booking (`can_see_exact_location`). Everyone else sees `approximate_location`. That point is 300–900 m from the real one, in a direction seeded from `SECRET_KEY` and the property id. It's stored and stable, so repeated requests can't be averaged back to the real spot. Public "nearby" queries must use it too (`within_radius(public=True)`, the default), because ordering by the real distance would leak the pin.

**Pin flow.** Creating a property, or changing its address without sending a pin, geocodes the address once to suggest a pin. The vendor then confirms or moves it (`location_confirmed`). Moving the pin or changing the address clears the confirmation unless the same request confirms it again.

**Geocoding.** `apps.geo.services.geocode()` normalizes the query and returns the cached `GeocodeResult` when there is one. Hits are kept forever; "not found" is asked again after 30 days. Otherwise it calls the `GEOCODER` (a code setting). `NominatimGeocoder` follows the OpenStreetMap usage policy:
- an identifying `NOMINATIM_USER_AGENT` and optional `NOMINATIM_EMAIL`;
- at most one request per second across every instance, through a slot in the shared Postgres cache;
- results limited to India;
- a 5-second timeout.

We never geocode on each keystroke: only on save, or when a vendor presses "find on map" (`POST /api/v1/geo/geocode/`, 30 an hour per vendor). Tests use `FakeGeocoder`.

**Photos.** Upload through the signed flow (`/api/v1/media/upload-url/`, then `/confirm/`, kind `photo`), then `POST /api/v1/properties/{id}/photos/ {media_id, latitude?, longitude?, captured_at?}`. There's a limit of 20 per property. `POST /api/v1/properties/{id}/verification/` needs at least 3 photos taken within 500 m of the confirmed pin. The public page lists only photos that are ready to serve.

### Gigs

A gig belongs to one of the vendor's properties. It has a role template (`volunteer`, `content_creator`, `trip_leader`, `specialist`) and a compensation model (`volunteer`, `barter`, `hybrid`, `paid`).

**Rules** (`apps.gigs.rules`, run by the services whatever the caller):
- At most 6 hours a day and 6 days a week (at least one day off).
- At least 1 slot.
- A start date in the future; apply-by on or before the start; an end date after the start, or a duration.
- Volunteer gigs state the stay and the meals.
- Barter gigs list at least one deliverable.
- Hybrid and paid gigs have a stipend above zero and say its period. A stipend only on hybrid and paid gigs; deliverables only on barter and hybrid.
- Eligibility is a fixed minimum age of 18, plus optional languages, minimum followers and minimum stay. Up to 5 screening questions.

Drafts may be incomplete but never wrong. The full rules apply on submit and on every edit of a gig past draft, and all problems are reported together as field errors. A few rules are also database constraints, as a backstop.

**Status machine.** `apps.gigs.constants.TRANSITIONS` lists every allowed `(from, to)` move and who may make it (vendor, admin or system):
- **Vendor:** submits a draft (draft → in_review), withdraws it (in_review → draft), pauses, resumes, closes and archives.
- **Admin:** approves (in_review → live), or sends back to draft with a reason the vendor sees.
- **System:** reopens review, fills, and auto-closes.

Every change writes an audit row `gig.<status>`. Its `after.by` records whether the vendor, an admin or the system made it. Stipend changes also write `gig.compensation_changed`.

**Re-review.** Editing a live or paused gig's pay (`compensation_model`, `stipend_*`), hours (`hours_per_day`, `days_per_week`) or dates sends it back to `in_review`. Other edits keep it live. Filled, closed and archived gigs can't be edited.

**Plan limits.** `GIG_PLAN_POLICY` names a `PlanPolicy` that returns the vendor's `Plan(max_live_gigs)`. It's checked when a gig goes live, either approved or resumed. `UnlimitedPlanPolicy` is used for now.

**Jobs and hooks.**
- `manage.py close_expired_gigs` closes live and paused gigs whose apply-by date has passed. It should run daily.
- `on_confirmed_bookings_changed(gig_id, confirmed)` is for bookings (Phase 3). It marks a live gig `filled` when confirmed bookings reach its slots, and reopens it if one is cancelled before applications close.

### Discovery

`GET /api/v1/gigs/` is for talent. Vendors create gigs with `POST /gigs/` and list their own at `/gigs/mine/`.

**Hard filters first, in SQL.** A talent sees only live gigs that are still taking applications, at properties that still exist, that they're eligible for:
- They share at least one of the gig's languages, if the gig lists any.
- Their `instagram_followers` meets `min_followers`. An unknown follower count counts as 0.

Then their own filters apply:
- compensation model, role and stay type (comma lists);
- city, or a point with a radius (on the approximate location);
- a start-date range;
- women-friendly;
- verified hosts (property approved, and the vendor holds an active `id_verified` badge);
- how many days they can stay (`min_stay`);
- keywords (`q`): Postgres full text, `websearch_to_tsquery`, on `Gig.search_vector`. Title is weighted A and description B, with a GIN index. A signal keeps the vector up to date.

**Fit score** (`apps.discovery.scoring.fit_score`): a pure function of the talent's facts, the gig's facts and `DISCOVERY_FIT_WEIGHTS`.

| Component | Weight | Data today |
| --- | --- | --- |
| Skill match | 30 | Gig skills matched by the talent's profile skills |
| Reliability | 25 | None until bookings (Phase 3), so neutral |
| Ratings | 20 | None until reviews (Phase 3), so neutral |
| Audience quality | 15 | No source yet, so neutral |
| Distance and availability | 10 | Distance from the searcher's point (0 at `DISCOVERY_DISTANCE_ZERO_KM`), and the share of the gig inside their date range |

Each component is 0–1. Missing data scores the neutral 0.5, never 0. Weights are scaled to 100. Every result carries `fit.breakdown`: value, weight, points, whether the value was neutral, and a reason. `talent_signals()` is where Phase 3 plugs in reliability, ratings and audience quality.

**Sorts and pages.** The sorts are `best_fit` (the default), `newest`, `start_date` and `distance` (needs a point). Pages use an opaque keyset cursor tied to the sort: pass `next_cursor` back as `cursor`. `best_fit` scores the newest `DISCOVERY_MAX_CANDIDATES` (1000) matching gigs in Python; the other sorts page in SQL. A list request costs 5 queries however many gigs it returns, and a test asserts it.

**Saved searches and alerts.** Talent save up to 10 searches (`/api/v1/gigs/saved-searches/`), stored as validated filter params. `manage.py run_search_alerts` (hourly) finds gigs published since each search's `last_checked_at` that it hasn't matched before. It stores each match with its fit breakdown (`SavedSearchMatch`, unique per search and gig, so nothing repeats) and queues one `Notification` (`gigs.search_alert`) per search with new matches. Delivery (FCM and email) comes in Phase 3.

### Applications

Talent apply with `POST /api/v1/gigs/{id}/applications/`. An application has a pitch, one answer per screening question (stored with the question text), proposed dates, up to 8 attachments (their own photo, video and document uploads, or https links), and a snapshot of the fit score and its breakdown at the time they applied.

**Apply rules** (`apps.applications.rules`). Every failed check is collected, and a 422 `application_blocked` returns all of them in `details.reasons` as `[{code, message}]`. The checks are:
- talent role, and not the gig's own vendor;
- the gig is live and still taking applications;
- a complete profile;
- the gig's `required_verification` (`none`, `id_verified` by default, or `trusted_member`);
- no other active application to the gig;
- a shared language, and the follower minimum;
- 18 or older on the start date;
- dates inside the gig and at least its minimum stay;
- every screening question answered;
- usable attachments.

A database constraint also allows only one active application per talent per gig (`applied`, `shortlisted`, `interview`, `offered`).

**Statuses.** `apps.applications.constants.TRANSITIONS` defines every move and who makes it:
- **Vendor:** shortlist, interview, offer and reject.
- **Talent:** withdraw (from any active status, so up to accepting an offer) and decline an offer.
- **System:** expire.

This phase uses apply and withdraw. The rest are wired for Phase 3. Every change writes an audit row `application.<status>`.

**Vendors** list applicants with `GET /api/v1/gigs/{id}/applications/`. Filters are status (comma list) and `min_score`. Sorts are `fit` (default), `newest` and `oldest`. The query count is fixed and a test checks it. `GET /api/v1/applications/{id}/` adds attachments with short-lived signed URLs and the applicant's active badges. Applicant data never includes phone, email, emergency contact, birth date or social handle.

**Notification.** A new application queues `applications.new` for the vendor.

### Verification

Each user has one `VerificationCase` per check, kept across attempts. Statuses: `not_started → submitted → in_review → approved | rejected | changes_requested`, plus `expired`. The allowed moves are in `apps.verification.constants.TRANSITIONS`, and anything else returns 409.

| Role | Check | How it is checked | Badge |
| --- | --- | --- | --- |
| both | `id_selfie` | KYC provider: ID plus selfie, result by webhook | `id_verified` |
| vendor | `business_registration` | PAN format, GSTIN format, GSTIN contains the PAN; then a reviewer | `licence_verified` |
| vendor | `property` (one case per property) | Confirmed map pin in India, at least 3 own photos taken within 500 m of it; then a reviewer | `property_verified` (held while any property is approved) |
| talent | `social_account` | Instagram handle from the profile; the reviewer looks for `details.bio_code` in its bio | `social_verified` |
| talent | `certificate` (optional) | Own document uploads; then a reviewer | `licence_verified` |
| talent | `reference` | One contact (not the user's own number); a reviewer calls them | `reference_checked` |

`trusted_member` is granted while a user holds every required badge for their role and revoked as soon as one goes. Badges are granted and revoked with a reason; revoked rows stay as history. Every case status change and every badge change is audit-logged (`verification.case.<status>`, `verification.badge.granted|revoked`).

**What we store.** Provider reference ids, statuses and the last four characters of a number. ID images and selfies go straight from the app to the provider. A check constraint stops an ID document row from pointing at an upload; only property photos and certificates may.

**KYC provider.** `KycProvider` (`start_check`, `get_result`, `verify_webhook`) is named by the code setting `KYC_PROVIDER`. Deployed services use `ExternalKycProvider`, a documented stub that answers 503 until a real provider is wired in (see `providers/external.py`). Local runs and tests use `FakeKycProvider`. To finish a check locally, run `uv run python manage.py fake_kyc_result <reference> approved`.

**Webhook.** `POST /api/v1/verification/webhooks/kyc/` has no user auth. The provider signs the raw body (HMAC-SHA256 with `KYC_WEBHOOK_SECRET`, timestamp within 5 minutes), and a bad signature returns 401. Each delivery's idempotency key is stored, so a repeat is acknowledged and skipped. A result for an older attempt, or one arriving after a reviewer decided, changes nothing. `manage.py sync_kyc_results` polls the provider for checks whose webhook never came.

**Re-verification.** Profile saves are watched through model signals, so the API, the admin and scripts all trigger it. Changing a verified field moves an approved case back to `in_review` and revokes its badge until a reviewer approves again. The watched fields are a property's name, address, city, state and pin (that property's case), the business name and GSTIN (business check), and the Instagram handle (social check). Starting a new ID check on an approved case does the same for the ID badge.

**Review.** Admins use `GET /api/v1/verification/admin/cases/?status=submitted` (oldest first), then `POST …/cases/{id}/decision/ {decision, reason}`. The decision is one of `start_review`, `approve`, `reject`, `request_changes`, or `revoke` for an approved case. The Django admin is read-only. `manage.py expire_verifications` expires approved cases after their validity (ID 2 years; business, property and reference 1 year; social 6 months) and should run daily.

### Audit log

Money and status changes write an `AuditLog` entry through `apps.common.services.audit.log_action()`, in the same transaction as the change. Each entry records the actor, a dotted action (`user.role_changed`), the target's type and id, JSON before/after, the client IP and the request id. Entries are append-only: updates and deletes raise, and the admin is read-only. Users with audit history can't be hard-deleted (`PROTECT`); deactivate them. Role and `is_active` changes go through `apps.accounts.services.users` (and the admin's save hook), which audit them.

### Errors, pagination, docs

- Every API error has the shape `{"code", "message", "details"}`: `validation_error` with field errors in `details`, plus `not_found`, `permission_denied`, `not_authenticated`, `throttled` (`details.retry_after_seconds`) and `server_error`. Unhandled exceptions are logged, sent to Sentry if it's on, and returned as a JSON 500. Unknown `/api/` URLs also return the JSON 404. `ErrorSerializer` documents the shape in OpenAPI.
- Lists are paginated with `?page=` and `?page_size=` (20 by default, 100 at most), returning `{count, next, previous, results}`.
- OpenAPI is served at `/api/schema/` everywhere. Swagger UI at `/api/docs/` is turned off in production (`API_DOCS_ENABLED`).

### Logging and errors in production

- `RequestIDMiddleware` assigns each request an id: a valid incoming `X-Request-ID`, else the Cloud Run trace id, else a new UUID. The id is returned in `X-Request-ID`, stored on audit entries and added to every log line.
- Logs are JSON, one object per line, with `severity`, `message`, `logger`, `request_id` and any `extra=` fields, so Cloud Logging parses them directly. Set `LOG_FORMAT=plain` for readable local output (the local default).
- Sentry is off unless `SENTRY_ENABLED=1` and `SENTRY_DSN` are set (the DSN goes in Secret Manager). It doesn't send PII.
- `apps.accounts.services.user_model_switch` runs from `release` and switches a database that was first migrated with Django's built-in user model. It acts only when the old user tables are empty, and does nothing otherwise. Delete it once staging and production have been switched.

## Web console

Next.js 16 App Router with Cache Components. Pages: `/` (landing), `/login`, `/start` (sends a signed-in person to the right place), `/onboarding/role`, `/onboarding/vendor`, `/talent` (talent are pointed at the mobile app) and `/console/*` (Dashboard, Gigs, Applicants, Talent search, Agreements, Payments, Analytics; unbuilt sections show an empty state).

**Calling the API.** The browser only talks to its own origin. `src/app/api/v1/[...path]/route.ts` forwards `/api/v1/*` to `API_URL`, so the API needs no CORS.
- The JWTs live in httpOnly, SameSite=Lax cookies (`barterly_access`, `barterly_refresh`) that expire with their tokens. Browser JavaScript never sees a token.
- The forwarder turns the access cookie into `Authorization: Bearer`. It handles exchange, refresh and logout itself: it sets and clears the cookies and strips the tokens from the response.
- POST, PATCH, PUT and DELETE must come from this site's own origin.

**Typed client.** `src/lib/api/client.ts` is openapi-fetch over types generated from `web/openapi/schema.yaml`. After changing the API, run `npm run api:generate` in `web/` and commit both files. Backend CI fails if the schema file is stale, and web CI fails if the types are.
- **401 handling:** on a 401 the client refreshes once and replays the request. Refreshes are shared within a tab and serialised across tabs with a Web Lock, because refresh tokens rotate and a reused one is blacklisted.
- **Global error handler:** server errors, 429, 403 and network failures become toasts (with the request id). An expired session sends the person to `/login?next=…`. Validation errors stay with the form that caused them.

**Access.** `src/proxy.ts` redirects signed-out visitors away from the signed-in pages, and signed-in visitors away from `/login`. It only checks that the cookie exists. `RequireRole` then checks the role from `/api/v1/me/`:
- No role yet goes to `/onboarding/role`.
- A vendor with an incomplete profile goes to `/onboarding/vendor`.
- Anyone with the wrong role sees an explanation.

The API authorizes every call regardless.

**Sign-in.** Firebase phone OTP with an invisible reCAPTCHA (`@firebase/app` and `@firebase/auth` only, loaded on demand). The Firebase ID token is exchanged once, and then the Firebase session is dropped. Config comes from `FIREBASE_PROJECT_ID`, `FIREBASE_WEB_API_KEY` and `FIREBASE_WEB_APP_ID` at request time. Terraform sets them from `firebase_web` in each environment's tfvars.

**Design.** The tokens are in `src/app/globals.css`:
- Colours: ground `#FBF8F3`, ink `#1F2A24`, accent `#0F6B5C`.
- Type: Space Grotesk headings, Inter body.
- Layout is mobile first. Every control is at least 44 px tall, and the colour pairs meet WCAG 2.1 AA (ratios are listed in the file).

Forms use react-hook-form with zod. Every screen has loading, empty and error states (`src/components/ui/states.tsx`).

## Talent app (mobile)

Flutter 3.47 with Riverpod 3, go_router 18 and Dio. Material comes from the standalone `material_ui` package; import `package:material_ui/material_ui.dart`, not `package:flutter/material.dart`.

**Environments.** Each build targets one environment through a settings file: `flutter run --dart-define-from-file=env/staging.json --dart-define-from-file=env/firebase-keys.json` (or `local.json`, `production.json`). Firebase API keys sit in the uncommitted `env/firebase-keys.json` so they never land in git.
- The files set the API base URL, the Firebase app config and the Sentry DSN. All are public client identifiers, not secrets.
- With no file, the app talks to `localhost:8000`, or `10.0.2.2:8000` from the Android emulator.

**Layers.** Screens never call the API directly.
- Screens use Riverpod providers (`lib/src/providers.dart`).
- The providers wrap repositories: `AuthRepository`, `ProfileRepository`, `GigsRepository`, `ApplicationsRepository` (with `MediaUploader`) and `VerificationRepository`.
- The repositories use one Dio client.
- Tests override the providers, or swap in a fake HTTP adapter, so no screen needs a network.

**Sign-in.**
1. Firebase phone OTP proves the number. Android may read the SMS itself.
2. The Firebase ID token is exchanged once at `/api/v1/auth/exchange/`, and the Firebase session is dropped.
3. The API's tokens are kept in flutter_secure_storage: the Keychain on iOS (this device only, not synced) and encrypted storage on Android.

`AuthInterceptor` attaches the access token. On a 401 it refreshes once and retries. It is a queued interceptor, so parallel 401s share one refresh, because refresh tokens rotate and a reused one is blacklisted.
- A rejected refresh clears the tokens and signs the person out.
- A network failure keeps the session.

**Navigation.** `redirectFor` in `lib/src/router.dart` is a pure function of the session:
- Loading → splash.
- Signed out → `/login`.
- No role → `/join` (join as talent).
- Vendor or admin → `/wrong-app`.
- Incomplete profile → `/setup`.
- Everyone else → the bottom bar: Discover, My trips, Wallet, Profile.

**Profile setup.** The form checks the API's rules before submitting:
- Date of birth: 18 or older, counted on today's date in India. The picker won't offer a later date.
- At least one skill (from `/api/v1/profiles/skills/`) and one language.
- An emergency contact whose number isn't the user's own.

Field errors from the API are shown on the matching fields.

**Discover.** `GET /api/v1/gigs/` with filter chips (pay model), a search box and a filter sheet (sort, role, stay, city, dates, how long you can stay, verified hosts, saved searches). Pages load with the keyset cursor as you scroll.
- The map uses flutter_map with OpenStreetMap tiles. Each gig sits at its property's approximate point with its radius drawn; the API never sends the exact one before booking. Nearby gigs cluster on a grid (`clusterByGrid`). "Search this area" sets a point and radius, which also enables the distance sort.
- OSM tile policy: the credit "© OpenStreetMap contributors" is always on the map and opens the copyright page; tiles are requested with the app's User-Agent (`in.barterly.barterly`) and no prefetching. Set `MAP_TILE_URL` (a `--dart-define`) to move to another tile server before traffic grows.

**Gig and apply.** The gig screen uses the discover card, plus `GET /api/v1/gigs/{id}/public/` for the description and screening questions (live gigs only; a gig that stopped taking applications shows its card fields). Applying uploads each photo or video (`upload-url` → PUT to the signed URL without the API token → `confirm`), then posts the pitch, dates, answers and attachments (up to 8, or https links). A 422 `application_blocked` lists every reason. The agreement checkbox is checked in the app only: the apply API has no field for it.

**Offline.**
- The last first page of discover is kept on the device (shared_preferences). Without a network the feed shows it under an offline banner, with the time it was saved, and refreshes when the network returns.
- An application sent offline, or cut off mid-send, goes into an outbox kept on the device, with picked files copied to app storage. It is sent when connectivity returns (or on "Send now" in My trips). Uploads that finished are remembered so a retry doesn't repeat them. If the API refuses it, it stays in My trips with the reasons.

**Verification.** `/profile/verification` lists the checks from `GET /api/v1/verification/me/` with their status and the active badges. The ID and selfie check opens the KYC provider's hosted page (`redirect_url`, https only) in the in-app browser (SFSafariViewController / Custom Tabs); the status refreshes when the app comes back. Linking Instagram saves the handle on the profile, submits the social check and shows the code to put in the bio.

**Crash reporting.** Sentry starts only when `SENTRY_DSN` is set. Reports carry the account id, never the phone number, and personal data is off (`sendDefaultPii = false`).

**Firebase setup still needed per environment.**
1. Add iOS and Android apps to the Firebase project and enable Phone sign-in.
2. Put their app ids and API key in `env/*.json`.
3. Add the Android SHA-256 fingerprints.
4. On iOS, add the reversed client id (or the encoded app id) as a URL scheme in `ios/Runner/Info.plist`, for the reCAPTCHA fallback, and upload an APNs key so codes can be verified silently.

Until then, sign-in says it isn't available.

## Commands

| Task | backend/ | web/ | mobile/ |
| --- | --- | --- | --- |
| Install | `uv sync` | `npm ci` | `flutter pub get` |
| Run | `uv run python manage.py runserver` | `npm run dev` | `flutter run --dart-define-from-file=env/local.json --dart-define-from-file=env/firebase-keys.json` |
| Lint | `uv run ruff check .` | `npm run lint` | `flutter analyze --fatal-infos` |
| Format check | `uv run ruff format --check .` | `npm run format:check` | `dart format --output=none --set-exit-if-changed .` |
| Type check | — | `npm run typecheck` | (part of analyze) |
| Unit tests | `uv run pytest --cov` | `npm test` | `flutter test` |
| E2E / integration | — | `npm run test:e2e` | `flutter test integration_test` |
| Build | — | `npm run build` | `flutter build apk --dart-define-from-file=env/production.json --dart-define-from-file=env/firebase-keys.json` (or `ios`) |
| Dependency audit | `uv export … \| uvx pip-audit` | `npm audit` | — |

The backend needs Postgres: `docker compose up -d db` from `backend/`, and `DJANGO_DEBUG=1` for local runs.

## Deployment

- Merge to `main` → `deploy.yml` builds `api:<sha>` and `web:<sha>`, deploys staging.
- Push tag `v*.*.*` → after approval on the `production` GitHub environment, promotes the same images to production.
- Each deploy: new API revision with no traffic → migrate job (`manage.py release`: migrate + collectstatic) → smoke test of the candidate URL → 100% traffic. Then web.
- Setup, IAM and recreation steps: [infra/README.md](../infra/README.md). Rollback: [infra/ROLLBACK.md](../infra/ROLLBACK.md).

## CI

Each workflow runs on pushes to `main` and on pull requests, filtered by path so it runs only when its folder or its own workflow file changes.

- **backend.yml**: `lint` (ruff check + format check); `test` with a Postgres 16 service (Django check, `makemigrations --check`, migrate, OpenAPI validation, pytest with coverage, an 85% gate on `apps/*/services/*`); `audit` (pip-audit on the locked dependencies).
- **web.yml**: ESLint, Prettier check, generated API types up to date, `tsc`, Vitest, `next build`, `npm audit`, Playwright on Chromium.
- **infra.yml**: `terraform fmt -check`, `terraform validate` for every root, shellcheck on the scripts.
- **backend.yml** / **web.yml** also build the Docker image and check that it runs as non-root.
- **mobile.yml**: `dart format` check, `flutter analyze --fatal-infos`, `flutter test`. Integration tests need a device and are not run in CI yet.
