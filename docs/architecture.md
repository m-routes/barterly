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
- Money and status changes write an audit log entry.
- Migrations must be reversible.

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
