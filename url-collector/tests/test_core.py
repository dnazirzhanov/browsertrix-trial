"""Offline tests: a fake fetcher serves real ripost-shaped XML, so the whole
pipeline is exercised without touching the network.

Run:  python -m pytest -q      (from the project root)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from urlcollector import urltools
from urlcollector.collector import Collector
from urlcollector.config import Config
from urlcollector.fetcher import FetchResult
from urlcollector.sitemaps import parse_sitemap

# --------------------------------------------------------------------------
# Fixtures: trimmed but structurally identical to the live ripost documents.
# --------------------------------------------------------------------------
ROBOTS = b"""User-agent: *
Disallow: /hirdetesek
Disallow: /kereses
Allow: /publicapi/hu/rss/
Disallow: /publicapi/
Crawl-delay: 2
Sitemap: https://ripost.hu/sitemapindex.xml
"""

SITEMAP_INDEX = b"""<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://ripost.hu/202605_sitemap.xml</loc><lastmod>2026-05-31T20:00:40+00:00</lastmod></sitemap>
  <sitemap><loc>https://ripost.hu/202606_sitemap.xml</loc><lastmod>2026-06-15T20:00:26+00:00</lastmod></sitemap>
  <sitemap><loc>https://ripost.hu/news_sitemap.xml</loc><lastmod></lastmod></sitemap>
</sitemapindex>
"""

# A monthly child sitemap (plain urlset, no news namespace).
SITEMAP_202606 = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://ripost.hu/politik/2026/06/orban-viktor-nem-adom-fel</loc><lastmod>2026-06-14T07:15:00+00:00</lastmod></url>
  <url><loc>https://ripost.hu/nino/2026/06/baleset-az-m0-ason</loc><lastmod>2026-06-14T12:40:00+00:00</lastmod></url>
  <!-- same article again but with tracking params: must collapse to the one above -->
  <url><loc>https://ripost.hu/politik/2026/06/orban-viktor-nem-adom-fel?utm_source=fb&amp;fbclid=xyz</loc></url>
  <!-- a robots-disallowed path, to prove we still record it but flag it -->
  <url><loc>https://ripost.hu/publicapi/private/secret</loc></url>
</urlset>
"""

SITEMAP_202605 = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://ripost.hu/kulfold/2026/05/regi-cikk-egy</loc></url>
  <url><loc>https://ripost.hu/kulfold/2026/05/regi-cikk-ketto</loc></url>
</urlset>
"""

NEWS_SITEMAP = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">
  <url>
    <loc>https://ripost.hu/medicina/2026/06/alvas-titka-vegre-kiderult</loc>
    <news:news>
      <news:publication><news:name>Ripost</news:name><news:language>hu</news:language></news:publication>
      <news:publication_date>2026-06-14T20:00:00+00:00</news:publication_date>
      <news:title>Kiderult a pihenteto alvas titka</news:title>
    </news:news>
  </url>
</urlset>
"""

FIXTURES = {
    "https://ripost.hu/robots.txt": (ROBOTS, "text/plain"),
    "https://ripost.hu/sitemapindex.xml": (SITEMAP_INDEX, "text/xml"),
    "https://ripost.hu/202606_sitemap.xml": (SITEMAP_202606, "text/xml"),
    "https://ripost.hu/202605_sitemap.xml": (SITEMAP_202605, "text/xml"),
    "https://ripost.hu/news_sitemap.xml": (NEWS_SITEMAP, "text/xml"),
}


class FakeFetcher:
    """Serves fixtures by exact URL; 404s anything else. Records what was fetched."""
    def __init__(self):
        self.requested = []

    def get(self, url):
        self.requested.append(url)
        if url in FIXTURES:
            body, ctype = FIXTURES[url]
            return FetchResult(url, url, 200, body, ctype)
        return FetchResult(url, url, 404, b"", "", error="HTTP 404")

    def set_host_delay(self, d):
        pass


# --------------------------------------------------------------------------
# Unit tests
# --------------------------------------------------------------------------
def test_normalize_strips_tracking_and_fragment():
    tp = Config().tracking_params
    a = urltools.normalize("https://ripost.hu/politik/2026/06/x?utm_source=fb&fbclid=1#top", tracking_params=tp)
    b = urltools.normalize("https://RIPOST.hu/politik/2026/06/x", tracking_params=tp)
    assert a == b == "https://ripost.hu/politik/2026/06/x"


def test_scope_rejects_offsite_and_assets():
    assert urltools.in_scope("https://ripost.hu/politik/2026/06/x", "https://ripost.hu/")
    assert urltools.in_scope("https://sport.ripost.hu/x", "https://ripost.hu/")       # subdomain
    assert not urltools.in_scope("https://facebook.com/ripost", "https://ripost.hu/")
    assert not urltools.in_scope("https://ripost.hu/img/photo.jpg", "https://ripost.hu/")


def test_classify_shapes():
    assert urltools.classify("https://ripost.hu/politik/2026/06/x") == "article"
    assert urltools.classify("https://ripost.hu/sitemapindex.xml") == "sitemap"
    assert urltools.classify("https://ripost.hu/politik") == "section"
    assert urltools.classify("https://ripost.hu/tag/foci") == "tag"


def test_parse_index_and_urlset():
    kind, entries = parse_sitemap(SITEMAP_INDEX)
    assert kind == "index" and len(entries) == 3
    kind, entries = parse_sitemap(NEWS_SITEMAP)
    assert kind == "urlset" and entries[0].news_title == "Kiderult a pihenteto alvas titka"


# --------------------------------------------------------------------------
# End-to-end pipeline
# --------------------------------------------------------------------------
def _run(tmp_out, **overrides):
    cfg = Config(site="https://ripost.hu/", out_dir=tmp_out)
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return Collector(cfg, fetcher=FakeFetcher()).run()


def test_end_to_end_full(tmp_path):
    summary = _run(str(tmp_path))
    # 202606 has 4 <loc>, but the utm-duplicate collapses -> 3 unique from that file;
    # 202605 -> 2; news_sitemap -> 1. Total unique = 3 + 2 + 1 = 6.
    assert summary["total_unique_urls"] == 6
    assert summary["run_stats"]["duplicates"] == 1          # the tracking-param dup
    assert summary["robots_blocked_urls"] == 1              # the /publicapi/ URL
    assert summary["by_type"]["article"] == 5               # 6 total minus the publicapi non-article
    # CSV actually written
    assert os.path.exists(os.path.join(str(tmp_path), "url_inventory.csv"))


def test_date_filter_keeps_only_june(tmp_path):
    summary = _run(str(tmp_path), since="2026-06", until="2026-06")
    # 202605 child must be skipped entirely; its two URLs must not appear.
    assert summary["total_unique_urls"] == 6 - 2
    import sqlite3
    conn = sqlite3.connect(os.path.join(str(tmp_path), "frontier.sqlite"))
    urls = ",".join(row[0] for row in conn.execute("SELECT normalized_url FROM urls"))
    assert "2026/05" not in urls


def test_max_urls_cap(tmp_path):
    summary = _run(str(tmp_path), max_urls=2)
    assert summary["total_unique_urls"] == 2


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python", "-m", "pytest", "-q", __file__]))
