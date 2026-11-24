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
from lib.pretrade_risk.correlation import CorrelationAssessment, CorrelationOutcome, PairCorrelation
from lib.pretrade_risk.liquidity import LiquidityAssessment, LiquidityOutcome
from lib.screener.dividend_yield import (
    DividendBasis,
    DividendYieldAssessment,
    DividendYieldFigure,
)
from lib.screener.earnings_schedule import EarningsSchedule, ScheduledEarnings
from lib.screener.financial_trend import AnnualObservation, FinancialTrend, MetricTrend
from lib.screener.forecast_revisions import ForecastRevisionSeries
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
                basis=DividendBasis.TRAILING_12M,
                source_metric_type="dividend_per_share_annual",
                dividend=Decimal("95"),
                yield_ratio=Decimal("0.0287"),
                fiscal_period_end=date(2026, 3, 31),
                published_at=AS_OF,
                months_covered=12,
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


# --- 予想: familyを固定しない(2026-11-24の実データで発覚) ---


def _series(family: str, target: date, values: list[str | None]) -> ForecastRevisionSeries:
    from lib.screener.forecast_revisions import (
        ForecastRevision,
        RevisionDirection,
        RevisionUnknownReason,
    )

    return ForecastRevisionSeries(
        metric_family=family,
        target_fiscal_year_end=target,
        decision_at=AS_OF,
        availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT,
        revisions=tuple(
            ForecastRevision(
                published_at=AS_OF,
                available_at=AS_OF,
                disclosure_period_type="2Q",
                source_metric_type=f"{family}_current_year_forecast",
                value=None if v is None else Decimal(v),
                previous_value=None,
                change_ratio=None,
                direction=RevisionDirection.UNKNOWN,
                accounting_standard="IFRS",
                unknown_reason=None if v else RevisionUnknownReason.VALUE_NOT_NUMERIC,
                source_version_id=f"V{i}",
            )
            for i, v in enumerate(values)
        ),
    )


def test_forecast_falls_back_to_a_family_that_has_values() -> None:
    """[回帰] eps固定だと、epsだけ空の銘柄で「取得不可」と出て他の予想が隠れた。

    6758はepsが3系列すべて空だが、営業利益・売上・純利益・配当に値がある。
    8951はepsが空で営業利益・経常利益・売上に値がある。
    """
    forecasts = (
        _series("eps", date(2027, 3, 31), [None, None]),
        _series("operating_profit", date(2027, 3, 31), ["1400000000000", "1500000000000"]),
    )
    text = "\n".join(_render(forecasts=forecasts))
    assert "営業利益" in text
    assert "1.40兆" in text
    assert "1.50兆" in text


def test_forecast_shows_the_declared_priority_order_first() -> None:
    forecasts = (
        _series("sales", date(2027, 3, 31), ["50000000000000"]),
        _series("operating_profit", date(2027, 3, 31), ["4000000000000"]),
        _series("eps", date(2027, 3, 31), ["300"]),
    )
    lines = _render(forecasts=forecasts)
    text = "\n".join(lines)
    assert text.index("営業利益") < text.index("EPS")
    assert "売上" not in text  # 上限2 familyなので表示されない


def test_hidden_forecast_families_are_counted_not_dropped_silently() -> None:
    forecasts = (
        _series("operating_profit", date(2027, 3, 31), ["4000000000000"]),
        _series("eps", date(2027, 3, 31), ["300"]),
        _series("sales", date(2027, 3, 31), ["50000000000000"]),
        _series("net_profit", date(2027, 3, 31), ["3500000000000"]),
    )
    text = "\n".join(_render(forecasts=forecasts))
    assert "他 2 指標あり" in text


def test_all_empty_forecasts_state_a_reason() -> None:
    forecasts = (
        _series("eps", date(2027, 3, 31), [None, None]),
        _series("net_profit", date(2027, 3, 31), [None]),
    )
    text = "\n".join(_render(forecasts=forecasts))
    assert "取得不可" in text
    assert "値のある予想が無い" in text


def test_forecast_picks_the_latest_target_within_a_family() -> None:
    forecasts = (
        _series("eps", date(2026, 3, 31), ["273.91"]),
        _series("eps", date(2027, 3, 31), ["299.95"]),
    )
    text = "\n".join(_render(forecasts=forecasts))
    assert "2027-03-31" in text
    assert "299.95" in text


def test_forecast_is_labelled_as_company_guidance() -> None:
    forecasts = (_series("eps", date(2027, 3, 31), ["299.95"]),)
    text = "\n".join(_render(forecasts=forecasts))
    assert "会社予想、実績ではない" in text


def test_unmapped_accounting_standard_does_not_claim_to_be_unknown() -> None:
    """REITは`_REIT`を意図的にマップしていない。「不明」は誤読を招く。"""
    reit_roe = [(date(2026, 6, 30), "0.033", None)]
    text = "\n".join(_render(trend=_trend(reit_roe), instrument_kind=InstrumentKind.REIT, valuation=None))
    assert "基準不明" not in text
    assert "基準の対応なし" in text


# --- 読みやすさ(2026-11-24の実出力で発覚) ---


def test_amounts_are_rounded_to_tril_and_hundred_million() -> None:
    """[回帰] 営業利益予想が `3000000000000.00` と出ていた(3兆円)。

    13桁の数字列は1画面の目的を損ねる。
    """
    from lib.screener.render_text import _yen

    assert _yen(Decimal("3000000000000")) == "3.00兆"
    assert _yen(Decimal("26476000000")) == "265億"
    assert _yen(Decimal("-1500000000000")) == "-1.50兆"
    assert _yen(Decimal("5000000")) == "5,000,000"


def test_per_share_forecasts_are_not_rounded_to_units() -> None:
    """EPSや配当は円単位のまま。兆・億に丸めない。"""
    forecasts = (_series("eps", date(2027, 3, 31), ["251.25", "299.95"]),)
    text = "\n".join(_render(forecasts=forecasts))
    assert "251.25" in text
    assert "兆" not in text


def test_long_family_names_do_not_collide_with_values() -> None:
    """[回帰] `operating_profit` は18セルでラベル列(14)を超え、値とくっついていた。"""
    forecasts = (_series("operating_profit", date(2027, 3, 31), ["3000000000000"]),)
    text = "\n".join(_render(forecasts=forecasts))
    assert "営業利益" in text
    assert "operating_profit" not in text  # 表示は短縮名、JSONは内部名
    assert "期  " in text  # 期と値のあいだに空白がある


def test_history_is_capped_and_the_count_is_stated() -> None:
    """[回帰] REITは半期開示で10年20点。間引かず末尾を取り、何期中かを明示する。"""
    twenty = [(date(2017 + i // 2, 6 if i % 2 == 0 else 12, 30), f"0.0{23 + i}", "IFRS") for i in range(20)]
    text = "\n".join(_render(trend=_trend(twenty)))
    assert "推移(直近10/20期)" in text


def test_short_history_states_the_plain_count() -> None:
    text = "\n".join(_render())
    assert "推移(6期)" in text
    assert "直近" not in text


def test_revision_count_shares_the_line_with_the_sequence() -> None:
    forecasts = (_series("eps", date(2027, 3, 31), ["251.25", "299.95"]),)
    lines = _render(forecasts=forecasts)
    sequence_lines = [ln for ln in lines if "251.25" in ln]
    assert len(sequence_lines) == 1
    assert "改定" in sequence_lines[0]


# --- 実績の分子が何か月分かを必ず書く(2026-11-24の回帰) ---


def test_twelve_month_trailing_shows_the_summed_components() -> None:
    """半期2期を合算したときは、月数と内訳を出す。合算を隠さない。"""
    dividend = _dividend(
        figures=(
            DividendYieldFigure(
                basis=DividendBasis.TRAILING_12M,
                source_metric_type="distribution_per_unit",
                dividend=Decimal("3432"),
                yield_ratio=Decimal("0.0419"),
                fiscal_period_end=date(2026, 5, 31),
                published_at=AS_OF,
                period_count=2,
                months_covered=12,
                components=(Decimal("1716"), Decimal("1716")),
            ),
        )
    )
    line = next(x for x in _render(dividend=dividend) if "配当利回り" in x)
    assert "実績12か月" in line
    assert "1716+1716円" in line
    assert "まで2期" in line


def test_single_period_trailing_is_not_shown_as_an_annual_figure() -> None:
    """[回帰] 半期の分配金を「実績」とだけ書くと、読み手は年額として読む。

    3283で `1716 / 81900 = 2.10%` が「実績」と並び、市場水準の4%台と
    2倍ずれていた。月数と、年額でない理由を出す。
    """
    dividend = _dividend(
        figures=(
            DividendYieldFigure(
                basis=DividendBasis.TRAILING_PERIOD,
                source_metric_type="distribution_per_unit",
                dividend=Decimal("1716"),
                yield_ratio=Decimal("0.0210"),
                fiscal_period_end=date(2026, 5, 31),
                published_at=AS_OF,
                months_covered=6,
                notes=("開示済みの期が12か月を覆わないため合算しない(6か月 × 1期)",),
            ),
        )
    )
    lines = [x for x in _render(dividend=dividend) if "配当利回り" in x or "年額ではない" in x]
    assert any("実績6か月" in x for x in lines)
    assert any("年額ではない" in x for x in lines)


def test_correlation_prints_every_pair_not_only_breaches() -> None:
    """[回帰] 0.68と0.05が同じ「超えるペアなし」になると、分散の判断に使えない。"""
    pairs = (
        PairCorrelation(
            code_a="3283",
            code_b="2979",
            overlapping_returns=240,
            correlation=0.68,
            max_interval_days=3,
            threshold=0.7,
            outcome=CorrelationOutcome.OK,
        ),
        PairCorrelation(
            code_a="3283",
            code_b="8967",
            overlapping_returns=240,
            correlation=0.05,
            max_interval_days=3,
            threshold=0.7,
            outcome=CorrelationOutcome.OK,
        ),
    )
    assessment = CorrelationAssessment(
        as_of=AS_OF,
        codes=("3283", "2979", "8967"),
        window_sessions=250,
        min_overlap=200,
        threshold=0.7,
        max_staleness_days=3,
        coverage=(),
        pairs=pairs,
    )
    text = render_report(as_of=AS_OF, entries=[_render()], correlation=assessment, unavailable=[])
    assert "0.68" in text
    assert "0.05" in text
    assert "閾値 0.7 を超えるペアなし" in text
