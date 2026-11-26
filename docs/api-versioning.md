# API versioning and deprecation

The web console ships with the API: one tag deploys both, so it always matches. The
talent app doesn't. People update it days or months late, and some never do. These
rules keep old apps working until we choose to retire them, and make that choice
explicit.

## The version is in the path

Every endpoint lives under `/api/v1/`. A new major version (`/api/v2/`) is a last
resort, for a redesign that can't be done additively. Until then, `v1` only changes
in compatible ways.

### Compatible: ship any time

- New endpoints.
- New optional request fields, and new query parameters with a default.
- New response fields. Clients ignore fields they don't know (the Dart models read
  only what they use; keep it that way).
- New error codes on an endpoint that already returns errors in the
  `{code, message, details}` shape. Apps show `message` for codes they don't know.
- New enum values, **only** where the OpenAPI description says the list may grow.
  Apps map unknown values to a fallback such as "other".
- Looser validation: longer limits, more accepted formats.

### Breaking: needs the deprecation process

- Removing or renaming an endpoint, field, query parameter or enum value.
- Making an optional request field required, or tightening validation.
- Changing a field's type, format, units or meaning (for example rupees to paise).
- Changing pagination on an existing list, the error shape, or auth.
- Changing what a status code means for an endpoint.

The OpenAPI schema (`web/openapi/schema.yaml`, checked in CI against the code) is
the contract. Review its diff in every PR. Removed lines are a breaking change
unless they belong to something already past its sunset date.

## Deprecating something

1. **Add the replacement first.** Ship it, and an app version that uses it.
2. **Mark the old one deprecated.** Add an entry to
   `backend/apps/common/deprecation.py` with the date and the sunset date, at least
   **90 days** later (`MINIMUM_NOTICE_DAYS`, enforced by a test). Responses then carry:
   - `Deprecation: @<unix time>` ([RFC 9745](https://www.rfc-editor.org/rfc/rfc9745));
   - `Sunset: <date>` ([RFC 8594](https://www.rfc-editor.org/rfc/rfc8594));
   - `Link: <…/docs/api-versioning.md>; rel="deprecation"`.

   Also set `deprecated=True` in the view's `extend_schema`, so the OpenAPI schema
   says so, and add a row to the schedule below.
3. **Watch who still calls it.** Every call to a deprecated operation logs a line
   with `deprecated_call: true`, the path, `client_platform` and `client_version`
   (from the app's headers; empty for the web). In Cloud Logging, filter on
   `jsonPayload.deprecated_call=true` and group by `jsonPayload.client_version`.
4. **Raise the minimum app version** (below) to the first version that doesn't use
   it, once few enough people are on older ones. In Play Console and App Store
   Connect, compare installs by version first.
5. **Remove it** after the sunset date, in a release whose notes say so. Delete the
   `deprecation.py` entry in the same PR.

Each step is its own release. Steps 1 to 3 must reach production before step 4.

## Forcing old apps to update

The backend decides which app versions it still serves, per platform
(`apps.appversions`):

| Setting | Effect |
| --- | --- |
| `minimum_version` | Older apps get **426 Upgrade Required** on every call, with `{"code": "upgrade_required", "details": {"minimum_version", "store_url"}}`, and show a blocking update screen. |
| `latest_version` | Older apps show an "update available" card, which the person can dismiss once per version. |

How the app takes part:
- It sends `X-Client-Platform: android|ios` and `X-Client-Version: 1.4.2` on every call.
- On launch it calls `GET /api/v1/app/version/?platform=…&version=…`, which always
  answers, so a blocked app can still show why.
- Any 426 `upgrade_required` switches it to the blocking screen at once, even if the
  launch check failed. The web console sends no version headers, so it's never
  blocked.

To change the minimum or latest version, ops staff (the `appversions.set_app_version`
permission) use the back office (**App versions**) or
`PUT /api/v1/admin/app-versions/<platform>/`. Either way a reason is required, the
change is audited (`appversions.changed`), and it reaches every instance within 30
seconds. Until someone sets a policy, the defaults force nothing (`0.0.0`). The
defaults come from `APP_MIN_VERSION_*` and `APP_LATEST_VERSION_*` in the environment.

Raise `latest_version` once a release has reached 100% on both stores. Raise
`minimum_version` only for a breaking change, and only after the version that handles
it has been fully rolled out on both stores for at least a week. Otherwise people get
told to install an update the store won't give them yet.

### Breaking change emergency

If a security fix can't wait 90 days, the minimum version can be raised at once.
That trades the notice period for blocking everyone below it. Say so in the release
notes and the incident record.

## Deprecation schedule

Nothing in `v1` is deprecated yet. These changes are planned. Each one starts the
process above when its replacement ships. The dates are filled in at that point, and
`deprecation.py` gets its entry.

| What | Why | Replacement | Deprecated | Earliest sunset | Removal needs app ≥ |
| --- | --- | --- | --- | --- | --- |
| `POST /api/v1/notifications/devices/` and `…/devices/remove/` with an FCM registration `token` | firebase_messaging 17 deprecates registration tokens in favour of installation IDs (`mobile/lib/src/notifications/push.dart`) | The same endpoints taking an installation id (an additive field first) | when the replacement ships | +90 days | the first version that sends installation ids |
| An unpaginated `GET /api/v1/applications/mine/` | It grows with every application. The app already accepts a paginated body (`applications_repository.dart`) | A paginated response (`results`, `next`) | when the app version that reads pages is at 100% | +90 days | 1.0.0 (already reads both) |

When something is removed, move its row to "Removed" below with the release that
removed it.

### Removed

None yet.
