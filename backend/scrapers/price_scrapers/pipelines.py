import logging
import os
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

sys.path.append(os.path.join(os.path.dirname(__file__), "../../"))

from alerts.evaluator import evaluate_deal
from models import Alert, Platform, PriceHistory, Product, SessionLocal
from notifications.telegram import send_deal_alert

logger = logging.getLogger(__name__)

_ALERT_COOLDOWN_HOURS = 6


class DatabasePipeline:
    def __init__(self):
        self.session = None

    def open_spider(self, spider):
        self.session = SessionLocal()

    def close_spider(self, spider):
        self.session.commit()
        self.session.close()

    # ------------------------------------------------------------------
    # Alert evaluation
    # ------------------------------------------------------------------

    def _check_alerts(
        self,
        session: Session,
        product: Product,
        item: dict,
        previous_price: float | None,
        price_history_prices: list[float],
    ) -> None:
        """Evaluate active alerts for *product* and fire Telegram notifications.

        This method is intentionally wrapped in a broad try/except so that any
        notification failure never disrupts the surrounding DB save.
        """
        try:
            current_price: float = item["price"]
            now = datetime.now(timezone.utc)
            cooldown_cutoff = now - timedelta(hours=_ALERT_COOLDOWN_HOURS)

            # Query alerts that are active and whose platform matches (or is Any)
            alerts = (
                session.query(Alert)
                .filter(
                    Alert.is_active.is_(True),
                    (Alert.platform_id.is_(None))
                    | (Alert.platform_id == product.platform_id),
                )
                .all()
            )

            for alert in alerts:
                # Case-insensitive substring match of search_query in product title
                if alert.search_query.lower() not in product.title.lower():
                    continue

                # Anti-spam: skip if triggered within the cooldown window
                if (
                    alert.last_triggered_at is not None
                    and alert.last_triggered_at.replace(tzinfo=timezone.utc)
                    > cooldown_cutoff
                ):
                    continue

                result = evaluate_deal(
                    current_price=current_price,
                    previous_price=previous_price,
                    price_history=price_history_prices,
                    max_price=alert.max_price,
                    min_drop_pct=alert.min_drop_pct,
                    below_avg_pct=alert.below_avg_pct,
                )

                if not result.matched:
                    continue

                chat_id = alert.telegram_chat_id or os.getenv(
                    "TELEGRAM_DEFAULT_CHAT_ID"
                )
                if not chat_id:
                    logger.warning(
                        "Alert %d matched but has no chat_id and "
                        "TELEGRAM_DEFAULT_CHAT_ID is not set — skipping.",
                        alert.id,
                    )
                    continue

                sent = send_deal_alert(
                    chat_id,
                    title=product.title,
                    link=product.link,
                    current_price=current_price,
                    currency=item["currency"],
                    platform=item["platform"],
                    previous_price=result.previous_price,
                    avg_price=result.avg_price,
                    discount_pct=result.discount_pct,
                    image_url=product.image_url,
                    reasons=result.reasons,
                )

                if sent:
                    alert.last_triggered_at = now
                    logger.info(
                        "Deal alert %d fired for product %d ('%s').",
                        alert.id,
                        product.id,
                        product.title[:60],
                    )
                else:
                    logger.warning(
                        "Deal alert %d matched but Telegram delivery failed "
                        "for product %d.",
                        alert.id,
                        product.id,
                    )

        except Exception as exc:
            logger.error(
                "Unexpected error during alert evaluation for product %r: %s",
                getattr(product, "id", None),
                exc,
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # Scrapy pipeline
    # ------------------------------------------------------------------

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

                # Collect historical prices (excluding the new entry, not yet committed)
                history_prices: list[float] = (
                    self.session.query(PriceHistory.price)
                    .filter_by(product_id=product.id)
                    .order_by(PriceHistory.scraped_at.desc())
                    .all()
                )
                price_history_prices = [row[0] for row in history_prices]

                self._check_alerts(
                    self.session,
                    product,
                    item,
                    previous_price=last_price.price,
                    price_history_prices=price_history_prices,
                )

            product.title = item["title"]
            product.image_url = item.get("image")
            product.available = True
            product.rating = item.get("rating")
            product.location = item.get("location")
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
                location=item.get("location"),
            )

            self.session.add(new_product)
            self.session.flush()

            first_price = PriceHistory(
                product_id=new_product.id,
                price=item["price"],
                currency=item["currency"],
            )

            self.session.add(first_price)

            # New product: no price history yet, no previous price
            self._check_alerts(
                self.session,
                new_product,
                item,
                previous_price=None,
                price_history_prices=[],
            )

        try:
            self.session.commit()
        except Exception as e:
            self.session.rollback()
            spider.logger.error(f"Error saving DB: {e}")
            raise

        return item
