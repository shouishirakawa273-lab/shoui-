"""Stage 3.6/3.7(D0080/D0081): `financial_quality_metric_to_evidence_market_public_at()`のTest。

Cash Flow(CFO/CFI/CFF、CUMULATIVE)とBalance Sheet(TA/ShEq/EqAR、
POINT_IN_TIME)の両方で、既存`source_version_to_evidence_market_public_at()`
と同じA系統PIT Semanticsを維持しつつ、`metric.period_basis`のTyped Branchで
Contentが正しく分岐すること(CUMULATIVEはperiod=start..end、POINT_IN_TIMEは
value_dateのみ・period_startを表示しない)を確認する。
`source_version_to_evidence_market_public_at()`自体は変更していないため、
既存`test_fundamentals_evidence_market_public_at.py`はそのまま維持する。
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from lib.evidence.model import AvailabilityBasis, AvailabilitySemantics, RevisionHistory, SourceVersion, ValueAvailability
from lib.fundamentals.evidence import (
    MARKET_PUBLIC_AT_SOURCE_TYPE,
    UNIT_STATUS_UNVERIFIED,
    financial_quality_metric_to_evidence_market_public_at,
)
from lib.fundamentals.model import (
    ActualOrForecast,
    ConsolidationScope,
    DisclosureEnvelope,
    FiscalYearTarget,
    FundamentalMetric,
    PeriodBasis,
    PeriodType,
)
from lib.fundamentals.view import fundamentals_as_of

_ENTITY = "7203"
_SERIES = "7203|cash_flow_from_operations|CURRENT_FISCAL_YEAR|2Q|CONSOLIDATED|IFRS"
_STOCK_SERIES = "7203|total_assets|CURRENT_FISCAL_YEAR|2Q|CONSOLIDATED|IFRS"


def _envelope(
    *,
    envelope_id: str = "ENV_TEST_FQ_1",
    market_public_at: datetime | None,
    retrieved_at: datetime = datetime(2026, 8, 16, tzinfo=UTC),
    current_period_start: date | None = date(2024, 4, 1),
    current_period_end: date | None = date(2024, 9, 30),
) -> DisclosureEnvelope:
    return DisclosureEnvelope(
        envelope_id=envelope_id,
        provider_code="72030",
        internal_code=_ENTITY,
        disclosure_number="D1",
        document_type="2QFinancialStatements_Consolidated_IFRS",
        disclosure_date=market_public_at.date() if market_public_at is not None else None,
        disclosure_time=market_public_at.strftime("%H:%M") if market_public_at is not None else None,
        market_public_at=market_public_at,
        retrieved_at=retrieved_at,
        current_period_type=PeriodType.Q2,
        current_period_start=current_period_start,
        current_period_end=current_period_end,
        accounting_standard="IFRS",
    )


def _metric(envelope: DisclosureEnvelope, *, metric_id: str = "MET_TEST_FQ_1", value: str = "1817177000000") -> FundamentalMetric:
    return FundamentalMetric(
        metric_id=metric_id,
        envelope_id=envelope.envelope_id,
        series_id=_SERIES,
        metric_type="cash_flow_from_operations",
        raw_value=value,
        value=Decimal(value),
        value_availability=ValueAvailability.PRESENT,
        actual_or_forecast=ActualOrForecast.ACTUAL,
        fiscal_year_target=FiscalYearTarget.CURRENT_FISCAL_YEAR,
        period_type=PeriodType.Q2,
        period_basis=PeriodBasis.CUMULATIVE,
        consolidation_scope=ConsolidationScope.CONSOLIDATED,
        accounting_standard="IFRS",
        source_field="CFO",
    )


def _version(
    *, published_at: datetime | None, source_version_id: str = "MET_TEST_FQ_1", value: str = "1817177000000"
) -> SourceVersion:
    return SourceVersion(
        source_record_id=_SERIES,
        source_version_id=source_version_id,
        value=value,
        available_at=datetime(2026, 8, 16, tzinfo=UTC),
        retrieved_at=datetime(2026, 8, 16, tzinfo=UTC),
        availability_basis=AvailabilityBasis.UNKNOWN,
        published_at=published_at,
    )


def _stock_metric(
    envelope: DisclosureEnvelope, *, metric_id: str = "MET_TEST_TA_1", value: str = "89169296000000"
) -> FundamentalMetric:
    return FundamentalMetric(
        metric_id=metric_id,
        envelope_id=envelope.envelope_id,
        series_id=_STOCK_SERIES,
        metric_type="total_assets",
        raw_value=value,
        value=Decimal(value),
        value_availability=ValueAvailability.PRESENT,
        actual_or_forecast=ActualOrForecast.ACTUAL,
        fiscal_year_target=FiscalYearTarget.CURRENT_FISCAL_YEAR,
        period_type=PeriodType.Q2,
        period_basis=PeriodBasis.POINT_IN_TIME,
        consolidation_scope=ConsolidationScope.CONSOLIDATED,
        accounting_standard="IFRS",
        source_field="TA",
    )


def _stock_version(
    *, published_at: datetime | None, source_version_id: str = "MET_TEST_TA_1", value: str = "89169296000000"
) -> SourceVersion:
    return SourceVersion(
        source_record_id=_STOCK_SERIES,
        source_version_id=source_version_id,
        value=value,
        available_at=datetime(2026, 8, 16, tzinfo=UTC),
        retrieved_at=datetime(2026, 8, 16, tzinfo=UTC),
        availability_basis=AvailabilityBasis.UNKNOWN,
        published_at=published_at,
    )


def test_point_in_time_evidence_hides_period_start_shows_value_date() -> None:
    """Stage 3.7(D0081): POINT_IN_TIME Metricのcontentはperiod_startを表示せず、
    value_date(=current_period_end)を明示する(§5/§6)。"""
    published_at = datetime(2024, 11, 6, 4, 55, tzinfo=UTC)
    envelope = _envelope(market_public_at=published_at)
    metric = _stock_metric(envelope)
    version = _stock_version(published_at=published_at)

    evidence = financial_quality_metric_to_evidence_market_public_at(
        version, metric=metric, envelope=envelope, entity_code=_ENTITY
    )
    assert "value_date=2024-09-30" in evidence.content
    assert "period=2024-04-01..2024-09-30" not in evidence.content
    assert "2024-04-01" not in evidence.content
    assert "period_type=2Q" in evidence.content
    assert "period_basis=POINT_IN_TIME" in evidence.content
    assert evidence.value_date == date(2024, 9, 30)


def test_point_in_time_unit_and_currency_are_not_guessed() -> None:
    published_at = datetime(2024, 11, 6, 4, 55, tzinfo=UTC)
    envelope = _envelope(market_public_at=published_at)
    metric = _stock_metric(envelope)
    version = _stock_version(published_at=published_at)

    evidence = financial_quality_metric_to_evidence_market_public_at(
        version, metric=metric, envelope=envelope, entity_code=_ENTITY
    )
    assert f"unit={UNIT_STATUS_UNVERIFIED}" in evidence.content
    assert f"currency={UNIT_STATUS_UNVERIFIED}" in evidence.content
    for forbidden in ("JPY", "yen", "円"):
        assert forbidden not in evidence.content


def test_point_in_time_a_path_source_tag_is_preserved() -> None:
    published_at = datetime(2024, 11, 6, 4, 55, tzinfo=UTC)
    envelope = _envelope(market_public_at=published_at)
    metric = _stock_metric(envelope)
    version = _stock_version(published_at=published_at)

    evidence = financial_quality_metric_to_evidence_market_public_at(
        version, metric=metric, envelope=envelope, entity_code=_ENTITY
    )
    assert evidence.source.source_type == MARKET_PUBLIC_AT_SOURCE_TYPE
    assert evidence.source.available_at == published_at


def test_point_in_time_future_disclosure_excluded_by_market_public_at() -> None:
    published_at = datetime(2024, 11, 6, 4, 55, tzinfo=UTC)
    v = _stock_version(published_at=published_at)
    history = RevisionHistory(series_id=_STOCK_SERIES, versions=(v,))
    result = fundamentals_as_of(
        {_STOCK_SERIES: history},
        datetime(2024, 11, 1, tzinfo=UTC),
        availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT,
    )
    assert result[_STOCK_SERIES] is None


def test_point_in_time_unknown_published_at_is_rejected() -> None:
    envelope = _envelope(market_public_at=None)
    metric = _stock_metric(envelope)
    version = _stock_version(published_at=None)

    with pytest.raises(ValueError, match="UNKNOWN"):
        financial_quality_metric_to_evidence_market_public_at(version, metric=metric, envelope=envelope, entity_code=_ENTITY)


def test_point_in_time_future_revision_does_not_leak() -> None:
    old = _stock_version(published_at=datetime(2024, 8, 1, tzinfo=UTC), value="94037319000000", source_version_id="V_OLD")
    new = _stock_version(published_at=datetime(2024, 11, 6, tzinfo=UTC), value="89169296000000", source_version_id="V_NEW")
    history = RevisionHistory(series_id=_STOCK_SERIES, versions=(old, new))

    result = fundamentals_as_of(
        {_STOCK_SERIES: history},
        datetime(2024, 9, 1, tzinfo=UTC),  # newの公表前
        availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT,
    )
    assert result[_STOCK_SERIES] is old


def test_unsupported_period_basis_fails_closed() -> None:
    """CUMULATIVE/POINT_IN_TIME以外のPeriodBasis(例: STANDALONE)では、
    暗黙のContent生成をせずfail closedする(§6のTyped Branch要件)。"""
    published_at = datetime(2024, 11, 6, 4, 55, tzinfo=UTC)
    envelope = _envelope(market_public_at=published_at)
    metric = FundamentalMetric(
        metric_id="MET_TEST_STANDALONE_1",
        envelope_id=envelope.envelope_id,
        series_id="7203|some_standalone_metric|CURRENT_FISCAL_YEAR|2Q|CONSOLIDATED|IFRS",
        metric_type="some_standalone_metric",
        raw_value="1",
        value=Decimal("1"),
        value_availability=ValueAvailability.PRESENT,
        actual_or_forecast=ActualOrForecast.ACTUAL,
        fiscal_year_target=FiscalYearTarget.CURRENT_FISCAL_YEAR,
        period_type=PeriodType.Q2,
        period_basis=PeriodBasis.STANDALONE,
        consolidation_scope=ConsolidationScope.CONSOLIDATED,
        accounting_standard="IFRS",
        source_field="SOME_FIELD",
    )
    version = SourceVersion(
        source_record_id=metric.series_id,
        source_version_id=metric.metric_id,
        value="1",
        available_at=published_at,
        retrieved_at=datetime(2026, 8, 16, tzinfo=UTC),
        availability_basis=AvailabilityBasis.UNKNOWN,
        published_at=published_at,
    )

    with pytest.raises(ValueError, match="period_basis"):
        financial_quality_metric_to_evidence_market_public_at(version, metric=metric, envelope=envelope, entity_code=_ENTITY)


def test_evidence_content_preserves_period_start_and_end() -> None:
    published_at = datetime(2024, 11, 6, 4, 55, tzinfo=UTC)
    envelope = _envelope(market_public_at=published_at)
    metric = _metric(envelope)
    version = _version(published_at=published_at)

    evidence = financial_quality_metric_to_evidence_market_public_at(
        version, metric=metric, envelope=envelope, entity_code=_ENTITY
    )
    assert "2024-04-01" in evidence.content
    assert "2024-09-30" in evidence.content
    assert "period_type=2Q" in evidence.content
    assert "period_basis=CUMULATIVE" in evidence.content
    assert "consolidation_scope=CONSOLIDATED" in evidence.content
    assert "accounting_standard=IFRS" in evidence.content
    assert evidence.value_date == date(2024, 9, 30)


def test_unit_and_currency_are_not_guessed() -> None:
    """Raw PayloadにCurrency/Unit Metadataが確認できていないため、"JPY"/"yen"/"円"を
    推測で書かず、UNIT_STATUS_UNVERIFIEDを明示する(D0079要件)。"""
    published_at = datetime(2024, 11, 6, 4, 55, tzinfo=UTC)
    envelope = _envelope(market_public_at=published_at)
    metric = _metric(envelope)
    version = _version(published_at=published_at)

    evidence = financial_quality_metric_to_evidence_market_public_at(
        version, metric=metric, envelope=envelope, entity_code=_ENTITY
    )
    assert f"unit={UNIT_STATUS_UNVERIFIED}" in evidence.content
    assert f"currency={UNIT_STATUS_UNVERIFIED}" in evidence.content
    for forbidden in ("JPY", "yen", "円"):
        assert forbidden not in evidence.content


def test_a_path_source_tag_is_preserved() -> None:
    published_at = datetime(2024, 11, 6, 4, 55, tzinfo=UTC)
    envelope = _envelope(market_public_at=published_at)
    metric = _metric(envelope)
    version = _version(published_at=published_at)

    evidence = financial_quality_metric_to_evidence_market_public_at(
        version, metric=metric, envelope=envelope, entity_code=_ENTITY
    )
    assert evidence.source.source_type == MARKET_PUBLIC_AT_SOURCE_TYPE
    assert evidence.source.available_at == published_at


def test_unknown_published_at_is_rejected() -> None:
    envelope = _envelope(market_public_at=None)
    metric = _metric(envelope)
    version = _version(published_at=None)

    with pytest.raises(ValueError, match="UNKNOWN"):
        financial_quality_metric_to_evidence_market_public_at(version, metric=metric, envelope=envelope, entity_code=_ENTITY)


def test_metric_version_mismatch_is_rejected() -> None:
    envelope = _envelope(market_public_at=datetime(2024, 11, 6, tzinfo=UTC))
    metric = _metric(envelope, metric_id="MET_TEST_FQ_1")
    mismatched_version = _version(published_at=datetime(2024, 11, 6, tzinfo=UTC), source_version_id="MET_OTHER")

    with pytest.raises(ValueError, match="metric.metric_id"):
        financial_quality_metric_to_evidence_market_public_at(
            mismatched_version, metric=metric, envelope=envelope, entity_code=_ENTITY
        )


def test_metric_envelope_mismatch_is_rejected() -> None:
    envelope_a = _envelope(envelope_id="ENV_A", market_public_at=datetime(2024, 11, 6, tzinfo=UTC))
    envelope_b = _envelope(envelope_id="ENV_B", market_public_at=datetime(2024, 11, 6, tzinfo=UTC))
    metric = _metric(envelope_a)
    version = _version(published_at=datetime(2024, 11, 6, tzinfo=UTC))

    with pytest.raises(ValueError, match="metric.envelope_id"):
        financial_quality_metric_to_evidence_market_public_at(version, metric=metric, envelope=envelope_b, entity_code=_ENTITY)


def test_future_disclosure_excluded_by_market_public_at() -> None:
    """as_ofが開示(market_public_at)より前の場合、A系統selectionはNoneを返す
    (未来の開示を過去へ漏らさない、既存A系統Bridgeと同じ挙動)。"""
    published_at = datetime(2024, 11, 6, 4, 55, tzinfo=UTC)
    v = _version(published_at=published_at)
    history = RevisionHistory(series_id=_SERIES, versions=(v,))
    result = fundamentals_as_of(
        {_SERIES: history}, datetime(2024, 11, 1, tzinfo=UTC), availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT
    )
    assert result[_SERIES] is None


def test_unknown_published_at_excluded_by_fundamentals_as_of() -> None:
    unknown = _version(published_at=None, source_version_id="V_UNKNOWN")
    history = RevisionHistory(series_id=_SERIES, versions=(unknown,))
    result = fundamentals_as_of(
        {_SERIES: history}, datetime(2026, 1, 1, tzinfo=UTC), availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT
    )
    assert result[_SERIES] is None


def test_future_revision_does_not_leak() -> None:
    old = _version(published_at=datetime(2024, 8, 1, tzinfo=UTC), value="683661000000", source_version_id="V_OLD")
    new = _version(published_at=datetime(2024, 11, 6, tzinfo=UTC), value="1817177000000", source_version_id="V_NEW")
    history = RevisionHistory(series_id=_SERIES, versions=(old, new))

    result = fundamentals_as_of(
        {_SERIES: history},
        datetime(2024, 9, 1, tzinfo=UTC),  # newの公表前
        availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT,
    )
    assert result[_SERIES] is old
