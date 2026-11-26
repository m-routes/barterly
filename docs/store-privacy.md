# Store privacy answers: Play Data safety and App Store privacy labels

These answers come from the code, not from intentions. The machine-readable source is
`mobile/store/data_safety.json`. It lists every data type with the code that sends
it, and every SDK in `pubspec.yaml` with what it touches. The iOS privacy manifest
(`mobile/ios/Runner/PrivacyInfo.xcprivacy`) declares the same Apple types.
`test/store/data_safety_test.dart` fails when:
- a dependency is added and not described;
- the manifest and the JSON disagree.

**When you change what the app sends** (a new field in a repository's request body, a
new SDK, a new permission), update `data_safety.json`, the manifest and this page in
the same PR. Then update the store consoles before that build is released.

Reviewed against the code on 2026-11-24, with `feat/privacy` (PR #33) merged in. Privacy
adds consent records, account export and deletion, and the public legal pages
(`/legal/privacy`, `/account/privacy`) that the store forms link to.

## Google Play: Data safety form

**Overview questions**

| Question | Answer | Why |
| --- | --- | --- |
| Does your app collect or share any of the required user data types? | Yes | See below |
| Is all of the user data collected by your app encrypted in transit? | Yes | HTTPS only: `usesCleartextTraffic="false"`, HSTS, TLS 1.2+ at the edge |
| Do you provide a way for users to request that their data is deleted? | Yes | In-app and web deletion from `feat/privacy`. Give the web URL `https://barterly.in/account/privacy` |
| Shared with third parties? | No | Firebase (Google), Sentry, Razorpay/RazorpayX and the KYC provider act as service providers on our behalf. A host seeing an application is a transfer the person starts, which Play exempts. |

**Data types.** All are *collected*, *not shared*, and *not processed ephemerally*.

| Play category → type | Required or optional | Purposes | What, from where |
| --- | --- | --- | --- |
| Personal info → Name | Required | App functionality, Account management | Display name; emergency contact's name (`talent_profile.dart`) |
| Personal info → Phone number | Required | App functionality, Account management | Sign-in (Firebase Auth); emergency contact's phone |
| Personal info → User IDs | Required | App functionality, Account management | Account id (tags crash reports); Instagram handle (optional) |
| Personal info → Other info | Required | App functionality, Account management, Fraud prevention/security/compliance | Date of birth, bio, home city (typed), languages, skills, talent type; the ID check's result |
| Financial info → Other financial info | Optional | App functionality | UPI ID or bank account and IFSC for payouts (`wallet_repository.dart`) |
| Location → Precise location | Optional | App functionality | One reading when a check-in pass is opened and the person agrees (`attendance/location.dart`) |
| Messages → Other in-app messages | Optional | App functionality | Chat with hosts |
| Photos and videos → Photos, Videos | Optional | App functionality | Portfolio and deliverable files, chat photos |
| Files and docs → Files and docs | Optional | App functionality | PDFs attached to applications |
| App activity → Other user-generated content | Optional | App functionality | Notes, reviews, hours notes, deliverable links and stats |
| App activity → In-app search history | Optional | App functionality | Saved gig searches |
| App info and performance → Crash logs | Required | App functionality, Analytics | Sentry, only in builds with a DSN |
| App info and performance → Diagnostics | Required | App functionality, Fraud prevention/security/compliance | Device model and OS in crash reports; rooted/jailbroken signals |
| Device or other IDs → Device or other IDs | Optional | App functionality | Push token, only after notifications are allowed |

**Not collected:**
- email address;
- approximate (device) location;
- contacts, calendar, audio files, health and fitness;
- web browsing, purchase history;
- app interactions or analytics events: there is no analytics SDK.

The KYC provider captures the ID document and selfie on its own hosted page, in the
system browser. The app never handles those images. Confirm with the provider's DPA
that it processes them as our service provider, as described here.

## App Store: App Privacy ("nutrition labels")

In App Store Connect, under App Privacy:
- "Do you or your third-party partners collect data from this app?" **Yes**.
- For every type below: **linked to the user**, **not used for tracking**.
- Purpose for every type: **App Functionality**. Apple counts crash reports and
  diagnostics under this purpose ("minimize app crashes").

| Apple category | Data type |
| --- | --- |
| Contact Info | Name; Phone Number; Other User Contact Info (Instagram handle, emergency contact) |
| Location | Precise Location |
| User Content | Photos or Videos; Emails or Text Messages (in-app chat); Other User Content (notes, reviews, PDFs) |
| Financial Info | Other Financial Info (payout account) |
| Search History | Search History (saved searches) |
| Identifiers | User ID; Device ID (push token) |
| Diagnostics | Crash Data; Other Diagnostic Data |
| Other Data | Other Data Types (date of birth, bio, skills, languages, home city) |

**Tracking:** none. No IDFA and no App Tracking Transparency prompt, and
`NSPrivacyTracking` is false.

**Open question for legal:** if the KYC provider does face matching on the selfie,
Apple may expect *Sensitive Info* to be declared even though the capture happens on
the provider's page. Decide before submission.

## Permission prompts and their reasons

The app explains each runtime permission in its own sheet first
(`lib/src/platform/permission_rationale.dart`), and only then asks the system.
"Not now" never blocks anything.

| Permission | When it's asked | In-app explanation (summary) | iOS purpose string (`Info.plist`) |
| --- | --- | --- | --- |
| Camera | The first time the person taps "Take a photo" or "Record a video" | Photos/videos of your work for applications and deliverables; only when you tap | `NSCameraUsageDescription`, `NSMicrophoneUsageDescription` (video sound) |
| Location (while in use) | Opening a check-in pass, once per booking | The host sees how far you are; read once, never in the background; optional | `NSLocationWhenInUseUsageDescription` |
| Notifications | After sign-in. If declined, asked again after 30 days at the earliest | Replies, offers, confirmations, check-in reminders; no marketing | (system text; Android 13+ declares `POST_NOTIFICATIONS`) |
| Photos | No runtime permission: Android's photo picker and iOS's PHPicker share only what's picked | (explained by the picker itself) | `NSPhotoLibraryUsageDescription` (needed by the plugin) |

There is no background location, no contacts access, no calendar read access
(`add_2_calendar` opens the system's own editor) and no microphone use outside
video recording.

## Third parties the app talks to directly

| Host | Why | What it receives |
| --- | --- | --- |
| `api.barterly.in`, `media.barterly.in` | The app's backend and media CDN | Everything above |
| `storage.googleapis.com` | Uploads (signed URLs) | The files the person picks |
| Firebase Auth / FCM (Google) | Sign-in by SMS code; push delivery | Phone number; push token |
| Sentry (`*.ingest.sentry.io`) | Crash reports | Crash data, device model/OS, account id |
| `tile.openstreetmap.org` (or `MAP_TILE_URL`) | Map tiles | IP address and the map area viewed |
| `fonts.gstatic.com` | Inter and Space Grotesk fonts (`google_fonts`, first launch) | IP address |
| The KYC provider's page (system browser) | ID check | ID document and selfie, on their page |

Follow-up worth doing: bundle the two fonts and set
`GoogleFonts.config.allowRuntimeFetching = false`. That removes the Google Fonts
request, and the fonts then work offline from the first launch.
