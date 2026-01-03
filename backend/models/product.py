from sqlalchemy import Integer, Column, String, Boolean, ForeignKey, Float, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from models.base import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)

    title = Column(String, nullable=False)
    link = Column(String, unique=True, nullable=False, index=True)

    platform_id = Column(Integer, ForeignKey("platforms.id"), nullable=False)
    
    image_url = Column(String, nullable=True)
    available = Column(Boolean, default=True)
    rating = Column(Float, nullable=True)
    condition = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    platform = relationship("Platform", back_populates="products")
    price_history = relationship("PriceHistory", back_populates="product", order_by="PriceHistory.scraped_at.desc()")

    def __repr__(self):
        return f"<Product(title='{self.title[:30]}...', platform='{self.platform_id}')>"


