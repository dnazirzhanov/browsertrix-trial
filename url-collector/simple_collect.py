"""Collect every unique URL published by a single website.

Sources
-------
1. Sitemaps declared in robots.txt (recursed through sitemap indexes).
2. Dynamic link discovery: BFS from the homepage, extracting <a href>
   links from each HTML page. Stays on-site and honors robots.txt.

Compression
-----------
If the --out path ends in `.gz`, the URL list is gzipped
(~10-20x smaller than plain text for a big list).

Report
------
A small JSON report at --report tells you how many links were
discovered, how many were thrown away (as duplicates or out-of-scope),
and how many unique URLs were kept -- broken down by source.

Run it
------
    python simple_collect.py \\
        --site https://ripost.hu/ \\
        --out out/urls.txt.gz \\
        --report out/report.json \\
        --max-crawl-pages 50

The code is intentionally small and reads top-to-bottom.
"""

import argparse
import gzip
import json
import sys
import time
from collections import Counter
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import requests
from lxml import etree
from lxml import html as lxml_html
from protego import Protego

# --- Configuration ---------------------------------------------------------
USER_AGENT = "CausaliaArchiver/0.1 (+contact: dnazirzhonov@gmail.com)"
REQUEST_DELAY_SECONDS = 1.5   # pause between HTTP requests (be polite)
REQUEST_TIMEOUT_SECONDS = 20

# Query-string keys that never change page content. Dropped when we normalize
# URLs so `.../foo?utm_source=x` and `.../foo` dedupe as one URL.
TRACKING_PARAMS = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "gbraid", "wbraid", "msclkid",
})

# Tried only when robots.txt declares no sitemaps.
FALLBACK_SITEMAP_PATHS = ("/sitemap.xml", "/sitemap_index.xml", "/sitemapindex.xml")


# --- HTTP fetching ---------------------------------------------------------
class Fetcher:
    """Wrap `requests` with a stable User-Agent and a delay between calls.

    The delay is enforced across every call to `get()` on the same instance,
    so we never hammer the site -- even when fetching many URLs in a row.
    """

    def __init__(self, user_agent, delay, timeout):
        self._session = requests.Session()
        self._session.headers["User-Agent"] = user_agent
        self._delay = delay
        self._timeout = timeout
        self._last_call = 0.0

    def get(self, url):
        """Return response body bytes, or None if the fetch failed."""
        wait = self._delay - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        try:
            response = self._session.get(url, timeout=self._timeout)
            response.raise_for_status()
            return response.content
        except requests.RequestException as err:
            print(f"  ! fetch failed: {url} ({err})", file=sys.stderr)
            return None
        finally:
            self._last_call = time.monotonic()


# --- robots.txt ------------------------------------------------------------
def fetch_robots_txt(fetcher: Fetcher, site: str) -> str:
    """Fetch robots.txt once and return its text (or "" on failure)."""
    body = fetcher.get(urljoin(site, "/robots.txt"))
    return body.decode("utf-8", errors="replace") if body is not None else ""


def sitemap_urls_in(robots_text: str) -> list:
    """Every URL that appears on a `Sitemap:` line in robots.txt."""
    urls = []
    for line in robots_text.splitlines():
        key, _, value = line.partition(":")
        if key.strip().lower() == "sitemap" and value.strip():
            urls.append(value.strip())
    return urls


def robots_rules(robots_text: str):
    """A Protego object that can answer `.can_fetch(url, ua)`. None if empty."""
    return Protego.parse(robots_text) if robots_text else None


def can_crawl(rules, url: str, user_agent: str) -> bool:
    """Return True if robots.txt permits fetching `url` with `user_agent`."""
    return rules is None or rules.can_fetch(url, user_agent)


# --- Sitemap parsing -------------------------------------------------------
def parse_sitemap(xml_bytes: bytes):
    """Split a sitemap document into (child_sitemap_urls, page_urls).

    Sitemaps come in two shapes and we handle both:
      - <sitemapindex><sitemap><loc>...</loc></sitemap>...</sitemapindex>
      - <urlset>      <url>    <loc>...</loc></url>    ...</urlset>
    `local-name()` in the XPath ignores XML namespaces so both variants match
    whether or not the file declares the sitemaps.org namespace.
    """
    try:
        root = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError as err:
        print(f"  ! bad XML: {err}", file=sys.stderr)
        return [], []
    children = root.xpath("//*[local-name()='sitemap']/*[local-name()='loc']/text()")
    pages    = root.xpath("//*[local-name()='url']/*[local-name()='loc']/text()")
    return [c.strip() for c in children], [p.strip() for p in pages]


# --- URL normalization + scope --------------------------------------------
def normalize(url: str) -> str:
    """Rewrite a URL into a canonical form so trivial variants dedupe.

    - lowercase scheme + host
    - drop the URL fragment (`#...`)
    - drop known tracking query params (utm_*, fbclid, ...)
    - sort remaining query params so key order doesn't create duplicates
    """
    parts = urlparse(url)
    kept_params = sorted(
        (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in TRACKING_PARAMS
    )
    return urlunparse((
        parts.scheme.lower(),
        parts.netloc.lower(),
        parts.path,
        parts.params,
        urlencode(kept_params),
        "",  # fragment
    ))


def is_in_scope(url: str, site_host: str) -> bool:
    """True if the URL is on the same host as the site (or a subdomain)."""
    host = urlparse(url).netloc.lower()
    return host == site_host or host.endswith("." + site_host)


# --- URL tracking (dedup + counters) --------------------------------------
class UrlTracker:
    """Collect URLs from multiple sources and keep tallies for the report.

    - `add(url, source)` normalizes, scope-checks, and dedupes.
    - Every call increments the "discovered" counter for that source.
    - URLs dropped as duplicates or out-of-scope are counted but not stored.
    - Each stored URL remembers its FIRST source, so per-source kept counts
      sum cleanly to the total (no overlap between sources).
    """

    def __init__(self, site_host: str):
        self._site_host = site_host
        self._url_to_source = {}       # canonical URL -> first-source tag
        self._discovered = Counter()   # per-source raw discovery count
        self._duplicate_drops = 0
        self._out_of_scope_drops = 0

    def add(self, url: str, source: str):
        """Record a discovered link. Returns the canonical URL, or None if
        the URL was rejected as out-of-scope."""
        self._discovered[source] += 1
        canonical = normalize(url)
        if not is_in_scope(canonical, self._site_host):
            self._out_of_scope_drops += 1
            return None
        if canonical in self._url_to_source:
            self._duplicate_drops += 1
            return canonical
        self._url_to_source[canonical] = source
        return canonical

    def kept_urls(self):
        return self._url_to_source.keys()

    def summary(self) -> dict:
        kept_by_source = Counter(self._url_to_source.values())
        return {
            "unique_urls_kept": len(self._url_to_source),
            "discovered_total": sum(self._discovered.values()),
            "dropped_as_duplicate": self._duplicate_drops,
            "dropped_as_out_of_scope": self._out_of_scope_drops,
            "by_source": {
                source: {
                    "discovered": self._discovered[source],
                    "kept_unique": kept_by_source.get(source, 0),
                }
                for source in sorted(self._discovered)
            },
        }


# --- Source: sitemap walk --------------------------------------------------
def collect_from_sitemaps(fetcher: Fetcher, seed_sitemap_urls: list,
                          tracker: UrlTracker) -> int:
    """Recursively walk every sitemap and feed all URLs to the tracker.

    Uses an explicit work-list (not real recursion) -- easy to follow and it
    can't blow the Python call stack on deeply nested sitemap indexes.
    Returns the number of distinct sitemap documents fetched.
    """
    to_visit = list(seed_sitemap_urls)
    already_visited = set()
    while to_visit:
        sitemap_url = to_visit.pop()
        if sitemap_url in already_visited:
            continue
        already_visited.add(sitemap_url)
        print(f"  . sitemap: {sitemap_url}", file=sys.stderr)
        body = fetcher.get(sitemap_url)
        if body is None:
            continue
        child_sitemaps, page_urls = parse_sitemap(body)
        to_visit.extend(child_sitemaps)
        for page_url in page_urls:
            tracker.add(page_url, "sitemap")
    return len(already_visited)


# --- Source: dynamic page crawl -------------------------------------------
def extract_hrefs(html_bytes: bytes, base_url: str) -> list:
    """Return every absolute http/https `href` found in an HTML document."""
    try:
        root = lxml_html.fromstring(html_bytes)
    except (etree.XMLSyntaxError, etree.ParserError):
        return []
    root.make_links_absolute(base_url, resolve_base_href=True)
    hrefs = []
    for _, attribute, link, _ in root.iterlinks():
        if attribute == "href" and link.startswith(("http://", "https://")):
            hrefs.append(link)
    return hrefs


def collect_from_page_crawl(fetcher: Fetcher, seeds: list, rules,
                            max_pages: int, site_host: str,
                            tracker: UrlTracker) -> int:
    """Breadth-first: fetch pages, extract <a href> links, follow in-scope ones.

    - Only follows in-scope URLs (same host / subdomain).
    - Respects robots.txt via the `rules` Protego object.
    - Stops when the queue empties or `max_pages` pages have been fetched.
    Returns the number of pages actually fetched.
    """
    to_visit = []
    queued = set()   # URLs already in `to_visit` or already fetched
    for seed in seeds:
        canonical = normalize(seed)
        if canonical not in queued:
            to_visit.append(canonical)
            queued.add(canonical)

    fetched = 0
    while to_visit and fetched < max_pages:
        page_url = to_visit.pop(0)
        if not can_crawl(rules, page_url, USER_AGENT):
            continue
        fetched += 1
        print(f"  . page {fetched}/{max_pages}: {page_url}", file=sys.stderr)
        body = fetcher.get(page_url)
        if body is None:
            continue
        for link in extract_hrefs(body, page_url):
            tracker.add(link, "page_crawl")   # count EVERY discovered link
            canonical = normalize(link)
            if is_in_scope(canonical, site_host) and canonical not in queued:
                to_visit.append(canonical)
                queued.add(canonical)
    return fetched


# --- Storage ---------------------------------------------------------------
def save_urls(urls, out_path: Path) -> None:
    """Write sorted, unique URLs -- gzipped when the path ends in `.gz`."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    content = ("\n".join(sorted(urls)) + "\n").encode("utf-8")
    if out_path.suffix == ".gz":
        with gzip.open(out_path, "wb") as f:
            f.write(content)
    else:
        out_path.write_bytes(content)


def save_report(report: dict, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


# --- Orchestration --------------------------------------------------------
def collect(site: str, out_path: Path, report_path: Path,
            max_crawl_pages: int) -> dict:
    """End-to-end: discover URLs from both sources, dedupe, save, report."""
    fetcher = Fetcher(USER_AGENT, REQUEST_DELAY_SECONDS, REQUEST_TIMEOUT_SECONDS)
    site_host = urlparse(site).netloc.lower()
    tracker = UrlTracker(site_host)

    # robots.txt is fetched exactly once and used for two things:
    # (a) the `Sitemap:` lines seed the sitemap walk;
    # (b) the Disallow rules guard the dynamic page crawl.
    robots_text = fetch_robots_txt(fetcher, site)
    rules = robots_rules(robots_text)

    # Source 1: sitemaps.
    sitemap_seeds = sitemap_urls_in(robots_text) or [
        urljoin(site, path) for path in FALLBACK_SITEMAP_PATHS
    ]
    print(f"  . {len(sitemap_seeds)} sitemap seed(s)", file=sys.stderr)
    sitemaps_walked = collect_from_sitemaps(fetcher, sitemap_seeds, tracker)

    # Source 2: dynamic link discovery, seeded from the homepage.
    # Always record the homepage URL itself; page_crawl runs only if enabled.
    tracker.add(site, "homepage_seed")
    pages_crawled = 0
    if max_crawl_pages > 0:
        pages_crawled = collect_from_page_crawl(
            fetcher, [site], rules, max_crawl_pages, site_host, tracker
        )

    save_urls(tracker.kept_urls(), out_path)

    report = {
        "site": site,
        **tracker.summary(),
        "sitemaps_walked": sitemaps_walked,
        "pages_crawled": pages_crawled,
        "outputs": {
            "urls_file": str(out_path),
            "report_file": str(report_path),
        },
    }
    save_report(report, report_path)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Collect every unique URL published by one website."
    )
    parser.add_argument("--site", required=True,
                        help="Base site URL, e.g. https://ripost.hu/")
    parser.add_argument("--out", type=Path, default=Path("out/urls.txt.gz"),
                        help="Where to write the URL list "
                             "(gzipped if the path ends in `.gz`).")
    parser.add_argument("--report", type=Path, default=Path("out/report.json"),
                        help="Where to write the small JSON report.")
    parser.add_argument("--max-crawl-pages", type=int, default=50,
                        help="Max HTML pages to visit for dynamic link "
                             "discovery (0 disables it).")
    args = parser.parse_args(argv)

    report = collect(args.site, args.out, args.report, args.max_crawl_pages)

    print(f"\nurls   -> {args.out}", file=sys.stderr)
    print(f"report -> {args.report}", file=sys.stderr)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())