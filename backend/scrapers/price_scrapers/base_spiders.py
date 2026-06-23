from abc import ABC, abstractmethod

import scrapy
from pydantic import ValidationError
from scrapy_playwright.page import PageMethod

from price_scrapers.items import ProductScraped

# URL fragments that indicate Mercado Libre redirected to an anti-bot wall
# instead of the real search results page.
_CAPTCHA_SIGNALS = ("captcha/wall", "account-verification", "/login")


class BaseMarketplaceSpider(scrapy.Spider, ABC):
    platform_name = None
    currency = None
    max_pages = 5

    # Playwright opt-in — set to True in a subclass to route requests through
    # a real Chromium browser (requires scrapy-playwright to be installed and
    # `playwright install chromium` to have been run).
    use_playwright = False
    # Optional CSS selector to wait for before Scrapy hands the response to
    # parse(). Only used when use_playwright is True.
    playwright_wait_selector = None
    # Named playwright context to use (must be declared in PLAYWRIGHT_CONTEXTS).
    # Override in subclasses that need a persistent / specialised context.
    playwright_context = "default"

    # How long (ms) to wait for playwright_wait_selector before giving up on
    # a single page.  Kept generous to handle slow connections, but the
    # TimeoutError is caught so one slow page does not kill the whole crawl.
    playwright_selector_timeout = 30000

    def __init__(self, search_query="", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.search_query = search_query

    @abstractmethod
    def get_product_container(self, response):
        """Return products HTML List"""
        pass

    @abstractmethod
    def extract_title(self, product):
        """Extracts product title"""
        pass

    @abstractmethod
    def extract_price(self, product):
        """Extracts product price"""
        pass

    @abstractmethod
    def extract_link(self, product):
        """Extracts product link"""
        pass

    @abstractmethod
    def extract_image(self, product):
        """Extracts product image"""
        pass

    @abstractmethod
    def build_page_url(self, page_number):
        """Build page URL for pagination"""
        pass

    def extract_location(self, product):
        """Extracts product location (optional, for local/C2C listings)."""
        return None

    def clean_price(self, price_str):
        return price_str.replace(",", "").strip()

    def _is_captcha_wall(self, response) -> bool:
        """Return True if the response looks like an anti-bot wall."""
        url = response.url
        for signal in _CAPTCHA_SIGNALS:
            if signal in url:
                return True
        return False

    def start_requests(self):
        for page_number in range(1, self.max_pages + 1):
            url = self.build_page_url(page_number=page_number)
            if self.use_playwright:
                meta: dict = {
                    "playwright": True,
                    "playwright_context": self.playwright_context,
                    # Prevent a single page timeout from raising an unhandled
                    # exception that aborts the whole spider.
                    "playwright_page_methods": [],
                }
                if self.playwright_wait_selector:
                    meta["playwright_page_methods"] = [
                        PageMethod(
                            "wait_for_selector",
                            self.playwright_wait_selector,
                            timeout=self.playwright_selector_timeout,
                            state="attached",
                        )
                    ]
                # errback lets us log timeouts/navigation errors without
                # crashing the whole crawl.
                yield scrapy.Request(
                    url=url,
                    callback=self.parse,
                    errback=self.handle_playwright_error,
                    meta=meta,
                )
            else:
                yield scrapy.Request(url=url, callback=self.parse)

    def handle_playwright_error(self, failure):
        """Log Playwright page-level errors (timeout, navigation) as warnings."""
        self.logger.warning(
            "Playwright request failed — skipping page. "
            f"URL: {failure.request.url} | Error: {failure.value}"
        )

    def parse(self, response):
        # ------------------------------------------------------------------
        # Captcha / anti-bot wall detection
        # ------------------------------------------------------------------
        if self._is_captcha_wall(response):
            self.logger.warning(
                "Anti-bot wall detected — skipping page. "
                f"Redirected to: {response.url}"
            )
            return

        products = self.get_product_container(response)

        if not products:
            self.logger.warning(
                f"No product containers found on {response.url} — "
                "possible anti-bot redirect or selector mismatch."
            )

        for product in products:
            title = self.extract_title(product=product)

            link = self.extract_link(product=product)

            image = self.extract_image(product=product)

            price = self.extract_price(product=product)

            location = self.extract_location(product=product)

            item = self._validate_and_create_item(
                image=image,
                title=title,
                price=price,
                link=link,
                location=location,
            )

            if item:
                yield item

    def _validate_and_create_item(self, title, price, link, image, location=None):
        """Validate data and create ProductScraped"""

        if not price or not link or not title:
            self.logger.warning(
                f"Invalid product: price: {price}, link: {link}, title: {title}"
            )
            return None

        price = float(self.clean_price(price))

        try:
            product_scraped = ProductScraped(
                **{
                    "title": title,
                    "price": price,
                    "image": image,
                    "platform": self.platform_name,
                    "currency": self.currency,
                    "link": link,
                    "location": location,
                }
            )

            return product_scraped.model_dump(mode="json")
        except ValidationError as e:
            self.logger.warning(f"Invalid Product: {e}")
            self.logger.debug(
                f"Data: title: {title}, price: {price}, image: {image}, "
                f"platform: {self.platform_name}, currency: {self.currency}, "
                f"link: {link}"
            )
            return None
