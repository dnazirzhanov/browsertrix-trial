"""Command-line entry point.

Examples
--------
# Tiny first trial: only the recent "news" sitemap, cap at 50 URLs
python -m urlcollector --site https://ripost.hu/ \
    --include-sitemap news_sitemap.xml --max-urls 50 --out out/trial1

# One month of the archive
python -m urlcollector --site https://ripost.hu/ --since 2026-06 --until 2026-06 --out out/june

# Everything the sitemaps know about (be patient + polite)
python -m urlcollector --site https://ripost.hu/ --out out/full --delay 2
"""
from __future__ import annotations

import argparse
import logging
import sys

from .collector import Collector
from .config import Config


def build_config(args) -> Config:
    cfg = Config(site=args.site, out_dir=args.out)
    if args.user_agent:
        cfg.user_agent = args.user_agent
    cfg.request_delay = args.delay
    cfg.since = args.since
    cfg.until = args.until
    cfg.max_urls = args.max_urls
    cfg.max_child_sitemaps = args.max_child_sitemaps
    if args.include_sitemap:
        cfg.include_sitemap_patterns = args.include_sitemap
    if args.exclude_sitemap:
        cfg.exclude_sitemap_patterns = args.exclude_sitemap
    if args.feed:
        cfg.feeds = args.feed
    cfg.homepage_crawl = args.homepage_crawl
    cfg.max_homepage_pages = args.max_homepage_pages
    cfg.obey_robots = not args.ignore_robots
    return cfg


def main(argv=None):
    p = argparse.ArgumentParser(prog="urlcollector", description="Polite URL discovery for one site.")
    p.add_argument("--site", required=True, help="Base site URL, e.g. https://ripost.hu/")
    p.add_argument("--out", default="out", help="Output directory")
    p.add_argument("--user-agent", default=None, help="Override the User-Agent string")
    p.add_argument("--delay", type=float, default=1.5, help="Min seconds between requests")
    p.add_argument("--since", default=None, help="Keep monthly sitemaps from this YYYY-MM onward")
    p.add_argument("--until", default=None, help="Keep monthly sitemaps up to this YYYY-MM")
    p.add_argument("--max-urls", type=int, default=None, help="Stop after N unique in-scope URLs")
    p.add_argument("--max-child-sitemaps", type=int, default=None, help="Cap child sitemaps fetched")
    p.add_argument("--include-sitemap", action="append", default=[],
                   help="Only child sitemaps whose URL contains this substring (repeatable)")
    p.add_argument("--exclude-sitemap", action="append", default=[],
                   help="Drop child sitemaps whose URL contains this substring (repeatable)")
    p.add_argument("--feed", action="append", default=[], help="RSS/Atom feed URL (repeatable)")
    p.add_argument("--homepage-crawl", action="store_true", help="Also do a small homepage link crawl")
    p.add_argument("--max-homepage-pages", type=int, default=40, help="Cap pages in the homepage crawl")
    p.add_argument("--ignore-robots", action="store_true",
                   help="Do NOT obey robots.txt (requires explicit sign-off; default is to obey)")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    cfg = build_config(args)
    summary = Collector(cfg).run()

    print("\n=== URL collection summary ===")
    print(f"site:               {summary['site']}")
    print(f"total unique URLs:  {summary['total_unique_urls']}")
    print(f"robots-blocked:     {summary['robots_blocked_urls']}")
    print("by source:")
    for k, v in summary["by_source"].items():
        print(f"  {k:<28} {v}")
    print("by type:")
    for k, v in summary["by_type"].items():
        print(f"  {k:<28} {v}")
    if summary["top_article_categories"]:
        print("top article categories:")
        for k, v in summary["top_article_categories"].items():
            print(f"  {k:<28} {v}")
    print(f"\nwrote: {summary['outputs']['inventory_csv']}")
    print(f"wrote: {summary['outputs']['summary_json']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
