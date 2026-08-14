from core.models import Market, StockSnapshot
from core.validation import check_change_rate, validate_snapshot


def _snapshot(**overrides) -> StockSnapshot:
    base = dict(code="7203", market=Market.JP, price=2500, per=15, pbr=1.2, roe=0.15, dividend_yield=0.025)
    base.update(overrides)
    return StockSnapshot(**base)


def test_normal_values_produce_no_warnings():
    assert validate_snapshot(_snapshot()) == []


def test_extreme_per_is_flagged():
    warnings = validate_snapshot(_snapshot(per=9999))
    assert any(w.field == "per" for w in warnings)


def test_negative_price_is_flagged():
    warnings = validate_snapshot(_snapshot(price=-100))
    assert any(w.field == "price" for w in warnings)


def test_week52_high_below_low_is_flagged():
    warnings = validate_snapshot(_snapshot(week52_high=100, week52_low=200))
    assert any(w.field == "week52_range" for w in warnings)


def test_extreme_dividend_yield_is_flagged():
    warnings = validate_snapshot(_snapshot(dividend_yield=0.9))
    assert any(w.field == "dividend_yield" for w in warnings)


def test_change_rate_within_normal_range_returns_none():
    assert check_change_rate(100, 110, "revenue") is None


def test_change_rate_extreme_returns_warning():
    warning = check_change_rate(100, 300, "revenue")
    assert warning is not None
    assert warning.field == "revenue"
