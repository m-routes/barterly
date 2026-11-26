from django import forms

from apps.beta.models import InviteRole, ReviewKind, ReviewOutcome


class InviteBatchForm(forms.Form):
    cohort = forms.CharField(max_length=40, initial="wave-1", help_text="The expansion step.")
    role = forms.ChoiceField(choices=InviteRole.choices, required=False, initial="vendor")
    labels = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 8}),
        required=False,
        help_text="One line per property (name, town): one code each. No phone numbers.",
    )
    count = forms.IntegerField(
        min_value=1, max_value=500, required=False, help_text="Or just a number of codes."
    )
    max_uses = forms.IntegerField(min_value=1, max_value=50, initial=1)
    expires_in_days = forms.IntegerField(min_value=1, max_value=365, initial=30)

    def clean(self):
        data = super().clean()
        data["label_list"] = [x.strip() for x in data.get("labels", "").splitlines() if x.strip()]
        if not data["label_list"] and not data.get("count"):
            raise forms.ValidationError("Give the properties, one per line, or a number of codes.")
        return data


class SafetyReviewForm(forms.Form):
    kind = forms.ChoiceField(choices=ReviewKind.choices, widget=forms.HiddenInput)
    object_id = forms.CharField(max_length=64, widget=forms.HiddenInput)
    outcome = forms.ChoiceField(choices=ReviewOutcome.choices)
    notes = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}), required=False)
