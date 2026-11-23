# Security

This page records how Barterly meets OWASP ASVS 4.0 Level 2 across the API, the web
app and the mobile app. It lists the decisions we made where the standard leaves a
choice, the CI checks that keep the controls in place, and the secret-rotation drill.
The abuse cases for money, contact unlock and SOS are in
[threat-model.md](threat-model.md).

## ASVS Level 2 mapping

| ASVS | Control | Where |
| --- | --- | --- |
| V1 Architecture | Threat model for the risky flows; trust boundaries | [threat-model.md](threat-model.md) |
| V2 Authentication | Phone OTP via Firebase. API sessions are short-lived JWTs, with refresh tokens rotated and blacklisted. Signing an agreement needs a fresh OTP. | `apps/accounts`, `apps/agreements` |
| V3 Session management | Web: tokens only in httpOnly, Secure, SameSite=Lax cookies, behind a same-origin BFF that checks Origin on unsafe methods. Admin: Django session and CSRF cookies are Secure and HttpOnly. Mobile: tokens in Keychain or Keystore. | `web/src/lib/server`, `config/settings/deployed.py`, `mobile/lib/src/api/token_store.dart` |
| V4 Access control | Every endpoint is checked for role and object scope. Staff need the specific back-office permission (`staff_can`, `IsStaffWith`); a staff account with no role gets nothing. CI walks every endpoint in the schema. | `apps/common/permissions.py`, `apps/backoffice/roles.py`, `apps/core/tests/test_access_control.py` |
| V5 Validation | Serializers validate everything. Every request string has a `maxLength` (or a pattern) and every list a `maxItems`, enforced by a test over the schema. Bodies are capped at 1 MB (413). Queries go through the ORM only; the few raw SQL statements quote identifiers and bind values. | `test_request_bodies_are_size_limited`, `DATA_UPLOAD_MAX_MEMORY_SIZE` |
| V6 Cryptography | AES-256-GCM field encryption for emergency contacts and payout references, with keys in Secret Manager and rotation. Ed25519 check-in passes. HMAC on webhooks. | `apps/common/encryption.py` |
| V7 Errors and logging | JSON logs carry a request id. Phone numbers, emails, UPI ids, PAN, Aadhaar, account numbers and tokens are redacted from every log record and Sentry event. Money and status changes are audit-logged. | `apps/common/redaction.py`, `config/sentry.py`, `apps/common/services/audit.py` |
| V8 Data protection | No PII in URLs. Sentry runs with `send_default_pii` off, no local variables and no request bodies. Mobile: no backups, and sensitive screens are protected. | see Mobile below |
| V9 Communications | HTTPS only: SSL redirect, HSTS (one year with preload in production, one hour on staging), cleartext traffic blocked on Android. | `config/settings/*`, `web/src/lib/security/headers.ts` |
| V10 Malicious code | Dependency and secret scanning, SAST, image scanning (see CI below). | `.github/workflows` |
| V12 Files | Uploads go straight to Cloud Storage through signed URLs (at most 15 minutes; `check_link_lifetime` refuses longer). The allowed type, size and magic bytes are checked per kind. ClamAV scans every upload when enabled. Files are always served from the storage domain, never ours. | `apps/media` |
| V13 API | OpenAPI for every endpoint. No CORS. A strict CSP on API responses. JSON only. | `apps/common/middleware.py` |
| V14 Configuration | Security headers on every response. `check --deploy` runs in CI. Secrets only in Secret Manager. Containers run as non-root. | below |

## Headers

| Header | API (Django) | Web (Next.js) |
| --- | --- | --- |
| Strict-Transport-Security | 1 year with preload (production), 1 hour (staging) | 1 year with preload (production builds) |
| Content-Security-Policy | `default-src 'none'; frame-ancestors 'none'` on the API. The admin gets `script-src 'self'` plus the static bucket. | See "Web CSP" |
| X-Frame-Options | DENY | DENY |
| X-Content-Type-Options | nosniff | nosniff |
| Referrer-Policy | same-origin | strict-origin-when-cross-origin |
| Permissions-Policy | everything off | camera and geolocation for our own pages only |
| Cross-Origin-Opener-Policy | same-origin | same-origin-allow-popups (Firebase sign-in) |
| CORS | none: no `Access-Control-*` headers for any origin (tested) | not needed (the BFF is same-origin) |

### Web CSP

The web app uses Cache Components (partial prerendering), so most pages are prerendered
at build time. Next.js inlines each page's RSC payload as `<script>` tags. A
per-request nonce can't reach those prerendered scripts (Next.js documents PPR and
nonces as incompatible), and their content changes per build, so they can't be hashed.

**Decision:** one fixed policy, with `script-src 'self' 'unsafe-inline'` plus Google's
sign-in hosts. Build-time SRI hashes (`experimental.sri`) cover every script file. Every
other directive is strict: `object-src 'none'`, `base-uri 'self'`,
`form-action 'self'`, `frame-ancestors 'none'`, a short `connect-src` allow-list, and
`upgrade-insecure-requests`. We tried a nonce policy, and it blocked hydration on 11 of
the 15 e2e journeys.

What still protects against XSS: React escapes all output, there is no
`dangerouslySetInnerHTML` on user content, and the API's own responses can't run
script (`default-src 'none'`). Revisit when Next.js supports nonces or hashes with PPR,
or if we move the signed-in console to dynamic rendering.

## Mobile

- **Token storage:** access and refresh tokens are kept in the iOS Keychain
  (`first_unlock_this_device`, so they're not in iCloud Keychain or backups) and in
  Android Keystore-backed storage (`flutter_secure_storage`). Nothing sensitive goes in
  shared preferences.
- **Backups:** Android has `allowBackup=false`, and its `dataExtractionRules` exclude
  everything from cloud backup and device transfer. On iOS, the Keychain items above are
  device-only.
- **Screenshots and the app switcher:** the wallet, link-account, check-in pass and
  profile (emergency contact) screens use `SecureScreen`.
  - On Android it sets FLAG_SECURE: no screenshots, no recordings, a blank app-switcher
    preview.
  - On both platforms the screen is covered while the app is inactive. That's when iOS
    takes its snapshot.
  - iOS has no API that blocks screenshots, so they stay possible there.
- **Rooted or jailbroken devices:** at start-up the app looks for common traces: `su`
  and Magisk paths and `test-keys` builds on Android; Cydia, Sileo and rootless paths on
  iOS. It reports them to Sentry as a non-fatal `DeviceIntegrityNotice`. It doesn't
  block the user: these checks are easy to bypass, and blocking would lock out
  legitimate users with rooted phones. If abuse appears, Play Integrity and App Attest
  are the next step.
- **Certificate pinning:** we decided not to pin.
  - The API and web are served by Google-managed certificates on Cloud Run, which
    rotate on Google's schedule without notice. A pinned leaf or intermediate would take
    the app offline until users update it.
  - Pinning Google's root CAs adds little over the platform trust store.
  - We rely on the OS trust store, HSTS, HTTPS-only (cleartext blocked) and short-lived
    tokens.
  - Revisit this if we move to our own certificate or a CDN with a stable pin, or if the
    threat model gains a network attacker able to install CAs on users' devices (then
    use dynamic pinning with backup pins and a kill switch).

## Uploads

1. The client asks for a signed PUT URL (15 minutes; one content type and size range).
2. The client uploads straight to the private bucket.
3. The client calls `confirm`.
4. The server checks the object's size and magic bytes against the declared type.
   Images are re-encoded.
5. `process_media` scans the file before it can be served:
   - With `clamav_enabled` in Terraform, a clamd sidecar runs beside the API and
     `CLAMAV_HOST` switches on `ClamdVirusScanner`.
   - It streams the file with INSTREAM.
   - Infected files are deleted and the record quarantined.
   - When clamd is down, the task fails and retries.
   - `MEDIA_REQUIRE_SCAN` then defaults to on: an unscanned file is never served.
6. Reads use signed GET URLs (5 minutes, at most 15).

Turning it on: set `clamav_enabled = true` for the environment and apply. The sidecar
needs about 2 GiB, which is why it's off by default.

## Secrets

Every secret lives in Secret Manager and reaches Cloud Run as an env var from a secret
reference. None are in code or in Terraform state. Local runs derive keys from the
local `SECRET_KEY`. Deployed settings refuse to start without `DJANGO_SECRET_KEY`,
`ATTENDANCE_SIGNING_KEY` and `FIELD_ENCRYPTION_KEYS`. gitleaks scans the full git
history on every PR.

| Secret | Rotated by |
| --- | --- |
| `django-secret-key-*` | `rotate-secrets.sh django-key`. This signs everyone out (API tokens are HS256). |
| `attendance-signing-key-*` | `rotate-secrets.sh attendance-key`, after the old public key is moved to `ATTENDANCE_PREVIOUS_PUBLIC_KEYS` |
| `field-encryption-keys-*` | `rotate-secrets.sh field-keys` → deploy → `reencrypt` → `drop-old-keys` |
| `database-url-*` | Terraform (database password resource) |
| Razorpay, RazorpayX, KYC, Sentry, SMTP, YouTube, Instagram | In the provider's dashboard; then `gcloud secrets versions add` and `rotate-secrets.sh restart` |

### Secret rotation drill

Run it once a year on production and after any suspected leak. Rehearse it on staging
first. Each step is a subcommand of `infra/scripts/rotate-secrets.sh`, and each one asks
for confirmation:

1. `audit`: list every secret, its newest version's date and who can read it. Remove
   readers who shouldn't be there.
2. `field-keys`: add a new key at the front. Deploy, or run `restart`.
3. `reencrypt`: re-encrypt every encrypted column under the new key, then confirm with
   `--check`.
4. `drop-old-keys`, then `restart`.
5. `attendance-key` (after the public-key step), then `restart`.
6. Provider secrets, one at a time: rotate in the dashboard, add the version, run
   `restart`, and watch the webhook delivery logs.
7. `django-key` last, in a quiet hour (everyone signs in again), then `restart`.
8. Disable the old versions (don't destroy them). Destroy them a week later.
9. Record the date, who ran it and any problems in the ops log.

**Status:** I haven't run the drill. The script, the runbook and the tests for key
rotation and re-encryption (`apps/common/tests/test_encryption.py`) are ready. A person
with Secret Manager admin rights needs to run it on staging, then on production.

### Field encryption rollout

The encryption migrations (`money.0005`, `profiles.0005`) are expand-only:
- Columns are widened to text.
- New writes are encrypted.
- Existing plaintext rows stay readable.

After the first deploy that includes them:

1. Set `field-encryption-keys-<env>` with `set-secrets.sh` before the deploy. Deployed
   settings require it.
2. Deploy.
3. Run `rotate-secrets.sh <env> reencrypt`. This encrypts the old rows. It waits until
   after the deploy because an old revision still serving would otherwise send
   ciphertext to RazorpayX.
4. Contract step, in a later release: remove the plaintext fallback in `decrypt()`.

The reverse migration decrypts every row before narrowing the columns, so a rollback
is safe.

## CI security checks

| Check | Workflow | Fails the build on |
| --- | --- | --- |
| Access-control walker, schema size limits | backend (pytest) | any leak, change, oracle or unbounded field |
| bandit | backend `sast` | any finding (false positives carry `# nosec` with a reason) |
| semgrep `p/django` + `p/python` | backend `sast` | any finding |
| pip-audit | backend `audit` | any known vulnerability |
| trivy (API and web images) | backend and web `docker` | fixable HIGH or CRITICAL |
| eslint-plugin-security | web (lint, `--max-warnings=0`) | any warning |
| npm audit | web | moderate or worse |
| Security headers served | web `docker` | missing CSP, XFO, nosniff or HSTS |
| gitleaks (full history) | security | any secret |
| dependency-review | security (PRs) | a new dependency with a moderate-or-worse advisory |
| OSV-Scanner (`pubspec.lock`, `package-lock.json`, `uv.lock`) | security, plus weekly | any known vulnerability |
| OWASP ZAP baseline | zap (after staging deploys, weekly) | new warnings beyond `.zap/rules.tsv` |

ZAP needs the repository variables `STAGING_WEB_URL` and `STAGING_API_URL`.
