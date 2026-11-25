from datetime import timedelta

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.tests.factories import AdminUserFactory, TalentFactory, VendorFactory
from apps.common.models import AuditLog
from apps.notifications.models import Notification
from apps.support import services
from apps.support.models import CannedResponse, Priority, Ticket, TicketStatus

pytestmark = pytest.mark.django_db

TICKETS = reverse("support:tickets")


def api_for(user) -> APIClient:
    api = APIClient()
    api.force_authenticate(user)
    return api


def open_one(user, **body):
    return api_for(user).post(
        TICKETS,
        {
            "kind": "help",
            "subject": "Can't upload my reel",
            "body": "It stops at 90%.",
            "screen": "trips/deliverables",
            "platform": "android",
            "app_version": "1.4.0",
            **body,
        },
        format="json",
    )


def staff(role="support"):
    user = AdminUserFactory(roles=[role])
    browser = Client()
    browser.force_login(user)
    browser.user = user
    return browser


class TestPeople:
    def test_opening_a_request_sets_its_slas(self):
        talent = TalentFactory()
        before = timezone.now()
        response = open_one(talent)
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "open"
        assert body["reference"].startswith("S-")
        assert [m["body"] for m in body["messages"]] == ["It stops at 90%."]
        ticket = Ticket.objects.get()
        assert ticket.priority == Priority.NORMAL
        assert (
            before + timedelta(hours=23)
            < ticket.first_response_due
            <= timezone.now() + timedelta(hours=24)
        )
        assert AuditLog.objects.filter(action="support.ticket_opened").exists()

    @pytest.mark.parametrize(
        ("kind", "priority"), [("safety", "urgent"), ("payment", "urgent"), ("feedback", "low")]
    )
    def test_priority_follows_the_kind(self, kind, priority):
        open_one(TalentFactory(), kind=kind)
        assert Ticket.objects.get().priority == priority

    def test_feedback_has_no_resolution_deadline(self):
        open_one(TalentFactory(), kind="feedback")
        assert Ticket.objects.get().resolve_due is None

    def test_people_see_only_their_own(self):
        open_one(TalentFactory())
        other = TalentFactory()
        body = api_for(other).get(TICKETS).json()
        assert (body["results"] if isinstance(body, dict) else body) == []
        ticket = Ticket.objects.get()
        assert api_for(other).get(reverse("support:ticket", args=[ticket.pk])).status_code == 404

    def test_a_booking_must_be_theirs(self):
        from apps.bookings.tests.helpers import booked

        booking = booked()
        response = open_one(TalentFactory(), booking_id=str(booking.pk))
        assert response.status_code == 404
        assert open_one(booking.talent, booking_id=str(booking.pk)).status_code == 201

    def test_writing_again_reopens_a_resolved_request(self):
        talent = TalentFactory()
        open_one(talent)
        ticket = Ticket.objects.get()
        services.set_status(ticket, TicketStatus.RESOLVED, staff=AdminUserFactory())
        response = api_for(talent).post(
            reverse("support:ticket-reply", args=[ticket.pk]),
            {"body": "Still broken."},
            format="json",
        )
        assert response.status_code == 201
        assert response.json()["status"] == "open"
        ticket.refresh_from_db()
        assert ticket.resolve_due > timezone.now()

    def test_internal_notes_never_reach_the_person(self):
        talent = TalentFactory()
        open_one(talent)
        ticket = Ticket.objects.get()
        services.reply_as_staff(
            ticket, staff=AdminUserFactory(), body="Looks like a fraud ring.", internal=True
        )
        detail = api_for(talent).get(reverse("support:ticket", args=[ticket.pk])).json()
        assert [m["body"] for m in detail["messages"]] == ["It stops at 90%."]


class TestInbox:
    def test_a_reply_answers_assigns_and_notifies(self, django_capture_on_commit_callbacks):
        talent = TalentFactory()
        open_one(talent)
        ticket = Ticket.objects.get()
        browser = staff()
        with django_capture_on_commit_callbacks(execute=True):
            response = browser.post(
                reverse("admin:support_ticket", args=[ticket.pk]),
                {"action": "reply", "body": "Try again on Wi-Fi; we've raised the limit."},
            )
        assert response.status_code == 302
        ticket.refresh_from_db()
        assert ticket.status == TicketStatus.WAITING
        assert ticket.first_responded_at is not None
        assert ticket.assigned_to == browser.user
        note = Notification.objects.get(user=talent, kind="support.replied")
        assert ticket.reference in note.body
        assert note.app_path == f"/profile/help/{ticket.pk}"
        assert AuditLog.objects.filter(action="support.replied", actor=browser.user).exists()

    def test_overdue_requests_come_first_and_are_counted(self):
        open_one(TalentFactory(), subject="Fresh one")
        open_one(TalentFactory(), kind="safety", subject="Old and urgent")
        Ticket.objects.filter(subject="Old and urgent").update(
            first_response_due=timezone.now() - timedelta(hours=1)
        )
        assert services.overdue_count() == 1
        page = staff().get(reverse("admin:support_inbox")).content.decode()
        assert page.index("Old and urgent") < page.index("Fresh one")
        assert "Answer overdue" in page

    def test_canned_replies_come_in_the_persons_language(self):
        from apps.notifications.models import NotificationSettings

        talent = TalentFactory()
        NotificationSettings.objects.update_or_create(user=talent, defaults={"locale": "hi"})
        open_one(talent, kind="payment")
        ticket = Ticket.objects.get()
        canned = CannedResponse.objects.get(title="Payment: when the stipend is released")
        page = staff().get(reverse("admin:support_ticket", args=[ticket.pk]), {"canned": canned.pk})
        assert canned.body_hi in page.content.decode()

    def test_only_support_ops_and_trust_work_the_inbox(self):
        for role, expected in [("support", 200), ("ops", 200), ("trust", 200), ("finance", 403)]:
            assert staff(role).get(reverse("admin:support_inbox")).status_code == expected, role

    def test_starter_canned_replies_exist_in_both_languages(self):
        replies = CannedResponse.objects.all()
        assert replies.count() >= 5
        assert all(r.body_hi for r in replies)


class TestTimeline:
    def test_it_brings_a_persons_story_together_and_is_audited(self):
        from apps.bookings.tests.helpers import booked

        booking = booked()
        open_one(booking.talent, subject="Host asked me to pay a deposit", kind="safety")
        browser = staff()
        page = browser.get(reverse("admin:support_timeline", args=[booking.talent_id]))
        assert page.status_code == 200
        text = page.content.decode()
        assert "Host asked me to pay a deposit" in text  # support
        assert "Booking" in text  # booking history
        assert "Application" in text
        assert AuditLog.objects.filter(
            action="support.timeline_viewed", actor=browser.user, object_id=str(booking.talent_id)
        ).exists()

    def test_find_by_phone(self):
        vendor = VendorFactory()
        response = staff().get(reverse("admin:support_find_person"), {"phone": vendor.phone[3:]})
        assert response.status_code == 302
        assert str(vendor.pk) in response["Location"]

    def test_finance_cant_open_timelines(self):
        vendor = VendorFactory()
        assert (
            staff("finance").get(reverse("admin:support_timeline", args=[vendor.pk])).status_code
            == 403
        )


class TestPrivacy:
    def test_export_includes_requests_but_not_internal_notes(self):
        from apps.privacy.services.exports import collect

        talent = TalentFactory()
        open_one(talent)
        services.reply_as_staff(
            Ticket.objects.get(), staff=AdminUserFactory(), body="internal!", internal=True
        )
        data = collect(talent)
        assert len(data["support_requests"]) == 1
        assert [m["body"] for m in data["support_messages"]] == ["It stops at 90%."]

    def test_erasure_drops_what_they_wrote(self):
        talent = TalentFactory()
        open_one(talent)
        services.anonymise(talent, timezone.now())
        ticket = Ticket.objects.get()
        assert ticket.subject == "[deleted]"
        assert set(ticket.messages.values_list("body", flat=True)) == {"[deleted]"}
