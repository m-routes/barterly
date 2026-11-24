# OTP provider outage (and notifications backing up)

**You'll notice it from:**
- **Alerts:** a spike of 4xx/5xx on `/api/v1/auth/exchange/`, "Notifications
  dead-lettered", "Backlog: notifications stuck", or "Background task queue backing
  up".
- **Support:** people saying the code never arrived.

**Severity:** SEV2. People who are already signed in keep working: refresh tokens last
30 days. Only new sign-ins and new devices are blocked.

Sign-in codes are sent by **Firebase Authentication** (phone). Notifications go through
FCM (push) and email, and SMS or WhatsApp where configured. Both paths are covered
here because they fail together when Google or a telecom route has trouble.

## First five minutes

1. **Is it Firebase or us?**
   - Firebase: <https://status.firebase.google.com> (Authentication, Cloud Messaging).
   - Us: if `/api/v1/auth/exchange/` returns 5xx, it's our side; see
     [bad-deploy-rollback](bad-deploy-rollback.md) and
     [database-outage](database-outage.md).
2. **Is it one telecom or region?** Firebase console → Authentication → Usage shows
   SMS sent vs verified. Codes that are sent but never verified point to delivery.
3. **Is it a quota or abuse block?** `auth/quota-exceeded` or `too-many-requests`
   errors in Sentry mean the SMS quota or Firebase's abuse protection. Check the
   Firebase usage page for a spike, which could be SMS pumping fraud.

## Fix

- **Firebase down:** there's no second OTP provider; that's a known single point of
  failure.
  - Post a notice: "New sign-ins are delayed. If you're signed in, you're fine."
  - Don't ask anyone to reinstall: that signs them out.
  - Watch the Firebase status page.
- **Quota:** raise it in Google Cloud (Identity Platform quotas) once you're sure it's
  real traffic.
- **SMS pumping:** in Firebase → Authentication → Settings → SMS region policy, allow
  India only (it should already be), and turn on App Check enforcement if it isn't.
- **Notifications stuck:** the queue retries with back-off for 2 hours. Dead letters can
  be resent from the back office (Notifications → Dead letters) once the provider
  recovers. FCM tokens it reports as invalid are dropped automatically.

## Afterwards

If the outage lasted more than an hour, consider a second OTP route behind the same
`TokenVerifier` interface (WhatsApp OTP, or a second SMS provider). Note this in the
review.
