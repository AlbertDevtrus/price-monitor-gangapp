from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean


@dataclass
class DealResult:
    matched: bool
    reasons: list[str]
    current_price: float
    previous_price: float | None
    avg_price: float | None
    discount_pct: float | None


def evaluate_deal(
    *,
    current_price: float,
    previous_price: float | None,
    price_history: list[float],
    max_price: float | None = None,
    min_drop_pct: float | None = None,
    below_avg_pct: float | None = None,
) -> DealResult:
    """Evaluate whether a price qualifies as a deal.

    Three criteria are OR-combined; any one match makes matched=True.

    Args:
        current_price: The latest scraped price.
        previous_price: The immediately preceding recorded price, or None.
        price_history: All historical prices (may be empty).
        max_price: Threshold criterion — fires when current_price <= max_price.
        min_drop_pct: Drop criterion — fires when the percentage fall from
            previous_price >= min_drop_pct (expressed as a fraction, e.g. 0.10).
        below_avg_pct: Below-average criterion — fires when current_price is at
            least below_avg_pct below the historical mean (fraction, e.g. 0.05).

    Returns:
        DealResult with matched flag, human-readable reasons, and computed
        statistics.
    """
    reasons: list[str] = []

    # --- Criterion 1: absolute price threshold ---
    if max_price is not None and current_price <= max_price:
        reasons.append(
            f"Precio por debajo del umbral (${current_price:.2f})"
        )

    # --- Criterion 2: percentage drop vs previous price ---
    if (
        min_drop_pct is not None
        and previous_price is not None
        and previous_price > 0
    ):
        drop = (previous_price - current_price) / previous_price
        if drop >= min_drop_pct:
            reasons.append(f"Cayó {drop:.1%} vs precio anterior")

    # --- Criterion 3: below historical average ---
    if below_avg_pct is not None and price_history:
        historical_mean = mean(price_history)
        if current_price <= historical_mean * (1 - below_avg_pct):
            reasons.append(
                f"{below_avg_pct:.1%} por debajo del promedio histórico"
            )

    # --- Derived statistics ---
    avg_price: float | None = mean(price_history) if price_history else None

    discount_pct: float | None = None
    if previous_price is not None and previous_price > 0:
        discount_pct = (previous_price - current_price) / previous_price

    return DealResult(
        matched=bool(reasons),
        reasons=reasons,
        current_price=current_price,
        previous_price=previous_price,
        avg_price=avg_price,
        discount_pct=discount_pct,
    )
