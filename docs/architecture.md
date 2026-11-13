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
│   ├── src/app/        routes and layouts
│   ├── src/lib/        shared, framework-free logic
│   ├── Dockerfile      Next.js standalone server, non-root
│   └── e2e/            Playwright tests
├── mobile/             Flutter talent app
│   ├── lib/src/        app code
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
| `profiles` | `TalentProfile` and `VendorProfile` (one per user, role must match, soft-deleted) |

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

## Commands

| Task | backend/ | web/ | mobile/ |
| --- | --- | --- | --- |
| Install | `uv sync` | `npm ci` | `flutter pub get` |
| Run | `uv run python manage.py runserver` | `npm run dev` | `flutter run` |
| Lint | `uv run ruff check .` | `npm run lint` | `flutter analyze --fatal-infos` |
| Format check | `uv run ruff format --check .` | `npm run format:check` | `dart format --output=none --set-exit-if-changed .` |
| Type check | — | `npm run typecheck` | (part of analyze) |
| Unit tests | `uv run pytest --cov` | `npm test` | `flutter test` |
| E2E / integration | — | `npm run test:e2e` | `flutter test integration_test` |
| Build | — | `npm run build` | `flutter build apk` / `flutter build ios` |
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
- **web.yml**: ESLint, Prettier check, `tsc`, Vitest, `next build`, `npm audit`, Playwright on Chromium.
- **infra.yml**: `terraform fmt -check`, `terraform validate` for every root, shellcheck on the scripts.
- **backend.yml** / **web.yml** also build the Docker image and check that it runs as non-root.
- **mobile.yml**: `dart format` check, `flutter analyze --fatal-infos`, `flutter test`. Integration tests need a device and are not run in CI yet.
