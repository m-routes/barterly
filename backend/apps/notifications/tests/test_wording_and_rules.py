"""Templates, the event catalog, preferences and quiet hours. Mostly pure."""

from datetime import datetime, time
from zoneinfo import ZoneInfo

import pytest

from apps.notifications import catalog, templates
from apps.notifications.models import Channel, NotificationSettings
from apps.notifications.services import quiet_until

IST = ZoneInfo("Asia/Kolkata")
SAMPLE = {
    "gig_title": "Front desk, Manali",
    "applicant_name": "Riya",
    "starts_at_ist": "Tue 18 Nov, 4:00 pm",
    "hours_left": 6,
    "version": 2,
    "sender_name": "Asha",
    "preview": "See you Monday",
    "saved_search_name": "Goa hostels",
    "count": 3,
}


@pytest.mark.parametrize("kind", sorted(templates.TEMPLATES))
@pytest.mark.parametrize("locale", ["en", "hi"])
def test_every_template_renders_in_both_languages(kind, locale):
    title, body = templates.render(kind, SAMPLE, locale)
    assert title.strip() and body.strip()
    assert "{" not in title + body
    raw_title, raw_body = templates.TEMPLATES[kind][locale]
    used = templates.used_variables(raw_title) | templates.used_variables(raw_body)
    assert used <= set(templates.VARIABLES[kind]), "a template uses an unlisted variable"


def test_hindi_is_hindi_and_english_is_english():
    en = templates.render("application.offered", SAMPLE, "en")
    hi = templates.render("application.offered", SAMPLE, "hi")
    assert en == ("You have an offer", "Front desk, Manali: answer within 48 hours.")
    assert hi[0] == "आपको ऑफ़र मिला है" and "48 घंटे" in hi[1]


def test_other_updates_use_the_generic_template_with_their_label():
    assert templates.render("booking.checked_in", SAMPLE, "en") == (
        "Checked in",
        "Front desk, Manali",
    )
    assert templates.render("booking.checked_in", SAMPLE, "hi")[0] == "चेक-इन हुआ"


def test_a_missing_variable_reads_as_empty_rather_than_failing():
    _, body = templates.render("offer.expiring", {"gig_title": "X"}, "en")
    assert body == "X:  hours left to answer."


def test_whatsapp_gets_an_approved_template_name_and_ordered_variables():
    assert templates.whatsapp_template("offer.expiring", "hi") == "barterly_offer_expiring_hi"
    assert templates.whatsapp_variables("offer.expiring", SAMPLE, "en") == [
        "Front desk, Manali",
        "6",
    ]
    assert templates.whatsapp_template("booking.checked_in", "en") == "barterly_other_en"


class TestCatalog:
    def test_aliases_share_their_types_settings(self):
        assert catalog.type_for("interview.reminder_hour").key == "reminder"
        assert catalog.type_for("agreement.sign_reminder").key == "agreement.ready"
        assert catalog.type_for("offer.reopened").key == "application.offered"
        assert catalog.type_for("booking.disputed").key == "other"

    def test_urgency(self):
        assert catalog.is_urgent("offer.expiring")
        assert catalog.is_urgent("interview.reminder_hour")
        assert not catalog.is_urgent("interview.reminder_day")
        assert not catalog.is_urgent("chat.message")

    def test_preferences_change_the_defaults_but_in_app_stays_on(self):
        assert catalog.enabled_channels("chat.message", {}) == {"in_app", "push"}
        overrides = {
            ("chat.message", "push"): False,
            ("chat.message", "email"): True,
            ("chat.message", "in_app"): False,
        }
        assert catalog.enabled_channels("chat.message", overrides) == {"in_app", "email"}
        reminder = {("reminder", "push"): False}
        assert "push" not in catalog.enabled_channels("interview.reminder_day", reminder)

    @pytest.mark.parametrize(
        ("kind", "side", "payload", "app", "web"),
        [
            ("application.applied", "vendor", {"application_id": "a1"}, "/trips",
             "https://web.test/console/applicants/a1"),
            ("application.offered", "talent", {"application_id": "a1"}, "/trips/offer/a1",
             "https://web.test/console/applicants/a1"),
            ("offer.expiring", "talent", {"application_id": "a1"}, "/trips/offer/a1",
             "https://web.test/console/applicants/a1"),
            ("agreement.ready", "talent", {"agreement_id": "ag1"}, "/trips/agreement/ag1",
             "https://web.test/console/agreements/ag1"),
            ("booking.confirmed", "vendor", {"agreement_id": "ag1", "booking_id": "b1"},
             "/trips/agreement/ag1", "https://web.test/console/agreements/ag1"),
            ("chat.message", "talent", {"conversation_id": "c1", "application_id": "a1"},
             "/trips/chat/c1", "https://web.test/console/messages/c1"),
            ("interview.scheduled", "vendor", {"application_id": "a1"}, "/trips",
             "https://web.test/console/applicants/a1"),
            ("gigs.search_alert", "talent", {}, "/discover", "https://web.test/talent"),
        ],
    )  # fmt: skip
    def test_deep_links(self, kind, side, payload, app, web):
        assert catalog.links(kind, side, payload) == (app, web)


class TestQuietHours:
    def prefs(self, **kw):
        return NotificationSettings(**{"quiet_start": time(22), "quiet_end": time(8), **kw})

    def test_across_midnight(self):
        prefs = self.prefs()
        late = datetime(2026, 11, 16, 23, 30, tzinfo=IST)
        early = datetime(2026, 11, 17, 6, 0, tzinfo=IST)
        assert quiet_until(prefs, late) == datetime(2026, 11, 17, 8, 0, tzinfo=IST)
        assert quiet_until(prefs, early) == datetime(2026, 11, 17, 8, 0, tzinfo=IST)
        assert quiet_until(prefs, datetime(2026, 11, 17, 8, 0, tzinfo=IST)) is None
        assert quiet_until(prefs, datetime(2026, 11, 17, 14, 0, tzinfo=IST)) is None

    def test_within_one_day_and_switched_off(self):
        prefs = self.prefs(quiet_start=time(13), quiet_end=time(15))
        assert quiet_until(prefs, datetime(2026, 11, 17, 14, 0, tzinfo=IST)) == datetime(
            2026, 11, 17, 15, 0, tzinfo=IST
        )
        off = self.prefs(quiet_hours_enabled=False)
        assert quiet_until(off, datetime(2026, 11, 16, 23, 30, tzinfo=IST)) is None
        same = self.prefs(quiet_start=time(9), quiet_end=time(9))
        assert quiet_until(same, datetime(2026, 11, 16, 9, 30, tzinfo=IST)) is None

    def test_utc_times_are_read_in_india_time(self):
        from datetime import UTC

        # 17:00 UTC is 22:30 in India.
        assert quiet_until(self.prefs(), datetime(2026, 11, 16, 17, 0, tzinfo=UTC)) == datetime(
            2026, 11, 17, 8, 0, tzinfo=IST
        )


def test_channel_choices_cover_every_provider_setting(settings):
    assert set(settings.NOTIFICATION_PROVIDERS) == set(Channel.values) - {"in_app"}
