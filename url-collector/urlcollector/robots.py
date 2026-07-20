"""robots.txt handling.

robots.txt is not a source of article URLs. It is a *policy* file that also
*points to* sitemaps. So we read it first to learn three things:
  1. which paths we're allowed to fetch (Disallow / Allow, per user-agent),
  2. the Crawl-delay the site requests (if any),
  3. the Sitemap: locations (our real starting seeds).
"""
from __future__ import annotations

import logging
from typing import List, Optional
from urllib.parse import urljoin

from protego import Protego

from .fetcher import PoliteFetcher

log = logging.getLogger("urlcollector.robots")


class Robots:
    def __init__(self, base_url: str, fetcher: PoliteFetcher, user_agent: str, obey: bool = True):
        self.user_agent = user_agent
        self.obey = obey
        self.robots_url = urljoin(base_url, "/robots.txt")
        self.sitemaps: List[str] = []
        self.crawl_delay: Optional[float] = None
        self._parser = Protego.parse("")   # empty ruleset == allow everything

        res = fetcher.get(self.robots_url)
        if res.ok and res.content:
            try:
                self._parser = Protego.parse(res.content.decode("utf-8", errors="replace"))
                self.sitemaps = list(self._parser.sitemaps)
                self.crawl_delay = self._parser.crawl_delay(user_agent)
                log.info(
                    "robots.txt: %d sitemap(s), crawl_delay=%s",
                    len(self.sitemaps), self.crawl_delay,
                )
            except Exception as exc:  # a malformed robots.txt shouldn't crash the run
                log.warning("could not parse robots.txt: %s", exc)
        else:
            # Missing robots.txt conventionally means "no restrictions".
            log.info("no usable robots.txt at %s (assuming allow-all)", self.robots_url)

    def allowed(self, url: str) -> bool:
        if not self.obey:
            return True
        return self._parser.can_fetch(url, self.user_agent)
