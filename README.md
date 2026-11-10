# Barterly

Work-exchange marketplace for travel and hospitality in India. Vendors list stays and roles, and talent applies under one of four pay models: volunteer (work for stay), barter (content for stay), hybrid (stay plus stipend) or paid.

| Folder | What | Stack |
| --- | --- | --- |
| `backend/` | API and admin console | Django 5, DRF, PostgreSQL |
| `web/` | Vendor console | Next.js (App Router), TypeScript |
| `mobile/` | Talent app | Flutter |
| `infra/` | Terraform (incl. Cloud SQL) and deploy scripts for staging and production | Terraform, gcloud |
| `docs/` | Architecture and decisions | — |

See [docs/architecture.md](docs/architecture.md) for the layout and [CONTRIBUTING.md](CONTRIBUTING.md) for the workflow.

## Prerequisites

- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- Node.js 24+ and npm
- Flutter (stable channel)
- Docker (for local Postgres)
- [pre-commit](https://pre-commit.com/)

## Setup

```bash
pre-commit install
```

## Backend

```bash
cd backend
cp .env.example .env            # local values only, never commit .env
docker compose up -d db         # Postgres 16 on localhost:5432
uv sync
export DJANGO_DEBUG=1
uv run python manage.py migrate
uv run python manage.py runserver   # http://localhost:8000/api/docs/
```

Checks:

```bash
uv run ruff check . && uv run ruff format --check .
uv run pytest --cov
uv run coverage report --include='apps/*/services/*' --fail-under=85
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py spectacular --validate --fail-on-warn --file openapi.yaml
```

## Web

```bash
cd web
npm ci
npm run dev            # http://localhost:3000
npm run lint && npm run format:check && npm run typecheck
npm test               # Vitest + React Testing Library
npm run build
npx playwright install chromium && npm run test:e2e
```

## Mobile

```bash
cd mobile
flutter pub get
flutter run
flutter analyze --fatal-infos
flutter test
flutter test integration_test   # needs a simulator, emulator or device
```

Settings modules: `config.settings.local` (default for `manage.py` and tests), `config.settings.staging`, `config.settings.production`.

## Docker

```bash
docker build -t barterly-api backend   # gunicorn + uvicorn workers, non-root, port 8080
docker build -t barterly-web web       # Next.js standalone, non-root, port 8080
```

## CI and deployment

GitHub Actions in `.github/workflows/`: `backend.yml`, `web.yml`, `mobile.yml` and `infra.yml` each run only when their folder (or their own workflow file) changes. `deploy.yml` deploys to staging on every merge to `main`, and to production on a `v*.*.*` tag after manual approval. See [infra/README.md](infra/README.md) for setup and [infra/ROLLBACK.md](infra/ROLLBACK.md) for rollback.
