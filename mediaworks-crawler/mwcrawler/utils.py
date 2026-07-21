"""Site-agnostic URL helpers. Nothing ripost-specific lives here — this is the
part that must work on every site, strong sitemap or not."""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import tldextract

_EXTRACT = tldextract.TLDExtract(suffix_list_urls=())   # offline; bundled suffix list

TRACKING_PARAMS = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "gbraid", "wbraid", "msclkid", "mc_cid", "mc_eid",
    "igshid", "ref", "ref_src", "source",
})

_ASSET = re.compile(
    r"\.(?:jpe?g|png|gif|webp|svg|ico|bmp|css|m?js|map|json|xml|rss|woff2?|ttf|"
    r"eot|mp4|webm|mov|avi|mp3|wav|pdf|zip|gz|rar|7z)$", re.I)

# generic pagination markers: ?page=N, ?p=N, ?oldal=N (hu), /page/N
_PAGE_PARAMS = ("page", "p", "oldal")
_PATH_PAGE = re.compile(r"/(?:page|oldal)/(\d+)/?$", re.I)


def registrable_domain(host: str) -> str:
    ext = _EXTRACT(host or "")
    return f"{ext.domain}.{ext.suffix}".lower() if ext.domain and ext.suffix else (host or "").lower()


def normalize(url: str, base: Optional[str] = None) -> Optional[str]:
    if not url:
        return None
    try:
        if base:
            from urllib.parse import urljoin
            url = urljoin(base, url)
        p = urlparse(url.strip())
    except ValueError:
        return None
    if p.scheme not in ("http", "https") or not p.netloc:
        return None
    host = (p.hostname or "").lower()
    if p.port and not ((p.scheme == "http" and p.port == 80) or (p.scheme == "https" and p.port == 443)):
        host = f"{host}:{p.port}"
    kept = sorted((k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
                  if k.lower() not in TRACKING_PARAMS)
    path = re.sub(r"/{2,}", "/", p.path) or "/"   # collapse //foo -> /foo
    return urlunparse((p.scheme.lower(), host, path, "", urlencode(kept), ""))


def in_scope(url: str, registrable: str, include_subdomains: bool = True) -> bool:
    host = (urlparse(url).hostname or "").lower()
    if include_subdomains:
        return registrable_domain(host) == registrable
    return host == registrable or host == "www." + registrable


def is_asset(url: str) -> bool:
    return bool(_ASSET.search(urlparse(url).path))


def page_number(url: str) -> Optional[int]:
    """Return the pagination index of a URL, or None if it isn't paginated."""
    p = urlparse(url)
    m = _PATH_PAGE.search(p.path)
    if m:
        return int(m.group(1))
    for k, v in parse_qsl(p.query):
        if k.lower() in _PAGE_PARAMS and v.isdigit():
            return int(v)
    return None


def is_pagination(url: str) -> bool:
    return page_number(url) is not None


def next_page(url: str) -> Optional[str]:
    """Build the URL of the *next* page: increment an existing page index, or
    add ?page=2 to a first page. Returns None if we can't form one."""
    p = urlparse(url)
    m = _PATH_PAGE.search(p.path)
    if m:
        nxt = int(m.group(1)) + 1
        new_path = _PATH_PAGE.sub(lambda _: f"/{m.group(0).strip('/').split('/')[0]}/{nxt}", p.path)
        return urlunparse((p.scheme, p.netloc, new_path, "", p.query, ""))
    params = parse_qsl(p.query, keep_blank_values=True)
    for i, (k, v) in enumerate(params):
        if k.lower() in _PAGE_PARAMS and v.isdigit():
            params[i] = (k, str(int(v) + 1))
            return urlunparse((p.scheme, p.netloc, p.path, "", urlencode(params), ""))
    # no page param yet -> page 2
    params.append(("page", "2"))
    return urlunparse((p.scheme, p.netloc, p.path, "", urlencode(params), ""))


def classify(url: str) -> str:
    if is_asset(url):
        return "asset"
    low = url.lower()
    if "/rss" in low or "/feed" in low or "/publicapi" in low:
        return "feed"
    if is_pagination(url):
        return "pagination"
    return "page"
