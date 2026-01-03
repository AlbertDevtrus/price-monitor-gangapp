from sqlalchemy import Integer, Column, String, ForeignKey, Float, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from models.base import Base


class PriceHistory(Base):

    __tablename__ = "price_history"
    
    id = Column(Integer, primary_key=True, index=True)

    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)

    price = Column(Float, nullable=False)
    currency = Column(String, nullable=False)

    scraped_at = Column(DateTime(timezone=True), server_default=func.now(), index=True, nullable=False)
    product = relationship("Product", back_populates="price_history")

    def __repr__(self):
        return f"<Price(price='{self.price}', date='{self.scraped_at}')>"
