import scrapy


class ArticleItem(scrapy.Item):
    """Field names deliberately match the plan's section 7.3
    article_metadata schema — so this output can later be loaded
    into SQLite/PostgreSQL without renaming anything."""
    normalized_url = scrapy.Field()
    canonical_url = scrapy.Field()
    domain = scrapy.Field()
    title = scrapy.Field()
    description = scrapy.Field()
    authors = scrapy.Field()
    published_at = scrapy.Field()
    modified_at = scrapy.Field()
    section = scrapy.Field()
    tags = scrapy.Field()
    image_url = scrapy.Field()
    outbound_links = scrapy.Field()
    language = scrapy.Field()