"""RSS/Atom ingestion. A minor source next to ripost's huge sitemaps, but cheap
insurance for very recent items and useful on sites with thin sitemaps.

Discover the real feed URLs by hand first (ripost's robots.txt explicitly allows
/publicapi/hu/rss/), then list them in Config.feeds.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, List, Optional

import feedparser

log = logging.getLogger("urlcollector.feeds")


@dataclass
class FeedItem:
    url: str
    title: Optional[str] = None
    published: Optional[str] = None


def gather_feed_urls(fetcher, feeds: List[str], on_item: Callable[[FeedItem, str], None]):
    stats = {"feeds_fetched": 0, "feed_errors": 0}
    for feed_url in feeds:
        res = fetcher.get(feed_url)
        if not res.ok:
            stats["feed_errors"] += 1
            log.warning("could not fetch feed %s (%s)", feed_url, res.error)
            continue
        stats["feeds_fetched"] += 1
        parsed = feedparser.parse(res.content)
        for entry in parsed.entries:
            link = entry.get("link")
            if not link:
                continue
            on_item(
                FeedItem(url=link, title=entry.get("title"), published=entry.get("published")),
                feed_url,
            )
    return stats
