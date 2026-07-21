"""Portfolio dashboard. Reads out/<domain>/report.json (and coverage.json if you
ran wayback_diff) and prints one table.

    python stats.py           # scans ./out
    python stats.py --dir out
"""
import argparse
import glob
import json
import os


def load(out_dir):
    rows = []
    for rp in sorted(glob.glob(os.path.join(out_dir, "*", "report.json"))):
        with open(rp, encoding="utf-8") as f:
            r = json.load(f)
        cov_path = os.path.join(os.path.dirname(rp), "coverage.json")
        cov = None
        if os.path.exists(cov_path):
            with open(cov_path, encoding="utf-8") as f:
                cov = json.load(f)
        src, typ = r.get("by_source", {}), r.get("by_type", {})
        rows.append({
            "domain": r.get("domain", "?"),
            "total": r.get("total_unique_urls", 0),
            "sitemap": src.get("sitemap", 0),
            "crawl": src.get("crawl", 0),          # the gap dynamic discovery added
            "page": typ.get("page", 0),
            "pag": typ.get("pagination", 0),
            "feed": typ.get("feed", 0),
            "cov": cov.get("coverage_pct") if cov else None,
            "missed": cov.get("missed") if cov else None,
        })
    return rows


def main(out_dir):
    rows = load(out_dir)
    if not rows:
        print(f"no report.json files under {out_dir}/ — run a crawl first.")
        return
    rows.sort(key=lambda r: r["total"], reverse=True)

    hdr = ["domain", "total", "sitemap", "crawl", "page", "pag", "feed", "cov%", "missed"]
    wd = max(len(r["domain"]) for r in rows + [{"domain": "domain"}]) + 2

    def fmt(v):
        return "-" if v is None else (f"{v:.1f}" if isinstance(v, float) else f"{v:,}")

    line = f"{'domain':<{wd}}" + "".join(f"{h:>11}" for h in hdr[1:])
    print(line)
    print("-" * len(line))
    tot = dict.fromkeys(["total", "sitemap", "crawl", "page", "pag", "feed", "missed"], 0)
    for r in rows:
        print(f"{r['domain']:<{wd}}" + "".join(
            f"{fmt(r[k]):>11}" for k in ["total", "sitemap", "crawl", "page", "pag", "feed", "cov", "missed"]))
        for k in tot:
            if isinstance(r[k], int):
                tot[k] += r[k]
    print("-" * len(line))
    print(f"{'TOTAL':<{wd}}" + "".join(
        f"{fmt(tot[k]):>11}" for k in ["total", "sitemap", "crawl", "page", "pag", "feed"]) +
        f"{'-':>11}{fmt(tot['missed']):>11}")
    print("\ncrawl = URLs dynamic discovery added beyond the sitemap.  "
          "cov%/missed appear only for sites you ran wayback_diff on.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="out")
    main(ap.parse_args().dir)
