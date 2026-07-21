BOT_NAME = "mwcrawler"
SPIDER_MODULES = ["mwcrawler.spiders"]
NEWSPIDER_MODULE = "mwcrawler.spiders"

# --- identity + rules ---------------------------------------------------
# Put a real contact address here so an admin can reach you, not just block you.
USER_AGENT = "CausaliaArchiver/1.0 (+https://example.org/bot; contact: crawler@example.org)"
ROBOTSTXT_OBEY = True          # Scrapy fetches robots.txt and skips disallowed URLs for you

# --- speed WITHOUT getting banned --------------------------------------
# AutoThrottle watches each server's response latency and speeds up or slows
# down automatically. This is how you crawl "as fast as the site can handle"
# without hammering it. It is the single most important setting here.
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 0.5
AUTOTHROTTLE_MAX_DELAY = 20.0
AUTOTHROTTLE_TARGET_CONCURRENCY = 6.0     # aim for ~6 in-flight requests per site
AUTOTHROTTLE_DEBUG = False

CONCURRENT_REQUESTS = 64                   # total across all sites at once
CONCURRENT_REQUESTS_PER_DOMAIN = 8         # ceiling per single site (politeness)
DOWNLOAD_DELAY = 0.25                      # floor; AutoThrottle adjusts upward
RANDOMIZE_DOWNLOAD_DELAY = True

# --- resilience ---------------------------------------------------------
RETRY_ENABLED = True
RETRY_TIMES = 3
RETRY_HTTP_CODES = [429, 500, 502, 503, 504, 522, 524]
DOWNLOAD_TIMEOUT = 30
AJAXCRAWL_ENABLED = False

# We control depth ourselves (homepage links + pagination), so no blind DFS.
DEPTH_PRIORITY = 1              # breadth-first: shallow pages before deep ones
SCHEDULER_DISK_QUEUE = "scrapy.squeues.PickleFifoDiskQueue"
SCHEDULER_MEMORY_QUEUE = "scrapy.squeues.FifoMemoryQueue"

ITEM_PIPELINES = {"mwcrawler.pipelines.DedupGzipPipeline": 300}

REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
LOG_LEVEL = "INFO"
