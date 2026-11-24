"""配当利回り(現在値)のテスト。実APIには接続しない。

配当値は2026-11-24の実観測に合わせた形(7203は`DivAnn`が入り`DivUnit`が空、
89510は逆)。要点は**予想と実績を混ぜないこと**と、**取得不可を0や空欄にしない**
こと。
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from lib.evidence.model import AvailabilitySemantics
from lib.screener.dividend_yield import DividendBasis, assess_dividend_yield
from lib.screener.financial_trend import AnnualObservation, FinancialTrend, MetricTrend
from lib.screener.forecast_revisions import (
    ForecastRevision,
    ForecastRevisionSeries,
    RevisionDirection,
    RevisionUnknownReason,
)
from lib.screener.instrument import InstrumentKind

DECISION_AT = datetime(2026, 11, 24, 15, 30, tzinfo=UTC)
PRICE = Decimal("3050")


def _trend(code: str, rows: list[tuple[str, date, str]]) -> FinancialTrend:
    trends = [
        MetricTrend(
            metric_type=metric_type,
            accounting_standard="IFRS",
            series_id=f"{code}|{metric_type}",
            observations=(
                AnnualObservation(
                    fiscal_period_end=period_end,
                    value=Decimal(value),
                    published_at=DECISION_AT,
                    source_version_id=f"V_{metric_type}_{period_end}",
                    superseded_count=0,
                ),
            ),
        )
        for metric_type, period_end, value in rows
    ]
    return FinancialTrend(
        code=code,
        decision_at=DECISION_AT,
        availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT,
        trends=tuple(trends),
        unmapped_metrics=(),
    )


def _forecast_series(family: str, target: date, value: str | None) -> ForecastRevisionSeries:
    return ForecastRevisionSeries(
        metric_family=family,
        target_fiscal_year_end=target,
        decision_at=DECISION_AT,
        availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT,
        revisions=(
            ForecastRevision(
                published_at=DECISION_AT,
                available_at=DECISION_AT,
                disclosure_period_type="2Q",
                source_metric_type=f"{family}_current_year_forecast",
                value=None if value is None else Decimal(value),
                previous_value=None,
                change_ratio=None,
                direction=RevisionDirection.UNKNOWN,
                accounting_standard="IFRS",
                unknown_reason=RevisionUnknownReason.FIRST_OBSERVED if value else None,
                source_version_id="V1",
            ),
        ),
    )


def _assess(**kwargs: object) -> object:
    base: dict[str, object] = {
        "code": "7203",
        "instrument_kind": InstrumentKind.SHARE,
        "price": PRICE,
        "price_session": date(2026, 11, 20),
        "actual_trend": _trend("7203", [("dividend_per_share_annual", date(2026, 3, 31), "95")]),
        "forecast_series": (),
        "decision_at": DECISION_AT,
    }
    base.update(kwargs)
    return assess_dividend_yield(**base)  # type: ignore[arg-type]


def test_trailing_yield_from_actual_dividend() -> None:
    result = _assess()
    trailing = result.trailing  # type: ignore[attr-defined]
    assert trailing.basis is DividendBasis.TRAILING
    assert trailing.dividend == Decimal("95")
    assert trailing.yield_ratio == Decimal("95") / PRICE
    assert trailing.source_metric_type == "dividend_per_share_annual"


def test_forecast_and_trailing_are_both_reported() -> None:
    """予想と実績は別の量。両方あるなら両方出し、どちらかを黙って選ばない。"""
    result = _assess(forecast_series=(_forecast_series("dividend_per_share_annual", date(2027, 3, 31), "100"),))
    bases = {f.basis for f in result.figures}  # type: ignore[attr-defined]
    assert bases == {DividendBasis.FORECAST, DividendBasis.TRAILING}
    assert result.forecast.dividend == Decimal("100")  # type: ignore[attr-defined]
    assert result.trailing.dividend == Decimal("95")  # type: ignore[attr-defined]


def test_missing_forecast_does_not_silently_become_trailing() -> None:
    """[回帰] 片方が無いとき、もう片方を別の名前で出さない。"""
    result = _assess(forecast_series=())
    assert result.forecast is None  # type: ignore[attr-defined]
    assert result.trailing is not None  # type: ignore[attr-defined]


def test_yield_is_a_decimal_ratio_not_a_percentage() -> None:
    result = _assess()
    assert result.trailing.yield_ratio < 1  # type: ignore[attr-defined]
    assert result.trailing.yield_ratio == pytest.approx(Decimal("0.0311"), abs=Decimal("0.0001"))  # type: ignore[attr-defined]


# --- 銘柄種別でFieldを決め打ちする ---


def test_reit_reads_distribution_per_unit() -> None:
    result = _assess(
        code="8951",
        instrument_kind=InstrumentKind.REIT,
        price=Decimal("600000"),
        actual_trend=_trend("8951", [("distribution_per_unit", date(2026, 6, 30), "11500")]),
    )
    assert result.trailing.source_metric_type == "distribution_per_unit"  # type: ignore[attr-defined]
    assert result.trailing.dividend == Decimal("11500")  # type: ignore[attr-defined]


def test_reit_does_not_fall_back_to_per_share_dividend() -> None:
    """[回帰] REITで`dividend_per_share_annual`が空なのは失敗ではなく概念が違う。"""
    result = _assess(
        code="8951",
        instrument_kind=InstrumentKind.REIT,
        actual_trend=_trend("8951", [("dividend_per_share_annual", date(2026, 3, 31), "95")]),
    )
    assert result.figures == ()  # type: ignore[attr-defined]
    assert result.unknown_reason is not None  # type: ignore[attr-defined]


def test_share_does_not_fall_back_to_distribution_per_unit() -> None:
    result = _assess(actual_trend=_trend("7203", [("distribution_per_unit", date(2026, 3, 31), "11500")]))
    assert result.figures == ()  # type: ignore[attr-defined]


@pytest.mark.parametrize("kind", [InstrumentKind.OTHER, InstrumentKind.UNKNOWN])
def test_other_and_unknown_kinds_produce_nothing(kind: InstrumentKind) -> None:
    """どのFieldが適切か確認していない種別では推測で読まない。"""
    result = _assess(instrument_kind=kind)
    assert result.figures == ()  # type: ignore[attr-defined]
    assert kind.value in result.unknown_reason  # type: ignore[attr-defined]


# --- 取得不可を0や空欄にしない ---


def test_missing_price_is_a_stated_reason_not_zero() -> None:
    result = _assess(price=None)
    assert result.figures == ()  # type: ignore[attr-defined]
    assert "株価" in result.unknown_reason  # type: ignore[attr-defined]


@pytest.mark.parametrize("price", [Decimal(0), Decimal(-10)])
def test_non_positive_price_is_rejected(price: Decimal) -> None:
    result = _assess(price=price)
    assert result.figures == ()  # type: ignore[attr-defined]
    assert result.unknown_reason is not None  # type: ignore[attr-defined]


def test_no_dividend_data_is_a_stated_reason() -> None:
    result = _assess(actual_trend=_trend("7203", []))
    assert result.figures == ()  # type: ignore[attr-defined]
    assert result.unknown_reason is not None  # type: ignore[attr-defined]


# --- 予想の決算期の選び方 ---


def test_forecast_picks_the_nearest_future_fiscal_year() -> None:
    result = _assess(
        forecast_series=(
            _forecast_series("dividend_per_share_annual", date(2028, 3, 31), "120"),
            _forecast_series("dividend_per_share_annual", date(2027, 3, 31), "100"),
        )
    )
    assert result.forecast.dividend == Decimal("100")  # type: ignore[attr-defined]
    assert result.forecast.fiscal_period_end == date(2027, 3, 31)  # type: ignore[attr-defined]


def test_past_target_fiscal_years_are_not_used_as_current_forecast() -> None:
    result = _assess(forecast_series=(_forecast_series("dividend_per_share_annual", date(2025, 3, 31), "90"),))
    assert result.forecast is None  # type: ignore[attr-defined]


def test_non_numeric_forecast_is_skipped_for_the_last_valid_value() -> None:
    """年度確定で枠が空になっても、最後の有効値が残る。"""
    series = ForecastRevisionSeries(
        metric_family="dividend_per_share_annual",
        target_fiscal_year_end=date(2027, 3, 31),
        decision_at=DECISION_AT,
        availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT,
        revisions=(
            ForecastRevision(
                published_at=DECISION_AT,
                available_at=DECISION_AT,
                disclosure_period_type="1Q",
                source_metric_type="dividend_per_share_annual_current_year_forecast",
                value=Decimal("100"),
                previous_value=None,
                change_ratio=None,
                direction=RevisionDirection.UNKNOWN,
                accounting_standard="IFRS",
                unknown_reason=RevisionUnknownReason.FIRST_OBSERVED,
                source_version_id="V1",
            ),
            ForecastRevision(
                published_at=DECISION_AT,
                available_at=DECISION_AT,
                disclosure_period_type="FY",
                source_metric_type="dividend_per_share_annual_current_year_forecast",
                value=None,
                previous_value=Decimal("100"),
                change_ratio=None,
                direction=RevisionDirection.UNKNOWN,
                accounting_standard="IFRS",
                unknown_reason=RevisionUnknownReason.TARGET_YEAR_ALREADY_REPORTED,
                source_version_id="V2",
            ),
        ),
    )
    result = _assess(forecast_series=(series,))
    assert result.forecast.dividend == Decimal("100")  # type: ignore[attr-defined]


def test_other_metric_families_are_ignored() -> None:
    """EPS予想を配当予想として読まない。"""
    result = _assess(forecast_series=(_forecast_series("eps", date(2027, 3, 31), "299"),))
    assert result.forecast is None  # type: ignore[attr-defined]


def test_latest_fiscal_period_wins_for_trailing() -> None:
    trend = _trend(
        "7203",
        [("dividend_per_share_annual", date(2025, 3, 31), "75")],
    )
    newer = MetricTrend(
        metric_type="dividend_per_share_annual",
        accounting_standard=None,
        series_id="7203|dividend_per_share_annual|old_standard",
        observations=(
            AnnualObservation(
                fiscal_period_end=date(2026, 3, 31),
                value=Decimal("95"),
                published_at=DECISION_AT,
                source_version_id="V_new",
                superseded_count=0,
            ),
        ),
    )
    trend = FinancialTrend(
        code=trend.code,
        decision_at=trend.decision_at,
        availability_semantics=trend.availability_semantics,
        trends=(*trend.trends, newer),
        unmapped_metrics=(),
    )
    result = _assess(actual_trend=trend)
    assert result.trailing.dividend == Decimal("95")  # type: ignore[attr-defined]
    assert result.trailing.fiscal_period_end == date(2026, 3, 31)  # type: ignore[attr-defined]
