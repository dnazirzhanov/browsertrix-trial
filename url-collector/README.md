# urlcollector

A small, **polite URL-discovery tool** for one site at a time. It is the "find
the URLs" building block of a larger crawler — deliberately *not* responsible for
downloading article bodies, screenshots, or WARC/WACZ. Keeping discovery separate
is what keeps everything else simple.

Built and tested against **ripost.hu**, but nothing site-specific is hard-coded in
the logic — point it at another site and adjust `config.py` / CLI flags.

## What it does

```
robots.txt  ->  sitemaps (recursive)  ->  feeds  ->  optional homepage crawl
                      |                      |               |
                      +----------> normalize + scope-filter + dedup (one gate)
                                                  |
                                                  v
                                        SQLite frontier  ->  CSV + JSON reports
```

1. **Reads `robots.txt` first** — not for URLs, but for the *rules* (what you may
   fetch), the *Crawl-delay*, and the *`Sitemap:` locations*.
2. **Expands sitemaps recursively.** ripost's `sitemapindex.xml` is an *index* of
   ~135 child sitemaps (monthly archives `YYYYMM_sitemap.xml` back to 2015, plus
   `news_`, `fresh_`, `categories_`, `tags_`, …). The tool detects index-vs-list,
   recurses, handles gzip, and lets you **filter which children** to pull.
3. **Optionally reads RSS/Atom feeds** and does a **bounded homepage link crawl**
   to catch anything the sitemaps miss.
4. **Normalizes, scope-filters, and deduplicates** every discovered URL through a
   single gate before it enters the frontier.
5. **Writes reports:** `url_inventory.csv` (every URL + where it came from) and
   `summary.json` (counts by source, type, and article category).

## Key ideas (why it's built this way)

- **Politeness is in every request, from the first.** All fetching goes through
  one `PoliteFetcher` (identifying User-Agent, per-host delay, retry+backoff,
  honors `Retry-After`). You cannot add politeness "later."
- **robots.txt is policy, not seeds.** It tells you the rules and points to
  sitemaps; it rarely lists article URLs itself.
- **Sitemaps are the primary source; the homepage crawl is a supplement.** On a
  well-mapped site like ripost, sitemaps give near-complete coverage at a tiny
  fraction of the request cost of link-crawling.
- **Normalization/dedup is a gate, not a phase.** Every URL from every source
  passes through the same `normalize -> in_scope -> dedup` check.
- **"Collect as many URLs as we can" means in-scope article URLs, not junk.**
  Off-domain links, assets (`.jpg/.css/...`), and tracking-param duplicates are
  filtered out. Robots-disallowed URLs are *recorded but flagged*
  (`robots_allowed=0`) rather than silently dropped, so nothing is lost.

## Install

```bash
pip install -r requirements.txt
```

## Usage

```bash
# Tiny first trial: only the recent news sitemap, capped at 50 URLs
python -m urlcollector --site https://ripost.hu/ \
    --include-sitemap news_sitemap.xml --max-urls 50 --out out/trial1 -v

# One month of the archive
python -m urlcollector --site https://ripost.hu/ --since 2026-06 --until 2026-06 --out out/june -v

# Skip the huge monthly history, grab the "current state" sitemaps only
python -m urlcollector --site https://ripost.hu/ \
    --include-sitemap news_sitemap.xml \
    --include-sitemap fresh_sitemap.xml \
    --include-sitemap categories_sitemap.xml --out out/current -v

# Everything the sitemaps know about (be patient and polite)
python -m urlcollector --site https://ripost.hu/ --delay 2 --out out/full -v
```

Useful flags: `--delay`, `--since/--until` (YYYY-MM), `--max-urls`,
`--include-sitemap/--exclude-sitemap` (repeatable substring filters),
`--max-child-sitemaps`, `--homepage-crawl`, `--feed`. See `--help`.

> **Before your first real run:** set a real contact address in the User-Agent
> (`--user-agent` or `config.py`). Start with `--max-urls 50` and `-v` so you can
> watch it behave, then scale up (50 → 100 → 500 → full), mirroring the staged
> plan in the project doc.

## Output

- `out/<dir>/url_inventory.csv` — one row per unique URL: `normalized_url`,
  `url_type`, `source`, `discovered_from`, `robots_allowed`, `lastmod`, `title`.
- `out/<dir>/summary.json` — totals, `by_source`, `by_type`,
  `top_article_categories`, `robots_blocked_urls`, run stats.
- `out/<dir>/frontier.sqlite` — the frontier DB (re-runs dedupe against it).

## Tests

```bash
python -m pytest -q
```

The suite serves **real ripost-shaped XML** through a fake fetcher, so the full
pipeline (recursion, date filtering, tracking-param dedup, robots flagging, scope
filtering, CSV output) is verified offline with no network access.

## How it plugs into the bigger crawler

The `captures`/`article_metadata` stages in your project plan consume this tool's
output. The `urls` table here maps directly onto the `urls` table in your SQL
schema (`normalized_url`, `url_hash`, `url_type`, `discovered_from`, `status`…).
A capture worker would read rows where `robots_allowed=1`, hand each URL to
Browsertrix, and write back a `captures` row — discovery and capture stay cleanly
decoupled.

## Files

| File | Responsibility |
|------|----------------|
| `config.py` | All tunable settings |
| `fetcher.py` | Polite HTTP fetching (delay, retry, backoff) |
| `robots.py` | robots.txt rules, crawl-delay, sitemap discovery |
| `urltools.py` | normalize / scope / classify / hash / link extraction |
| `sitemaps.py` | sitemap index+urlset parsing, recursion, gzip, filtering |
| `feeds.py` | RSS/Atom ingestion |
| `frontier.py` | SQLite frontier with dedup |
| `collector.py` | Orchestration + reporting |
| `cli.py` | Command-line interface |
