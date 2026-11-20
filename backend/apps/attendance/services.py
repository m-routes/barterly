"""Check-in passes, check-in (QR, code or by hand, live or synced from an offline
queue), check-out and no-shows.

Check-in itself is the booking's confirmed → checked_in move (bookings.services
.transition), so its rules still apply: the check-in window, the agreement in force and,
for paid and hybrid gigs, the stipend funded. Attendance adds how it was confirmed, when
the host scanned it (`checked_in_at`, which can be before the sync), and the talent's
distance from the property, flagged for review when it's large but never blocking.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.attendance import signing
from apps.attendance.models import AttendancePass, CheckIn, CheckInMethod, FlagReason
from apps.bookings import lifecycle
from apps.bookings.lifecycle import Actor, BookingStatus
from apps.bookings.models import Booking
from apps.bookings.services import BookingRefused, transition
from apps.common.services.audit import log_action
from apps.geo.distance import haversine_m

B = BookingStatus
IN_HOUSE = (B.CHECKED_IN, B.DELIVERING)


class AttendanceError(Exception):
    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.message = message
        self.status = status


# ---------- Times ----------


def _local(day: date, at: time = time.min) -> datetime:
    return timezone.make_aware(datetime.combine(day, at))


def check_in_window(booking: Booking) -> tuple[datetime, datetime]:
    """From the start of the day before the stay to the end of its last day (India)."""
    return (
        _local(booking.start_date - lifecycle.CHECK_IN_EARLY),
        _local(booking.end_date + timedelta(days=1)),
    )


def no_show_from(booking: Booking) -> datetime:
    return _local(booking.start_date) + timedelta(hours=settings.ATTENDANCE_NO_SHOW_GRACE_HOURS)


# ---------- Passes ----------


def issue_pass(booking: Booking, *, location: dict | None = None, now=None) -> AttendancePass:
    """The booking's current pass, or a new one. A pass lasts ATTENDANCE_PASS_HOURS
    inside the check-in window; one with under two hours left is replaced."""
    now = now or timezone.now()
    opens, closes = check_in_window(booking)
    if now >= closes:
        raise AttendanceError("This stay has ended.")
    start = max(now, opens)
    current = (
        AttendancePass.objects.filter(booking=booking, valid_until__gt=start + timedelta(hours=2))
        .order_by("-valid_until")
        .first()
    )
    if current is None:
        current = AttendancePass.objects.create(
            booking=booking,
            talent_id=booking.talent_id,
            issued_at=now,
            valid_from=start,
            valid_until=min(start + timedelta(hours=settings.ATTENDANCE_PASS_HOURS), closes),
            code_secret=signing.new_code_secret(),
        )
    if location:
        current.latitude, current.longitude = location["latitude"], location["longitude"]
        current.accuracy_m, current.located_at = location.get("accuracy_m"), now
        current.save(update_fields=["latitude", "longitude", "accuracy_m", "located_at"])
    return current


def token_for(attendance_pass: AttendancePass) -> str:
    return signing.sign(
        booking_id=attendance_pass.booking_id,
        talent_id=attendance_pass.talent_id,
        pass_id=attendance_pass.pk,
        not_before=attendance_pass.valid_from,
        expires=attendance_pass.valid_until,
    )


def talent_pass(booking_id, *, talent, location: dict | None = None, request=None, now=None):
    booking = Booking.objects.select_related("gig").get(pk=booking_id, talent=talent)
    if booking.status != B.CONFIRMED:
        raise AttendanceError(
            "You're already checked in."
            if booking.status in IN_HOUSE
            else "A pass is for a confirmed booking that hasn't started."
        )
    return issue_pass(booking, location=location, now=now)


# ---------- The host's day ----------


def readiness(booking: Booking, now) -> str:
    """Why this booking can't check in now (empty: it can)."""
    try:
        lifecycle.check(
            booking.status,
            B.CHECKED_IN,
            lifecycle.Context(subject=booking, actor=Actor.VENDOR, now=now),
        )
    except (lifecycle.InvalidTransition, lifecycle.GuardFailed) as exc:
        return str(exc)
    return ""


@dataclass
class Arrival:
    booking: Booking
    attendance_pass: AttendancePass
    problem: str


def arrivals(vendor, day: date, now=None) -> tuple[list[Arrival], list[Booking]]:
    """Who's expected (confirmed, in their check-in window on `day`) and who's in house.
    Each arrival has a pass, so the console can check its QR or code offline."""
    now = now or timezone.now()
    expected = (
        Booking.objects.filter(
            vendor=vendor,
            status=B.CONFIRMED,
            start_date__lte=day + lifecycle.CHECK_IN_EARLY,
            end_date__gte=day,
        )
        .select_related("gig__property", "talent__talent_profile", "agreement__current_version")
        .order_by("start_date")
    )
    found = [Arrival(b, issue_pass(b, now=now), readiness(b, now)) for b in expected]
    in_house = (
        Booking.objects.filter(vendor=vendor, status__in=IN_HOUSE)
        .select_related("gig", "talent__talent_profile")
        .order_by("end_date")
    )
    return found, list(in_house)


# ---------- Check-in ----------


@dataclass
class Outcome:
    status: str  # "applied" or "duplicate"
    check_in: CheckIn


def _distance(booking: Booking, attendance_pass: AttendancePass | None, at: datetime):
    prop = booking.gig.property
    if (
        attendance_pass is None
        or attendance_pass.latitude is None
        or prop is None
        or prop.latitude is None
    ):
        return None, None
    metres = haversine_m(
        float(attendance_pass.latitude),
        float(attendance_pass.longitude),
        float(prop.latitude),
        float(prop.longitude),
    )
    age = max(0, int((at - attendance_pass.located_at).total_seconds() // 60))
    return round(metres), age


def _pass_for(booking, method, *, token, code, scanned_at) -> AttendancePass | None:
    skew = timedelta(seconds=settings.ATTENDANCE_CLOCK_SKEW_SECONDS)
    if method == CheckInMethod.QR:
        try:
            payload = signing.verify(token or "")
        except signing.TokenError as exc:
            raise AttendanceError(str(exc), 400) from exc
        if payload.get("b") != str(booking.pk) or payload.get("t") != str(booking.talent_id):
            raise AttendanceError("This pass is for a different booking.", 400)
        stamp = scanned_at.timestamp()
        if (
            not payload["nbf"] - skew.total_seconds()
            <= stamp
            <= payload["exp"] + skew.total_seconds()
        ):
            raise AttendanceError(
                "This pass had expired when it was scanned. Ask for a fresh one.", 400
            )
        found = AttendancePass.objects.filter(pk=payload.get("p"), booking=booking).first()
        if found is None:
            raise AttendanceError("This pass isn't one we issued.", 400)
        return found
    if method == CheckInMethod.CODE:
        passes = AttendancePass.objects.filter(
            booking=booking, valid_from__lte=scanned_at + skew, valid_until__gte=scanned_at - skew
        )
        for candidate in passes:
            if signing.code_matches(candidate.code_secret, code or "", scanned_at):
                return candidate
        raise AttendanceError("That code isn't right, or it has expired. Ask for the new one.", 400)
    # By hand: no proof, but the latest pass may still say where the talent was.
    return AttendancePass.objects.filter(booking=booking, located_at__isnull=False).first()


def check_in(
    *,
    vendor,
    booking_id=None,
    method: str,
    token: str = "",
    code: str = "",
    reason: str = "",
    scanned_at: datetime | None = None,
    client_id=None,
    request=None,
    now=None,
) -> Outcome:
    now = now or timezone.now()
    scanned_at = scanned_at or now
    if client_id and (done := CheckIn.objects.filter(client_id=client_id).first()):
        return Outcome("duplicate", done)
    if method not in (CheckInMethod.QR, CheckInMethod.CODE, CheckInMethod.MANUAL):
        raise AttendanceError("Check in by QR, code or by hand.", 400)
    if scanned_at > now + timedelta(seconds=settings.ATTENDANCE_CLOCK_SKEW_SECONDS):
        raise AttendanceError("The check-in time is in the future: check the device's clock.", 400)
    if now - scanned_at > timedelta(hours=settings.ATTENDANCE_SYNC_MAX_AGE_HOURS):
        raise AttendanceError("This check-in waited too long to sync. Check the talent in again.")
    if method == CheckInMethod.MANUAL and len(reason.strip()) < 3:
        raise AttendanceError("Say why you're confirming by hand.", 400)
    if booking_id is None and method == CheckInMethod.QR:
        try:
            booking_id = signing.verify(token or "").get("b")
        except signing.TokenError as exc:
            raise AttendanceError(str(exc), 400) from exc
    booking = (
        Booking.objects.select_related("gig__property").filter(pk=booking_id, vendor=vendor).first()
    )
    if booking is None:
        raise AttendanceError("This booking isn't one of yours.", 404)
    existing = CheckIn.objects.filter(booking=booking).first()
    if existing and booking.status != B.CONFIRMED:
        return Outcome("duplicate", existing)  # checked in already (another device, say)
    attendance_pass = _pass_for(booking, method, token=token, code=code, scanned_at=scanned_at)
    distance, age = _distance(booking, attendance_pass, scanned_at)
    far = distance is not None and distance > settings.ATTENDANCE_GEOFENCE_FLAG_METERS
    try:
        with transaction.atomic():
            record = CheckIn.objects.create(
                booking=booking,
                method=method,
                attendance_pass=attendance_pass,
                client_id=client_id,
                checked_in_at=scanned_at,
                recorded_at=now,
                recorded_by=vendor,
                reason=reason.strip()[:300],
                distance_m=distance,
                location_age_minutes=age,
                flag=FlagReason.FAR if far else FlagReason.NONE,
            )
            transition(
                booking.pk,
                B.CHECKED_IN,
                actor=Actor.VENDOR,
                user=vendor,
                reason=reason.strip() if method == CheckInMethod.MANUAL else "",
                metadata={"method": method, "check_in_id": str(record.pk), "distance_m": distance},
                request=request,
                now=scanned_at,
            )
            log_action(
                actor=vendor,
                action="attendance.checked_in",
                obj=record,
                after={
                    "method": method,
                    "distance_m": distance,
                    "flag": record.flag,
                    "checked_in_at": scanned_at.isoformat(),
                    "synced_at": now.isoformat(),
                },
                request=request,
            )
    except BookingRefused as exc:
        raise AttendanceError(str(exc)) from exc
    except IntegrityError:
        # The same client id, or another device, got there a moment ago.
        done = CheckIn.objects.filter(booking=booking).first()
        if done is None:
            raise
        return Outcome("duplicate", done)
    return Outcome("applied", record)


def on_checked_in(event) -> None:
    """A check-in made by moving the booking directly (not through attendance) still
    gets its record."""
    booking_id = event.payload.get("booking_id")
    if booking_id and not CheckIn.objects.filter(booking_id=booking_id).exists():
        CheckIn.objects.create(
            booking_id=booking_id,
            method=CheckInMethod.OTHER,
            checked_in_at=event.occurred_at,
            recorded_at=event.occurred_at,
        )


def sync(vendor, events: list[dict], *, request=None, now=None) -> list[dict]:
    """Apply a device's queued check-ins, each on its own; return a result for each."""
    results = []
    for item in events:
        try:
            outcome = check_in(vendor=vendor, request=request, now=now, **item)
            results.append(
                {
                    "client_id": item["client_id"],
                    "status": outcome.status,
                    "message": "",
                    "booking_id": outcome.check_in.booking_id,
                }
            )
        except AttendanceError as exc:
            results.append(
                {
                    "client_id": item["client_id"],
                    "status": "refused",
                    "message": exc.message,
                    "booking_id": item.get("booking_id"),
                }
            )
    return results


# ---------- Check-out and no-shows ----------


def check_out(booking_id, *, vendor, request=None, now=None) -> CheckIn:
    """Ends the stay: the booking is completed."""
    now = now or timezone.now()
    booking = Booking.objects.filter(pk=booking_id, vendor=vendor).first()
    if booking is None:
        raise AttendanceError("This booking isn't one of yours.", 404)
    if booking.status not in IN_HOUSE:
        raise AttendanceError("Only someone checked in can be checked out.")
    try:
        with transaction.atomic():
            if booking.status == B.CHECKED_IN:
                transition(
                    booking.pk,
                    B.DELIVERING,
                    actor=Actor.VENDOR,
                    user=vendor,
                    request=request,
                    now=now,
                )
            transition(
                booking.pk,
                B.COMPLETED,
                actor=Actor.VENDOR,
                user=vendor,
                reason="Checked out",
                request=request,
                now=now,
            )
            record = CheckIn.objects.filter(booking=booking).first() or CheckIn.objects.create(
                booking=booking,
                method=CheckInMethod.OTHER,
                checked_in_at=booking.checked_in_at or now,
                recorded_at=now,
            )
            record.checked_out_at, record.checked_out_by = now, vendor
            record.save(update_fields=["checked_out_at", "checked_out_by"])
            log_action(
                actor=vendor,
                action="attendance.checked_out",
                obj=record,
                after={"checked_out_at": now.isoformat()},
                request=request,
            )
    except BookingRefused as exc:
        raise AttendanceError(str(exc)) from exc
    return record


def no_show(booking_id, *, vendor, reason: str, request=None, now=None) -> Booking:
    """The talent never came. Allowed from ATTENDANCE_NO_SHOW_GRACE_HOURS into the first
    day (the lifecycle guard checks it); counts against their reliability score."""
    now = now or timezone.now()
    if not Booking.objects.filter(pk=booking_id, vendor=vendor).exists():
        raise AttendanceError("This booking isn't one of yours.", 404)
    try:
        return transition(
            booking_id,
            B.NO_SHOW,
            actor=Actor.VENDOR,
            user=vendor,
            reason=reason,
            request=request,
            now=now,
        )
    except BookingRefused as exc:
        raise AttendanceError(str(exc)) from exc


def review_flag(check_in_id, *, admin, note: str, now=None) -> CheckIn:
    record = CheckIn.objects.get(pk=check_in_id)
    if not record.flag:
        raise AttendanceError("This check-in isn't flagged.")
    if not note.strip():
        raise AttendanceError("Add a note.", 400)
    record.reviewed_at, record.reviewed_by = now or timezone.now(), admin
    record.review_note = note.strip()[:300]
    record.save(update_fields=["reviewed_at", "reviewed_by", "review_note"])
    log_action(
        actor=admin,
        action="attendance.flag_reviewed",
        obj=record,
        after={"note": record.review_note, "distance_m": record.distance_m},
    )
    return record
