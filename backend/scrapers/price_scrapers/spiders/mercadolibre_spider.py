from urllib.parse import urlparse, urlunparse

from price_scrapers.base_spiders import BaseMarketplaceSpider
from price_scrapers.settings import ML_STATE_PATH


class MercadoLibreSpider(BaseMarketplaceSpider):
    name = "mercadolibre"
    allowed_domains = ["mercadolibre.com.mx"]
    platform_name = "Mercado Libre"
    currency = "MXN"

    # Mercado Libre serves an anti-bot "account-verification" page to plain
    # HTTP requests; a real browser (Playwright) loads the actual listings.
    use_playwright = True
    playwright_wait_selector = "li.ui-search-layout__item"
    # Use the persistent "ml" context (cookies/localStorage survive across
    # runs) to build session trust and reduce CAPTCHA frequency.
    # storage_state is loaded at startup (settings.py) if the file exists, and
    # saved after the first successful response by PlaywrightStateMiddleware.
    playwright_context = "ml"
    # Path where PlaywrightStateMiddleware will save the context state.
    playwright_state_path = ML_STATE_PATH

    def get_product_container(self, response):
        return response.css("li.ui-search-layout__item")

    def extract_title(self, product):
        return product.css("a.poly-component__title::text").get()

    def extract_price(self, product):
        return product.css(".andes-money-amount__fraction::text").get()

    def extract_link(self, product):
        raw_link = product.css("a.poly-component__title::attr(href)").get()
        return self.normalize_url(raw_link) if raw_link else None

    def normalize_url(self, url):
        """Remove tracking parameters from MercadoLibre URLs"""
        if not url:
            return url

        parsed = urlparse(url)

        normalized = urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                parsed.query,
                "",
            )
        )

        return normalized

    def extract_image(self, product):
        return product.css("img.poly-component__picture::attr(src)").get()

    def build_page_url(self, page_number):
        if page_number == 1:
            url = f"https://listado.mercadolibre.com.mx/{self.search_query}"
        else:
            offset = (page_number - 1) * 50 + 1
            url = (
                f"https://listado.mercadolibre.com.mx/"
                f"{self.search_query}_Desde_{offset}_NoIndex_True"
            )

        return url
