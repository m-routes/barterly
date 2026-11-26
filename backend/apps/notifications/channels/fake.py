"""Fake providers for tests and local runs: they keep what they were asked to send.

FakeProvider.outbox["push"] -> [Message, ...]
FakeProvider.fail_next["sms"] = [TemporaryFailure("...")]  # raised in turn
"""

from collections import defaultdict

from apps.notifications.channels.base import Message, Result


class FakeProvider:
    outbox: dict[str, list[Message]] = defaultdict(list)
    fail_next: dict[str, list[Exception]] = defaultdict(list)
    channel = ""

    @property
    def name(self) -> str:
        return f"fake_{self.channel}"

    def send(self, message: Message) -> Result:
        if self.fail_next[self.channel]:
            raise self.fail_next[self.channel].pop(0)
        self.outbox[self.channel].append(message)
        return Result(provider=self.name, reference=f"fake-{len(self.outbox[self.channel])}")

    @classmethod
    def reset(cls) -> None:
        cls.outbox.clear()
        cls.fail_next.clear()


class FakePush(FakeProvider):
    channel = "push"


class FakeEmail(FakeProvider):
    channel = "email"


class FakeSms(FakeProvider):
    """SMS: providers for India (MSG91, Gupshup, Twilio) go behind this interface."""

    channel = "sms"


class FakeWhatsApp(FakeProvider):
    """WhatsApp Business: approved templates only (see templates.whatsapp_template)."""

    channel = "whatsapp"
