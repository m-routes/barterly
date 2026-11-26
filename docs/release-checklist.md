# Release checklist

Copy this into the release PR's description and tick it off. The why is in
[release.md](release.md).

## One-time setup before the first production launch

Done by a person with project owner / store admin access. Claude doesn't do these.

**GCP and DNS** ([edge.md](edge.md))
- [ ] `terraform.tfvars` for staging and production with the domains and
      `edge_enabled = true`, then `terraform apply` in `infra/terraform/shared`
      (enables the compute API) and in both environments.
- [ ] A records at the registrar for every entry of `terraform output` →
      `environment.dns_records` (staging and production). Add a CAA record for
      `pki.goog` if the zone uses CAA.
- [ ] The managed certificate shows `ACTIVE` for every domain.
- [ ] `infra/scripts/set-cdn-key.sh <env>`, then `media_cdn_signing_enabled = true`,
      apply, and redeploy.
- [ ] Unsigned `https://media.<domain>/…` returns 403; a signed URL from the API loads.
- [ ] Cloud Armor in preview (`armor_preview = true`) for a few days on staging, then
      production. Review the denied-request logs, then switch preview off.
- [ ] `X-Forwarded-For` reaches the API as `<client>, <lb ip>` (one request through the
      edge, then check the API log's `ip` in an audit entry). If Google adds more
      hops, extend `EDGE_PROXY_IPS`.

**GitHub**
- [ ] Environment `production`:
  - required reviewers (at least one person other than whoever tags);
  - deployment branches and tags: tags matching `v*.*.*` only;
  - "Prevent self-review" on.
- [ ] Environment variables: `PUBLIC_API_URL` and `PUBLIC_WEB_URL` (the custom domains)
      on `staging` and `production`, and `WEB_URL` set to the canonical domain. Repository
      variable `MEDIA_CDN_ORIGINS=https://media.barterly.in,https://media.staging.barterly.in`.
- [ ] Environment `mobile-release`:
  - required reviewers;
  - tags `mobile-v*.*.*`;
  - secrets `ANDROID_UPLOAD_KEYSTORE_BASE64`, `ANDROID_UPLOAD_STORE_PASSWORD`,
    `ANDROID_UPLOAD_KEY_ALIAS`, `ANDROID_UPLOAD_KEY_PASSWORD`, `FIREBASE_KEYS_JSON`,
    `SENTRY_AUTH_TOKEN`;
  - vars `SENTRY_ORG`, `SENTRY_PROJECT_MOBILE`.
- [ ] Labels: `breaking`, `feature`, `security`, `skip-changelog` (the others exist).

**Mobile**
- [ ] Android upload key created and stored in the password manager
      ([release.md](release.md#signing)). Play App Signing enrolled on first upload.
- [ ] Apple Developer team, the App ID `in.barterly.barterly` with Push Notifications,
      and an APNs key uploaded to Firebase.
- [ ] Production Firebase apps (Android and iOS) registered. Their app ids go in
      `mobile/env/production.json`. The API keys go in the uncommitted
      `env/firebase-keys.json` and the `FIREBASE_KEYS_JSON` secret.
- [ ] `SENTRY_DSN` set in `mobile/env/production.json` (a public value).
- [ ] **Brand art**: the launcher icons are still Flutter's default. Supply:
  - an adaptive icon (Android) and a 1024×1024 App Store icon;
  - a Play feature graphic (1024×500);
  - 4–8 phone screenshots (1080×1920 or larger, 9:16) from the QA seed data;
  - iOS screenshots at 6.9" and 6.5".
- [ ] Privacy policy and account deletion pages live (`feat/privacy`, PR #33), with
      their URLs in both consoles.
- [ ] Play: listing text from `mobile/store/play/en-IN/`, Data safety and App Store
      privacy answers from [store-privacy.md](store-privacy.md), content rating,
      target audience 18+, app access (reviewer account), testing track requirements.
- [ ] App Store: privacy labels, age rating, review notes and account, export
      compliance.
- [ ] Settle the "Sensitive Info" question in [store-privacy.md](store-privacy.md) with
      legal.

## Every API and web release

- [ ] Release PR: `infra/scripts/changelog.sh vX.Y.Z`, review `CHANGELOG.md`, merge.
- [ ] Breaking API change? It follows [api-versioning.md](api-versioning.md): the
      replacement shipped, the deprecation is in `deprecation.py`, and the app version
      that handles it is fully rolled out.
- [ ] Migrations are expand-only for this release (no drops or renames of anything
      the running release uses).
- [ ] Staging runs the merge commit, and the acceptance suite is green on it.
- [ ] Error rate and latency on staging are normal; no new Sentry issues.
- [ ] `git tag -a vX.Y.Z <sha> && git push origin vX.Y.Z`.
- [ ] Approve in GitHub → Actions → deploy → production.
- [ ] The deploy job is green, including the public-domain checks, and the GitHub
      release is published.
- [ ] Watch the production dashboard and Sentry for 30 minutes. Roll back
      ([runbook](runbooks/bad-deploy-rollback.md)) on an error-rate or SLO burn alert.

## Every app release

- [ ] `version:` bumped in `mobile/pubspec.yaml`, and `release_notes.txt` updated.
- [ ] Any API the build needs is already in production.
- [ ] `store/data_safety.json`, the iOS privacy manifest and the consoles updated if
      the app collects anything new (the store test passes).
- [ ] `flutter analyze --fatal-infos` and `flutter test` green; acceptance suite green
      on staging with a staging build.
- [ ] Android: tag `mobile-vX.Y.Z`, approve `mobile-release`, download the AAB
      artifact, upload it to **internal testing**.
- [ ] iOS: `SENTRY_AUTH_TOKEN=… tool/build_release.sh ipa env/production.json`
      on the release Mac, then upload with Transporter or Xcode.
- [ ] Symbols uploaded to Sentry for both builds (`barterly@X.Y.Z+BUILD`), and
      `build/symbols` kept.
- [ ] Smoke test on real devices: sign-in, discover, apply with a photo, chat, the
      check-in pass offline, push, and the update prompt (set `latest_version` above
      this build on staging).
- [ ] Staged rollout per [release.md](release.md#staged-rollout): 5% → 20% → 50% → 100%
      on Play, phased release on iOS, checking the gates at each step.
- [ ] At 100% on both stores: raise `latest_version` for each platform in the back
      office (reason: "vX.Y.Z fully rolled out").
- [ ] Raise `minimum_version` only when a breaking API change needs it, and a week
      after the version that handles it reaches 100%.
