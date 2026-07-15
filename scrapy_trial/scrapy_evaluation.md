# Scrapy — Evaluation

**Date:** 2026-07-15
**Version:** Scrapy 2.17.0 (Python 3.13.5)
**Test domain:** pestisracok.hu (priority 1)
**Spider:** `scrapy_trial/scrapy_trial/spiders/pestisracok.py` (`SitemapSpider`, ~40 lines)
**Recommended role:** URL discovery and structured metadata extraction.

## Criteria assessment

| Criterion | Result | Evidence |
|---|---|---|
| Installation difficulty | **Trivial** | One `pip install scrapy`. No Docker, no daemon, no container. Easiest of the three tools evaluated by a wide margin. |
| Simple spider creation | **Good** | ~40 lines using the `SitemapSpider` base class. Sitemap index → child sitemap → article traversal handled by the framework (`request_depth_max: 3`). |
| Sitemap crawling | **Excellent** | Auto-discovered sitemaps from `robots.txt`; **8,833 article URLs enqueued** from one domain in under 3 minutes. |
| RSS crawling | **Feed exists, non-standard path** | `/feed/` returns 404. Autodiscovery via `<link rel="alternate">` on the homepage found `https://pestisracok.hu/publicapi/hu/rss/pesti_sracok/articles`. Feeds must be discovered, not guessed. |
| Link extraction | **Good** | `outbound_links` populated on 116/116 articles (100%). |
| Deduplication | **Built-in, free** | `dupefilter/filtered: 226` — duplicate requests suppressed by the framework, no custom code. |
| Logging | **Good** | Readable per-item DEBUG lines plus a comprehensive closing stats block (counts, timings, memory, dupes, robots.txt). |
| CSV/JSON output | **Native** | `-O file.csv` / `-O file.jsonl`, no code required. JSONL preferred for nested fields (`tags`, `outbound_links`). |
| URL discovery fit | **Excellent — standout capability** | 8,833 URLs discovered; run stopped only by our own `CLOSESPIDER_ITEMCOUNT=100` bound, not exhaustion. |
| Metadata extraction fit | **Strong** | 9/13 target fields at 100% coverage (see below). |

## Run statistics

| Metric | Value |
|---|---|
| Articles scraped | 116 |
| URLs discovered (enqueued) | 8,833 |
| Requests made | 137 (all HTTP 200, zero failures) |
| Duplicates filtered | 226 |
| Elapsed | 169 s (~2m50s) |
| Throughput | **41.2 items/min** (vs Browsertrix ~5.3 pages/min — ~8× faster) |
| Peak memory | 137 MB |
| Disk | ~few MB of CSV/JSONL (vs Browsertrix 415 MB, ArchiveBox: disk exhaustion) |
| Finish reason | `closespider_itemcount` (our bound, clean stop) |

## Metadata field coverage (116 articles, pestisracok.hu)

| Field (plan §7.3) | Coverage | Note |
|---|---|---|
| `normalized_url` | 100% | |
| `canonical_url` | 100% | |
| `domain` | 100% | |
| `title` | 100% | via OpenGraph |
| `description` | 100% | via OpenGraph |
| `published_at` | 100% | ISO 8601 with timezone |
| `image_url` | 100% | via `og:image` |
| `outbound_links` | 100% | |
| `language` | 100% | |
| `authors` | 92% | `meta[name="author"]` |
| `modified_at` | 0% | **Investigate:** `article:modified_time` *is* present on a 2026 test article, but absent across the 116 crawled (many from 2024). Likely template change over time or only set when modified. |
| `section` | 0% | **Site limitation:** `article:section` is not published by pestisracok.hu. |
| `tags` | 0% | **Our gap:** site publishes `meta[name="keywords"]`, not `article:tag`. Selector needs fixing, data is available. |

## Key findings

**1. URL discovery is the standout capability.** 8,833 article URLs from a single domain in under 3 minutes, discovered through `robots.txt` → sitemap index → child sitemaps, with zero traversal code written. This alone justifies the plan's proposed role.

**2. Metadata extraction works even on JavaScript-heavy sites — hypothesis disproven.** The prediction was that Scrapy, which does not execute JavaScript, would fail on Angular-driven sites (magyarnemzet, origo). It did not: magyarnemzet returned `og:title` and `article:published_time` correctly. **Reason: SEO requires meta tags to be server-side rendered**, so they are present in raw HTML regardless of how the page body is built.

The precise limitation is narrower than expected: **Scrapy is blind to JS-injected page *elements* (e.g. YouTube iframes — confirmed during the Browsertrix trial), but not to page *metadata*.** This directly supports the plan's architecture: Scrapy for discovery/metadata, browser-based capture for rendered content.

**3. Politeness and deduplication are free.** `ROBOTSTXT_OBEY`, `DOWNLOAD_DELAY`, and `AUTOTHROTTLE` are settings, not code. Contrast with the yt-dlp fallback, where rate limiting (HTTP 429) had to be hand-managed with `time.sleep()`.

**4. Resource cost is negligible.** 137 MB peak memory, megabytes of output. Compare: Browsertrix 415 MB for 31 pages; ArchiveBox exhausted 45 GB of disk before completing.

**5. Missing metadata has three distinct causes** — site limitation, our selector, or template drift over time. Reporting "0% coverage" without distinguishing these would misattribute a fixable bug to the tool.

## Limitations of this evaluation

- **One domain fully crawled** (pestisracok.hu). Metadata was spot-checked on magyarnemzet.hu only. Per-site selector work will likely be needed; coverage should not be assumed to generalize.
- RSS feed parsing was not completed (correct feed URL identified but not yet crawled).
- `OffsiteMiddleware` filtered a cross-domain `robots.txt` fetch during shell testing — expected given `allowed_domains`, but worth noting when testing multiple domains from one spider.

## Recommendation

**Adopt Scrapy for URL discovery and structured metadata extraction**, as the plan proposes. It is the cheapest tool to install and operate, the fastest by a wide margin, and it produced the plan's §7.3 `article_metadata` fields directly. It is not an archival tool and should not be evaluated as one — it captures no screenshots, WARC, or rendered content.

**Suggested next steps:** fix the `tags` selector (`meta[name="keywords"]`), resolve the `modified_at` discrepancy, crawl the discovered RSS feed, and build a second spider for a JS-heavy domain (magyarnemzet) to test whether per-site selector work is required.

## Artifacts

- `scrapy_trial/scrapy_trial/spiders/pestisracok.py` — working proof-of-concept spider
- `scrapy_trial/scrapy_trial/items.py` — schema matching plan §7.3
- `data/scrapy/article_metadata_sample.csv` — 116 articles, structured output
- `data/scrapy/article_metadata_sample.jsonl` — same, JSONL form
- `data/scrapy/crawl.log` — full run log
- 