"""Domain events: a status change announces itself; other modules react.

publish() calls the subscribed handlers straight away, inside the caller's database
transaction. A handler that queues a notification therefore commits or rolls back
with the change that caused it, so there are no notifications for changes that never
happened, and none missing for changes that did.

    publish(DomainEvent("booking.confirmed", {"booking_id": ...}))

Handlers subscribe to an exact name or a prefix ending in "." ("booking.").
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from django.utils import timezone


@dataclass(frozen=True)
class DomainEvent:
    name: str
    payload: dict[str, Any]
    occurred_at: datetime = field(default_factory=timezone.now)


Handler = Callable[[DomainEvent], None]
_handlers: list[tuple[str, Handler]] = []


def subscribe(pattern: str, handler: Handler) -> None:
    """Call `handler` for events named `pattern`, or starting with it if it ends in '.'."""
    if (pattern, handler) not in _handlers:
        _handlers.append((pattern, handler))


def unsubscribe(pattern: str, handler: Handler) -> None:
    if (pattern, handler) in _handlers:
        _handlers.remove((pattern, handler))


def _matches(pattern: str, name: str) -> bool:
    return name.startswith(pattern) if pattern.endswith(".") else name == pattern


def publish(event: DomainEvent) -> None:
    for pattern, handler in list(_handlers):
        if _matches(pattern, event.name):
            handler(event)
