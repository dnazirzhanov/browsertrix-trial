"""All tunable knobs live here, so the rest of the code reads cleanly.

Nothing site-specific is hard-coded in the logic; you point Config at a site
and adjust politeness/scope here (or via the CLI flags in cli.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Config:
    # --- target -------------------------------------------------------------
    site: str = "https://ripost.hu/"          # base URL; robots.txt is derived from this

    # --- identity + politeness ---------------------------------------------
    # ALWAYS identify yourself honestly. Put a real contact address here so a
    # site admin who sees you in their logs can reach you instead of blocking you.
    user_agent: str = (
        "CausaliaResearchCrawler/0.1 "
        "(+https://example.org/crawler-info; contact: crawler@example.org)"
    )
    request_delay: float = 1.5                # min seconds between requests to the host
    respect_crawl_delay: bool = True          # if robots.txt sets a larger delay, use it
    timeout: float = 20.0                     # per-request timeout, seconds
    max_retries: int = 3                      # retries on timeouts / 429 / 5xx
    backoff_base: float = 2.0                 # exponential backoff base, seconds

    # --- robots -------------------------------------------------------------
    obey_robots: bool = True                  # honor Disallow rules (leave True unless told otherwise)

    # --- scope --------------------------------------------------------------
    include_subdomains: bool = True           # treat foo.ripost.hu as in-scope
    # Query params that never change the page content: stripped during normalization.
    tracking_params: tuple = (
        "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
        "fbclid", "gclid", "gbraid", "wbraid", "msclkid", "mc_cid", "mc_eid",
        "igshid", "ref", "ref_src", "source", "amp",
    )

    # --- sitemap controls ---------------------------------------------------
    # If robots.txt lists no sitemaps, these are used as the starting points.
    extra_sitemaps: list = field(default_factory=list)
    # Substring filters applied to CHILD sitemap URLs inside an index.
    include_sitemap_patterns: list = field(default_factory=list)   # keep only children matching any
    exclude_sitemap_patterns: list = field(default_factory=list)   # drop children matching any
    # Date window for monthly archive sitemaps named like "202606_sitemap.xml".
    since: Optional[str] = None               # "YYYY-MM" inclusive lower bound
    until: Optional[str] = None               # "YYYY-MM" inclusive upper bound
    max_child_sitemaps: Optional[int] = None  # cap number of child sitemaps fetched
    max_sitemap_depth: int = 3                # guard against pathological nested indexes

    # --- feeds --------------------------------------------------------------
    feeds: list = field(default_factory=list)  # explicit RSS/Atom URLs (discover these by hand first)

    # --- optional homepage/category link crawl ------------------------------
    homepage_crawl: bool = False              # off by default: sitemaps already cover ripost fully
    max_homepage_pages: int = 40              # hard cap on pages fetched during the link crawl
    homepage_max_depth: int = 1               # how many link-hops from the homepage

    # --- global limits + output --------------------------------------------
    max_urls: int = 20                        # stop after N unique in-scope URLs (great for tiny trials)
    out_dir: str = "out"          # where the SQLite db + CSV/JSON reports are written
    db_name: str = "frontier.sqlite"
