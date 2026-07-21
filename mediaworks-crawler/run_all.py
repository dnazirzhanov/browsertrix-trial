"""Crawl every domain in domains.txt concurrently in one process.

Scrapy throttles each site independently (per-domain AutoThrottle), so running
many sites at once is the RIGHT kind of parallelism: linear speedup across hosts,
still polite to each one.

    python run_all.py                 # uses domains.txt
    python run_all.py sites.txt
"""
import sys

from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings

from mwcrawler.spiders.discovery import DiscoverySpider


def main(path="domains.txt"):
    domains = [l.strip() for l in open(path)
               if l.strip() and not l.startswith("#")]
    process = CrawlerProcess(get_project_settings())
    for d in domains:
        process.crawl(DiscoverySpider, domain=d)
    process.start()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "domains.txt")
