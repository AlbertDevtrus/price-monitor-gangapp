from __future__ import annotations

import pytest
from statistics import mean

from alerts.evaluator import DealResult, evaluate_deal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

HISTORY = [100.0, 120.0, 110.0, 130.0, 90.0]  # mean = 110.0


# ---------------------------------------------------------------------------
# Threshold criterion (max_price)
# ---------------------------------------------------------------------------


def test_threshold_match() -> None:
    result = evaluate_deal(
        current_price=49.99,
        previous_price=None,
        price_history=[],
        max_price=50.0,
    )
    assert result.matched is True
    assert len(result.reasons) == 1
    assert "umbral" in result.reasons[0]
    assert "49.99" in result.reasons[0]


def test_threshold_no_match() -> None:
    result = evaluate_deal(
        current_price=50.01,
        previous_price=None,
        price_history=[],
        max_price=50.0,
    )
    assert result.matched is False
    assert result.reasons == []


def test_threshold_exact_boundary() -> None:
    result = evaluate_deal(
        current_price=50.0,
        previous_price=None,
        price_history=[],
        max_price=50.0,
    )
    assert result.matched is True
    assert "umbral" in result.reasons[0]


# ---------------------------------------------------------------------------
# Drop percentage criterion (min_drop_pct)
# ---------------------------------------------------------------------------


def test_drop_match() -> None:
    # 20 % drop: (100 - 80) / 100 = 0.20
    result = evaluate_deal(
        current_price=80.0,
        previous_price=100.0,
        price_history=[],
        min_drop_pct=0.15,
    )
    assert result.matched is True
    assert any("Cayó" in r for r in result.reasons)


def test_drop_no_match() -> None:
    # 5 % drop: (100 - 95) / 100 = 0.05
    result = evaluate_deal(
        current_price=95.0,
        previous_price=100.0,
        price_history=[],
        min_drop_pct=0.10,
    )
    assert result.matched is False


def test_drop_previous_zero_is_ignored() -> None:
    # previous_price = 0 → division guard, criterion must NOT fire
    result = evaluate_deal(
        current_price=0.0,
        previous_price=0.0,
        price_history=[],
        min_drop_pct=0.10,
    )
    assert result.matched is False


def test_drop_previous_none_is_ignored() -> None:
    result = evaluate_deal(
        current_price=80.0,
        previous_price=None,
        price_history=[],
        min_drop_pct=0.10,
    )
    assert result.matched is False


# ---------------------------------------------------------------------------
# Below-average criterion (below_avg_pct)
# ---------------------------------------------------------------------------


def test_below_avg_match() -> None:
    # mean(HISTORY) = 110.0; 10 % below = 99.0; current = 95 → match
    result = evaluate_deal(
        current_price=95.0,
        previous_price=None,
        price_history=HISTORY,
        below_avg_pct=0.10,
    )
    assert result.matched is True
    assert any("promedio" in r for r in result.reasons)


def test_below_avg_no_match() -> None:
    # mean = 110.0; 10 % below = 99.0; current = 105 → no match
    result = evaluate_deal(
        current_price=105.0,
        previous_price=None,
        price_history=HISTORY,
        below_avg_pct=0.10,
    )
    assert result.matched is False


def test_below_avg_empty_history_is_ignored() -> None:
    result = evaluate_deal(
        current_price=1.0,
        previous_price=None,
        price_history=[],
        below_avg_pct=0.05,
    )
    assert result.matched is False


# ---------------------------------------------------------------------------
# No criteria set
# ---------------------------------------------------------------------------


def test_no_criteria_never_matches() -> None:
    result = evaluate_deal(
        current_price=50.0,
        previous_price=100.0,
        price_history=HISTORY,
    )
    assert result.matched is False
    assert result.reasons == []


# ---------------------------------------------------------------------------
# Combined: multiple reasons
# ---------------------------------------------------------------------------


def test_combined_multiple_reasons() -> None:
    # Threshold fires (current <= max_price) AND drop fires (>= min_drop_pct)
    # previous=200, current=80 → drop = 60 % >= 0.50; max_price=100 >= 80
    result = evaluate_deal(
        current_price=80.0,
        previous_price=200.0,
        price_history=HISTORY,
        max_price=100.0,
        min_drop_pct=0.50,
        below_avg_pct=0.10,
    )
    assert result.matched is True
    # All three criteria fire
    assert len(result.reasons) == 3


# ---------------------------------------------------------------------------
# discount_pct field
# ---------------------------------------------------------------------------


def test_discount_pct_computed() -> None:
    # (100 - 80) / 100 = 0.20
    result = evaluate_deal(
        current_price=80.0,
        previous_price=100.0,
        price_history=[],
    )
    assert result.discount_pct == pytest.approx(0.20)


def test_discount_pct_none_when_no_previous() -> None:
    result = evaluate_deal(
        current_price=80.0,
        previous_price=None,
        price_history=[],
    )
    assert result.discount_pct is None


def test_discount_pct_none_when_previous_zero() -> None:
    result = evaluate_deal(
        current_price=80.0,
        previous_price=0.0,
        price_history=[],
    )
    assert result.discount_pct is None


# ---------------------------------------------------------------------------
# avg_price field
# ---------------------------------------------------------------------------


def test_avg_price_computed() -> None:
    result = evaluate_deal(
        current_price=50.0,
        previous_price=None,
        price_history=HISTORY,
    )
    assert result.avg_price == pytest.approx(mean(HISTORY))


def test_avg_price_none_when_empty_history() -> None:
    result = evaluate_deal(
        current_price=50.0,
        previous_price=None,
        price_history=[],
    )
    assert result.avg_price is None
