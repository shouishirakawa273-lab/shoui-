from core.comparison import build_comparison_table, normalize_for_radar
from core.models import Market, StockSnapshot


def _snapshot(code, per, pbr) -> StockSnapshot:
    return StockSnapshot(code=code, market=Market.JP, per=per, pbr=pbr, roe=0.1, dividend_yield=0.02, market_cap=100)


def test_build_comparison_table_includes_fetched_at():
    table = build_comparison_table([_snapshot("A", 10, 1.0)])
    assert table[0]["銘柄コード"] == "A"
    assert "取得日時" in table[0]


def test_normalize_for_radar_inverts_lower_is_better_fields():
    snapshots = [_snapshot("A", per=10, pbr=1.0), _snapshot("B", per=30, pbr=3.0)]
    result = normalize_for_radar(snapshots)
    # PERは低いほど良い指標なので、値が小さいAの方がスコアが高くなる
    assert result["PER"][0] > result["PER"][1]


def test_normalize_for_radar_handles_missing_values():
    snapshots = [_snapshot("A", per=None, pbr=1.0), _snapshot("B", per=30, pbr=3.0)]
    result = normalize_for_radar(snapshots)
    assert result["PER"][0] == 0.0
