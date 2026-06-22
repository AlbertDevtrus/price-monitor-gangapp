import logging
import os

import httpx
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.telegram.org/bot{token}/{method}"


def _api_url(method: str) -> str:
    return _BASE_URL.format(token=TELEGRAM_BOT_TOKEN, method=method)


def send_message(
    chat_id: str,
    text: str,
    image_url: str | None = None,
) -> bool:
    """Send a text or photo message to a Telegram chat.

    Returns True on success, False on any error (never raises).
    """
    try:
        if image_url:
            payload = {
                "chat_id": chat_id,
                "photo": image_url,
                "caption": text,
                "parse_mode": "HTML",
            }
            response = httpx.post(_api_url("sendPhoto"), json=payload, timeout=10)
        else:
            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "HTML",
            }
            response = httpx.post(_api_url("sendMessage"), json=payload, timeout=10)

        if not response.is_success:
            logger.error(
                "Telegram API returned %s: %s",
                response.status_code,
                response.text,
            )
            return False

        return True

    except Exception as exc:
        logger.error("Failed to send Telegram message: %s", exc)
        return False


def send_deal_alert(
    chat_id: str,
    *,
    title: str,
    link: str,
    current_price: float,
    currency: str,
    platform: str,
    previous_price: float | None = None,
    avg_price: float | None = None,
    discount_pct: float | None = None,
    image_url: str | None = None,
    reasons: list[str] | None = None,
) -> bool:
    """Format and send a deal alert message to a Telegram chat.

    Returns True on success, False on any error (never raises).
    """
    lines: list[str] = []

    lines.append(f"<b>{title}</b>")
    lines.append("")

    lines.append(f"<b>Price:</b> {currency} {current_price:,.2f}")

    if previous_price is not None:
        lines.append(f"<b>Previous price:</b> {currency} {previous_price:,.2f}")

    if avg_price is not None:
        lines.append(f"<b>Avg price:</b> {currency} {avg_price:,.2f}")

    if discount_pct is not None:
        lines.append(f"<b>Discount:</b> {discount_pct:.1f}% off")

    lines.append(f"<b>Platform:</b> {platform}")
    lines.append("")

    if reasons:
        lines.append("<b>Why it's a deal:</b>")
        for reason in reasons:
            lines.append(f"  • {reason}")
        lines.append("")

    lines.append(f'<a href="{link}">View product</a>')

    text = "\n".join(lines)
    return send_message(chat_id, text, image_url=image_url)
