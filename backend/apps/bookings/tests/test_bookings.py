import threading
from datetime import timedelta

import pytest
import yaml
from django.core.management import call_command
from django.db import DatabaseError, connection, transaction
from django.utils import timezone

from apps.accounts.tests.factories import AdminUserFactory
from apps.applications.constants import ApplicationStatus as A
from apps.applications.models import Application
from apps.applications.services import InvalidApplicationTransition, apply
from apps.applications.services import transition as application_transition
from apps.applications.tests.helpers import dates, eligible_talent, live_gig
from apps.bookings import lifecycle
from apps.bookings.lifecycle import (
    TRANSITIONS,
    Actor,
    Context,
    GuardFailed,
    InvalidTransition,
    check,
)
from apps.bookings.lifecycle import (
    BookingStatus as B,
)
from apps.bookings.models import Booking, BookingEvent
from apps.bookings.services import BookingRefused, accept_offer, transition
from apps.bookings.tests.helpers import booked, offered
from apps.common.events import subscribe, unsubscribe
from apps.common.models import AuditLog
from apps.gigs.constants import CompensationModel, GigStatus
from apps.gigs.tests.factories import in_days
from apps.notifications.models import Notification
from apps.verification.tests.factories import client_for

pytestmark = pytest.mark.django_db


@pytest.fixture
def events():
    seen = []

    def handler(event):
        seen.append(event)

    subscribe("application.", handler)
    subscribe("booking.", handler)
    yield seen
    unsubscribe("application.", handler)
    unsubscribe("booking.", handler)


class TestTheTable:
    def test_every_row_names_known_states_and_actors(self):
        states = set(A.values) | set(B.values)
        for (frm, to), rule in TRANSITIONS.items():
            assert frm in states and to in states, (frm, to)
            assert rule.actors and rule.actors <= set(Actor.values), (frm, to)

    def test_every_booking_state_is_reachable_from_confirmed(self):
        reachable, frontier = {B.CONFIRMED}, [B.CONFIRMED]
        while frontier:
            state = frontier.pop()
            for frm, to in TRANSITIONS:
                if frm == state and to not in reachable:
                    reachable.add(to)
                    frontier.append(to)
        assert reachable >= set(B.values)

    def test_check_explains_refusals(self):
        booking = type("B", (), {"start_date": in_days(10), "end_date": in_days(20)})()
        with pytest.raises(InvalidTransition, match="Can't go"):
            check(B.CONFIRMED, B.REVIEWED, Context(booking, Actor.VENDOR))
        with pytest.raises(InvalidTransition, match="Only the"):
            check(B.DISPUTED, B.REFUNDED, Context(booking, Actor.TALENT))
        with pytest.raises(GuardFailed, match="Give a reason"):
            check(B.CONFIRMED, B.CANCELLED, Context(booking, Actor.TALENT))
        with pytest.raises(GuardFailed, match="Check-in opens"):
            check(B.CONFIRMED, B.CHECKED_IN, Context(booking, Actor.VENDOR))


class TestOffersAndAcceptance:
    def test_accepting_an_offer_books_the_slot(self, events):
        gig = live_gig(slots=1)
        application = offered(gig)
        assert application.offer_expires_at == application.status_changed_at + lifecycle.OFFER_TTL

        booking = accept_offer(application.pk, talent=application.talent)

        application.refresh_from_db()
        assert application.status == A.CONFIRMED
        assert booking.status == B.CONFIRMED
        assert (booking.start_date, booking.end_date) == (
            application.proposed_start,
            application.proposed_end,
        )
        event = BookingEvent.objects.get(booking=booking)
        assert (event.from_state, event.to_state, event.actor) == ("offered", "confirmed", "talent")
        assert AuditLog.objects.filter(
            action="booking.confirmed", object_id=str(booking.pk)
        ).exists()
        gig.refresh_from_db()
        assert gig.status == GigStatus.FILLED  # its only slot is booked
        assert [e.name for e in events][-2:] == ["application.confirmed", "booking.confirmed"]
        kinds = {(n.user_id, n.kind) for n in Notification.objects.all()}
        assert (application.talent_id, "application.offered") in kinds
        assert (gig.vendor_id, "booking.confirmed") in kinds

    def test_an_expired_offer_cant_be_accepted(self):
        application = offered()
        Application.objects.filter(pk=application.pk).update(
            offer_expires_at=timezone.now() - timedelta(minutes=1)
        )
        with pytest.raises(BookingRefused, match="expired"):
            accept_offer(application.pk, talent=application.talent)

    def test_no_offer_without_an_open_slot_and_no_overbooking(self):
        gig = live_gig(slots=1)
        first, second = offered(gig), offered(gig)
        waiting = apply(
            eligible_talent(), gig.pk, pitch="Hi", answers=[], attachments=[], **dates()
        )
        accept_offer(first.pk, talent=first.talent)
        with pytest.raises(BookingRefused, match="Every slot"):
            accept_offer(second.pk, talent=second.talent)
        with pytest.raises(InvalidApplicationTransition, match="Every slot"):
            application_transition(waiting.pk, A.OFFERED, actor=Actor.VENDOR, user=gig.vendor)

    def test_overlapping_bookings_are_refused(self):
        talent = eligible_talent()
        booked(talent=talent)
        clash = offered(talent=talent)
        with pytest.raises(BookingRefused, match="already have a booking"):
            accept_offer(clash.pk, talent=talent)

    def test_only_the_applicant_can_accept(self):
        application = offered()
        with pytest.raises(Booking.DoesNotExist):
            accept_offer(application.pk, talent=eligible_talent())


@pytest.mark.django_db(transaction=True)
def test_two_simultaneous_confirmations_cannot_overbook():
    gig = live_gig(slots=1)
    first, second = offered(gig), offered(gig)
    barrier = threading.Barrier(2)
    outcomes = []

    def accept(application):
        try:
            barrier.wait()
            accept_offer(application.pk, talent=application.talent)
            outcomes.append("booked")
        except BookingRefused as exc:
            outcomes.append(str(exc))
        finally:
            connection.close()

    threads = [threading.Thread(target=accept, args=(a,)) for a in (first, second)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert outcomes.count("booked") == 1
    assert "Every slot" in next(o for o in outcomes if o != "booked")
    assert Booking.objects.filter(gig=gig).count() == 1


class TestBookingTransitions:
    def test_the_happy_path_writes_an_event_for_each_step(self, events):
        booking = booked()
        on_day_one = timezone.make_aware(
            timezone.datetime.combine(booking.start_date, timezone.datetime.min.time())
        )
        transition(
            booking.pk, B.CHECKED_IN, actor=Actor.VENDOR, user=booking.vendor, now=on_day_one
        )
        transition(
            booking.pk, B.DELIVERING, actor=Actor.TALENT, user=booking.talent, now=on_day_one
        )
        transition(booking.pk, B.COMPLETED, actor=Actor.VENDOR, user=booking.vendor, now=on_day_one)
        transition(booking.pk, B.REVIEWED, actor=Actor.TALENT, user=booking.talent, now=on_day_one)
        steps = list(
            BookingEvent.objects.filter(booking=booking).values_list("from_state", "to_state")
        )
        assert steps == [
            ("offered", "confirmed"),
            ("confirmed", "checked_in"),
            ("checked_in", "delivering"),
            ("delivering", "completed"),
            ("completed", "reviewed"),
        ]
        booking.refresh_from_db()
        assert booking.checked_in_at and booking.completed_at
        assert [e.name for e in events if e.name.startswith("booking.")][-4:] == [
            "booking.checked_in",
            "booking.delivering",
            "booking.completed",
            "booking.reviewed",
        ]

    def test_cancelling_frees_the_slot_and_reopens_the_gig(self):
        gig = live_gig(slots=1)
        booking = booked(gig)
        gig.refresh_from_db()
        assert gig.status == GigStatus.FILLED
        with pytest.raises(BookingRefused, match="Give a reason"):
            transition(booking.pk, B.CANCELLED, actor=Actor.TALENT, user=booking.talent)
        transition(booking.pk, B.CANCELLED, actor=Actor.TALENT, user=booking.talent, reason="Exams")
        gig.refresh_from_db()
        assert gig.status == GigStatus.LIVE
        notified = set(
            Notification.objects.filter(kind="booking.cancelled").values_list("user_id", flat=True)
        )
        assert notified == {booking.vendor_id}  # the other side

    def test_disputes_and_refunds_are_for_admins(self):
        gig = live_gig(
            compensation_model=CompensationModel.PAID,
            stipend_amount=5000,
            stipend_period="total",
            stay_type="none",
        )
        booking = booked(gig)
        transition(
            booking.pk, B.CANCELLED, actor=Actor.VENDOR, user=booking.vendor, reason="Closed"
        )
        with pytest.raises(BookingRefused, match="Only the"):
            transition(booking.pk, B.REFUNDED, actor=Actor.TALENT, reason="Refund me")
        admin = AdminUserFactory()
        transition(booking.pk, B.REFUNDED, actor=Actor.ADMIN, user=admin, reason="Paid back")
        entry = AuditLog.objects.get(action="booking.refunded")
        assert entry.actor == admin and entry.after["by"] == "admin"

    def test_refunds_need_money_involved(self):
        booking = booked()  # a volunteer gig
        transition(booking.pk, B.CANCELLED, actor=Actor.VENDOR, user=booking.vendor, reason="x")
        with pytest.raises(BookingRefused, match="Only paid and hybrid"):
            transition(booking.pk, B.REFUNDED, actor=Actor.ADMIN, reason="?")

    def test_a_rolled_back_transition_leaves_no_trace(self):
        booking = booked()
        before = (
            BookingEvent.objects.count(),
            Notification.objects.count(),
            AuditLog.objects.count(),
        )
        with pytest.raises(RuntimeError), transaction.atomic():
            transition(booking.pk, B.CANCELLED, actor=Actor.TALENT, user=booking.talent, reason="x")
            raise RuntimeError("something later failed")
        after = (
            BookingEvent.objects.count(),
            Notification.objects.count(),
            AuditLog.objects.count(),
        )
        assert before == after
        booking.refresh_from_db()
        assert booking.status == B.CONFIRMED


class TestEventLogIsAppendOnly:
    def test_the_database_refuses_updates_and_deletes(self):
        event = BookingEvent.objects.get(booking=booked())
        with pytest.raises(DatabaseError, match="append-only"), transaction.atomic():
            BookingEvent.objects.filter(pk=event.pk).update(reason="rewritten")
        with (
            pytest.raises(DatabaseError, match="append-only"),
            transaction.atomic(),
            connection.cursor() as cursor,
        ):
            cursor.execute("DELETE FROM bookings_bookingevent WHERE id = %s", [event.pk])
        with (
            pytest.raises(DatabaseError, match="append-only"),
            transaction.atomic(),
            connection.cursor() as cursor,
        ):
            cursor.execute("UPDATE bookings_bookingevent SET to_state = 'x'")
        assert BookingEvent.objects.get(pk=event.pk).reason == ""

    def test_inserting_still_works(self):
        booking = booked()
        BookingEvent.objects.create(
            booking=booking, from_state="confirmed", to_state="confirmed", actor="system"
        )
        assert BookingEvent.objects.filter(booking=booking).count() == 2


class TestApi:
    def test_vendor_offers_talent_accepts_and_both_see_the_booking(self):
        gig = live_gig()
        application = offered(gig)
        Application.objects.filter(pk=application.pk).update(status=A.SHORTLISTED)
        vendor, talent = client_for(gig.vendor), client_for(application.talent)

        made = vendor.post(
            f"/api/v1/applications/{application.pk}/status/", {"status": "offered"}, format="json"
        )
        assert made.status_code == 200, made.json()
        assert made.json()["offer_expires_at"]

        accepted = talent.post(f"/api/v1/applications/{application.pk}/accept/")
        assert accepted.status_code == 201, accepted.json()
        booking = accepted.json()
        assert booking["status"] == "confirmed"
        assert booking["next_moves"] == ["cancelled"]
        assert [e["to_state"] for e in booking["events"]] == ["confirmed"]

        assert [b["id"] for b in vendor.get("/api/v1/bookings/").json()["results"]] == [
            booking["id"]
        ]
        detail = vendor.get(f"/api/v1/bookings/{booking['id']}/").json()
        assert set(detail["next_moves"]) == {"cancelled", "checked_in", "no_show"}

    def test_transition_endpoint_reports_refusals(self):
        booking = booked()
        talent = client_for(booking.talent)
        url = f"/api/v1/bookings/{booking.pk}/transition/"
        early = client_for(booking.vendor).post(url, {"status": "checked_in"}, format="json")
        assert early.status_code == 409 and "Check-in opens" in early.json()["message"]
        not_mine = talent.post(url, {"status": "checked_in"}, format="json")
        assert not_mine.status_code == 409 and "Only the vendor" in not_mine.json()["message"]
        Booking.objects.filter(pk=booking.pk).update(start_date=timezone.localdate())
        ok = client_for(booking.vendor).post(url, {"status": "checked_in"}, format="json")
        assert ok.status_code == 200 and ok.json()["status"] == "checked_in"
        stranger = client_for(eligible_talent()).post(url, {"status": "cancelled"}, format="json")
        assert stranger.status_code == 404

    def test_decline_and_vendor_moves(self):
        application = offered()
        vendor = client_for(application.gig.vendor)
        assert (
            vendor.post(
                f"/api/v1/applications/{application.pk}/status/",
                {"status": "interview"},
                format="json",
            ).status_code
            == 409
        )  # offered can't go back to interview
        declined = client_for(application.talent).post(
            f"/api/v1/applications/{application.pk}/decline/",
            {"reason": "Found another"},
            format="json",
        )
        assert declined.status_code == 200 and declined.json()["status"] == "declined"
        assert (
            client_for(eligible_talent())
            .post(f"/api/v1/applications/{application.pk}/decline/", {}, format="json")
            .status_code
            == 404
        )


def test_every_endpoint_is_in_the_openapi_schema(tmp_path):
    out = tmp_path / "schema.yaml"
    call_command("spectacular", "--file", str(out), "--validate", "--fail-on-warn")
    paths = set(yaml.safe_load(out.read_text())["paths"])
    assert {
        "/api/v1/applications/{application_id}/status/",
        "/api/v1/applications/{application_id}/decline/",
        "/api/v1/applications/{application_id}/accept/",
        "/api/v1/bookings/",
        "/api/v1/bookings/{booking_id}/",
        "/api/v1/bookings/{booking_id}/transition/",
        "/api/v1/jobs/{job}/",
    } <= paths


def test_guests_see_the_exact_location_only_while_booked():
    from apps.properties.services import can_see_exact_location

    booking = booked()
    prop = booking.gig.property
    assert can_see_exact_location(booking.talent, prop)
    assert not can_see_exact_location(eligible_talent(), prop)
    transition(booking.pk, B.CANCELLED, actor=Actor.TALENT, user=booking.talent, reason="x")
    assert not can_see_exact_location(booking.talent, prop)
