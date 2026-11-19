"""Every kind of notification: who it's for, how urgent, which channels by default, and
where tapping it goes.

The event types people can switch on and off one by one are FEATURED. Every other event
that reaches someone (a booking checked in, a change declined, ...) is an "other update":
it shares one preference and a generic template.
"""

from dataclasses import dataclass, field

from django.conf import settings

from apps.notifications.models import Channel

TALENT, VENDOR = "talent", "vendor"
C = Channel

# What a featured event goes out on unless the person changes it. In-app is always on.
STANDARD = frozenset({C.IN_APP, C.PUSH, C.EMAIL})
PUSH_ONLY = frozenset({C.IN_APP, C.PUSH})
TIME_CRITICAL = frozenset({C.IN_APP, C.PUSH, C.EMAIL, C.SMS, C.WHATSAPP})
OTHER = "other"


@dataclass(frozen=True)
class EventType:
    key: str
    label_en: str
    label_hi: str
    defaults: frozenset = STANDARD
    urgent: bool = False  # not held back by quiet hours
    configurable: bool = True
    aliases: tuple[str, ...] = field(default=())  # more event names sharing its settings


FEATURED: tuple[EventType, ...] = (
    EventType("application.applied", "New applicant", "नया आवेदक"),
    EventType("application.shortlisted", "You're shortlisted", "आप शॉर्टलिस्ट हुए"),
    EventType("interview.scheduled", "Interview scheduled", "इंटरव्यू तय हुआ"),
    EventType(
        "application.offered",
        "Offer sent to you",
        "आपको ऑफ़र भेजा गया",
        defaults=TIME_CRITICAL - {C.WHATSAPP},
        aliases=("offer.reopened", "offer.counter_declined"),
    ),
    EventType(
        "offer.expiring",
        "Offer about to expire",
        "ऑफ़र की समय-सीमा ख़त्म होने वाली है",
        defaults=TIME_CRITICAL,
        urgent=True,
    ),
    EventType(
        "agreement.ready",
        "Agreement to sign",
        "हस्ताक्षर के लिए अनुबंध",
        aliases=("agreement.sign_reminder",),
    ),
    EventType("booking.confirmed", "Booking confirmed", "बुकिंग पक्की हुई", defaults=TIME_CRITICAL),
    EventType("chat.message", "New message", "नया संदेश", defaults=PUSH_ONLY),
    EventType(
        "gigs.search_alert",
        "New gigs for a saved search",
        "सेव की गई खोज के लिए नए गिग",
        defaults=PUSH_ONLY,
    ),
    EventType(
        "reminder",
        "Reminders",
        "रिमाइंडर",
        aliases=("interview.reminder_day", "interview.reminder_hour", "booking.starts_soon"),
    ),
    EventType(
        "billing",
        "Billing and payments",
        "बिलिंग और भुगतान",
        aliases=("billing.payment_failed", "billing.grace_ending", "billing.features_locked"),
    ),
    EventType(OTHER, "Other updates", "अन्य अपडेट", defaults=frozenset({C.IN_APP})),
)
BY_KEY = {t.key: t for t in FEATURED}
_ALIASES = {alias: t for t in FEATURED for alias in t.aliases}
# Reminders that can't wait for morning.
URGENT_EVENTS = frozenset({"offer.expiring", "interview.reminder_hour"})

# Short names for the "other updates", shown in the generic template.
OTHER_LABELS: dict[str, tuple[str, str]] = {
    "application.rejected": ("Application not taken forward", "आवेदन आगे नहीं बढ़ा"),
    "application.withdrawn": ("Application withdrawn", "आवेदन वापस लिया गया"),
    "application.declined": ("Offer declined", "ऑफ़र अस्वीकार किया गया"),
    "application.confirmed": ("Offer accepted", "ऑफ़र स्वीकार किया गया"),
    "application.expired": ("Offer expired", "ऑफ़र की समय-सीमा ख़त्म"),
    "application.interview": ("Moved to interview", "इंटरव्यू के लिए चुना गया"),
    "application.interview_stale": ("Interview waiting on you", "इंटरव्यू आपकी राह देख रहा है"),
    "interview.proposed": ("Interview times proposed", "इंटरव्यू के समय सुझाए गए"),
    "interview.new_times_requested": ("New interview times asked for", "इंटरव्यू के नए समय माँगे गए"),
    "interview.cancelled": ("Interview cancelled", "इंटरव्यू रद्द हुआ"),
    "offer.countered": ("A change was asked for", "बदलाव माँगा गया"),
    "offer.held": ("Offer on hold", "ऑफ़र रुका हुआ है"),
    "offer.step_in": ("Place offered to the next applicant", "जगह अगले आवेदक को दी गई"),
    "agreement.signed": ("Agreement signed", "अनुबंध पर हस्ताक्षर हुए"),
    "agreement.in_force": ("Agreement in force", "अनुबंध लागू हुआ"),
    "agreement.change_proposed": ("Change to the agreement", "अनुबंध में बदलाव"),
    "agreement.change_declined": ("Change declined", "बदलाव अस्वीकार हुआ"),
    "booking.cancelled": ("Booking cancelled", "बुकिंग रद्द हुई"),
    "booking.checked_in": ("Checked in", "चेक-इन हुआ"),
    "booking.delivering": ("Work under way", "काम शुरू हुआ"),
    "booking.completed": ("Stay completed", "प्रवास पूरा हुआ"),
    "booking.no_show": ("Marked as a no-show", "नो-शो दर्ज हुआ"),
    "booking.disputed": ("Booking disputed", "बुकिंग पर विवाद"),
    "booking.refunded": ("Refunded", "रिफ़ंड हुआ"),
    "booking.reviewed": ("Reviewed", "समीक्षा हुई"),
    "booking.waiting_for_place": ("Waiting for a place", "जगह की प्रतीक्षा"),
    "booking.place_opened": ("A place opened up", "एक जगह ख़ाली हुई"),
    "money.funded": ("Stipend funded and held", "स्टाइपेंड जमा और सुरक्षित"),
    "money.payment_failed": ("Stipend payment failed", "स्टाइपेंड का भुगतान नहीं हुआ"),
    "money.released": ("Stipend released", "स्टाइपेंड जारी हुआ"),
    "money.refunded": ("Stipend refunded", "स्टाइपेंड वापस हुआ"),
    "money.deliverables_submitted": ("Work handed in", "काम जमा हुआ"),
    "money.changes_requested": ("Changes asked for", "बदलाव माँगे गए"),
}


def type_for(kind: str) -> EventType:
    """The event type whose preferences and defaults a notification kind follows."""
    return BY_KEY.get(kind) or _ALIASES.get(kind) or BY_KEY[OTHER]


def is_urgent(kind: str) -> bool:
    return kind in URGENT_EVENTS or type_for(kind).urgent


def label(kind: str, locale: str) -> str:
    if kind in OTHER_LABELS:
        en, hi = OTHER_LABELS[kind]
    else:
        t = type_for(kind)
        en, hi = t.label_en, t.label_hi
    return hi if locale == "hi" else en


# ---------- Where tapping it goes ----------


def _web(path: str) -> str:
    return f"{settings.WEB_APP_URL.rstrip('/')}{path}"


def links(kind: str, side: str, payload: dict) -> tuple[str, str]:
    """(mobile app route, web console URL) for this person. Hosts use the web console;
    talent use the app (their web link points at the same page for completeness)."""
    application = payload.get("application_id", "")
    agreement = payload.get("agreement_id", "")
    conversation = payload.get("conversation_id", "")
    if kind == "chat.message" and conversation:
        return f"/trips/chat/{conversation}", _web(f"/console/messages/{conversation}")
    if agreement or kind.startswith(("agreement.", "booking.", "money.")):
        if agreement:
            return f"/trips/agreement/{agreement}", _web(f"/console/agreements/{agreement}")
        return "/trips", _web("/console/agreements")
    if kind.startswith("billing."):
        return "/trips", _web("/console/billing")
    if kind == "gigs.search_alert":
        return "/discover", _web("/talent")
    if application:
        app = (
            f"/trips/offer/{application}"
            if _about_an_offer(kind)
            else f"/trips/application/{application}"
        )
        return app, _web(f"/console/applicants/{application}")
    return "/trips", _web("/console")


def _about_an_offer(kind: str) -> bool:
    return kind.startswith("offer.") or kind in ("application.offered", "application.expired")


ALL_CHANNELS = tuple(Channel.values)


def enabled_channels(kind: str, overrides: dict[tuple[str, str], bool]) -> set[str]:
    """Channels on for this kind: the type's defaults, changed by the person's choices
    (`overrides[(event_type, channel)]`). In-app can't be switched off: it's the inbox."""
    t = type_for(kind)
    on = set(t.defaults)
    for channel in ALL_CHANNELS:
        if (t.key, channel) in overrides:
            if overrides[(t.key, channel)]:
                on.add(channel)
            else:
                on.discard(channel)
    on.add(Channel.IN_APP)
    return on
