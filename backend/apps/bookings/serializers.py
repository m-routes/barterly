from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.bookings.lifecycle import BookingStatus, moves_from
from apps.bookings.models import (
    Booking,
    BookingEvent,
    Cancellation,
    CancellationEffect,
    CancellationReason,
)
from apps.bookings.services import actor_for


class BookingEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = BookingEvent
        fields = ["id", "from_state", "to_state", "actor", "reason", "metadata", "created_at"]
        read_only_fields = fields


class CancellationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Cancellation
        fields = [
            "by",
            "reason",
            "note",
            "effect",
            "policy",
            "notice_days",
            "days_before_start",
            "created_at",
        ]
        read_only_fields = fields


class BookingSerializer(serializers.ModelSerializer):
    gig_title = serializers.CharField(source="gig.title", read_only=True)
    next_moves = serializers.SerializerMethodField(
        help_text="Statuses you could move this booking to (rules are checked on the move)."
    )
    events = BookingEventSerializer(many=True, read_only=True)
    cancellation = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = [
            "id",
            "application",
            "gig",
            "gig_title",
            "talent",
            "vendor",
            "status",
            "status_reason",
            "start_date",
            "end_date",
            "confirmed_at",
            "checked_in_at",
            "completed_at",
            "cancelled_at",
            "next_moves",
            "cancellation",
            "events",
        ]
        read_only_fields = fields

    @extend_schema_field(CancellationSerializer(allow_null=True))
    def get_cancellation(self, booking):
        record = getattr(booking, "cancellation", None)
        return CancellationSerializer(record).data if record else None

    @extend_schema_field(
        serializers.ListField(child=serializers.ChoiceField(BookingStatus.choices))
    )
    def get_next_moves(self, booking) -> list[str]:
        request = self.context.get("request")
        actor = actor_for(request.user, booking) if request else None
        return moves_from(booking.status, actor) if actor else []


class BookingListItemSerializer(BookingSerializer):
    class Meta(BookingSerializer.Meta):
        fields = [f for f in BookingSerializer.Meta.fields if f != "events"]
        read_only_fields = fields


class BookingTransitionSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=BookingStatus.choices)
    reason = serializers.CharField(max_length=1000, required=False, allow_blank=True)
    metadata = serializers.DictField(required=False, help_text="Extra facts kept on the event.")


class JobResultSerializer(serializers.Serializer):
    job = serializers.CharField()
    run_id = serializers.IntegerField(allow_null=True)
    skipped = serializers.BooleanField()
    result = serializers.DictField()


class CancellationReasonOptionSerializer(serializers.Serializer):
    code = serializers.ChoiceField(choices=CancellationReason.choices)
    label = serializers.CharField()


class CancelPreviewSerializer(serializers.Serializer):
    """What cancelling now would do, to show before the person confirms."""

    reasons = CancellationReasonOptionSerializer(
        many=True, help_text="The reasons you can give, in order."
    )
    effect = serializers.ChoiceField(choices=CancellationEffect.choices)
    effect_label = serializers.CharField()
    policy = serializers.CharField(help_text="The agreement's cancellation policy.")
    notice_days = serializers.IntegerField(allow_null=True)
    days_before_start = serializers.IntegerField()


class CancelSerializer(serializers.Serializer):
    reason = serializers.ChoiceField(choices=CancellationReason.choices)
    note = serializers.CharField(
        max_length=1000, required=False, allow_blank=True, help_text="Required for other."
    )


class ContactSerializer(serializers.Serializer):
    name = serializers.CharField()
    phone = serializers.CharField(help_text="Verified by OTP at sign-in.")


class PlaceSerializer(serializers.Serializer):
    name = serializers.CharField()
    address = serializers.CharField()
    city = serializers.CharField()
    state = serializers.CharField()
    pincode = serializers.CharField()
    latitude = serializers.FloatField(allow_null=True)
    longitude = serializers.FloatField(allow_null=True)
    directions = serializers.CharField()
    maps_url = serializers.CharField(help_text="Directions in Google Maps; empty without a pin.")


class UnlockedSerializer(serializers.Serializer):
    """Shared once both have signed: each side's verified phone, and for the talent the
    exact address and directions."""

    booking_id = serializers.UUIDField()
    status = serializers.ChoiceField(choices=BookingStatus.choices)
    host = ContactSerializer()
    talent = ContactSerializer()
    place = PlaceSerializer(allow_null=True, help_text="For the talent only.")
