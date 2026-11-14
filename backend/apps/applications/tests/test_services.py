from datetime import timedelta

import pytest
from django.db import IntegrityError, transaction

from apps.accounts.tests.factories import TalentFactory
from apps.applications.constants import ACTIVE, TRANSITIONS, Actor, ApplicationStatus
from apps.applications.models import Application
from apps.applications.services import (
    NEW_APPLICATION_KIND,
    ApplicationBlocked,
    AttachmentInput,
    InvalidApplicationTransition,
    apply,
    transition,
    withdraw,
)
from apps.applications.tests.helpers import dates, eligible_talent, live_gig
from apps.common.models import AuditLog
from apps.gigs.constants import GigStatus, RequiredVerification
from apps.notifications.models import Notification
from apps.profiles.models import TalentProfile
from apps.profiles.tests.factories import SkillFactory, TalentProfileFactory
from apps.verification.tests.factories import MediaFileFactory

pytestmark = pytest.mark.django_db
S = ApplicationStatus


def do_apply(talent, gig, **overrides):
    kwargs = {
        "pitch": "I run reels for three hostels.",
        "answers": [],
        "attachments": [],
        **dates(),
    }
    kwargs.update(overrides)
    return apply(talent, gig.pk, **kwargs)


def reasons(talent, gig, **overrides) -> set[str]:
    with pytest.raises(ApplicationBlocked) as exc:
        do_apply(talent, gig, **overrides)
    return {r.code for r in exc.value.reasons}


def test_apply_snapshots_fit_audits_and_notifies_the_vendor():
    cooking = SkillFactory(slug="cooking")
    talent = eligible_talent()
    talent.talent_profile.skills.set([cooking])
    gig = live_gig(screening_questions=["Why us?"])
    gig.skills.set([cooking])
    photo = MediaFileFactory(owner=talent)

    application = do_apply(
        talent,
        gig,
        answers=["The mountains."],
        attachments=[
            AttachmentInput(kind="photo", media_id=str(photo.pk), title="Last mural"),
            AttachmentInput(kind="link", url="https://example.org/portfolio"),
        ],
    )
    assert application.status == S.APPLIED
    assert application.answers == [{"question": "Why us?", "answer": "The mountains."}]
    assert application.fit_score > 50
    assert application.fit_breakdown["skill_match"]["reason"] == "1 of 1 skills match."
    assert [a.kind for a in application.attachments.all()] == ["photo", "link"]
    assert AuditLog.objects.get(action="application.applied").actor == talent
    note = Notification.objects.get()
    assert note.user == gig.vendor and note.kind == NEW_APPLICATION_KIND
    assert note.payload["application_id"] == str(application.pk)


def test_every_blocking_reason_is_reported_together():
    talent = TalentProfileFactory(bare=True, languages=["fr"]).user  # incomplete, no ID badge
    gig = live_gig(
        languages=["hi"],
        min_followers=10_000,
        min_stay_days=20,
        screening_questions=["Q1", "Q2"],
    )
    got = reasons(talent, gig, **dates(32, 40), answers=["only one"])
    assert got == {
        "profile_incomplete",
        "verification_required",
        "language_mismatch",
        "not_enough_followers",
        "stay_too_short",
        "answers_missing",
    }
    assert not Application.objects.exists()
    assert not Notification.objects.exists()


@pytest.mark.parametrize(
    ("gig_kwargs", "code"),
    [
        ({"status": GigStatus.PAUSED}, "gig_not_open"),
        ({"required_verification": RequiredVerification.TRUSTED_MEMBER}, "verification_required"),
    ],
)
def test_gig_side_reasons(gig_kwargs, code):
    assert code in reasons(eligible_talent(), live_gig(**gig_kwargs))


def test_dates_must_sit_inside_the_gig():
    talent, gig = eligible_talent(), live_gig()
    assert "dates_outside_gig" in reasons(talent, gig, **dates(25, 40))
    assert "dates_outside_gig" in reasons(talent, gig, **dates(40, 70))
    assert "dates_invalid" in reasons(talent, gig, **dates(40, 35))


def test_requirements_are_waived_when_the_gig_asks_for_none():
    talent = TalentProfileFactory(languages=["en"]).user  # complete but unverified
    gig = live_gig(required_verification=RequiredVerification.NONE)
    assert do_apply(talent, gig).status == S.APPLIED


def test_own_gig_and_non_talent_are_refused():
    talent = eligible_talent()
    gig = live_gig()
    gig.vendor = talent  # a vendor can't hold the talent role; the rule still guards it
    gig.save(update_fields=["vendor"])
    assert "own_gig" in reasons(talent, gig)
    assert "not_talent" in reasons(gig.property.vendor, live_gig())


def test_must_be_18_when_the_gig_starts():
    talent, gig = eligible_talent(), live_gig()
    born = gig.start_date.replace(year=gig.start_date.year - 18) + timedelta(days=1)
    TalentProfile.objects.filter(user=talent).update(date_of_birth=born)
    assert "under_age" in reasons(talent, gig)


def test_unusable_attachments_are_a_reason():
    talent, gig = eligible_talent(), live_gig()
    someone_elses = MediaFileFactory(owner=TalentFactory())
    wrong_kind = MediaFileFactory(owner=talent, kind="document")
    got = reasons(
        talent,
        gig,
        attachments=[
            AttachmentInput(kind="photo", media_id=str(someone_elses.pk)),
            AttachmentInput(kind="photo", media_id=str(wrong_kind.pk)),
        ],
    )
    assert got == {"attachment_unusable"}


def test_one_active_application_per_gig_and_reapply_after_withdrawing():
    talent, gig = eligible_talent(), live_gig()
    first = do_apply(talent, gig)
    assert reasons(talent, gig) == {"already_applied"}
    withdraw(first.pk, talent=talent, reason="Dates changed")
    second = do_apply(talent, gig)
    assert second.pk != first.pk
    with pytest.raises(IntegrityError), transaction.atomic():
        Application.objects.create(
            gig=gig, talent=talent, pitch="x", fit_score=50, fit_breakdown={}, **dates()
        )


class TestTransitions:
    def test_withdraw_any_time_until_offer_accepted(self):
        for status in sorted(ACTIVE):
            assert TRANSITIONS[(status, S.WITHDRAWN)] == {Actor.TALENT}
        talent, gig = eligible_talent(), live_gig()
        application = do_apply(talent, gig)
        transition(application.pk, S.SHORTLISTED, actor=Actor.VENDOR, user=gig.vendor)
        transition(application.pk, S.OFFERED, actor=Actor.VENDOR, user=gig.vendor)
        application = withdraw(application.pk, talent=talent)
        assert application.status == S.WITHDRAWN and application.decided_at
        entry = AuditLog.objects.filter(action="application.withdrawn").get()
        assert entry.before["status"] == "offered" and entry.after["by"] == "talent"

    def test_final_statuses_stay_final_and_actors_are_checked(self):
        talent, gig = eligible_talent(), live_gig()
        application = do_apply(talent, gig)
        with pytest.raises(InvalidApplicationTransition):
            transition(application.pk, S.WITHDRAWN, actor=Actor.VENDOR)
        with pytest.raises(InvalidApplicationTransition):
            transition(application.pk, S.DECLINED, actor=Actor.TALENT)  # no offer yet
        withdraw(application.pk, talent=talent)
        with pytest.raises(InvalidApplicationTransition):
            withdraw(application.pk, talent=talent)
        final = {S.WITHDRAWN, S.DECLINED, S.REJECTED, S.EXPIRED}
        assert not [pair for pair in TRANSITIONS if pair[0] in final]

    def test_only_the_applicant_can_withdraw(self):
        application = do_apply(eligible_talent(), live_gig())
        with pytest.raises(Application.DoesNotExist):
            withdraw(application.pk, talent=eligible_talent())
