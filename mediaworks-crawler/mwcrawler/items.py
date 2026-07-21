import scrapy


class UrlItem(scrapy.Item):
    url = scrapy.Field()        # normalized URL
    domain = scrapy.Field()     # site it belongs to
    source = scrapy.Field()     # 'sitemap' | 'crawl'
    url_type = scrapy.Field()   # 'page' | 'pagination' | 'feed' | 'asset'
