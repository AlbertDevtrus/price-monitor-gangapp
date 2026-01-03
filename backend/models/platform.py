from sqlalchemy import Integer, Column, String, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from models.base import Base


class Platform(Base):
    __tablename__ = "platforms"


    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, nullable=False)
    base_url = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    products = relationship("Product", back_populates="platform")

    def __repr__(self):
        return f"<Platform(name='{self.name}')>"