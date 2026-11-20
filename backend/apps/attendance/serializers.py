from rest_framework import serializers

from apps.attendance.models import CheckIn, CheckInMethod, HourLog
from apps.attendance.signing import CODE_DIGITS, CODE_STEP_SECONDS


class LocationSerializer(serializers.Serializer):
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, min_value=-90, max_value=90)
    longitude = serializers.DecimalField(
        max_digits=9, decimal_places=6, min_value=-180, max_value=180
    )
    accuracy_m = serializers.IntegerField(
        min_value=0, max_value=100_000, required=False, allow_null=True, default=None
    )


class PassRequestSerializer(serializers.Serializer):
    location = LocationSerializer(
        required=False,
        allow_null=True,
        default=None,
        help_text="Where you are now (for the host's records).",
    )


class PublicKeySerializer(serializers.Serializer):
    kid = serializers.CharField()
    alg = serializers.CharField()
    public_key = serializers.CharField(help_text="Raw Ed25519 public key, base64url.")


class PassSerializer(serializers.Serializer):
    """Show `token` as a QR code. If scanning fails, show the six-digit code: TOTP
    (HMAC-SHA1) of `code_secret` (base32), changing every `code_period_seconds`."""

    booking_id = serializers.UUIDField()
    token = serializers.CharField()
    code_secret = serializers.CharField()
    code_period_seconds = serializers.IntegerField(default=CODE_STEP_SECONDS)
    code_digits = serializers.IntegerField(default=CODE_DIGITS)
    valid_from = serializers.DateTimeField()
    valid_until = serializers.DateTimeField()


class ArrivalSerializer(serializers.Serializer):
    booking_id = serializers.UUIDField()
    talent_id = serializers.UUIDField()
    talent_name = serializers.CharField()
    gig_title = serializers.CharField()
    property_name = serializers.CharField()
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    status = serializers.CharField()
    problem = serializers.CharField(help_text="Why check-in would be refused now, or empty.")
    pass_id = serializers.UUIDField()
    code_secret = serializers.CharField(help_text="To check the talent's code offline.")
    pass_valid_from = serializers.DateTimeField()
    pass_valid_until = serializers.DateTimeField()
    no_show_from = serializers.DateTimeField()


class InHouseSerializer(serializers.Serializer):
    booking_id = serializers.UUIDField()
    talent_name = serializers.CharField()
    gig_title = serializers.CharField()
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    status = serializers.CharField()
    hours_to_review = serializers.IntegerField()


class ArrivalsSerializer(serializers.Serializer):
    date = serializers.DateField()
    generated_at = serializers.DateTimeField()
    public_keys = PublicKeySerializer(many=True)
    code_period_seconds = serializers.IntegerField()
    clock_skew_seconds = serializers.IntegerField()
    arrivals = ArrivalSerializer(many=True)
    in_house = InHouseSerializer(many=True)


class CheckInRequestSerializer(serializers.Serializer):
    client_id = serializers.UUIDField(help_text="Made on the device; a re-sync applies once.")
    booking_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    method = serializers.ChoiceField(
        choices=[CheckInMethod.QR, CheckInMethod.CODE, CheckInMethod.MANUAL]
    )
    token = serializers.CharField(required=False, allow_blank=True, default="", max_length=600)
    code = serializers.CharField(required=False, allow_blank=True, default="", max_length=12)
    reason = serializers.CharField(required=False, allow_blank=True, default="", max_length=300)
    scanned_at = serializers.DateTimeField(
        required=False, allow_null=True, default=None, help_text="When it was scanned (offline)."
    )

    def validate(self, attrs):
        if attrs["method"] != CheckInMethod.QR and not attrs["booking_id"]:
            raise serializers.ValidationError({"booking_id": "Say which booking."})
        return attrs


class SyncRequestSerializer(serializers.Serializer):
    events = CheckInRequestSerializer(many=True, max_length=200)


class SyncResultSerializer(serializers.Serializer):
    client_id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=["applied", "duplicate", "refused"])
    message = serializers.CharField()
    booking_id = serializers.UUIDField(allow_null=True)


class SyncResponseSerializer(serializers.Serializer):
    results = SyncResultSerializer(many=True)


class CheckInSerializer(serializers.ModelSerializer):
    booking_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = CheckIn
        fields = [
            "id",
            "booking_id",
            "method",
            "checked_in_at",
            "recorded_at",
            "reason",
            "distance_m",
            "location_age_minutes",
            "flag",
            "reviewed_at",
            "review_note",
            "checked_out_at",
        ]
        read_only_fields = fields


class NoShowSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=300)


class FlagReviewSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=300)


class HourLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = HourLog
        fields = [
            "id",
            "day",
            "minutes",
            "note",
            "status",
            "vendor_note",
            "reviewed_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class LogHoursSerializer(serializers.Serializer):
    day = serializers.DateField()
    minutes = serializers.IntegerField(min_value=1, max_value=24 * 60)
    note = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")


class HoursCheckSerializer(serializers.Serializer):
    allowed = serializers.BooleanField()
    problems = serializers.ListField(child=serializers.CharField())
    warnings = serializers.ListField(child=serializers.CharField())
    week_start = serializers.DateField()
    week_minutes = serializers.IntegerField()
    week_days = serializers.IntegerField()
    weekly_cap_minutes = serializers.IntegerField()
    days_per_week = serializers.IntegerField()


class LoggedHoursSerializer(serializers.Serializer):
    log = HourLogSerializer()
    check = HoursCheckSerializer()


class HoursWeekSerializer(serializers.Serializer):
    week_start = serializers.DateField()
    week_end = serializers.DateField()
    logs = HourLogSerializer(many=True)
    minutes = serializers.IntegerField()
    days_worked = serializers.IntegerField()
    weekly_cap_minutes = serializers.IntegerField()
    hours_per_day = serializers.IntegerField()
    days_per_week = serializers.IntegerField()


class HourReviewSerializer(serializers.Serializer):
    confirm = serializers.BooleanField()
    note = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")


class PendingHourLogSerializer(HourLogSerializer):
    booking_id = serializers.UUIDField(read_only=True)
    talent_name = serializers.SerializerMethodField()
    gig_title = serializers.CharField(source="booking.gig.title", read_only=True)

    class Meta(HourLogSerializer.Meta):
        fields = [*HourLogSerializer.Meta.fields, "booking_id", "talent_name", "gig_title"]
        read_only_fields = fields

    def get_talent_name(self, obj) -> str:
        return _name(obj.booking.talent)


def _name(user) -> str:
    profile = getattr(user, "talent_profile", None)
    return getattr(profile, "display_name", "") or "Talent"
