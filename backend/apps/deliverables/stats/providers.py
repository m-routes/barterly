import logging
import re
from urllib.parse import parse_qs, urlparse

import requests
from django.conf import settings

from apps.deliverables.stats.base import Stats

log = logging.getLogger(__name__)
TIMEOUT = 10


def youtube_id(url: str) -> str | None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    if host == "youtu.be":
        return parsed.path.strip("/").split("/")[0] or None
    if host in ("youtube.com", "music.youtube.com"):
        if parsed.path == "/watch":
            return (parse_qs(parsed.query).get("v") or [None])[0]
        match = re.match(r"^/(shorts|embed|live)/([\w-]{6,})", parsed.path)
        return match[2] if match else None
    return None


def instagram_shortcode(url: str) -> str | None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if host != "instagram.com":
        return None
    match = re.match(r"^/(?:[\w.]+/)?(p|reel|reels|tv)/([\w-]+)", parsed.path)
    return match[2] if match else None


def _int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class YouTubeProvider:
    API = "https://www.googleapis.com/youtube/v3/videos"

    def stats_for(self, url, *, handle=""):
        video = youtube_id(url)
        if not video or not settings.YOUTUBE_API_KEY:
            return None
        try:
            response = requests.get(
                self.API,
                params={"id": video, "part": "statistics,snippet", "key": settings.YOUTUBE_API_KEY},
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            items = response.json().get("items") or []
        except (requests.RequestException, ValueError):
            log.warning("YouTube stats failed for %s", video)
            return None
        if not items:
            return None
        stats, snippet = items[0].get("statistics") or {}, items[0].get("snippet") or {}
        return Stats(
            source="youtube",
            views=_int(stats.get("viewCount")),
            likes=_int(stats.get("likeCount")),
            comments=_int(stats.get("commentCount")),
            caption=f"{snippet.get('title', '')}\n{snippet.get('description', '')}",
        )


class InstagramProvider:
    """Business discovery: the platform's Instagram business account looks up the
    talent's public media by their handle. Needs Meta app review (instagram_basic,
    business discovery) before INSTAGRAM_STATS_ENABLED."""

    API = "https://graph.facebook.com/v21.0"

    def stats_for(self, url, *, handle=""):
        code = instagram_shortcode(url)
        if not code or not handle or not settings.INSTAGRAM_STATS_ENABLED:
            return None
        if not settings.INSTAGRAM_GRAPH_TOKEN or not settings.INSTAGRAM_BUSINESS_ACCOUNT_ID:
            return None
        fields = (
            f"business_discovery.username({handle})"
            "{media.limit(50){permalink,like_count,comments_count,view_count,caption}}"
        )
        try:
            response = requests.get(
                f"{self.API}/{settings.INSTAGRAM_BUSINESS_ACCOUNT_ID}",
                params={"fields": fields},
                # In a header, so the token never sits in a URL (or a log of one).
                headers={"Authorization": f"Bearer {settings.INSTAGRAM_GRAPH_TOKEN}"},
                timeout=TIMEOUT,
            )
            response.raise_for_status()
            media = ((response.json().get("business_discovery") or {}).get("media") or {}).get(
                "data"
            ) or []
        except (requests.RequestException, ValueError):
            log.warning("Instagram stats failed for %s", handle)
            return None
        for item in media:
            if instagram_shortcode(item.get("permalink") or "") == code:
                return Stats(
                    source="instagram",
                    views=_int(item.get("view_count")),
                    likes=_int(item.get("like_count")),
                    comments=_int(item.get("comments_count")),
                    caption=item.get("caption") or "",
                )
        return None


class FakeProvider:
    """Tests: answers from `answers` (url -> Stats)."""

    answers: dict = {}

    def stats_for(self, url, *, handle=""):
        return FakeProvider.answers.get(url)
