import os
import sys
from datetime import datetime, timezone

from sqlalchemy.orm import Session

sys.path.append(os.path.join(os.path.dirname(__file__), "../../"))

from models import Platform, PriceHistory, Product, SessionLocal


class DatabasePipeline:
    def __init__(self):
        self.session = None

    def open_spider(self, spider):
        self.session = SessionLocal()

    def close_spider(self, spider):
        self.session.commit()
        self.session.close()

    def process_item(self, item, spider):
        platform = self.session.query(Platform).filter_by(name=item["platform"]).first()

        if not platform:
            platform = Platform(name=item["platform"], base_url=None)

            self.session.add(platform)
            self.session.flush()

        product = self.session.query(Product).filter_by(link=item["link"]).first()

        if product:
            last_price = (
                self.session.query(PriceHistory)
                .filter_by(product_id=product.id)
                .order_by(PriceHistory.scraped_at.desc())
                .first()
            )

            if last_price and last_price.price != item["price"]:
                new_price = PriceHistory(
                    product_id=product.id,
                    price=item["price"],
                    currency=item["currency"],
                )

                self.session.add(new_price)

            product.title = item["title"]
            product.image_url = item.get("image")
            product.available = True
            product.rating = item.get("rating")
            product.updated_at = datetime.now(timezone.utc)
        else:
            new_product = Product(
                title=item["title"],
                link=item["link"],
                platform_id=platform.id,
                image_url=item.get("image"),
                available=True,
                rating=item.get("rating"),
                condition=item.get("condition"),
            )

            self.session.add(new_product)
            self.session.flush()

            first_price = PriceHistory(
                product_id=new_product.id,
                price=item["price"],
                currency=item["currency"],
            )

            self.session.add(first_price)

        try:
            self.session.commit()
        except Exception as e:
            self.session.rollback()
            spider.logger.error(f"Error saving DB: {e}")
            raise

        return item
