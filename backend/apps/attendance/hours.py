"""Volunteer hour logs: the talent logs each day's hours, the host confirms or disputes.

The agreement's terms set the limits:
- the weekly cap: hours_per_day x days_per_week (a week is Monday to Sunday, India);
- the day-off rule: at most days_per_week working days a week (so at least one off).

Both are enforced: a log that would break either is refused, saying why. Before that,
check() warns: a day over the agreed hours_per_day, a week close to its cap, or the last
working day the week allows.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone

from apps.attendance.models import HourLog, HourStatus
from apps.bookings.lifecycle import BookingStatus
from apps.bookings.models import Booking
from apps.common.events import DomainEvent, publish
from apps.common.services.audit import log_action

LOGGABLE = (BookingStatus.CHECKED_IN, BookingStatus.DELIVERING, BookingStatus.COMPLETED)
LATE_LOGGING_DAYS = 7  # after the stay ends, hours can still be logged for a week
NEAR_CAP = 0.9


class HoursError(Exception):
    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.message = message
        self.status = status


@dataclass
class Limits:
    hours_per_day: int
    days_per_week: int

    @property
    def weekly_cap_minutes(self) -> int:
        return self.hours_per_day * self.days_per_week * 60


@dataclass
class Check:
    allowed: bool
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    week_start: date | None = None
    week_minutes: int = 0  # including this log
    week_days: int = 0
    weekly_cap_minutes: int = 0
    days_per_week: int = 0


def week_of(day: date) -> tuple[date, date]:
    start = day - timedelta(days=day.weekday())
    return start, start + timedelta(days=6)


def limits_for(booking: Booking) -> Limits:
    agreement = getattr(booking, "agreement", None)
    version = agreement and agreement.current_version
    terms = version.terms if version else {}
    gig = booking.gig
    return Limits(
        int(terms.get("hours_per_day") or gig.hours_per_day or 6),
        int(terms.get("days_per_week") or gig.days_per_week or 6),
    )


def _hours(minutes: int) -> str:
    h, m = divmod(minutes, 60)
    return f"{h} h {m} min" if m else f"{h} h"


def check(booking: Booking, day: date, minutes: int) -> Check:
    limits = limits_for(booking)
    start, end = week_of(day)
    others = HourLog.objects.filter(booking=booking, day__range=(start, end)).exclude(day=day)
    week_minutes = sum(o.minutes for o in others) + minutes
    week_days = len({o.day for o in others}) + 1
    result = Check(
        True,
        week_start=start,
        week_minutes=week_minutes,
        week_days=week_days,
        weekly_cap_minutes=limits.weekly_cap_minutes,
        days_per_week=limits.days_per_week,
    )
    cap = limits.weekly_cap_minutes
    if week_minutes > cap:
        result.problems.append(
            f"That makes {_hours(week_minutes)} this week; the agreed most is {_hours(cap)}."
        )
    if week_days > limits.days_per_week:
        off = 7 - limits.days_per_week
        result.problems.append(
            f"That would be {week_days} working days this week. The agreement keeps "
            f"{off} day{'s' if off != 1 else ''} off a week."
        )
    if minutes > limits.hours_per_day * 60:
        result.warnings.append(
            f"That's more than the {limits.hours_per_day} hours a day you agreed."
        )
    if not result.problems:
        if week_minutes >= cap * NEAR_CAP:
            result.warnings.append(
                f"That brings this week to {_hours(week_minutes)} of {_hours(cap)}."
            )
        if week_days == limits.days_per_week and day < end:
            result.warnings.append("After this, take the rest of the week off.")
    result.allowed = not result.problems
    return result


def _loggable(booking: Booking, day: date, today: date) -> None:
    if booking.status not in LOGGABLE:
        raise HoursError("Log hours once you've checked in.")
    if not booking.start_date <= day <= booking.end_date:
        raise HoursError("That day isn't part of the stay.", 400)
    if day > today:
        raise HoursError("You can't log hours for a day that hasn't happened.", 400)
    if today > booking.end_date + timedelta(days=LATE_LOGGING_DAYS):
        raise HoursError("It's too late to log hours for this stay.")


def preview(booking_id, *, talent, day: date, minutes: int, now=None) -> Check:
    booking = Booking.objects.select_related("gig", "agreement__current_version").get(
        pk=booking_id, talent=talent
    )
    _loggable(booking, day, timezone.localdate(now or timezone.now()))
    return check(booking, day, minutes)


def log(
    booking_id, *, talent, day: date, minutes: int, note: str = "", request=None, now=None
) -> tuple[HourLog, Check]:
    now = now or timezone.now()
    with transaction.atomic():
        booking = (
            Booking.objects.select_for_update(of=("self",))
            .select_related("gig", "agreement__current_version")
            .get(pk=booking_id, talent=talent)
        )
        _loggable(booking, day, timezone.localdate(now))
        existing = HourLog.objects.filter(booking=booking, day=day).first()
        if existing and existing.status == HourStatus.CONFIRMED:
            raise HoursError("Your host has confirmed this day; it can't change now.")
        result = check(booking, day, minutes)
        if not result.allowed:
            raise HoursError(" ".join(result.problems))
        entry = existing or HourLog(booking=booking, talent=talent, day=day, created_at=now)
        before = {"minutes": existing.minutes, "status": existing.status} if existing else {}
        entry.minutes, entry.note = minutes, note.strip()[:300]
        entry.status, entry.vendor_note, entry.reviewed_at = HourStatus.PENDING, "", None
        entry.save()
        log_action(
            actor=talent,
            action="attendance.hours_logged",
            obj=entry,
            before=before,
            after={"day": str(day), "minutes": minutes},
            request=request,
        )
    return entry, result


def review(log_id, *, vendor, confirm: bool, note: str = "", request=None, now=None) -> HourLog:
    now = now or timezone.now()
    if not confirm and not note.strip():
        raise HoursError("Say what's wrong with these hours.", 400)
    with transaction.atomic():
        entry = (
            HourLog.objects.select_for_update(of=("self",))
            .select_related("booking__gig")
            .get(pk=log_id, booking__vendor=vendor)
        )
        if entry.status != HourStatus.PENDING:
            raise HoursError("You've already answered this one.")
        entry.status = HourStatus.CONFIRMED if confirm else HourStatus.DISPUTED
        entry.vendor_note, entry.reviewed_at = note.strip()[:300], now
        entry.save(update_fields=["status", "vendor_note", "reviewed_at", "updated_at"])
        log_action(
            actor=vendor,
            action=f"attendance.hours_{entry.status}",
            obj=entry,
            after={"day": str(entry.day), "minutes": entry.minutes, "note": entry.vendor_note},
            request=request,
        )
        if not confirm:
            booking = entry.booking
            publish(
                DomainEvent(
                    "attendance.hours_disputed",
                    {
                        "booking_id": str(booking.pk),
                        "talent_id": str(booking.talent_id),
                        "vendor_id": str(booking.vendor_id),
                        "gig_title": booking.gig.title,
                        "day": entry.day.strftime("%d %b"),
                        "note": entry.vendor_note,
                        "dedup_key": f"hours_disputed:{entry.pk}:{now.isoformat()}",
                        "notify": ["talent"],
                    },
                    occurred_at=now,
                )
            )
    return entry


def week_summary(booking: Booking, week_start: date) -> dict:
    limits = limits_for(booking)
    start, end = week_of(week_start)
    logs = list(HourLog.objects.filter(booking=booking, day__range=(start, end)).order_by("day"))
    return {
        "week_start": start,
        "week_end": end,
        "logs": logs,
        "minutes": sum(x.minutes for x in logs),
        "days_worked": len(logs),
        "weekly_cap_minutes": limits.weekly_cap_minutes,
        "hours_per_day": limits.hours_per_day,
        "days_per_week": limits.days_per_week,
    }
