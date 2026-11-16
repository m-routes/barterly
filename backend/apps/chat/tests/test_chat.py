import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import VendorFactory
from apps.applications.constants import ApplicationStatus as A
from apps.applications.services import apply, transition
from apps.applications.tests.helpers import dates, eligible_talent, live_gig
from apps.bookings.lifecycle import Actor
from apps.bookings.services import accept_offer
from apps.chat import filters
from apps.chat.models import Block, Conversation, LeakageEvent, Message, MessageReport, OpenedBy
from apps.chat.throttles import ChatSendThrottle
from apps.common.models import AuditLog
from apps.notifications.models import Notification
from apps.verification.tests.factories import MediaFileFactory

pytestmark = pytest.mark.django_db


def client(user) -> APIClient:
    c = APIClient()
    c.force_authenticate(user)
    return c


def applied(gig=None):
    gig = gig or live_gig()
    return apply(eligible_talent(), gig.pk, pitch="Hi", answers=[], attachments=[], **dates())


def shortlisted():
    application = applied()
    return transition(
        application.pk, A.SHORTLISTED, actor=Actor.VENDOR, user=application.gig.vendor
    )


def chat():
    """A shortlisted application's conversation, with clients for both sides."""
    application = shortlisted()
    conversation = Conversation.objects.get(application=application)
    return conversation, client(application.talent), client(application.gig.vendor)


def send(c, conversation, body="", **extra):
    return c.post(
        f"/api/v1/conversations/{conversation.pk}/messages/",
        {"body": body, **extra},
        format="json",
    )


def poll(c, conversation, **params):
    return c.get(f"/api/v1/conversations/{conversation.pk}/messages/", params)


class TestOpening:
    def test_shortlisting_opens_the_chat(self):
        application = shortlisted()
        conversation = Conversation.objects.get(application=application)
        assert conversation.opened_by == OpenedBy.SHORTLIST
        assert conversation.talent_id == application.talent_id
        assert conversation.vendor_id == application.gig.vendor_id
        assert AuditLog.objects.filter(action="chat.opened").exists()

    def test_vendor_can_open_by_messaging_and_its_idempotent(self):
        application = applied()
        vendor = client(application.gig.vendor)
        url = f"/api/v1/applications/{application.pk}/conversation/"
        first = vendor.post(url)
        assert first.status_code == 201
        assert first.json()["opened_at"] and first.json()["can_send"] is True
        again = vendor.post(url)
        assert again.status_code == 200 and again.json()["id"] == first.json()["id"]
        assert Conversation.objects.get().opened_by == OpenedBy.VENDOR_MESSAGE

    def test_talent_cant_open_and_cant_see_unopened(self):
        application = applied()
        talent = client(application.talent)
        assert (
            talent.post(f"/api/v1/applications/{application.pk}/conversation/").status_code == 403
        )
        assert talent.get("/api/v1/conversations/").json()["count"] == 0

    def test_other_vendors_and_closed_applications(self):
        application = applied()
        other = client(VendorFactory())
        url = f"/api/v1/applications/{application.pk}/conversation/"
        assert other.post(url).status_code == 404
        transition(application.pk, A.WITHDRAWN, actor=Actor.TALENT, user=application.talent)
        response = client(application.gig.vendor).post(url)
        assert response.status_code == 409


class TestMessaging:
    def test_send_poll_by_cursor_and_read(self):
        conversation, talent, vendor = chat()
        first = send(vendor, conversation, "Hi Priya, when can you start?")
        assert first.status_code == 201
        assert first.json()["notice"] == ""
        assert first.json()["message"]["cursor"] == "1" and first.json()["message"]["mine"]

        page = poll(talent, conversation).json()
        assert [m["body"] for m in page["results"]] == ["Hi Priya, when can you start?"]
        assert page["cursor"] == "1" and page["results"][0]["mine"] is False

        # Nothing new since the cursor.
        assert poll(talent, conversation, after=page["cursor"]).json()["results"] == []

        send(talent, conversation, "From the 1st of next month")
        newer = poll(vendor, conversation, after="1").json()
        assert [m["cursor"] for m in newer["results"]] == ["2"] and newer["cursor"] == "2"

        # Unread counts, then reading clears them and shows up as a read receipt.
        assert talent.get("/api/v1/conversations/unread/").json() == {
            "unread": 1,
            "conversations": 1,
        }
        listed = talent.get("/api/v1/conversations/").json()["results"][0]
        assert listed["unread"] == 1 and listed["other"]["role"] == "vendor"
        assert listed["last_message"]["body"] == "From the 1st of next month"
        assert listed["last_message"]["mine"] is True
        read = talent.post(
            f"/api/v1/conversations/{conversation.pk}/read/", {"up_to": "2"}, format="json"
        )
        assert read.json() == {"marked": 1}  # only the vendor's message; not their own
        assert talent.get("/api/v1/conversations/unread/").json()["unread"] == 0
        assert poll(vendor, conversation, after="2").json()["other_read_up_to"] == "1"

    def test_history_pages_back(self):
        conversation, _, vendor = chat()
        for i in range(5):
            send(vendor, conversation, f"m{i}")
        newest = poll(vendor, conversation, limit=2).json()
        assert [m["body"] for m in newest["results"]] == ["m3", "m4"] and newest["has_earlier"]
        older = poll(vendor, conversation, before="4", limit=2).json()
        assert [m["body"] for m in older["results"]] == ["m1", "m2"]
        assert poll(vendor, conversation, after="nope").status_code == 400

    def test_client_id_makes_retries_safe(self):
        conversation, _, vendor = chat()
        one = send(vendor, conversation, "Hello", client_id="abc")
        two = send(vendor, conversation, "Hello", client_id="abc")
        assert one.json()["message"]["id"] == two.json()["message"]["id"]
        assert Message.objects.count() == 1

    def test_strangers_get_404(self):
        conversation, _, _ = chat()
        stranger = client(eligible_talent())
        assert poll(stranger, conversation).status_code == 404
        assert send(stranger, conversation, "hi").status_code == 404

    def test_empty_and_too_long(self):
        conversation, _, vendor = chat()
        assert send(vendor, conversation, "   ").status_code == 400
        assert send(vendor, conversation, "x" * 2001).status_code == 400

    def test_closed_application_is_read_only(self):
        conversation, talent, vendor = chat()
        send(vendor, conversation, "hi")
        transition(
            conversation.application_id, A.WITHDRAWN, actor=Actor.TALENT,
            user=conversation.talent,
        )  # fmt: skip
        response = send(talent, conversation, "bye")
        assert response.status_code == 403 and "read-only" in response.json()["message"]
        assert poll(talent, conversation).status_code == 200  # still readable
        detail = talent.get(f"/api/v1/conversations/{conversation.pk}/").json()
        assert detail["can_send"] is False

    def test_new_message_queues_one_push_per_burst(self):
        conversation, talent, vendor = chat()
        Notification.objects.all().delete()
        send(vendor, conversation, "one")
        send(vendor, conversation, "two")
        note = Notification.objects.get(kind="chat.message")
        assert note.user_id == conversation.talent_id
        assert note.payload["count"] == 2 and note.payload["preview"] == "two"
        send(talent, conversation, "reply")
        assert (
            Notification.objects.filter(kind="chat.message", user=conversation.vendor).count() == 1
        )


class TestLeakageGuard:
    def test_masks_before_booking_tells_sender_and_logs(self):
        conversation, talent, _ = chat()
        response = send(talent, conversation, "WhatsApp me: 98765 43210")
        body = response.json()
        assert body["message"]["body"] == "[hidden] me: [hidden]"
        assert body["message"]["masked"] is True
        assert "phone number" in body["notice"] and "booking is confirmed" in body["notice"]
        event = LeakageEvent.objects.get()
        assert event.original_body == "WhatsApp me: 98765 43210"
        assert (
            event.kinds == ["off_platform", "phone"] and event.sender_id == conversation.talent_id
        )
        log = AuditLog.objects.get(action="chat.contact_masked")
        assert log.after["kinds"] == ["off_platform", "phone"]
        assert "98765" not in str(log.after)  # the hidden text stays out of the audit log
        # The other side never sees the original.
        assert "98765" not in str(poll(client(conversation.vendor), conversation).json())

    def test_contacts_allowed_once_booking_is_confirmed(self):
        conversation, talent, _ = chat()
        transition(
            conversation.application_id, A.OFFERED, actor=Actor.VENDOR, user=conversation.vendor
        )
        accept_offer(conversation.application_id, talent=conversation.talent)
        detail = talent.get(f"/api/v1/conversations/{conversation.pk}/").json()
        assert detail["contact_sharing_allowed"] is True
        response = send(talent, conversation, "My number is 98765 43210")
        assert response.json()["message"]["body"] == "My number is 98765 43210"
        assert response.json()["notice"] == ""
        assert not LeakageEvent.objects.exists()


class TestSafety:
    def test_block_stops_both_sides_and_unblock(self):
        conversation, talent, vendor = chat()
        url = f"/api/v1/conversations/{conversation.pk}/block/"
        assert talent.post(url).json()["blocked_by_me"] is True
        assert "Unblock" in send(talent, conversation, "hi").json()["message"]
        assert (
            send(vendor, conversation, "hi").json()["message"] == "You can't message this person."
        )
        assert AuditLog.objects.filter(action="chat.blocked").exists()
        assert talent.delete(url).json()["can_send"] is True
        assert not Block.objects.exists()
        assert send(vendor, conversation, "hi").status_code == 201
        assert AuditLog.objects.filter(action="chat.unblocked").exists()

    def test_report_a_message(self):
        conversation, talent, vendor = chat()
        message_id = send(vendor, conversation, "rude words").json()["message"]["id"]
        url = f"/api/v1/messages/{message_id}/report/"
        response = talent.post(url, {"reason": "harassment", "note": "Not ok"}, format="json")
        assert response.status_code == 201 and response.json()["status"] == "open"
        assert MessageReport.objects.get().reason == "harassment"
        assert talent.post(url, {"reason": "spam"}, format="json").status_code == 409
        assert vendor.post(url, {"reason": "spam"}, format="json").status_code == 400  # own
        assert (
            client(eligible_talent()).post(url, {"reason": "spam"}, format="json").status_code
            == 404
        )
        assert talent.post(url, {"reason": "nope"}, format="json").status_code == 400
        assert AuditLog.objects.filter(action="chat.message_reported").exists()

    def test_sending_is_rate_limited(self, monkeypatch):
        monkeypatch.setattr(ChatSendThrottle, "rate", "3/minute", raising=False)
        conversation, _, vendor = chat()
        codes = [send(vendor, conversation, f"m{i}").status_code for i in range(4)]
        assert codes == [201, 201, 201, 429]
        assert poll(vendor, conversation).status_code == 200  # polling isn't limited

    def test_attachment_rules(self):
        conversation, talent, _ = chat()
        me = conversation.talent
        photo = MediaFileFactory(owner=me, content_type="image/png", kind="photo")
        pdf = MediaFileFactory(owner=me, content_type="application/pdf", kind="document")
        ok = send(talent, conversation, "", attachment_ids=[str(photo.pk), str(pdf.pk)])
        assert ok.status_code == 201
        kinds = [a["kind"] for a in ok.json()["message"]["attachments"]]
        assert kinds == ["image", "document"]

        video = MediaFileFactory(owner=me, content_type="video/mp4", kind="video")
        assert (
            "PDFs"
            in send(talent, conversation, "", attachment_ids=[str(video.pk)]).json()["message"]
        )
        big = MediaFileFactory(owner=me, content_type="image/jpeg", size_bytes=11 * 1024 * 1024)
        assert (
            "10 MB"
            in send(talent, conversation, "", attachment_ids=[str(big.pk)]).json()["message"]
        )
        theirs = MediaFileFactory(content_type="image/jpeg")
        assert send(talent, conversation, "x", attachment_ids=[str(theirs.pk)]).status_code == 400
        pending = MediaFileFactory(owner=me, status="processing")
        assert send(talent, conversation, "x", attachment_ids=[str(pending.pk)]).status_code == 400
        four = [str(MediaFileFactory(owner=me).pk) for _ in range(4)]
        assert send(talent, conversation, "x", attachment_ids=four).status_code == 400


class TestProfanityHook:
    def test_word_list_filter_masks_and_says_so(self, settings):
        settings.CHAT_PROFANITY_FILTER = "apps.chat.filters.WordListProfanityFilter"
        settings.CHAT_PROFANITY_WORDS = ["darn"]
        filters._build.cache_clear()
        try:
            conversation, talent, _ = chat()
            body = send(talent, conversation, "Darn, the bus is late").json()
            assert body["message"]["body"] == "****, the bus is late"
            assert body["notice"] == "Some words were hidden."
        finally:
            filters._build.cache_clear()

    def test_a_filter_can_refuse(self, settings, monkeypatch):
        class Refuser:
            def check(self, text):
                return filters.FilterResult(filters.FilterResult.REFUSE, text, "Too spicy.")

        monkeypatch.setattr(filters, "get_filter", lambda: Refuser())
        monkeypatch.setattr("apps.chat.services.get_filter", lambda: Refuser())
        conversation, talent, _ = chat()
        response = send(talent, conversation, "anything")
        assert response.status_code == 400 and response.json()["message"] == "Too spicy."


class TestApplicationLists:
    def test_lists_carry_the_conversation_and_unread(self):
        conversation, talent, vendor = chat()
        send(vendor, conversation, "hi")
        mine = talent.get("/api/v1/applications/mine/").json()
        rows = mine["results"] if isinstance(mine, dict) else mine
        assert rows[0]["conversation"] == str(conversation.pk)
        assert rows[0]["unread_messages"] == 1
        gig_id = conversation.application.gig_id
        listed = vendor.get(f"/api/v1/gigs/{gig_id}/applications/").json()["results"][0]
        assert listed["conversation"] == str(conversation.pk) and listed["unread_messages"] == 0
