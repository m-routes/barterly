"""Domain events and reminders turning into notifications; the API; the task endpoint;
the real providers' message building."""

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.accounts.tests.factories import UserFactory
from apps.agreements.tests.helpers import sign_both
from apps.applications.services import apply
from apps.applications.tests.helpers import dates, eligible_talent, live_gig
from apps.bookings.tests.fakes import GOOD_TOKEN
from apps.bookings.tests.helpers import accepted, offered
from apps.common.events import DomainEvent, publish
from apps.notifications import reminders, services
from apps.notifications.channels.base import Message
from apps.notifications.models import Delivery, Notification, NotificationPreference, PushDevice
from apps.verification.tests.factories import client_for

pytestmark = pytest.mark.django_db


def latest(user, kind) -> Notification:
    return Notification.objects.filter(user=user, kind=kind).latest("created_at")


class TestTriggers:
    def test_new_applicant_reaches_the_host_with_the_name_and_a_console_link(self):
        gig = live_gig()
        talent = eligible_talent(display_name="Riya Sharma")
        application = apply(talent, gig.pk, pitch="Hi", answers=[], attachments=[], **dates())
        n = latest(gig.vendor, "application.applied")
        assert n.title == f"New applicant for {gig.title}"
        assert n.body == "Riya Sharma applied. Have a look."
        assert n.web_url == f"https://web.test/console/applicants/{application.pk}"

    def test_offer_sent_and_agreement_to_sign_and_booking_confirmed(self):
        booking = accepted()
        talent, vendor = booking.talent, booking.vendor
        offer = latest(talent, "application.offered")
        assert offer.app_path == f"/trips/offer/{booking.application_id}"
        ready = latest(talent, "agreement.ready")
        assert ready.app_path.startswith("/trips/agreement/")
        assert latest(vendor, "agreement.ready").web_url.startswith(
            "https://web.test/console/agreements/"
        )
        sign_both(booking)
        for user in (talent, vendor):
            confirmed = latest(user, "booking.confirmed")
            assert confirmed.title == "Booking confirmed"
            assert confirmed.app_path == ready.app_path  # the agreement, found by booking
            assert {d.channel for d in confirmed.deliveries.all()} >= {"push", "sms"}
        assert not Notification.objects.filter(kind="booking.signing").exists()

    def test_handling_the_same_event_twice_notifies_once(self):
        application = offered()
        event = DomainEvent(
            "interview.scheduled",
            {
                "interview_id": "i1",
                "application_id": str(application.pk),
                "gig_title": "X",
                "talent_id": str(application.talent_id),
                "vendor_id": str(application.gig.vendor_id),
            },
        )
        publish(event)
        publish(event)
        assert Notification.objects.filter(kind="interview.scheduled").count() == 2  # 1 each

    def test_a_burst_of_chat_messages_is_one_push(self):
        user = UserFactory()
        payload = {
            "conversation_id": "c1",
            "recipient_id": str(user.pk),
            "sender_name": "Asha",
            "gig_title": "X",
        }
        for i, text in enumerate(["Hi", "Are you there?", "See you Monday"]):
            publish(
                DomainEvent("chat.message", {**payload, "message_id": f"m{i}", "preview": text})
            )
        n = Notification.objects.get(user=user, kind="chat.message")
        assert (n.title, n.body, n.payload["count"]) == ("Asha", "See you Monday", 3)
        assert n.app_path == "/trips/chat/c1"

    def test_preferences_switch_a_channel_off_for_that_event(self):
        application = offered()
        NotificationPreference.objects.create(
            user=application.talent, event_type="reminder", channel="push", enabled=False
        )
        publish(
            DomainEvent(
                "interview.reminder_day",
                {
                    "interview_id": "i9",
                    "application_id": str(application.pk),
                    "gig_title": "X",
                    "starts_at_ist": "Tue 4 pm",
                    "talent_id": str(application.talent_id),
                    "vendor_id": str(application.gig.vendor_id),
                },
            )
        )
        talent_side = latest(application.talent, "interview.reminder_day")
        assert "push" not in {d.channel for d in talent_side.deliveries.all()}
        host_side = latest(application.gig.vendor, "interview.reminder_day")
        assert "push" in {d.channel for d in host_side.deliveries.all()}


class TestReminders:
    def test_offer_expiring_goes_to_whoever_must_answer_once(self):
        application = offered()
        now = application.offer_expires_at - timedelta(hours=5)
        assert reminders.send_reminders(now)["offers_expiring"] == 1
        reminders.send_reminders(now + timedelta(hours=1))
        notes = Notification.objects.filter(kind="offer.expiring")
        assert [(n.user_id, n.urgent) for n in notes] == [(application.talent_id, True)]
        assert "5 hours left" in notes[0].body
        assert reminders.send_reminders(application.offer_expires_at - timedelta(hours=20)) == {
            "offers_expiring": 0,
            "agreements_to_sign": 0,
            "stays_starting": 0,
        }

    def test_agreement_waiting_a_day_reminds_who_hasnt_signed(self):
        from apps.agreements.tests.helpers import awaiting, sign

        booking = accepted()
        version = awaiting(booking)
        sign(version, booking.vendor)
        later = timezone.now() + timedelta(hours=25)
        assert reminders.send_reminders(later)["agreements_to_sign"] == 1
        reminders.send_reminders(later + timedelta(hours=1))
        notes = Notification.objects.filter(kind="agreement.sign_reminder")
        assert [n.user_id for n in notes] == [booking.talent_id]

    def test_stay_starting_tomorrow_reminds_both(self):
        from apps.bookings.tests.helpers import booked

        booking = booked()
        day_before = timezone.make_aware(
            timezone.datetime.combine(
                booking.start_date - timedelta(days=1), timezone.datetime.min.time()
            )
        ) + timedelta(hours=9)
        assert reminders.send_reminders(day_before)["stays_starting"] == 1
        assert set(
            Notification.objects.filter(kind="booking.starts_soon").values_list(
                "user_id", flat=True
            )
        ) == {booking.talent_id, booking.vendor_id}

    def test_the_jobs_are_registered(self):
        from apps.bookings import jobs

        assert {"send_reminders", "dispatch_notifications"} <= set(jobs.JOBS)


class TestApi:
    def test_inbox_unread_count_and_reading(self):
        user = UserFactory()
        other = UserFactory()
        first = services.notify(user, "booking.checked_in", {"gig_title": "A"}, side="talent")
        services.notify(user, "booking.completed", {"gig_title": "B"}, side="talent")
        mine = services.notify(other, "booking.completed", {"gig_title": "C"}, side="talent")
        api = client_for(user)
        listed = api.get("/api/v1/notifications/").json()
        assert [n["title"] for n in listed["results"]] == ["Stay completed", "Checked in"]
        assert listed["results"][0]["app_path"] == "/trips"
        assert api.get("/api/v1/notifications/unread-count/").json() == {"unread": 2}
        read = api.post(
            f"/api/v1/notifications/{first.pk}/read/", {"from_push": True}, format="json"
        )
        assert read.status_code == 200 and read.json()["read"] is True
        assert len(api.get("/api/v1/notifications/?unread=true").json()["results"]) == 1
        assert api.post(f"/api/v1/notifications/{mine.pk}/read/").status_code == 404
        assert api.post("/api/v1/notifications/read-all/").json() == {"marked": 1}
        assert api.get("/api/v1/notifications/unread-count/").json() == {"unread": 0}
        assert client_for(None).get("/api/v1/notifications/").status_code == 401

    def test_preferences_round_trip(self):
        api = client_for(UserFactory())
        body = api.get("/api/v1/notifications/preferences/").json()
        assert body["locale"] == "en" and body["quiet_start"] == "22:00"
        assert body["channels_available"] == ["in_app", "push", "email", "sms", "whatsapp"]
        chat = next(t for t in body["event_types"] if t["key"] == "chat.message")
        assert chat["channels"]["push"] == {"enabled": True, "locked": False}
        assert chat["channels"]["in_app"] == {"enabled": True, "locked": True}
        expiring = next(t for t in body["event_types"] if t["key"] == "offer.expiring")
        assert expiring["urgent"] is True

        changed = api.put(
            "/api/v1/notifications/preferences/",
            {
                "locale": "hi",
                "quiet_start": "23:00",
                "quiet_end": "07:30",
                "changes": [
                    {"event_type": "chat.message", "channel": "push", "enabled": False},
                    {"event_type": "chat.message", "channel": "in_app", "enabled": False},
                ],
            },
            format="json",
        ).json()
        assert (changed["locale"], changed["quiet_start"], changed["quiet_end"]) == (
            "hi",
            "23:00",
            "07:30",
        )
        chat = next(t for t in changed["event_types"] if t["key"] == "chat.message")
        assert chat["label"] == "नया संदेश"
        assert chat["channels"]["push"]["enabled"] is False
        assert chat["channels"]["in_app"]["enabled"] is True  # can't switch the inbox off
        bad = api.put(
            "/api/v1/notifications/preferences/",
            {"changes": [{"event_type": "nope", "channel": "push", "enabled": True}]},
            format="json",
        )
        assert bad.status_code == 400

    def test_devices_register_move_and_unregister(self):
        one, two = UserFactory(), UserFactory()
        url = "/api/v1/notifications/devices/"
        assert client_for(one).post(url, {"token": "t1", "platform": "android"}).status_code == 204
        assert client_for(two).post(url, {"token": "t1", "platform": "android"}).status_code == 204
        assert PushDevice.objects.get(token="t1").user == two  # the phone changed hands
        client_for(one).post(f"{url}remove/", {"token": "t1"})
        assert PushDevice.objects.filter(token="t1").exists()  # not one's to remove
        client_for(two).post(f"{url}remove/", {"token": "t1"})
        assert not PushDevice.objects.filter(token="t1").exists()


class TestTaskEndpoint:
    def post(self, client, name, payload, token=GOOD_TOKEN):
        return client.post(
            f"/api/v1/tasks/{name}/",
            payload,
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )

    def test_runs_a_delivery_and_asks_for_a_retry_on_failure(self, client):
        from apps.notifications.channels.base import TemporaryFailure
        from apps.notifications.channels.fake import FakeProvider

        user = UserFactory()
        PushDevice.objects.create(user=user, token="t", platform="android")
        n = services.notify(
            user, "chat.message", {"sender_name": "A", "preview": "hi"}, side="talent"
        )
        push = n.deliveries.get(channel="push")
        FakeProvider.fail_next["push"] = [TemporaryFailure("FCM down")]
        retry = self.post(client, "notifications.deliver", {"delivery_id": push.pk})
        assert retry.status_code == 503
        ok = self.post(client, "notifications.deliver", {"delivery_id": push.pk})
        assert ok.status_code == 204
        push.refresh_from_db()
        assert (push.status, push.attempts) == ("sent", 2)

    def test_needs_the_tasks_token_and_a_known_task(self, client):
        assert self.post(client, "notifications.deliver", {}, token="nope").status_code == 401
        assert self.post(client, "no.such.task", {}).status_code == 404


class TestProviders:
    def message(self, **kw):
        return Message(
            notification_id="n1",
            kind="offer.expiring",
            locale="en",
            title="Offer expires soon",
            body="Front desk: 5 hours left to answer.",
            app_path="/trips/offer/a1",
            web_url="https://web.test/console/applicants/a1",
            urgent=True,
            **kw,
        )

    def test_fcm_payload_carries_the_deep_links(self):
        from apps.notifications.channels.fcm import build

        built = build(self.message(), "token-1")
        assert built.data == {
            "notification_id": "n1",
            "kind": "offer.expiring",
            "path": "/trips/offer/a1",
            "url": "https://web.test/console/applicants/a1",
        }
        assert built.android.priority == "high"
        assert built.webpush.fcm_options.link == "https://web.test/console/applicants/a1"
        assert built.notification.title == "Offer expires soon"

    def test_email_has_the_link_and_how_to_change_settings(self, mailoutbox=None):
        from django.core import mail

        from apps.notifications.channels.email import DjangoEmailProvider

        DjangoEmailProvider().send(self.message(to=("riya@example.com",)))
        sent = mail.outbox[-1]
        assert sent.subject == "Offer expires soon"
        assert "Open: https://web.test/console/applicants/a1" in sent.body
        assert "notification settings" in sent.body

    def test_cloud_tasks_queue_builds_an_authenticated_delayed_task(self, settings, monkeypatch):
        import sys
        import types

        created = []

        class Client:
            def queue_path(self, *parts):
                return "/".join(parts)

            def task_path(self, *parts):
                return "/".join(parts)

            def create_task(self, parent, task):
                created.append((parent, task))

        fake = types.SimpleNamespace(
            CloudTasksClient=Client, HttpMethod=types.SimpleNamespace(POST="POST")
        )
        monkeypatch.setitem(sys.modules, "google.cloud.tasks_v2", fake)
        import google.cloud

        monkeypatch.setattr(google.cloud, "tasks_v2", fake, raising=False)
        settings.CLOUD_TASKS_PROJECT, settings.CLOUD_TASKS_QUEUE = "proj", "notify"
        settings.TASKS_AUDIENCE = "https://api.test"
        settings.TASKS_INVOKER_EMAIL = "tasks@proj.iam.gserviceaccount.com"
        from apps.media.tasks import CloudTasksQueue

        CloudTasksQueue().enqueue("notifications.deliver", {"delivery_id": 7}, delay_seconds=60,
                                  task_id="delivery-7")  # fmt: skip
        parent, task = created[0]
        assert parent == "proj/asia-south1/notify"
        request = task["http_request"]
        assert request["url"] == "https://api.test/api/v1/tasks/notifications.deliver/"
        assert request["body"] == b'{"delivery_id": 7}'
        assert request["oidc_token"] == {
            "service_account_email": "tasks@proj.iam.gserviceaccount.com",
            "audience": "https://api.test",
        }
        assert task["name"].endswith("delivery-7")
        assert task["schedule_time"].seconds > 0


def test_every_delivery_row_names_a_real_channel():
    assert {c for c, _ in Delivery._meta.get_field("channel").choices} == {
        "in_app",
        "push",
        "email",
        "sms",
        "whatsapp",
    }


class TestFcmSending:
    @pytest.fixture
    def fcm(self, monkeypatch):
        from firebase_admin import exceptions, messaging

        from apps.notifications.channels import fcm

        outcomes: dict[str, object] = {}

        def send(message, app=None):
            outcome = outcomes.get(message.token, "ok")
            if isinstance(outcome, Exception):
                raise outcome
            return f"projects/p/messages/{message.token}"

        monkeypatch.setattr(messaging, "send", send)
        monkeypatch.setattr(fcm, "messaging_app", lambda: None)
        return fcm.FcmPushProvider(), outcomes, exceptions, messaging

    def message(self, *tokens):
        return TestProviders().message(to=tokens)

    def test_sends_and_reports_tokens_fcm_no_longer_knows(self, fcm):
        provider, outcomes, _, messaging = fcm
        outcomes["gone"] = messaging.UnregisteredError("gone")
        result = provider.send(self.message("good", "gone"))
        assert result.reference == "projects/p/messages/good"
        assert result.dead_tokens == ("gone",)

    def test_outages_are_temporary_and_bad_tokens_permanent(self, fcm):
        from apps.notifications.channels.base import PermanentFailure, TemporaryFailure

        provider, outcomes, exceptions, _ = fcm
        outcomes["a"] = exceptions.UnavailableError("FCM down")
        with pytest.raises(TemporaryFailure, match="FCM down"):
            provider.send(self.message("a"))
        outcomes["b"] = exceptions.InvalidArgumentError("bad token")
        with pytest.raises(PermanentFailure, match="rejected"):
            provider.send(self.message("b"))
        with pytest.raises(PermanentFailure, match="No device"):
            provider.send(self.message())


class TestEmailFailures:
    def test_refused_recipients_are_permanent_and_outages_temporary(self, monkeypatch):
        import smtplib

        from django.core.mail import EmailMessage

        from apps.notifications.channels.base import PermanentFailure, TemporaryFailure
        from apps.notifications.channels.email import DjangoEmailProvider

        provider = DjangoEmailProvider()
        message = TestProviders().message(to=("x@example.com",))

        def refuse(self, fail_silently=False):
            raise smtplib.SMTPRecipientsRefused({"x@example.com": (550, b"no")})

        monkeypatch.setattr(EmailMessage, "send", refuse)
        with pytest.raises(PermanentFailure):
            provider.send(message)

        def down(self, fail_silently=False):
            raise OSError("connection refused")

        monkeypatch.setattr(EmailMessage, "send", down)
        with pytest.raises(TemporaryFailure):
            provider.send(message)
        with pytest.raises(PermanentFailure, match="No email"):
            provider.send(TestProviders().message())
