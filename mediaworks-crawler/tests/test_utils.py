import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mwcrawler.utils import (classify, in_scope, is_asset, is_pagination,
                             next_page, normalize, page_number)


def test_normalize_dedupes_tracking_and_case():
    a = normalize("https://Ripost.hu/x?utm_source=fb&fbclid=1")
    b = normalize("https://ripost.hu/x")
    assert a == b == "https://ripost.hu/x"


def test_scope_and_subdomains():
    assert in_scope("https://ripost.hu/x", "ripost.hu")
    assert in_scope("https://api.ripost.hu/x", "ripost.hu")     # subdomain kept
    assert not in_scope("https://facebook.com/ripost", "ripost.hu")


def test_assets_detected():
    assert is_asset("https://ripost.hu/a/b/icon.svg")
    assert is_asset("https://ripost.hu/chunk-ABC.js")
    assert not is_asset("https://ripost.hu/politik/2026/06/x")


def test_pagination_parsing():
    assert page_number("https://ripost.hu/rovat/sport?page=7816") == 7816
    assert page_number("https://x.hu/news/page/3") == 3
    assert page_number("https://ripost.hu/rovat/sport") is None
    assert is_pagination("https://ripost.hu/rovat/sport?page=2")


def test_next_page_increment_and_seed():
    assert next_page("https://ripost.hu/rovat/sport?page=2") == "https://ripost.hu/rovat/sport?page=3"
    assert next_page("https://x.hu/n/page/3") == "https://x.hu/n/page/4"
    # first page with no param -> page 2
    assert next_page("https://ripost.hu/rovat/sport") == "https://ripost.hu/rovat/sport?page=2"


def test_classify():
    assert classify("https://ripost.hu/icon.svg") == "asset"
    assert classify("https://ripost.hu/rovat/sport?page=2") == "pagination"
    assert classify("https://ripost.hu/publicapi/hu/rss/x") == "feed"
    assert classify("https://ripost.hu/politik/2026/06/x") == "page"


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call(["python", "-m", "pytest", "-q", __file__]))
