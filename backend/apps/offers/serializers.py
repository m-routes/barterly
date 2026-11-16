from rest_framework import serializers

from apps.offers import terms as offer_terms
from apps.offers.models import Offer, OfferStatus, Party
from apps.offers.terms import (
    COUNTERABLE,
    TermsDeliverableSerializer,
    TermsSerializer,
    UsageRightsSerializer,
)
from apps.reliability import services as reliability
from apps.reliability.models import Side
from apps.reliability.serializers import ReliabilitySerializer


class OfferSerializer(serializers.ModelSerializer):
    terms = TermsSerializer(read_only=True)
    mine = serializers.SerializerMethodField(help_text="You sent this one.")
    changed_fields = serializers.SerializerMethodField(
        help_text="For a counter or the host's reply: what differs from the offer it answers."
    )

    class Meta:
        model = Offer
        fields = [
            "id",
            "revision",
            "proposed_by",
            "mine",
            "terms",
            "terms_sha256",
            "counter_of",
            "changed_fields",
            "final",
            "message",
            "status",
            "status_reason",
            "created_at",
            "answered_at",
        ]
        read_only_fields = fields

    def get_mine(self, offer) -> bool:
        return offer.created_by_id == self.context["request"].user.pk

    def get_changed_fields(self, offer) -> list[str]:
        if offer.counter_of is None:
            return []
        return offer_terms.changed_fields(offer.counter_of.terms, offer.terms)


class OfferThreadSerializer(serializers.Serializer):
    """Every offer on an application, oldest first, and what you can do next."""

    offers = OfferSerializer(many=True)
    open_offer = serializers.UUIDField(allow_null=True)
    your_turn = serializers.BooleanField(help_text="The open offer is waiting for your answer.")
    can_counter = serializers.BooleanField(
        help_text="You may still ask for a change (the talent, once per application)."
    )
    counterable = serializers.ListField(child=serializers.CharField())
    offer_expires_at = serializers.DateTimeField(allow_null=True)
    host_reliability = ReliabilitySerializer(help_text="The host's reliability (v1).")


def thread(application, user, offers) -> dict:
    offers = list(offers)
    open_offer = next((o for o in offers if o.status == OfferStatus.OPEN), None)
    held = next((o for o in offers if o.status == OfferStatus.HELD), None)
    is_talent = application.talent_id == user.pk
    mine = Party.TALENT if is_talent else Party.VENDOR
    your_turn = bool(open_offer and open_offer.recipient == mine)
    return {
        "offers": offers,
        "open_offer": open_offer.pk if open_offer else None,
        "your_turn": your_turn,
        "can_counter": bool(
            your_turn
            and is_talent
            and not open_offer.final
            and not any(o.proposed_by == Party.TALENT for o in offers)
        ),
        "counterable": list(COUNTERABLE),
        "offer_expires_at": application.offer_expires_at if open_offer or held else None,
        "host_reliability": reliability.for_user(application.gig.vendor, Side.VENDOR),
    }


class MakeOfferSerializer(serializers.Serializer):
    terms = TermsSerializer(help_text="Checked against the gig's pay model.")
    message = serializers.CharField(max_length=1000, required=False, allow_blank=True)


class CounterChangesSerializer(serializers.Serializer):
    """The terms the talent may change. Send only the ones you want different."""

    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False)
    hours_per_day = serializers.IntegerField(required=False)
    days_per_week = serializers.IntegerField(required=False)
    stipend_amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, allow_null=True
    )
    deliverables = TermsDeliverableSerializer(many=True, required=False)
    usage_rights = UsageRightsSerializer(required=False, allow_null=True)


class CounterSerializer(serializers.Serializer):
    changes = CounterChangesSerializer()
    message = serializers.CharField(max_length=1000, required=False, allow_blank=True)


class AnswerSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)


class AcceptedSerializer(serializers.Serializer):
    booking = serializers.UUIDField()
    agreement_version = serializers.UUIDField(
        help_text="Version 1 of the agreement, for both of you to sign."
    )


def raw_object(data, name: str) -> dict:
    """The JSON object sent as `name`: the service validates it against the gig."""
    value = data.get(name) if hasattr(data, "get") else None
    if not isinstance(value, dict):
        raise serializers.ValidationError({name: "Send an object."})
    return value
