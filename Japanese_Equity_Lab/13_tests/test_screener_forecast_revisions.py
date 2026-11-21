"""Step 3 会社予想改定履歴の合成データテスト。実APIには一切接続しない。

2026-11-21の実データ確認で、series_idで束ねると「毎年の同じ四半期」が1系列に
なり、別の決算期に対する予想の前年同期比を「改定」と呼ぶ出力になることが判明した。
束ねる単位を対象決算期へ変更した際の回帰テストを含む。
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from lib.evidence.model import AvailabilitySemantics, RevisionHistory, SourceVersion
from lib.fundamentals.model import (
    ActualOrForecast,
    ConsolidationScope,
    DisclosureEnvelope,
    FiscalYearTarget,
    FundamentalMetric,
    PeriodBasis,
    PeriodType,
    ValueAvailability,
)
from lib.screener.forecast_revisions import RevisionDirection, build_forecast_revision_series

DECISION_AT = datetime(2026, 11, 21, 15, 30, tzinfo=UTC)
FY2026 = date(2026, 3, 31)
FY2027 = date(2027, 3, 31)


def _envelope(
    eid: str,
    *,
    period_type: PeriodType,
    current_fy_end: date,
    next_fy_end: date | None = None,
) -> DisclosureEnvelope:
    return DisclosureEnvelope(
        envelope_id=eid,
        provider_code="7203",
        internal_code="7203",
        retrieved_at=DECISION_AT,
        current_period_type=period_type,
        current_fiscal_year_end=current_fy_end,
        next_fiscal_year_end=next_fy_end,
        accounting_standard="IFRS",
    )


def _metric(
    mid: str,
    *,
    target: FiscalYearTarget,
    metric_type: str = "eps_current_year_forecast",
    accounting_standard: str | None = "IFRS",
) -> FundamentalMetric:
    return FundamentalMetric(
        metric_id=mid,
        envelope_id=f"E_{mid}",
        # series_id は意図的にバラバラにする。束ねる単位がこれでないことを示すため。
        series_id=f"7203|{metric_type}|{target.value}|UNUSED|CONSOLIDATED|IFRS|{mid}",
        metric_type=metric_type,
        raw_value="0",
        value=Decimal(0),
        value_availability=ValueAvailability.PRESENT,
        actual_or_forecast=ActualOrForecast.COMPANY_FORECAST,
        fiscal_year_target=target,
        period_type=PeriodType.FY,
        period_basis=PeriodBasis.CUMULATIVE,
        consolidation_scope=ConsolidationScope.CONSOLIDATED,
        accounting_standard=accounting_standard,
        source_field="FEPS",
    )


def _version(mid: str, value: str, published: datetime) -> SourceVersion:
    return SourceVersion(
        source_record_id=f"series_of_{mid}",
        source_version_id=mid,
        value=value,
        available_at=published,
        retrieved_at=DECISION_AT,
        published_at=published,
    )


def _build(
    rows: list[tuple[str, str, datetime, PeriodType, FiscalYearTarget, date, date | None]],
    *,
    metric_type: str = "eps_current_year_forecast",
):
    """rows: (id, value, published_at, 開示期種別, 相対target, 当期末, 翌期末)"""
    metrics, envelopes, histories = [], [], {}
    for mid, value, published, period_type, target, cur_fy, next_fy in rows:
        mtype = (
            metric_type
            if target is FiscalYearTarget.CURRENT_FISCAL_YEAR
            else metric_type.replace("_current_year_", "_next_year_")
        )
        metrics.append(_metric(mid, target=target, metric_type=mtype))
        envelopes.append(_envelope(f"E_{mid}", period_type=period_type, current_fy_end=cur_fy, next_fy_end=next_fy))
        version = _version(mid, value, published)
        histories[version.source_record_id] = RevisionHistory(series_id=version.source_record_id, versions=(version,))
    return build_forecast_revision_series(
        revision_histories=histories,
        metrics=metrics,
        envelopes=envelopes,
        decision_at=DECISION_AT,
        availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT,
    )


def test_one_fiscal_year_is_one_series_across_quarters() -> None:
    """[回帰] FY開示のnext_year と Q1〜Q3のcurrent_year が1本の改定列になる。

    実データ(7203 FY2026 EPS)と同じ形: 237.57 → 204.09 → 224.81 → 273.91。
    """
    C, N = FiscalYearTarget.CURRENT_FISCAL_YEAR, FiscalYearTarget.NEXT_FISCAL_YEAR
    result = _build(
        [
            ("fy", "237.57", datetime(2025, 5, 8, tzinfo=UTC), PeriodType.FY, N, date(2025, 3, 31), FY2026),
            ("q1", "204.09", datetime(2025, 8, 7, tzinfo=UTC), PeriodType.Q1, C, FY2026, FY2027),
            ("q2", "224.81", datetime(2025, 11, 5, tzinfo=UTC), PeriodType.Q2, C, FY2026, FY2027),
            ("q3", "273.91", datetime(2026, 2, 6, tzinfo=UTC), PeriodType.Q3, C, FY2026, FY2027),
        ]
    )

    (series,) = result
    assert series.target_fiscal_year_end == FY2026
    assert series.metric_family == "eps"
    assert [float(r.value) for r in series.revisions if r.value is not None] == [237.57, 204.09, 224.81, 273.91]
    assert [r.disclosure_period_type for r in series.revisions] == [
        PeriodType.FY,
        PeriodType.Q1,
        PeriodType.Q2,
        PeriodType.Q3,
    ]
    assert series.revision_count == 3


def test_different_fiscal_years_are_not_compared() -> None:
    """[回帰] 毎年のQ1開示を1系列にしない。別の決算期は別の列。"""
    C = FiscalYearTarget.CURRENT_FISCAL_YEAR
    result = _build(
        [
            ("a", "204.09", datetime(2025, 8, 7, tzinfo=UTC), PeriodType.Q1, C, FY2026, FY2027),
            ("b", "300.00", datetime(2026, 8, 5, tzinfo=UTC), PeriodType.Q1, C, FY2027, date(2028, 3, 31)),
        ]
    )

    assert len(result) == 2
    assert {s.target_fiscal_year_end for s in result} == {FY2026, FY2027}
    # どちらも初出のみ。年またぎの比較が生まれていないこと。
    for series in result:
        assert series.revision_count == 0
        assert series.revisions[0].direction is RevisionDirection.UNKNOWN
        assert series.revisions[0].change_ratio is None


def test_direction_and_ratio_within_one_fiscal_year() -> None:
    C = FiscalYearTarget.CURRENT_FISCAL_YEAR
    (series,) = _build(
        [
            ("q1", "1000", datetime(2025, 8, 7, tzinfo=UTC), PeriodType.Q1, C, FY2026, FY2027),
            ("q2", "1200", datetime(2025, 11, 5, tzinfo=UTC), PeriodType.Q2, C, FY2026, FY2027),
            ("q3", "900", datetime(2026, 2, 6, tzinfo=UTC), PeriodType.Q3, C, FY2026, FY2027),
        ]
    )

    first, second, third = series.revisions
    assert first.direction is RevisionDirection.UNKNOWN
    assert "first observed forecast for this fiscal year" in (first.unknown_reason or "")
    assert second.direction is RevisionDirection.UP
    assert second.change_ratio == Decimal("0.2")
    assert third.direction is RevisionDirection.DOWN
    assert third.change_ratio == Decimal("-0.25")


def test_unchanged_forecast_is_flat_with_zero_ratio() -> None:
    C = FiscalYearTarget.CURRENT_FISCAL_YEAR
    (series,) = _build(
        [
            ("q1", "1000", datetime(2025, 8, 7, tzinfo=UTC), PeriodType.Q1, C, FY2026, FY2027),
            ("q2", "1000", datetime(2025, 11, 5, tzinfo=UTC), PeriodType.Q2, C, FY2026, FY2027),
        ]
    )

    _, second = series.revisions
    assert second.direction is RevisionDirection.FLAT
    assert second.change_ratio == Decimal(0)


def test_ratio_from_a_zero_base_is_unknown_not_infinite() -> None:
    C = FiscalYearTarget.CURRENT_FISCAL_YEAR
    (series,) = _build(
        [
            ("q1", "0", datetime(2025, 8, 7, tzinfo=UTC), PeriodType.Q1, C, FY2026, FY2027),
            ("q2", "500", datetime(2025, 11, 5, tzinfo=UTC), PeriodType.Q2, C, FY2026, FY2027),
        ]
    )

    _, second = series.revisions
    assert second.direction is RevisionDirection.UP
    assert second.change_ratio is None
    assert "zero" in (second.unknown_reason or "")


def test_negative_base_uses_absolute_denominator() -> None:
    """赤字予想からの改善で符号が反転しないこと。"""
    C = FiscalYearTarget.CURRENT_FISCAL_YEAR
    (series,) = _build(
        [
            ("q1", "-200", datetime(2025, 8, 7, tzinfo=UTC), PeriodType.Q1, C, FY2026, FY2027),
            ("q2", "-100", datetime(2025, 11, 5, tzinfo=UTC), PeriodType.Q2, C, FY2026, FY2027),
        ]
    )

    _, second = series.revisions
    assert second.direction is RevisionDirection.UP
    assert second.change_ratio == Decimal("0.5")


def test_non_numeric_value_does_not_become_the_new_base() -> None:
    C = FiscalYearTarget.CURRENT_FISCAL_YEAR
    (series,) = _build(
        [
            ("q1", "1000", datetime(2025, 8, 7, tzinfo=UTC), PeriodType.Q1, C, FY2026, FY2027),
            ("q2", "", datetime(2025, 11, 5, tzinfo=UTC), PeriodType.Q2, C, FY2026, FY2027),
            ("q3", "1100", datetime(2026, 2, 6, tzinfo=UTC), PeriodType.Q3, C, FY2026, FY2027),
        ]
    )

    _, second, third = series.revisions
    assert second.value is None
    assert second.direction is RevisionDirection.UNKNOWN
    assert third.previous_value == Decimal(1000)
    assert third.change_ratio == Decimal("0.1")


def test_revisions_published_after_decision_at_are_excluded() -> None:
    C = FiscalYearTarget.CURRENT_FISCAL_YEAR
    (series,) = _build(
        [
            ("q1", "1000", datetime(2025, 8, 7, tzinfo=UTC), PeriodType.Q1, C, FY2026, FY2027),
            ("later", "9999", datetime(2026, 12, 1, tzinfo=UTC), PeriodType.Q3, C, FY2026, FY2027),
        ]
    )

    assert [r.source_version_id for r in series.revisions] == ["q1"]


def test_metric_families_are_kept_apart() -> None:
    C = FiscalYearTarget.CURRENT_FISCAL_YEAR
    eps = _build([("q1", "100", datetime(2025, 8, 7, tzinfo=UTC), PeriodType.Q1, C, FY2026, FY2027)])
    op = _build(
        [("q1b", "200", datetime(2025, 8, 7, tzinfo=UTC), PeriodType.Q1, C, FY2026, FY2027)],
        metric_type="operating_profit_current_year_forecast",
    )

    assert eps[0].metric_family == "eps"
    assert op[0].metric_family == "operating_profit"


def test_missing_fiscal_year_end_is_kept_as_unknown_target() -> None:
    """Envelopeに期末日が無ければNoneのまま。推測で埋めない。"""
    metric = _metric("x", target=FiscalYearTarget.NEXT_FISCAL_YEAR, metric_type="eps_next_year_forecast")
    envelope = _envelope("E_x", period_type=PeriodType.FY, current_fy_end=FY2026, next_fy_end=None)
    version = _version("x", "100", datetime(2026, 5, 8, tzinfo=UTC))

    result = build_forecast_revision_series(
        revision_histories={"s": RevisionHistory(series_id="s", versions=(version,))},
        metrics=[metric],
        envelopes=[envelope],
        decision_at=DECISION_AT,
        availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT,
    )

    (series,) = result
    assert series.target_fiscal_year_end is None


def test_accounting_standard_change_within_a_year_is_visible() -> None:
    C = FiscalYearTarget.CURRENT_FISCAL_YEAR
    metrics = [
        _metric("q1", target=C),
        _metric("q2", target=C, accounting_standard=None),
    ]
    envelopes = [
        _envelope("E_q1", period_type=PeriodType.Q1, current_fy_end=FY2026, next_fy_end=FY2027),
        _envelope("E_q2", period_type=PeriodType.Q2, current_fy_end=FY2026, next_fy_end=FY2027),
    ]
    versions = [
        _version("q1", "1000", datetime(2025, 8, 7, tzinfo=UTC)),
        _version("q2", "1100", datetime(2025, 11, 5, tzinfo=UTC)),
    ]
    histories = {v.source_record_id: RevisionHistory(series_id=v.source_record_id, versions=(v,)) for v in versions}

    (series,) = build_forecast_revision_series(
        revision_histories=histories,
        metrics=metrics,
        envelopes=envelopes,
        decision_at=DECISION_AT,
        availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT,
    )

    assert series.accounting_standards == ("IFRS", None)


def test_naive_decision_at_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        build_forecast_revision_series(
            revision_histories={},
            metrics=[],
            envelopes=[],
            decision_at=datetime(2026, 11, 21, 15, 30),
            availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT,
        )
