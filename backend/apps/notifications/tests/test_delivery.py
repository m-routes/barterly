"""Making notifications, delivering them through providers, retries and dead letters."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.notifications import services
from apps.notifications.channels.base import PermanentFailure, Result, TemporaryFailure
from apps.notifications.channels.fake import FakeProvider
from apps.notifications.models import (
    Delivery,
    DeliveryStatus,
    Notification,
    NotificationPreference,
    NotificationSettings,
    NotificationStatus,
    PushDevice,
)

pytestmark = pytest.mark.django_db
IST = ZoneInfo("Asia/Kolkata")
NOON = datetime(2026, 11, 17, 12, 0, tzinfo=IST)
LATE = datetime(2026, 11, 17, 23, 0, tzinfo=IST)


@pytest.fixture
def person():
    user = UserFactory(email="riya@example.com")
    PushDevice.objects.create(user=user, token="token-1", platform="android")
    return user


def offer_for(user, now=NOON, **payload):
    return services.notify(
        user,
        "application.offered",
        {"application_id": "a1", "gig_title": "Front desk", **payload},
        side="talent",
        now=now,
    )


def by_channel(notification) -> dict[str, Delivery]:
    return {d.channel: d for d in notification.deliveries.all()}


class TestMaking:
    def test_one_delivery_per_wanted_channel_in_the_users_language(self, person):
        NotificationSettings.objects.create(user=person, locale="hi")
        notification = offer_for(person)
        assert notification.title == "आपको ऑफ़र मिला है"
        assert notification.app_path == "/trips/offer/a1"
        assert notification.web_url == "https://web.test/console/applicants/a1"
        deliveries = by_channel(notification)
        assert set(deliveries) == {"in_app", "push", "email", "sms"}  # offer defaults
        assert deliveries["in_app"].status == DeliveryStatus.SENT
        assert all(
            d.status == DeliveryStatus.QUEUED for c, d in deliveries.items() if c != "in_app"
        )

    def test_preferences_are_respected(self, person):
        NotificationPreference.objects.create(
            user=person, event_type="application.offered", channel="email", enabled=False
        )
        NotificationPreference.objects.create(
            user=person, event_type="application.offered", channel="whatsapp", enabled=True
        )
        assert set(by_channel(offer_for(person))) == {"in_app", "push", "sms", "whatsapp"}

    def test_channels_without_a_provider_are_left_out(self, person, settings):
        settings.NOTIFICATION_PROVIDERS = {**settings.NOTIFICATION_PROVIDERS, "sms": None}
        assert "sms" not in by_channel(offer_for(person))

    def test_a_dedup_key_makes_one_notification(self, person):
        first = services.notify(person, "chat.message", {}, side="talent", dedup_key="k1")
        again = services.notify(person, "chat.message", {}, side="talent", dedup_key="k1")
        assert first is not None and again is None
        assert Notification.objects.filter(user=person).count() == 1

    def test_in_app_only_is_sent_at_once(self, person):
        n = services.notify(person, "booking.checked_in", {"gig_title": "X"}, side="talent")
        assert set(by_channel(n)) == {"in_app"}
        assert n.status == NotificationStatus.SENT

    def test_quiet_hours_hold_back_interrupting_channels_only(self, person):
        notification = offer_for(person, now=LATE)
        deliveries = by_channel(notification)
        morning = datetime(2026, 11, 18, 8, 0, tzinfo=IST)
        assert deliveries["push"].send_after == morning
        assert deliveries["sms"].send_after == morning
        assert deliveries["email"].send_after == LATE  # email doesn't wake anyone

    def test_urgent_ones_ignore_quiet_hours(self, person):
        notification = services.notify(
            person, "offer.expiring", {"gig_title": "X", "hours_left": 2}, side="talent", now=LATE
        )
        assert notification.urgent
        assert by_channel(notification)["push"].send_after == LATE

    def test_queued_once_the_transaction_commits(self, person, django_capture_on_commit_callbacks):
        # Real time here (the inline queue sends "now"): no quiet hours to wait for.
        NotificationSettings.objects.create(user=person, quiet_hours_enabled=False)
        with django_capture_on_commit_callbacks(execute=True):
            notification = offer_for(person, now=timezone.now())
        sent = FakeProvider.outbox["push"]
        assert [m.notification_id for m in sent] == [str(notification.pk)]
        message = sent[0]
        assert message.to == ("token-1",)
        assert (message.app_path, message.web_url) == (
            "/trips/offer/a1",
            "https://web.test/console/applicants/a1",
        )
        assert FakeProvider.outbox["email"][0].to == ("riya@example.com",)
        assert FakeProvider.outbox["sms"][0].to == (person.phone,)
        assert len(FakeProvider.outbox["sms"][0].body) <= 140 + len(
            " https://web.test/console/applicants/a1"
        )
        notification.refresh_from_db()
        assert notification.status == NotificationStatus.SENT


class TestDelivering:
    def push_of(self, person, now=NOON):
        return by_channel(offer_for(person, now=now))["push"]

    def test_sends_once_however_often_the_task_runs(self, person):
        delivery = self.push_of(person)
        services.deliver(delivery.pk, now=NOON)
        services.deliver(delivery.pk, now=NOON)
        delivery.refresh_from_db()
        assert delivery.status == DeliveryStatus.SENT and delivery.attempts == 1
        assert delivery.provider == "fake_push" and delivery.provider_reference == "fake-1"
        assert len(FakeProvider.outbox["push"]) == 1

    def test_not_before_quiet_hours_end(self, person):
        delivery = self.push_of(person, now=LATE)
        services.deliver(delivery.pk, now=LATE + timedelta(hours=1))
        assert FakeProvider.outbox["push"] == []
        services.deliver(delivery.pk, now=datetime(2026, 11, 18, 8, 1, tzinfo=IST))
        assert len(FakeProvider.outbox["push"]) == 1

    def test_temporary_failures_retry_then_become_dead_letters(self, person, settings):
        settings.NOTIFICATION_MAX_ATTEMPTS = 3
        delivery = self.push_of(person)
        FakeProvider.fail_next["push"] = [TemporaryFailure("FCM 503")] * 3
        for _ in range(2):
            with pytest.raises(services.RetryLater, match="FCM 503"):
                services.deliver(delivery.pk, now=NOON)
        delivery.refresh_from_db()
        assert (delivery.status, delivery.attempts) == (DeliveryStatus.QUEUED, 2)
        services.deliver(delivery.pk, now=NOON)  # the last attempt: no more retries
        delivery.refresh_from_db()
        assert delivery.status == DeliveryStatus.DEAD
        assert "FCM 503" in delivery.last_error

    def test_unexpected_errors_are_retried_too(self, person):
        delivery = self.push_of(person)
        FakeProvider.fail_next["push"] = [RuntimeError("boom")]
        with pytest.raises(services.RetryLater):
            services.deliver(delivery.pk, now=NOON)
        services.deliver(delivery.pk, now=NOON)
        delivery.refresh_from_db()
        assert delivery.status == DeliveryStatus.SENT and delivery.attempts == 2

    def test_permanent_failures_stop_at_once(self, person):
        delivery = self.push_of(person)
        FakeProvider.fail_next["push"] = [PermanentFailure("bad token")]
        services.deliver(delivery.pk, now=NOON)
        delivery.refresh_from_db()
        assert delivery.status == DeliveryStatus.FAILED and delivery.attempts == 1
        delivery.notification.refresh_from_db()
        assert delivery.notification.status == NotificationStatus.QUEUED  # others still to go

    def test_nowhere_to_send_is_skipped(self):
        user = UserFactory(email=None)
        email = by_channel(offer_for(user))["email"]
        services.deliver(email.pk, now=NOON)
        email.refresh_from_db()
        assert email.status == DeliveryStatus.SKIPPED and "Nowhere" in email.last_error

    def test_tokens_fcm_rejects_are_switched_off(self, person, monkeypatch):
        from apps.notifications.channels.fake import FakePush

        PushDevice.objects.create(user=person, token="stale", platform="ios")
        monkeypatch.setattr(
            FakePush, "send", lambda self, m: Result(provider="fake_push", dead_tokens=("stale",))
        )
        services.deliver(self.push_of(person).pk, now=NOON)
        assert PushDevice.objects.get(token="stale").disabled_at is not None
        assert PushDevice.objects.get(token="token-1").disabled_at is None

    def test_dead_letters_can_be_sent_again(
        self, person, settings, django_capture_on_commit_callbacks
    ):
        settings.NOTIFICATION_MAX_ATTEMPTS = 1
        delivery = self.push_of(person)
        FakeProvider.fail_next["push"] = [TemporaryFailure("down")]
        services.deliver(delivery.pk, now=NOON)
        delivery.refresh_from_db()
        assert delivery.status == DeliveryStatus.DEAD
        with django_capture_on_commit_callbacks(execute=True):
            assert services.requeue([delivery.pk]) == 1
        delivery.refresh_from_db()
        assert delivery.status == DeliveryStatus.SENT


class Recorder:
    def __init__(self):
        self.tasks = []

    def enqueue(self, name, payload, *, delay_seconds=0, task_id=None):
        self.tasks.append((name, payload["delivery_id"], delay_seconds))


class TestDispatchJob:
    def test_queues_lost_and_held_deliveries_once_due(self, person, monkeypatch):
        queue = Recorder()
        monkeypatch.setattr(services, "get_queue", lambda: queue)
        offer = offer_for(person, now=LATE)
        offer.deliveries.update(enqueued_at=LATE)  # their tasks were created at once
        held = by_channel(offer)["push"]
        lost = by_channel(services.notify(person, "chat.message", {}, side="talent", now=NOON))[
            "push"
        ]  # never queued: the commit hook didn't run

        assert services.dispatch_due(NOON + timedelta(minutes=5)) == {"queued": 1}
        assert queue.tasks == [("notifications.deliver", lost.pk, 0)]
        # Held until 8:00; its own task should run then. Ten minutes later, it's lost.
        queue.tasks.clear()
        services.dispatch_due(datetime(2026, 11, 18, 8, 5, tzinfo=IST))
        assert held.pk not in [pk for _, pk, _ in queue.tasks]
        queue.tasks.clear()
        services.dispatch_due(datetime(2026, 11, 18, 8, 15, tzinfo=IST))
        assert held.pk in [pk for _, pk, _ in queue.tasks]


class TestReading:
    def test_reading_marks_the_inbox_and_optionally_the_push(self, person):
        notification = offer_for(person)
        services.deliver(by_channel(notification)["push"].pk, now=NOON)
        assert services.mark_read(person, [notification.pk], from_push=True) == 1
        deliveries = by_channel(notification)
        assert deliveries["in_app"].status == DeliveryStatus.READ
        assert deliveries["push"].status == DeliveryStatus.READ
        assert deliveries["email"].status == DeliveryStatus.QUEUED
        assert services.mark_read(person, [notification.pk]) == 0  # already read


class TestAdmin:
    @pytest.fixture
    def admin_client(self, client):
        from apps.accounts.models import User

        client.force_login(User.objects.create_superuser("+919876599999", "admin-pass-123"))
        return client

    def test_the_dead_letter_view_lists_only_dead_ones_and_sends_again(
        self, admin_client, person, settings, django_capture_on_commit_callbacks
    ):
        settings.NOTIFICATION_MAX_ATTEMPTS = 1
        dead = by_channel(offer_for(person))["push"]
        FakeProvider.fail_next["push"] = [TemporaryFailure("down")]
        services.deliver(dead.pk, now=NOON)
        url = reverse("admin:notifications_deadletter_changelist")
        page = admin_client.get(url)
        assert page.status_code == 200
        assert list(page.context["cl"].queryset.values_list("pk", flat=True)) == [dead.pk]
        with django_capture_on_commit_callbacks(execute=True):
            admin_client.post(url, {"action": "send_again", "_selected_action": [dead.pk]})
        dead.refresh_from_db()
        assert dead.status == DeliveryStatus.SENT
        for name in ("notification", "delivery", "pushdevice", "notificationsettings"):
            assert (
                admin_client.get(reverse(f"admin:notifications_{name}_changelist")).status_code
                == 200
            )
        notification = dead.notification
        assert (
            admin_client.get(
                reverse("admin:notifications_notification_change", args=[notification.pk])
            ).status_code
            == 200
        )


def test_the_hours_default_to_ten_at_night_to_eight(person):
    prefs = services.settings_for(person)
    assert (prefs.quiet_start, prefs.quiet_end) in (("22:00", "08:00"), (time(22), time(8)))
