from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, HttpUrl


class ProductScraped(BaseModel):
    title: str
    price: float = Field(gt=0, description="Price is more than 0")
    image: str | None = None
    platform: str
    currency: Literal["MXN", "USD"]
    link: HttpUrl
    scraped_at: datetime = Field(default_factory=datetime.now)
