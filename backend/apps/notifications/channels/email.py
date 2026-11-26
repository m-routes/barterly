"""Email through Django's mail backend (EMAIL_BACKEND and EMAIL_* settings: SMTP from a
transactional email service in production, the console backend locally)."""

import smtplib

from django.conf import settings
from django.core.mail import EmailMessage

from apps.notifications.channels.base import Message, PermanentFailure, Result, TemporaryFailure

FOOTER = {
    "en": "You can choose what Barterly emails you about in your notification settings.",
    "hi": "Barterly आपको किन बातों पर ईमेल भेजे, यह आप अपनी सूचना सेटिंग में चुन सकते हैं।",
}
OPEN = {"en": "Open", "hi": "खोलें"}


def body_text(message: Message) -> str:
    lines = [message.body]
    if message.web_url:
        lines += ["", f"{OPEN.get(message.locale, OPEN['en'])}: {message.web_url}"]
    lines += ["", "—", FOOTER.get(message.locale, FOOTER["en"])]
    return "\n".join(lines)


class DjangoEmailProvider:
    name = "email"

    def send(self, message: Message) -> Result:
        if not message.to:
            raise PermanentFailure("No email address.")
        email = EmailMessage(
            subject=message.title,
            body=body_text(message),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=list(message.to),
            headers={"X-Barterly-Notification": message.notification_id},
        )
        try:
            email.send(fail_silently=False)
        except smtplib.SMTPRecipientsRefused as exc:
            raise PermanentFailure(str(exc)) from exc
        except (smtplib.SMTPException, OSError) as exc:
            raise TemporaryFailure(str(exc)) from exc
        return Result(provider=self.name)
