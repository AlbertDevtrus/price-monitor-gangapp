import scrapy
from price_scrapers.items import ProductScraped
from pydantic import ValidationError

class MercadoLibreSpider(scrapy.Spider):
    name = "mercadolibre"
    allowed_domains = ["mercadolibre.com.mx"]
    
    def __init__(self, search_query="", *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.search_query = search_query
        

    def start_requests(self):
        max_pages = 3
        
        for page in range(1, max_pages + 1):
            if page == 1:
                url= f"https://listado.mercadolibre.com.mx/{self.search_query}"
            else:
                offset = (page - 1) * 50 + 1
                url= f"https://listado.mercadolibre.com.mx/{self.search_query}_Desde_{offset}"
        
            yield scrapy.Request(url=url, callback=self.parse)

    
    def parse(self, response):
        products = response.css('li.ui-search-layout__item')
        self.logger.info(f"Encontrados {len(products)} productos")
        
        for product in products:
            title_element = product.css('a.poly-component__title')
            title = title_element.css('::text').get()
            
            link = title_element.css('::attr(href)').get()

            image_element = product.css('img.poly-component__picture')
            image = image_element.css('::attr(src)').get()
            
            price = product.css('.andes-money-amount__fraction::text').get()

            if not price or not link or not title: 
                self.logger.warning(f"Invalid product: price: {price}, link: {link}, title: {title}")
                continue

            try: 
                product_scraped = ProductScraped(**{"title": title, "price": float(price.replace(',','')), "image": image, "platform": 'Mercado Libre', "currency": "MXN", "link": link })
            
                yield product_scraped.model_dump(mode="json")
            except ValidationError as e:
                self.logger.warning(f"Invalid Product: {e}")
                self.logger.debug(f"Data: title: {title}, price: {price}, image: {image}, platform: Mercado Libre, currency: MXN, link: {link} ")
                continue