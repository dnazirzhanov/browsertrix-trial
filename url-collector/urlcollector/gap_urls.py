"""Show the URLs that dynamic crawling finds but the sitemaps do NOT list.

    python gap_urls.py --site https://ripost.hu/ --max-pages 50

What it does, in order:
  1. robots.txt   -> rules + sitemap locations
  2. sitemaps     -> SITEMAP SET (no page fetching, just the listed URLs)
  3. page crawl   -> CRAWL SET (BFS from the homepage, budget = --max-pages)
  4. prints       -> CRAWL SET minus SITEMAP SET

Guardrails on every discovered link:
  * must be http/https
  * must be on the same site (subdomains ok), never a foreign domain
  * never an asset (.svg .css .js .jpg .png .pdf ...)
  * normalized first (lowercase host, no #fragment, no utm_/fbclid tracking,
    no duplicate slashes) so trivial variants collapse
  * robots.txt Disallow is obeyed before fetching anything
"""

import argparse
import gzip
import re
import sys
import time
from collections import Counter, deque
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import requests
from lxml import etree
from lxml import html as lxml_html
from protego import Protego

USER_AGENT = "CausaliaArchiver/0.1 (+contact: dnazirzhonov@gmail.com)"

TRACKING = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "gbraid", "wbraid", "msclkid", "igshid",
})

ASSET_RE = re.compile(
    r"\.(?:jpe?g|png|gif|webp|svg|ico|bmp|css|m?js|map|woff2?|ttf|eot|"
    r"mp4|webm|mov|mp3|wav|pdf|zip|gz|rar)$", re.I)

FALLBACK_SITEMAPS = ("/sitemap.xml", "/sitemap_index.xml", "/sitemapindex.xml")


# --------------------------------------------------------------- guardrails
def normalize(url, base=None):
    """Canonical form, or None if this is not a usable http(s) URL."""
    if not url:
        return None
    if base:
        url = urljoin(base, url.strip())
    p = urlparse(url.strip())
    if p.scheme not in ("http", "https") or not p.netloc:
        return None
    kept = sorted((k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
                  if k.lower() not in TRACKING)
    path = re.sub(r"/{2,}", "/", p.path) or "/"
    return urlunparse((p.scheme.lower(), p.netloc.lower(), path, "",
                       urlencode(kept), ""))


def same_site(url, host):
    """True only for the site itself or its subdomains. Blocks foreign domains."""
    h = urlparse(url).netloc.lower()
    return h == host or h.endswith("." + host)


def is_asset(url):
    return bool(ASSET_RE.search(urlparse(url).path))


def keep(url, host):
    """The one gate. True if this URL is worth recording at all."""
    return bool(url) and same_site(url, host) and not is_asset(url)


# --------------------------------------------------------------- fetching
class Fetcher:
    def __init__(self, delay):
        self.s = requests.Session()
        self.s.headers["User-Agent"] = USER_AGENT
        self.delay = delay
        self.last = 0.0

    def get(self, url):
        wait = self.delay - (time.monotonic() - self.last)
        if wait > 0:
            time.sleep(wait)
        try:
            r = self.s.get(url, timeout=20)
            r.raise_for_status()
            return r.content
        except requests.RequestException as e:
            print(f"  ! {url} ({e})", file=sys.stderr)
            return None
        finally:
            self.last = time.monotonic()


# --------------------------------------------------------------- sitemaps
def parse_sitemap(body):
    """-> (child sitemap urls, page urls). Handles gzip + both XML shapes."""
    if body[:2] == b"\x1f\x8b":
        try:
            body = gzip.decompress(body)
        except OSError:
            return [], []
    try:
        root = etree.fromstring(body, parser=etree.XMLParser(recover=True, huge_tree=True))
    except etree.XMLSyntaxError:
        return [], []
    if root is None:
        return [], []
    kids = root.xpath("//*[local-name()='sitemap']/*[local-name()='loc']/text()")
    pages = root.xpath("//*[local-name()='url']/*[local-name()='loc']/text()")
    return [k.strip() for k in kids], [p.strip() for p in pages]


def collect_sitemap_urls(fetcher, seeds, host):
    """Walk every sitemap. Returns the SITEMAP SET."""
    found, todo, seen_sm = set(), list(seeds), set()
    while todo:
        sm = todo.pop()
        if sm in seen_sm:
            continue
        seen_sm.add(sm)
        body = fetcher.get(sm)
        if body is None:
            continue
        kids, pages = parse_sitemap(body)
        todo.extend(kids)
        for p in pages:
            u = normalize(p)
            if keep(u, host):
                found.add(u)
        print(f"  . sitemaps walked: {len(seen_sm)}, urls: {len(found)}",
              end="\r", file=sys.stderr)
    print(file=sys.stderr)
    return found


# --------------------------------------------------------------- page crawl
def links_on(body, base_url):
    try:
        root = lxml_html.fromstring(body)
    except (etree.XMLSyntaxError, etree.ParserError):
        return []
    root.make_links_absolute(base_url, resolve_base_href=True)
    return [l for _, a, l, _ in root.iterlinks() if a == "href"]


def crawl(fetcher, start, rules, host, max_pages):
    """BFS from the homepage. Returns (CRAWL SET, pages_fetched, where_seen).

    CRAWL SET = every in-scope, non-asset URL seen in a page's links.
    where_seen maps url -> the page it was first found on (for inspection).
    """
    seen, where = set(), {}
    queue = deque([start])
    queued = {start}
    fetched = 0

    while queue and fetched < max_pages:
        page = queue.popleft()
        if rules is not None and not rules.can_fetch(page, USER_AGENT):
            continue
        body = fetcher.get(page)
        fetched += 1
        print(f"  . page {fetched}/{max_pages}: {page}", file=sys.stderr)
        if body is None:
            continue
        for raw in links_on(body, page):
            u = normalize(raw, base=page)
            if not keep(u, host):
                continue                    # foreign domain / asset / junk
            if u not in seen:
                seen.add(u)
                where[u] = page
            if u not in queued:
                queued.add(u)
                queue.append(u)
    return seen, fetched, where


# --------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", required=True)
    ap.add_argument("--max-pages", type=int, default=50)
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--out", type=Path, default=Path("out/gap_urls.txt"))
    a = ap.parse_args()

    host = urlparse(a.site).netloc.lower()
    f = Fetcher(a.delay)

    robots_body = f.get(urljoin(a.site, "/robots.txt"))
    robots_txt = robots_body.decode("utf-8", "replace") if robots_body else ""
    rules = Protego.parse(robots_txt) if robots_txt else None
    seeds = [m.strip() for m in re.findall(r"^\s*sitemap:\s*(\S+)", robots_txt, re.I | re.M)]
    if not seeds:
        seeds = [urljoin(a.site, p) for p in FALLBACK_SITEMAPS]

    print(f"\n[1/2] sitemaps ({len(seeds)} seed(s))", file=sys.stderr)
    sitemap_set = collect_sitemap_urls(f, seeds, host)

    print(f"\n[2/2] crawling {a.max_pages} pages", file=sys.stderr)
    crawl_set, pages, where = crawl(f, normalize(a.site), rules, host, a.max_pages)

    gap = sorted(crawl_set - sitemap_set)

    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text("\n".join(gap) + "\n", encoding="utf-8")

    print(f"\n{'=' * 62}")
    print(f"sitemap URLs                 {len(sitemap_set):>8}")
    print(f"crawl URLs (in scope)        {len(crawl_set):>8}")
    print(f"  already in sitemap         {len(crawl_set & sitemap_set):>8}")
    print(f"  NOT in sitemap  <-- gap    {len(gap):>8}")
    print(f"pages fetched                {pages:>8}")
    print(f"{'=' * 62}\n")

    shape = Counter("/".join(u.split("/")[3:4]) or "(root)" for u in gap)
    print("gap URLs by first path segment:")
    for seg, n in shape.most_common(20):
        print(f"  {n:>5}  /{seg}")

    print(f"\nfull gap list -> {a.out}\n")
    for u in gap:
        print(f"  {u}\n      found on: {where.get(u, '?')}")


if __name__ == "__main__":
    main()