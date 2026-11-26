"""The channel provider interface: one provider per channel, chosen in settings.

    NOTIFICATION_PROVIDERS = {"push": "apps.notifications.channels.fcm.FcmPushProvider", ...}

A channel with no provider (None) is off for everyone: no deliveries are made for it.
Providers raise TemporaryFailure for anything worth retrying (timeouts, 5xx, quota) and
PermanentFailure for anything that won't get better (bad token, no address).
"""

from dataclasses import dataclass, field
from functools import cache
from typing import Protocol

from django.conf import settings
from django.utils.module_loading import import_string


class TemporaryFailure(Exception):
    """Retry later (Cloud Tasks backs off)."""


class PermanentFailure(Exception):
    """Don't retry: the delivery is marked failed."""


@dataclass(frozen=True)
class Message:
    """One notification, rendered, for one channel."""

    notification_id: str
    kind: str
    locale: str
    title: str
    body: str
    app_path: str
    web_url: str
    urgent: bool = False
    # Where to: phone for SMS/WhatsApp, email address, FCM tokens for push.
    to: tuple[str, ...] = ()
    # WhatsApp: the approved template and its parameters, in order.
    template: str = ""
    variables: tuple[str, ...] = ()
    data: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Result:
    provider: str
    reference: str = ""
    # Push: tokens FCM said are no longer valid (to switch those devices off).
    dead_tokens: tuple[str, ...] = ()


class ChannelProvider(Protocol):
    name: str

    def send(self, message: Message) -> Result: ...


@cache
def _build(path: str) -> ChannelProvider:
    return import_string(path)()


def get_provider(channel: str) -> ChannelProvider | None:
    path = settings.NOTIFICATION_PROVIDERS.get(channel)
    return _build(path) if path else None


def available(channel: str) -> bool:
    return bool(settings.NOTIFICATION_PROVIDERS.get(channel))
