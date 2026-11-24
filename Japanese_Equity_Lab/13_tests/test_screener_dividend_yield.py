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
    assert trailing.basis is DividendBasis.TRAILING_12M
    assert trailing.dividend == Decimal("95")
    assert trailing.yield_ratio == Decimal("95") / PRICE
    assert trailing.source_metric_type == "dividend_per_share_annual"


def test_forecast_and_trailing_are_both_reported() -> None:
    """予想と実績は別の量。両方あるなら両方出し、どちらかを黙って選ばない。"""
    result = _assess(forecast_series=(_forecast_series("dividend_per_share_annual", date(2027, 3, 31), "100"),))
    bases = {f.basis for f in result.figures}  # type: ignore[attr-defined]
    assert bases == {DividendBasis.FORECAST, DividendBasis.TRAILING_12M}
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


# --- 株価がfloatで来る経路(2026-11-24の実行時エラー) ---


def test_float_price_from_the_bar_pipeline_is_accepted() -> None:
    """[回帰] `RawOHLCVBar.close` は float。Decimalと割れず実行時に落ちていた。

    株価パイプラインは意図的にfloat、配当は開示文字列由来でDecimal。利回りは
    両者をまたぐので、境界で変換する。
    """
    result = _assess(price=3050.0)
    assert result.trailing is not None  # type: ignore[attr-defined]
    assert result.price == Decimal("3050")  # type: ignore[attr-defined]


def test_float_price_does_not_leak_binary_expansion() -> None:
    """`Decimal(float)` ではなく `Decimal(str(float))` を使うこと。

    前者だと 0.1 が 0.1000000000000000055511151231257827... になり、
    その展開がそのまま利回りに入る。
    """
    from lib.screener.dividend_yield import _to_decimal_price

    assert _to_decimal_price(0.1) == Decimal("0.1")
    assert str(_to_decimal_price(0.1)) == "0.1"
    assert _to_decimal_price(3050.0) == Decimal("3050.0")


def test_decimal_price_is_passed_through_unchanged() -> None:
    from lib.screener.dividend_yield import _to_decimal_price

    original = Decimal("3050.25")
    assert _to_decimal_price(original) is original


def test_none_price_stays_none() -> None:
    from lib.screener.dividend_yield import _to_decimal_price

    assert _to_decimal_price(None) is None


def test_float_zero_price_is_still_rejected() -> None:
    result = _assess(price=0.0)
    assert result.figures == ()  # type: ignore[attr-defined]
    assert result.unknown_reason is not None  # type: ignore[attr-defined]


# --- 分子は12か月を覆わなければならない(2026-11-24の回帰) ---
#
# 3283(日本プロロジスリート、5月期/11月期)で `1716 / 81900 = 2.10%` と出ていた。
# `DivUnit` は**その決算期の分**なので、半期決算では半年分しか入らない。
# 市場が語る水準は4%台で、**取得できている値を別の量として見せていた。**

REIT_PRICE = Decimal("81900")


def _reit_assess(rows: list[tuple[str, date, str]], **kwargs: object) -> object:
    base: dict[str, object] = {
        "code": "3283",
        "instrument_kind": InstrumentKind.REIT,
        "price": REIT_PRICE,
        "price_session": date(2026, 11, 20),
        "actual_trend": _trend("3283", rows),
        "forecast_series": (),
        "decision_at": DECISION_AT,
    }
    base.update(kwargs)
    return assess_dividend_yield(**base)  # type: ignore[arg-type]


_SEMIANNUAL_ROWS = [
    ("distribution_per_unit", date(2025, 11, 30), "1716"),
    ("distribution_per_unit", date(2026, 5, 31), "1716"),
]


def test_semiannual_reit_distribution_is_summed_to_twelve_months() -> None:
    """[回帰] 半期決算の分配金は、開示済みの連続2期を合算して12か月にする。"""
    trailing = _reit_assess(_SEMIANNUAL_ROWS).trailing  # type: ignore[attr-defined]
    assert trailing.basis is DividendBasis.TRAILING_12M
    assert trailing.dividend == Decimal("3432")
    assert trailing.months_covered == 12
    assert trailing.period_count == 2
    assert trailing.components == (Decimal("1716"), Decimal("1716"))
    # 2.10%ではなく4.19%。半分に見えていたのがこれ。
    assert trailing.yield_ratio == pytest.approx(Decimal("0.0419"), abs=Decimal("0.0001"))
    assert trailing.notes == ()


def test_single_semiannual_period_is_not_doubled() -> None:
    """[回帰] 1期しか無いとき、2倍して年額を作らない(ルートCLAUDE.md 規約3)。

    取得できない値を計算で埋めることになる。期の長さを明示して1期分だけ出す。
    """
    trailing = _reit_assess([_SEMIANNUAL_ROWS[1]]).trailing  # type: ignore[attr-defined]
    assert trailing.basis is DividendBasis.TRAILING_PERIOD
    assert trailing.dividend == Decimal("1716")
    assert trailing.months_covered is None  # 1点では期の長さが分からない。12と仮定しない
    assert trailing.notes  # なぜ年額でないかを必ず持つ


def test_basis_discontinuity_inside_the_window_blocks_summation() -> None:
    """[回帰] 合算する期の間に1口当たり基準の不連続があれば合算しない。

    一株/一口当たり配当は遡及調整されないので、分割をまたぐ和は無意味になる。
    「現在値は段差を踏まない」という当初の論拠は1点を採る限りの話だった。
    """
    trailing = _reit_assess(  # type: ignore[attr-defined]
        _SEMIANNUAL_ROWS,
        basis_break_period_ends=frozenset({date(2026, 5, 31)}),
    ).trailing
    assert trailing.basis is DividendBasis.TRAILING_PERIOD
    assert trailing.dividend == Decimal("1716")  # 合算しない
    assert any("不連続" in note for note in trailing.notes)


def test_basis_discontinuity_before_the_window_does_not_block_summation() -> None:
    """窓の外側の不連続は合算を妨げない。合算されない期の段差は関係しない。

    3283の実データでは不連続が 2024-11-30 → 2025-05-31 にあり、
    合算対象(2025-11-30, 2026-05-31)の外側だった。
    """
    trailing = _reit_assess(  # type: ignore[attr-defined]
        _SEMIANNUAL_ROWS,
        basis_break_period_ends=frozenset({date(2025, 5, 31)}),
    ).trailing
    assert trailing.basis is DividendBasis.TRAILING_12M
    assert trailing.dividend == Decimal("3432")


def test_periods_that_do_not_tile_twelve_months_are_not_summed() -> None:
    """期がタイル状に12か月を覆わないなら合算しない。隙間を埋めて推測しない。"""
    trailing = _reit_assess(  # type: ignore[attr-defined]
        [
            ("distribution_per_unit", date(2026, 1, 31), "800"),
            ("distribution_per_unit", date(2026, 5, 31), "1716"),
        ]
    ).trailing
    assert trailing.basis is DividendBasis.TRAILING_PERIOD
    assert trailing.dividend == Decimal("1716")
    assert trailing.months_covered == 4  # 1期の長さは言えるが、12か月は覆えていない


# --- 実績配当の期別推移(2026-11-24追加) ---
#
# 合算した直近2期だけでは「減少が初めてか、何度目か」が答えられなかった。
# 系列は既に取得していて、表示していないだけだった。

_FIVE_PERIODS = [
    ("distribution_per_unit", date(2024, 5, 31), "600"),
    ("distribution_per_unit", date(2024, 11, 30), "612"),
    ("distribution_per_unit", date(2025, 5, 31), "1830"),
    ("distribution_per_unit", date(2025, 11, 30), "1830"),
    ("distribution_per_unit", date(2026, 5, 31), "1716"),
]


def test_history_covers_every_visible_period_oldest_first() -> None:
    history = _reit_assess(_FIVE_PERIODS).history  # type: ignore[attr-defined]
    assert [p.fiscal_period_end for p in history] == [
        date(2024, 5, 31),
        date(2024, 11, 30),
        date(2025, 5, 31),
        date(2025, 11, 30),
        date(2026, 5, 31),
    ]
    assert [p.value for p in history] == [Decimal(v) for v in ("600", "612", "1830", "1830", "1716")]


def test_history_marks_the_basis_discontinuity() -> None:
    """3283の実データでは 2024-11-30 → 2025-05-31 で約2.99倍。

    印が無ければ 612 → 1830 を「分配金が3倍になった」と読む。
    """
    history = _reit_assess(  # type: ignore[attr-defined]
        _FIVE_PERIODS,
        basis_break_period_ends=frozenset({date(2025, 5, 31)}),
    ).history
    assert [p.basis_break_before for p in history] == [False, False, True, False, False]


def test_first_history_point_is_never_marked() -> None:
    """先頭の点には「直前」が無い。比較対象が系列の外にあるので印を立てない。"""
    history = _reit_assess(  # type: ignore[attr-defined]
        _FIVE_PERIODS,
        basis_break_period_ends=frozenset({date(2024, 5, 31)}),
    ).history
    assert history[0].basis_break_before is False


def test_history_survives_a_missing_price() -> None:
    """推移は株価に依らない。利回りが出せなくても推移は出す。"""
    result = _reit_assess(_FIVE_PERIODS, price=None)
    assert result.figures == ()  # type: ignore[attr-defined]
    assert result.unknown_reason  # type: ignore[attr-defined]
    assert len(result.history) == 5  # type: ignore[attr-defined]
