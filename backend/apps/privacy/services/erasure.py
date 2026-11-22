"""Delete my account: a request, a grace period, then anonymisation.

Nothing a person can be identified by survives, but the records the business has to
keep stay, with their personal fields replaced (docs/privacy.md has the full table):

- payments and the ledger: kept unchanged. They hold no names or phone numbers, only
  amounts, gateway references and the (now anonymous) user id. Invoices keep the buyer
  details the law requires on a tax invoice; only the email is removed.
- agreements: versions and terms are kept. Signatures keep the document hash, the
  provider reference and the time; the signer's phone is masked to its last four
  digits and the IP, user agent and device are removed.
- disputes: kept; apps that hold them register their own anonymiser.
- the audit log: entries are kept. Phone numbers, emails and names inside them are
  replaced with "[erased]".

The user row itself is kept (other records point at it) with a placeholder phone,
no email, no password, and is_active off.
"""

import secrets
from collections.abc import Callable
from datetime import timedelta

from django.apps import apps
from django.conf import settings
from django.db import connection, models, transaction
from django.utils import timezone

from apps.common.models import AuditLog
from apps.common.services.audit import log_action
from apps.media.storage import get_storage
from apps.privacy.models import DeletionRequest, DeletionStatus

ERASED = "[erased]"
DELETED_NAME = "Deleted member"
# Keys in audit before/after values that hold personal data.
PERSONAL_KEYS = frozenset(
    {
        "phone",
        "email",
        "name",
        "display_name",
        "contact_name",
        "business_name",
        "emergency_contact_name",
        "emergency_contact_phone",
        "date_of_birth",
        "address",
        "bio",
        "home_city",
        "instagram_handle",
        "buyer_email",
        "buyer_name",
        "note",
        "pitch",
        "body",
    }
)
ACTIVE_BOOKING = ("signing", "confirmed", "checked_in", "delivering", "disputed")
MONEY_IN_FLIGHT = ("funding", "held", "released")


class ErasureError(Exception):
    def __init__(self, code: str, message: str, status: int = 409, details=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details or {}


Anonymiser = Callable[..., int]
_anonymisers: list[tuple[str, Anonymiser]] = []


def register_anonymiser(name: str, fn: Anonymiser) -> None:
    """Add an erasure step: fn(user, now) -> rows changed. Runs in the same transaction."""
    if all(existing != name for existing, _ in _anonymisers):
        _anonymisers.append((name, fn))


# ---------- blockers ----------


def blockers(user) -> list[dict]:
    """Why the account can't be deleted yet. Empty when it can."""
    Booking = apps.get_model("bookings.Booking")
    Escrow = apps.get_model("money.Escrow")
    Payout = apps.get_model("money.Payout")
    Subscription = apps.get_model("billing.Subscription")
    found = []
    mine = models.Q(talent=user) | models.Q(vendor=user)
    active = Booking.objects.filter(mine, status__in=ACTIVE_BOOKING).count()
    if active:
        found.append(
            {
                "code": "active_bookings",
                "count": active,
                "message": "Finish or cancel your bookings first.",
            }
        )
    money = Escrow.objects.filter(
        models.Q(booking__talent=user) | models.Q(booking__vendor=user),
        status__in=MONEY_IN_FLIGHT,
    ).exclude(payout_status="settled")
    if money.exists():
        found.append(
            {
                "code": "money_in_flight",
                "count": money.count(),
                "message": "A stipend is still held or being paid out.",
            }
        )
    pending = Payout.objects.filter(talent=user, status__in=("creating", "processing")).count()
    if pending:
        found.append(
            {
                "code": "payouts_pending",
                "count": pending,
                "message": "A payout to you is still on its way.",
            }
        )
    open_plan = Subscription.objects.filter(
        vendor=user, status__in=("authenticated", "active", "past_due")
    ).count()
    if open_plan:
        found.append(
            {
                "code": "open_subscription",
                "count": open_plan,
                "message": "Cancel your Barterly plan first.",
            }
        )
    return found


# ---------- the request ----------


def request_deletion(user, *, reason: str = "", request=None, now=None) -> DeletionRequest:
    now = now or timezone.now()
    found = blockers(user)
    if found:
        raise ErasureError(
            "deletion_blocked", "Your account can't be deleted yet.", details={"blockers": found}
        )
    with transaction.atomic():
        existing = (
            DeletionRequest.objects.select_for_update()
            .filter(user=user, status=DeletionStatus.SCHEDULED)
            .first()
        )
        if existing:
            return existing
        entry = DeletionRequest.objects.create(
            user=user,
            status=DeletionStatus.SCHEDULED,
            reason=reason.strip()[:500],
            requested_at=now,
            scheduled_for=now + timedelta(days=settings.PRIVACY_DELETION_GRACE_DAYS),
        )
        log_action(
            actor=user,
            action="privacy.deletion_requested",
            obj=entry,
            before={"status": None},
            after={"status": entry.status, "scheduled_for": entry.scheduled_for},
            request=request,
        )
    return entry


def cancel_deletion(user, *, request=None, now=None) -> DeletionRequest:
    now = now or timezone.now()
    with transaction.atomic():
        entry = (
            DeletionRequest.objects.select_for_update()
            .filter(user=user, status=DeletionStatus.SCHEDULED)
            .first()
        )
        if entry is None:
            raise ErasureError("no_deletion_scheduled", "No deletion is scheduled.", 404)
        entry.status = DeletionStatus.CANCELLED
        entry.cancelled_at = now
        entry.save(update_fields=["status", "cancelled_at"])
        log_action(
            actor=user,
            action="privacy.deletion_cancelled",
            obj=entry,
            before={"status": DeletionStatus.SCHEDULED},
            after={"status": entry.status},
            request=request,
        )
    return entry


def run_due(now) -> dict[str, int]:
    """Job: anonymise accounts whose grace period is over. Blocked ones wait a day."""
    done = waiting = 0
    due = DeletionRequest.objects.filter(status=DeletionStatus.SCHEDULED, scheduled_for__lte=now)
    for pk in list(due.values_list("pk", flat=True)):
        with transaction.atomic():
            entry = DeletionRequest.objects.select_for_update().select_related("user").get(pk=pk)
            if entry.status != DeletionStatus.SCHEDULED:
                continue
            if blockers(entry.user):
                entry.scheduled_for = now + timedelta(days=1)
                entry.save(update_fields=["scheduled_for"])
                log_action(
                    actor=None,
                    action="privacy.deletion_postponed",
                    obj=entry,
                    after={"scheduled_for": entry.scheduled_for},
                )
                waiting += 1
                continue
            summary = anonymise(entry.user, now=now)
            entry.status = DeletionStatus.COMPLETED
            entry.completed_at = now
            entry.summary = summary
            entry.save(update_fields=["status", "completed_at", "summary"])
            log_action(
                actor=None,
                action="privacy.deletion_completed",
                obj=entry,
                before={"status": DeletionStatus.SCHEDULED},
                after={"status": entry.status, "summary": summary},
            )
            done += 1
    return {"anonymised": done, "postponed": waiting}


# ---------- anonymisation ----------


def anonymise(user, *, now=None, reason: str = "account_deleted") -> dict[str, int]:
    """Replace every personal field we hold about `user`. Idempotent. Call inside a
    transaction (run_due and the minor path do)."""
    now = now or timezone.now()
    with transaction.atomic():
        # Lets the agreements trigger accept the signature update below, for this
        # transaction only (apps/agreements/migrations/0003_signature_erasure.py).
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('barterly.erasure', 'on', true)")
        summary = {name: fn(user, now) for name, fn in [*STEPS, *_anonymisers]}
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('barterly.erasure', 'off', true)")
        log_action(
            actor=None,
            action="privacy.account_anonymised",
            obj=user,
            after={"reason": reason, "summary": summary},
        )
    return summary


def _model(label: str):
    return apps.get_model(label)


def _user(user, now) -> int:
    User = _model("accounts.User")
    placeholder = f"del-{secrets.token_hex(6)}"  # 16 characters, never a valid phone
    User.objects.filter(pk=user.pk).update(
        phone=placeholder,
        email=None,
        password=f"!{secrets.token_urlsafe(30)}",
        is_active=False,
        updated_at=now,
    )
    user.refresh_from_db()
    return 1


def _tokens(user, now) -> int:
    from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

    count = 0
    for token in OutstandingToken.objects.filter(user_id=user.pk):
        _, created = BlacklistedToken.objects.get_or_create(token=token)
        count += created
    return count


def _profiles(user, now) -> int:
    changed = (
        _model("profiles.TalentProfile")
        .all_objects.filter(user=user)
        .update(
            display_name=DELETED_NAME,
            bio="",
            talent_type="",
            languages=[],
            home_city="",
            emergency_contact_name="",
            emergency_contact_phone="",
            date_of_birth=None,
            instagram_handle="",
            instagram_followers=None,
            deleted_at=now,
        )
    )
    for profile in _model("profiles.TalentProfile").all_objects.filter(user=user):
        profile.skills.clear()
    changed += (
        _model("profiles.VendorProfile")
        .all_objects.filter(user=user)
        .update(
            business_name=DELETED_NAME,
            contact_name="",
            about="",
            address="",
            gstin="",
            website="",
            deleted_at=now,
        )
    )
    return changed


def _media(user, now) -> int:
    MediaFile = _model("media.MediaFile")
    storage = get_storage()
    count = 0
    for media in MediaFile.all_objects.filter(owner=user):
        for key in [media.object_key, *(media.variants or {}).values()]:
            if key:
                storage.delete(key)
        count += 1
    MediaFile.all_objects.filter(owner=user, deleted_at__isnull=True).update(deleted_at=now)
    return count


def _properties(user, now) -> int:
    Property = _model("properties.Property")
    rows = Property.objects.model._base_manager.filter(vendor=user)
    return rows.update(address="", directions="", pincode="", latitude=None, longitude=None)


def _gigs(user, now) -> int:
    Gig = _model("gigs.Gig")
    count = 0
    for gig in Gig.objects.filter(vendor=user).exclude(status__in=("closed", "archived")):
        before = gig.status
        Gig.objects.filter(pk=gig.pk).update(status="closed", status_reason="Account deleted.")
        log_action(
            actor=None,
            action="gig.closed",
            obj=gig,
            before={"status": before},
            after={"status": "closed", "reason": "account_deleted"},
        )
        count += 1
    return count


def _verification(user, now) -> int:
    count = (
        _model("verification.VerificationCase")
        .objects.filter(user=user)
        .update(details={}, reason="")
    )
    # Keep the status and the masked last four (fraud checks); drop everything else.
    count += (
        _model("verification.VerificationDocument")
        .objects.filter(case__user=user)
        .update(metadata={})
    )
    return count


def _personal_rows(user, now) -> int:
    """Settings, devices, searches and scores: deleted outright, nobody needs them."""
    count = 0
    for label, field in (
        ("notifications.PushDevice", "user"),
        ("notifications.NotificationPreference", "user"),
        ("notifications.NotificationSettings", "user"),
        ("discovery.SavedSearch", "talent"),
        ("hiring.SavedApplicantFilter", "vendor"),
        ("reliability.ReliabilityScore", "user"),
        ("reviews.Reputation", "user"),
        ("chat.Block", "blocker"),
        ("chat.Block", "blocked"),
    ):
        count += _model(label).objects.filter(**{field: user}).delete()[0]
    Notification = _model("notifications.Notification")
    count += Notification.objects.filter(user=user).update(
        title=ERASED, body="", payload={}, web_url="", app_path=""
    )
    return count


def _applications(user, now) -> int:
    Application = _model("applications.Application")
    mine = Application.objects.filter(talent=user)
    count = mine.update(pitch="", answers=[])
    count += (
        _model("applications.ApplicationAttachment")
        .objects.filter(application__talent=user)
        .delete()[0]
    )
    count += (
        _model("hiring.Interview")
        .objects.filter(application__talent=user)
        .update(video_link="", note="")
    )
    note = _model("hiring.ApplicationNote")
    count += note.objects.filter(application__talent=user).update(body=ERASED)
    count += note.objects.filter(author=user).update(body=ERASED)
    count += _model("bookings.Cancellation").objects.filter(user=user).update(note="")
    return count


def _chat(user, now) -> int:
    count = (
        _model("chat.Message")
        .objects.filter(sender=user)
        .update(body="Message removed: the sender deleted their account.")
    )
    count += _model("chat.LeakageEvent").objects.filter(sender=user).update(original_body="")
    count += _model("chat.MessageReport").objects.filter(reporter=user).update(note="")
    return count


def _agreements(user, now) -> int:
    Signature = _model("agreements.Signature")
    count = 0
    for signature in Signature.objects.filter(user=user):
        masked = f"******{signature.phone[-4:]}" if signature.phone else ""
        evidence = {k: v for k, v in (signature.evidence or {}).items() if k in SAFE_EVIDENCE}
        count += Signature.objects.filter(pk=signature.pk).update(
            phone=masked, ip=None, user_agent="", device="", evidence=evidence
        )
    return count


# Evidence keys that identify nothing on their own.
SAFE_EVIDENCE = frozenset({"otp_provider", "method", "provider"})


def _money(user, now) -> int:
    count = (
        _model("money.PayoutAccount")
        .objects.filter(talent=user)
        .update(active=False, validation_reason="")
    )
    count += _model("billing.Invoice").objects.filter(vendor=user).update(buyer_email="")
    return count


def _attendance(user, now) -> int:
    count = (
        _model("attendance.AttendancePass")
        .objects.filter(talent=user)
        .update(latitude=None, longitude=None, accuracy_m=None, code_secret="")
    )
    count += _model("attendance.HourLog").objects.filter(talent=user).update(note="")
    return count


def _reviews(user, now) -> int:
    Review = _model("reviews.Review")
    # Published reviews are frozen in the database and stay, by "Deleted member".
    count = Review.objects.filter(author=user, published_at__isnull=True).update(text="")
    count += _model("reviews.ReviewReport").objects.filter(reporter=user).update(note="")
    return count


def _audit(user, now) -> int:
    """Scrub personal values from the audit entries about or by this person. The audit
    log is append-only in the ORM; this is the one sanctioned rewrite, and it is itself
    audited (privacy.account_anonymised)."""
    entries = AuditLog.objects.filter(
        models.Q(actor=user) | models.Q(object_type="accounts.user", object_id=str(user.pk))
    )
    count = 0
    for entry in entries.iterator():
        before, after = _scrub(entry.before), _scrub(entry.after)
        if before != entry.before or after != entry.after:
            models.QuerySet.update(AuditLog.objects.filter(pk=entry.pk), before=before, after=after)
            count += 1
    return count


def _scrub(value):
    if isinstance(value, dict):
        return {
            k: (ERASED if k in PERSONAL_KEYS and v not in (None, "") else _scrub(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    return value


STEPS: list[tuple[str, Anonymiser]] = [
    ("profiles", _profiles),
    ("media", _media),
    ("properties", _properties),
    ("gigs", _gigs),
    ("verification", _verification),
    ("personal_rows", _personal_rows),
    ("applications", _applications),
    ("chat", _chat),
    ("agreements", _agreements),
    ("money", _money),
    ("attendance", _attendance),
    ("reviews", _reviews),
    ("audit", _audit),
    ("tokens", _tokens),
    ("user", _user),
]
