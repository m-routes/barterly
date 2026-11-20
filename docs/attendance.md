# Attendance: check-in, hours, check-out

`apps/attendance` (backend), the console's **Arrivals** screen (`web/…/console/arrivals`,
an installable PWA), and the talent app's **check-in pass** and **hours** screens
(`mobile/lib/src/attendance`).

## Check-in passes

The talent's pass has two forms:
- **QR code.** The QR holds a token, `BRT1.<payload>.<signature>` (base64url), signed by
  the server with Ed25519. The payload is `{v, kid, b: booking, t: talent, p: pass,
  nbf, exp}`.
- **Six-digit code.** If scanning fails, the talent reads out a code: RFC 6238 TOTP
  (HMAC-SHA1, a 5-minute step, the previous step also accepted) from the pass's
  `code_secret`.

The server, the console and the app all compute the same codes. Their tests share
fixtures to prove it, and the console verifies a token the backend signed.

Validity:
- A pass lasts `ATTENDANCE_PASS_HOURS` (48) inside the booking's check-in window, which
  runs from the day before the stay to its last day.
- Asking again returns the same pass until it has under two hours left.
- The app keeps it on the phone, so it shows without signal.

Location:
- When the talent opens the pass, the app sends their location if they allow it. It's
  stored on the pass (with accuracy and time), never required.

Keys:
- The private key is `ATTENDANCE_SIGNING_KEY`: 32 random bytes, base64, kept in Secret
  Manager as `attendance-signing-key-<env>`. `infra/scripts/set-secrets.sh` generates
  it.
- Deployed settings refuse to start without it. Local runs and tests derive one from
  `SECRET_KEY`.
- To rotate: add the current public key (from `GET /api/v1/attendance/keys/`, base64url
  converted to base64) to `ATTENDANCE_PREVIOUS_PUBLIC_KEYS`, then run
  `ROTATE=1 infra/scripts/set-secrets.sh <env>`, deploy, and remove the old key after a
  day.

## The host's Arrivals screen (offline)

`GET /api/v1/attendance/arrivals/?date=` returns:
- the public keys, the code step and the allowed clock skew;
- every confirmed booking in its check-in window that day, with what's needed to check
  it offline (the pass id, the code secret, the pass window), why check-in would be
  refused now (`problem`), and when a no-show may be marked;
- everyone in house, for check-out and hours.

The console keeps the response in IndexedDB. A service worker (`public/sw.js`) caches
the page and its build files, so it opens with no network once it's been visited. API
calls and sign-in are never cached.

**Checking someone in, offline:**
- **Scan:** the camera reads the QR, using BarcodeDetector where the browser has it and
  jsQR otherwise. The console verifies the signature (`@noble/curves`, strict RFC 8032)
  and the window against the cached keys, and matches the booking.
- **Code:** the console computes the expected code from the cached secret
  (`@noble/hashes`).
- **By hand:** with a reason.

Each check-in is queued in IndexedDB with a client id and the time it happened.

**Syncing:** `POST /api/v1/attendance/sync/` runs when the screen opens, when the device
comes back online, every 30 seconds, and on "Sync now". Each event is applied on its
own and comes back `applied`, `duplicate` or `refused` (with why). Refused ones stay on
screen. The server checks again:
- the signature or code, at the scan time;
- that the scan time isn't in the future (allowing for clock skew) or more than
  `ATTENDANCE_SYNC_MAX_AGE_HOURS` (72) old;
- the booking's own rules: check-in window, agreement in force, stipend funded for paid
  and hybrid gigs.

A repeated client id, or a second device scanning the same talent, records one
check-in. The booking's check-in time is the scan time.

## Soft geofence

Check-in records the talent's distance from the property: from the pass's location to
the property's pin, and how old that location was. Over
`ATTENDANCE_GEOFENCE_FLAG_METERS` (1 km) the check-in is flagged (`far`) but never
blocked. Ops and trust review flagged check-ins:
- `GET /api/v1/admin/attendance/flagged/`
- `POST /api/v1/admin/attendance/<id>/review/` with a note (audited)

## Check-out and no-shows

- **Check-out** (`POST /bookings/<id>/attendance/check-out/`, host): moves the booking
  through delivering to completed, which ends the stay and feeds reviews and the
  reliability score as before.
- **No-show** (`POST /bookings/<id>/attendance/no-show/`, host, with a reason): allowed
  only `ATTENDANCE_NO_SHOW_GRACE_HOURS` (18, so 6 pm) into the first day. This is the
  lifecycle guard on confirmed → no_show. It counts against the talent's reliability
  score, and they can dispute it.
- A booking checked in some other way (the generic status endpoint, or an admin) still
  gets a check-in record (`other`).

## Volunteer hours

- The talent logs each day's hours (`POST /bookings/<id>/hours/`), one log per day.
  Logging again replaces it until the host confirms.
- The limits come from the agreement's terms:
  - **weekly cap:** hours_per_day × days_per_week, Monday to Sunday;
  - **day-off rule:** at most days_per_week working days a week.
- Both are enforced: a log that breaks them is refused, saying why.
- `POST /bookings/<id>/hours/check/` previews a log without saving it, and warns about a
  day over the agreed hours, a week at 90% of its cap, or the last working day the week
  allows. The app checks as the talent changes the hours, and disables Save when the log
  would be refused.
- The host confirms or disputes each day (`POST /hours/<id>/review/`). A dispute needs a
  note and notifies the talent, who can correct it. Confirmed days are locked.
- Hours can be logged from check-in until a week after the stay ends.

## Settings

| Setting | Default | |
|---|---|---|
| `ATTENDANCE_SIGNING_KEY` | (required when deployed) | Secret Manager |
| `ATTENDANCE_PREVIOUS_PUBLIC_KEYS` | | For rotation |
| `ATTENDANCE_PASS_HOURS` | 48 | |
| `ATTENDANCE_GEOFENCE_FLAG_METERS` | 1000 | |
| `ATTENDANCE_SYNC_MAX_AGE_HOURS` | 72 | |
| `ATTENDANCE_CLOCK_SKEW_SECONDS` | 120 | |
| `ATTENDANCE_NO_SHOW_GRACE_HOURS` | 18 | Hours into the first day |
