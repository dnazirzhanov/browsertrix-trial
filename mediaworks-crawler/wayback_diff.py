"""Measure coverage by diffing your crawl against the Internet Archive.

The Wayback CDX API lists every URL the Archive has ever seen for a domain. If
lots of those are missing from your set, your sitemap+crawl has gaps (or orphan
pages nothing links to). This turns "did I get everything?" into a number.

    python wayback_diff.py ripost.hu out/ripost.hu/urls.txt.gz

Writes out/<domain>/wayback_only.txt.gz = URLs the Archive knows but you missed.
"""
import gzip
import json
import sys

import requests

from mwcrawler.utils import in_scope, is_asset, normalize, registrable_domain

CDX = ("http://web.archive.org/cdx/search/cdx"
       "?url={domain}*&output=text&fl=original&collapse=urlkey&limit={limit}")


def load_collected(path):
    op = gzip.open if path.endswith(".gz") else open
    with op(path, "rt", encoding="utf-8") as f:
        return {n for n in (normalize(l.strip()) for l in f) if n}


def fetch_wayback(domain, limit):
    reg = registrable_domain(domain)
    urls = set()
    with requests.get(CDX.format(domain=domain, limit=limit),
                      stream=True, timeout=120,
                      headers={"User-Agent": "CausaliaArchiver/1.0"}) as r:
        r.raise_for_status()
        for line in r.iter_lines(decode_unicode=True):
            n = normalize((line or "").strip())
            if n and not is_asset(n) and in_scope(n, reg):
                urls.add(n)
    return urls


def main(domain, collected_path, limit=500000):
    mine = load_collected(collected_path)
    theirs = fetch_wayback(domain, limit)
    missed = theirs - mine          # Archive has these, you don't
    extra = mine - theirs           # you have these, Archive doesn't

    out = f"out/{domain}/wayback_only.txt.gz"
    with gzip.open(out, "wt", encoding="utf-8") as f:
        f.write("\n".join(sorted(missed)) + "\n")

    cov = 100 * len(mine & theirs) / len(theirs) if theirs else 0.0
    with open(f"out/{domain}/coverage.json", "w", encoding="utf-8") as f:
        json.dump({"domain": domain, "mine": len(mine), "wayback": len(theirs),
                   "in_both": len(mine & theirs), "missed": len(missed),
                   "extra": len(extra), "coverage_pct": round(cov, 2)}, f, indent=2)

    print(f"your unique URLs:       {len(mine):>8}")
    print(f"wayback unique URLs:    {len(theirs):>8}")
    print(f"in both:                {len(mine & theirs):>8}")
    print(f"you MISSED (in wayback):{len(missed):>8}   -> {out}")
    print(f"you have, wayback lacks:{len(extra):>8}")
    print(f"coverage vs wayback:    {cov:6.2f}%")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("usage: python wayback_diff.py <domain> <collected_urls.txt.gz>")
    main(sys.argv[1], sys.argv[2])
