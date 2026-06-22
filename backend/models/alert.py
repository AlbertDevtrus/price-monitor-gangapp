from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from models.base import Base


class Alert(Base):
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    label = Column(String, nullable=False)
    search_query = Column(String, nullable=False)
    platform_id = Column(Integer, ForeignKey("platforms.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    max_price = Column(Float, nullable=True)
    min_drop_pct = Column(Float, nullable=True)
    below_avg_pct = Column(Float, nullable=True)
    telegram_chat_id = Column(String, nullable=True)
    last_triggered_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    platform = relationship("Platform", backref="alerts")

    def __repr__(self):
        return f"<Alert(label='{self.label}', active='{self.is_active}')>"
