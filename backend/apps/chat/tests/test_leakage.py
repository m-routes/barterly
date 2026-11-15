import pytest

from apps.chat.leakage import MASK, explain, scan


def hidden(text: str) -> tuple[str, list[str]]:
    result = scan(text)
    return result.text, result.kinds


@pytest.mark.parametrize(
    "text",
    [
        "call 9876543210",
        "+91 98765 43210",
        "98765-43210",
        "9 8 7 6 5 4 3 2 1 0",
        "(022) 2345 6789",
        "nine eight seven six five four three two one zero",
        "nine 8 seven 6 five 4 three 2 one 0",
        "double nine eight seven six five four three two",
        "nau aath saat chhe paanch chaar teen do ek shunya",
        "98.76.54.32.10",
    ],
)
def test_phone_numbers_in_any_spelling(text):
    masked, kinds = hidden(text)
    assert "phone" in kinds
    assert not any(ch.isdigit() for ch in masked), masked


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("mail me at priya.k@gmail.com", "email"),
        ("priya at gmail dot com", "email"),
        ("priya(at)yahoo(dot)in", "email"),
        ("see https://example.org/me", "url"),
        ("www.myhostel.in has photos", "url"),
        ("check myportfolio.com/work", "url"),
        ("wa.me/919876543210", "url"),
        ("t.me/priyatravels", "url"),
        ("I'm @priya.travels everywhere", "handle"),
        ("pay me at priya@okaxis", "upi"),
        ("lets move to whatsapp", "off_platform"),
        ("ping me on whats app", "off_platform"),
        ("what's app?", "off_platform"),
        ("my watsap is open", "off_platform"),
        ("on telegram?", "off_platform"),
        ("send your insta id", "off_platform"),
        ("whats your ig handle", "off_platform"),
        ("follow me on insta", "off_platform"),
        ("call me on this", "off_platform"),
        ("share your number", "off_platform"),
        ("I'll gpay you", "off_platform"),
    ],
)
def test_contacts_and_off_platform_phrases(text, kind):
    masked, kinds = hidden(text)
    assert kind in kinds, (masked, kinds)
    assert MASK in masked


@pytest.mark.parametrize(
    "text",
    [
        "Arriving 15-11-2026 around 4 pm, staying 14 nights.",
        "Dates: 2026.11.15 to 2026.11.29",
        "Budget is ₹15,000 - 20,000 for 3 reels",
        "We have 2 rooms, 4 beds and 120 followers asked",
        "I do 3 shifts a week, one day off",
        "Loved your Instagram reels from Goa!",
        "What's the wifi like? Is breakfast included?",
        "Room 204, floor 2",
    ],
)
def test_everyday_messages_pass(text):
    assert hidden(text) == (text, [])


def test_masks_only_the_match():
    masked, kinds = hidden("Hi! WhatsApp me on 98765 43210 or priya@gmail.com, thanks")
    assert masked == f"Hi! {MASK} me on {MASK} or {MASK}, thanks"
    assert kinds == ["email", "off_platform", "phone"]


def test_explain_names_what_was_hidden():
    assert explain(["phone"]).startswith("We hid a phone number.")
    assert "phone number and link" in explain(["phone", "url"])
    assert "booking is confirmed" in explain(["email"])
