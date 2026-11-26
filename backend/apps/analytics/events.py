"""The product events apps may send, and the only properties each may carry.

Anything else is dropped on arrival: unknown events, unknown properties, and values of the
wrong shape. Properties are never free text, so nothing personal can ride along.
Adding an event: add it here, then in web/src/lib/analytics/events.ts and
mobile/lib/src/analytics/events.dart (tests compare the three lists).
"""

import re
import uuid

SLUG = re.compile(r"^[a-z0-9][a-z0-9_/-]{0,59}$")


def _slug(value):
    return value if isinstance(value, str) and SLUG.match(value) else None


def _uuid(value):
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError):
        return None


def _count(value):
    return (
        value
        if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 10_000
        else None
    )


def _bool(value):
    return value if isinstance(value, bool) else None


def _one_of(*allowed):
    def check(value):
        return value if value in allowed else None

    return check


# Screens are route templates with the ids taken out: "trips/agreement", not ".../<uuid>".
EVENTS: dict[str, dict] = {
    "screen_view": {"screen": _slug},
    "onboarding_step": {"step": _one_of("role", "consent", "profile", "property", "done")},
    "invite_entered": {"ok": _bool},
    "gig_builder_step": {"step": _count},
    "gig_submitted": {"gig_id": _uuid},
    "search": {"filters": _count, "results": _count},
    "gig_viewed": {"gig_id": _uuid, "source": _one_of("search", "alert", "saved", "link", "home")},
    "apply_started": {"gig_id": _uuid},
    "apply_submitted": {"gig_id": _uuid, "offline": _bool},
    "offer_viewed": {"application_id": _uuid},
    "help_opened": {"screen": _slug},
    "feedback_sent": {"kind": _one_of("help", "feedback", "bug", "safety", "payment")},
}


def clean(name: str, props) -> dict | None:
    """The event's allowed properties, or None if the event isn't one we take."""
    spec = EVENTS.get(name)
    if spec is None:
        return None
    props = props if isinstance(props, dict) else {}
    out = {}
    for key, check in spec.items():
        if key in props:
            value = check(props[key])
            if value is not None:
                out[key] = value
    return out
