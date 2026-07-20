"""Sitemap parsing and recursive expansion.

Two things make sitemaps slightly tricky, both of which ripost exercises:
  1. A *sitemap index* lists other sitemaps, so you must detect index-vs-urlset
     and recurse (with a depth guard).
  2. Sitemaps may be gzip-compressed (.xml.gz), so sniff the bytes.

We parse namespace-agnostically (by local tag name) so the standard sitemap
namespace and the Google "news:" namespace both just work.
"""
from __future__ import annotations

import gzip
import logging
import re
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from lxml import etree

log = logging.getLogger("urlcollector.sitemaps")

_MONTHLY_RE = re.compile(r"(\d{4})(\d{2})_sitemap\.xml", re.IGNORECASE)


@dataclass
class SitemapEntry:
    loc: str
    lastmod: Optional[str] = None
    news_title: Optional[str] = None
    news_date: Optional[str] = None


def _maybe_gunzip(content: bytes) -> bytes:
    if content[:2] == b"\x1f\x8b":            # gzip magic number
        try:
            return gzip.decompress(content)
        except OSError:
            return content
    return content


def _localname(el) -> str:
    return etree.QName(el).localname


def parse_sitemap(content: bytes):
    """Return (kind, entries) where kind is 'index' | 'urlset' | 'unknown'."""
    content = _maybe_gunzip(content)
    try:
        # recover=True tolerates the small malformations real sitemaps often have
        root = etree.fromstring(content, parser=etree.XMLParser(recover=True, huge_tree=True))
    except etree.XMLSyntaxError as exc:
        log.warning("sitemap parse error: %s", exc)
        return "unknown", []
    if root is None:
        return "unknown", []

    root_name = _localname(root)
    entries: List[SitemapEntry] = []

    if root_name == "sitemapindex":
        for sm in root:
            if not isinstance(sm.tag, str) or _localname(sm) != "sitemap":
                continue
            loc = lastmod = None
            for child in sm:
                if not isinstance(child.tag, str):
                    continue
                name = _localname(child)
                if name == "loc":
                    loc = (child.text or "").strip()
                elif name == "lastmod":
                    lastmod = (child.text or "").strip()
            if loc:
                entries.append(SitemapEntry(loc=loc, lastmod=lastmod))
        return "index", entries

    if root_name == "urlset":
        for u in root:
            if not isinstance(u.tag, str) or _localname(u) != "url":
                continue
            rec = SitemapEntry(loc="")
            for child in u:
                if not isinstance(child.tag, str):
                    continue
                name = _localname(child)
                if name == "loc":
                    rec.loc = (child.text or "").strip()
                elif name == "lastmod":
                    rec.lastmod = (child.text or "").strip()
                elif name == "news":                       # Google News block
                    for nc in child.iter():
                        if not isinstance(nc.tag, str):
                            continue
                        nn = _localname(nc)
                        if nn == "title":
                            rec.news_title = (nc.text or "").strip()
                        elif nn == "publication_date":
                            rec.news_date = (nc.text or "").strip()
            if rec.loc:
                entries.append(rec)
        return "urlset", entries

    return "unknown", []


def _child_wanted(loc: str, cfg) -> bool:
    """Apply include/exclude substring filters and the YYYY-MM date window."""
    if cfg.include_sitemap_patterns and not any(p in loc for p in cfg.include_sitemap_patterns):
        return False
    if any(p in loc for p in cfg.exclude_sitemap_patterns):
        return False
    if cfg.since or cfg.until:
        m = _MONTHLY_RE.search(loc)
        if m:  # only date-filter the monthly archive sitemaps; always keep special ones
            ym = f"{m.group(1)}-{m.group(2)}"
            if cfg.since and ym < cfg.since:
                return False
            if cfg.until and ym > cfg.until:
                return False
    return True


def gather_sitemap_urls(fetcher, roots: List[str], cfg, on_entry: Callable[[SitemapEntry, str, str], None]):
    """Recursively walk sitemap roots, calling on_entry(entry, source, sitemap_url) per URL.

    `source` is the child sitemap's basename (e.g. 'news_sitemap.xml' or
    '202606_sitemap.xml'), which we carry through as the discovery source so the
    final report can say where each URL came from.
    """
    seen = set()
    queue = [(u, 0) for u in roots]
    child_budget = cfg.max_child_sitemaps
    stats = {"sitemaps_fetched": 0, "sitemap_errors": 0}

    while queue:
        sm_url, depth = queue.pop(0)
        if sm_url in seen:
            continue
        seen.add(sm_url)

        res = fetcher.get(sm_url)
        if not res.ok:
            stats["sitemap_errors"] += 1
            log.warning("could not fetch sitemap %s (%s)", sm_url, res.error)
            continue
        stats["sitemaps_fetched"] += 1

        kind, entries = parse_sitemap(res.content)
        source = sm_url.rstrip("/").split("/")[-1] or sm_url

        if kind == "index":
            if depth >= cfg.max_sitemap_depth:
                log.warning("max sitemap depth reached at %s", sm_url)
                continue
            for e in entries:
                if not _child_wanted(e.loc, cfg):
                    continue
                if child_budget is not None:
                    if child_budget <= 0:
                        break
                    child_budget -= 1
                queue.append((e.loc, depth + 1))
        elif kind == "urlset":
            for e in entries:
                on_entry(e, source, sm_url)

    return stats
