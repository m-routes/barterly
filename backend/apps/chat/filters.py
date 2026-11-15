"""Profanity filter hook for chat messages.

settings.CHAT_PROFANITY_FILTER names the class (like the other provider settings). A
filter returns what to do with a message: send it as is, send a cleaned copy, or refuse
it with a reason. The default lets everything through; WordListProfanityFilter masks
the words in settings.CHAT_PROFANITY_WORDS. A moderation service can be plugged in
the same way.
"""

import re
from dataclasses import dataclass
from functools import cache
from typing import Protocol

from django.conf import settings
from django.utils.module_loading import import_string


@dataclass(frozen=True)
class FilterResult:
    action: str  # "allow", "mask" or "refuse"
    text: str
    reason: str = ""

    ALLOW = "allow"
    MASK = "mask"
    REFUSE = "refuse"


class ProfanityFilter(Protocol):
    def check(self, text: str) -> FilterResult: ...


class NoopProfanityFilter:
    def check(self, text: str) -> FilterResult:
        return FilterResult(FilterResult.ALLOW, text)


class WordListProfanityFilter:
    """Masks whole words from settings.CHAT_PROFANITY_WORDS (case-insensitive)."""

    def __init__(self, words: list[str] | None = None):
        words = words if words is not None else settings.CHAT_PROFANITY_WORDS
        self._pattern = (
            re.compile(r"\b(?:" + "|".join(re.escape(w) for w in words) + r")\b", re.I)
            if words
            else None
        )

    def check(self, text: str) -> FilterResult:
        if not self._pattern or not self._pattern.search(text):
            return FilterResult(FilterResult.ALLOW, text)
        return FilterResult(
            FilterResult.MASK, self._pattern.sub(lambda m: "*" * len(m.group()), text)
        )


@cache
def _build(path: str) -> ProfanityFilter:
    return import_string(path)()


def get_filter() -> ProfanityFilter:
    return _build(settings.CHAT_PROFANITY_FILTER)
