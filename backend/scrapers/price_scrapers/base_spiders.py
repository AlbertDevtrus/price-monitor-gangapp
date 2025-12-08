from abc import ABC, abstractmethod
from pydantic import ValidationError
import scrapy


from price_scrapers.items import ProductScraped


class BaseMarketplaceSpider(scrapy.Spider, ABC):
    
    platform_name = None
    currency = None
    max_pages = 5

    def __init__(self, search_query="",*args, **kwargs):
        super().__init__(*args, **kwargs)
        self.search_query = search_query

    @abstractmethod
    def get_product_container(self, response):
        """ Return products HTML List """
        pass

    @abstractmethod
    def extract_title(self, product):
        """ Extracts product title """
        pass

    @abstractmethod
    def extract_price(self, product):
        """ Extracts product price """
        pass

    @abstractmethod
    def extract_link(self, product):
        """ Extracts product link """
        pass
    
    @abstractmethod 
    def extract_image(self, product):
        """ Extracts product image """
        pass
    
    @abstractmethod
    def build_page_url(self, page_number):
        """ Build page URL for pagination """
        pass

    def clean_price(self, price_str):
        return price_str.replace(',', '').strip()
    
    def start_requests(self):
        for page_number in range(1, self.max_pages + 1):
            yield scrapy.Request(url=self.build_page_url(page_number=page_number), callback=self.parse)

    def parse(self, response):
        products = self.get_product_container(response)

        for product in products:
            title = self.extract_title(product=product)
            
            link = self.extract_link(product=product)

            image = self.extract_image(product=product)
            
            price = self.extract_price(product=product)

            item = self._validate_and_create_item(image=image,title=title,price=price,link=link)

            if item:
                yield item


    def _validate_and_create_item(self, title, price, link, image):
        """Validate data and create ProductScraped"""

        if not price or not link or not title: 
            self.logger.warning(f"Invalid product: price: {price}, link: {link}, title: {title}")
            return None
        
        price=float(self.clean_price(price))
        
        try: 
            product_scraped = ProductScraped(**{"title": title, "price": price, "image": image, "platform": self.platform_name, "currency": self.currency, "link": link })
        
            return product_scraped.model_dump(mode="json")
        except ValidationError as e:
            self.logger.warning(f"Invalid Product: {e}")
            self.logger.debug(f"Data: title: {title}, price: {price}, image: {image}, platform: {self.platform_name}, currency: {self.currency}, link: {link} ")
            return None
