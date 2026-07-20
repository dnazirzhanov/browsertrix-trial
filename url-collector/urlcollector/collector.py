"""The orchestrator: runs the whole discovery pipeline and writes reports."""
from __future__ import annotations

import csv
import json
import logging
import os
from collections import Counter, deque
from typing import Optional

from . import urltools
from .config import Config
from .feeds import FeedItem, gather_feed_urls
from .fetcher import PoliteFetcher
from .frontier import Frontier
from .robots import Robots
from .sitemaps import SitemapEntry, gather_sitemap_urls

log = logging.getLogger("urlcollector.collector")


class Collector:
    def __init__(self, cfg: Config, fetcher: Optional[PoliteFetcher] = None):
        self.cfg = cfg
        # fetcher is injectable so tests can pass a fake one (no network needed)
        self.fetcher = fetcher or PoliteFetcher(
            user_agent=cfg.user_agent,
            delay=cfg.request_delay,
            timeout=cfg.timeout,
            max_retries=cfg.max_retries,
            backoff_base=cfg.backoff_base,
        )
        db_path = os.path.join(cfg.out_dir, cfg.db_name)
        self.frontier = Frontier(db_path)
        self.robots: Optional[Robots] = None
        self.stats: Counter = Counter()

    # -- the normalize + scope + dedup GATE ---------------------------------
    def _accept(self, raw_url: str, source: str, discovered_from: str,
                base: Optional[str] = None, lastmod=None, title=None) -> bool:
        if self.cfg.max_urls is not None and self.frontier.count() >= self.cfg.max_urls:
            return False
        norm = urltools.normalize(raw_url, base=base, tracking_params=self.cfg.tracking_params)
        if not norm:
            self.stats["skipped_not_http"] += 1
            return False
        if not urltools.in_scope(norm, self.cfg.site, self.cfg.include_subdomains):
            self.stats["skipped_out_of_scope"] += 1
            return False
        allowed = self.robots.allowed(norm) if self.robots else True
        newly = self.frontier.add(
            url_hash=urltools.url_hash(norm),
            normalized_url=norm,
            raw_url=raw_url,
            url_type=urltools.classify(norm),
            source=source,
            discovered_from=discovered_from,
            robots_allowed=allowed,
            lastmod=lastmod,
            title=title,
        )
        self.stats["accepted_new" if newly else "duplicates"] += 1
        return newly

    # -- pipeline stages -----------------------------------------------------
    def run(self) -> dict:
        cfg = self.cfg
        log.info("=== URL collection: %s ===", cfg.site)

        # 1) robots.txt first: rules + crawl-delay + sitemap locations
        self.robots = Robots(cfg.site, self.fetcher, cfg.user_agent, obey=cfg.obey_robots)
        if cfg.respect_crawl_delay and self.robots.crawl_delay:
            self.fetcher.set_host_delay(self.robots.crawl_delay)

        # 2) sitemaps (recursive) — the primary source
        roots = list(self.robots.sitemaps) or list(cfg.extra_sitemaps)
        if roots:
            def on_sitemap_entry(e: SitemapEntry, source: str, sm_url: str):
                self._accept(e.loc, source=source, discovered_from=sm_url,
                             lastmod=e.lastmod, title=e.news_title)
            sm_stats = gather_sitemap_urls(self.fetcher, roots, cfg, on_sitemap_entry)
            self.stats.update(sm_stats)
        else:
            log.warning("no sitemaps found in robots.txt and none configured")

        # 3) feeds (secondary)
        if cfg.feeds:
            def on_feed_item(item: FeedItem, feed_url: str):
                self._accept(item.url, source="rss", discovered_from=feed_url, title=item.title)
            self.stats.update(gather_feed_urls(self.fetcher, cfg.feeds, on_feed_item))

        # 4) optional bounded homepage/category crawl (off by default)
        if cfg.homepage_crawl:
            self._crawl_homepage()

        # 5) reports
        self.frontier.commit()
        summary = self._write_reports()
        self.frontier.close()
        return summary

    def _crawl_homepage(self):
        """Small BFS from the homepage to catch URLs that sitemaps miss.

        Bounded three ways: pages fetched, link-hop depth, and robots rules.
        This is a completeness *check*, not the main engine.
        """
        cfg = self.cfg
        start = urltools.normalize(cfg.site, tracking_params=cfg.tracking_params) or cfg.site
        queue = deque([(start, 0)])
        visited = set()
        pages = 0
        while queue and pages < cfg.max_homepage_pages:
            url, depth = queue.popleft()
            if url in visited:
                continue
            visited.add(url)
            if self.robots and not self.robots.allowed(url):
                self.stats["homepage_robots_skipped"] += 1
                continue
            res = self.fetcher.get(url)
            pages += 1
            if not res.ok or "html" not in res.content_type:
                continue
            for link in urltools.extract_links(res.content, base_url=res.final_url):
                norm = urltools.normalize(link, tracking_params=cfg.tracking_params)
                if not norm or not urltools.in_scope(norm, cfg.site, cfg.include_subdomains):
                    continue
                is_new = self._accept(link, source="homepage_crawl", discovered_from=url,
                                      base=res.final_url)
                # only descend into section/tag pages, never chase every article link
                if (is_new and depth + 1 <= cfg.homepage_max_depth
                        and urltools.classify(norm) in ("section", "tag")):
                    queue.append((norm, depth + 1))
        self.stats["homepage_pages_fetched"] = pages

    # -- reporting -----------------------------------------------------------
    def _write_reports(self) -> dict:
        cfg = self.cfg
        os.makedirs(cfg.out_dir, exist_ok=True)
        csv_path = os.path.join(cfg.out_dir, "url_inventory.csv")
        summary_path = os.path.join(cfg.out_dir, "summary.json")

        category_counter: Counter = Counter()
        with open(csv_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow([
                "url_hash", "normalized_url", "url_type", "source",
                "discovered_from", "robots_allowed", "lastmod", "title", "discovered_at",
            ])
            for row in self.frontier.iter_rows():
                writer.writerow([
                    row["url_hash"], row["normalized_url"], row["url_type"], row["source"],
                    row["discovered_from"], row["robots_allowed"], row["lastmod"],
                    row["title"], row["discovered_at"],
                ])
                cat = urltools.article_category(row["normalized_url"])
                if cat:
                    category_counter[cat] += 1

        summary = {
            "site": cfg.site,
            "total_unique_urls": self.frontier.count(),
            "by_source": self.frontier.counts_by("source"),
            "by_type": self.frontier.counts_by("url_type"),
            "top_article_categories": dict(category_counter.most_common(15)),
            "robots_blocked_urls": self.robots_blocked(),
            "run_stats": dict(self.stats),
            "outputs": {"inventory_csv": csv_path, "summary_json": summary_path},
        }
        with open(summary_path, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, ensure_ascii=False, indent=2)
        return summary

    def robots_blocked(self) -> int:
        return self.frontier.robots_blocked_count()
