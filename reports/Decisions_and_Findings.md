# Browsertrix Crawler — Evaluation

**Date:** 2026-07-13
**Version:** Browsertrix Crawler 1.13.2
**Test set:** 31 seed URLs across 6 Mediaworks-related sites (see `data/seed_urls/test_urls.csv`)
**Recommended role:** Primary archival crawler.

## Command used

```bash
docker run -v "$PWD/data/seed_urls:/seeds/:ro" -v "$PWD/crawls:/crawls/" \
  -it webrecorder/browsertrix-crawler crawl \
  --seedFile /seeds/test_urls.txt --scopeType page \
  --collection <name> --generateWACZ \
  --text to-pages,to-warc --screenshot view,fullPage \
  --behaviors autoscroll,autoplay,siteSpecific --workers 2
```

## Criteria assessment

| Criterion | Result | Notes |
|---|---|---|
| Installation | Good | Single Docker image, no local build. |
| Docker setup | Good | Volume mounts (`:ro` seeds, RW crawls) work as expected. |
| Basic crawl command | Good | Reliable; `--scopeType page` correctly limits to seeds. |
| Seed-file input | Good | Runs directly from the shared `test_urls.txt`. |
| Screenshots | Good | `view` + `fullPage` produced per page. |
| WARC/WACZ output | Good | WACZ generated; multiple WARCs merged automatically. |
| Logs | Good | Structured JSON (JSONL), machine-parseable. |
| Failure reporting | Good | Per-page status visible; partial states flagged (e.g. `loadState 3`, behavior timeouts). |
| Disk usage | Acceptable | ~415 MB for 31 mixed pages (~13 MB/page avg; inflated by video/gallery pages). |
| Speed | Good | ~6 min for 31 pages at `--workers 2`. |
| Capture quality | Good | Text, images, native/self-hosted video captured and replay correctly. |
| Replayability | Good, w/ one gap | Replays faithfully in ReplayWeb.page — except YouTube (see below). |
| JavaScript support | Good | Renders JS-injected content Chromium executes. |
| Cookie banners | No blocking issues | No captures blocked by banners in this set. |

## Key findings

**1. YouTube embeds cannot be captured replayably.** Native/self-hosted video works; YouTube embeds fail to replay due to platform-side signed, time-limited `googlevideo.com` URLs and anti-bot measures — outside the crawler's control. Tested and confirmed this is *not* fixable via the `autoplay` behavior (re-crawled with it; no change). yt-dlp is required as a fallback and successfully recovers these videos with audio.

**2. Embed detection must use the crawl's own rendered-resource records, not page source.** Scanning raw HTML (`requests.get`) is unreliable: it misses JS-injected embeds (false negatives) and matches URLs sitting in config/menu blobs that are never rendered (false positives). Using Browsertrix's `pageinfo` records — what the real browser actually requested — resolved both. This directly demonstrates the value of high-fidelity browser-based crawling.

**3. Replay executes captured third-party scripts.** Archived ad/anti-adblock scripts re-run on replay and can display deceptive overlays. Page content is still usable, but worth flagging for any researcher-facing review.

**4. Audio/video captured as separate streams.** Adaptive-streaming players deliver video and audio as separate resources; "video captured" does not imply "audio captured." Not fully resolved from the WARC in this trial (scoped out); the yt-dlp fallback sidesteps it by re-fetching complete video+audio.

## Recommendation

Adopt Browsertrix as the primary archival crawler. Pair it with a yt-dlp fallback for YouTube-embedded video, triggered off the crawl's `pageinfo` records (implemented: `scripts/report_missing_videos.py` → `scripts/download_videos.py`).

## Artifacts

- `crawls/collections/browsertrix-trial-2-autoplay/` — crawl output (WACZ)
- `reports/missing_videos.json` — pages with real YouTube embeds Browsertrix missed
- `data/videos/video_index.json` — recovered videos (3/3 success)