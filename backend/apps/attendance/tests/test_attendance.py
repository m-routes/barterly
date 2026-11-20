"""Passes, signatures, codes, check-in (live and offline), the geofence, check-out and
no-shows."""

import uuid
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse
from django.utils import timezone

from apps.accounts.tests.factories import AdminUserFactory, VendorFactory
from apps.attendance import services, signing
from apps.attendance.models import AttendancePass, CheckIn
from apps.attendance.services import AttendanceError
from apps.backoffice.roles import AdminRole, sync_roles
from apps.bookings.lifecycle import Actor, BookingStatus
from apps.bookings.services import transition
from apps.bookings.tests.helpers import booked
from apps.common.models import AuditLog
from apps.reliability.models import ReliabilityScore
from apps.verification.tests.factories import client_for

pytestmark = pytest.mark.django_db
B = BookingStatus


def at(day, hour=10):
    return timezone.make_aware(datetime.combine(day, time(hour)))


def located(booking, metres_north=0):
    """Where the talent was when they opened their pass, relative to the property."""
    prop = booking.gig.property
    return {
        "latitude": prop.latitude + Decimal(str(round(metres_north / 111_000, 6))),
        "longitude": prop.longitude,
        "accuracy_m": 15,
    }


def pass_for(booking, *, now=None, metres_north=None):
    location = None if metres_north is None else located(booking, metres_north)
    return services.talent_pass(
        booking.pk, talent=booking.talent, location=location, now=now or at(booking.start_date, 9)
    )


def scan(booking, attendance_pass=None, *, when=None, **extra):
    when = when or at(booking.start_date)
    attendance_pass = attendance_pass or pass_for(booking, now=when)
    return services.check_in(
        vendor=booking.vendor,
        method="qr",
        token=services.token_for(attendance_pass),
        scanned_at=when,
        now=when,
        **extra,
    )


class TestSigning:
    def test_a_token_round_trips_and_resists_tampering(self):
        now = timezone.now()
        token = signing.sign(
            booking_id="b1",
            talent_id="t1",
            pass_id="p1",
            not_before=now,
            expires=now + timedelta(hours=1),
        )
        payload = signing.verify(token)
        assert (payload["b"], payload["t"], payload["p"]) == ("b1", "t1", "p1")
        prefix, body, sig = token.split(".")
        forged = signing.b64url(signing.unb64url(body).replace(b"b1", b"b2"))
        for bad in (f"{prefix}.{forged}.{sig}", token[:-4] + "AAAA", "hello", "BRT2.a.b"):
            with pytest.raises(signing.TokenError):
                signing.verify(bad)

    def test_rotated_keys_still_verify_and_unknown_keys_dont(self, settings):
        import base64

        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

        now = timezone.now()
        old = signing.sign(booking_id="b", talent_id="t", pass_id="p", not_before=now, expires=now)
        old_public = signing.current_key().raw_public
        settings.ATTENDANCE_SIGNING_KEY = base64.b64encode(b"\x07" * 32).decode()
        with pytest.raises(signing.TokenError, match="no longer in use"):
            signing.verify(old)
        settings.ATTENDANCE_PREVIOUS_PUBLIC_KEYS = [base64.b64encode(old_public).decode()]
        assert signing.verify(old)["b"] == "b"
        assert len(signing.public_keys()) == 2
        other = (
            Ed25519PrivateKey.generate().public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        )
        assert signing.b64url(other) not in {k["public_key"] for k in signing.public_keys()}

    def test_codes_are_rfc_6238(self):
        # RFC 6238's SHA-1 vector: counter 1 gives 94287082 (8 digits), so 287082 in six.
        # Counter 1 is 300-599 seconds at this 5-minute step.
        secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # noqa: S105 (a published test vector)
        moment = datetime.fromtimestamp(300, tz=UTC)
        assert signing.code_at(secret, moment) == "287082"
        assert signing.code_matches(secret, "287082", moment)
        assert signing.code_matches(secret, "287 082", moment + timedelta(seconds=300))  # late
        assert not signing.code_matches(secret, "287082", moment + timedelta(seconds=600))
        assert not signing.code_matches(secret, "123456", moment)


class TestPasses:
    def test_a_pass_lives_inside_the_check_in_window_and_is_reused(self):
        booking = booked()
        early = at(booking.start_date - timedelta(days=5))
        first = pass_for(booking, now=early)
        opens, _ = services.check_in_window(booking)
        assert first.valid_from == opens
        assert first.valid_until == opens + timedelta(hours=48)
        assert pass_for(booking, now=early + timedelta(hours=1)).pk == first.pk

    def test_a_location_is_recorded(self):
        booking = booked()
        attendance_pass = pass_for(booking, metres_north=250)
        assert attendance_pass.located_at is not None and attendance_pass.accuracy_m == 15

    def test_only_confirmed_bookings_get_one(self):
        booking = booked()
        scan(booking)
        with pytest.raises(AttendanceError, match="already checked in"):
            pass_for(booking)


class TestCheckIn:
    def test_a_scanned_pass_checks_in(self):
        booking = booked()
        outcome = scan(booking, client_id=uuid.uuid4())
        booking.refresh_from_db()
        assert outcome.status == "applied" and booking.status == B.CHECKED_IN
        assert outcome.check_in.method == "qr" and outcome.check_in.recorded_by == booking.vendor
        assert AuditLog.objects.filter(action="attendance.checked_in").count() == 1

    def test_offline_check_ins_keep_their_scan_time_and_apply_once(self):
        booking = booked()
        scanned = at(booking.start_date, 9)
        attendance_pass = pass_for(booking, now=scanned - timedelta(hours=1))
        client_id = uuid.uuid4()
        later = scanned + timedelta(hours=5)
        event = {
            "client_id": client_id,
            "booking_id": booking.pk,
            "method": "qr",
            "token": services.token_for(attendance_pass),
            "scanned_at": scanned,
        }
        results = services.sync(booking.vendor, [event, event], now=later)
        assert [r["status"] for r in results] == ["applied", "duplicate"]
        record = CheckIn.objects.get()
        assert (record.checked_in_at, record.recorded_at) == (scanned, later)
        booking.refresh_from_db()
        assert booking.status_changed_at == scanned

    def test_two_devices_scanning_the_same_talent_check_in_once(self):
        booking = booked()
        attendance_pass = pass_for(booking)
        first = scan(booking, attendance_pass, client_id=uuid.uuid4())
        second = scan(booking, attendance_pass, client_id=uuid.uuid4())
        assert second.status == "duplicate" and second.check_in.pk == first.check_in.pk

    def test_the_six_digit_code_checks_in(self):
        booking = booked()
        when = at(booking.start_date)
        attendance_pass = pass_for(booking, now=when)
        with pytest.raises(AttendanceError, match="code isn't right"):
            services.check_in(
                vendor=booking.vendor,
                booking_id=booking.pk,
                method="code",
                code="000000",
                scanned_at=when,
                now=when,
            )
        code = signing.code_at(attendance_pass.code_secret, when)
        outcome = services.check_in(
            vendor=booking.vendor,
            booking_id=booking.pk,
            method="code",
            code=code,
            scanned_at=when,
            now=when,
        )
        assert outcome.check_in.method == "code"

    def test_by_hand_needs_a_reason(self):
        booking = booked()
        when = at(booking.start_date)
        with pytest.raises(AttendanceError, match="Say why"):
            services.check_in(
                vendor=booking.vendor,
                booking_id=booking.pk,
                method="manual",
                scanned_at=when,
                now=when,
            )
        outcome = services.check_in(
            vendor=booking.vendor,
            booking_id=booking.pk,
            method="manual",
            reason="Phone battery dead",
            scanned_at=when,
            now=when,
        )
        assert outcome.check_in.reason == "Phone battery dead"

    @pytest.mark.parametrize(
        ("change", "message"),
        [
            ({"scanned_at_offset": timedelta(minutes=10), "now_offset": timedelta(0)}, "future"),
            ({"scanned_at_offset": timedelta(0), "now_offset": timedelta(hours=73)}, "too long"),
        ],
    )
    def test_scan_times_are_checked(self, change, message):
        booking = booked()
        when = at(booking.start_date)
        attendance_pass = pass_for(booking, now=when)
        with pytest.raises(AttendanceError, match=message):
            services.check_in(
                vendor=booking.vendor,
                method="qr",
                token=services.token_for(attendance_pass),
                scanned_at=when + change["scanned_at_offset"],
                now=when + change["now_offset"],
            )

    def test_an_expired_or_foreign_pass_is_refused(self):
        booking, other = booked(), booked()
        stale = pass_for(booking, now=at(booking.start_date - timedelta(days=1), 1))
        with pytest.raises(AttendanceError, match="expired"):
            scan(booking, stale, when=stale.valid_until + timedelta(hours=1))
        foreign = pass_for(other)
        with pytest.raises(AttendanceError, match="different booking"):
            services.check_in(
                vendor=booking.vendor,
                booking_id=booking.pk,
                method="qr",
                token=services.token_for(foreign),
                scanned_at=at(booking.start_date),
                now=at(booking.start_date),
            )
        with pytest.raises(AttendanceError, match="isn't one of yours"):
            services.check_in(
                vendor=VendorFactory(),
                method="qr",
                token=services.token_for(foreign),
                scanned_at=at(other.start_date),
                now=at(other.start_date),
            )

    def test_the_bookings_rules_still_apply(self):
        booking = booked()
        too_early = at(booking.start_date - timedelta(days=3))
        attendance_pass = pass_for(booking, now=too_early)
        # A pass from a booking's own window, scanned before check-in opens: the
        # signature is fine, but the booking's check-in window refuses it.
        attendance_pass.valid_from = too_early - timedelta(hours=1)
        attendance_pass.save()
        with pytest.raises(AttendanceError, match="Check-in opens"):
            services.check_in(
                vendor=booking.vendor,
                method="qr",
                token=services.token_for(attendance_pass),
                scanned_at=too_early,
                now=too_early,
            )
        assert not CheckIn.objects.exists()

    def test_a_direct_status_change_still_gets_a_record(self):
        booking = booked()
        transition(
            booking.pk,
            B.CHECKED_IN,
            actor=Actor.VENDOR,
            user=booking.vendor,
            now=at(booking.start_date),
        )
        assert CheckIn.objects.get(booking=booking).method == "other"


class TestGeofence:
    def test_the_distance_is_recorded_and_far_ones_flagged(self):
        near, far = booked(), booked()
        scan(near, pass_for(near, metres_north=300))
        scan(far, pass_for(far, metres_north=5_000))
        near_record, far_record = (
            CheckIn.objects.get(booking=near),
            CheckIn.objects.get(booking=far),
        )
        assert 280 <= near_record.distance_m <= 320 and near_record.flag == ""
        assert 4_900 <= far_record.distance_m <= 5_100 and far_record.flag == "far"
        assert far_record.location_age_minutes == 60
        far.refresh_from_db()
        assert far.status == B.CHECKED_IN  # flagged, not blocked

    def test_no_location_no_distance(self):
        booking = booked()
        assert scan(booking).check_in.distance_m is None

    def test_admins_review_flagged_check_ins(self):
        sync_roles()
        reviewer = AdminUserFactory()
        reviewer.groups.add(Group.objects.get(name=AdminRole.OPS))
        booking = booked()
        record = scan(booking, pass_for(booking, metres_north=5_000)).check_in
        listed = client_for(reviewer).get(reverse("attendance:flagged")).json()
        assert [r["id"] for r in listed["results"]] == [str(record.pk)]
        assert client_for(AdminUserFactory()).get(reverse("attendance:flagged")).status_code == 403
        url = reverse("attendance:flag-review", args=[record.pk])
        assert (
            client_for(reviewer)
            .post(url, {"note": "Parked at the station"}, format="json")
            .status_code
            == 200
        )
        assert client_for(reviewer).get(reverse("attendance:flagged")).json()["count"] == 0


class TestCheckOutAndNoShow:
    def test_check_out_ends_the_stay(self):
        booking = booked()
        scan(booking)
        record = services.check_out(
            booking.pk, vendor=booking.vendor, now=at(booking.start_date + timedelta(days=5))
        )
        booking.refresh_from_db()
        assert booking.status == B.COMPLETED and record.checked_out_at is not None
        with pytest.raises(AttendanceError, match="Only someone checked in"):
            services.check_out(booking.pk, vendor=booking.vendor)

    def test_a_no_show_waits_for_the_grace_period_then_counts(self):
        booking = booked()
        with pytest.raises(AttendanceError, match="Give them until"):
            services.no_show(
                booking.pk, vendor=booking.vendor, reason="Not here", now=at(booking.start_date, 12)
            )
        services.no_show(
            booking.pk, vendor=booking.vendor, reason="Not here", now=at(booking.start_date, 19)
        )
        booking.refresh_from_db()
        assert booking.status == B.NO_SHOW
        score = ReliabilityScore.objects.get(user=booking.talent, side="talent")
        assert score.inputs["no_shows"] == 1


class TestApi:
    def test_the_talent_gets_a_pass(self):
        booking = booked()
        url = reverse("attendance:pass", args=[booking.pk])
        body = (
            client_for(booking.talent)
            .post(
                url,
                {"location": {"latitude": "15.5", "longitude": "73.8", "accuracy_m": 20}},
                format="json",
            )
            .json()
        )
        assert signing.verify(body["token"])["b"] == str(booking.pk)
        assert body["code_period_seconds"] == 300 and len(body["code_secret"]) >= 16
        assert client_for(booking.vendor).post(url, {}, format="json").status_code == 403
        assert AttendancePass.objects.get().located_at is not None

    def test_the_host_gets_arrivals_and_checks_in_offline(self):
        booking = booked()
        client = client_for(booking.vendor)
        day = booking.start_date.isoformat()
        data = client.get(reverse("attendance:arrivals"), {"date": day}).json()
        assert [a["booking_id"] for a in data["arrivals"]] == [str(booking.pk)]
        assert data["public_keys"][0]["alg"] == "Ed25519"
        arrival = data["arrivals"][0]
        assert arrival["code_secret"] and arrival["no_show_from"]
        attendance_pass = AttendancePass.objects.get(pk=arrival["pass_id"])
        event = {
            "client_id": str(uuid.uuid4()),
            "method": "qr",
            "token": services.token_for(attendance_pass),
        }
        results = client.post(
            reverse("attendance:sync"), {"events": [event]}, format="json"
        ).json()["results"]
        assert results[0]["status"] in ("applied", "refused")
        if results[0]["status"] == "refused":  # outside today's window: the reason is given
            assert results[0]["message"]

    def test_check_in_check_out_and_no_show_endpoints(self):
        booking = booked()
        client = client_for(booking.vendor)
        attendance_pass = pass_for(booking, now=timezone.now())
        response = client.post(
            reverse("attendance:check-in"),
            {"client_id": str(uuid.uuid4()), "method": "manual", "reason": "x"},
            format="json",
        )
        assert response.status_code == 400  # manual needs booking_id
        assert attendance_pass.booking_id == booking.pk
        assert client.post(reverse("attendance:check-out", args=[booking.pk])).status_code == 409
        assert (
            client_for(booking.talent)
            .post(reverse("attendance:no-show", args=[booking.pk]), {"reason": "x"}, format="json")
            .status_code
            == 403
        )
        assert (
            client_for(booking.talent)
            .get(reverse("attendance:record", args=[booking.pk]))
            .status_code
            == 404
        )
        assert client.get(reverse("attendance:keys")).json()[0]["kid"]
