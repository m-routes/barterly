from rest_framework import serializers


class BetaRulesSerializer(serializers.Serializer):
    closed_beta = serializers.BooleanField(help_text="True while sign-up is invite-only.")
    invite_required_for = serializers.ListField(
        child=serializers.ChoiceField(choices=["vendor", "talent"]),
        help_text="Roles that need an invite code at /api/v1/me/role/.",
    )
    max_live_gigs = serializers.IntegerField(
        allow_null=True, help_text="Live gigs a host may have at once; null: the plan decides."
    )
    max_stipend_rupees = serializers.IntegerField(
        allow_null=True, help_text="Largest stipend for one booking; null: no beta limit."
    )
