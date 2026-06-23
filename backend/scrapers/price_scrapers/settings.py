# Scrapy settings for price_scrapers project
#
# For simplicity, this file contains only settings considered important or
# commonly used. You can find more settings consulting the documentation:
#
#     https://docs.scrapy.org/en/latest/topics/settings.html
#     https://docs.scrapy.org/en/latest/topics/downloader-middleware.html
#     https://docs.scrapy.org/en/latest/topics/spider-middleware.html

import os

BOT_NAME = "price_scrapers"

SPIDER_MODULES = ["price_scrapers.spiders"]
NEWSPIDER_MODULE = "price_scrapers.spiders"

ADDONS = {}


# Crawl responsibly by identifying yourself (and your website) on the user-agent
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Obey robots.txt rules
# NOTE: sites that block scrapers via robots.txt (e.g. Mercado Libre) may
# require disabling this per-run: `scrapy crawl <spider> -s ROBOTSTXT_OBEY=False`
ROBOTSTXT_OBEY = True

# Concurrency and throttling settings
# CONCURRENT_REQUESTS = 16
CONCURRENT_REQUESTS_PER_DOMAIN = 1
DOWNLOAD_DELAY = 2

# AUTOTHROTTLE_ENABLED = True
# AUTOTHROTTLE_START_DELAY = 1
# AUTOTHROTTLE_MAX_DELAY = 3
# AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0

# Disable cookies (enabled by default)
# COOKIES_ENABLED = False

# Disable Telnet Console (enabled by default)
# TELNETCONSOLE_ENABLED = False

# Override the default request headers:
DEFAULT_REQUEST_HEADERS = {
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}

# Enable or disable spider middlewares
# See https://docs.scrapy.org/en/latest/topics/spider-middleware.html
# SPIDER_MIDDLEWARES = {
#    "price_scrapers.middlewares.PriceScrapersSpiderMiddleware": 543,
# }

# Enable or disable downloader middlewares
# See https://docs.scrapy.org/en/latest/topics/downloader-middleware.html
# DOWNLOADER_MIDDLEWARES = {
#    "price_scrapers.middlewares.PriceScrapersDownloaderMiddleware": 543,
# }
DOWNLOADER_MIDDLEWARES = {
    # Saves Playwright context storage state after the first successful
    # response for any spider that declares a `playwright_state_path`
    # attribute (e.g. MercadoLibreSpider).  Runs late (priority 900) so
    # other middleware can process the response first.
    "price_scrapers.middlewares.PlaywrightStateMiddleware": 900,
}

# Enable or disable extensions
# See https://docs.scrapy.org/en/latest/topics/extensions.html
# EXTENSIONS = {
#    "scrapy.extensions.telnet.TelnetConsole": None,
# }

# Configure item pipelines
# See https://docs.scrapy.org/en/latest/topics/item-pipeline.html
ITEM_PIPELINES = {
    "price_scrapers.pipelines.DatabasePipeline": 300,
}

# Enable and configure the AutoThrottle extension (disabled by default)
# See https://docs.scrapy.org/en/latest/topics/autothrottle.html
# AUTOTHROTTLE_ENABLED = True
# The initial download delay
# AUTOTHROTTLE_START_DELAY = 5
# The maximum download delay to be set in case of high latencies
# AUTOTHROTTLE_MAX_DELAY = 60
# The average number of requests Scrapy should be sending in parallel to
# each remote server
# AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0
# Enable showing throttling stats for every response received:
# AUTOTHROTTLE_DEBUG = False

# Enable and configure HTTP caching (disabled by default)
# See https://docs.scrapy.org/en/latest/topics/downloader-middleware.html#httpcache-middleware-settings
# HTTPCACHE_ENABLED = True
# HTTPCACHE_EXPIRATION_SECS = 0
# HTTPCACHE_DIR = "httpcache"
# HTTPCACHE_IGNORE_HTTP_CODES = []
# HTTPCACHE_STORAGE = "scrapy.extensions.httpcache.FilesystemCacheStorage"

# Set settings whose default value is deprecated to a future-proof value
FEED_EXPORT_ENCODING = "utf-8"

# ---------------------------------------------------------------------------
# Playwright (real browser) — required to get past anti-bot / JS-rendered pages
# Spiders opt in by setting `use_playwright = True` on the spider class.
# ---------------------------------------------------------------------------
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
DOWNLOAD_HANDLERS = {
    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
}
PLAYWRIGHT_BROWSER_TYPE = "chromium"

# Anti-headless-detection flags:
#   --disable-blink-features=AutomationControlled  suppresses the
#     navigator.webdriver property used by sites to detect headless Chrome.
#   --disable-dev-shm-usage  avoids /dev/shm crashes in constrained envs.
PLAYWRIGHT_LAUNCH_OPTIONS = {
    "headless": True,
    "args": [
        "--disable-blink-features=AutomationControlled",
        "--disable-dev-shm-usage",
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-infobars",
        "--window-size=1920,1080",
    ],
}

PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT = 45000

# ---------------------------------------------------------------------------
# Named browser contexts.
#
# "ml"      — Isolated context for Mercado Libre with Mexican locale and
#             timezone so fingerprinting looks like a real Mexico City user.
#             Persistent storage state (cookies / localStorage) is written by
#             the PlaywrightStateExtension after each crawl and reloaded here
#             on the next run so the site builds trust in the "session".
#
# "default" — Generic context used by any spider that does not request a
#             named context via playwright_context = "...".
# ---------------------------------------------------------------------------
_PW_STATE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    ".pw_state",
)
os.makedirs(_PW_STATE_DIR, exist_ok=True)

# Path to the Mercado Libre browser state file.  Exported by the extension on
# close; loaded here at startup only when the file actually exists (a missing
# file would cause Playwright to raise FileNotFoundError).
ML_STATE_PATH = os.path.join(_PW_STATE_DIR, "ml_state.json")

_ml_context: dict = {
    "user_agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "locale": "es-MX",
    "timezone_id": "America/Mexico_City",
    "viewport": {"width": 1920, "height": 1080},
}
if os.path.isfile(ML_STATE_PATH):
    _ml_context["storage_state"] = ML_STATE_PATH

PLAYWRIGHT_CONTEXTS = {
    "ml": _ml_context,
    "default": {
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "locale": "es-MX",
        "viewport": {"width": 1280, "height": 900},
    },
}
