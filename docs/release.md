# Releasing Barterly

Two things are released, on their own schedules:

| What | How it ships | Version |
| --- | --- | --- |
| API + web console | A `vMAJOR.MINOR.PATCH` git tag on a commit staging already runs, approved in the GitHub environment `production` | The tag, e.g. `v1.3.0` |
| Talent app (Android, iOS) | A store build from `mobile/tool/build_release.sh`, then a staged rollout in each store | `mobile/pubspec.yaml` `version`, plus a build number |

The step-by-step list is in [release-checklist.md](release-checklist.md). This page
explains the moving parts.

## API and web: tag-based, approved deploys

1. Everything reaches `main` through a PR, and every merge deploys staging
   (`.github/workflows/deploy.yml`, job `staging`). The images are built once, tagged
   with the commit SHA.
2. **Release PR.** On a branch, run `infra/scripts/changelog.sh vX.Y.Z`. It writes the
   release's section of `CHANGELOG.md` from the PRs merged since the last tag. Review
   it, fix PR titles if needed, and merge. Mention any breaking API change and its
   minimum app version ([api-versioning.md](api-versioning.md)).
3. **Check staging.** Confirm staging runs that merge commit. The acceptance suite
   (`acceptance.yml`, from `feat/acceptance`) runs after each staging deploy and must
   be green.
4. **Tag** the merge commit and push the tag:

   ```bash
   git tag -a v1.3.0 -m "v1.3.0" <sha> && git push origin v1.3.0
   ```

5. **Approve.** The `production` job waits for a required reviewer on the GitHub
   environment `production`. The environment only accepts `v*.*.*` tags. Then the job:
   - refuses a tag that isn't `vX.Y.Z` or isn't on `main`;
   - checks that the `api:<sha>` and `web:<sha>` images exist (production never
     builds);
   - runs `infra/scripts/deploy.sh production <sha>`: candidate revision, migrations,
     smoke test, traffic, the same for web, then a check through the public domains;
   - publishes the GitHub release, with notes generated from the merged PRs and
     grouped by label (`.github/release.yml`).
6. **Watch** the dashboard and Sentry for 30 minutes
   ([operations.md](operations.md)). To roll back, follow
   [runbooks/bad-deploy-rollback.md](runbooks/bad-deploy-rollback.md).

Migrations are expand/contract (CONTRIBUTING.md). The previous revision keeps serving
while they run, and a rollback doesn't need a down-migration.

**Labels for release notes:**
- `breaking`, `enhancement`/`feature`, `bug`, `security`, `accessibility`,
  `documentation`;
- `skip-changelog` hides a PR;
- anything else goes under "Other changes".

## Talent app

### Versioning

- **Version name** (`1.4.2`, semantic): `version:` in `mobile/pubspec.yaml`, bumped in
  the release PR.
  - Patch: fixes only.
  - Minor: features, or an API change behind a compatible endpoint.
  - Major: drops support for something people use.
- **Build number** (Android `versionCode`, iOS `CFBundleVersion`): must always go up.
  `build_release.sh` uses the number of commits on `HEAD` by default (it grows with
  every merge to `main`); CI can pass `BUILD_NUMBER`.
  - Never reuse one, even for a build that was rejected.
  - Android's limit is 2,100,000,000.
- **Tag**: `mobile-vX.Y.Z` on the commit the store build came from, which also runs
  `.github/workflows/mobile-release.yml`.
- **Sentry release**: `barterly@X.Y.Z+BUILD`, the same name the app reports and the
  symbols are uploaded under.

### Signing

| | Android | iOS |
| --- | --- | --- |
| Key | Upload key (a `.jks` keystore). Google holds the app signing key (Play App Signing) | Apple Distribution certificate and an App Store provisioning profile for `in.barterly.barterly`, managed by Xcode (automatic signing) |
| Where it lives | A password manager, plus the `mobile-release` GitHub environment's secrets for CI. Never in the repo: `android/key.properties` and `*.jks` are gitignored | The Mac that builds, signed in to the team. `ios/ExportOptions.plist` (gitignored) names the team |
| Lost it? | Ask Google to reset the upload key (Play Console → App integrity). The app key is safe with Google | Revoke and recreate in the developer portal |

Create the Android upload key once:

```bash
keytool -genkeypair -v -keystore barterly-upload.jks -alias upload -keyalg RSA -keysize 4096 -validity 10000
```

`android/app/build.gradle.kts` reads it from `android/key.properties` (see
`key.properties.example`) or the `BARTERLY_UPLOAD_*` environment variables. Without a
key, a production app bundle is refused by `build_release.sh`. Local
`flutter run --release` falls back to the debug key.

### Obfuscation and crash symbols

`build_release.sh` builds with `--obfuscate --split-debug-info=build/symbols`, plus R8
and resource shrinking on Android. Then `sentry_dart_plugin` uploads the Dart symbols
(`SENTRY_AUTH_TOKEN`, `SENTRY_ORG`, `SENTRY_PROJECT`), so Sentry shows readable stack
traces. Keep `build/symbols` from every store build as a CI artifact or in storage
until that version is retired. Without it, crashes from that build can't be read.

Crash reporting needs `SENTRY_DSN` in `mobile/env/production.json`. It's empty today,
so production builds report nothing until it's set (the DSN is public).

### Store listings

`mobile/store/` holds what goes into the consoles:
- `play/en-IN/`: title, short and full description, release notes. A test checks the
  console's length limits.
- `data_safety.json`: the Data safety and App Privacy answers, explained in
  [store-privacy.md](store-privacy.md).

The graphics come from design; the specs are in the checklist.

### Staged rollout

Android (Play Console), for each release:

| Day | Track and share | Go on when |
| --- | --- | --- |
| 0 | **Internal testing** (team, about 20 people), then **closed testing** with QA's accounts | Smoke checklist passes on a low-end Android (2 GB RAM) and a recent one |
| 1 | **Production 5%** | Crash-free users ≥ 99.5% (Play vitals and Sentry), no new top crash, ANR rate < 0.47%, no spike in API 4xx/5xx by app version |
| 3 | **20%** | Same, plus support tickets normal |
| 5 | **50%** | Same |
| 7 | **100%** | Same; then raise `latest_version` for Android ([api-versioning.md](api-versioning.md)) |

iOS (App Store Connect): submit for review with **phased release for automatic
updates**. Apple's 7-day schedule (1%, 2%, 5%, 10%, 20%, 50%, 100%) matches the
gates above. People can still update by hand from the store. Release manually after
approval, during working hours IST.

**Halting:**
- Play Console: **Halt rollout**. iOS: **Pause phased release**.
- If a crash is in a server path, roll back the API instead (tag-based).
- A broken app version can't be withdrawn from phones that have it. If it corrupts
  data, raise `minimum_version` above it once the fix is out (see "Breaking change
  emergency" in [api-versioning.md](api-versioning.md)).

### First release (1.0.0) on top of that

- Play: start with **internal testing**, then **closed testing** for at least 14 days
  with 12 or more testers. Google requires this before production access for new
  personal developer accounts; organisation accounts can skip it.
- Fill in the Play listing, content rating (IARC questionnaire), target audience
  (18+), Data safety, the app access instructions (a reviewer test account from the
  QA seed) and the privacy policy URL.
- App Store: privacy labels, age rating, the review notes with a test account, and
  export compliance (HTTPS only: standard encryption, exempt).
