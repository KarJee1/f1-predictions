"""News for the Home tab: headlines from public F1 RSS feeds. Items link out to the publisher."""

from __future__ import annotations

import calendar
import logging
import re
from datetime import datetime, timezone

import feedparser
import requests

log = logging.getLogger(__name__)

FEEDS = {
    "Autosport": "https://www.autosport.com/rss/f1/news/",
    "Motorsport.com": "https://www.motorsport.com/rss/f1/news/",
    "The Race": "https://www.the-race.com/rss/",
    "BBC Sport": "https://feeds.bbci.co.uk/sport/formula1/rss.xml",
}
# Feeds that cover several series: keep only entries tagged as F1.
TAG_FILTER = {"The Race": "Formula 1"}

_TAGS = re.compile(r"<[^>]+>")


def _image(entry) -> str | None:
    for key in ("media_content", "media_thumbnail"):
        for media in entry.get(key, []) or []:
            if media.get("url"):
                return media["url"]
    for link in entry.get("links", []):
        if link.get("rel") == "enclosure" and str(link.get("type", "")).startswith("image"):
            return link.get("href")
    return None


def _published(entry) -> datetime | None:
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    return datetime.fromtimestamp(calendar.timegm(parsed), tz=timezone.utc) if parsed else None


def fetch_news(since: datetime, limit: int = 60, per_source: int = 15) -> list[dict]:
    items: dict[str, dict] = {}
    for source, url in FEEDS.items():
        try:
            resp = requests.get(url, timeout=20, headers={"User-Agent": "f1-predictions-app/2.0"})
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)
        except requests.RequestException as exc:
            log.warning("News feed %s failed: %s", source, exc)
            continue
        taken = 0
        for entry in sorted(feed.entries, key=lambda e: _published(e) or since, reverse=True):
            if taken >= per_source:
                break
            link, published = entry.get("link"), _published(entry)
            if not link or not published or published < since:
                continue
            if source in TAG_FILTER and TAG_FILTER[source] not in {t.get("term") for t in entry.get("tags", [])}:
                continue
            summary = _TAGS.sub("", entry.get("summary", "")).strip()
            items[link] = {
                "title": entry.get("title", "").strip(),
                "url": link,
                "source": source,
                "published_at": published.isoformat(),
                "summary": summary[:280],
                "image": _image(entry),
            }
            taken += 1
    return sorted(items.values(), key=lambda i: i["published_at"], reverse=True)[:limit]
