"""OLX México spider for second-hand / C2C listings.

OLX Mexico uses a Next.js-based design system with ``data-ds-component``
attributes as primary selectors.  The selectors below were determined by
cross-referencing multiple OLX scrapers targeting the same design system
(shared across OLX Group properties in Latin America) and confirmed via
Spider Cloud's public OLX scraper documentation.

NOTE: OLX serves its pages as server-side-rendered Next.js HTML, so
standard Scrapy HTTP requests capture the initial HTML payload.  However,
if Cloudflare protection or bot-detection is active the spider will need a
rotating proxy or a headless middleware (e.g. scrapy-playwright) to
retrieve real listing HTML.  The selectors below target the SSR markup;
validate them in a real browser's DevTools (F12) before production use.

Example run::

    scrapy crawl olx_mx -a search_query=iphone -o results.json

    # With custom page limit:
    scrapy crawl olx_mx -a search_query=iphone -s CLOSESPIDER_PAGECOUNT=3
"""

from urllib.parse import quote_plus, urlparse, urlunparse

from price_scrapers.base_spiders import BaseMarketplaceSpider
from price_scrapers.items import ProductScraped
from pydantic import ValidationError


class OlxMxSpider(BaseMarketplaceSpider):
    """Spider for olx.com.mx — peer-to-peer classifieds (C2C).

    Search URL pattern:
        https://www.olx.com.mx/items/q-<query>?page=<N>

    Card selectors (OLX design-system ``data-ds-component`` attributes):
        Container : ``[data-ds-component='DS-AdCard']``
        Title     : ``h2`` (first h2 within card)
        Price     : ``[data-ds-component='DS-Text'] span`` (first span)
        Link      : ``a`` (outermost anchor in card, href attribute)
        Image     : ``img`` (first img in card, src attribute)
        Location  : ``[data-ds-component='DS-LocationDate'] span``
                    (first span — city/state; second span is the date)
    """

    name = "olx_mx"
    allowed_domains = ["olx.com.mx"]
    platform_name = "OLX México"
    currency = "MXN"

    # ------------------------------------------------------------------ #
    # URL construction                                                     #
    # ------------------------------------------------------------------ #

    def build_page_url(self, page_number: int) -> str:
        """Return the search URL for *page_number*.

        OLX Mexico uses a simple ``?page=N`` query parameter (1-indexed).
        Page 1 is served without the parameter as well, but including it is
        harmless and keeps the logic uniform.
        """
        encoded_query = quote_plus(self.search_query)
        return (
            f"https://www.olx.com.mx/items/q-{encoded_query}?page={page_number}"
        )

    # ------------------------------------------------------------------ #
    # Container                                                            #
    # ------------------------------------------------------------------ #

    def get_product_container(self, response):
        """Return all ad-card elements on the search results page."""
        return response.css("[data-ds-component='DS-AdCard']")

    # ------------------------------------------------------------------ #
    # Field extractors                                                     #
    # ------------------------------------------------------------------ #

    def extract_title(self, product) -> str | None:
        """Extract listing title from the card's first ``<h2>``."""
        return product.css("h2::text").get()

    def extract_price(self, product) -> str | None:
        """Extract price text from the DS-Text component span.

        OLX renders the price inside a nested ``<span>`` within the
        ``[data-ds-component='DS-Text']`` element.  The first such span
        on a card is always the price; subsequent spans hold secondary
        info (e.g. "Precio negociable").
        """
        return product.css("[data-ds-component='DS-Text'] span::text").get()

    def extract_link(self, product) -> str | None:
        """Extract the listing URL from the card's anchor element."""
        raw = product.css("a::attr(href)").get()
        return self.normalize_url(raw) if raw else None

    def extract_image(self, product) -> str | None:
        """Extract the thumbnail image URL.

        OLX lazy-loads images; the ``src`` attribute holds the actual URL
        in the SSR payload.  If the page is fully JS-rendered, ``src`` may
        be a placeholder and the real URL will be in ``data-src``.  We try
        ``src`` first and fall back to ``data-src``.
        """
        return (
            product.css("img::attr(src)").get()
            or product.css("img::attr(data-src)").get()
        )

    def extract_location(self, product) -> str | None:
        """Extract the city/location label from the DS-LocationDate span.

        The ``DS-LocationDate`` component renders two ``<span>`` children:
          - index 0: location string (e.g. "Ciudad de México, CDMX")
          - index 1: relative date (e.g. "hace 2 horas")

        We take the first span only.
        """
        return product.css(
            "[data-ds-component='DS-LocationDate'] span::text"
        ).get()

    # ------------------------------------------------------------------ #
    # URL normalisation                                                    #
    # ------------------------------------------------------------------ #

    def normalize_url(self, url: str | None) -> str | None:
        """Strip OLX tracking query parameters, keeping only the path.

        OLX appends UTM parameters and internal tracking tokens to listing
        URLs.  We retain scheme + netloc + path and discard all query
        strings and fragments.
        """
        if not url:
            return url
        parsed = urlparse(url)
        # Resolve relative URLs that omit the scheme/host
        if not parsed.netloc:
            url = f"https://www.olx.com.mx{url}"
            parsed = urlparse(url)
        return urlunparse(
            (parsed.scheme, parsed.netloc, parsed.path, "", "", "")
        )

    # ------------------------------------------------------------------ #
    # Item creation (overridden to inject location)                       #
    # ------------------------------------------------------------------ #

    def parse(self, response):
        """Override parse to thread ``location`` through item creation."""
        products = self.get_product_container(response)

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

    def _validate_and_create_item(
        self,
        title: str | None,
        price: str | None,
        link: str | None,
        image: str | None,
        location: str | None = None,
    ) -> dict | None:
        """Validate fields and build a ``ProductScraped`` dict.

        Extends the base implementation to include the ``location`` field
        that BaseMarketplaceSpider's version omits.
        """
        if not price or not link or not title:
            self.logger.warning(
                f"Invalid product: price={price!r}, link={link!r}, "
                f"title={title!r}"
            )
            return None

        try:
            cleaned_price = float(self.clean_price(price))
        except ValueError:
            self.logger.warning(f"Could not parse price: {price!r}")
            return None

        try:
            product_scraped = ProductScraped(
                title=title,
                price=cleaned_price,
                image=image,
                location=location,
                platform=self.platform_name,
                currency=self.currency,
                link=link,
            )
            return product_scraped.model_dump(mode="json")
        except ValidationError as e:
            self.logger.warning(f"Invalid Product: {e}")
            self.logger.debug(
                f"Data: title={title!r}, price={cleaned_price!r}, "
                f"image={image!r}, location={location!r}, "
                f"platform={self.platform_name!r}, "
                f"currency={self.currency!r}, link={link!r}"
            )
            return None
