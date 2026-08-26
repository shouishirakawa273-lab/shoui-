"""Stage 3 v1(Research Engine): ResearchArtifactの原則ベースTest。

**Research != Decision**を最優先で検証する(BUY/SELL/target price/position
sizing相当のFieldが構造的に存在しないこと)。次いでEvidence捏造防止・
Future Leakage防止・Confidence 3軸分離・INSUFFICIENT_EVIDENCE abstention・
D0057(Positioning Evidence Path)を安全に回避する新規Consumer設計を確認する。
"""

from __future__ import annotations

from dataclasses import fields
from datetime import UTC, date, datetime

import pytest
from lib.disclosures.evidence import disclosure_document_to_evidence
from lib.disclosures.model import DisclosureDocument, DocumentKind
from lib.errors import LookAheadBiasError
from lib.evidence.model import DataLayer, EvidenceRecord, EvidenceRelation, EvidenceType, ValueAvailability
from lib.evidence.research_artifact import (
    ConfidenceLevel,
    DataGap,
    DataGapStatus,
    NarrativeCase,
    ResearchArtifact,
    ResearchConclusion,
    build_research_artifact,
    price_derived_record_to_evidence,
)
from lib.evidence.retrieval import ResearchQuestion
from lib.fundamentals.evidence import disclosure_metric_to_evidence
from lib.fundamentals.model import (
    ActualOrForecast,
    ConsolidationScope,
    DisclosureEnvelope,
    FiscalYearTarget,
    FundamentalMetric,
    PeriodBasis,
    PeriodType,
)
from lib.positioning.evidence import positioning_record_to_evidence
from lib.positioning.model import Frequency, PositioningRecord
from lib.sources.catalog import DataCapability, PrimaryOrSecondary, SourceAuthorityClass, SourceMetadata

_ENTITY = "7203"


def _question(as_of: datetime) -> ResearchQuestion:
    return ResearchQuestion(question_id="RQ_TEST_0001", text="7203の業績は堅調か", as_of=as_of, related_codes=(_ENTITY,))


def _fundamental_evidence(*, retrieved_at: datetime, suffix: str = "1") -> EvidenceRecord:
    envelope = DisclosureEnvelope(
        envelope_id=f"ENV_TEST_{suffix}",
        provider_code="72030",
        internal_code=_ENTITY,
        disclosure_number="D1",
        document_type="FYFinancialStatements_Consolidated_IFRS",
        disclosure_date=retrieved_at.date(),
        disclosure_time=retrieved_at.strftime("%H:%M"),
        market_public_at=retrieved_at,
        retrieved_at=retrieved_at,
    )
    metric = FundamentalMetric(
        metric_id=f"MET_TEST_{suffix}",
        envelope_id=envelope.envelope_id,
        series_id="7203|operating_profit_current_year_forecast|CURRENT_FISCAL_YEAR|FY|CONSOLIDATED|IFRS",
        metric_type="operating_profit_current_year_forecast",
        raw_value="120",
        value=None,
        value_availability=ValueAvailability.PRESENT,
        actual_or_forecast=ActualOrForecast.COMPANY_FORECAST,
        fiscal_year_target=FiscalYearTarget.CURRENT_FISCAL_YEAR,
        period_type=PeriodType.FY,
        period_basis=PeriodBasis.CUMULATIVE,
        consolidation_scope=ConsolidationScope.CONSOLIDATED,
        accounting_standard="IFRS",
        source_field="FOP",
    )
    return disclosure_metric_to_evidence(envelope, metric)


def _disclosure_evidence(*, retrieved_at: datetime) -> EvidenceRecord:
    document = DisclosureDocument(
        internal_document_id="DOC_TEST_1",
        source_document_id="D1",
        entity_id=_ENTITY,
        title="FY決算短信",
        document_kind=DocumentKind.FINANCIAL_RESULTS,
        retrieved_at=retrieved_at,
        market_public_at=retrieved_at,
    )
    return disclosure_document_to_evidence(document, source_authority_class=SourceAuthorityClass.COMPANY_PRIMARY)


def _positioning_record(*, observation_end: date, retrieved_at: datetime) -> PositioningRecord:
    return PositioningRecord(
        record_id=f"POS_TURNOVER_{_ENTITY}_{observation_end.isoformat()}",
        series_id=f"{_ENTITY}:TURNOVER_VALUE:PRICE_DERIVED:{Frequency.DAILY.value}",
        entity_code=_ENTITY,
        metric_type="TURNOVER_VALUE",
        source_id="PRICE_DERIVED",
        frequency=Frequency.DAILY,
        observation_start=observation_end,
        observation_end=observation_end,
        raw_value="12345678900",
        value=None,
        unit="JPY",
        value_availability=ValueAvailability.PRESENT,
        retrieved_at=retrieved_at,
        normalizer_version="POSITIONING_PRICE_DERIVED_NORMALIZER_V1",
    )


def _bull() -> NarrativeCase:
    return NarrativeCase(summary="Bull", supporting_evidence_ids=())


def _base() -> NarrativeCase:
    return NarrativeCase(summary="Base", supporting_evidence_ids=())


def _bear() -> NarrativeCase:
    return NarrativeCase(summary="Bear", supporting_evidence_ids=())


# --- Research != Decision(最優先) ------------------------------------------------------


def test_research_artifact_carries_no_buy_sell_field() -> None:
    """Phase5 VAL-026(`test_val026_split_run_result_carries_no_buy_sell_field`)と
    同じパターン: BUY/SELL/target_price/position_size相当のFieldが構造的に
    存在しないことを直接確認する。"""
    field_names = {f.name for f in fields(ResearchArtifact)}
    forbidden = {
        "buy",
        "sell",
        "action",
        "recommendation",
        "signal_to_act_on",
        "target_price",
        "position_size",
        "position_sizing",
        "order",
        "quantity",
    }
    assert field_names.isdisjoint(forbidden)


# --- Evidence捏造防止(Bull/Base/Bear、要件v1-3) -----------------------------------------


def test_narrative_case_cannot_reference_evidence_outside_packet() -> None:
    as_of = datetime(2026, 6, 1, tzinfo=UTC)
    evidence = _fundamental_evidence(retrieved_at=datetime(2026, 5, 1, tzinfo=UTC))
    with pytest.raises(ValueError, match="捏造防止"):
        build_research_artifact(
            artifact_id="ART_TEST_1",
            entity_code=_ENTITY,
            question=_question(as_of),
            evidence_pool=[evidence],
            relations={evidence.evidence_id: EvidenceRelation.SUPPORTS},
            bull_case=NarrativeCase(summary="Bull", supporting_evidence_ids=("EVID_DOES_NOT_EXIST",)),
            base_case=_base(),
            bear_case=_bear(),
            data_confidence=ConfidenceLevel.MEDIUM,
            evidence_confidence=ConfidenceLevel.MEDIUM,
            research_confidence=ConfidenceLevel.MEDIUM,
            conclusion=ResearchConclusion.PARTIALLY_SUPPORTED,
            conclusion_rationale="test",
        )


# --- Future Evidence Leakage防止(Safety要件) --------------------------------------------


def test_build_research_artifact_rejects_future_evidence_referenced_in_relations() -> None:
    """as_of後にretrieved_at(=available_at)を持つEvidenceがrelationsで参照された場合、
    Silent Dropせず LookAheadBiasError にする。"""
    as_of = datetime(2026, 6, 1, tzinfo=UTC)
    future_evidence = _fundamental_evidence(retrieved_at=datetime(2026, 6, 2, tzinfo=UTC))
    with pytest.raises(LookAheadBiasError):
        build_research_artifact(
            artifact_id="ART_TEST_2",
            entity_code=_ENTITY,
            question=_question(as_of),
            evidence_pool=[future_evidence],
            relations={future_evidence.evidence_id: EvidenceRelation.SUPPORTS},
            bull_case=_bull(),
            base_case=_base(),
            bear_case=_bear(),
            data_confidence=ConfidenceLevel.MEDIUM,
            evidence_confidence=ConfidenceLevel.MEDIUM,
            research_confidence=ConfidenceLevel.MEDIUM,
            conclusion=ResearchConclusion.PARTIALLY_SUPPORTED,
            conclusion_rationale="test",
        )


def test_build_research_artifact_excludes_future_evidence_from_packet_silently_otherwise() -> None:
    """relations/Narrativeで参照されない限り、as_of後のEvidenceはPacketから
    静かに除外されるだけでよい(全件を強制的にエラーにはしない、既存
    filter_usable_at()の挙動を尊重する)。"""
    as_of = datetime(2026, 6, 1, tzinfo=UTC)
    past_evidence = _fundamental_evidence(retrieved_at=datetime(2026, 5, 1, tzinfo=UTC), suffix="PAST")
    future_evidence = _fundamental_evidence(retrieved_at=datetime(2026, 6, 2, tzinfo=UTC), suffix="FUTURE")
    artifact, packet = build_research_artifact(
        artifact_id="ART_TEST_3",
        entity_code=_ENTITY,
        question=_question(as_of),
        evidence_pool=[past_evidence, future_evidence],
        relations={past_evidence.evidence_id: EvidenceRelation.SUPPORTS},
        bull_case=NarrativeCase(summary="Bull", supporting_evidence_ids=(past_evidence.evidence_id,)),
        base_case=_base(),
        bear_case=_bear(),
        data_confidence=ConfidenceLevel.MEDIUM,
        evidence_confidence=ConfidenceLevel.MEDIUM,
        research_confidence=ConfidenceLevel.MEDIUM,
        conclusion=ResearchConclusion.PARTIALLY_SUPPORTED,
        conclusion_rationale="test",
    )
    assert past_evidence.evidence_id in artifact.included_evidence_ids
    assert future_evidence.evidence_id not in artifact.included_evidence_ids
    assert past_evidence.evidence_id in packet.positive_evidence


# --- Allowed Default Data(fail closed、Safety要件) --------------------------------------


def test_build_research_artifact_rejects_disallowed_capability_by_default() -> None:
    """Macro/News/Consensus等はStage 3 v1の既定許可Capability外であり、
    evidence_poolに混入した場合fail closedでValueErrorにする。"""
    as_of = datetime(2026, 6, 1, tzinfo=UTC)
    disallowed_evidence = EvidenceRecord(
        evidence_id="EVID_NEWS_1",
        evidence_type=EvidenceType.INTERPRETATION,
        layer=DataLayer.NORMALIZED,
        capability=DataCapability.NEWS,
        content="市場予想を上回るとの報道",
        source=SourceMetadata(
            source_id="NEWS_1",
            source_type="NEWS_ARTICLE",
            provider_name="TEST_NEWS",
            source_authority_class=SourceAuthorityClass.VERIFIED_SECONDARY,
            primary_or_secondary=PrimaryOrSecondary.SECONDARY,
            retrieved_at=datetime(2026, 5, 1, tzinfo=UTC),
            published_at=datetime(2026, 5, 1, tzinfo=UTC),
            available_at=datetime(2026, 5, 1, tzinfo=UTC),
        ),
    )
    with pytest.raises(ValueError, match="fail closed"):
        build_research_artifact(
            artifact_id="ART_TEST_4",
            entity_code=_ENTITY,
            question=_question(as_of),
            evidence_pool=[disallowed_evidence],
            relations={},
            bull_case=_bull(),
            base_case=_base(),
            bear_case=_bear(),
            data_confidence=ConfidenceLevel.MEDIUM,
            evidence_confidence=ConfidenceLevel.MEDIUM,
            research_confidence=ConfidenceLevel.MEDIUM,
            conclusion=ResearchConclusion.INCONCLUSIVE,
            conclusion_rationale="test",
        )


# --- Confidence 3軸分離(要件v1-5) -------------------------------------------------------


def test_confidence_axes_are_independently_settable() -> None:
    """Data/Evidence/Research Confidenceが互いに独立していることを直接確認する
    (1つが低くても他が高いままでよい、暗黙の連動が無いことの構造確認)。"""
    as_of = datetime(2026, 6, 1, tzinfo=UTC)
    evidence = _fundamental_evidence(retrieved_at=datetime(2026, 5, 1, tzinfo=UTC))
    artifact, _packet = build_research_artifact(
        artifact_id="ART_TEST_5",
        entity_code=_ENTITY,
        question=_question(as_of),
        evidence_pool=[evidence],
        relations={evidence.evidence_id: EvidenceRelation.SUPPORTS},
        bull_case=NarrativeCase(summary="Bull", supporting_evidence_ids=(evidence.evidence_id,)),
        base_case=_base(),
        bear_case=_bear(),
        data_confidence=ConfidenceLevel.LOW,
        evidence_confidence=ConfidenceLevel.HIGH,
        research_confidence=ConfidenceLevel.MEDIUM,
        conclusion=ResearchConclusion.PARTIALLY_SUPPORTED,
        conclusion_rationale="test",
    )
    assert artifact.data_confidence == ConfidenceLevel.LOW
    assert artifact.evidence_confidence == ConfidenceLevel.HIGH
    assert artifact.research_confidence == ConfidenceLevel.MEDIUM


# --- INSUFFICIENT_EVIDENCE abstention(要件v1-8) -----------------------------------------


def test_zero_evidence_forces_insufficient_evidence_conclusion() -> None:
    """Evidenceが0件の状態で他のConclusionを主張することを構造的に禁止する。"""
    with pytest.raises(ValueError, match="INSUFFICIENT_EVIDENCE"):
        ResearchArtifact(
            artifact_id="ART_TEST_6",
            entity_code=_ENTITY,
            as_of=datetime(2026, 6, 1, tzinfo=UTC),
            research_question_id="RQ_TEST_0001",
            evidence_packet_id="PKT_TEST_6",
            bull_case=_bull(),
            base_case=_base(),
            bear_case=_bear(),
            data_confidence=ConfidenceLevel.MEDIUM,
            evidence_confidence=ConfidenceLevel.MEDIUM,
            research_confidence=ConfidenceLevel.MEDIUM,
            conclusion=ResearchConclusion.SUPPORTED,
            conclusion_rationale="test",
        )


def test_insufficient_evidence_conclusion_requires_insufficient_research_confidence() -> None:
    """conclusion=INSUFFICIENT_EVIDENCEなのにresearch_confidence=HIGHという
    矛盾した状態を禁止する。"""
    with pytest.raises(ValueError, match="矛盾"):
        ResearchArtifact(
            artifact_id="ART_TEST_7",
            entity_code=_ENTITY,
            as_of=datetime(2026, 6, 1, tzinfo=UTC),
            research_question_id="RQ_TEST_0001",
            evidence_packet_id="PKT_TEST_7",
            bull_case=_bull(),
            base_case=_base(),
            bear_case=_bear(),
            data_confidence=ConfidenceLevel.MEDIUM,
            evidence_confidence=ConfidenceLevel.MEDIUM,
            research_confidence=ConfidenceLevel.HIGH,
            conclusion=ResearchConclusion.INSUFFICIENT_EVIDENCE,
            conclusion_rationale="test",
        )


def test_zero_evidence_with_insufficient_evidence_conclusion_is_allowed() -> None:
    """正しい形のAbstentionは許可される(0件Evidence + INSUFFICIENT_EVIDENCE +
    INSUFFICIENT Research Confidence)。"""
    artifact = ResearchArtifact(
        artifact_id="ART_TEST_8",
        entity_code=_ENTITY,
        as_of=datetime(2026, 6, 1, tzinfo=UTC),
        research_question_id="RQ_TEST_0001",
        evidence_packet_id="PKT_TEST_8",
        bull_case=_bull(),
        base_case=_base(),
        bear_case=_bear(),
        data_confidence=ConfidenceLevel.INSUFFICIENT,
        evidence_confidence=ConfidenceLevel.INSUFFICIENT,
        research_confidence=ConfidenceLevel.INSUFFICIENT,
        conclusion=ResearchConclusion.INSUFFICIENT_EVIDENCE,
        conclusion_rationale="Evidence Poolが空のため判断を保留する",
    )
    assert artifact.conclusion == ResearchConclusion.INSUFFICIENT_EVIDENCE


# --- missing source != negative evidence(Safety要件) ------------------------------------


def test_data_gap_is_structurally_separate_from_bear_case() -> None:
    """DataGap(取得できなかったTopic)がbear_caseのEvidenceとして紛れ込まないことを
    構造で確認する(別Fieldであり、bear_case.supporting_evidence_idsには
    DataGap由来のIDを一切含められない)。"""
    as_of = datetime(2026, 6, 1, tzinfo=UTC)
    evidence = _fundamental_evidence(retrieved_at=datetime(2026, 5, 1, tzinfo=UTC))
    gap = DataGap(topic="Consensus予想", status=DataGapStatus.MISSING, note="v1では取得しない")
    artifact, _packet = build_research_artifact(
        artifact_id="ART_TEST_9",
        entity_code=_ENTITY,
        question=_question(as_of),
        evidence_pool=[evidence],
        relations={evidence.evidence_id: EvidenceRelation.NEUTRAL},
        bull_case=_bull(),
        base_case=_base(),
        bear_case=_bear(),
        data_confidence=ConfidenceLevel.MEDIUM,
        evidence_confidence=ConfidenceLevel.MEDIUM,
        research_confidence=ConfidenceLevel.MEDIUM,
        conclusion=ResearchConclusion.INCONCLUSIVE,
        conclusion_rationale="test",
        data_gaps=[gap],
    )
    assert artifact.data_gaps == (gap,)
    assert not set(g.topic for g in artifact.data_gaps) & set(artifact.bear_case.supporting_evidence_ids)


# --- CONTRADICTS/ALTERNATIVE_EXPLANATIONがsynthesisを生き残る(Safety要件) ---------------


def test_contradictory_and_alternative_evidence_survive_in_packet() -> None:
    as_of = datetime(2026, 6, 1, tzinfo=UTC)
    supporting = _fundamental_evidence(retrieved_at=datetime(2026, 5, 1, tzinfo=UTC))
    contradicting = _disclosure_evidence(retrieved_at=datetime(2026, 5, 2, tzinfo=UTC))
    _artifact, packet = build_research_artifact(
        artifact_id="ART_TEST_10",
        entity_code=_ENTITY,
        question=_question(as_of),
        evidence_pool=[supporting, contradicting],
        relations={
            supporting.evidence_id: EvidenceRelation.SUPPORTS,
            contradicting.evidence_id: EvidenceRelation.CONTRADICTS,
        },
        bull_case=NarrativeCase(summary="Bull", supporting_evidence_ids=(supporting.evidence_id,)),
        base_case=_base(),
        bear_case=NarrativeCase(summary="Bear", supporting_evidence_ids=(contradicting.evidence_id,)),
        data_confidence=ConfidenceLevel.MEDIUM,
        evidence_confidence=ConfidenceLevel.MEDIUM,
        research_confidence=ConfidenceLevel.MEDIUM,
        conclusion=ResearchConclusion.PARTIALLY_SUPPORTED,
        conclusion_rationale="test",
    )
    assert contradicting.evidence_id in packet.negative_evidence
    assert supporting.evidence_id in packet.positive_evidence


# --- Versioned Artifact(要件v1-1) --------------------------------------------------------


def test_artifact_version_lineage_via_supersedes_artifact_id() -> None:
    as_of = datetime(2026, 6, 1, tzinfo=UTC)
    evidence = _fundamental_evidence(retrieved_at=datetime(2026, 5, 1, tzinfo=UTC))
    v1, _packet1 = build_research_artifact(
        artifact_id="ART_TEST_11_V1",
        entity_code=_ENTITY,
        question=_question(as_of),
        evidence_pool=[evidence],
        relations={evidence.evidence_id: EvidenceRelation.SUPPORTS},
        bull_case=NarrativeCase(summary="Bull", supporting_evidence_ids=(evidence.evidence_id,)),
        base_case=_base(),
        bear_case=_bear(),
        data_confidence=ConfidenceLevel.MEDIUM,
        evidence_confidence=ConfidenceLevel.MEDIUM,
        research_confidence=ConfidenceLevel.MEDIUM,
        conclusion=ResearchConclusion.PARTIALLY_SUPPORTED,
        conclusion_rationale="v1",
    )
    v2, _packet2 = build_research_artifact(
        artifact_id="ART_TEST_11_V2",
        entity_code=_ENTITY,
        question=_question(as_of),
        evidence_pool=[evidence],
        relations={evidence.evidence_id: EvidenceRelation.SUPPORTS},
        bull_case=NarrativeCase(summary="Bull(改訂)", supporting_evidence_ids=(evidence.evidence_id,)),
        base_case=_base(),
        bear_case=_bear(),
        data_confidence=ConfidenceLevel.MEDIUM,
        evidence_confidence=ConfidenceLevel.MEDIUM,
        research_confidence=ConfidenceLevel.MEDIUM,
        conclusion=ResearchConclusion.PARTIALLY_SUPPORTED,
        conclusion_rationale="v2",
        artifact_version=2,
        supersedes_artifact_id=v1.artifact_id,
    )
    assert v2.supersedes_artifact_id == v1.artifact_id
    assert v2.artifact_version == 2
    assert v1.artifact_id != v2.artifact_id  # 上書きせず新IDを発行する


# --- D0057: Positioning Evidence Pathを安全に回避する(Safety要件) -----------------------


def test_price_derived_evidence_uses_session_close_not_retrieved_at_when_retrieved_before_close() -> None:
    """D0057 §5 Failure Exampleの直接再現: retrieved_atがSession Closeより早い
    (Intraday取得)場合でも、price_derived_record_to_evidence()のavailable_atは
    Session Close(resolve_available_at())であり、retrieved_atそのものではない
    (`positioning_record_to_evidence()`が持つLeak Riskをこの新規Consumerが
    回避していることの直接確認)。"""
    from lib.market_calendar import session_close_at

    observation_end = date(2026, 6, 1)
    # 東証は9:00-15:30 JST(UTC+9)。session_close_at(2026-06-01)は15:30 JST=06:30 UTC。
    # 03:00 UTC=12:00 JSTは取引時間中(Session Close前)。
    intraday_retrieved_at = datetime(2026, 6, 1, 3, 0, tzinfo=UTC)
    record = _positioning_record(observation_end=observation_end, retrieved_at=intraday_retrieved_at)

    evidence = price_derived_record_to_evidence(
        record,
        layer=DataLayer.DERIVED,
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        originating_source="JQUANTS_SOURCE_DATA",
        delivery_provider="JQUANTS",
    )

    expected_available_at = session_close_at(observation_end)
    assert evidence.source.available_at == expected_available_at
    assert evidence.source.available_at != intraday_retrieved_at
    assert evidence.source.available_at > intraday_retrieved_at  # Session Closeの方が保守的(遅い)


def test_price_derived_evidence_is_pit_excluded_before_session_close_decision_at() -> None:
    """上記の安全なavailable_atにより、Session Close前のdecision_atでは
    `is_usable_at()`がFalseになる(旧`positioning_record_to_evidence()`なら
    Trueになってしまっていたはずのケース、D0057 §5)。"""
    observation_end = date(2026, 6, 1)
    intraday_retrieved_at = datetime(2026, 6, 1, 3, 0, tzinfo=UTC)  # 12:00 JST(取引時間中)
    record = _positioning_record(observation_end=observation_end, retrieved_at=intraday_retrieved_at)
    evidence = price_derived_record_to_evidence(
        record,
        layer=DataLayer.DERIVED,
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        originating_source="JQUANTS_SOURCE_DATA",
        delivery_provider="JQUANTS",
    )
    decision_at_intraday = datetime(2026, 6, 1, 5, 0, tzinfo=UTC)  # 14:00 JST、まだSession Close(15:30 JST)前
    assert evidence.is_usable_at(decision_at_intraday) is False


def test_price_derived_evidence_included_in_research_artifact() -> None:
    """price_derived_record_to_evidence()の出力がbuild_research_artifact()へ
    そのまま渡せる(DataCapability.POSITIONINGとして既定許可Capabilityに含まれる)
    ことをEnd-to-Endで確認する。"""
    observation_end = date(2026, 5, 29)
    record = _positioning_record(observation_end=observation_end, retrieved_at=datetime(2026, 5, 29, 16, 0, tzinfo=UTC))
    evidence = price_derived_record_to_evidence(
        record,
        layer=DataLayer.DERIVED,
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        originating_source="JQUANTS_SOURCE_DATA",
        delivery_provider="JQUANTS",
    )
    as_of = datetime(2026, 6, 1, tzinfo=UTC)
    artifact, packet = build_research_artifact(
        artifact_id="ART_TEST_12",
        entity_code=_ENTITY,
        question=_question(as_of),
        evidence_pool=[evidence],
        relations={evidence.evidence_id: EvidenceRelation.NEUTRAL},
        bull_case=_bull(),
        base_case=NarrativeCase(summary="Base", supporting_evidence_ids=(evidence.evidence_id,)),
        bear_case=_bear(),
        data_confidence=ConfidenceLevel.MEDIUM,
        evidence_confidence=ConfidenceLevel.MEDIUM,
        research_confidence=ConfidenceLevel.MEDIUM,
        conclusion=ResearchConclusion.INCONCLUSIVE,
        conclusion_rationale="test",
    )
    assert evidence.evidence_id in artifact.included_evidence_ids
    assert evidence.evidence_id in packet.unknowns


# --- pit-auditor HIGH Finding回帰: Capability Tagだけでは安全な構築元を区別できない -------


def test_build_research_artifact_rejects_positioning_evidence_from_unsafe_converter() -> None:
    """pit-auditorのHIGH Finding再現・回帰Test: 同じPrice-derived
    `PositioningRecord`でも、既存の(D0057でLeak Riskが確認済みの)
    `positioning_record_to_evidence()`(retrieved_at基準)経由で構築した
    Evidenceは、`capability=DataCapability.POSITIONING`というTagだけでは
    `DEFAULT_ALLOWED_CAPABILITIES`を通過してしまう。`build_research_
    artifact()`が`_uses_session_close_availability()`による追加検証で
    これをfail closedに拒否することを確認する。"""
    observation_end = date(2026, 6, 1)
    intraday_retrieved_at = datetime(2026, 6, 1, 3, 0, tzinfo=UTC)  # 12:00 JST(取引時間中)
    record = _positioning_record(observation_end=observation_end, retrieved_at=intraday_retrieved_at)

    # 安全でない既存Converter(D0057 Leak Riskあり)を意図的に使う。
    unsafe_evidence = positioning_record_to_evidence(
        record,
        layer=DataLayer.DERIVED,
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        originating_source="JQUANTS_SOURCE_DATA",
        delivery_provider="JQUANTS",
    )
    assert unsafe_evidence.capability == DataCapability.POSITIONING  # allowed_capabilitiesだけでは弾けない前提の確認
    assert unsafe_evidence.source.available_at == intraday_retrieved_at  # retrieved_atがそのままavailable_at(Leak Risk)

    as_of = datetime(2026, 6, 1, 5, 0, tzinfo=UTC)  # 14:00 JST、Session Close(15:30 JST)前
    with pytest.raises(ValueError, match="Session Close基準"):
        build_research_artifact(
            artifact_id="ART_TEST_UNSAFE_1",
            entity_code=_ENTITY,
            question=_question(as_of),
            evidence_pool=[unsafe_evidence],
            relations={unsafe_evidence.evidence_id: EvidenceRelation.NEUTRAL},
            bull_case=_bull(),
            base_case=_base(),
            bear_case=_bear(),
            data_confidence=ConfidenceLevel.MEDIUM,
            evidence_confidence=ConfidenceLevel.MEDIUM,
            research_confidence=ConfidenceLevel.MEDIUM,
            conclusion=ResearchConclusion.INCONCLUSIVE,
            conclusion_rationale="test",
        )


def test_build_research_artifact_rejects_duplicate_evidence_id() -> None:
    """pit-auditorのLOW Finding回帰: evidence_pool内でevidence_idが重複する場合、
    Future Leakage判定・Evidence捏造判定が別のEvidenceを指してしまう可能性が
    あるため拒否する。"""
    as_of = datetime(2026, 6, 1, tzinfo=UTC)
    evidence_a = _fundamental_evidence(retrieved_at=datetime(2026, 5, 1, tzinfo=UTC), suffix="DUP")
    evidence_b = _fundamental_evidence(retrieved_at=datetime(2026, 5, 2, tzinfo=UTC), suffix="DUP")
    assert evidence_a.evidence_id == evidence_b.evidence_id  # 同じsuffixのため意図的に重複させる

    with pytest.raises(ValueError, match="重複"):
        build_research_artifact(
            artifact_id="ART_TEST_DUP_1",
            entity_code=_ENTITY,
            question=_question(as_of),
            evidence_pool=[evidence_a, evidence_b],
            relations={},
            bull_case=_bull(),
            base_case=_base(),
            bear_case=_bear(),
            data_confidence=ConfidenceLevel.MEDIUM,
            evidence_confidence=ConfidenceLevel.MEDIUM,
            research_confidence=ConfidenceLevel.MEDIUM,
            conclusion=ResearchConclusion.INCONCLUSIVE,
            conclusion_rationale="test",
        )


# --- Acceptance: 1 company + as_of -> ResearchArtifact生成可能(End-to-End) ---------------


def test_single_company_as_of_produces_research_artifact_with_all_evidence_traceable() -> None:
    """Acceptance Criteria: 1企業(7203) + 明示的as_ofについて、Fundamentals/
    Disclosures/Price-derived Positioningを混ぜたEvidence PoolからArtifactが
    生成でき、Bull/Base/Bearの全material claimがEvidenceへ遡れることを確認する。"""
    as_of = datetime(2026, 6, 1, tzinfo=UTC)
    fundamental = _fundamental_evidence(retrieved_at=datetime(2026, 5, 1, tzinfo=UTC))
    disclosure = _disclosure_evidence(retrieved_at=datetime(2026, 5, 5, tzinfo=UTC))
    positioning_record = _positioning_record(
        observation_end=date(2026, 5, 29), retrieved_at=datetime(2026, 5, 29, 16, 0, tzinfo=UTC)
    )
    positioning = price_derived_record_to_evidence(
        positioning_record,
        layer=DataLayer.DERIVED,
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        originating_source="JQUANTS_SOURCE_DATA",
        delivery_provider="JQUANTS",
    )

    artifact, packet = build_research_artifact(
        artifact_id="ART_ACCEPTANCE_1",
        entity_code=_ENTITY,
        question=_question(as_of),
        evidence_pool=[fundamental, disclosure, positioning],
        relations={
            fundamental.evidence_id: EvidenceRelation.SUPPORTS,
            disclosure.evidence_id: EvidenceRelation.NEUTRAL,
            positioning.evidence_id: EvidenceRelation.NEUTRAL,
        },
        bull_case=NarrativeCase(summary="業績予想は堅調", supporting_evidence_ids=(fundamental.evidence_id,)),
        base_case=NarrativeCase(
            summary="開示・出来高ともに特段の異常なし", supporting_evidence_ids=(disclosure.evidence_id, positioning.evidence_id)
        ),
        bear_case=_bear(),
        data_confidence=ConfidenceLevel.MEDIUM,
        evidence_confidence=ConfidenceLevel.MEDIUM,
        research_confidence=ConfidenceLevel.MEDIUM,
        conclusion=ResearchConclusion.PARTIALLY_SUPPORTED,
        conclusion_rationale="Fundamentals支持1件、対立なし、Evidence件数は限定的",
    )

    all_referenced = (
        set(artifact.bull_case.supporting_evidence_ids)
        | set(artifact.base_case.supporting_evidence_ids)
        | set(artifact.bear_case.supporting_evidence_ids)
    )
    assert all_referenced <= set(artifact.included_evidence_ids)
    assert artifact.entity_code == _ENTITY
    assert artifact.as_of == as_of
    assert artifact.evidence_packet_id == packet.packet_id
