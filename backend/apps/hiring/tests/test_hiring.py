import json
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from apps.accounts.tests.factories import VendorFactory
from apps.applications.constants import ApplicationStatus as A
from apps.applications.models import Application
from apps.applications.services import apply
from apps.applications.tests.helpers import dates, eligible_talent, live_gig
from apps.bookings import jobs
from apps.hiring import services
from apps.hiring.models import Interview, InterviewStatus
from apps.notifications.models import Notification
from apps.offers.tests.helpers import make_offer_for
from apps.profiles.tests.factories import SkillFactory
from apps.verification.tests.factories import client_for

pytestmark = pytest.mark.django_db
IST = ZoneInfo("Asia/Kolkata")


def applied(gig=None, talent=None, **overrides):
    gig = gig or live_gig()
    return apply(
        talent or eligible_talent(),
        gig.pk,
        pitch="Three seasons at hostels.",
        answers=[],
        attachments=[],
        **{**dates(), **overrides},
    )


def at(days: int, hour: int, minute: int = 0) -> datetime:
    """A time `days` from today, in India time."""
    day = timezone.localdate() + timedelta(days=days)
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=IST)


class TestStatusMoves:
    def test_reject_needs_a_reason_and_the_applicant_reads_it(self):
        application = applied()
        vendor = client_for(application.gig.vendor)
        url = f"/api/v1/applications/{application.pk}/status/"
        assert vendor.post(url, {"status": "rejected"}, format="json").status_code == 400
        done = vendor.post(
            url,
            {
                "status": "rejected",
                "reason_code": "dates",
                "message": "We need someone by the 5th.",
            },
            format="json",
        )
        assert done.status_code == 200, done.json()
        assert done.json()["rejection_code"] == "dates"

        mine = client_for(application.talent).get(f"/api/v1/applications/{application.pk}/").json()
        assert mine["status"] == "rejected"
        assert mine["status_reason"] == (
            "Your dates don't work for this gig. Message from the host: We need someone by the 5th."
        )
        assert [step["status"] for step in mine["timeline"]] == ["applied", "rejected"]
        assert "rejection_code" not in mine
        assert Notification.objects.filter(
            user=application.talent, kind="application.rejected"
        ).exists()

    def test_shortlist_and_move_to_interview(self):
        application = applied()
        vendor = client_for(application.gig.vendor)
        url = f"/api/v1/applications/{application.pk}/status/"
        assert (
            vendor.post(url, {"status": "shortlisted"}, format="json").json()["status"]
            == "shortlisted"
        )
        assert (
            vendor.post(url, {"status": "interview"}, format="json").json()["status"] == "interview"
        )

    def test_reasons_list(self):
        reasons = client_for(VendorFactory()).get("/api/v1/hiring/rejection-reasons/").json()
        assert [r["code"] for r in reasons] == [
            "not_a_fit",
            "dates",
            "filled",
            "language",
            "incomplete",
            "other",
        ]

    def test_bulk_reports_each_result(self):
        gig = live_gig()
        first, second, done = applied(gig), applied(gig), applied(gig)
        services.reject(done.pk, user=gig.vendor, code="filled")
        elsewhere = applied()
        vendor = client_for(gig.vendor)
        url = f"/api/v1/gigs/{gig.pk}/applications/bulk/"
        ids = [str(first.pk), str(second.pk), str(done.pk), str(elsewhere.pk)]
        assert (
            vendor.post(
                url, {"action": "reject", "application_ids": ids}, format="json"
            ).status_code
            == 400
        )
        results = vendor.post(
            url,
            {"action": "reject", "application_ids": ids, "reason_code": "not_a_fit"},
            format="json",
        ).json()
        assert [r["ok"] for r in results] == [True, True, False, False]
        assert results[2]["error"] == "Can't go from rejected to rejected."
        assert results[3]["error"] == "No such application on this gig."
        assert Application.objects.get(pk=first.pk).rejection_code == "not_a_fit"
        assert (
            client_for(VendorFactory())
            .post(url, {"action": "shortlist", "application_ids": ids}, format="json")
            .status_code
            == 404
        )


class TestAutoReject:
    def test_rules_are_validated(self):
        gig = live_gig()
        vendor = client_for(gig.vendor)
        url = f"/api/v1/gigs/{gig.pk}/auto-reject-rules/"
        assert (
            vendor.put(
                url, {"rules": [{"type": "language", "languages": ["xx"]}]}, format="json"
            ).status_code
            == 400
        )
        assert (
            vendor.put(
                url, {"rules": [{"type": "skill", "skills": ["nope"]}]}, format="json"
            ).status_code
            == 400
        )
        ok = vendor.put(
            url,
            {
                "rules": [
                    {"type": "language", "languages": ["ta"]},
                    {"type": "min_stay_days", "value": 30},
                ]
            },
            format="json",
        )
        assert ok.status_code == 200
        assert vendor.get(url).json()["rules"][0] == {"type": "language", "languages": ["ta"]}

    def test_a_missed_rule_rejects_on_submit_and_says_why(self):
        SkillFactory(slug="photography", name="Photography")
        gig = live_gig()
        gig.auto_reject_rules = [
            {"type": "language", "languages": ["ta"]},
            {"type": "skill", "skills": ["photography"]},
        ]
        gig.save()
        application = applied(gig)  # speaks en and hi, no photography
        assert application.status == A.REJECTED
        assert application.rejection_code == "auto_rule"
        assert application.status_reason == (
            "Your application didn't meet the host's requirements: This host is looking for "
            "someone who speaks Tamil; and who has the skill photography on their profile."
        )
        assert Notification.objects.filter(
            user=application.talent, kind="application.rejected"
        ).exists()

    def test_meeting_the_rules_goes_through(self):
        gig = live_gig()
        gig.auto_reject_rules = [
            {"type": "language", "languages": ["hi"]},
            {"type": "min_stay_days", "value": 10},
        ]
        gig.save()
        assert applied(gig).status == A.APPLIED


class TestPrivateNotesAndTags:
    def test_vendor_sees_them_and_the_applicant_never_does(self):
        application = applied()
        vendor = client_for(application.gig.vendor)
        base = f"/api/v1/applications/{application.pk}"
        note = vendor.post(f"{base}/notes/", {"body": "SECRET-NOTE great energy"}, format="json")
        assert note.status_code == 201
        assert vendor.put(
            f"{base}/tags/", {"tags": ["SECRET-TAG", "Night shift "]}, format="json"
        ).json() == {"tags": ["night shift", "secret-tag"]}
        detail = vendor.get(f"{base}/").json()
        assert detail["tags"] == ["night shift", "secret-tag"]
        assert detail["notes"][0]["body"] == "SECRET-NOTE great energy"

        talent = client_for(application.talent)
        for url in (f"{base}/", "/api/v1/applications/mine/"):
            text = json.dumps(talent.get(url).json()).lower()
            assert "secret-note" not in text and "secret-tag" not in text, url
        assert talent.get(f"{base}/notes/").status_code == 403
        assert talent.put(f"{base}/tags/", {"tags": ["x"]}, format="json").status_code == 403
        assert client_for(VendorFactory()).get(f"{base}/notes/").status_code == 404

        vendor.delete(f"{base}/notes/{note.json()['id']}/")
        assert vendor.get(f"{base}/notes/").json() == []

    def test_list_filters_by_tag_and_shows_counts(self):
        gig = live_gig()
        tagged, other = applied(gig), applied(gig)
        services.set_tags(tagged, ["call back"])
        services.add_note(tagged, author=gig.vendor, body="Good")
        vendor = client_for(gig.vendor)
        rows = vendor.get(f"/api/v1/gigs/{gig.pk}/applications/", {"tag": "Call Back"}).json()[
            "results"
        ]
        assert [r["id"] for r in rows] == [str(tagged.pk)]
        assert rows[0]["tags"] == ["call back"] and rows[0]["note_count"] == 1
        assert len(vendor.get(f"/api/v1/gigs/{gig.pk}/applications/").json()["results"]) == 2
        assert other

    def test_list_searches_names_and_filters_by_badge(self):
        from apps.verification.models import Badge

        gig = live_gig()
        riya = applied(gig, eligible_talent(display_name="Riya Sharma"))
        kabir = applied(gig, eligible_talent(display_name="Kabir Rana"))
        Badge.objects.filter(user=kabir.talent).update(
            revoked_at=timezone.now(), revoke_reason="test"
        )
        vendor = client_for(gig.vendor)
        url = f"/api/v1/gigs/{gig.pk}/applications/"
        assert [r["id"] for r in vendor.get(url, {"q": "riya"}).json()["results"]] == [str(riya.pk)]
        verified = vendor.get(url, {"badge": "id_verified"}).json()["results"]
        assert [r["id"] for r in verified] == [str(riya.pk)]
        assert vendor.get(url, {"badge": "nope"}).status_code == 400

    def test_saved_filters(self):
        gig = live_gig()
        vendor = client_for(gig.vendor)
        body = {
            "name": "Strong",
            "gig": str(gig.pk),
            "params": {"min_score": 70, "tag": "call back", "q": "ri", "badge": "id_verified"},
        }
        saved = vendor.post("/api/v1/applicant-filters/", body, format="json")
        assert saved.status_code == 201, saved.json()
        assert vendor.post("/api/v1/applicant-filters/", body, format="json").status_code == 400
        assert vendor.get("/api/v1/applicant-filters/").json()[0]["params"] == {
            "min_score": 70,
            "tag": "call back",
            "q": "ri",
            "badge": "id_verified",
        }
        other_gig = {"name": "Theirs", "gig": str(live_gig().pk), "params": {}}
        assert (
            vendor.post("/api/v1/applicant-filters/", other_gig, format="json").status_code == 400
        )
        assert (
            client_for(VendorFactory())
            .get(f"/api/v1/applicant-filters/{saved.json()['id']}/")
            .status_code
            == 404
        )
        assert vendor.delete(f"/api/v1/applicant-filters/{saved.json()['id']}/").status_code == 204


class TestInterviews:
    def propose(self, application, slots, **extra):
        return client_for(application.gig.vendor).post(
            f"/api/v1/applications/{application.pk}/interview/",
            {"slots": slots, "video_link": "https://meet.google.com/abc-defg-hij", **extra},
            format="json",
        )

    def test_vendor_proposes_talent_picks_times_in_utc_and_ist(self):
        application = applied()
        naive_ist = at(3, 16, 30).replace(tzinfo=None).isoformat()  # read as India time
        response = self.propose(application, [naive_ist, at(4, 10).isoformat()])
        assert response.status_code == 201, response.json()
        interview = response.json()
        first = interview["slots"][0]
        expected_utc = at(3, 16, 30).astimezone(UTC)
        assert first["starts_at"] == expected_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        assert first["starts_at_ist"].endswith("4:30 PM IST")
        assert interview["video_link"] == ""  # not until a time is picked
        assert interview["timezone"] == "Asia/Kolkata"
        application.refresh_from_db()
        assert application.status == A.INTERVIEW
        assert Notification.objects.filter(
            user=application.talent, kind="interview.proposed"
        ).exists()

        talent = client_for(application.talent)
        picked = talent.post(
            f"/api/v1/applications/{application.pk}/interview/pick/",
            {"slot_id": first["id"]},
            format="json",
        )
        assert picked.status_code == 200, picked.json()
        assert picked.json()["status"] == "scheduled"
        assert picked.json()["video_link"] == "https://meet.google.com/abc-defg-hij"
        stored = Interview.objects.get(pk=interview["id"])
        assert stored.starts_at == expected_utc  # stored in UTC
        kinds = set(
            Notification.objects.filter(kind="interview.scheduled").values_list(
                "user_id", flat=True
            )
        )
        assert kinds == {application.talent_id, application.gig.vendor_id}
        mine = talent.get(f"/api/v1/applications/{application.pk}/").json()
        assert mine["interview"]["status"] == "scheduled"

    def test_slot_rules(self):
        application = applied()
        assert self.propose(application, []).status_code == 400
        four = [at(d, 10).isoformat() for d in (2, 3, 4, 5)]
        assert self.propose(application, four).status_code == 400
        soon = (timezone.now() + timedelta(minutes=20)).isoformat()
        assert "too soon" in self.propose(application, [soon]).json()["message"]
        assert "60 days" in self.propose(application, [at(70, 10).isoformat()]).json()["message"]
        same = [at(2, 10).isoformat(), at(2, 10).isoformat()]
        assert "different" in self.propose(application, same).json()["message"]
        bad_link = self.propose(
            application, [at(2, 10).isoformat()], video_link="http://meet.example"
        )
        assert bad_link.status_code == 409
        assert (
            client_for(VendorFactory())
            .post(
                f"/api/v1/applications/{application.pk}/interview/",
                {"slots": [at(2, 10).isoformat()], "video_link": "https://meet.google.com/x"},
                format="json",
            )
            .status_code
            == 404
        )

    def test_new_times_cancel_and_reproposing(self):
        application = applied()
        self.propose(application, [at(2, 10).isoformat()])
        talent = client_for(application.talent)
        asked = talent.post(
            f"/api/v1/applications/{application.pk}/interview/new-times/",
            {"note": "Evenings?"},
            format="json",
        )
        assert asked.json()["status"] == "new_times_requested"
        again = self.propose(application, [at(2, 19).isoformat()])
        assert again.status_code == 201
        assert Interview.objects.filter(application=application).count() == 2
        assert (
            Interview.objects.filter(
                application=application, status=InterviewStatus.CANCELLED
            ).count()
            == 1
        )
        cancelled = client_for(application.gig.vendor).post(
            f"/api/v1/applications/{application.pk}/interview/cancel/", {}, format="json"
        )
        assert cancelled.json()["status"] == "cancelled"

    def test_moving_past_interview_closes_it(self):
        application = applied()
        self.propose(application, [at(2, 10).isoformat()])
        make_offer_for(application)
        assert Interview.objects.get(application=application).status == InterviewStatus.CANCELLED


class TestReminders:
    def scheduled(self, starts_at):
        application = applied()
        interview = services.propose_interview(
            application.pk,
            vendor=application.gig.vendor,
            slots=[starts_at],
            video_link="https://meet.google.com/abc",
            now=starts_at - timedelta(days=5),
        )
        return services.pick_slot(
            application.pk,
            interview.slots.get().pk,
            talent=application.talent,
            now=starts_at - timedelta(days=5),
        )

    def test_a_day_before_then_an_hour_before_each_once(self):
        starts = at(10, 15)
        interview = self.scheduled(starts)
        assert services.send_reminders(starts - timedelta(days=2)) == {"day": 0, "hour": 0}
        assert services.send_reminders(starts - timedelta(hours=20)) == {"day": 1, "hour": 0}
        assert services.send_reminders(starts - timedelta(hours=19)) == {"day": 0, "hour": 0}
        assert services.send_reminders(starts - timedelta(minutes=50)) == {"day": 0, "hour": 1}
        assert services.send_reminders(starts - timedelta(minutes=10)) == {"day": 0, "hour": 0}
        day = Notification.objects.filter(kind="interview.reminder_day")
        assert set(day.values_list("user_id", flat=True)) == {
            interview.application.talent_id,
            interview.application.gig.vendor_id,
        }
        assert day.first().payload["starts_at_ist"].endswith("3:00 PM IST")
        assert Notification.objects.filter(kind="interview.reminder_hour").count() == 2

    def test_picked_at_the_last_minute_gets_only_the_hour_reminder(self):
        starts = at(10, 15)
        self.scheduled(starts)
        assert services.send_reminders(starts - timedelta(minutes=40)) == {"day": 0, "hour": 1}
        assert not Notification.objects.filter(kind="interview.reminder_day").exists()

    def test_runs_as_a_scheduled_job(self):
        assert jobs.run("send_interview_reminders").result == {"day": 0, "hour": 0}

    def test_an_upcoming_interview_is_not_stale(self):
        interview = self.scheduled(timezone.now() + timedelta(days=2))
        Application.objects.filter(pk=interview.application_id).update(
            status_changed_at=timezone.now() - timedelta(days=9)
        )
        assert jobs.flag_stale_interviews(timezone.now()) == {"flagged": 0}
