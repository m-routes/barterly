from django import forms

from apps.verification.services.cases import Decision

VERIFICATION_ACTIONS = [
    (Decision.START_REVIEW, "Start review"),
    (Decision.APPROVE, "Approve"),
    (Decision.REQUEST_CHANGES, "Request changes"),
    (Decision.REJECT, "Reject"),
    (Decision.REVOKE, "Revoke approval"),
]
# Every decision that changes the outcome needs a reason (kept in the audit log; for
# changes and rejections it is also what the user reads).
NEEDS_REASON = {Decision.APPROVE, Decision.REQUEST_CHANGES, Decision.REJECT, Decision.REVOKE}


class VerificationDecisionForm(forms.Form):
    decision = forms.ChoiceField(choices=VERIFICATION_ACTIONS)
    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}), required=False, max_length=1000
    )

    def clean(self):
        data = super().clean()
        if data.get("decision") in NEEDS_REASON and not data.get("reason", "").strip():
            self.add_error("reason", "Give a reason. It is kept in the audit log.")
        return data


class GigDecisionForm(forms.Form):
    decision = forms.ChoiceField(choices=[("approve", "Approve"), ("send_back", "Send back")])
    reason = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 3}), required=False, max_length=500
    )

    def clean(self):
        data = super().clean()
        if data.get("decision") == "send_back" and not data.get("reason", "").strip():
            self.add_error("reason", "Say what the vendor needs to change.")
        return data
