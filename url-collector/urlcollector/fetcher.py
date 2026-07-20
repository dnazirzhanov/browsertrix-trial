"""One polite way to fetch a URL. Everything else in the tool uses this.

Politeness is not a feature you bolt on later; it is a property of *every*
request, starting with the very first one (robots.txt itself). So all fetching
funnels through PoliteFetcher, which:
  * sends an honest, identifying User-Agent,
  * waits at least `delay` seconds between hits on the same host,
  * times out instead of hanging,
  * retries only on transient failures (timeout / connection / 429 / 5xx),
    with exponential backoff + jitter, honoring Retry-After when present.
"""
from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass
from typing import Dict, Optional
from urllib.parse import urlsplit

import requests

log = logging.getLogger("urlcollector.fetcher")

# Transient statuses worth retrying. 4xx (except 429) are permanent -> no retry.
RETRY_STATUSES = {429, 500, 502, 503, 504}


@dataclass
class FetchResult:
    url: str                 # requested URL
    final_url: str           # URL after redirects
    status: Optional[int]    # HTTP status, or None if the request never completed
    content: bytes           # raw body bytes (empty on error)
    content_type: str        # lowercased Content-Type header
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.status is not None and 200 <= self.status < 300


class PoliteFetcher:
    def __init__(
        self,
        user_agent: str,
        delay: float = 1.5,
        timeout: float = 20.0,
        max_retries: int = 3,
        backoff_base: float = 2.0,
    ):
        self.delay = delay
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent})
        self._last_hit: Dict[str, float] = {}   # host -> monotonic timestamp of last request

    # -- per-host rate limiting ---------------------------------------------
    def _respect_delay(self, host: str) -> None:
        last = self._last_hit.get(host)
        if last is not None:
            wait = self.delay - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
        self._last_hit[host] = time.monotonic()

    def set_host_delay(self, delay: float) -> None:
        """Raise the delay (e.g. because robots.txt asked for a bigger Crawl-delay)."""
        self.delay = max(self.delay, delay)

    # -- the one entry point -------------------------------------------------
    def get(self, url: str) -> FetchResult:
        host = urlsplit(url).netloc.lower()
        attempt = 0
        while True:
            attempt += 1
            self._respect_delay(host)
            try:
                resp = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            except requests.RequestException as exc:
                if attempt <= self.max_retries:
                    self._sleep_backoff(attempt)
                    continue
                log.warning("fetch failed (%s): %s", url, exc)
                return FetchResult(url, url, None, b"", "", error=str(exc))

            status = resp.status_code
            if status in RETRY_STATUSES and attempt <= self.max_retries:
                self._sleep_backoff(attempt, resp.headers.get("Retry-After"))
                continue

            return FetchResult(
                url=url,
                final_url=str(resp.url),
                status=status,
                content=resp.content,
                content_type=resp.headers.get("Content-Type", "").lower(),
                error=None if 200 <= status < 300 else f"HTTP {status}",
            )

    def _sleep_backoff(self, attempt: int, retry_after: Optional[str] = None) -> None:
        if retry_after:
            try:
                time.sleep(min(float(retry_after), 60.0))
                return
            except (TypeError, ValueError):
                pass  # Retry-After can be an HTTP-date; fall back to backoff
        delay = self.backoff_base ** (attempt - 1) + random.uniform(0, 0.5)
        log.info("retry %d in %.1fs", attempt, delay)
        time.sleep(delay)
