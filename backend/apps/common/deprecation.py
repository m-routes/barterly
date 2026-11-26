"""Deprecated API operations and their sunset dates (docs/api-versioning.md).

Add an entry when an operation is deprecated; DeprecationMiddleware then sends
- `Deprecation: @<unix time>` (RFC 9745): since when;
- `Sunset: <HTTP date>` (RFC 8594): the earliest date it may be removed;
- `Link: <url>; rel="deprecation"`: what to use instead.

Remove the entry in the release that deletes the operation. `test_deprecation` checks
that every sunset is at least the policy's minimum notice after deprecation.
"""

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from email.utils import format_datetime

# Mobile users update slowly: a removed field or endpoint must wait this long, and
# until the minimum app version (apps.appversions) excludes every caller.
MINIMUM_NOTICE_DAYS = 90
POLICY_URL = "https://github.com/m-routes/barterly/blob/main/docs/api-versioning.md"


@dataclass(frozen=True)
class Deprecated:
    path: str  # a regex matched against the request path, e.g. r"^/api/v1/gigs/search/$"
    deprecated_on: date
    sunset_on: date
    link: str = POLICY_URL
    methods: frozenset[str] = field(default_factory=frozenset)  # empty: every method

    def matches(self, method: str, path: str) -> bool:
        if self.methods and method.upper() not in self.methods:
            return False
        return re.search(self.path, path) is not None


DEPRECATIONS: list[Deprecated] = []


def _midnight(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


def headers_for(method: str, path: str) -> dict[str, str]:
    for entry in DEPRECATIONS:
        if entry.matches(method, path):
            return {
                "Deprecation": f"@{int(_midnight(entry.deprecated_on).timestamp())}",
                "Sunset": format_datetime(_midnight(entry.sunset_on), usegmt=True),
                "Link": f'<{entry.link}>; rel="deprecation"',
            }
    return {}
