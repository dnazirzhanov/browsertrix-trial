import json
import subprocess as sp
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MISSING_JSON = PROJECT_ROOT / "reports/missing_videos.json"
VIDEOS_DIR = PROJECT_ROOT / "data/videos"
INDEX_JSON = VIDEOS_DIR / "video_index.json"

DELAY_SECONDS = 30  # politeness — avoid YouTube 429 rate limiting


def load_index():
    if INDEX_JSON.exists():
        with open(INDEX_JSON, encoding="utf-8") as f:
            return json.load(f)
    return []


def save_index(index):
    with open(INDEX_JSON, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)


def main():
    if not MISSING_JSON.exists():
        print(f"ERROR: {MISSING_JSON} missing. Run scripts/report_missing_videos.py first.")
        return

    with open(MISSING_JSON, encoding="utf-8") as f:
        missing = json.load(f)

    index = load_index()
    done = {e["video_id"] for e in index if e["status"] == "success"}

    # Dedup: same video ID may appear on multiple articles; download once.
    jobs = {}  # video_id -> article_url (first one wins)
    for article in missing:
        for vid in article["youtube_ids"]:
            jobs.setdefault(vid, article["article_url"])

    for video_id, article_url in jobs.items():
        if video_id in done:
            print(f"SKIP (already downloaded): {video_id}")
            continue

        out_dir = VIDEOS_DIR / video_id
        out_dir.mkdir(parents=True, exist_ok=True)
        cmd = [
            "yt-dlp", f"https://www.youtube.com/watch?v={video_id}",
            "-o", str(out_dir / f"{video_id}.%(ext)s"),
            "--write-info-json",
            "--no-progress",
        ]
        print(f"Downloading {video_id} ...")
        result = sp.run(cmd, capture_output=True, text=True)
        success = result.returncode == 0

        index.append({
            "article_url": article_url,
            "video_id": video_id,
            "video_url": f"https://www.youtube.com/watch?v={video_id}",
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
            "status": "success" if success else "failed",
            "error": None if success else result.stderr[-300:],
        })
        save_index(index)
        print("  OK" if success else f"  FAILED: {result.stderr[-200:]}")
        time.sleep(DELAY_SECONDS)

    print(f"\nDone. Index: {INDEX_JSON}")


if __name__ == "__main__":
    main()