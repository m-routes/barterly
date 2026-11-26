# First production deploy: runbook

The exact order to take Barterly from today's state to production. Run each step
yourself; every command is copy-paste. Written 2026-11-24 against GCP project
`project-19c38b75-2d9e-4394-ae1` (number `430344535597`), region `asia-south1`.
Background: [release.md](release.md) and [edge.md](edge.md). Tick-list:
[release-checklist.md](release-checklist.md).

## Where things stand

- Production and staging Cloud Run services exist. Production runs an early build
  (revision 2). Staging runs `main` as of PR #19 (16 Nov).
- Everything since is in the `integrate/prod` PR. It combines the stacked PRs
  #20–#36 with `feat/acceptance` (#35) and `feat/privacy` (#33), and resolves their
  conflicts (all additive). Its checks are green.
- Terraform state exists for `shared`, `staging` and `production` in
  `gs://project-19c38b75-2d9e-4394-ae1-tfstate`.
- Every existing secret has a value. New ones are created by Terraform below.
- GitHub `production` has required reviewers. Staging and production `WEB_URL` point
  at run.app.

## Step 0: decide the domain (blocker)

`barterly.in` currently resolves to `160.153.0.18`, which isn't Google: it's
someone's existing site or parking page, and `api.barterly.in` doesn't resolve at
all. The edge, the production app build (`mobile/env/production.json` →
`https://api.barterly.in`) and the CSP all assume you control `barterly.in`'s DNS.

- **You own it:** carry on. You'll change its A records in step 4. The current site
  at `160.153.0.18` goes away then.
- **You don't own it, or want another domain:** replace `barterly.in` everywhere in:
  - `infra/terraform/envs/*/terraform.tfvars`;
  - `mobile/env/production.json` and the production default in
    `mobile/lib/src/config/env.dart`;
  - the `MEDIA_CDN_ORIGINS` variable (below).

  Then rebuild the app.

```bash
export PROJECT_ID=project-19c38b75-2d9e-4394-ae1
export STATE_BUCKET=${PROJECT_ID}-tfstate
gcloud config set project "$PROJECT_ID"
```

Run Terraform from a checkout of `integrate/prod` (or `main` once it's merged).
Terraform ≥ 1.11, or Docker:

```bash
alias terraform='docker run --rm -it -v "$PWD":/w -w /w -v "$HOME/.config/gcloud":/root/.config/gcloud hashicorp/terraform:1.13'
```

## Step 1: shared infra

```bash
cd infra/terraform/shared
terraform init -backend-config="bucket=${STATE_BUCKET}"
terraform plan    # expect: compute.googleapis.com (already enabled) and nothing destroyed
terraform apply
cd -
```

## Step 2: staging infra, without the edge first

In `infra/terraform/envs/staging/terraform.tfvars`, keep your current values and add:

```hcl
edge_enabled = false   # until staging DNS exists (step 4b)
```

```bash
cd infra/terraform/envs/staging
terraform init -backend-config="bucket=${STATE_BUCKET}"
terraform plan -out staging.plan
```

Read the plan before applying. Expect it to add:
- scheduler jobs (privacy retention and deletions);
- the QA job and its secret;
- monitoring;
- new secrets (`media-cdn-key-staging`).

It also changes Cloud Run env vars. Stop if it wants to **destroy or replace** Cloud
SQL, a bucket or a service.

```bash
terraform apply staging.plan
cd -
```

The QA admin password, for the acceptance suite:

```bash
openssl rand -base64 24 | tr -d '\n' | gcloud secrets versions add qa-admin-password-staging --data-file=-
gcloud secrets versions access latest --secret qa-admin-password-staging   # copy into GitHub secret E2E_ADMIN_PASSWORD
```

## Step 3: merge, then staging deploys itself

1. Merge the `integrate/prod` PR into `main` with **Create a merge commit**, not
   squash: that keeps each feature's history.
2. Close #20–#36 with a comment pointing at it.
3. `deploy.yml` builds the images, runs migrations (the privacy, security and
   appversions migrations are additive) and moves staging traffic. Watch it:

```bash
gh run watch --repo m-routes/barterly $(gh run list --repo m-routes/barterly --workflow deploy.yml --limit 1 --json databaseId -q '.[0].databaseId')
curl -fsS https://barterly-api-staging-430344535597.asia-south1.run.app/api/v1/health/
curl -fsS "https://barterly-api-staging-430344535597.asia-south1.run.app/api/v1/app/version/?platform=android"
```

4. Set up and run the acceptance suite. In GitHub, set:
   - variables `STAGING_WEB_URL`, `STAGING_API_URL` and the `E2E_FIREBASE_*` values;
   - secrets `E2E_OTP_CODE`, `E2E_ADMIN_PASSWORD`, `FIREBASE_KEYS_JSON`.

   See `docs/qa/README.md`. Then run it:

   ```bash
   gh workflow run acceptance.yml --repo m-routes/barterly
   ```

   Don't go on until it's green.

## Step 4: the edge (load balancer, TLS, Cloud Armor, CDN)

### 4a. Production infra

`infra/terraform/envs/production/terraform.tfvars`, keeping your current values:

```hcl
api_domains   = ["api.barterly.in"]
web_domains   = ["barterly.in", "www.barterly.in"]
media_domain  = "media.barterly.in"
edge_enabled  = true
armor_preview = true    # log-only for the first days
alert_emails  = ["you@yourdomain"]
```

```bash
cd infra/terraform/envs/production
terraform init -backend-config="bucket=${STATE_BUCKET}"
terraform plan -out production.plan   # same rule: nothing destroyed or replaced
terraform apply production.plan
terraform output -json environment | jq '.dns_records, .edge_ip, .certificate_name'
cd -
```

### 4b. DNS (at your registrar)

Make A records for `barterly.in`, `www`, `api` and `media` point at `edge_ip`, and
remove any old A/AAAA records for those names. Add `CAA 0 issue "pki.goog"` if the
zone has CAA records. Then wait for the certificate (15–60 minutes):

```bash
gcloud compute ssl-certificates describe <certificate_name> --global --format='value(managed.status, managed.domainStatus)'
```

For staging, do the same with its domains (`api.staging…`, `staging…`,
`media.staging…`, `edge_enabled = true`) once you want staging to mirror production.

### 4c. Media through the CDN

```bash
infra/scripts/set-cdn-key.sh production
# terraform.tfvars: media_cdn_signing_enabled = true ; then plan + apply again
```

Check it:

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://media.barterly.in/anything   # must be 403
curl -sI https://api.barterly.in/api/v1/health/ | head -1                       # HTTP/2 200
curl -sI http://barterly.in | grep -i location                                  # https://barterly.in/
```

## Step 5: GitHub settings for the production deploy

```bash
R=m-routes/barterly
gh variable set WEB_URL        --repo $R --env production --body https://barterly.in
gh variable set PUBLIC_API_URL --repo $R --env production --body https://api.barterly.in
gh variable set PUBLIC_WEB_URL --repo $R --env production --body https://barterly.in
gh variable set MEDIA_CDN_ORIGINS --repo $R --body "https://media.barterly.in,https://media.staging.barterly.in"
gh label create breaking --repo $R; gh label create feature --repo $R; gh label create security --repo $R; gh label create skip-changelog --repo $R
```

In the GitHub UI, under Settings → Environments → production:
- **Deployment branches and tags**: tags matching `v*.*.*` only.
- **Prevent self-review**: on.

`MEDIA_CDN_ORIGINS` is baked into the web image at build time. After setting it, the
next merge to `main` builds the image production will promote. Merge the release PR
(step 6) after this.

## Step 6: release PR, tag, approve

```bash
git switch -c release/v1.0.0 origin/main
infra/scripts/changelog.sh v1.0.0
git commit -am "Release v1.0.0" && git push -u origin release/v1.0.0
gh pr create --repo m-routes/barterly --base main --title "Release v1.0.0" --body "CHANGELOG for v1.0.0"
# merge it, wait for the staging deploy to finish green, then:
git fetch origin && git tag -a v1.0.0 -m v1.0.0 origin/main && git push origin v1.0.0
```

Approve the `production` job in Actions → deploy. It:
- checks the tag;
- promotes the images staging ran;
- migrates;
- smoke-tests run.app and then the public domains;
- publishes the GitHub release.

## Step 7: after the deploy

- Watch the **Barterly production** dashboard and Sentry for 30 minutes.
- Set Sentry on the API and web once you have a DSN:

  ```bash
  printf '%s' 'https://…@….ingest.sentry.io/…' | gcloud secrets versions add sentry-dsn-production --data-file=-
  ```

  Then set `sentry_enabled = true` in the production tfvars and apply.
- After 3–7 days, review Cloud Armor's preview logs ([edge.md](edge.md)), then set
  `armor_preview = false` and apply.
- Rollback: [runbooks/bad-deploy-rollback.md](runbooks/bad-deploy-rollback.md)
  (`infra/scripts/rollback.sh production <revision>`).

## Making the app production-ready

Done in code:
- version check and forced upgrade;
- permission explanations;
- Android signing config, R8 and obfuscation, Sentry symbols;
- iOS privacy manifest;
- store listing text and privacy answers;
- privacy screens (consent, export, deletion).

Still needed from you, in order:

1. **Brand art.** The launcher icons are Flutter's default. Supply:
   - an adaptive icon and a 1024×1024 icon;
   - a 1024×500 feature graphic;
   - screenshots (spec in [release-checklist.md](release-checklist.md)).
2. **Firebase production apps.** Register the Android (`in.barterly.barterly`) and iOS
   apps in the production Firebase project. Put the app ids in
   `mobile/env/production.json` and the API keys in `env/firebase-keys.json`
   (uncommitted). Add the release SHA-256 of the Play app-signing key and the upload
   key to the Android app in Firebase, or phone sign-in fails. Upload an APNs key for
   iOS push.
3. **Sentry DSN** (public) in `mobile/env/production.json`.
4. **Android upload key:**

   ```bash
   keytool -genkeypair -v -keystore ~/barterly-upload.jks -alias upload -keyalg RSA -keysize 4096 -validity 10000
   cp mobile/android/key.properties.example mobile/android/key.properties   # fill in; never commit
   ```

5. **Build and upload to Play internal testing:**

   ```bash
   cd mobile && BUILD_NUMBER=100 SENTRY_AUTH_TOKEN=… SENTRY_ORG=… SENTRY_PROJECT=… tool/build_release.sh appbundle env/production.json
   # upload build/app/outputs/bundle/release/app-release.aab in Play Console → Internal testing
   ```

   Or tag `mobile-v1.0.0` after filling the `mobile-release` environment's secrets.
6. **Play Console:**
   - listing (`mobile/store/play/en-IN/`);
   - Data safety and the App Store labels ([store-privacy.md](store-privacy.md));
   - content rating, target audience 18+;
   - app access (a reviewer test number);
   - privacy policy `https://barterly.in/legal/privacy` and account deletion
     `https://barterly.in/account/privacy`.

   Then closed testing (12+ testers for 14 days if it's a personal account), then the
   staged rollout ([release.md](release.md#staged-rollout)).
7. **iOS:**
   - an Apple Developer team;
   - copy `ios/ExportOptions.plist.example` to `ios/ExportOptions.plist` with your team
     id;
   - run `tool/build_release.sh ipa env/production.json` on a Mac and upload it;
   - privacy labels and review notes, then a phased release.

The app's production API URL only works after step 4 (DNS and certificate). Don't
release a production build before `https://api.barterly.in/api/v1/health/` answers.
