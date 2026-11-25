from django import forms

from apps.support.models import TicketStatus


class StaffReplyForm(forms.Form):
    body = forms.CharField(widget=forms.Textarea(attrs={"rows": 8}), max_length=5000)
    internal = forms.BooleanField(required=False, label="Internal note (the person won't see it)")
    status = forms.ChoiceField(
        choices=[("", "Waiting for the person (default after a reply)"), *TicketStatus.choices],
        required=False,
        label="Then set the status to",
    )
    canned_id = forms.IntegerField(required=False, widget=forms.HiddenInput)
