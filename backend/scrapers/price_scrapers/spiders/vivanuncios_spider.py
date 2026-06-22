"""Vivanuncios Mexico spider for the price-monitor project.

Vivanuncios (vivanuncios.com.mx) is a C2C classifieds platform (Adevinta
group).  It renders listings server-side for the initial HTML response, so
plain Scrapy CSS selectors work as long as the request carries a realistic
browser User-Agent (already set globally in settings.py).

NOTE — selector validation required
------------------------------------
Vivanuncios returns HTTP 403 to plain curl / requests-based fetchers
(Cloudflare bot-management is active).  The CSS selectors below were derived
from the Adevinta shared listing-page HTML structure (the same engine powers
OLX MX / Segundamano) and from community-documented scraping patterns for the
site.  **They must be validated against a live browser session** before
treating output as reliable.  See the "Selector validation" section below for
instructions.

Pagination URL pattern
----------------------
Vivanuncios uses Adevinta's V1 URL scheme:

    https://www.vivanuncios.com.mx/s-{category}/{keywords}/v1c{cat_id}p{page}

For a keyword-only search (no category) the pattern simplifies to:

    https://www.vivanuncios.com.mx/s-mexico/{keywords}/v1c0p{page}

Where ``p1`` is page 1, ``p2`` is page 2, etc.  The spider uses the
category-free ``v1c0p{page}`` form because the search_query argument is
a free-form keyword supplied at runtime.

Selector validation
-------------------
To inspect live selectors:

1. Open https://www.vivanuncios.com.mx/s-mexico/laptop/v1c0p1 in a browser.
2. Right-click a listing card → Inspect.
3. Verify the container, title, price, link, image, and location classes
   match the constants defined in this file (SELECTORS dict).
4. Update any mismatches and re-run.

Example run (from ``backend/scrapers/``):

    scrapy crawl vivanuncios -a search_query=laptop
    scrapy crawl vivanuncios -a search_query=iphone -a max_pages=3
    scrapy crawl vivanuncios -a search_query="silla+gamer"
"""

from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

from price_scrapers.base_spiders import BaseMarketplaceSpider
from price_scrapers.items import ProductScraped
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# CSS selectors — update these after live-browser validation
# ---------------------------------------------------------------------------
# The Adevinta listing page wraps each ad in an <li> or <article> that carries
# a data-testid or a stable BEM class.  Known variants across the platform:
#
#   Container : li[data-testid="adCard"]            (testid variant)
#              article.sc-card                       (BEM variant)
#   Title     : .sc-card-content h2 a               or
#               [data-testid="adCard-title"] a
#   Price     : .price-tag span                     or
#               [data-testid="adCard-price"]
#   Link      : h2 a::attr(href)                    (relative, needs urljoin)
#   Image     : .sc-card-image img::attr(src)       or
#               [data-testid="adCard-image"] img::attr(src)
#   Location  : .sc-card-content .sc-card-location  or
#               [data-testid="adCard-location"]
#
# The selectors below use attribute-based testids first (more stable) and fall
# back to BEM class names.

_SELECTORS = {
    # Each listing card element
    "container": "li[data-testid='adCard'], article.sc-card",
    # Title text — the <a> inside the heading carries the ad title
    "title": (
        "[data-testid='adCard-title'] a::text, "
        ".sc-card-content h2 a::text, "
        "h2.sc-card-title a::text"
    ),
    # Canonical link — same <a> element, href attribute
    "link": (
        "[data-testid='adCard-title'] a::attr(href), "
        ".sc-card-content h2 a::attr(href), "
        "h2.sc-card-title a::attr(href)"
    ),
    # Price — numeric text inside the price widget
    "price": (
        "[data-testid='adCard-price']::text, "
        ".price-tag span::text, "
        ".sc-card-price span::text"
    ),
    # Thumbnail image
    "image": (
        "[data-testid='adCard-image'] img::attr(src), "
        ".sc-card-image img::attr(src), "
        "img.sc-card-img::attr(src)"
    ),
    # Human-readable location string (e.g. "Cuauhtémoc, Ciudad de México")
    "location": (
        "[data-testid='adCard-location']::text, "
        ".sc-card-location span::text, "
        ".sc-card-content .location::text"
    ),
}

_BASE_URL = "https://www.vivanuncios.com.mx"

# Tracking / session query parameters that add no semantic value
_STRIP_PARAMS = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "ref",
        "ad_id",
        "sid",
    }
)


class VivanunciosSpider(BaseMarketplaceSpider):
    """Spider for Vivanuncios Mexico (vivanuncios.com.mx).

    Inherits pagination and item-validation logic from BaseMarketplaceSpider.
    Overrides ``parse`` to extract the ``location`` field, which the base class
    does not handle (its ``_validate_and_create_item`` signature omits it).
    """

    name = "vivanuncios"
    platform_name = "Vivanuncios"
    currency = "MXN"
    allowed_domains = ["vivanuncios.com.mx"]

    # Vivanuncios is sensitive to rapid crawling — keep one request at a time.
    custom_settings = {
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
        "DOWNLOAD_DELAY": 2,
    }

    # ------------------------------------------------------------------
    # URL building
    # ------------------------------------------------------------------

    def build_page_url(self, page_number: int) -> str:
        """Return the search URL for a given page number.

        URL pattern:
            https://www.vivanuncios.com.mx/s-mexico/{query}/v1c0p{page}

        ``v1`` is the API version, ``c0`` means no category filter,
        ``p{page}`` is the 1-based page index.
        """
        query = self.search_query.replace(" ", "+")
        return f"{_BASE_URL}/s-mexico/{query}/v1c0p{page_number}"

    # ------------------------------------------------------------------
    # Container
    # ------------------------------------------------------------------

    def get_product_container(self, response):
        """Return the list of per-listing Selector objects."""
        return response.css(_SELECTORS["container"])

    # ------------------------------------------------------------------
    # Field extractors (operate on a single card Selector)
    # ------------------------------------------------------------------

    def extract_title(self, product) -> str | None:
        return product.css(_SELECTORS["title"]).get("").strip() or None

    def extract_price(self, product) -> str | None:
        """Return the raw price string (digits + commas), or None.

        Vivanuncios displays prices like "$12,500" or "Precio a convenir".
        We return the raw text; ``clean_price`` in the base class strips commas
        before conversion to float.  Non-numeric strings (e.g. "Precio a
        convenir") are caught by the float() conversion in
        ``_validate_and_create_item`` and cause the item to be skipped.
        """
        raw = product.css(_SELECTORS["price"]).get("").strip()
        # Strip the leading peso sign if present so the base class can parse it
        return raw.lstrip("$").strip() or None

    def extract_link(self, product) -> str | None:
        raw = product.css(_SELECTORS["link"]).get("").strip() or None
        if not raw:
            return None
        # Vivanuncios hrefs may be relative ("/ad/laptop-123/p-...")
        if raw.startswith("http"):
            return self.normalize_url(raw)
        return self.normalize_url(f"{_BASE_URL}{raw}")

    def extract_image(self, product) -> str | None:
        return product.css(_SELECTORS["image"]).get("").strip() or None

    def extract_location(self, product) -> str | None:
        """Extract the human-readable location string from a listing card."""
        return product.css(_SELECTORS["location"]).get("").strip() or None

    # ------------------------------------------------------------------
    # URL normalisation
    # ------------------------------------------------------------------

    def normalize_url(self, url: str | None) -> str | None:
        """Strip tracking query parameters from Vivanuncios ad URLs."""
        if not url:
            return url
        parsed = urlparse(url)
        clean_qs = urlencode(
            [(k, v) for k, v in parse_qsl(parsed.query) if k not in _STRIP_PARAMS]
        )
        return urlunparse(
            (parsed.scheme, parsed.netloc, parsed.path, parsed.params, clean_qs, "")
        )

    # ------------------------------------------------------------------
    # Parse override — adds location support
    # ------------------------------------------------------------------

    def parse(self, response):
        """Parse one search-results page and yield ProductScraped dicts.

        Overrides the base ``parse`` because ``BaseMarketplaceSpider`` does not
        pass ``location`` through ``_validate_and_create_item``.  We call our
        own ``_create_item`` which includes the field.
        """
        products = self.get_product_container(response)

        if not products:
            self.logger.info(
                "No listing cards found on %s — selectors may need updating.",
                response.url,
            )

        for product in products:
            title = self.extract_title(product)
            price = self.extract_price(product)
            link = self.extract_link(product)
            image = self.extract_image(product)
            location = self.extract_location(product)

            item = self._create_item(
                title=title,
                price=price,
                link=link,
                image=image,
                location=location,
            )
            if item:
                yield item

    # ------------------------------------------------------------------
    # Item creation (location-aware, does not call super's version)
    # ------------------------------------------------------------------

    def _create_item(
        self,
        title: str | None,
        price: str | None,
        link: str | None,
        image: str | None,
        location: str | None,
    ) -> dict | None:
        """Validate fields and return a ``ProductScraped`` dict or ``None``."""
        if not title or not price or not link:
            self.logger.debug(
                "Skipping item — missing required field: "
                "title=%r, price=%r, link=%r",
                title,
                price,
                link,
            )
            return None

        try:
            price_float = float(self.clean_price(price))
        except ValueError:
            self.logger.debug(
                "Non-numeric price %r — skipping (likely 'Precio a convenir').",
                price,
            )
            return None

        try:
            scraped = ProductScraped(
                title=title,
                price=price_float,
                image=image,
                location=location,
                platform=self.platform_name,
                currency=self.currency,
                link=link,
            )
            return scraped.model_dump(mode="json")
        except ValidationError as exc:
            self.logger.warning("ProductScraped validation failed: %s", exc)
            self.logger.debug(
                "Data: title=%r, price=%r, link=%r, location=%r",
                title,
                price_float,
                link,
                location,
            )
            return None
