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
    "money.payout_account_changed": {
        "en": (
            "Your payout account changed",
            "Payouts now go to {account}, from {hold_until_ist}. If this wasn't you, "
            "contact Barterly support now.",
        ),
        "hi": (
            "आपका पेआउट खाता बदला गया",
            "अब भुगतान {account} में {hold_until_ist} से जाएगा। अगर यह आपने नहीं किया, "
            "तो तुरंत Barterly सहायता से संपर्क करें।",
        ),
    },
    "money.payout_paid": {
        "en": ("Payout sent", "{amount} for {gig_title} is on its way to {account}."),
        "hi": ("भुगतान भेजा गया", "{gig_title} के लिए {amount} {account} में भेजा जा रहा है।"),
    },
    "money.payout_failed": {
        "en": (
            "Payout didn't go through",
            "{amount} for {gig_title} couldn't be paid to {account}. We'll try again; check "
            "your payout account.",
        ),
        "hi": (
            "भुगतान नहीं हो सका",
            "{gig_title} के लिए {amount} {account} में नहीं भेजा जा सका। हम फिर कोशिश करेंगे; "
            "अपना पेआउट खाता जाँचें।",
        ),
    },
    "money.payout_on_hold": {
        "en": ("Payout waiting", "{gig_title}: {message}"),
        "hi": ("भुगतान रुका है", "{gig_title}: भुगतान पाने के लिए ऐप में अपना वॉलेट देखें।"),
    },
    "money.payout_account_failed": {
        "en": (
            "Payout account not verified",
            "We couldn't verify {account}. Check the details and add it again.",
        ),
        "hi": (
            "पेआउट खाता सत्यापित नहीं हुआ",
            "हम {account} को सत्यापित नहीं कर सके। विवरण जाँचकर फिर से जोड़ें।",
        ),
    },
    "attendance.hours_disputed": {
        "en": ("Hours disputed", "{gig_title}: your host disputed your hours on {day}: {note}"),
        "hi": ("घंटों पर आपत्ति", "{gig_title}: होस्ट ने {day} के आपके घंटों पर आपत्ति की: {note}"),
    },
    "deliverables.submitted": {
        "en": ("Work handed in", "{gig_title}: {deliverable} is ready for you to review."),
        "hi": ("काम जमा हुआ", "{gig_title}: {deliverable} आपकी समीक्षा के लिए तैयार है।"),
    },
    "deliverables.all_submitted": {
        "en": (
            "Everything's handed in",
            "{gig_title}: review it within 72 hours, or it's approved automatically.",
        ),
        "hi": (
            "सारा काम जमा हुआ",
            "{gig_title}: 72 घंटों में समीक्षा करें, वरना यह अपने-आप स्वीकृत हो जाएगा।",
        ),
    },
    "deliverables.approved": {
        "en": ("Approved", "{gig_title}: your host approved {deliverable}."),
        "hi": ("स्वीकृत", "{gig_title}: होस्ट ने {deliverable} स्वीकृत किया।"),
    },
    "deliverables.changes_requested": {
        "en": ("Changes asked for", "{deliverable}: {note}"),
        "hi": ("बदलाव माँगे गए", "{deliverable}: {note}"),
    },
    "deliverables.due_date_changed": {
        "en": ("New due date", "{deliverable} is now due {due}."),
        "hi": ("नई तारीख़", "{deliverable} अब {due} तक देना है।"),
    },
    "deliverables.due_in_two_days": {
        "en": ("Due in two days", "{deliverable} for {gig_title} is due {due}."),
        "hi": ("दो दिन बाक़ी", "{gig_title} के लिए {deliverable} {due} तक देना है।"),
    },
    "deliverables.due_today": {
        "en": ("Due today", "{deliverable} for {gig_title} is due today."),
        "hi": ("आज देना है", "{gig_title} के लिए {deliverable} आज देना है।"),
    },
    "deliverables.due_overdue": {
        "en": (
            "Overdue",
            "{deliverable} for {gig_title} was due {due}. Hand it in, or talk to your host.",
        ),
        "hi": (
            "देर हो गई",
            "{gig_title} के लिए {deliverable} {due} तक देना था। जमा करें या होस्ट से बात करें।",
        ),
    },
    "reviews.published": {
        "en": (
            "Your review is up",
            "{gig_title}: the reviews of this stay are published. See yours and reply.",
        ),
        "hi": ("आपकी समीक्षा प्रकाशित", "{gig_title}: इस प्रवास की समीक्षाएँ प्रकाशित हुईं। देखें और जवाब दें।"),
    },
    "reviews.awaiting_yours": {
        "en": (
            "You've been reviewed",
            "{gig_title}: leave your review to see theirs. Both publish together.",
        ),
        "hi": (
            "आपकी समीक्षा हुई",
            "{gig_title}: उनकी समीक्षा देखने के लिए अपनी लिखें। दोनों साथ प्रकाशित होंगी।",
        ),
    },
    "reviews.window_closing": {
        "en": (
            "Two days left to review",
            "{gig_title}: review your stay before the window closes.",
        ),
        "hi": ("समीक्षा के दो दिन बाक़ी", "{gig_title}: समय ख़त्म होने से पहले अपनी समीक्षा लिखें।"),
    },
    "support.replied": {
        "en": ("Support replied", '{reference}: we\'ve answered "{subject}". Tap to read it.'),
        "hi": ("सहायता टीम का जवाब", '{reference}: "{subject}" का जवाब आ गया है। पढ़ने के लिए टैप करें।'),
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
    "money.payout_account_changed": ("account", "hold_until_ist"),
    "money.payout_paid": ("amount", "gig_title", "account"),
    "money.payout_failed": ("amount", "gig_title", "account"),
    "money.payout_on_hold": ("gig_title", "message"),
    "money.payout_account_failed": ("account",),
    "attendance.hours_disputed": ("gig_title", "day", "note"),
    "deliverables.submitted": ("gig_title", "deliverable"),
    "deliverables.all_submitted": ("gig_title",),
    "deliverables.approved": ("gig_title", "deliverable"),
    "deliverables.changes_requested": ("deliverable", "note"),
    "deliverables.due_date_changed": ("deliverable", "due"),
    "deliverables.due_in_two_days": ("deliverable", "gig_title", "due"),
    "deliverables.due_today": ("deliverable", "gig_title"),
    "deliverables.due_overdue": ("deliverable", "gig_title", "due"),
    "reviews.published": ("gig_title",),
    "reviews.awaiting_yours": ("gig_title",),
    "reviews.window_closing": ("gig_title",),
    "support.replied": ("reference", "subject"),
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
