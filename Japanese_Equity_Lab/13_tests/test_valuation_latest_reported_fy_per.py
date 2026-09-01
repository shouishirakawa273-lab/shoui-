"""LATEST_REPORTED_FY_PER v1(D0077): Price Selector・Fundamental Denominator
(A系統)・Corporate Action Guard・Evidence化・Provenanceを確認する。

「Trailing PER」ではない、「割安/割高」等のInterpretationは一切含まない、
という要件を最優先で検証する。
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from lib.errors import LookAheadBiasError
from lib.evidence.model import (
    AvailabilitySemantics,
    DataLayer,
    EvidenceRecord,
    EvidenceRelation,
    EvidenceType,
    SourceVersion,
    ValueAvailability,
)
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
from lib.fundamentals.view import fundamentals_as_of
from lib.registry.provenance import ProvenanceLink, ProvenanceStore
from lib.schemas.price_data import CorporateAction, CorporateActionType, RawOHLCVBar
from lib.sources.catalog import DataCapability, PrimaryOrSecondary, SourceAuthorityClass, SourceMetadata
from lib.valuation.builder import build_latest_reported_fy_per, select_latest_close_bar
from lib.valuation.evidence import (
    is_latest_reported_fy_per_evidence,
    is_latest_reported_fy_per_v2_evidence,
    latest_reported_fy_per_to_evidence,
    latest_reported_fy_per_to_evidence_v2,
)
from lib.valuation.model import CorporateActionBasisStatus

_JST = ZoneInfo("Asia/Tokyo")
_ENTITY = "7203"
_AS_OF = datetime(2024, 11, 15, 15, 0, tzinfo=_JST)
_FY_END = date(2024, 3, 31)
_FY_PUBLISHED_AT = datetime(2024, 5, 8, 13, 55, tzinfo=_JST)
_FY_EPS = Decimal("365.94")


def _bar(session_date: date, close: float) -> RawOHLCVBar:
    return RawOHLCVBar(code=_ENTITY, session_date=session_date, open=close, high=close, low=close, close=close, volume=1000.0)


def _raw_bars() -> list[RawOHLCVBar]:
    return [_bar(date(2024, 11, 13), 2662.0), _bar(date(2024, 11, 14), 2666.0), _bar(date(2024, 11, 15), 2704.0)]


def _fy_eps_envelope() -> DisclosureEnvelope:
    return DisclosureEnvelope(
        envelope_id="ENV_7203_FY2024",
        provider_code="72030",
        internal_code=_ENTITY,
        disclosure_number="D_FY2024",
        document_type="FYFinancialStatements_Consolidated_IFRS",
        disclosure_date=_FY_PUBLISHED_AT.date(),
        disclosure_time="13:55",
        market_public_at=_FY_PUBLISHED_AT,
        retrieved_at=datetime(2026, 8, 16, tzinfo=UTC),
        current_period_type=PeriodType.FY,
        current_period_end=_FY_END,
    )


def _fy_eps_metric(envelope: DisclosureEnvelope, *, value: Decimal = _FY_EPS) -> FundamentalMetric:
    return FundamentalMetric(
        metric_id=f"{envelope.envelope_id}_eps",
        envelope_id=envelope.envelope_id,
        series_id=f"{_ENTITY}|eps|CURRENT_FISCAL_YEAR|FY|CONSOLIDATED|IFRS",
        metric_type="eps",
        raw_value=str(value),
        value=value,
        value_availability=ValueAvailability.PRESENT,
        actual_or_forecast=ActualOrForecast.ACTUAL,
        fiscal_year_target=FiscalYearTarget.CURRENT_FISCAL_YEAR,
        period_type=PeriodType.FY,
        period_basis=PeriodBasis.CUMULATIVE,
        consolidation_scope=ConsolidationScope.CONSOLIDATED,
        accounting_standard="IFRS",
        source_field="EPS",
    )


def _fy_eps_version(envelope: DisclosureEnvelope, metric: FundamentalMetric) -> SourceVersion:
    return SourceVersion(
        source_record_id=metric.series_id,
        source_version_id=metric.metric_id,
        value=metric.raw_value or "",
        available_at=envelope.retrieved_at,
        retrieved_at=envelope.retrieved_at,
        published_at=envelope.market_public_at,
    )


def _q2_eps_envelope() -> DisclosureEnvelope:
    return DisclosureEnvelope(
        envelope_id="ENV_7203_2Q2025",
        provider_code="72030",
        internal_code=_ENTITY,
        disclosure_number="D_2Q2025",
        document_type="2QFinancialStatements_Consolidated_IFRS",
        disclosure_date=date(2024, 11, 6),
        disclosure_time="13:55",
        market_public_at=datetime(2024, 11, 6, 13, 55, tzinfo=_JST),
        retrieved_at=datetime(2026, 8, 16, tzinfo=UTC),
        current_period_type=PeriodType.Q2,
        current_period_end=date(2024, 9, 30),
    )


def _q2_eps_metric(envelope: DisclosureEnvelope) -> FundamentalMetric:
    value = Decimal("142.15")
    return FundamentalMetric(
        metric_id=f"{envelope.envelope_id}_eps",
        envelope_id=envelope.envelope_id,
        series_id=f"{_ENTITY}|eps|CURRENT_FISCAL_YEAR|2Q|CONSOLIDATED|IFRS",
        metric_type="eps",
        raw_value=str(value),
        value=value,
        value_availability=ValueAvailability.PRESENT,
        actual_or_forecast=ActualOrForecast.ACTUAL,
        fiscal_year_target=FiscalYearTarget.CURRENT_FISCAL_YEAR,
        period_type=PeriodType.Q2,
        period_basis=PeriodBasis.CUMULATIVE,
        consolidation_scope=ConsolidationScope.CONSOLIDATED,
        accounting_standard="IFRS",
        source_field="EPS",
    )


# --- 1. Price Selector -----------------------------------------------------------------


def test_price_selector_rejects_same_day_close_before_session_close_and_selects_prior_day() -> None:
    """2024-11-15 15:00 JSTでは、その日の大引け(15:30 JST)がまだ確定していないため
    2024-11-15 Closeを拒否し、2024-11-14 Close(前日15:30 JST大引け、確定済み)を選ぶ。"""
    bar = select_latest_close_bar(_raw_bars(), as_of=_AS_OF)
    assert bar is not None
    assert bar.session_date == date(2024, 11, 14)
    assert bar.close == 2666.0


def test_price_selector_returns_none_when_no_bar_is_confirmed_yet() -> None:
    bar = select_latest_close_bar([_bar(date(2024, 11, 15), 2704.0)], as_of=_AS_OF)
    assert bar is None


# --- 2/3. Fundamental Denominator(A系統、FY実績・連結のみ) -----------------------------


def test_fy_actual_eps_is_selected_via_market_public_at_as_of() -> None:
    envelope = _fy_eps_envelope()
    metric = _fy_eps_metric(envelope)
    from lib.fundamentals.normalize import build_revision_histories

    histories = build_revision_histories([envelope], [metric])
    selected = fundamentals_as_of(histories, _AS_OF, availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT)
    version = selected[metric.series_id]
    assert version is not None
    assert version.value == "365.94"


def test_2q_cumulative_eps_is_rejected_as_denominator() -> None:
    """metric_typeがepsでもperiod_type=2Qの累計値は分母として拒否する(fail closed)。"""
    envelope = _q2_eps_envelope()
    metric = _q2_eps_metric(envelope)
    version = _fy_eps_version(envelope, metric)
    with pytest.raises(ValueError, match="FY実績・連結"):
        build_latest_reported_fy_per(
            entity_code=_ENTITY,
            as_of=_AS_OF,
            raw_bars=_raw_bars(),
            corporate_action_events=[],
            eps_version=version,
            eps_metric=metric,
            eps_envelope=envelope,
        )


# --- 4. Future disclosureを拒否 ----------------------------------------------------------


def test_future_disclosure_is_rejected() -> None:
    envelope = _fy_eps_envelope()
    metric = _fy_eps_metric(envelope)
    future_published_at = _AS_OF.astimezone(_JST).replace(year=2025)
    future_envelope = DisclosureEnvelope(
        envelope_id=envelope.envelope_id,
        provider_code=envelope.provider_code,
        internal_code=envelope.internal_code,
        document_type=envelope.document_type,
        market_public_at=future_published_at,
        retrieved_at=envelope.retrieved_at,
        current_period_type=envelope.current_period_type,
        current_period_end=envelope.current_period_end,
    )
    version = _fy_eps_version(future_envelope, metric)
    with pytest.raises(LookAheadBiasError):
        build_latest_reported_fy_per(
            entity_code=_ENTITY,
            as_of=_AS_OF,
            raw_bars=_raw_bars(),
            corporate_action_events=[],
            eps_version=version,
            eps_metric=metric,
            eps_envelope=future_envelope,
        )


# --- 5. published_at UNKNOWNを拒否 --------------------------------------------------------


def test_unknown_published_at_is_rejected() -> None:
    envelope = _fy_eps_envelope()
    metric = _fy_eps_metric(envelope)
    unknown_version = SourceVersion(
        source_record_id=metric.series_id,
        source_version_id=metric.metric_id,
        value=metric.raw_value or "",
        available_at=envelope.retrieved_at,
        retrieved_at=envelope.retrieved_at,
        published_at=None,
    )
    with pytest.raises(ValueError, match="UNKNOWN"):
        build_latest_reported_fy_per(
            entity_code=_ENTITY,
            as_of=_AS_OF,
            raw_bars=_raw_bars(),
            corporate_action_events=[],
            eps_version=unknown_version,
            eps_metric=metric,
            eps_envelope=envelope,
        )


# --- 6/7. Corporate Action Guard ---------------------------------------------------------


def test_corporate_action_in_window_fails_closed() -> None:
    envelope = _fy_eps_envelope()
    metric = _fy_eps_metric(envelope)
    version = _fy_eps_version(envelope, metric)
    action = CorporateAction(
        code=_ENTITY, action_type=CorporateActionType.ADJUSTMENT_EVENT, effective_date=date(2024, 9, 2), raw_adj_factor=0.5
    )
    record = build_latest_reported_fy_per(
        entity_code=_ENTITY,
        as_of=_AS_OF,
        raw_bars=_raw_bars(),
        corporate_action_events=[action],
        eps_version=version,
        eps_metric=metric,
        eps_envelope=envelope,
    )
    assert record is None


def test_no_corporate_action_allows_calculation() -> None:
    envelope = _fy_eps_envelope()
    metric = _fy_eps_metric(envelope)
    version = _fy_eps_version(envelope, metric)
    record = build_latest_reported_fy_per(
        entity_code=_ENTITY,
        as_of=_AS_OF,
        raw_bars=_raw_bars(),
        corporate_action_events=[],
        eps_version=version,
        eps_metric=metric,
        eps_envelope=envelope,
    )
    assert record is not None
    assert record.corporate_action_basis_status == CorporateActionBasisStatus.CONFIRMED_NO_ACTION
    assert record.price_value == Decimal("2666")
    assert record.eps_value == Decimal("365.94")
    assert record.multiple == Decimal("2666") / Decimal("365.94")
    assert record.price_date == date(2024, 11, 14)
    assert record.fiscal_period_end == _FY_END
    assert record.consolidation_scope == "CONSOLIDATED"
    assert record.accounting_standard == "IFRS"


# --- 8. Price/EPS entity mismatch拒否 -----------------------------------------------------


def test_price_eps_entity_mismatch_is_rejected() -> None:
    envelope = _fy_eps_envelope()
    metric = _fy_eps_metric(envelope)
    version = _fy_eps_version(envelope, metric)
    mismatched_bars = [_bar(date(2024, 11, 14), 2666.0)]
    object.__setattr__(mismatched_bars[0], "code", "9999")
    with pytest.raises(ValueError, match="一致しません"):
        build_latest_reported_fy_per(
            entity_code=_ENTITY,
            as_of=_AS_OF,
            raw_bars=mismatched_bars,
            corporate_action_events=[],
            eps_version=version,
            eps_metric=metric,
            eps_envelope=envelope,
        )


# --- 8b. Non-Positive EPS Hardening(Stage 3.10、D0084 Codex Audit Finding) --------------


def test_zero_eps_returns_none_not_zero_division_error() -> None:
    """旧実装はEPS=0を無条件除算していたためZeroDivisionErrorになっていた。
    Hardening後はRecordを生成しない(None、fail closed)。"""
    envelope = _fy_eps_envelope()
    metric = _fy_eps_metric(envelope, value=Decimal("0"))
    version = _fy_eps_version(envelope, metric)
    record = build_latest_reported_fy_per(
        entity_code=_ENTITY,
        as_of=_AS_OF,
        raw_bars=_raw_bars(),
        corporate_action_events=[],
        eps_version=version,
        eps_metric=metric,
        eps_envelope=envelope,
    )
    assert record is None


def test_negative_eps_returns_none_not_negative_multiple() -> None:
    """旧実装は負のEPSでもそのままNegative PERを通常のValuation Multiple FACTと
    して生成していた。Hardening後はRecordを生成しない(None)。"""
    envelope = _fy_eps_envelope()
    metric = _fy_eps_metric(envelope, value=Decimal("-50.00"))
    version = _fy_eps_version(envelope, metric)
    record = build_latest_reported_fy_per(
        entity_code=_ENTITY,
        as_of=_AS_OF,
        raw_bars=_raw_bars(),
        corporate_action_events=[],
        eps_version=version,
        eps_metric=metric,
        eps_envelope=envelope,
    )
    assert record is None


def test_positive_eps_path_unchanged_after_hardening() -> None:
    """Hardening後もPositive EPS経路のBehaviorは完全に維持される(7203実データ
    相当の365.94、multiple ≈ 7.2853)。"""
    envelope = _fy_eps_envelope()
    metric = _fy_eps_metric(envelope)
    version = _fy_eps_version(envelope, metric)
    record = build_latest_reported_fy_per(
        entity_code=_ENTITY,
        as_of=_AS_OF,
        raw_bars=_raw_bars(),
        corporate_action_events=[],
        eps_version=version,
        eps_metric=metric,
        eps_envelope=envelope,
    )
    assert record is not None
    assert record.multiple == Decimal("2666") / Decimal("365.94")


# --- 8c. 追加Defense-in-Depth(Stage 3.10、D0084 Codex Audit Finding 6) -------------------


def test_metric_id_version_source_version_id_mismatch_is_rejected() -> None:
    envelope = _fy_eps_envelope()
    metric = _fy_eps_metric(envelope)
    version = SourceVersion(
        source_record_id=metric.series_id,
        source_version_id="MISMATCHED_VERSION_ID",
        value=metric.raw_value or "",
        available_at=envelope.retrieved_at,
        retrieved_at=envelope.retrieved_at,
        published_at=envelope.market_public_at,
    )
    with pytest.raises(ValueError, match="metric_id"):
        build_latest_reported_fy_per(
            entity_code=_ENTITY,
            as_of=_AS_OF,
            raw_bars=_raw_bars(),
            corporate_action_events=[],
            eps_version=version,
            eps_metric=metric,
            eps_envelope=envelope,
        )


def test_version_source_record_id_series_id_mismatch_is_rejected() -> None:
    envelope = _fy_eps_envelope()
    metric = _fy_eps_metric(envelope)
    version = SourceVersion(
        source_record_id="MISMATCHED_SERIES_ID",
        source_version_id=metric.metric_id,
        value=metric.raw_value or "",
        available_at=envelope.retrieved_at,
        retrieved_at=envelope.retrieved_at,
        published_at=envelope.market_public_at,
    )
    with pytest.raises(ValueError, match="source_record_id"):
        build_latest_reported_fy_per(
            entity_code=_ENTITY,
            as_of=_AS_OF,
            raw_bars=_raw_bars(),
            corporate_action_events=[],
            eps_version=version,
            eps_metric=metric,
            eps_envelope=envelope,
        )


def test_version_value_metric_value_mismatch_is_rejected() -> None:
    envelope = _fy_eps_envelope()
    metric = _fy_eps_metric(envelope)
    version = SourceVersion(
        source_record_id=metric.series_id,
        source_version_id=metric.metric_id,
        value="999.99",  # metric.value(365.94)と食い違う
        available_at=envelope.retrieved_at,
        retrieved_at=envelope.retrieved_at,
        published_at=envelope.market_public_at,
    )
    with pytest.raises(ValueError, match="一致しません"):
        build_latest_reported_fy_per(
            entity_code=_ENTITY,
            as_of=_AS_OF,
            raw_bars=_raw_bars(),
            corporate_action_events=[],
            eps_version=version,
            eps_metric=metric,
            eps_envelope=envelope,
        )


# --- 9/10. Evidence ------------------------------------------------------------------------

_FORBIDDEN_WORDS = (
    "Cheap",
    "Expensive",
    "Undervalued",
    "Overvalued",
    "Attractive",
    "Bullish",
    "Bearish",
    "BUY",
    "SELL",
    "target price",
    "割安",
    "割高",
)


def _build_record():
    envelope = _fy_eps_envelope()
    metric = _fy_eps_metric(envelope)
    version = _fy_eps_version(envelope, metric)
    record = build_latest_reported_fy_per(
        entity_code=_ENTITY,
        as_of=_AS_OF,
        raw_bars=_raw_bars(),
        corporate_action_events=[],
        eps_version=version,
        eps_metric=metric,
        eps_envelope=envelope,
    )
    assert record is not None
    return record, version


def test_valuation_evidence_has_derived_layer_and_valuation_capability() -> None:
    record, _version = _build_record()
    evidence = latest_reported_fy_per_to_evidence(
        record,
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        originating_source="JQUANTS_SOURCE_DATA",
        delivery_provider="JQUANTS",
    )
    assert evidence.layer == DataLayer.DERIVED
    assert evidence.capability == DataCapability.VALUATION
    assert evidence.source.available_at == max(record.price_available_at, record.published_at)


def test_valuation_evidence_content_has_no_interpretation_words() -> None:
    record, _version = _build_record()
    evidence = latest_reported_fy_per_to_evidence(
        record,
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        originating_source="JQUANTS_SOURCE_DATA",
        delivery_provider="JQUANTS",
    )
    lowered = evidence.content.lower()
    for word in _FORBIDDEN_WORDS:
        assert word.lower() not in lowered, f"禁止語 {word!r} がEvidence content に含まれています: {evidence.content!r}"
    assert "7.2853" in evidence.content or str(record.multiple) in evidence.content


# --- 11. Provenance(Price parent + EPS parent、multi-parentはall()で確認) ------------------


def test_valuation_evidence_traces_to_both_price_and_eps_parents(tmp_path: Path) -> None:
    record, version = _build_record()
    evidence = latest_reported_fy_per_to_evidence(
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
            link_id="L_EPS",
            from_type="fundamental_source_version",
            from_id=version.source_version_id,
            to_type="valuation_evidence",
            to_id=evidence.evidence_id,
        )
    )
    parents = [link for link in store.all() if link.to_id == evidence.evidence_id]
    assert len(parents) == 2
    assert {link.from_type for link in parents} == {"price_bar", "fundamental_source_version"}


# --- 12. ResearchArtifactがVALUATIONを受理 -------------------------------------------------


def test_research_artifact_accepts_valuation_evidence_neutral_relation() -> None:
    """Stage 3.15.3(D0092): 新規構築ArtifactはCollision-Safe Identity(v2)の
    LATEST_REPORTED_FY_PER Evidenceのみを受理する(v1は`build_research_
    artifact()`自体がfail closedで拒否する、下のTest参照)。"""
    record, _version = _build_record()
    evidence = latest_reported_fy_per_to_evidence_v2(
        record,
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        originating_source="JQUANTS_SOURCE_DATA",
        delivery_provider="JQUANTS",
    )
    artifact, packet = build_research_artifact(
        artifact_id="ART_TEST_VALUATION_1",
        entity_code=_ENTITY,
        question=ResearchQuestion(question_id="RQ_VAL_1", text="q", as_of=_AS_OF, related_codes=(_ENTITY,)),
        evidence_pool=[evidence],
        relations={evidence.evidence_id: EvidenceRelation.NEUTRAL},
        bull_case=NarrativeCase(summary="Bull Caseは主張しない"),
        base_case=NarrativeCase(summary="LATEST_REPORTED_FY_PERを観測", supporting_evidence_ids=(evidence.evidence_id,)),
        bear_case=NarrativeCase(summary="Bear Caseも主張しない"),
        data_confidence=ConfidenceLevel.LOW,
        evidence_confidence=ConfidenceLevel.MEDIUM,
        research_confidence=ConfidenceLevel.LOW,
        conclusion=ResearchConclusion.INCONCLUSIVE,
        conclusion_rationale="Valuation Evidence 1件のみ",
        data_gaps=[DataGap(topic="test", status=DataGapStatus.MISSING)],
    )
    assert evidence.evidence_id in artifact.included_evidence_ids
    assert evidence.evidence_id in packet.unknowns or evidence.evidence_id in packet.positive_evidence  # NEUTRALはunknownsへ


def test_research_artifact_rejects_v1_latest_reported_fy_per_evidence() -> None:
    """Stage 3.15.3(D0092): 新規構築ArtifactへのLATEST_REPORTED_FY_PER v1
    Evidenceの混入をfail closedで拒否する(Identity Collision Risk、D0090)。
    既に永続化済みのv1 Artifactを`ResearchArtifactRegistry`経由でReloadする
    ことはこの関数を経由しないため無関係(§21確認)。"""
    record, _version = _build_record()
    v1_evidence = latest_reported_fy_per_to_evidence(
        record,
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        originating_source="JQUANTS_SOURCE_DATA",
        delivery_provider="JQUANTS",
    )
    with pytest.raises(ValueError, match="v1 Evidence"):
        build_research_artifact(
            artifact_id="ART_TEST_VALUATION_V1_REJECT",
            entity_code=_ENTITY,
            question=ResearchQuestion(question_id="RQ_VAL_2", text="q", as_of=_AS_OF, related_codes=(_ENTITY,)),
            evidence_pool=[v1_evidence],
            relations={v1_evidence.evidence_id: EvidenceRelation.NEUTRAL},
            bull_case=NarrativeCase(summary="Bull Caseは主張しない"),
            base_case=NarrativeCase(summary="q", supporting_evidence_ids=(v1_evidence.evidence_id,)),
            bear_case=NarrativeCase(summary="Bear Caseも主張しない"),
            data_confidence=ConfidenceLevel.LOW,
            evidence_confidence=ConfidenceLevel.MEDIUM,
            research_confidence=ConfidenceLevel.LOW,
            conclusion=ResearchConclusion.INCONCLUSIVE,
            conclusion_rationale="v1 Reject Test",
        )


def test_is_latest_reported_fy_per_evidence_helpers_distinguish_v1_v2_and_other() -> None:
    """Stage 3.15.3(D0092): `is_latest_reported_fy_per_evidence()`/`is_latest_
    reported_fy_per_v2_evidence()`がv1/v2/その他(例: Forecast PER、別
    source_type)を正しく区別することを確認する(Free-form Parsingではなく
    source_type/evidence_id Prefixによる判定)。"""
    record, _version = _build_record()
    v1_evidence = latest_reported_fy_per_to_evidence(
        record,
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        originating_source="JQUANTS_SOURCE_DATA",
        delivery_provider="JQUANTS",
    )
    v2_evidence = latest_reported_fy_per_to_evidence_v2(
        record,
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        originating_source="JQUANTS_SOURCE_DATA",
        delivery_provider="JQUANTS",
    )
    assert is_latest_reported_fy_per_evidence(v1_evidence) is True
    assert is_latest_reported_fy_per_v2_evidence(v1_evidence) is False
    assert is_latest_reported_fy_per_evidence(v2_evidence) is True
    assert is_latest_reported_fy_per_v2_evidence(v2_evidence) is True

    other_evidence = EvidenceRecord(
        evidence_id="EVID_OTHER_1",
        evidence_type=EvidenceType.FACT,
        layer=DataLayer.DERIVED,
        capability=DataCapability.VALUATION,
        content="不関係のEvidence",
        source=SourceMetadata(
            source_id="OTHER_1",
            source_type="CURRENT_FY_COMPANY_FORECAST_PER",
            provider_name="test",
            source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
            primary_or_secondary=PrimaryOrSecondary.PRIMARY,
            retrieved_at=_AS_OF,
            published_at=_AS_OF,
            available_at=_AS_OF,
        ),
    )
    assert is_latest_reported_fy_per_evidence(other_evidence) is False
    assert is_latest_reported_fy_per_v2_evidence(other_evidence) is False
