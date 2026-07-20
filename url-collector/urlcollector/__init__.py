"""urlcollector — a small, polite URL-discovery tool.

This is deliberately *only* about finding and inventorying URLs (discovery +
frontier), not about downloading article bodies or taking screenshots. Keeping
discovery separate is what lets the rest of the crawler stay simple.

Pipeline, at a glance:

    robots.txt  ->  sitemaps (recursive)  ->  feeds  ->  optional homepage crawl
                          |                     |               |
                          v                     v               v
                    normalize + scope-filter + dedup  ->  SQLite frontier  ->  CSV reports

Every fetch goes through one polite fetcher (user-agent, delay, retry/backoff),
and every discovered URL passes through one normalize/scope/dedup "gate" before
it is allowed into the frontier.
"""

__version__ = "0.1.0"
