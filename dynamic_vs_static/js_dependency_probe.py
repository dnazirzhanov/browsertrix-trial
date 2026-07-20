#!/usr/bin/env python3
"""
js_dependency_probe.py — decide, per outlet, whether URL discovery needs a headless browser.

Method (per page):
    S1 = static fetch  (t0)
    D  = browser fetch (t1)  -- with scroll + consent click
    S2 = static fetch  (t2)

    churn      = |S1 symmetric-difference S2|      <- noise floor: the page mutating over time
    js_only    = D - (S1 | S2)                     <- links ONLY the browser ever saw
    static_only= (S1 & S2) - D                     <- stable static links the browser missed
                                                      (consent wall / JS rewrite / nav collapse)

A js_only count that does not exceed `churn` is not evidence of JS dependency.

Usage:
    pip install requests beautifulsoup4 lxml playwright
    playwright install chromium
    python js_dependency_probe.py --config outlets.yaml --out data/probe/
    python js_dependency_probe.py --url https://ripost.hu/ --article-re '/\\d{4}/\\d{2}/'
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

# Identical in BOTH arms. If the arms use different User-Agents you are measuring
# bot-blocking, not JavaScript. Honest UA is the right default for an archival
# project; if it gets you 403s, that is itself a finding worth recording.
USER_AGENT = "CausaliaResearchBot/0.1 (+mailto:you@example.org)"

REQUEST_TIMEOUT = 20
NAV_TIMEOUT_MS = 30_000
POLITENESS_DELAY = 2.0      # seconds between requests to the same host
SCROLL_ROUNDS = 8           # max lazy-load scroll iterations
SCROLL_PAUSE_MS = 1_200

# Params stripped before comparison. Conservative on purpose: `id`, `p`, `page`
# etc. are load-bearing on some CMSes and must NOT be dropped.
TRACKING_KEYS = {
    "fbclid", "gclid", "gbraid", "wbraid", "msclkid", "igshid", "yclid",
    "mc_cid", "mc_eid", "_ga", "ref_src", "ref_url", "cmpid", "cmp",
}

# Best-effort consent dismissal. Order matters: framework selectors first,
# then Hungarian/English button text.
CONSENT_SELECTORS = [
    "#onetrust-accept-btn-handler",
    "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
    "button#didomi-notice-agree-button",
    "[aria-label*='Elfogad' i]",
    "button:has-text('Elfogadom')",
    "button:has-text('Összes elfogadása')",
    "button:has-text('Elfogad')",
    "button:has-text('Accept all')",
    "button:has-text('I agree')",
]

# Fallback article heuristic, used only when an outlet has no `article_re`.
# Derive a real regex per outlet from ~20 sitemap URLs -- it is 5 minutes of work
# and far more reliable than this.
DEFAULT_ARTICLE_RE = re.compile(r"/\d{4}/\d{2}/|/\d{6,}|-\w+-\w+-\w+")
NON_ARTICLE_PATH_HINTS = (
    "/tag/", "/cimke/", "/cimkek/", "/szerzo/", "/author/", "/kereses/",
    "/search", "/rss", "/sitemap", "/galeria/oldal/", "/page/", "/oldal/",
)


# --------------------------------------------------------------------------
# URL normalization  (shared by both arms -- this is what makes them comparable)
# --------------------------------------------------------------------------

def registrable_host(host: str) -> str:
    host = (host or "").lower()
    return host[4:] if host.startswith("www.") else host


def normalize(link: str, base: str) -> Optional[str]:
    """Absolute, tracking-free, scheme-stable comparison key. None = not comparable."""
    if not link or link.startswith(("javascript:", "mailto:", "tel:", "#", "data:")):
        return None
    try:
        absu = urljoin(base, link.strip())
        p = urlsplit(absu)
    except ValueError:
        return None
    if p.scheme not in ("http", "https"):
        return None

    host = registrable_host(p.hostname or "")
    if not host:
        return None

    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
         if not k.lower().startswith("utm_") and k.lower() not in TRACKING_KEYS]
    q.sort()

    path = p.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    # Scheme forced to https: http->https upgrades in-browser would otherwise
    # register as fake "JS-only" links. Fragment dropped by omission.
    return urlunsplit(("https", host, path, urlencode(q), ""))


def in_scope(url: str, base_host: str) -> bool:
    h = registrable_host(urlsplit(url).hostname or "")
    return h == base_host or h.endswith("." + base_host)


def is_article(url: str, article_re: Optional[re.Pattern]) -> bool:
    path = urlsplit(url).path.lower()
    if any(hint in path for hint in NON_ARTICLE_PATH_HINTS):
        return False
    rx = article_re or DEFAULT_ARTICLE_RE
    return bool(rx.search(url))


def link_set(raw: Iterable[str], base: str, base_host: str,
             article_re: Optional[re.Pattern]) -> tuple[set, set]:
    """-> (all in-scope links, article links). Both normalized."""
    all_links, articles = set(), set()
    for link in raw:
        n = normalize(link, base)
        if not n or not in_scope(n, base_host):
            continue
        all_links.add(n)
        if is_article(n, article_re):
            articles.add(n)
    return all_links, articles


# --------------------------------------------------------------------------
# Arm 1: static
# --------------------------------------------------------------------------

def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "hu-HU,hu;q=0.9,en;q=0.8",
    })
    retry = Retry(total=2, backoff_factor=1.0,
                  status_forcelist=[429, 500, 502, 503, 504],
                  allowed_methods=["GET"])
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    return s


def fetch_static(session, url, base_host, article_re):
    """-> (all_links, articles, status_code, elapsed, error)"""
    t0 = time.time()
    try:
        r = session.get(url, timeout=REQUEST_TIMEOUT)
    except Exception as e:
        return set(), set(), None, time.time() - t0, f"{type(e).__name__}: {e}"
    elapsed = time.time() - t0

    if r.status_code >= 400:
        return set(), set(), r.status_code, elapsed, f"HTTP {r.status_code}"

    soup = BeautifulSoup(r.text, "lxml")
    # Honor <base href> exactly as the browser does, and resolve against the
    # POST-redirect URL, not the URL we asked for.
    base_tag = soup.find("base", href=True)
    base = urljoin(str(r.url), base_tag["href"]) if base_tag else str(r.url)

    raw = [a["href"] for a in soup.find_all("a", href=True)]
    all_links, articles = link_set(raw, base, base_host, article_re)
    return all_links, articles, r.status_code, elapsed, None


# --------------------------------------------------------------------------
# Arm 2: browser
# --------------------------------------------------------------------------

def dismiss_consent(page) -> bool:
    for sel in CONSENT_SELECTORS:
        try:
            el = page.locator(sel).first
            if el.is_visible(timeout=800):
                el.click(timeout=2_000)
                page.wait_for_timeout(600)
                return True
        except Exception:
            continue
    return False


def autoscroll(page) -> int:
    """Trigger lazy-loading. Returns rounds actually performed."""
    last = page.evaluate("document.body.scrollHeight")
    for i in range(SCROLL_ROUNDS):
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(SCROLL_PAUSE_MS)
        height = page.evaluate("document.body.scrollHeight")
        if height == last:
            return i + 1
        last = height
    return SCROLL_ROUNDS


def fetch_dynamic(context, url, base_host, article_re):
    """-> dict of results. Browser launch cost is NOT included in nav_seconds."""
    page = context.new_page()
    page.set_default_timeout(NAV_TIMEOUT_MS)
    out = {"status": None, "error": None, "consent_clicked": False,
           "scroll_rounds": 0, "nav_seconds": 0.0}
    t0 = time.time()
    try:
        resp = page.goto(url, wait_until="load", timeout=NAV_TIMEOUT_MS)
        out["status"] = resp.status if resp else None

        # networkidle frequently never fires on ad-heavy news sites. Best effort.
        try:
            page.wait_for_load_state("networkidle", timeout=8_000)
        except Exception:
            pass

        out["consent_clicked"] = dismiss_consent(page)
        out["scroll_rounds"] = autoscroll(page)

        raw = page.evaluate(
            "() => Array.from(document.querySelectorAll('a[href]')).map(a => a.href)"
        )
        base = page.url
        all_links, articles = link_set(raw, base, base_host, article_re)
        out["all_links"], out["articles"] = all_links, articles
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
        out["all_links"], out["articles"] = set(), set()
    finally:
        out["nav_seconds"] = time.time() - t0
        page.close()
    return out


# --------------------------------------------------------------------------
# Decision
# --------------------------------------------------------------------------

@dataclass
class PageResult:
    outlet: str
    url: str
    page_type: str
    static_status: Optional[int] = None
    dynamic_status: Optional[int] = None
    static_error: Optional[str] = None
    dynamic_error: Optional[str] = None
    consent_clicked: bool = False
    scroll_rounds: int = 0
    static_all: int = 0
    dynamic_all: int = 0
    static_articles: int = 0      # |S1 & S2|, the stable static set
    dynamic_articles: int = 0     # |D|
    churn: int = 0                # noise floor
    js_only: int = 0
    static_only: int = 0
    js_only_ratio: float = 0.0
    static_seconds: float = 0.0
    dynamic_nav_seconds: float = 0.0
    decision: str = ""
    reason: str = ""
    js_only_samples: list = field(default_factory=list)
    static_only_samples: list = field(default_factory=list)


def decide(r: PageResult) -> tuple[str, str]:
    if r.static_error and r.dynamic_error:
        return "FAILED", "both arms failed; nothing to compare"
    if r.static_status and r.static_status >= 400 and (r.dynamic_status or 0) < 400:
        return "BLOCKED_STATIC", (f"static got HTTP {r.static_status} while the browser got "
                                  f"{r.dynamic_status} — this is bot-blocking, NOT a JS finding. "
                                  "Fix headers/TLS before judging JS dependency.")
    if r.dynamic_articles == 0 and r.static_articles == 0:
        return "NO_DATA", "neither arm found article links — article_re is probably wrong"
    if r.static_only > max(3, 0.10 * max(r.dynamic_articles, 1)):
        return "INVESTIGATE", (f"{r.static_only} stable static links absent from the browser run "
                               "— consent wall, JS rewriting the DOM, or a failed render. "
                               "Do not trust this comparison yet.")
    if r.dynamic_articles == 0:
        return "INVESTIGATE", "browser found no articles but static did — likely a broken render"
    if r.js_only <= r.churn:
        return "STATIC_OK", (f"JS-only links ({r.js_only}) do not exceed the churn floor "
                             f"({r.churn}) — the difference is the page mutating, not JS")
    if r.js_only_ratio <= 0.05:
        return "STATIC_OK", f"static reaches {(1 - r.js_only_ratio) * 100:.1f}% of article links"
    if r.js_only_ratio <= 0.25:
        return "MIXED", (f"static misses {r.js_only_ratio * 100:.1f}% of article links — usable "
                         "with sitemap/RSS backfill; browser only if that gap matters")
    return "BROWSER_NEEDED", f"static misses {r.js_only_ratio * 100:.1f}% of article links"


# --------------------------------------------------------------------------
# Probe
# --------------------------------------------------------------------------

def probe_page(session, context, outlet, url, page_type, article_re) -> PageResult:
    base_host = registrable_host(urlsplit(url).hostname or "")
    r = PageResult(outlet=outlet, url=url, page_type=page_type)

    # S1
    s1_all, s1_art, s1_status, s1_time, s1_err = fetch_static(session, url, base_host, article_re)
    time.sleep(POLITENESS_DELAY)

    # D  (between the two static fetches, so churn brackets it)
    d = fetch_dynamic(context, url, base_host, article_re)
    time.sleep(POLITENESS_DELAY)

    # S2 — the control
    s2_all, s2_art, s2_status, s2_time, s2_err = fetch_static(session, url, base_host, article_re)

    stable_static = s1_art & s2_art
    union_static = s1_art | s2_art
    churn = len(s1_art ^ s2_art)
    js_only = d["articles"] - union_static
    static_only = stable_static - d["articles"]

    r.static_status, r.dynamic_status = s1_status, d["status"]
    r.static_error, r.dynamic_error = s1_err, d["error"]
    r.consent_clicked, r.scroll_rounds = d["consent_clicked"], d["scroll_rounds"]
    r.static_all, r.dynamic_all = len(s1_all), len(d["all_links"])
    r.static_articles, r.dynamic_articles = len(stable_static), len(d["articles"])
    r.churn, r.js_only, r.static_only = churn, len(js_only), len(static_only)
    r.js_only_ratio = len(js_only) / len(d["articles"]) if d["articles"] else 0.0
    r.static_seconds = (s1_time + s2_time) / 2
    r.dynamic_nav_seconds = d["nav_seconds"]
    r.js_only_samples = sorted(js_only)[:5]
    r.static_only_samples = sorted(static_only)[:5]
    r.decision, r.reason = decide(r)
    return r


def load_outlets(path: Optional[str], url: Optional[str],
                 article_re: Optional[str]) -> list[dict]:
    if url:
        return [{"name": registrable_host(urlsplit(url).hostname or "site"),
                 "article_re": article_re,
                 "pages": [{"url": url, "type": "homepage"}]}]
    import yaml  # only needed in config mode
    return yaml.safe_load(Path(path).read_text())["outlets"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", help="YAML file of outlets")
    ap.add_argument("--url", help="single URL, for a quick one-off probe")
    ap.add_argument("--article-re", help="article URL regex (single-URL mode)")
    ap.add_argument("--out", default="data/probe", help="output directory")
    ap.add_argument("--headful", action="store_true", help="watch the browser (debugging)")
    args = ap.parse_args()

    if not args.config and not args.url:
        ap.error("give --config or --url")

    outlets = load_outlets(args.config, args.url, args.article_re)
    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    from playwright.sync_api import sync_playwright

    session = make_session()
    results: list[PageResult] = []

    with sync_playwright() as p:
        t_launch = time.time()
        browser = p.chromium.launch(headless=not args.headful)
        context = browser.new_context(
            user_agent=USER_AGENT,
            locale="hu-HU",
            viewport={"width": 1440, "height": 900},
        )
        launch_cost = time.time() - t_launch
        print(f"browser launch: {launch_cost:.2f}s (one-off — amortized over all pages)\n")

        for outlet in outlets:
            name = outlet["name"]
            rx = re.compile(outlet["article_re"]) if outlet.get("article_re") else None
            if not rx:
                print(f"  ! {name}: no article_re — falling back to a weak heuristic")
            for page_cfg in outlet["pages"]:
                url, ptype = page_cfg["url"], page_cfg.get("type", "unknown")
                print(f"probing {name} [{ptype}] {url}")
                try:
                    r = probe_page(session, context, name, url, ptype, rx)
                except Exception as e:
                    r = PageResult(outlet=name, url=url, page_type=ptype,
                                   decision="FAILED", reason=f"{type(e).__name__}: {e}")
                results.append(r)
                print(f"   static={r.static_articles} browser={r.dynamic_articles} "
                      f"churn={r.churn} js_only={r.js_only} static_only={r.static_only} "
                      f"-> {r.decision}")
                print(f"   {r.reason}\n")
                time.sleep(POLITENESS_DELAY)

        context.close()
        browser.close()

    stamp = time.strftime("%Y%m%d_%H%M%S")
    jsonl_path = outdir / f"js_probe_{stamp}.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")

    csv_path = outdir / f"js_probe_{stamp}.csv"
    cols = [c for c in asdict(results[0]).keys() if not c.endswith("_samples")]
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in results:
            w.writerow({k: v for k, v in asdict(r).items() if k in cols})

    # Outlet-level roll-up: the worst page decides, since discovery must cover all of them.
    severity = {"STATIC_OK": 0, "MIXED": 1, "BROWSER_NEEDED": 2,
                "INVESTIGATE": 3, "BLOCKED_STATIC": 3, "NO_DATA": 3, "FAILED": 3}
    print("=" * 72)
    print(f"{'outlet':<24}{'verdict':<18}{'worst page'}")
    print("-" * 72)
    by_outlet: dict[str, list[PageResult]] = {}
    for r in results:
        by_outlet.setdefault(r.outlet, []).append(r)
    for name, rs in by_outlet.items():
        worst = max(rs, key=lambda r: severity.get(r.decision, 3))
        print(f"{name:<24}{worst.decision:<18}{worst.page_type}")
    print("=" * 72)
    print(f"\nwrote {jsonl_path}\n      {csv_path}")


if __name__ == "__main__":
    main()