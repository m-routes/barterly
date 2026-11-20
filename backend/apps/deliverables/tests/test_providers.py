"""Stats providers: URL parsing, the label check, and the platform APIs (faked HTTP)."""

import pytest
import requests

from apps.deliverables.stats import providers
from apps.deliverables.stats.base import CombinedProvider, has_disclosure
from apps.deliverables.stats.providers import (
    InstagramProvider,
    YouTubeProvider,
    instagram_shortcode,
    youtube_id,
)


@pytest.mark.parametrize(
    ("url", "video"),
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ?t=3", "dQw4w9WgXcQ"),
        ("https://m.youtube.com/shorts/abcdefGH", "abcdefGH"),
        ("https://www.instagram.com/reel/Cabc/", None),
    ],
)
def test_youtube_ids(url, video):
    assert youtube_id(url) == video


@pytest.mark.parametrize(
    ("url", "code"),
    [
        ("https://www.instagram.com/reel/Cabc123/", "Cabc123"),
        ("https://instagram.com/p/Bxyz_9/?igsh=1", "Bxyz_9"),
        ("https://www.instagram.com/asha.paints/reel/Cq1/", "Cq1"),
        ("https://instagram.com/asha.paints/", None),
        ("https://youtu.be/x", None),
    ],
)
def test_instagram_shortcodes(url, code):
    assert instagram_shortcode(url) == code


@pytest.mark.parametrize(
    ("caption", "found"),
    [
        ("Sunset at the hostel #ad", True),
        ("#Collab with @seabreeze", True),
        ("Paid partnership with Sea Breeze", True),
        ("Loved my #adventure here", False),
        ("#adventure #goa", False),
        ("Sunset", False),
    ],
)
def test_the_label_check(caption, found):
    assert has_disclosure(caption) is found


class Reply:
    def __init__(self, body, status=200):
        self.body, self.status_code = body, status

    def json(self):
        return self.body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(self.status_code)


@pytest.fixture
def http(monkeypatch):
    calls, replies = [], []

    def get(url, params=None, headers=None, timeout=None):
        calls.append({"url": url, "params": params or {}, "headers": headers or {}})
        reply = replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(providers.requests, "get", get)
    return calls, replies


def test_youtube_numbers(http, settings):
    calls, replies = http
    settings.YOUTUBE_API_KEY = "yt-key"
    replies.append(
        Reply(
            {
                "items": [
                    {
                        "statistics": {"viewCount": "1200", "likeCount": "88", "commentCount": "9"},
                        "snippet": {"title": "Goa", "description": "#ad"},
                    }
                ]
            }
        )
    )
    stats = YouTubeProvider().stats_for("https://youtu.be/dQw4w9WgXcQ")
    assert (stats.views, stats.likes, stats.comments) == (1200, 88, 9)
    assert has_disclosure(stats.caption)
    assert calls[0]["params"]["id"] == "dQw4w9WgXcQ"
    replies.append(requests.ConnectionError())
    assert YouTubeProvider().stats_for("https://youtu.be/dQw4w9WgXcQ") is None
    settings.YOUTUBE_API_KEY = ""
    assert YouTubeProvider().stats_for("https://youtu.be/dQw4w9WgXcQ") is None


def test_instagram_waits_for_app_review(http, settings):
    calls, replies = http
    url = "https://www.instagram.com/reel/Cabc123/"
    assert InstagramProvider().stats_for(url, handle="asha.paints") is None  # off by default
    settings.INSTAGRAM_STATS_ENABLED = True
    settings.INSTAGRAM_GRAPH_TOKEN = "ig-token"  # noqa: S105
    settings.INSTAGRAM_BUSINESS_ACCOUNT_ID = "1789"
    replies.append(
        Reply(
            {
                "business_discovery": {
                    "media": {
                        "data": [
                            {"permalink": "https://www.instagram.com/reel/Other/", "like_count": 1},
                            {
                                "permalink": url,
                                "like_count": 40,
                                "comments_count": 3,
                                "view_count": 500,
                                "caption": "#collab",
                            },
                        ]
                    }
                }
            }
        )
    )
    stats = InstagramProvider().stats_for(url, handle="asha.paints")
    assert (stats.views, stats.likes, stats.comments) == (500, 40, 3)
    assert calls[0]["headers"] == {"Authorization": "Bearer ig-token"}
    assert "ig-token" not in str(calls[0]["params"])  # never in the URL
    assert InstagramProvider().stats_for(url) is None  # needs the handle


def test_combined_asks_each_in_turn(http, settings):
    _, replies = http
    settings.YOUTUBE_API_KEY = "yt-key"
    replies.append(Reply({"items": [{"statistics": {"viewCount": "5"}}]}))
    combined = CombinedProvider()
    assert combined.stats_for("https://youtu.be/abcdefgh").views == 5
    assert combined.stats_for("https://example.com/blog") is None
