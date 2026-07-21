"""One spider that works on any site:

  1. SITEMAP PASS  - read robots.txt, walk every sitemap (recursing indexes,
     handling gzip). Records URLs without fetching the articles. Cheap, complete
     on strong-sitemap sites.
  2. GAP CRAWL     - from the homepage, follow section/listing links one hop, then
     walk each listing's pagination. Records every in-scope link it sees.
     Pagination stops per-chain once it stops finding NEW urls ("stop when dry"),
     so a strong-sitemap site backs off fast and a weak one keeps going.

Run:  scrapy crawl discovery -a domain=ripost.hu
Knobs: -a max_page=50 -a patience=3 -a crawl=1
"""
import re

import scrapy
from scrapy import Request
from scrapy.linkextractors import LinkExtractor
from scrapy.utils.gz import gunzip
from scrapy.utils.sitemap import Sitemap

from mwcrawler.items import UrlItem
from mwcrawler.utils import (classify, in_scope, is_asset, is_pagination,
                             next_page, normalize, page_number, registrable_domain)

_SITEMAP_LINE = re.compile(r"^\s*sitemap:\s*(\S+)", re.I | re.M)
_FALLBACKS = ("/sitemap.xml", "/sitemap_index.xml", "/sitemapindex.xml")


class DiscoverySpider(scrapy.Spider):
    name = "discovery"

    def __init__(self, domain=None, crawl="1", max_page="50", patience="3", **kw):
        super().__init__(**kw)
        if not domain:
            raise ValueError("pass -a domain=example.com")
        self.domain = domain.replace("https://", "").replace("http://", "").strip("/")
        self.registrable = registrable_domain(self.domain)
        self.allowed_domains = [self.registrable]
        self.do_crawl = crawl not in ("0", "false", "no")
        self.max_page = int(max_page)      # hard cap on pagination depth per chain
        self.patience = int(patience)      # dry pages in a row before a chain stops
        self.seen = set()                  # every URL recorded, drives dedup + stop-when-dry

    def _initial_requests(self):
        yield Request(f"https://{self.domain}/robots.txt", self.parse_robots,
                      dont_filter=True, meta={"handle_httpstatus_all": True})

    async def start(self):            # Scrapy >= 2.13 (including 2.17)
        for req in self._initial_requests():
            yield req

    def start_requests(self):         # Scrapy < 2.13 fallback
        return self._initial_requests()

    # -- step 1: robots -> sitemap seeds + homepage -------------------------
    def parse_robots(self, response):
        sitemaps = _SITEMAP_LINE.findall(response.text or "")
        if not sitemaps:
            sitemaps = [f"https://{self.domain}{p}" for p in _FALLBACKS]
        for sm in sitemaps:
            yield Request(sm, self.parse_sitemap, priority=20,
                          meta={"handle_httpstatus_all": True})
        if self.do_crawl:
            yield Request(f"https://{self.domain}/", self.parse_page,
                          priority=10, meta={"hop": 0})

    # -- step 1: sitemaps (recurse index, handle gzip) ----------------------
    def parse_sitemap(self, response):
        if response.status >= 400:
            return
        body = response.body
        if body[:2] == b"\x1f\x8b":
            try:
                body = gunzip(body)
            except OSError:
                return
        try:
            sm = Sitemap(body)
        except Exception:
            return
        if sm.type == "sitemapindex":
            for entry in sm:
                loc = entry.get("loc")
                if loc:
                    yield Request(loc, self.parse_sitemap, priority=20,
                                  meta={"handle_httpstatus_all": True})
        else:  # urlset
            for entry in sm:
                item = self._record(entry.get("loc"), "sitemap")
                if item:
                    yield item

    # -- step 2: gap crawl --------------------------------------------------
    def parse_page(self, response):
        if response.status >= 400 or "text/html" not in response.headers.get("Content-Type", b"").decode("latin1"):
            return
        hop = response.meta.get("hop", 0)
        boring = response.meta.get("boring", 0)

        new_here = 0
        for link in LinkExtractor(allow_domains=self.allowed_domains).extract_links(response):
            u = normalize(link.url)
            if not u or is_asset(u) or not in_scope(u, self.registrable):
                continue
            item = self._record(u, "crawl")
            if item:
                yield item
                if item["url_type"] == "page":   # only real content keeps a chain alive
                    new_here += 1
            if hop == 0 and not is_pagination(u):
                yield response.follow(u, self.parse_page, priority=8, meta={"hop": 1})

        # walk this listing's pagination, stopping when it stops finding new urls
        boring = boring + 1 if new_here == 0 else 0
        nxt = next_page(response.url)
        if nxt and (page_number(nxt) or 1) <= self.max_page and boring < self.patience:
            yield response.follow(nxt, self.parse_page, priority=5,
                                  meta={"hop": 1, "boring": boring})

    # -- record + dedup -----------------------------------------------------
    def _record(self, raw, source):
        u = normalize(raw)
        if not u or not in_scope(u, self.registrable) or u in self.seen:
            return None
        self.seen.add(u)
        return UrlItem(url=u, domain=self.domain, source=source, url_type=classify(u))