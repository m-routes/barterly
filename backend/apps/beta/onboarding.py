"""The onboarding tracker: where each invited property is on the checklist.

docs/beta/onboarding/checklist.md is the same list, step for step. Ops call the hosts who
are stuck, using docs/beta/onboarding/first-gig-call-script.md.
"""

from dataclasses import dataclass, field

from django.db.models import Count, Min, Q

from apps.beta.models import InviteCode

STEPS = [
    ("signed_up", "Signed up with their code"),
    ("profile", "Business profile filled in"),
    ("property", "Property added"),
    ("verified", "ID or property verified"),
    ("gig_drafted", "First gig drafted"),
    ("gig_live", "First gig live"),
    ("hired", "First talent hired"),
]


@dataclass
class Row:
    invite: InviteCode
    user_id: object = None
    phone: str = ""
    done: dict = field(default_factory=dict)
    first_live_at: object = None

    @property
    def next_step(self) -> str:
        for key, label in STEPS:
            if not self.done.get(key):
                return label
        return "All done"

    @property
    def progress(self) -> int:
        return sum(1 for key, _ in STEPS if self.done.get(key))


def rows_for(cohort: str) -> list[Row]:
    from apps.bookings.models import Booking
    from apps.gigs.models import Gig
    from apps.profiles.models import VendorProfile
    from apps.properties.models import Property
    from apps.verification.constants import BadgeKind
    from apps.verification.models import Badge

    invites = list(
        InviteCode.objects.filter(cohort=cohort)
        .prefetch_related("redemptions__user")
        .order_by("label", "created_at")
    )
    users = {r.user_id: r.user for invite in invites for r in invite.redemptions.all()}
    ids = list(users)
    profiles = set(VendorProfile.objects.filter(user_id__in=ids).values_list("user_id", flat=True))
    properties = set(Property.objects.filter(vendor_id__in=ids).values_list("vendor_id", flat=True))
    verified = set(
        Badge.objects.filter(
            user_id__in=ids,
            revoked_at__isnull=True,
            kind__in=[BadgeKind.ID_VERIFIED, BadgeKind.PROPERTY_VERIFIED],
        ).values_list("user_id", flat=True)
    )
    gigs = {
        row["vendor_id"]: row
        for row in Gig.objects.filter(vendor_id__in=ids)
        .values("vendor_id")
        .annotate(
            total=Count("id"),
            went_live=Count("id", filter=Q(published_at__isnull=False)),
            first_live=Min("published_at"),
        )
    }
    hired = set(Booking.objects.filter(vendor_id__in=ids).values_list("vendor_id", flat=True))
    rows = []
    for invite in invites:
        redemptions = list(invite.redemptions.all()) or [None]
        for redemption in redemptions:
            row = Row(invite=invite)
            if redemption:
                uid = redemption.user_id
                g = gigs.get(uid, {})
                row.user_id = uid
                row.phone = users[uid].phone
                row.first_live_at = g.get("first_live")
                row.done = {
                    "signed_up": True,
                    "profile": uid in profiles,
                    "property": uid in properties,
                    "verified": uid in verified,
                    "gig_drafted": bool(g.get("total")),
                    "gig_live": bool(g.get("went_live")),
                    "hired": uid in hired,
                }
            rows.append(row)
    return rows


def funnel(rows: list[Row]) -> list[tuple[str, int]]:
    return [(label, sum(1 for r in rows if r.done.get(key))) for key, label in STEPS]


def cohorts() -> list[str]:
    return list(InviteCode.objects.order_by("cohort").values_list("cohort", flat=True).distinct())
