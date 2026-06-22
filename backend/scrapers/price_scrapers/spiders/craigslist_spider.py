"""Craigslist RSS spider for the price-monitor project.

Craigslist exposes stable, JavaScript-free RSS/RDF feeds for every search:

    https://<site>.craigslist.org/search/sss?query=<query>&format=rss

This spider fetches those feeds (up to ``max_pages`` pages via the ``start=``
offset param), parses each ``<item>`` in the RDF/XML response, and yields
``ProductScraped`` items into the shared ``DatabasePipeline``.

Example run (from ``backend/scrapers/``):

    scrapy crawl craigslist -a search_query=bicycle -a site=newyork
    scrapy crawl craigslist -a search_query=laptop   -a site=losangeles
    scrapy crawl craigslist -a search_query=sofa     -a site=chicago -a max_pages=3

Why a plain ``scrapy.Spider`` instead of ``BaseMarketplaceSpider``:
    ``BaseMarketplaceSpider`` couples ``start_requests`` to integer page numbers
    and ``parse`` to CSS selectors on HTML.  Craigslist RSS uses XPath with
    multiple XML namespaces and offset-based pagination — adapting the abstract
    contract would require overriding every hook, producing more noise than
    clarity.  The ``DatabasePipeline`` only requires ``ProductScraped`` dicts,
    not a specific spider base class.
"""

import re

import scrapy
from pydantic import ValidationError

from price_scrapers.items import ProductScraped


# Craigslist RSS is RDF 1.0 with Dublin Core and Syndication modules.
_NS = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rss": "http://purl.org/rss/1.0/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "syn": "http://purl.org/rss/1.0/modules/syndication/",
    "geo": "http://www.w3.org/2003/01/geo/wgs84_pos#",
}

# Results per RSS page (Craigslist returns up to 120 per request).
_PAGE_SIZE = 120

# Regex that captures the leading dollar-amount from strings like "$200 Bicycle"
# or "nice sofa $85 obo".  Accepts optional comma-thousands separators and
# optional cents (e.g. $1,200.50).
_PRICE_RE = re.compile(r"\$\s*([\d,]+(?:\.\d{1,2})?)")


class CraigslistSpider(scrapy.Spider):
    """Spider that reads Craigslist for-sale RSS feeds and emits ProductScraped items."""

    name = "craigslist"
    platform_name = "Craigslist"
    currency = "USD"

    # Craigslist throttles aggressively; one request at a time is safest.
    custom_settings = {
        "CONCURRENT_REQUESTS_PER_DOMAIN": 1,
    }

    def __init__(self, search_query="", site="newyork", max_pages=5, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not search_query:
            raise ValueError("search_query is required (e.g. -a search_query=bicycle)")
        self.search_query = search_query
        self.site = site
        self.max_pages = int(max_pages)

    # ------------------------------------------------------------------
    # URL helpers
    # ------------------------------------------------------------------

    def _build_feed_url(self, offset: int) -> str:
        """Return the RSS feed URL for the given result offset."""
        base = f"https://{self.site}.craigslist.org/search/sss"
        return (
            f"{base}?query={self.search_query}&format=rss&start={offset}"
        )

    # ------------------------------------------------------------------
    # Scrapy entry points
    # ------------------------------------------------------------------

    def start_requests(self):
        for page in range(self.max_pages):
            offset = page * _PAGE_SIZE
            url = self._build_feed_url(offset)
            yield scrapy.Request(
                url=url,
                callback=self.parse,
                cb_kwargs={"page": page + 1},
            )

    def parse(self, response, page=1):
        """Parse one RSS page and yield ProductScraped dicts."""
        # Register all namespaces so XPath expressions work correctly.
        response.selector.remove_namespaces()

        items = response.xpath("//item")
        if not items:
            self.logger.info(
                "Page %d returned no items — stopping early.", page
            )
            return

        for node in items:
            title = self._extract_title(node)
            link = self._extract_link(node)
            price_str = self._extract_price_str(node, title)
            location = self._extract_location(node)

            product = self._validate_and_create_item(
                title=title,
                price_str=price_str,
                link=link,
                location=location,
            )
            if product:
                yield product

    # ------------------------------------------------------------------
    # Field extractors
    # ------------------------------------------------------------------

    def _extract_title(self, node) -> str | None:
        return node.xpath("title/text()").get("").strip() or None

    def _extract_link(self, node) -> str | None:
        # <link> in RDF RSS is text content, not an attribute.
        return node.xpath("link/text()").get("").strip() or None

    def _extract_price_str(self, node, title: str | None) -> str | None:
        """Return a raw price string (e.g. '200' or '1,200.50') or None.

        Craigslist does not have a dedicated price element in the RSS feed.
        Prices are embedded in the item title (e.g. '$200 Bicycle') or
        sometimes in the description.  We try the title first, then the
        description, and return the first dollar-amount found.
        """
        for text in [title or "", node.xpath("description/text()").get("") or ""]:
            match = _PRICE_RE.search(text)
            if match:
                return match.group(1)
        return None

    def _extract_location(self, node) -> str | None:
        """Return a human-readable location string if the feed provides one.

        After namespace stripping, ``<dc:coverage>`` or ``<dc:rights>`` may
        carry area info.  Craigslist also embeds ``<georss:point>`` in some
        feeds but that is a coordinate, not a name.  We check common tags and
        fall back to None.
        """
        for xpath_expr in [
            "coverage/text()",   # dc:coverage after ns strip
            "rights/text()",     # dc:rights sometimes contains city
        ]:
            value = node.xpath(xpath_expr).get("").strip()
            if value:
                return value
        return None

    # ------------------------------------------------------------------
    # Validation / item creation
    # ------------------------------------------------------------------

    def _clean_price(self, price_str: str) -> float:
        """Strip commas and convert to float."""
        return float(price_str.replace(",", "").strip())

    def _validate_and_create_item(
        self,
        title: str | None,
        price_str: str | None,
        link: str | None,
        location: str | None,
    ) -> dict | None:
        """Validate extracted fields and return a ProductScraped dict or None."""
        if not title or not link or not price_str:
            self.logger.debug(
                "Skipping item — missing required field: "
                "title=%r, link=%r, price=%r",
                title,
                link,
                price_str,
            )
            return None

        try:
            price = self._clean_price(price_str)
        except ValueError:
            self.logger.warning("Could not parse price %r — skipping.", price_str)
            return None

        try:
            product = ProductScraped(
                title=title,
                price=price,
                image=None,
                location=location,
                platform=self.platform_name,
                currency=self.currency,
                link=link,
            )
            return product.model_dump(mode="json")
        except ValidationError as exc:
            self.logger.warning("ProductScraped validation failed: %s", exc)
            self.logger.debug(
                "Data: title=%r, price=%r, link=%r, location=%r",
                title,
                price,
                link,
                location,
            )
            return None
