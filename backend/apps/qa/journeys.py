"""Starting points for the acceptance journeys (manage.py prepare_journey).

The Playwright suite walks the whole journey itself, the vendor in the browser and the
talent through the API. The Flutter suite tests the talent's side in the app, so it
needs the vendor's steps already done. prepare_journey does those for a talent
persona and prints the ids:

- a fresh live gig to apply to,
- an offer waiting for the talent's answer,
- a booking starting today (to show the check-in pass),
- a paid booking with a deliverable due (to hand in),
- a finished stay waiting for the talent's review,
- a paid booking the host hasn't funded yet (the double-tap-on-pay scenario),
- a booking starting tomorrow (the late-cancellation scenario).
"""

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.qa.seed import Seeder

ARCHIVE_PREFIX = "+9190009"  # +91 90009 NNNNN: retired onboarding accounts


def _retire(phone: str) -> User | None:
    """Move an account off `phone` (deactivated, archive number) so the number's next
    sign-in is a brand-new account. Accounts are never deleted: their bookings, money
    and audit trail stay."""
    with transaction.atomic():
        user = User.objects.select_for_update().filter(phone=phone).first()
        if user is None:
            return None
        taken = User.objects.filter(phone__startswith=ARCHIVE_PREFIX).count()
        user.phone = f"{ARCHIVE_PREFIX}{taken + 1:05d}"
        user.is_active = False
        user.save(update_fields=["phone", "is_active"])
    return user


def reset_onboarding_persona(personas: dict) -> User | None:
    """The onboarding host signs up from scratch on the next run."""
    return _retire(personas["onboarding_vendor"]["phone"])


def reset_journey_personas(personas: dict, seeder: Seeder | None = None) -> None:
    """Before each hire journey: a brand-new host to onboard, and a talent with a
    complete, ID-verified profile and no stays booked (bookings can't overlap)."""
    reset_onboarding_persona(personas)
    _retire(personas["journey_creator"]["phone"])
    (seeder or Seeder(personas=personas)).persona("journey_creator")


def prepare(talent_key: str, seeder: Seeder | None = None) -> dict[str, str]:
    from apps.qa.providers import seed_providers

    seeder = seeder or Seeder()
    with seed_providers(), transaction.atomic():
        return _prepare(seeder, talent_key)


def _prepare(seeder: Seeder, talent_key: str) -> dict[str, str]:
    from apps.bookings.lifecycle import Actor, BookingStatus
    from apps.bookings.services import transition as move_booking

    talent = seeder.persona(talent_key)
    hostel, cafe = seeder.persona("hostel_owner"), seeder.persona("cafe_owner")
    seeder.payout_account(talent)
    hostel_prop = seeder.property_for(hostel, seeder.personas["hostel_owner"])
    cafe_prop = seeder.property_for(cafe, seeder.personas["cafe_owner"])
    stamp = f"{talent_key} {timezone.localtime().strftime('%d %b %H:%M:%S')}"

    to_apply = seeder.gig(hostel, hostel_prop, title=f"Apply here {stamp}", slots=3)
    to_apply_offline = seeder.gig(hostel, hostel_prop, title=f"Apply offline {stamp}", slots=3)

    today_gig = seeder.gig(
        hostel, hostel_prop, title=f"Arriving today {stamp}", slots=1, **seeder.window(talent)
    )
    arriving = seeder.booking(today_gig, talent)
    seeder.move_into_past(arriving, 0)

    def paid(title):
        from decimal import Decimal

        return seeder.gig(
            cafe,
            cafe_prop,
            title=title,
            slots=1,
            **seeder.window(talent),
            role_template="content_creator",
            compensation_model="hybrid",
            stipend_amount=Decimal("5000"),
            stipend_period="total",
            deliverables=[{"type": "instagram_reel", "quantity": 1}],
        )

    delivering = seeder.booking(paid(f"Reel due {stamp}"), talent)
    seeder.fund(delivering)
    seeder.move_into_past(delivering, 12)  # the stay ended; the reel is still due
    seeder.check_in(delivering)

    unfunded = seeder.booking(paid(f"Not paid yet {stamp}"), talent)

    tomorrow_gig = seeder.gig(
        hostel, hostel_prop, title=f"Starts tomorrow {stamp}", slots=1, **seeder.window(talent)
    )
    starts_tomorrow = seeder.booking(tomorrow_gig, talent)
    seeder.move_into_past(starts_tomorrow, -1)

    finished = seeder.booking(paid(f"Review me {stamp}"), talent)
    seeder.fund(finished)
    seeder.move_into_past(finished, 30)
    seeder.check_in(finished)
    seeder.hand_in_all(finished, approve=True)
    move_booking(finished.pk, BookingStatus.COMPLETED, actor=Actor.SYSTEM, reason="Stay ended.")

    # Last, so its dates come after every stay above (accepting it must not overlap).
    offer_gig = seeder.gig(
        hostel, hostel_prop, title=f"Offer waiting {stamp}", slots=1, **seeder.window(talent)
    )
    offered = seeder.application(offer_gig, talent)
    seeder.offer(offered)

    return {
        "talent_phone": talent.phone,
        "gig_to_apply": str(to_apply.pk),
        "gig_to_apply_title": to_apply.title,
        "gig_to_apply_offline_title": to_apply_offline.title,
        "offer_application": str(offered.pk),
        "booking_arriving_today": str(arriving.pk),
        "booking_arriving_today_title": arriving.gig.title,
        "booking_deliverable_due": str(delivering.pk),
        "booking_deliverable_due_title": delivering.gig.title,
        "booking_to_review": str(finished.pk),
        "booking_unfunded": str(unfunded.pk),
        "booking_starts_tomorrow": str(starts_tomorrow.pk),
        "booking_starts_tomorrow_title": starts_tomorrow.gig.title,
        "booking_starts_tomorrow_agreement": str(starts_tomorrow.agreement.pk),
    }
