"""Notification wording, with {variables}, in English and Hindi.

Each template is a (title, body) pair per locale. Variables come from the event's payload
plus a few added when the notification is made (see context()). A template may only use
the variables it lists in VARIABLES; a test renders every template in every locale.

The Hindi wording is a first draft: have a native speaker review it before launch.

Channels use the rendering like this: push and in-app show title and body; email uses
the title as subject and adds the link; SMS is "title: body link", trimmed; WhatsApp
sends the approved template `whatsapp_template(kind, locale)` with the variables in
VARIABLES order (WhatsApp only delivers pre-approved templates).
"""

import string

from apps.notifications import catalog

Template = dict[str, tuple[str, str]]  # locale -> (title, body)

TEMPLATES: dict[str, Template] = {
    "application.applied": {
        "en": ("New applicant for {gig_title}", "{applicant_name} applied. Have a look."),
        "hi": ("{gig_title} के लिए नया आवेदक", "{applicant_name} ने आवेदन किया है। एक नज़र डालें।"),
    },
    "application.shortlisted": {
        "en": ("You're shortlisted", "{gig_title}: the host shortlisted you."),
        "hi": ("आप शॉर्टलिस्ट हुए", "{gig_title}: होस्ट ने आपको शॉर्टलिस्ट किया है।"),
    },
    "interview.scheduled": {
        "en": ("Interview booked", "{gig_title}: {starts_at_ist}."),
        "hi": ("इंटरव्यू तय हुआ", "{gig_title}: {starts_at_ist}।"),
    },
    "application.offered": {
        "en": ("You have an offer", "{gig_title}: answer within 48 hours."),
        "hi": ("आपको ऑफ़र मिला है", "{gig_title}: 48 घंटे के भीतर जवाब दें।"),
    },
    "offer.reopened": {
        "en": (
            "Your offer is open again",
            "{gig_title}: a place opened up. Answer within 48 hours.",
        ),
        "hi": ("आपका ऑफ़र फिर से खुला है", "{gig_title}: एक जगह ख़ाली हुई। 48 घंटे के भीतर जवाब दें।"),
    },
    "offer.counter_declined": {
        "en": ("The host's final offer", "{gig_title}: accept or decline the original terms."),
        "hi": ("होस्ट का अंतिम ऑफ़र", "{gig_title}: मूल शर्तें स्वीकार या अस्वीकार करें।"),
    },
    "offer.expiring": {
        "en": ("Offer expires soon", "{gig_title}: {hours_left} hours left to answer."),
        "hi": ("ऑफ़र जल्द ख़त्म होगा", "{gig_title}: जवाब देने के लिए {hours_left} घंटे बचे हैं।"),
    },
    "agreement.ready": {
        "en": ("Agreement ready to sign", "{gig_title}: version {version} is waiting for you."),
        "hi": ("अनुबंध हस्ताक्षर के लिए तैयार", "{gig_title}: संस्करण {version} आपका इंतज़ार कर रहा है।"),
    },
    "agreement.sign_reminder": {
        "en": (
            "Please sign the agreement",
            "{gig_title}: the booking is confirmed only once you both sign.",
        ),
        "hi": ("कृपया अनुबंध पर हस्ताक्षर करें", "{gig_title}: दोनों के हस्ताक्षर के बाद ही बुकिंग पक्की होगी।"),
    },
    "booking.confirmed": {
        "en": (
            "Booking confirmed",
            "{gig_title}: you've both signed. Contact details are in the app.",
        ),
        "hi": ("बुकिंग पक्की हुई", "{gig_title}: दोनों ने हस्ताक्षर कर दिए। संपर्क जानकारी ऐप में है।"),
    },
    "chat.message": {
        "en": ("{sender_name}", "{preview}"),
        "hi": ("{sender_name}", "{preview}"),
    },
    "interview.reminder_day": {
        "en": ("Interview tomorrow", "{gig_title}: {starts_at_ist}."),
        "hi": ("कल इंटरव्यू है", "{gig_title}: {starts_at_ist}।"),
    },
    "interview.reminder_hour": {
        "en": ("Interview in an hour", "{gig_title}: {starts_at_ist}."),
        "hi": ("एक घंटे में इंटरव्यू", "{gig_title}: {starts_at_ist}।"),
    },
    "booking.starts_soon": {
        "en": (
            "Your stay starts tomorrow",
            "{gig_title}: check the address and directions in the app.",
        ),
        "hi": ("आपका प्रवास कल से शुरू है", "{gig_title}: पता और रास्ता ऐप में देखें।"),
    },
    "gigs.search_alert": {
        "en": ("New gigs for “{saved_search_name}”", "{count} new matches. Have a look."),
        "hi": ("“{saved_search_name}” के लिए नए गिग", "{count} नए मिलान। एक नज़र डालें।"),
    },
    "billing.payment_failed": {
        "en": (
            "Payment failed",
            "We couldn't charge you for {plan_name}. We'll retry; update your card to "
            "keep your plan.",
        ),
        "hi": (
            "भुगतान नहीं हुआ",
            "{plan_name} के लिए भुगतान नहीं हो सका। हम फिर कोशिश करेंगे; "
            "अपना प्लान बनाए रखने के लिए कार्ड अपडेट करें।",
        ),
    },
    "billing.grace_ending": {
        "en": (
            "Your plan is about to lock",
            "Paid features on {plan_name} lock soon unless the payment goes through.",
        ),
        "hi": ("आपका प्लान जल्द लॉक होगा", "भुगतान न होने पर {plan_name} की सुविधाएँ जल्द लॉक हो जाएँगी।"),
    },
    "billing.features_locked": {
        "en": (
            "Paid features locked",
            "Live gigs keep running, but new ones and {plan_name} features wait until you pay.",
        ),
        "hi": (
            "पेड सुविधाएँ लॉक हुईं",
            "चालू गिग चलते रहेंगे, पर भुगतान तक नए गिग और {plan_name} की सुविधाएँ बंद रहेंगी।",
        ),
    },
    catalog.OTHER: {
        "en": ("{label}", "{gig_title}"),
        "hi": ("{label}", "{gig_title}"),
    },
}

# The variables each template may use, in order (the WhatsApp template's parameters).
VARIABLES: dict[str, tuple[str, ...]] = {
    "application.applied": ("gig_title", "applicant_name"),
    "application.shortlisted": ("gig_title",),
    "interview.scheduled": ("gig_title", "starts_at_ist"),
    "application.offered": ("gig_title",),
    "offer.reopened": ("gig_title",),
    "offer.counter_declined": ("gig_title",),
    "offer.expiring": ("gig_title", "hours_left"),
    "agreement.ready": ("gig_title", "version"),
    "agreement.sign_reminder": ("gig_title",),
    "booking.confirmed": ("gig_title",),
    "chat.message": ("sender_name", "preview"),
    "interview.reminder_day": ("gig_title", "starts_at_ist"),
    "interview.reminder_hour": ("gig_title", "starts_at_ist"),
    "booking.starts_soon": ("gig_title",),
    "gigs.search_alert": ("saved_search_name", "count"),
    "billing.payment_failed": ("plan_name",),
    "billing.grace_ending": ("plan_name",),
    "billing.features_locked": ("plan_name",),
    catalog.OTHER: ("label", "gig_title"),
}


class _Context(dict):
    """Missing variables read as empty rather than failing a notification."""

    def __missing__(self, key: str) -> str:
        return ""


def template_key(kind: str) -> str:
    return kind if kind in TEMPLATES else catalog.OTHER


def context(kind: str, payload: dict, locale: str) -> dict:
    values = {k: v for k, v in payload.items() if isinstance(v, str | int)}
    values.setdefault("gig_title", "Barterly")
    values["label"] = catalog.label(kind, locale)
    return values


def render(kind: str, payload: dict, locale: str) -> tuple[str, str]:
    key = template_key(kind)
    title, body = TEMPLATES[key].get(locale) or TEMPLATES[key]["en"]
    values = _Context(context(kind, payload, locale))
    formatter = string.Formatter()
    return formatter.vformat(title, (), values), formatter.vformat(body, (), values)


def used_variables(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def whatsapp_template(kind: str, locale: str) -> str:
    return f"barterly_{template_key(kind).replace('.', '_')}_{locale}"


def whatsapp_variables(kind: str, payload: dict, locale: str) -> list[str]:
    values = _Context(context(kind, payload, locale))
    return [str(values[name]) for name in VARIABLES[template_key(kind)]]
