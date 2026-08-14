from core.models import Market, StockSnapshot
from core.screening import Operator, ScreeningRule, screen


def _snapshot(code, **overrides) -> StockSnapshot:
    base = dict(code=code, market=Market.JP, per=15, pbr=1.2, dividend_yield=0.02, market_cap=1_000_000)
    base.update(overrides)
    return StockSnapshot(**base)


def test_screen_filters_by_per_upper_bound():
    snapshots = [_snapshot("A", per=10), _snapshot("B", per=30)]
    rules = [ScreeningRule(field="per", operator=Operator.LTE, threshold=15)]
    result = screen(snapshots, rules)
    assert [s.code for s in result] == ["A"]


def test_screen_combines_rules_with_and():
    snapshots = [
        _snapshot("A", per=10, dividend_yield=0.01),
        _snapshot("B", per=10, dividend_yield=0.05),
    ]
    rules = [
        ScreeningRule(field="per", operator=Operator.LTE, threshold=20),
        ScreeningRule(field="dividend_yield", operator=Operator.GTE, threshold=0.03),
    ]
    result = screen(snapshots, rules)
    assert [s.code for s in result] == ["B"]


def test_screen_excludes_missing_values():
    snapshots = [_snapshot("A", per=None)]
    rules = [ScreeningRule(field="per", operator=Operator.LTE, threshold=20)]
    assert screen(snapshots, rules) == []
