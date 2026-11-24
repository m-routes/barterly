"""Every feature flag, its default and what turning it off does.

A flag with no database row uses its default here, so a fresh database behaves as
before. Add a flag here first; the API refuses names that aren't listed.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Flag:
    default: bool
    description: str
    when_off: str


FLAGS: dict[str, Flag] = {
    "escrow_funding": Flag(
        default=True,
        description="Hosts can fund a booking's escrow.",
        when_off=(
            "New funding is refused with a 503 and a message; money already held, "
            "releases and payouts carry on (the kill switch stops those)."
        ),
    ),
    "sos_live_sharing": Flag(
        default=True,
        description="Talent can start a live location share from SOS.",
        when_off=(
            "New shares are refused with a message to call the emergency contact "
            "directly; active shares keep running until they expire. SOS alerts "
            "themselves are never switched off."
        ),
    ),
    "ai_safety_checks": Flag(
        default=True,
        description="Automated safety checks on new gigs.",
        when_off="Gigs skip the automated checks and go to the human review queue.",
    ),
}
