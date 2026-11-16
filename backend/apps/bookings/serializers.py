from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.bookings.lifecycle import BookingStatus, moves_from
from apps.bookings.models import Booking, BookingEvent
from apps.bookings.services import actor_for


class BookingEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = BookingEvent
        fields = ["id", "from_state", "to_state", "actor", "reason", "metadata", "created_at"]
        read_only_fields = fields


class BookingSerializer(serializers.ModelSerializer):
    gig_title = serializers.CharField(source="gig.title", read_only=True)
    next_moves = serializers.SerializerMethodField(
        help_text="Statuses you could move this booking to (rules are checked on the move)."
    )
    events = BookingEventSerializer(many=True, read_only=True)

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
            "events",
        ]
        read_only_fields = fields

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
