"""Post stats from the platforms, behind one interface.

- YouTube: the Data API v3 with an API key (public numbers of any video).
- Instagram: the Graph API's business discovery, with the platform's own Instagram
  business account token, looking the talent's handle up. META APP REVIEW NEEDED before
  it can be switched on (INSTAGRAM_STATS_ENABLED); until then talent enter their numbers
  by hand with a screenshot, shown as self-reported.

A provider returns None when it can't answer for a URL (not its platform, not set up,
the post not found): the caller then relies on self-reported numbers.
"""

import re
from dataclasses import dataclass
from functools import cache
from typing import Protocol

from django.conf import settings
from django.utils.module_loading import import_string

# Labels that disclose a paid collaboration (ASCI guidelines), case-insensitive.
DISCLOSURE_LABELS = (
    "#ad",
    "#collab",
    "#sponsored",
    "#partner",
    "#paidpartnership",
    "#barter",
    "paid partnership",
)


@dataclass(frozen=True)
class Stats:
    source: str  # "instagram" or "youtube"
    views: int | None
    likes: int | None
    comments: int | None
    caption: str | None = None  # when the platform gives it, to check the label


class SocialStatsProvider(Protocol):
    def stats_for(self, url: str, *, handle: str = "") -> Stats | None: ...


def has_disclosure(caption: str) -> bool:
    text = caption.lower()
    return any(
        re.search(rf"(?<![\w#]){re.escape(label)}(?!\w)", text) for label in DISCLOSURE_LABELS
    )


class CombinedProvider:
    """Asks each configured provider in turn."""

    def __init__(self):
        self.providers = [import_string(path)() for path in settings.SOCIAL_STATS_PROVIDERS]

    def stats_for(self, url, *, handle=""):
        for provider in self.providers:
            found = provider.stats_for(url, handle=handle)
            if found is not None:
                return found
        return None


@cache
def _build(path: str) -> SocialStatsProvider:
    return import_string(path)()


def get_provider() -> SocialStatsProvider:
    return _build(settings.SOCIAL_STATS_PROVIDER)
