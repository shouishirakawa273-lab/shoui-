"""SAME_PERIOD_YOY_CHANGE_RATIO v1(Stage 3.12、D0086): Typed Selector・
Builder・Evidence化・Provenanceを確認する。

Actual-to-Actualのみ(Company Forecastとの比較禁止)、Quarter-only
Derivation(2Q-1Q)禁止、Fiscal Calendarのズレを推測で比較しないこと、
Prior<=0ではRecordを生成しないこと、を最優先で検証する。
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from lib.evidence.model import DataLayer, EvidenceRelation, SourceVersion, ValueAvailability
from lib.evidence.research_artifact import (
    ConfidenceLevel,
    DataGap,
    DataGapStatus,
    NarrativeCase,
    ResearchConclusion,
    build_research_artifact,
)
from lib.evidence.retrieval import ResearchQuestion
from lib.fundamentals.evidence import MARKET_PUBLIC_AT_SOURCE_TYPE
from lib.fundamentals.model import (
    ActualOrForecast,
    ConsolidationScope,
    DisclosureEnvelope,
    FiscalYearTarget,
    FundamentalMetric,
    PeriodBasis,
    PeriodType,
)
from lib.fundamentals.same_period_yoy_builder import build_same_period_yoy_change, select_same_period_yoy_candidates
from lib.fundamentals.same_period_yoy_evidence import same_period_yoy_change_to_evidence
from lib.registry.provenance import ProvenanceLink, ProvenanceStore
from lib.sources.catalog import DataCapability, SourceAuthorityClass

_ENTITY = "7203"
_AS_OF = datetime(2024, 11, 15, 15, 0, tzinfo=UTC)

_CURRENT_FY = (date(2024, 4, 1), date(2025, 3, 31))
_CURRENT_PERIOD = (date(2024, 4, 1), date(2024, 9, 30))
_CURRENT_PUBLISHED_AT = datetime(2024, 11, 6, 4, 55, tzinfo=UTC)

_PRIOR_FY = (date(2023, 4, 1), date(2024, 3, 31))
_PRIOR_PERIOD = (date(2023, 4, 1), date(2023, 9, 30))
_PRIOR_PUBLISHED_AT = datetime(2023, 11, 1, 4, 55, tzinfo=UTC)

_CURRENT_SALES = Decimal("15200000000000")
_PRIOR_SALES = Decimal("15517000000000")


def _envelope(
    *,
    envelope_id: str,
    fy: tuple[date, date],
    period: tuple[date, date],
    period_type: PeriodType = PeriodType.Q2,
    published_at: datetime | None,
    accounting_standard: str | None = "IFRS",
) -> DisclosureEnvelope:
    return DisclosureEnvelope(
        envelope_id=envelope_id,
        provider_code="72030",
        internal_code=_ENTITY,
        disclosure_number="D1",
        document_type="2QFinancialStatements_Consolidated_IFRS",
        disclosure_date=published_at.date() if published_at is not None else None,
        disclosure_time=published_at.strftime("%H:%M") if published_at is not None else None,
        market_public_at=published_at,
        retrieved_at=datetime(2026, 8, 16, tzinfo=UTC),
        current_period_type=period_type,
        current_period_start=period[0],
        current_period_end=period[1],
        current_fiscal_year_start=fy[0],
        current_fiscal_year_end=fy[1],
        accounting_standard=accounting_standard,
    )


def _metric(
    envelope: DisclosureEnvelope,
    *,
    metric_id_suffix: str = "sales",
    value: Decimal,
    metric_type: str = "sales",
    actual_or_forecast: ActualOrForecast = ActualOrForecast.ACTUAL,
    consolidation_scope: ConsolidationScope = ConsolidationScope.CONSOLIDATED,
    period_basis: PeriodBasis = PeriodBasis.CUMULATIVE,
    value_availability: ValueAvailability = ValueAvailability.PRESENT,
    accounting_standard: str | None = "IFRS",
) -> FundamentalMetric:
    return FundamentalMetric(
        metric_id=f"{envelope.envelope_id}_{metric_id_suffix}",
        envelope_id=envelope.envelope_id,
        series_id=f"{_ENTITY}|{metric_type}|CURRENT_FISCAL_YEAR|{envelope.current_period_type.value}|"
        f"{consolidation_scope.value}|{accounting_standard or 'UNKNOWN'}",
        metric_type=metric_type,
        raw_value=str(value) if value is not None else None,
        value=value,
        value_availability=value_availability,
        actual_or_forecast=actual_or_forecast,
        fiscal_year_target=FiscalYearTarget.CURRENT_FISCAL_YEAR,
        period_type=envelope.current_period_type,
        period_basis=period_basis,
        consolidation_scope=consolidation_scope,
        accounting_standard=accounting_standard,
        source_field="Sales",
    )


def _version(envelope: DisclosureEnvelope, metric: FundamentalMetric, *, value: str | None = None) -> SourceVersion:
    return SourceVersion(
        source_record_id=metric.series_id,
        source_version_id=metric.metric_id,
        value=value if value is not None else (metric.raw_value or ""),
        available_at=envelope.retrieved_at,
        retrieved_at=envelope.retrieved_at,
        published_at=envelope.market_public_at,
    )


def _current_triple(**overrides: object):
    envelope = _envelope(
        envelope_id=overrides.get("envelope_id", "ENV_CUR"),
        fy=overrides.get("fy", _CURRENT_FY),
        period=overrides.get("period", _CURRENT_PERIOD),
        period_type=overrides.get("period_type", PeriodType.Q2),
        published_at=overrides.get("published_at", _CURRENT_PUBLISHED_AT),
        accounting_standard=overrides.get("accounting_standard", "IFRS"),
    )
    metric = _metric(
        envelope,
        value=overrides.get("value", _CURRENT_SALES),
        metric_type=overrides.get("metric_type", "sales"),
        actual_or_forecast=overrides.get("actual_or_forecast", ActualOrForecast.ACTUAL),
        consolidation_scope=overrides.get("consolidation_scope", ConsolidationScope.CONSOLIDATED),
        period_basis=overrides.get("period_basis", PeriodBasis.CUMULATIVE),
        value_availability=overrides.get("value_availability", ValueAvailability.PRESENT),
        accounting_standard=overrides.get("accounting_standard", "IFRS"),
    )
    version = _version(envelope, metric, value=overrides.get("version_value"))
    return version, metric, envelope


def _prior_triple(**overrides: object):
    envelope = _envelope(
        envelope_id=overrides.get("envelope_id", "ENV_PRI"),
        fy=overrides.get("fy", _PRIOR_FY),
        period=overrides.get("period", _PRIOR_PERIOD),
        period_type=overrides.get("period_type", PeriodType.Q2),
        published_at=overrides.get("published_at", _PRIOR_PUBLISHED_AT),
        accounting_standard=overrides.get("accounting_standard", "IFRS"),
    )
    metric = _metric(
        envelope,
        value=overrides.get("value", _PRIOR_SALES),
        metric_type=overrides.get("metric_type", "sales"),
        actual_or_forecast=overrides.get("actual_or_forecast", ActualOrForecast.ACTUAL),
        consolidation_scope=overrides.get("consolidation_scope", ConsolidationScope.CONSOLIDATED),
        period_basis=overrides.get("period_basis", PeriodBasis.CUMULATIVE),
        value_availability=overrides.get("value_availability", ValueAvailability.PRESENT),
        accounting_standard=overrides.get("accounting_standard", "IFRS"),
    )
    version = _version(envelope, metric, value=overrides.get("version_value"))
    return version, metric, envelope


# --- §23. Matching -----------------------------------------------------------------------


def test_same_metric_accepted() -> None:
    current = _current_triple()
    prior = _prior_triple()
    result = select_same_period_yoy_candidates(
        [current, prior], entity_code=_ENTITY, as_of=_AS_OF, underlying_metric_type="sales"
    )
    assert result == (current, prior)


def test_different_metric_rejected() -> None:
    current = _current_triple(metric_type="sales")
    prior = _prior_triple(metric_type="operating_profit")
    result = select_same_period_yoy_candidates(
        [current, prior], entity_code=_ENTITY, as_of=_AS_OF, underlying_metric_type="sales"
    )
    assert result is None


def test_same_period_type_accepted() -> None:
    current = _current_triple(period_type=PeriodType.Q2)
    prior = _prior_triple(period_type=PeriodType.Q2)
    result = select_same_period_yoy_candidates(
        [current, prior], entity_code=_ENTITY, as_of=_AS_OF, underlying_metric_type="sales"
    )
    assert result == (current, prior)


def test_different_period_type_rejected() -> None:
    current = _current_triple(period_type=PeriodType.Q2)
    prior = _prior_triple(period_type=PeriodType.Q3, period=(date(2023, 4, 1), date(2023, 12, 31)))
    result = select_same_period_yoy_candidates(
        [current, prior], entity_code=_ENTITY, as_of=_AS_OF, underlying_metric_type="sales"
    )
    assert result is None


def test_same_scope_accepted() -> None:
    current = _current_triple(consolidation_scope=ConsolidationScope.CONSOLIDATED)
    prior = _prior_triple(consolidation_scope=ConsolidationScope.CONSOLIDATED)
    result = select_same_period_yoy_candidates(
        [current, prior], entity_code=_ENTITY, as_of=_AS_OF, underlying_metric_type="sales"
    )
    assert result == (current, prior)


def test_scope_mismatch_rejected() -> None:
    current = _current_triple(consolidation_scope=ConsolidationScope.CONSOLIDATED)
    prior = _prior_triple(consolidation_scope=ConsolidationScope.NON_CONSOLIDATED)
    result = select_same_period_yoy_candidates(
        [current, prior], entity_code=_ENTITY, as_of=_AS_OF, underlying_metric_type="sales"
    )
    assert result is None


def test_same_accounting_standard_accepted() -> None:
    current = _current_triple(accounting_standard="IFRS")
    prior = _prior_triple(accounting_standard="IFRS")
    result = select_same_period_yoy_candidates(
        [current, prior], entity_code=_ENTITY, as_of=_AS_OF, underlying_metric_type="sales"
    )
    assert result == (current, prior)


def test_accounting_standard_mismatch_rejected() -> None:
    current_version, current_metric, current_envelope = _current_triple(accounting_standard="IFRS")
    prior_version, prior_metric, prior_envelope = _prior_triple(accounting_standard="IFRS")
    object.__setattr__(prior_metric, "accounting_standard", "PROVIDER_SUFFIX_JP")
    with pytest.raises(ValueError, match="accounting_standard"):
        build_same_period_yoy_change(
            entity_code=_ENTITY,
            as_of=_AS_OF,
            underlying_metric_type="sales",
            current_version=current_version,
            current_metric=current_metric,
            current_envelope=current_envelope,
            prior_version=prior_version,
            prior_metric=prior_metric,
            prior_envelope=prior_envelope,
        )


def test_cumulative_vs_cumulative_accepted() -> None:
    current = _current_triple(period_basis=PeriodBasis.CUMULATIVE)
    prior = _prior_triple(period_basis=PeriodBasis.CUMULATIVE)
    result = select_same_period_yoy_candidates(
        [current, prior], entity_code=_ENTITY, as_of=_AS_OF, underlying_metric_type="sales"
    )
    assert result == (current, prior)


def test_period_basis_mismatch_rejected_by_selector() -> None:
    current = _current_triple(period_basis=PeriodBasis.CUMULATIVE)
    prior = _prior_triple(period_basis=PeriodBasis.POINT_IN_TIME)
    result = select_same_period_yoy_candidates(
        [current, prior], entity_code=_ENTITY, as_of=_AS_OF, underlying_metric_type="sales"
    )
    assert result is None


def test_prior_exactly_one_fiscal_year_earlier_accepted() -> None:
    current = _current_triple()
    prior = _prior_triple()
    result = select_same_period_yoy_candidates(
        [current, prior], entity_code=_ENTITY, as_of=_AS_OF, underlying_metric_type="sales"
    )
    assert result is not None
    assert result[1][2].current_fiscal_year_start == date(2023, 4, 1)


def test_wrong_prior_fiscal_year_rejected() -> None:
    current = _current_triple()
    wrong_prior = _prior_triple(
        fy=(date(2022, 4, 1), date(2023, 3, 31)),  # 2年前(1年前ではない)
        period=(date(2022, 4, 1), date(2022, 9, 30)),
        published_at=datetime(2022, 11, 1, tzinfo=UTC),
    )
    result = select_same_period_yoy_candidates(
        [current, wrong_prior], entity_code=_ENTITY, as_of=_AS_OF, underlying_metric_type="sales"
    )
    assert result is None


def test_fiscal_calendar_mismatch_fails_closed() -> None:
    """current_period_start/endが1年前と一致しない(FY境界が変わった等)場合、
    推測で比較せずUNAVAILABLEとする。"""
    current = _current_triple()
    mismatched_prior = _prior_triple(period=(date(2023, 6, 1), date(2023, 11, 30)))  # FY一致だがPeriod境界がズレている
    result = select_same_period_yoy_candidates(
        [current, mismatched_prior], entity_code=_ENTITY, as_of=_AS_OF, underlying_metric_type="sales"
    )
    assert result is None


def test_series_id_free_form_parse_not_required() -> None:
    """series_idの文字列内容がTypo等で予期しない形式でも、Typed Fieldsのみで
    Matchingが成立することを確認する(Free-form Parse不要の実装であることの確認)。"""
    current_version, current_metric, current_envelope = _current_triple()
    object.__setattr__(current_metric, "series_id", "COMPLETELY_UNSTRUCTURED_STRING")
    current_version2 = _version(current_envelope, current_metric)
    prior = _prior_triple()
    result = select_same_period_yoy_candidates(
        [(current_version2, current_metric, current_envelope), prior],
        entity_code=_ENTITY,
        as_of=_AS_OF,
        underlying_metric_type="sales",
    )
    assert result is not None


# --- §24. PIT / Revision ------------------------------------------------------------------


def _build_valid_pair():
    return _current_triple(), _prior_triple()


def test_current_published_at_le_as_of_enforced() -> None:
    current, prior = _build_valid_pair()
    record = build_same_period_yoy_change(
        entity_code=_ENTITY,
        as_of=_AS_OF,
        underlying_metric_type="sales",
        current_version=current[0],
        current_metric=current[1],
        current_envelope=current[2],
        prior_version=prior[0],
        prior_metric=prior[1],
        prior_envelope=prior[2],
    )
    assert record is not None
    assert record.current_published_at <= _AS_OF


def test_prior_published_at_le_as_of_enforced() -> None:
    current, prior = _build_valid_pair()
    record = build_same_period_yoy_change(
        entity_code=_ENTITY,
        as_of=_AS_OF,
        underlying_metric_type="sales",
        current_version=current[0],
        current_metric=current[1],
        current_envelope=current[2],
        prior_version=prior[0],
        prior_metric=prior[1],
        prior_envelope=prior[2],
    )
    assert record is not None
    assert record.prior_published_at <= _AS_OF


def test_future_current_excluded_by_selector() -> None:
    current = _current_triple(published_at=_AS_OF.replace(year=2025))
    prior = _prior_triple()
    result = select_same_period_yoy_candidates(
        [current, prior], entity_code=_ENTITY, as_of=_AS_OF, underlying_metric_type="sales"
    )
    assert result is None


def test_future_prior_revision_excluded_by_selector() -> None:
    current = _current_triple()
    future_prior = _prior_triple(published_at=_AS_OF.replace(year=2025))
    result = select_same_period_yoy_candidates(
        [current, future_prior], entity_code=_ENTITY, as_of=_AS_OF, underlying_metric_type="sales"
    )
    assert result is None


def test_unknown_published_at_rejected_by_builder() -> None:
    current, prior = _build_valid_pair()
    unknown_version = SourceVersion(
        source_record_id=current[1].series_id,
        source_version_id=current[1].metric_id,
        value=current[1].raw_value or "",
        available_at=current[2].retrieved_at,
        retrieved_at=current[2].retrieved_at,
        published_at=None,
    )
    with pytest.raises(ValueError, match="UNKNOWN|published_at"):
        build_same_period_yoy_change(
            entity_code=_ENTITY,
            as_of=_AS_OF,
            underlying_metric_type="sales",
            current_version=unknown_version,
            current_metric=current[1],
            current_envelope=current[2],
            prior_version=prior[0],
            prior_metric=prior[1],
            prior_envelope=prior[2],
        )


def test_metric_version_mismatch_rejected() -> None:
    current, prior = _build_valid_pair()
    mismatched_version = SourceVersion(
        source_record_id=current[1].series_id,
        source_version_id="MISMATCHED",
        value=current[1].raw_value or "",
        available_at=current[2].retrieved_at,
        retrieved_at=current[2].retrieved_at,
        published_at=current[2].market_public_at,
    )
    with pytest.raises(ValueError, match="metric_id"):
        build_same_period_yoy_change(
            entity_code=_ENTITY,
            as_of=_AS_OF,
            underlying_metric_type="sales",
            current_version=mismatched_version,
            current_metric=current[1],
            current_envelope=current[2],
            prior_version=prior[0],
            prior_metric=prior[1],
            prior_envelope=prior[2],
        )


def test_metric_envelope_mismatch_rejected() -> None:
    current, prior = _build_valid_pair()
    other_envelope = _envelope(
        envelope_id="ENV_OTHER", fy=_CURRENT_FY, period=_CURRENT_PERIOD, published_at=_CURRENT_PUBLISHED_AT
    )
    with pytest.raises(ValueError, match="envelope_id"):
        build_same_period_yoy_change(
            entity_code=_ENTITY,
            as_of=_AS_OF,
            underlying_metric_type="sales",
            current_version=current[0],
            current_metric=current[1],
            current_envelope=other_envelope,
            prior_version=prior[0],
            prior_metric=prior[1],
            prior_envelope=prior[2],
        )


def test_entity_mismatch_rejected() -> None:
    current, prior = _build_valid_pair()
    with pytest.raises(ValueError, match="entity_code"):
        build_same_period_yoy_change(
            entity_code="9999",
            as_of=_AS_OF,
            underlying_metric_type="sales",
            current_version=current[0],
            current_metric=current[1],
            current_envelope=current[2],
            prior_version=prior[0],
            prior_metric=prior[1],
            prior_envelope=prior[2],
        )


# --- §25. Math -----------------------------------------------------------------------------


def test_decimal_only() -> None:
    current, prior = _build_valid_pair()
    record = build_same_period_yoy_change(
        entity_code=_ENTITY,
        as_of=_AS_OF,
        underlying_metric_type="sales",
        current_version=current[0],
        current_metric=current[1],
        current_envelope=current[2],
        prior_version=prior[0],
        prior_metric=prior[1],
        prior_envelope=prior[2],
    )
    assert record is not None
    assert isinstance(record.change_ratio, Decimal)
    assert isinstance(record.current_value, Decimal)
    assert isinstance(record.prior_value, Decimal)


def test_prior_positive_works() -> None:
    current, prior = _build_valid_pair()
    record = build_same_period_yoy_change(
        entity_code=_ENTITY,
        as_of=_AS_OF,
        underlying_metric_type="sales",
        current_version=current[0],
        current_metric=current[1],
        current_envelope=current[2],
        prior_version=prior[0],
        prior_metric=prior[1],
        prior_envelope=prior[2],
    )
    assert record is not None
    assert record.change_ratio == (_CURRENT_SALES / _PRIOR_SALES) - 1


def test_prior_zero_returns_none() -> None:
    current, _ = _build_valid_pair()
    prior = _prior_triple(value=Decimal("0"))
    record = build_same_period_yoy_change(
        entity_code=_ENTITY,
        as_of=_AS_OF,
        underlying_metric_type="sales",
        current_version=current[0],
        current_metric=current[1],
        current_envelope=current[2],
        prior_version=prior[0],
        prior_metric=prior[1],
        prior_envelope=prior[2],
    )
    assert record is None


def test_prior_negative_returns_none() -> None:
    current, _ = _build_valid_pair()
    prior = _prior_triple(value=Decimal("-500000000000"))
    record = build_same_period_yoy_change(
        entity_code=_ENTITY,
        as_of=_AS_OF,
        underlying_metric_type="sales",
        current_version=current[0],
        current_metric=current[1],
        current_envelope=current[2],
        prior_version=prior[0],
        prior_metric=prior[1],
        prior_envelope=prior[2],
    )
    assert record is None


def test_current_zero_with_prior_positive_works() -> None:
    current = _current_triple(value=Decimal("0"))
    _, prior_metric, prior_envelope = _prior_triple()
    prior_version = _version(prior_envelope, prior_metric)
    record = build_same_period_yoy_change(
        entity_code=_ENTITY,
        as_of=_AS_OF,
        underlying_metric_type="sales",
        current_version=current[0],
        current_metric=current[1],
        current_envelope=current[2],
        prior_version=prior_version,
        prior_metric=prior_metric,
        prior_envelope=prior_envelope,
    )
    assert record is not None
    assert record.current_value == Decimal("0")
    assert record.change_ratio == Decimal("-1")


def test_current_negative_with_prior_positive_works() -> None:
    current = _current_triple(value=Decimal("-1000000000000"))
    _, prior_metric, prior_envelope = _prior_triple()
    prior_version = _version(prior_envelope, prior_metric)
    record = build_same_period_yoy_change(
        entity_code=_ENTITY,
        as_of=_AS_OF,
        underlying_metric_type="sales",
        current_version=current[0],
        current_metric=current[1],
        current_envelope=current[2],
        prior_version=prior_version,
        prior_metric=prior_metric,
        prior_envelope=prior_envelope,
    )
    assert record is not None
    assert record.current_value == Decimal("-1000000000000")


def test_formula_is_reproducible() -> None:
    current, prior = _build_valid_pair()
    record1 = build_same_period_yoy_change(
        entity_code=_ENTITY,
        as_of=_AS_OF,
        underlying_metric_type="sales",
        current_version=current[0],
        current_metric=current[1],
        current_envelope=current[2],
        prior_version=prior[0],
        prior_metric=prior[1],
        prior_envelope=prior[2],
    )
    record2 = build_same_period_yoy_change(
        entity_code=_ENTITY,
        as_of=_AS_OF,
        underlying_metric_type="sales",
        current_version=current[0],
        current_metric=current[1],
        current_envelope=current[2],
        prior_version=prior[0],
        prior_metric=prior[1],
        prior_envelope=prior[2],
    )
    assert record1 is not None
    assert record2 is not None
    assert record1.change_ratio == record2.change_ratio
    assert record1.calculation_expression == record2.calculation_expression


# --- §26. Evidence ---------------------------------------------------------------------

_FORBIDDEN_WORDS = (
    "growth",
    "decline",
    "accelerating",
    "slowing",
    "improved",
    "deteriorated",
    "増収",
    "減収",
    "増益",
    "減益",
    "改善",
    "悪化",
    "成長",
    "鈍化",
)


def _build_record_and_versions():
    current, prior = _build_valid_pair()
    record = build_same_period_yoy_change(
        entity_code=_ENTITY,
        as_of=_AS_OF,
        underlying_metric_type="sales",
        current_version=current[0],
        current_metric=current[1],
        current_envelope=current[2],
        prior_version=prior[0],
        prior_metric=prior[1],
        prior_envelope=prior[2],
    )
    assert record is not None
    return record, current[0], prior[0]


def test_evidence_is_fact() -> None:
    record, _cv, _pv = _build_record_and_versions()
    evidence = same_period_yoy_change_to_evidence(
        record,
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        originating_source="JQUANTS_SOURCE_DATA",
        delivery_provider="JQUANTS",
    )
    from lib.evidence.model import EvidenceType

    assert evidence.evidence_type == EvidenceType.FACT


def test_evidence_is_derived() -> None:
    record, _cv, _pv = _build_record_and_versions()
    evidence = same_period_yoy_change_to_evidence(
        record,
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        originating_source="JQUANTS_SOURCE_DATA",
        delivery_provider="JQUANTS",
    )
    assert evidence.layer == DataLayer.DERIVED


def test_evidence_has_correct_capability() -> None:
    record, _cv, _pv = _build_record_and_versions()
    evidence = same_period_yoy_change_to_evidence(
        record,
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        originating_source="JQUANTS_SOURCE_DATA",
        delivery_provider="JQUANTS",
    )
    assert evidence.capability == DataCapability.FUNDAMENTAL
    assert evidence.source.source_type == MARKET_PUBLIC_AT_SOURCE_TYPE


def test_evidence_available_at_is_max_of_current_and_prior() -> None:
    record, _cv, _pv = _build_record_and_versions()
    evidence = same_period_yoy_change_to_evidence(
        record,
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        originating_source="JQUANTS_SOURCE_DATA",
        delivery_provider="JQUANTS",
    )
    assert evidence.source.available_at == max(record.current_published_at, record.prior_published_at)


def test_evidence_retains_both_period_metadata() -> None:
    record, _cv, _pv = _build_record_and_versions()
    evidence = same_period_yoy_change_to_evidence(
        record,
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        originating_source="JQUANTS_SOURCE_DATA",
        delivery_provider="JQUANTS",
    )
    assert "2024-04-01" in evidence.content
    assert "2024-09-30" in evidence.content
    assert "2023-04-01" in evidence.content
    assert "2023-09-30" in evidence.content


def test_evidence_retains_both_source_versions() -> None:
    record, current_version, prior_version = _build_record_and_versions()
    evidence = same_period_yoy_change_to_evidence(
        record,
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        originating_source="JQUANTS_SOURCE_DATA",
        delivery_provider="JQUANTS",
    )
    assert record.current_source_version_id == current_version.source_version_id
    assert record.prior_source_version_id == prior_version.source_version_id
    assert evidence.value_date == record.current_period_end


def test_dual_parent_provenance(tmp_path: Path) -> None:
    record, current_version, prior_version = _build_record_and_versions()
    evidence = same_period_yoy_change_to_evidence(
        record,
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        originating_source="JQUANTS_SOURCE_DATA",
        delivery_provider="JQUANTS",
    )
    store = ProvenanceStore(tmp_path / "provenance.jsonl")
    store.add_link(
        ProvenanceLink(
            link_id="L_CURRENT",
            from_type="fundamental_source_version",
            from_id=current_version.source_version_id,
            to_type="yoy_evidence",
            to_id=evidence.evidence_id,
        )
    )
    store.add_link(
        ProvenanceLink(
            link_id="L_PRIOR",
            from_type="fundamental_source_version",
            from_id=prior_version.source_version_id,
            to_type="yoy_evidence",
            to_id=evidence.evidence_id,
        )
    )
    parents = [link for link in store.all() if link.to_id == evidence.evidence_id]
    assert len(parents) == 2
    assert {link.from_id for link in parents} == {current_version.source_version_id, prior_version.source_version_id}


def test_research_artifact_accepts_evidence_neutral_relation() -> None:
    record, _cv, _pv = _build_record_and_versions()
    evidence = same_period_yoy_change_to_evidence(
        record,
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        originating_source="JQUANTS_SOURCE_DATA",
        delivery_provider="JQUANTS",
    )
    from lib.evidence.model import AvailabilitySemantics

    artifact, packet = build_research_artifact(
        artifact_id="ART_TEST_YOY_1",
        entity_code=_ENTITY,
        question=ResearchQuestion(question_id="RQ_YOY_1", text="q", as_of=_AS_OF, related_codes=(_ENTITY,)),
        evidence_pool=[evidence],
        relations={evidence.evidence_id: EvidenceRelation.NEUTRAL},
        bull_case=NarrativeCase(summary="Bull Caseは主張しない"),
        base_case=NarrativeCase(summary="SAME_PERIOD_YOY_CHANGE_RATIOを観測", supporting_evidence_ids=(evidence.evidence_id,)),
        bear_case=NarrativeCase(summary="Bear Caseも主張しない"),
        data_confidence=ConfidenceLevel.LOW,
        evidence_confidence=ConfidenceLevel.MEDIUM,
        research_confidence=ConfidenceLevel.LOW,
        conclusion=ResearchConclusion.INCONCLUSIVE,
        conclusion_rationale="YoY Evidence 1件のみ",
        data_gaps=[DataGap(topic="test", status=DataGapStatus.MISSING)],
        fundamentals_availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT,
    )
    assert evidence.evidence_id in artifact.included_evidence_ids
    assert evidence.evidence_id in packet.unknowns or evidence.evidence_id in packet.positive_evidence


def test_evidence_content_has_no_interpretation_words() -> None:
    record, _cv, _pv = _build_record_and_versions()
    evidence = same_period_yoy_change_to_evidence(
        record,
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        originating_source="JQUANTS_SOURCE_DATA",
        delivery_provider="JQUANTS",
    )
    lowered = evidence.content.lower()
    for word in _FORBIDDEN_WORDS:
        assert word.lower() not in lowered, f"禁止語 {word!r} がEvidence content に含まれています: {evidence.content!r}"
