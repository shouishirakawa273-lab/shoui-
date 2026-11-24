"""Step 3 1株当たり指標の比較可能性テスト。実APIには一切接続しない。

回帰の中心は2026-11-21に実データ(7203)で見つかった読み違え:
EPSが803.23→205.23と並び74%減に見えるが、同期の `net_profit/eps` は4.97倍に
切り替わっており、1株当たりの基準そのものが変わっていた。
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from lib.evidence.model import AvailabilitySemantics
from lib.schemas.price_data import CorporateAction, CorporateActionType
from lib.screener.financial_trend import AnnualObservation, FinancialTrend, MetricTrend
from lib.screener.per_share import (
    DEFAULT_DIVISOR_TOLERANCE,
    DIVISOR_SOURCES,
    assess_per_share_comparability,
)

DECISION_AT = datetime(2026, 11, 21, 15, 30, tzinfo=UTC)
CODE = "7203"


def _obs(period_end: date, value: str | None) -> AnnualObservation:
    return AnnualObservation(
        fiscal_period_end=period_end,
        value=None if value is None else Decimal(value),
        published_at=DECISION_AT,
        source_version_id=f"V_{period_end.isoformat()}_{value}",
        superseded_count=0,
    )


def _trend(
    metric_type: str,
    rows: list[tuple[date, str | None]],
    *,
    accounting_standard: str | None = "IFRS",
) -> MetricTrend:
    return MetricTrend(
        metric_type=metric_type,
        accounting_standard=accounting_standard,
        series_id=f"{CODE}|{metric_type}|CURRENT_FISCAL_YEAR|FY|CONSOLIDATED|{accounting_standard}",
        observations=tuple(_obs(p, v) for p, v in rows),
    )


def _financial_trend(trends: list[MetricTrend]) -> FinancialTrend:
    return FinancialTrend(
        code=CODE,
        decision_at=DECISION_AT,
        availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT,
        trends=tuple(trends),
        unmapped_metrics=(),
    )


# 7203実データ。EPSは開示時点のまま、FY2022でper-share基準が切り替わる。
_REAL_EPS = [
    (date(2021, 3, 31), "803.23"),
    (date(2022, 3, 31), "205.23"),
    (date(2023, 3, 31), "179.47"),
    (date(2024, 3, 31), "365.94"),
]
_REAL_NET_PROFIT = [
    (date(2021, 3, 31), "2245261000000"),
    (date(2022, 3, 31), "2850110000000"),
    (date(2023, 3, 31), "2451318000000"),
    (date(2024, 3, 31), "4944933000000"),
]


def test_real_7203_split_boundary_is_detected() -> None:
    """実データ回帰。EPSの74%減は業績ではなく基準の切り替わりだった。"""
    trend = _financial_trend([_trend("eps", _REAL_EPS), _trend("net_profit", _REAL_NET_PROFIT)])
    result = assess_per_share_comparability(code=CODE, trend=trend, per_share_metrics=["eps"])

    assert len(result.breaks) == 1
    found = result.breaks[0]
    assert found.metric_type == "eps"
    assert found.from_fiscal_period_end == date(2021, 3, 31)
    assert found.to_fiscal_period_end == date(2022, 3, 31)
    assert found.divisor_ratio == pytest.approx(Decimal("4.97"), abs=Decimal("0.01"))
    assert not result.is_comparable_throughout


def test_break_detail_does_not_assert_a_cause() -> None:
    """分割と断定しない。増資・訂正でも同じ形になる。"""
    trend = _financial_trend([_trend("eps", _REAL_EPS), _trend("net_profit", _REAL_NET_PROFIT)])
    detail = assess_per_share_comparability(code=CODE, trend=trend, per_share_metrics=["eps"]).breaks[0].detail
    assert "断定しない" in detail
    assert "株式分割があった" not in detail


def test_buyback_sized_drift_does_not_warn() -> None:
    """株数が年1〜2%減る程度では警告しない。"""
    eps = [(date(2023, 3, 31), "100"), (date(2024, 3, 31), "102"), (date(2025, 3, 31), "104")]
    net = [(date(2023, 3, 31), "1000"), (date(2024, 3, 31), "1000"), (date(2025, 3, 31), "1000")]
    trend = _financial_trend([_trend("eps", eps), _trend("net_profit", net)])
    result = assess_per_share_comparability(code=CODE, trend=trend)
    assert result.breaks == ()
    assert result.is_comparable_throughout


def test_values_are_never_modified() -> None:
    """検知のみ。推移の数値には触らない。"""
    eps_trend = _trend("eps", _REAL_EPS)
    trend = _financial_trend([eps_trend, _trend("net_profit", _REAL_NET_PROFIT)])
    before = tuple(o.value for o in eps_trend.observations)
    assess_per_share_comparability(code=CODE, trend=trend)
    assert tuple(o.value for o in eps_trend.observations) == before


def test_divisor_is_not_compared_across_accounting_standards() -> None:
    """基準が違うseries同士で除数を比べない(financial_trendが分けた境界を尊重する)。"""
    ifrs_eps = _trend("eps", [(date(2022, 3, 31), "205.23")], accounting_standard="IFRS")
    jp_eps = _trend("eps", [(date(2021, 3, 31), "803.23")], accounting_standard=None)
    ifrs_np = _trend("net_profit", [(date(2022, 3, 31), "2850110000000")], accounting_standard="IFRS")
    jp_np = _trend("net_profit", [(date(2021, 3, 31), "2245261000000")], accounting_standard=None)
    trend = _financial_trend([ifrs_eps, jp_eps, ifrs_np, jp_np])
    result = assess_per_share_comparability(code=CODE, trend=trend)
    # 各基準内に1期しか無いので比較対象が無い。基準をまたいで勝手に繋がない。
    assert result.breaks == ()
    assert "eps" in result.unchecked_metrics


def test_missing_divisor_metric_is_reported_as_unchecked() -> None:
    """net_profitが無ければ判定できない。できたふりをしない。

    bpsも既定の監視対象(2026-11-24追加)なので、除数が無い以上こちらも未確認。
    """
    trend = _financial_trend([_trend("eps", _REAL_EPS)])
    result = assess_per_share_comparability(code=CODE, trend=trend)
    assert result.breaks == ()
    assert set(result.unchecked_metrics) == {"eps", "bps"}


def test_absent_per_share_metric_is_unchecked_not_ok() -> None:
    trend = _financial_trend([_trend("net_profit", _REAL_NET_PROFIT)])
    result = assess_per_share_comparability(code=CODE, trend=trend)
    assert result.per_share_metrics == ()
    assert set(result.unchecked_metrics) == {"eps", "bps"}


def test_zero_per_share_value_is_skipped_not_treated_as_zero_divisor() -> None:
    """EPS=0の期は除数が定義できない。0除算もせず、0扱いもしない。"""
    eps = [(date(2023, 3, 31), "0"), (date(2024, 3, 31), "100"), (date(2025, 3, 31), "101")]
    net = [(date(2023, 3, 31), "1000"), (date(2024, 3, 31), "1000"), (date(2025, 3, 31), "1000")]
    trend = _financial_trend([_trend("eps", eps), _trend("net_profit", net)])
    result = assess_per_share_comparability(code=CODE, trend=trend)
    assert result.breaks == ()


def test_none_values_are_skipped() -> None:
    eps = [(date(2023, 3, 31), "100"), (date(2024, 3, 31), None), (date(2025, 3, 31), "101")]
    net = [(date(2023, 3, 31), "1000"), (date(2024, 3, 31), "1000"), (date(2025, 3, 31), "1000")]
    trend = _financial_trend([_trend("eps", eps), _trend("net_profit", net)])
    result = assess_per_share_comparability(code=CODE, trend=trend)
    assert result.breaks == ()


def test_reverse_split_direction_is_also_detected() -> None:
    """併合(除数が減る側)も見逃さない。"""
    eps = [(date(2024, 3, 31), "100"), (date(2025, 3, 31), "1000")]
    net = [(date(2024, 3, 31), "1000000"), (date(2025, 3, 31), "1000000")]
    trend = _financial_trend([_trend("eps", eps), _trend("net_profit", net)])
    result = assess_per_share_comparability(code=CODE, trend=trend, per_share_metrics=["eps"])
    assert len(result.breaks) == 1
    assert result.breaks[0].divisor_ratio == pytest.approx(Decimal("0.1"), abs=Decimal("0.001"))


def test_corporate_actions_are_reported_with_their_known_window() -> None:
    """Provider確定Eventは窓の境界とセットで出す。空は「無かった」ではない。"""
    trend = _financial_trend([_trend("eps", _REAL_EPS), _trend("net_profit", _REAL_NET_PROFIT)])
    action = CorporateAction(
        code=CODE,
        provider_code="72030",
        action_type=CorporateActionType.ADJUSTMENT_EVENT,
        effective_date=date(2025, 4, 1),
        raw_adj_factor=0.2,
    )
    result = assess_per_share_comparability(
        code=CODE,
        trend=trend,
        corporate_actions=[action],
        corporate_actions_known_from=date(2025, 1, 6),
    )
    assert result.corporate_action_dates == (date(2025, 4, 1),)
    assert result.corporate_actions_known_from == date(2025, 1, 6)


def test_unknown_corporate_action_window_is_none_not_empty_claim() -> None:
    """株価が無ければ経路1は全くUNKNOWN。Noneで表す。"""
    trend = _financial_trend([_trend("eps", _REAL_EPS), _trend("net_profit", _REAL_NET_PROFIT)])
    result = assess_per_share_comparability(code=CODE, trend=trend)
    assert result.corporate_action_dates == ()
    assert result.corporate_actions_known_from is None


def test_adjustment_factor_of_one_is_not_a_corporate_action_date() -> None:
    """ExRTのみでAdjFactor==1の行を基準変更として扱わない。"""
    trend = _financial_trend([_trend("eps", _REAL_EPS), _trend("net_profit", _REAL_NET_PROFIT)])
    action = CorporateAction(
        code=CODE,
        provider_code="72030",
        action_type=CorporateActionType.ADJUSTMENT_EVENT,
        effective_date=date(2025, 3, 28),
        raw_adj_factor=1.0,
    )
    result = assess_per_share_comparability(code=CODE, trend=trend, corporate_actions=[action])
    assert result.corporate_action_dates == ()


def test_other_codes_actions_are_ignored() -> None:
    trend = _financial_trend([_trend("eps", _REAL_EPS), _trend("net_profit", _REAL_NET_PROFIT)])
    action = CorporateAction(
        code="6758",
        provider_code="67580",
        action_type=CorporateActionType.ADJUSTMENT_EVENT,
        effective_date=date(2025, 4, 1),
        raw_adj_factor=0.2,
    )
    result = assess_per_share_comparability(code=CODE, trend=trend, corporate_actions=[action])
    assert result.corporate_action_dates == ()


def test_tolerance_must_be_positive() -> None:
    trend = _financial_trend([_trend("eps", _REAL_EPS), _trend("net_profit", _REAL_NET_PROFIT)])
    with pytest.raises(ValueError, match="tolerance"):
        assess_per_share_comparability(code=CODE, trend=trend, tolerance=Decimal(0))


def test_default_tolerance_sits_below_the_smallest_split() -> None:
    """最小の分割(2倍)が必ず検知される位置に閾値がある。"""
    assert DEFAULT_DIVISOR_TOLERANCE < 1


# --- BPS(2026-11-24追加) ---

# 7203のFY行。実観測値。FY2022で1株当たり基準が切り替わる。
_REAL_BPS = [
    (date(2021, 3, 31), "8370.88"),
    (date(2022, 3, 31), "1904.88"),
    (date(2023, 3, 31), "2089.08"),
    (date(2024, 3, 31), "2539.75"),
]
_REAL_SHEQ = [
    (date(2021, 3, 31), "23404547000000"),
    (date(2022, 3, 31), "26245969000000"),
    (date(2023, 3, 31), "28338706000000"),
    (date(2024, 3, 31), "34220991000000"),
]


def test_bps_is_watched_by_default() -> None:
    """[回帰] BPSはEPSと同じ不連続を持つ。既定の監視対象に入っている。"""
    assert "bps" in __import__("lib.screener.per_share", fromlist=["x"]).PER_SHARE_METRICS


def test_bps_divisor_is_shareholders_equity_not_net_assets() -> None:
    """除数は自己資本。7203 FY2026で ShEq/BPS と NP/EPS が6桁一致したことから確定。"""
    assert DIVISOR_SOURCES["bps"] == "provider_reported_sheq"
    assert DIVISOR_SOURCES["eps"] == "net_profit"


def test_real_7203_bps_break_is_detected() -> None:
    """[回帰] BPS 8370.88 -> 1904.88 は業績ではなく基準の切り替わり。"""
    trend = _financial_trend([_trend("bps", _REAL_BPS), _trend("provider_reported_sheq", _REAL_SHEQ)])
    result = assess_per_share_comparability(code=CODE, trend=trend, per_share_metrics=["bps"])

    assert len(result.breaks) == 1
    found = result.breaks[0]
    assert found.metric_type == "bps"
    assert found.divisor_source_metric == "provider_reported_sheq"
    assert found.from_fiscal_period_end == date(2021, 3, 31)
    assert found.to_fiscal_period_end == date(2022, 3, 31)
    assert found.divisor_ratio == pytest.approx(Decimal("4.93"), abs=Decimal("0.01"))


def test_eps_and_bps_are_reported_as_separate_breaks() -> None:
    """同じ境界でも指標ごとに1件ずつ出る。除数も別々に記録される。"""
    trend = _financial_trend(
        [
            _trend("eps", _REAL_EPS),
            _trend("net_profit", _REAL_NET_PROFIT),
            _trend("bps", _REAL_BPS),
            _trend("provider_reported_sheq", _REAL_SHEQ),
        ]
    )
    result = assess_per_share_comparability(code=CODE, trend=trend)
    assert {b.metric_type for b in result.breaks} == {"eps", "bps"}
    assert {b.divisor_source_metric for b in result.breaks} == {"net_profit", "provider_reported_sheq"}
    assert dict(result.divisor_sources) == {"eps": "net_profit", "bps": "provider_reported_sheq"}


def test_reit_without_sheq_leaves_bps_unchecked_not_clean() -> None:
    """[回帰] REITは`ShEq`が空(89510: 0/27)。純資産で代用せず、未確認と報告する。"""
    trend = _financial_trend([_trend("bps", _REAL_BPS), _trend("provider_reported_eq", _REAL_SHEQ)])
    result = assess_per_share_comparability(code=CODE, trend=trend, per_share_metrics=["bps"])
    assert result.breaks == ()
    assert "bps" in result.unchecked_metrics
    assert not result.is_comparable_throughout or "bps" in result.unchecked_metrics


def test_metric_without_a_configured_divisor_is_unchecked() -> None:
    """除数の作り方が無い指標を、黙って「問題なし」にしない。"""
    trend = _financial_trend([_trend("distribution_per_unit", [(date(2024, 6, 30), "11500")])])
    result = assess_per_share_comparability(code=CODE, trend=trend, per_share_metrics=["distribution_per_unit"])
    assert result.unchecked_metrics == ("distribution_per_unit",)
    assert result.breaks == ()


def test_dividend_metrics_are_not_in_the_default_watch_list() -> None:
    """配当・分配金は遡及調整されないが、除数が無いので本手法では検知できない。

    監視対象に入れると「検知できたのに不連続が無い」と誤読される。
    """
    from lib.screener.per_share import PER_SHARE_METRICS

    assert "dividend_per_share_annual" not in PER_SHARE_METRICS
    assert "distribution_per_unit" not in PER_SHARE_METRICS


def test_checked_and_unchecked_do_not_overlap() -> None:
    """[回帰] 系列が存在することと、比較できたことは別。

    8951ではBPSの系列はあるが`ShEq`が無いため比較できない。以前は
    `per_share_metrics`(確認済み)と`unchecked_metrics`の両方に入っていた。
    """
    trend = _financial_trend([_trend("bps", _REAL_BPS), _trend("eps", _REAL_EPS), _trend("net_profit", _REAL_NET_PROFIT)])
    result = assess_per_share_comparability(code=CODE, trend=trend)
    assert set(result.per_share_metrics).isdisjoint(result.unchecked_metrics)
    assert "eps" in result.per_share_metrics
    assert "bps" in result.unchecked_metrics


def test_divisor_sources_only_lists_sources_actually_used() -> None:
    """[回帰] 比較できなかった指標の除数を「使った」と報告しない。"""
    trend = _financial_trend([_trend("bps", _REAL_BPS), _trend("eps", _REAL_EPS), _trend("net_profit", _REAL_NET_PROFIT)])
    result = assess_per_share_comparability(code=CODE, trend=trend)
    assert dict(result.divisor_sources) == {"eps": "net_profit"}
