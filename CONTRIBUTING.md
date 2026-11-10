# Contributing to Barterly

## Workflow

1. Branch from `main` (`feature/<short-name>`, `fix/<short-name>`).
2. Before coding, read the relevant code and list the files you will change in the PR description.
3. Write tests with the code. Keep CI green; a PR does not merge with a red check.
4. After coding, run the lint and test commands for every folder you touched (see the README) and paste the results into the PR.

## Rules

- **Tests with the code.** Backend service modules (`apps/*/services/`) must stay at 85%+ coverage; CI enforces it.
- **Reversible migrations.** Every migration must apply and roll back. Use `RunPython` with a `reverse_code` (or `migrations.RunPython.noop` when safe). CI runs `makemigrations --check`.
- **Backwards-compatible migrations (expand/contract).** Migrations run while the previous release still serves traffic, so a release may only add things the previous release ignores (new nullable columns, new tables, new indexes created concurrently). Drop or rename in a later release, once no running code uses the old shape.
- **OpenAPI for every endpoint.** Annotate DRF views with `drf_spectacular.utils.extend_schema`. CI validates the schema with `--fail-on-warn`.
- **No secrets in code.** Configuration comes from environment variables (`backend/.env.example` lists them). The `detect-private-key` pre-commit hook and `.gitignore` help, but you are responsible.
- **Audit log on money and status changes.** Any change to payments, stipends, payouts or a record's status must write an audit entry recording who changed what, when, and from which value to which.
- **Business logic in services.** Views and serializers stay thin; logic lives in `apps/<app>/services/` so it is testable without HTTP.

## Pre-commit

```bash
pip install pre-commit   # or: uv tool install pre-commit
pre-commit install
pre-commit run --all-files
```

Hooks: ruff (lint + format) for `backend/`, ESLint and Prettier for `web/`, `dart format` for `mobile/`, plus whitespace, YAML and private-key checks. The web hooks need `npm ci` in `web/` first; the Dart hook needs Flutter on your `PATH`.

## Commit messages

Use the imperative mood and a short subject line: `Add listing search endpoint`. Reference the issue in the body when there is one.
