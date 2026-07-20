"""The "gate" every discovered URL passes through before entering the frontier.

Four jobs:
  * normalize()   -> one canonical string form, so duplicates collapse
  * url_hash()    -> stable id for that canonical form (used as the dedup key)
  * in_scope()    -> is this on the target site (and not an asset)?
  * classify()    -> article / feed / sitemap / other, from the URL shape

Normalization is intentionally conservative. We fix things that are *always*
safe (case of scheme/host, default ports, fragments, tracking params) but we do
NOT force or strip trailing slashes, because on ripost an article URL has no
trailing slash and changing it could point at a different (or 404) page. When in
doubt, prefer under-normalizing: a rare duplicate is cheaper than a lost page.
"""
from __future__ import annotations

import hashlib
import re
from typing import Iterable, List, Optional
from urllib.parse import parse_qsl, urljoin, urlsplit, urlunsplit, urlencode

import tldextract
from lxml import html as lxml_html

# ripost article shape: /<category>/<YYYY>/<MM>/<slug>
_ARTICLE_RE = re.compile(r"^/[^/]+/\d{4}/\d{2}/[^/]+/?$")
# file extensions we treat as assets, not pages worth inventorying as "articles"
_ASSET_RE = re.compile(
    r"\.(?:jpg|jpeg|png|gif|webp|svg|ico|css|js|mp4|mp3|avi|mov|webm|"
    r"pdf|zip|gz|rar|woff2?|ttf|eot)$",
    re.IGNORECASE,
)
# a tldextract instance that uses its bundled suffix snapshot (no network)
_EXTRACT = tldextract.TLDExtract(suffix_list_urls=())


def registrable_domain(host: str) -> str:
    """example: 'foo.ripost.hu' -> 'ripost.hu'."""
    ext = _EXTRACT(host)
    if ext.domain and ext.suffix:
        return f"{ext.domain}.{ext.suffix}".lower()
    return host.lower()


def normalize(url: str, base: Optional[str] = None, tracking_params: Iterable[str] = ()) -> Optional[str]:
    """Return a canonical URL string, or None if it isn't a usable http(s) URL."""
    if not url:
        return None
    url = url.strip()
    if base:
        url = urljoin(base, url)          # resolve relative links against the page they came from
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        return None
    if not parts.netloc:
        return None

    scheme = parts.scheme.lower()
    host = parts.hostname.lower() if parts.hostname else ""
    # drop default ports
    port = parts.port
    if port and not ((scheme == "http" and port == 80) or (scheme == "https" and port == 443)):
        host = f"{host}:{port}"

    # strip tracking params, keep the rest in stable (sorted) order
    tracking = {p.lower() for p in tracking_params}
    kept = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if k.lower() not in tracking]
    query = urlencode(sorted(kept))

    # drop fragment entirely (#... never changes which document the server returns)
    return urlunsplit((scheme, host, parts.path, query, ""))


def url_hash(normalized_url: str) -> str:
    return hashlib.sha1(normalized_url.encode("utf-8")).hexdigest()


def in_scope(normalized_url: str, target_site: str, include_subdomains: bool = True) -> bool:
    parts = urlsplit(normalized_url)
    host = parts.hostname or ""
    target_host = urlsplit(target_site).hostname or ""
    if _ASSET_RE.search(parts.path):
        return False
    if include_subdomains:
        return registrable_domain(host) == registrable_domain(target_host)
    return host == target_host or host == "www." + target_host or "www." + host == target_host


def classify(normalized_url: str) -> str:
    """Coarse type from the URL shape alone (no fetching)."""
    parts = urlsplit(normalized_url)
    path = parts.path
    low = normalized_url.lower()
    if low.endswith(".xml") or "sitemap" in path.lower():
        return "sitemap"
    if "/rss" in low or "/feed" in low or low.endswith(".rss"):
        return "feed"
    if _ARTICLE_RE.match(path):
        return "article"
    if "/tag/" in path or "/tags/" in path:
        return "tag"
    segments = [s for s in path.split("/") if s]
    if len(segments) <= 1:
        return "section"       # homepage or a single-segment category/section page
    return "other"


def article_category(normalized_url: str) -> Optional[str]:
    """First path segment of an article URL, e.g. '/politik/2026/06/x' -> 'politik'."""
    path = urlsplit(normalized_url).path
    if _ARTICLE_RE.match(path):
        segs = [s for s in path.split("/") if s]
        return segs[0] if segs else None
    return None


def extract_links(html_bytes: bytes, base_url: str) -> List[str]:
    """Pull absolute <a href> targets out of an HTML page."""
    try:
        doc = lxml_html.fromstring(html_bytes)
    except Exception:
        return []
    doc.make_links_absolute(base_url, resolve_base_href=True)
    out = []
    for _, attr, link, _ in doc.iterlinks():
        if attr == "href":
            out.append(link)
    return out
