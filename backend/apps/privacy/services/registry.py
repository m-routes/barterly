"""What a person's data is, for export and erasure.

EXPORT_SECTIONS lists every table we hand back in an export, and how each one leads to
the person. UNEXPORTED_LINKS lists the user links we deliberately leave out, with why.
apps/privacy/tests/test_registry.py fails when a model gains a user link that is in
neither, so a new table can't quietly escape export or erasure.

Other apps add their own tables from AppConfig.ready() with register_section() and
register_unexported(), and their erasure step with erasure.register_anonymiser().
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Section:
    name: str  # key in the export file
    model: str  # "app_label.ModelName"
    path: str  # lookup from the model to the user, e.g. "talent" or "case__user"
    exclude: tuple[str, ...] = ()  # internal or secret fields never exported
    only_if: dict = field(default_factory=dict)  # extra filter


# Fields that are internal to us or are secrets: never exported, whatever the table.
ALWAYS_EXCLUDED = frozenset(
    {
        "password",
        "object_key",
        "pdf_key",
        "idempotency_key",
        "code_secret",
        "token",
        "checksum_md5",
        "variants",
    }
)

EXPORT_SECTIONS: list[Section] = [
    Section("talent_profile", "profiles.TalentProfile", "user"),
    Section("vendor_profile", "profiles.VendorProfile", "user"),
    Section("consents", "privacy.ConsentRecord", "user"),
    Section("data_exports", "privacy.DataExport", "user"),
    Section("deletion_requests", "privacy.DeletionRequest", "user"),
    Section("correction_requests", "privacy.CorrectionRequest", "user", ("resolved_by",)),
    Section("age_checks", "privacy.MinorCase", "user", ("decided_by", "restriction")),
    Section("uploads", "media.MediaFile", "owner"),
    Section("properties", "properties.Property", "vendor"),
    Section("property_photos", "properties.PropertyPhoto", "property__vendor"),
    Section("verification_cases", "verification.VerificationCase", "user", ("reviewer",)),
    Section(
        "verification_documents",
        "verification.VerificationDocument",
        "case__user",
        ("provider_reference",),
    ),
    Section("badges", "verification.Badge", "user", ("granted_by", "revoked_by")),
    Section("gigs", "gigs.Gig", "vendor"),
    Section("saved_searches", "discovery.SavedSearch", "talent"),
    Section("notifications", "notifications.Notification", "user"),
    Section("notification_settings", "notifications.NotificationSettings", "user"),
    Section("notification_preferences", "notifications.NotificationPreference", "user"),
    Section("push_devices", "notifications.PushDevice", "user"),
    Section("applications", "applications.Application", "talent"),
    Section("application_attachments", "applications.ApplicationAttachment", "application__talent"),
    Section("bookings_as_talent", "bookings.Booking", "talent"),
    Section("bookings_as_host", "bookings.Booking", "vendor"),
    Section("booking_events", "bookings.BookingEvent", "actor_user"),
    Section("cancellations", "bookings.Cancellation", "user"),
    Section("applicant_notes_written", "hiring.ApplicationNote", "author"),
    Section("saved_applicant_filters", "hiring.SavedApplicantFilter", "vendor"),
    Section("interviews", "hiring.Interview", "application__talent"),
    Section("conversations_as_talent", "chat.Conversation", "talent"),
    Section("conversations_as_host", "chat.Conversation", "vendor"),
    Section("messages_sent", "chat.Message", "sender"),
    Section("blocks", "chat.Block", "blocker"),
    Section("message_reports", "chat.MessageReport", "reporter"),
    Section("masked_contact_details", "chat.LeakageEvent", "sender"),
    Section("offers_sent", "offers.Offer", "created_by"),
    Section("agreement_versions_proposed", "agreements.AgreementVersion", "proposed_by"),
    Section("signatures", "agreements.Signature", "user"),
    Section("reliability", "reliability.ReliabilityScore", "user"),
    Section("subscriptions", "billing.Subscription", "vendor", ("checkout_url",)),
    Section("invoices", "billing.Invoice", "vendor"),
    Section(
        "payout_account",
        "money.PayoutAccount",
        "talent",
        ("gateway_account_id", "provider_contact_id", "fund_account_id", "validation_id"),
    ),
    Section("payouts", "money.Payout", "talent", ("fund_account_id",)),
    Section("payout_runs", "money.PayoutRun", "talent", ("started_by",)),
    Section("check_in_passes", "attendance.AttendancePass", "talent"),
    Section("hours", "attendance.HourLog", "talent"),
    Section("post_stats_reported", "deliverables.PostStats", "reported_by"),
    Section("reviews_written", "reviews.Review", "author", ("moderated_by", "moderation_note")),
    Section(
        "reviews_about_you",
        "reviews.Review",
        "subject",
        ("moderated_by", "moderation_note", "flags"),
        {"status": "published"},
    ),
    Section("review_reports", "reviews.ReviewReport", "reporter"),
    Section("reputation", "reviews.Reputation", "user"),
    Section("activity_log", "common.AuditLog", "actor"),
]

# (model, field) user links that are not in the export, and why.
UNEXPORTED_LINKS: dict[tuple[str, str], str] = {
    ("verification.VerificationCase", "reviewer"): "The staff member who decided a case.",
    ("verification.Badge", "granted_by"): "The staff member who granted a badge.",
    ("verification.Badge", "revoked_by"): "The staff member who revoked a badge.",
    ("chat.Block", "blocked"): "Someone else's choice to block this person.",
    ("attendance.CheckIn", "recorded_by"): "The host's action; the booking is exported.",
    ("attendance.CheckIn", "reviewed_by"): "Staff action on a check-in.",
    ("attendance.CheckIn", "checked_out_by"): "The host's action; the booking is exported.",
    ("money.EscrowControl", "changed_by"): "Staff kill-switch changes.",
    ("money.PayoutRun", "started_by"): "Who started a payout run (staff or talent).",
    ("reviews.Review", "moderated_by"): "The moderator of a review.",
    ("privacy.CorrectionRequest", "resolved_by"): "The staff member who handled it.",
    ("privacy.MinorCase", "decided_by"): "The trust team member who decided it.",
    ("flags.FeatureFlag", "updated_by"): "The staff member who last switched a flag.",
    ("appversions.AppVersionPolicy", "updated_by"): "The staff member who set app versions.",
}


def register_section(section: Section) -> None:
    if all(s.name != section.name for s in EXPORT_SECTIONS):
        EXPORT_SECTIONS.append(section)


def register_unexported(model: str, field_name: str, reason: str) -> None:
    UNEXPORTED_LINKS[(model, field_name)] = reason


def covered_links() -> set[tuple[str, str]]:
    """(model, first hop) pairs the export follows, plus those left out on purpose."""
    direct = {(s.model, s.path) for s in EXPORT_SECTIONS if "__" not in s.path}
    return direct | set(UNEXPORTED_LINKS)
