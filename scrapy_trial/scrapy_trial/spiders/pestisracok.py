import re
from urllib.parse import urlparse

from scrapy.spiders import SitemapSpider

from scrapy_trial.items import ArticleItem


class PestisracokSpider(SitemapSpider):
    name = "pestisracok"
    allowed_domains = ["pestisracok.hu"]

    # Point at robots.txt — Scrapy parses it and auto-discovers the
    # Sitemap: entries. Recon and crawling in one step.
    sitemap_urls = ["https://pestisracok.hu/robots.txt"]

    # (regex on URL) -> (callback name). Only URLs matching go to parse_article.
    # Article URLs look like /rovat/2026/06/slug, so /YYYY/MM/ filters out
    # category pages, tags, and other non-article URLs.
    sitemap_rules = [(r"/\d{4}/\d{2}/", "parse_article")]

    def parse_article(self, response):
        item = ArticleItem()

        item["normalized_url"] = response.url
        item["domain"] = urlparse(response.url).netloc.removeprefix("www.")
        item["canonical_url"] = response.css('link[rel="canonical"]::attr(href)').get()
        item["language"] = response.css("html::attr(lang)").get()

        # Prefer OpenGraph (structured, intended for machines) over <title>
        # (intended for humans, often has site-name suffixes appended).
        item["title"] = (
                response.css('meta[property="og:title"]::attr(content)').get()
                or response.css("title::text").get()
        )
        item["description"] = response.css('meta[property="og:description"]::attr(content)').get()
        item["image_url"] = response.css('meta[property="og:image"]::attr(content)').get()
        item["published_at"] = response.css('meta[property="article:published_time"]::attr(content)').get()
        item["modified_at"] = response.css('meta[property="article:modified_time"]::attr(content)').get()
        item["section"] = response.css('meta[property="article:section"]::attr(content)').get()
        item["tags"] = response.css('meta[property="article:tag"]::attr(content)').getall()
        item["authors"] = response.css('meta[name="author"]::attr(content)').getall()

        # response.urljoin() resolves relative hrefs ("/foo") against the
        # current page URL — never string-concatenate URLs by hand.
        links = [response.urljoin(h) for h in response.css("a::attr(href)").getall()]
        item["outbound_links"] = sorted({
            l for l in links
            if l.startswith("http") and urlparse(l).netloc.removeprefix("www.") != item["domain"]
        })

        yield item