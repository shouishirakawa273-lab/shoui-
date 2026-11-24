"""1画面表示のテスト。実APIには接続しない。

値は2026-11-24の7203実観測に合わせている(PER 9.62/分位41.4%、PBR 1.04/46.8%、
予想配当利回り3.02%、実績2.87%、ROE FY2026 10.1%)。

固定したいのは見た目ではなく**契約**:

- 推奨判定・評価語を出さない(方針書「やらないこと」)
- 取得不可を空欄にしない
- 予想に「予想」ラベルが付く
- 1画面に収まる
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from lib.evidence.model import AvailabilitySemantics
from lib.pretrade_risk.liquidity import LiquidityAssessment, LiquidityOutcome
from lib.screener.dividend_yield import (
    DividendBasis,
    DividendYieldAssessment,
    DividendYieldFigure,
)
from lib.screener.earnings_schedule import EarningsSchedule, ScheduledEarnings
from lib.screener.financial_trend import AnnualObservation, FinancialTrend, MetricTrend
from lib.screener.instrument import InstrumentKind
from lib.screener.per_share import PerShareBreak, PerShareComparability
from lib.screener.render_text import render_entry, render_report
from lib.screener.valuation_percentile import IndicatorPercentile, ValuationPercentiles

AS_OF = datetime(2026, 11, 24, 15, 30, tzinfo=UTC)
CODE = "7203"

# 1画面の上限。方針書の受入基準「1画面」を機械的に守るための線。
MAX_LINES_PER_ENTRY = 24

_FORBIDDEN_WORDS = ("割安", "割高", "買い", "売り", "推奨", "おすすめ", "お得", "狙い目", "有望")


def _trend(roe_points: list[tuple[date, str, str | None]]) -> FinancialTrend:
    by_standard: dict[str | None, list[AnnualObservation]] = {}
    for period_end, value, standard in roe_points:
        by_standard.setdefault(standard, []).append(
            AnnualObservation(
                fiscal_period_end=period_end,
                value=Decimal(value),
                published_at=AS_OF,
                source_version_id=f"V_{period_end}",
                superseded_count=0,
            )
        )
    return FinancialTrend(
        code=CODE,
        decision_at=AS_OF,
        availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT,
        trends=tuple(
            MetricTrend(
                metric_type="provider_reported_roe",
                accounting_standard=standard,
                series_id=f"{CODE}|roe|{standard}",
                observations=tuple(observations),
            )
            for standard, observations in by_standard.items()
        ),
        unmapped_metrics=(),
    )


_REAL_ROE = [
    (date(2017, 3, 31), "0.106", "USGAAP"),
    (date(2018, 3, 31), "0.137", "USGAAP"),
    (date(2019, 3, 31), "0.098", "USGAAP"),
    (date(2020, 3, 31), "0.104", "USGAAP"),
    (date(2021, 3, 31), "0.102", "IFRS"),
    (date(2026, 3, 31), "0.101", "IFRS"),
]


def _liquidity(*, outcome: LiquidityOutcome = LiquidityOutcome.OK) -> LiquidityAssessment:
    return LiquidityAssessment(
        code=CODE,
        as_of=AS_OF,
        position_value=1_000_000.0,
        window_sessions=20,
        sessions_observed=20,
        sessions_known=20,
        sessions_unknown=0,
        duplicate_sessions_dropped=0,
        first_session=date(2026, 10, 23),
        last_session=date(2026, 11, 20),
        staleness_days=4,
        max_staleness_days=10,
        average_daily_turnover=96_294_619_610.0,
        days_to_liquidate=1.0384796202010771e-05,
        threshold_days=3.0,
        outcome=outcome,
        unknown_reason=None if outcome is not LiquidityOutcome.UNKNOWN else "履歴が短い",
    )


def _dividend(*, figures: tuple[DividendYieldFigure, ...] | None = None) -> DividendYieldAssessment:
    if figures is None:
        figures = (
            DividendYieldFigure(
                basis=DividendBasis.FORECAST,
                source_metric_type="dividend_per_share_annual_current_year_forecast",
                dividend=Decimal("100"),
                yield_ratio=Decimal("0.0302"),
                fiscal_period_end=date(2027, 3, 31),
                published_at=AS_OF,
            ),
            DividendYieldFigure(
                basis=DividendBasis.TRAILING,
                source_metric_type="dividend_per_share_annual",
                dividend=Decimal("95"),
                yield_ratio=Decimal("0.0287"),
                fiscal_period_end=date(2026, 3, 31),
                published_at=AS_OF,
            ),
        )
    return DividendYieldAssessment(
        code=CODE,
        instrument_kind=InstrumentKind.SHARE,
        price=Decimal("3310"),
        price_session=date(2026, 11, 20),
        figures=figures,
        unknown_reason=None if figures else "株価が取得できないため算出できない",
    )


def _valuation(*, indicators: tuple[IndicatorPercentile, ...] | None = None) -> ValuationPercentiles:
    if indicators is None:
        indicators = (
            IndicatorPercentile(
                indicator="PER",
                current_value=Decimal("9.62"),
                percentile=Decimal("0.414"),
                sample_size=2440,
                excluded_non_positive=0,
                excluded_missing=0,
                first_session=date(2016, 11, 24),
                last_session=date(2026, 11, 20),
                unknown_reason=None,
            ),
            IndicatorPercentile(
                indicator="PBR",
                current_value=Decimal("1.04"),
                percentile=Decimal("0.468"),
                sample_size=2440,
                excluded_non_positive=0,
                excluded_missing=0,
                first_session=date(2016, 11, 24),
                last_session=date(2026, 11, 20),
                unknown_reason=None,
            ),
        )
    return ValuationPercentiles(
        code=CODE,
        decision_at=AS_OF,
        window_years=10,
        window_start=date(2016, 11, 24),
        current_session=date(2026, 11, 20),
        staleness_days=4,
        indicators=indicators,
        unknown_reason=None,
    )


def _earnings(*, next_scheduled: ScheduledEarnings | None = None) -> EarningsSchedule:
    return EarningsSchedule(
        code=CODE,
        decision_at=AS_OF,
        entries=(),
        next_scheduled=next_scheduled,
        unknown_reason=None if next_scheduled else "判定時点以降の予定日が公表されていない",
    )


def _per_share(*, breaks: tuple[PerShareBreak, ...] = (), unchecked: tuple[str, ...] = ()) -> PerShareComparability:
    return PerShareComparability(
        code=CODE,
        per_share_metrics=("eps",),
        breaks=breaks,
        corporate_action_dates=(),
        corporate_actions_known_from=date(2025, 4, 3),
        divisor_sources=(("eps", "net_profit"),),
        tolerance=Decimal("0.25"),
        unchecked_metrics=unchecked,
    )


def _render(**overrides: object) -> list[str]:
    base: dict[str, object] = {
        "code": CODE,
        "instrument_kind": InstrumentKind.SHARE,
        "as_of": AS_OF,
        "trend": _trend(_REAL_ROE),
        "forecasts": (),
        "liquidity": _liquidity(),
        "dividend": _dividend(),
        "valuation": _valuation(),
        "earnings": _earnings(),
        "per_share": _per_share(),
    }
    base.update(overrides)
    return render_entry(**base)  # type: ignore[arg-type]


# --- 契約: 評価語を出さない ---


def test_no_recommendation_words_anywhere() -> None:
    """方針書「やらないこと: 推奨判定、スコアリング、自動ランキング」。"""
    text = "\n".join(_render())
    for word in _FORBIDDEN_WORDS:
        assert word not in text, f"評価語 '{word}' が出力に含まれている"


def test_percentile_is_shown_without_a_verdict() -> None:
    text = "\n".join(_render())
    assert "41%" in text
    assert "分位" in text


# --- 契約: 取得不可を空欄にしない ---


def test_missing_valuation_states_a_reason() -> None:
    text = "\n".join(_render(valuation=None, instrument_kind=InstrumentKind.REIT))
    assert "取得不可" in text
    assert "REIT" in text


def test_missing_dividend_states_a_reason() -> None:
    dividend = DividendYieldAssessment(
        code=CODE,
        instrument_kind=InstrumentKind.OTHER,
        price=None,
        price_session=None,
        figures=(),
        unknown_reason="株価が取得できないため算出できない",
    )
    text = "\n".join(_render(dividend=dividend))
    assert "取得不可" in text
    assert "株価" in text


def test_unknown_percentile_states_a_reason_not_zero() -> None:
    indicators = (
        IndicatorPercentile(
            indicator="PER",
            current_value=None,
            percentile=None,
            sample_size=2188,
            excluded_non_positive=0,
            excluded_missing=252,
            first_session=date(2016, 11, 24),
            last_session=date(2026, 11, 20),
            unknown_reason="PER の現在値が2026-11-20の行に無い",
        ),
    )
    text = "\n".join(_render(valuation=_valuation(indicators=indicators)))
    assert "取得不可" in text
    assert "0.0%" not in text
    assert "0%" not in text


def test_no_roe_states_a_reason() -> None:
    empty = FinancialTrend(
        code=CODE,
        decision_at=AS_OF,
        availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT,
        trends=(),
        unmapped_metrics=(),
    )
    text = "\n".join(_render(trend=empty))
    assert "ROE" in text
    assert "取得不可" in text


def test_unpublished_next_earnings_date_is_stated_not_replaced_by_a_past_one() -> None:
    """[実データ] 11月下旬に3Q予定日は未公表。過去の日付を代わりに出さない。"""
    text = "\n".join(_render(earnings=_earnings(next_scheduled=None)))
    assert "未公表" in text


# --- 契約: 予想にラベル ---


def test_forecast_dividend_is_labelled_as_a_forecast() -> None:
    """ルート CLAUDE.md ルール1: 予想値にはラベルと出典を付ける。"""
    text = "\n".join(_render())
    assert "予想" in text
    assert "実績" in text


def test_dividend_shows_the_target_period_for_each_basis() -> None:
    text = "\n".join(_render())
    assert "2027-03-31" in text
    assert "2026-03-31" in text


# --- 契約: 警告が出る ---


def test_per_share_break_is_shown_with_its_hedge() -> None:
    found = PerShareBreak(
        metric_type="eps",
        accounting_standard="IFRS",
        from_fiscal_period_end=date(2021, 3, 31),
        to_fiscal_period_end=date(2022, 3, 31),
        divisor_source_metric="net_profit",
        divisor_ratio=Decimal("4.968"),
        detail="...",
    )
    text = "\n".join(_render(per_share=_per_share(breaks=(found,))))
    assert "4.97倍" in text
    assert "断定しない" in text


def test_unchecked_metrics_are_surfaced() -> None:
    text = "\n".join(_render(per_share=_per_share(unchecked=("bps",))))
    assert "bps" in text
    assert "確認できず" in text


def test_corporate_action_window_boundary_is_stated() -> None:
    """空が「イベントなし」と読まれないようにする。"""
    text = "\n".join(_render())
    assert "2025-04-03" in text
    assert "無かったという意味ではない" in text


# --- 契約: ROEの基準が複数なら明示 ---


def test_multiple_accounting_standards_are_flagged() -> None:
    text = "\n".join(_render())
    assert "USGAAP" in text
    assert "IFRS" in text
    assert "基準が複数" in text


def test_single_standard_does_not_add_the_note() -> None:
    single = [(date(2026, 3, 31), "0.101", "IFRS")]
    text = "\n".join(_render(trend=_trend(single)))
    assert "基準が複数" not in text


# --- 契約: 1画面に収まる ---


def test_entry_fits_one_screen() -> None:
    lines = _render()
    assert len(lines) <= MAX_LINES_PER_ENTRY, f"{len(lines)}行は1画面に収まらない"


def test_entry_with_every_warning_still_fits() -> None:
    found = PerShareBreak(
        metric_type="eps",
        accounting_standard="IFRS",
        from_fiscal_period_end=date(2021, 3, 31),
        to_fiscal_period_end=date(2022, 3, 31),
        divisor_source_metric="net_profit",
        divisor_ratio=Decimal("4.968"),
        detail="...",
    )
    lines = _render(
        liquidity=_liquidity(outcome=LiquidityOutcome.WARN),
        per_share=_per_share(breaks=(found, found), unchecked=("bps",)),
    )
    assert len(lines) <= MAX_LINES_PER_ENTRY, f"{len(lines)}行は1画面に収まらない"


def test_lines_are_not_absurdly_wide() -> None:
    for line in _render():
        assert len(line) <= 110, f"{len(line)}文字は折り返す: {line!r}"


# --- レポート全体 ---


def test_report_joins_entries_and_lists_unavailable_metrics() -> None:
    text = render_report(as_of=AS_OF, entries=[_render(), _render()], correlation=None, unavailable=["shares_outstanding"])
    assert text.count(CODE) >= 2
    assert "shares_outstanding" in text


def test_report_without_correlation_or_unavailable_is_just_entries() -> None:
    text = render_report(as_of=AS_OF, entries=[_render()], correlation=None, unavailable=[])
    assert "相関" not in text
    assert "=" * 78 not in text


def test_warn_outcome_is_marked() -> None:
    text = "\n".join(_render(liquidity=_liquidity(outcome=LiquidityOutcome.WARN)))
    assert "⚠" in text


def test_unknown_liquidity_states_a_reason() -> None:
    text = "\n".join(_render(liquidity=_liquidity(outcome=LiquidityOutcome.UNKNOWN)))
    assert "取得不可" in text


@pytest.mark.parametrize("kind", list(InstrumentKind))
def test_every_instrument_kind_renders(kind: InstrumentKind) -> None:
    lines = _render(instrument_kind=kind, valuation=None if kind is not InstrumentKind.SHARE else _valuation())
    assert lines[0].startswith(CODE)
    assert kind.value in lines[0]


# --- 列揃え(全角幅) ---


def test_labels_are_padded_by_display_width_not_character_count() -> None:
    """[回帰] `str.ljust` は文字数で埋めるので日本語ラベルの列が崩れる。

    `配当利回り` は5文字だが等幅端末では10セルを占める。文字数で揃えると
    英字ラベルと並ばない。
    """
    from lib.screener.render_text import _LABEL_WIDTH, _display_width, _label

    for text in ("PER", "PBR", "ROE", "配当利回り", "会社予想(eps)", "流動性", "次回決算発表"):
        assert _display_width(_label(text)) == _LABEL_WIDTH, text


def test_display_width_counts_fullwidth_as_two_cells() -> None:
    from lib.screener.render_text import _display_width

    assert _display_width("PER") == 3
    assert _display_width("配当利回り") == 10
    assert _display_width("会社予想(eps)") == 13


def test_tiny_liquidation_days_do_not_collapse_to_zero() -> None:
    """[回帰] 大型株では `.3f` が全て 0.000 になり情報が消える(7203で1.04e-05日)。"""
    from lib.screener.render_text import _days

    assert "0.01日未満" in _days(1.0384796202010771e-05, 3.0)
    assert "0.000" not in _days(1.0384796202010771e-05, 3.0)
    assert "閾値 3日" in _days(1.0384796202010771e-05, 3.0)


def test_normal_liquidation_days_are_shown_as_numbers() -> None:
    from lib.screener.render_text import _days

    assert "0.40日" in _days(0.4, 3.0)
    assert "5.0日" in _days(5.0, 3.0)
