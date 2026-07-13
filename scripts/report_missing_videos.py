import io
import json
import re
import zipfile
from pathlib import Path

from warcio.archiveiterator import ArchiveIterator

PROJECT_ROOT = Path(__file__).resolve().parent.parent
WACZ_PATH = PROJECT_ROOT / "crawls/collections/browsertrix-trial/browsertrix-trial.wacz"
OUTPUT_JSON = PROJECT_ROOT / "reports/missing_videos.json"

# A YouTube embed resource the RENDERED page actually requested.
YT_EMBED_RE = re.compile(r"(?:youtube\.com/embed/|youtu\.be/)([a-zA-Z0-9_-]{11})")


def iter_pageinfo(wacz_path: Path):
    with zipfile.ZipFile(wacz_path) as z:
        warc_names = [n for n in z.namelist() if n.startswith("archive/") and n.endswith(".warc.gz")]
        for warc_name in warc_names:
            data = io.BytesIO(z.read(warc_name))
            for record in ArchiveIterator(data):
                uri = record.rec_headers.get_header("WARC-Target-URI") or ""
                if uri.startswith("urn:pageinfo:"):
                    page_url = uri[len("urn:pageinfo:"):]
                    try:
                        info = json.loads(record.content_stream().read())
                    except json.JSONDecodeError:
                        continue
                    yield page_url, info


def main():
    if not WACZ_PATH.exists():
        print(f"ERROR: {WACZ_PATH} not found.")
        return

    missing = []
    for page_url, info in iter_pageinfo(WACZ_PATH):
        urls = info.get("urls", {})

        # Real embeds: the rendered page actually requested a youtube embed URL.
        yt_ids = set()
        for resource_url in urls:
            m = YT_EMBED_RE.search(resource_url)
            if m:
                yt_ids.add(m.group(1))

        if not yt_ids:
            continue  # no real YouTube embed on this page

        # Did the page capture ANY real video bytes?
        has_video = any(
            str(meta.get("mime", "")).startswith("video/") and meta.get("status") == 200
            for meta in urls.values()
        )

        if not has_video:
            missing.append({
                "article_url": page_url,
                "youtube_ids": sorted(yt_ids),
            })

    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(missing, f, ensure_ascii=False, indent=2)

    print("Pages with a REAL (rendered) YouTube embed but NO captured video:\n")
    for a in missing:
        print(f"  {a['article_url']}")
        print(f"      -> youtube: {', '.join(a['youtube_ids'])}\n")
    print(f"{len(missing)} page(s) need yt-dlp. Written to {OUTPUT_JSON}")


if __name__ == "__main__":
    main()