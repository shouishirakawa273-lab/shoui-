"""CURRENT_FY_COMPANY_FORECAST_PER v1(Stage 3.10、D0084): Typed Selector・
Builder・Corporate Action Guard(Forecast-specific window)・Evidence化・
Provenanceを確認する。

genericな「Forward PER」ではないこと、Forecast Horizon(current_fiscal_
year_start/end)とDisclosure Current Period(current_period_start/end)を
混同しないこと、Non-Positive EPSではRecordを生成しないこと、を最優先で
検証する。
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

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
from lib.fundamentals.model import (
    ActualOrForecast,
    ConsolidationScope,
    DisclosureEnvelope,
    FiscalYearTarget,
    FundamentalMetric,
    PeriodBasis,
    PeriodType,
)
from lib.registry.provenance import ProvenanceLink, ProvenanceStore
from lib.schemas.price_data import CorporateAction, CorporateActionType, RawOHLCVBar
from lib.sources.catalog import DataCapability, SourceAuthorityClass
from lib.valuation.current_fy_forecast_builder import (
    build_current_fy_company_forecast_per,
    select_current_fy_company_forecast_eps_candidate,
)
from lib.valuation.evidence import current_fy_company_forecast_per_to_evidence
from lib.valuation.model import CorporateActionBasisStatus

_JST = ZoneInfo("Asia/Tokyo")
_ENTITY = "7203"
_AS_OF = datetime(2024, 11, 15, 15, 0, tzinfo=_JST)
_FY_START = date(2024, 4, 1)
_FY_END = date(2025, 3, 31)
_GUIDANCE_PUBLISHED_AT = datetime(2024, 11, 6, 13, 55, tzinfo=_JST)
_FEPS = Decimal("268.77")


def _bar(session_date: date, close: float) -> RawOHLCVBar:
    return RawOHLCVBar(code=_ENTITY, session_date=session_date, open=close, high=close, low=close, close=close, volume=1000.0)


def _raw_bars() -> list[RawOHLCVBar]:
    return [_bar(date(2024, 11, 13), 2662.0), _bar(date(2024, 11, 14), 2666.0), _bar(date(2024, 11, 15), 2704.0)]


def _forecast_envelope(
    *,
    envelope_id: str = "ENV_7203_2Q2025_FORECAST",
    period_type: PeriodType = PeriodType.Q2,
    published_at: datetime | None = _GUIDANCE_PUBLISHED_AT,
    fiscal_year_start: date | None = _FY_START,
    fiscal_year_end: date | None = _FY_END,
) -> DisclosureEnvelope:
    return DisclosureEnvelope(
        envelope_id=envelope_id,
        provider_code="72030",
        internal_code=_ENTITY,
        disclosure_number="D_2Q2025_FORECAST",
        document_type="2QFinancialStatements_Consolidated_IFRS",
        disclosure_date=published_at.date() if published_at is not None else None,
        disclosure_time=published_at.strftime("%H:%M") if published_at is not None else None,
        market_public_at=published_at,
        retrieved_at=datetime(2026, 8, 16, tzinfo=UTC),
        current_period_type=period_type,
        current_period_start=date(2024, 4, 1),
        current_period_end=date(2024, 9, 30),
        current_fiscal_year_start=fiscal_year_start,
        current_fiscal_year_end=fiscal_year_end,
        accounting_standard="IFRS",
    )


def _forecast_metric(
    envelope: DisclosureEnvelope,
    *,
    metric_id_suffix: str = "eps_current_year_forecast",
    value: Decimal = _FEPS,
    metric_type: str = "eps_current_year_forecast",
    source_field: str = "FEPS",
    actual_or_forecast: ActualOrForecast = ActualOrForecast.COMPANY_FORECAST,
    fiscal_year_target: FiscalYearTarget = FiscalYearTarget.CURRENT_FISCAL_YEAR,
    consolidation_scope: ConsolidationScope = ConsolidationScope.CONSOLIDATED,
    value_availability: ValueAvailability = ValueAvailability.PRESENT,
) -> FundamentalMetric:
    return FundamentalMetric(
        metric_id=f"{envelope.envelope_id}_{metric_id_suffix}",
        envelope_id=envelope.envelope_id,
        series_id=f"{_ENTITY}|{metric_type}|{fiscal_year_target.value}|{envelope.current_period_type.value}|"
        f"{consolidation_scope.value}|IFRS",
        metric_type=metric_type,
        raw_value=str(value) if value is not None else None,
        value=value,
        value_availability=value_availability,
        actual_or_forecast=actual_or_forecast,
        fiscal_year_target=fiscal_year_target,
        period_type=envelope.current_period_type,
        period_basis=PeriodBasis.CUMULATIVE,
        consolidation_scope=consolidation_scope,
        accounting_standard="IFRS",
        source_field=source_field,
    )


def _forecast_version(envelope: DisclosureEnvelope, metric: FundamentalMetric, *, value: str | None = None) -> SourceVersion:
    return SourceVersion(
        source_record_id=metric.series_id,
        source_version_id=metric.metric_id,
        value=value if value is not None else (metric.raw_value or ""),
        available_at=envelope.retrieved_at,
        retrieved_at=envelope.retrieved_at,
        published_at=envelope.market_public_at,
    )


def _triple(**overrides: object) -> tuple[SourceVersion, FundamentalMetric, DisclosureEnvelope]:
    envelope = _forecast_envelope(
        **{
            k: v
            for k, v in overrides.items()
            if k in ("envelope_id", "period_type", "published_at", "fiscal_year_start", "fiscal_year_end")
        }
    )
    metric_kwargs = {
        k: v
        for k, v in overrides.items()
        if k
        in (
            "value",
            "metric_type",
            "source_field",
            "actual_or_forecast",
            "fiscal_year_target",
            "consolidation_scope",
            "value_availability",
        )
    }
    metric = _forecast_metric(envelope, **metric_kwargs)
    version = _forecast_version(envelope, metric)
    return version, metric, envelope


# --- §20. Selector ---------------------------------------------------------------------


def test_current_fy_feps_is_accepted() -> None:
    candidate = _triple()
    selected = select_current_fy_company_forecast_eps_candidate([candidate], entity_code=_ENTITY, as_of=_AS_OF)
    assert selected == candidate


def test_actual_eps_is_rejected() -> None:
    candidate = _triple(metric_type="eps", actual_or_forecast=ActualOrForecast.ACTUAL)
    selected = select_current_fy_company_forecast_eps_candidate([candidate], entity_code=_ENTITY, as_of=_AS_OF)
    assert selected is None


def test_next_fiscal_year_forecast_is_rejected() -> None:
    candidate = _triple(metric_type="eps_next_year_forecast", fiscal_year_target=FiscalYearTarget.NEXT_FISCAL_YEAR)
    selected = select_current_fy_company_forecast_eps_candidate([candidate], entity_code=_ENTITY, as_of=_AS_OF)
    assert selected is None


def test_non_feps_guidance_metric_is_rejected() -> None:
    candidate = _triple(metric_type="sales_current_year_forecast", source_field="FSales", value=Decimal("46000000000000"))
    selected = select_current_fy_company_forecast_eps_candidate([candidate], entity_code=_ENTITY, as_of=_AS_OF)
    assert selected is None


def test_source_field_mismatch_is_rejected() -> None:
    version, metric, envelope = _triple()
    object.__setattr__(metric, "source_field", "NOT_FEPS")
    selected = select_current_fy_company_forecast_eps_candidate([(version, metric, envelope)], entity_code=_ENTITY, as_of=_AS_OF)
    assert selected is None


def test_present_is_required() -> None:
    candidate = _triple(value_availability=ValueAvailability.MISSING_OR_UNSPECIFIED)
    selected = select_current_fy_company_forecast_eps_candidate([candidate], entity_code=_ENTITY, as_of=_AS_OF)
    assert selected is None


def test_forecast_period_start_end_required() -> None:
    candidate = _triple(fiscal_year_start=None, fiscal_year_end=None)
    selected = select_current_fy_company_forecast_eps_candidate([candidate], entity_code=_ENTITY, as_of=_AS_OF)
    assert selected is None


def test_as_of_outside_forecast_target_is_excluded() -> None:
    """FY2024/3(2023-04-01..2024-03-31)向けの古いGuidanceはas_of(2024-11-15)を
    含まないため除外される。"""
    candidate = _triple(fiscal_year_start=date(2023, 4, 1), fiscal_year_end=date(2024, 3, 31))
    selected = select_current_fy_company_forecast_eps_candidate([candidate], entity_code=_ENTITY, as_of=_AS_OF)
    assert selected is None


def test_old_fy2024_3q_not_selected_over_fy2025_2q() -> None:
    old_fy2024_3q = _triple(
        envelope_id="ENV_7203_3Q2024_FORECAST",
        published_at=datetime(2024, 2, 6, 13, 25, tzinfo=_JST),
        fiscal_year_start=date(2023, 4, 1),
        fiscal_year_end=date(2024, 3, 31),
        value=Decimal("332.97"),
    )
    fy2025_2q = _triple()
    selected = select_current_fy_company_forecast_eps_candidate([old_fy2024_3q, fy2025_2q], entity_code=_ENTITY, as_of=_AS_OF)
    assert selected == fy2025_2q


def test_same_target_selects_max_published_at() -> None:
    older = _triple(
        envelope_id="ENV_7203_1Q2025_FORECAST",
        period_type=PeriodType.Q1,
        published_at=datetime(2024, 8, 1, 13, 25, tzinfo=_JST),
        value=Decimal("265.04"),
    )
    newer = _triple()  # 2Q, published 2024-11-06
    selected = select_current_fy_company_forecast_eps_candidate([older, newer], entity_code=_ENTITY, as_of=_AS_OF)
    assert selected == newer


def test_multiple_distinct_active_targets_fail_closed() -> None:
    """通常は起こり得ない(1社に同時に2つのCurrent FYが有効なことは無い)が、
    データ異常に備えfail closedで拒否する。"""
    target_a = _triple(fiscal_year_start=date(2024, 4, 1), fiscal_year_end=date(2025, 3, 31))
    target_b = _triple(envelope_id="ENV_7203_ANOMALY", fiscal_year_start=date(2024, 6, 1), fiscal_year_end=date(2025, 5, 31))
    with pytest.raises(ValueError, match="Target Fiscal Year"):
        select_current_fy_company_forecast_eps_candidate([target_a, target_b], entity_code=_ENTITY, as_of=_AS_OF)


def test_same_latest_timestamp_conflicting_values_fail_closed() -> None:
    version_a, metric_a, envelope_a = _triple(envelope_id="ENV_A")
    version_b, metric_b, envelope_b = _triple(envelope_id="ENV_B", value=Decimal("999.99"))
    # 同一published_atへ揃える(Ambiguity検証のため意図的に同時刻にする)。
    object.__setattr__(envelope_b, "market_public_at", envelope_a.market_public_at)
    version_b2 = _forecast_version(envelope_b, metric_b)
    with pytest.raises(ValueError, match="一意に選定できません"):
        select_current_fy_company_forecast_eps_candidate(
            [(version_a, metric_a, envelope_a), (version_b2, metric_b, envelope_b)], entity_code=_ENTITY, as_of=_AS_OF
        )


def test_future_published_at_is_rejected_by_selector() -> None:
    candidate = _triple(published_at=_AS_OF.replace(year=2025))
    selected = select_current_fy_company_forecast_eps_candidate([candidate], entity_code=_ENTITY, as_of=_AS_OF)
    assert selected is None


def test_unknown_published_at_is_rejected_by_selector() -> None:
    candidate = _triple(published_at=None)
    selected = select_current_fy_company_forecast_eps_candidate([candidate], entity_code=_ENTITY, as_of=_AS_OF)
    assert selected is None


# --- §21. Join / Value(Builder) --------------------------------------------------------


def test_entity_mismatch_is_rejected() -> None:
    version, metric, envelope = _triple()
    with pytest.raises(ValueError, match="一致しません"):
        build_current_fy_company_forecast_per(
            entity_code="9999",
            as_of=_AS_OF,
            raw_bars=_raw_bars(),
            corporate_action_events=[],
            guidance_version=version,
            guidance_metric=metric,
            guidance_envelope=envelope,
        )


def test_metric_version_mismatch_is_rejected() -> None:
    _version, metric, envelope = _triple()
    mismatched_version = SourceVersion(
        source_record_id=metric.series_id,
        source_version_id="MISMATCHED",
        value=metric.raw_value or "",
        available_at=envelope.retrieved_at,
        retrieved_at=envelope.retrieved_at,
        published_at=envelope.market_public_at,
    )
    with pytest.raises(ValueError, match="metric_id"):
        build_current_fy_company_forecast_per(
            entity_code=_ENTITY,
            as_of=_AS_OF,
            raw_bars=_raw_bars(),
            corporate_action_events=[],
            guidance_version=mismatched_version,
            guidance_metric=metric,
            guidance_envelope=envelope,
        )


def test_metric_envelope_mismatch_is_rejected() -> None:
    version, metric, _envelope = _triple()
    other_envelope = _forecast_envelope(envelope_id="ENV_OTHER")
    with pytest.raises(ValueError, match="envelope_id"):
        build_current_fy_company_forecast_per(
            entity_code=_ENTITY,
            as_of=_AS_OF,
            raw_bars=_raw_bars(),
            corporate_action_events=[],
            guidance_version=version,
            guidance_metric=metric,
            guidance_envelope=other_envelope,
        )


def test_version_source_record_id_mismatch_is_rejected() -> None:
    _version, metric, envelope = _triple()
    mismatched_version = SourceVersion(
        source_record_id="MISMATCHED_SERIES",
        source_version_id=metric.metric_id,
        value=metric.raw_value or "",
        available_at=envelope.retrieved_at,
        retrieved_at=envelope.retrieved_at,
        published_at=envelope.market_public_at,
    )
    with pytest.raises(ValueError, match="source_record_id"):
        build_current_fy_company_forecast_per(
            entity_code=_ENTITY,
            as_of=_AS_OF,
            raw_bars=_raw_bars(),
            corporate_action_events=[],
            guidance_version=mismatched_version,
            guidance_metric=metric,
            guidance_envelope=envelope,
        )


def test_version_value_metric_value_mismatch_is_rejected() -> None:
    _version, metric, envelope = _triple()
    mismatched_version = _forecast_version(envelope, metric, value="1.23")
    with pytest.raises(ValueError, match="一致しません"):
        build_current_fy_company_forecast_per(
            entity_code=_ENTITY,
            as_of=_AS_OF,
            raw_bars=_raw_bars(),
            corporate_action_events=[],
            guidance_version=mismatched_version,
            guidance_metric=metric,
            guidance_envelope=envelope,
        )


def test_zero_eps_returns_none() -> None:
    version, metric, envelope = _triple(value=Decimal("0"))
    record = build_current_fy_company_forecast_per(
        entity_code=_ENTITY,
        as_of=_AS_OF,
        raw_bars=_raw_bars(),
        corporate_action_events=[],
        guidance_version=version,
        guidance_metric=metric,
        guidance_envelope=envelope,
    )
    assert record is None


def test_negative_eps_returns_none() -> None:
    version, metric, envelope = _triple(value=Decimal("-12.5"))
    record = build_current_fy_company_forecast_per(
        entity_code=_ENTITY,
        as_of=_AS_OF,
        raw_bars=_raw_bars(),
        corporate_action_events=[],
        guidance_version=version,
        guidance_metric=metric,
        guidance_envelope=envelope,
    )
    assert record is None


def test_positive_eps_succeeds() -> None:
    version, metric, envelope = _triple()
    record = build_current_fy_company_forecast_per(
        entity_code=_ENTITY,
        as_of=_AS_OF,
        raw_bars=_raw_bars(),
        corporate_action_events=[],
        guidance_version=version,
        guidance_metric=metric,
        guidance_envelope=envelope,
    )
    assert record is not None
    assert record.eps_value == _FEPS
    assert record.multiple == Decimal("2666") / _FEPS


# --- §22. Price / Corporate Action ------------------------------------------------------


def test_same_day_close_rejected_at_1500() -> None:
    version, metric, envelope = _triple()
    record = build_current_fy_company_forecast_per(
        entity_code=_ENTITY,
        as_of=_AS_OF,
        raw_bars=_raw_bars(),
        corporate_action_events=[],
        guidance_version=version,
        guidance_metric=metric,
        guidance_envelope=envelope,
    )
    assert record is not None
    assert record.price_date == date(2024, 11, 14)


def test_1114_close_selected() -> None:
    version, metric, envelope = _triple()
    record = build_current_fy_company_forecast_per(
        entity_code=_ENTITY,
        as_of=_AS_OF,
        raw_bars=_raw_bars(),
        corporate_action_events=[],
        guidance_version=version,
        guidance_metric=metric,
        guidance_envelope=envelope,
    )
    assert record is not None
    assert record.price_value == Decimal("2666")


def test_no_corporate_action_succeeds() -> None:
    version, metric, envelope = _triple()
    record = build_current_fy_company_forecast_per(
        entity_code=_ENTITY,
        as_of=_AS_OF,
        raw_bars=_raw_bars(),
        corporate_action_events=[],
        guidance_version=version,
        guidance_metric=metric,
        guidance_envelope=envelope,
    )
    assert record is not None
    assert record.corporate_action_basis_status == CorporateActionBasisStatus.CONFIRMED_NO_ACTION


def test_action_on_forecast_period_start_fails_closed() -> None:
    version, metric, envelope = _triple()
    action = CorporateAction(
        code=_ENTITY, action_type=CorporateActionType.ADJUSTMENT_EVENT, effective_date=_FY_START, raw_adj_factor=0.5
    )
    record = build_current_fy_company_forecast_per(
        entity_code=_ENTITY,
        as_of=_AS_OF,
        raw_bars=_raw_bars(),
        corporate_action_events=[action],
        guidance_version=version,
        guidance_metric=metric,
        guidance_envelope=envelope,
    )
    assert record is None


def test_action_between_forecast_start_and_price_date_fails_closed() -> None:
    version, metric, envelope = _triple()
    action = CorporateAction(
        code=_ENTITY, action_type=CorporateActionType.ADJUSTMENT_EVENT, effective_date=date(2024, 9, 2), raw_adj_factor=0.5
    )
    record = build_current_fy_company_forecast_per(
        entity_code=_ENTITY,
        as_of=_AS_OF,
        raw_bars=_raw_bars(),
        corporate_action_events=[action],
        guidance_version=version,
        guidance_metric=metric,
        guidance_envelope=envelope,
    )
    assert record is None


def test_action_on_price_date_fails_closed() -> None:
    version, metric, envelope = _triple()
    action = CorporateAction(
        code=_ENTITY, action_type=CorporateActionType.ADJUSTMENT_EVENT, effective_date=date(2024, 11, 14), raw_adj_factor=0.5
    )
    record = build_current_fy_company_forecast_per(
        entity_code=_ENTITY,
        as_of=_AS_OF,
        raw_bars=_raw_bars(),
        corporate_action_events=[action],
        guidance_version=version,
        guidance_metric=metric,
        guidance_envelope=envelope,
    )
    assert record is None


def test_event_before_forecast_period_start_does_not_trigger_window() -> None:
    version, metric, envelope = _triple()
    action = CorporateAction(
        code=_ENTITY, action_type=CorporateActionType.ADJUSTMENT_EVENT, effective_date=date(2024, 3, 31), raw_adj_factor=0.5
    )
    record = build_current_fy_company_forecast_per(
        entity_code=_ENTITY,
        as_of=_AS_OF,
        raw_bars=_raw_bars(),
        corporate_action_events=[action],
        guidance_version=version,
        guidance_metric=metric,
        guidance_envelope=envelope,
    )
    assert record is not None


def test_future_event_after_price_date_does_not_trigger_window() -> None:
    version, metric, envelope = _triple()
    action = CorporateAction(
        code=_ENTITY, action_type=CorporateActionType.ADJUSTMENT_EVENT, effective_date=date(2024, 11, 15), raw_adj_factor=0.5
    )
    record = build_current_fy_company_forecast_per(
        entity_code=_ENTITY,
        as_of=_AS_OF,
        raw_bars=_raw_bars(),
        corporate_action_events=[action],
        guidance_version=version,
        guidance_metric=metric,
        guidance_envelope=envelope,
    )
    assert record is not None


# --- §23. Evidence / Provenance ----------------------------------------------------------

_FORBIDDEN_WORDS = (
    "cheap",
    "expensive",
    "undervalued",
    "overvalued",
    "attractive",
    "upside",
    "downside",
    "buy",
    "sell",
    "割安",
    "割高",
)


def _build_record() -> tuple:
    version, metric, envelope = _triple()
    record = build_current_fy_company_forecast_per(
        entity_code=_ENTITY,
        as_of=_AS_OF,
        raw_bars=_raw_bars(),
        corporate_action_events=[],
        guidance_version=version,
        guidance_metric=metric,
        guidance_envelope=envelope,
    )
    assert record is not None
    return record, version


def test_evidence_is_fact_derived_valuation() -> None:
    record, _version = _build_record()
    evidence = current_fy_company_forecast_per_to_evidence(
        record,
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        originating_source="JQUANTS_SOURCE_DATA",
        delivery_provider="JQUANTS",
    )
    assert evidence.layer == DataLayer.DERIVED
    assert evidence.capability == DataCapability.VALUATION


def test_evidence_available_at_is_max_of_price_and_guidance() -> None:
    record, _version = _build_record()
    evidence = current_fy_company_forecast_per_to_evidence(
        record,
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        originating_source="JQUANTS_SOURCE_DATA",
        delivery_provider="JQUANTS",
    )
    assert evidence.source.available_at == max(record.price_available_at, record.guidance_published_at)


def test_evidence_value_date_is_price_date() -> None:
    record, _version = _build_record()
    evidence = current_fy_company_forecast_per_to_evidence(
        record,
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        originating_source="JQUANTS_SOURCE_DATA",
        delivery_provider="JQUANTS",
    )
    assert evidence.value_date == record.price_date


def test_evidence_content_retains_forecast_period() -> None:
    record, _version = _build_record()
    evidence = current_fy_company_forecast_per_to_evidence(
        record,
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        originating_source="JQUANTS_SOURCE_DATA",
        delivery_provider="JQUANTS",
    )
    assert "2024-04-01..2025-03-31" in evidence.content
    assert "disclosure_period_type=2Q" in evidence.content


def test_evidence_content_shows_company_forecast_identity() -> None:
    record, _version = _build_record()
    evidence = current_fy_company_forecast_per_to_evidence(
        record,
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        originating_source="JQUANTS_SOURCE_DATA",
        delivery_provider="JQUANTS",
    )
    assert "CURRENT_FY_COMPANY_FORECAST_PER" in evidence.content
    assert "FORWARD_PER" not in evidence.content


def test_evidence_content_has_no_interpretation_words() -> None:
    record, _version = _build_record()
    evidence = current_fy_company_forecast_per_to_evidence(
        record,
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        originating_source="JQUANTS_SOURCE_DATA",
        delivery_provider="JQUANTS",
    )
    lowered = evidence.content.lower()
    for word in _FORBIDDEN_WORDS:
        assert word not in lowered, f"禁止語 {word!r} がEvidence content に含まれています: {evidence.content!r}"


def test_evidence_traces_to_price_and_guidance_parents(tmp_path: Path) -> None:
    record, version = _build_record()
    evidence = current_fy_company_forecast_per_to_evidence(
        record,
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        originating_source="JQUANTS_SOURCE_DATA",
        delivery_provider="JQUANTS",
    )
    store = ProvenanceStore(tmp_path / "provenance.jsonl")
    store.add_link(
        ProvenanceLink(
            link_id="L_PRICE",
            from_type="price_bar",
            from_id=f"{_ENTITY}:{record.price_date.isoformat()}",
            to_type="valuation_evidence",
            to_id=evidence.evidence_id,
        )
    )
    store.add_link(
        ProvenanceLink(
            link_id="L_GUIDANCE",
            from_type="fundamental_source_version",
            from_id=version.source_version_id,
            to_type="valuation_evidence",
            to_id=evidence.evidence_id,
        )
    )
    parents = [link for link in store.all() if link.to_id == evidence.evidence_id]
    assert len(parents) == 2
    assert {link.from_type for link in parents} == {"price_bar", "fundamental_source_version"}


def test_research_artifact_accepts_evidence_with_neutral_relation() -> None:
    record, _version = _build_record()
    evidence = current_fy_company_forecast_per_to_evidence(
        record,
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        originating_source="JQUANTS_SOURCE_DATA",
        delivery_provider="JQUANTS",
    )
    artifact, packet = build_research_artifact(
        artifact_id="ART_TEST_CURRENT_FY_FORECAST_PER_1",
        entity_code=_ENTITY,
        question=ResearchQuestion(question_id="RQ_CFY_1", text="q", as_of=_AS_OF, related_codes=(_ENTITY,)),
        evidence_pool=[evidence],
        relations={evidence.evidence_id: EvidenceRelation.NEUTRAL},
        bull_case=NarrativeCase(summary="Bull Caseは主張しない"),
        base_case=NarrativeCase(summary="CURRENT_FY_COMPANY_FORECAST_PERを観測", supporting_evidence_ids=(evidence.evidence_id,)),
        bear_case=NarrativeCase(summary="Bear Caseも主張しない"),
        data_confidence=ConfidenceLevel.LOW,
        evidence_confidence=ConfidenceLevel.MEDIUM,
        research_confidence=ConfidenceLevel.LOW,
        conclusion=ResearchConclusion.INCONCLUSIVE,
        conclusion_rationale="Valuation Evidence 1件のみ",
        data_gaps=[DataGap(topic="test", status=DataGapStatus.MISSING)],
    )
    assert evidence.evidence_id in artifact.included_evidence_ids
    assert evidence.evidence_id in packet.unknowns or evidence.evidence_id in packet.positive_evidence
