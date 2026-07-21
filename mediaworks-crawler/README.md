# Mediaworks URL discovery (Scrapy)

Fast, polite, large-scale URL discovery for news sites. Built on Scrapy, so the
frontier, dedup, retries, and **latency-based auto-throttling** (crawl as fast as
each site can handle, no faster) come for free. Works on strong- and weak-sitemap
sites with the same code.

## How it works

For each site, one spider does two things:

1. **Sitemap pass** — reads `robots.txt`, walks every sitemap (recursing indexes,
   handling gzip), and records URLs *without* downloading the articles. Cheap and
   near-complete on sites with good sitemaps.
2. **Gap crawl** — from the homepage, follows section/listing links one hop, then
   walks each listing's pagination (`?page=2, 3, …`). Each pagination chain stops
   once it stops finding **new** URLs. So a strong-sitemap site backs off fast; a
   weak one keeps going. Same code, the site decides.

Trap-safe: assets (`.js/.css/.svg/…`) and off-site links are dropped, and huge
"jump to last page" links (`?page=13077`) are recorded but never followed.

## Install

```bash
pip install -r requirements.txt
```

## Run one site

```bash
scrapy crawl discovery -a domain=ripost.hu
# knobs:  -a crawl=0            sitemaps only (skip the gap crawl)
#         -a max_page=200       walk pagination deeper (weak-sitemap sites)
#         -a patience=5         tolerate more dry pages before stopping a chain
```

Output: `out/ripost.hu/urls.txt.gz` (gzipped URL list) and `out/ripost.hu/report.json`
(counts by source and type).

## Run the whole portfolio (parallel)

```bash
python run_all.py            # crawls every domain in domains.txt at once
```

All sites run concurrently; each is throttled independently, so this is the good
kind of parallelism — linear speedup across sites, still polite to each one. To
scale beyond one machine, split `domains.txt` and run a shard per machine.

## Measure coverage

```bash
python wayback_diff.py ripost.hu out/ripost.hu/urls.txt.gz
```

Diffs your set against every URL the Internet Archive has seen for the domain,
prints a coverage %, and writes `out/<domain>/coverage.json`. `wayback_only.txt.gz`
lists what you missed — your real gap report.

## Portfolio dashboard

```bash
python stats.py            # one table across every site in ./out
```

Shows total URLs, how many came from the sitemap vs the gap crawl, the type
breakdown, and coverage % (for sites you've run `wayback_diff` on). The `crawl`
column is the payoff metric: how much dynamic discovery added beyond the sitemap.

## Speed / politeness

Tune in `mwcrawler/settings.py`. The important ones:
`CONCURRENT_REQUESTS_PER_DOMAIN` (per-site ceiling), `AUTOTHROTTLE_TARGET_CONCURRENCY`
(how hard to push), `DOWNLOAD_DELAY` (floor). Raising per-domain concurrency is the
only way to crawl a single site faster — worker/CPU count won't do it. Watch the
logs for 429/503 and back off if you see them.

## Tests

```bash
python -m pytest -q
```

## Files

| File | Role |
|------|------|
| `mwcrawler/spiders/discovery.py` | the universal spider (sitemaps + gap crawl) |
| `mwcrawler/utils.py` | normalize / scope / asset+trap / pagination logic |
| `mwcrawler/pipelines.py` | gzip output + per-domain report |
| `mwcrawler/settings.py` | politeness, autothrottle, retries |
| `run_all.py` | crawl the whole portfolio concurrently |
| `wayback_diff.py` | coverage cross-check vs the Internet Archive |
| `stats.py` | portfolio dashboard across all crawled sites |
| `domains.txt` | list of sites to crawl |
