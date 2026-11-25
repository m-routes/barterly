"""A starter set of canned replies in English and Hindi. Support edits them in the admin."""

from django.db import migrations

STARTERS = [
    (
        "Got it, looking into it",
        "",
        "Thanks for writing. We've got your message and are looking into it. "
        "We'll reply here as soon as we know more.",
        "लिखने के लिए धन्यवाद। हमें आपका संदेश मिल गया है और हम इसे देख रहे हैं। "
        "जैसे ही हमें और जानकारी मिलेगी, हम यहीं जवाब देंगे।",
    ),
    (
        "Payment: when the stipend is released",
        "payment",
        "The stipend is held safely by Barterly once the host funds it. It's released to "
        "you after the stay starts and the host approves your work (or automatically if "
        "they don't respond in time). Payouts reach your bank in 1 to 3 working days.",
        "होस्ट के जमा करने के बाद स्टाइपेंड Barterly के पास सुरक्षित रहता है। प्रवास शुरू होने "
        "और होस्ट के आपका काम मंज़ूर करने के बाद (या समय पर जवाब न देने पर अपने-आप) यह आपको "
        "जारी होता है। पैसा 1 से 3 कामकाजी दिनों में आपके बैंक खाते में पहुँच जाता है।",
    ),
    (
        "Safety: are you safe right now?",
        "safety",
        "Thank you for telling us. First: are you safe right now? If you're in danger, "
        "call 112. You can also use SOS in the app to share your location with your "
        "emergency contact. Reply here and someone from our trust team will call you.",
        "हमें बताने के लिए धन्यवाद। सबसे पहले: क्या आप अभी सुरक्षित हैं? अगर आप ख़तरे में हैं, "
        "तो 112 पर कॉल करें। आप ऐप में SOS से अपनी लोकेशन अपने इमरजेंसी संपर्क को भेज सकते हैं। "
        "यहाँ जवाब दें, हमारी ट्रस्ट टीम का कोई सदस्य आपको कॉल करेगा।",
    ),
    (
        "Bug: tell us more",
        "bug",
        "Sorry about that. To help us fix it, could you tell us what you tapped just "
        "before it happened, and send a screenshot if you can? Updating the app to the "
        "latest version sometimes helps too.",
        "इसके लिए क्षमा करें। इसे ठीक करने में मदद के लिए, क्या आप बता सकते हैं कि ऐसा होने से "
        "ठीक पहले आपने क्या टैप किया था, और हो सके तो एक स्क्रीनशॉट भेजें? ऐप को नए वर्ज़न पर "
        "अपडेट करने से भी कभी-कभी मदद मिलती है।",
    ),
    (
        "Feedback: thank you",
        "feedback",
        "Thank you for the idea. We read every piece of feedback during the beta and "
        "share it with the team each week. We'll let you know if we build it.",
        "सुझाव के लिए धन्यवाद। बीटा के दौरान हम हर सुझाव पढ़ते हैं और हर हफ़्ते टीम के साथ साझा "
        "करते हैं। अगर हम इसे बनाते हैं, तो आपको बताएँगे।",
    ),
    (
        "Resolved: anything else?",
        "",
        "We think this is sorted now, so we've marked it resolved. If anything's still "
        "not right, just reply here and it opens again.",
        "हमें लगता है कि यह अब ठीक हो गया है, इसलिए हमने इसे हल मान लिया है। अगर अब भी कुछ "
        "ठीक नहीं है, तो बस यहीं जवाब दें, यह फिर से खुल जाएगा।",
    ),
]


def add(apps, schema_editor):
    CannedResponse = apps.get_model("support", "CannedResponse")
    for title, kind, en, hi in STARTERS:
        CannedResponse.objects.get_or_create(
            title=title, defaults={"kind": kind, "body_en": en, "body_hi": hi}
        )


def remove(apps, schema_editor):
    CannedResponse = apps.get_model("support", "CannedResponse")
    CannedResponse.objects.filter(title__in=[s[0] for s in STARTERS]).delete()


class Migration(migrations.Migration):
    dependencies = [("support", "0001_initial")]

    operations = [migrations.RunPython(add, remove)]
