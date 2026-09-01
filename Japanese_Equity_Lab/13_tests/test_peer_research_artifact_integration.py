"""Peer Context EvidenceのResearchArtifact統合(Stage 3.17、D0095、要件
v1 §13)。

Peer Evidenceを追加してもConfidence(Data/Evidence/Research)・
Conclusionを自動変更しないことを明示Testで固定する。`DataCapability.
PEER_COMPARISON`は`lib.evidence.research_artifact.DEFAULT_ALLOWED_
CAPABILITIES`に含まれないため、呼び出し側が`allowed_capabilities`
Parameter(既存Escape Hatch、Stage 3.15設計)を明示的に拡張して渡す
——`DEFAULT_ALLOWED_CAPABILITIES`自体(Stage 3.15 Frozen production
file)は変更しない。
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from lib.evidence.model import EvidenceRelation
from lib.evidence.research_artifact import (
    DEFAULT_ALLOWED_CAPABILITIES,
    ConfidenceLevel,
    NarrativeCase,
    ResearchConclusion,
    build_research_artifact,
)
from lib.evidence.retrieval import ResearchQuestion
from lib.market_calendar import session_close_at
from lib.peer.builder import (
    build_peer_aggregate_context,
    build_peer_comparison_record,
    latest_reported_fy_per_record_to_peer_observation,
)
from lib.peer.evidence import peer_valuation_context_to_evidence
from lib.peer.model import AcceptedPeer, PeerMetricType
from lib.registry.evidence_registry import EvidenceRegistry
from lib.sources.catalog import DataCapability, SourceAuthorityClass
from lib.valuation.evidence import latest_reported_fy_per_to_evidence_v2
from lib.valuation.model import CorporateActionBasisStatus, LatestReportedFyPerRecord

_JST = ZoneInfo("Asia/Tokyo")
_AS_OF = datetime(2024, 11, 15, 15, 0, tzinfo=_JST)
_AUTH = SourceAuthorityClass.PRIMARY_OFFICIAL
_ORIG = "JQUANTS_SOURCE_DATA"
_DELIV = "JQUANTS"
_ALLOWED = DEFAULT_ALLOWED_CAPABILITIES | frozenset({DataCapability.PEER_COMPARISON})


def _accepted_peer(entity_code: str) -> AcceptedPeer:
    return AcceptedPeer(entity_code=entity_code, classification_system="TSE_SECTOR_33", classification_code="3700", as_of=_AS_OF)


def _per_record(entity_code: str, *, multiple: Decimal, source_version_id: str) -> LatestReportedFyPerRecord:
    price_date = date(2024, 11, 14)
    eps_value = Decimal("100")
    price_value = multiple * eps_value
    return LatestReportedFyPerRecord(
        entity_code=entity_code,
        as_of=_AS_OF,
        price_date=price_date,
        price_value=price_value,
        price_available_at=session_close_at(price_date),
        denominator_type="FY_ACTUAL_EPS_CONSOLIDATED",
        eps_value=eps_value,
        fiscal_period_end=date(2024, 3, 31),
        published_at=datetime(2024, 5, 8, 13, 55, tzinfo=_JST),
        source_version_id=source_version_id,
        consolidation_scope="CONSOLIDATED",
        accounting_standard="IFRS",
        calculation_expression=f"price_close={price_value} / fy_actual_eps={eps_value}",
        multiple=multiple,
        corporate_action_basis_status=CorporateActionBasisStatus.CONFIRMED_NO_ACTION,
    )


def _build_context_evidence(tmp_path: Path):
    registry = EvidenceRegistry(tmp_path / "reg.jsonl")
    target_record = _per_record("7203", multiple=Decimal("10"), source_version_id="SV_7203")
    target_evidence = latest_reported_fy_per_to_evidence_v2(
        target_record, source_authority_class=_AUTH, originating_source=_ORIG, delivery_provider=_DELIV
    )
    registry.register(target_evidence)
    target_obs = latest_reported_fy_per_record_to_peer_observation(target_record, evidence=target_evidence, as_of=_AS_OF)

    comparisons = []
    for code, multiple in (("2001", Decimal("7")), ("2002", Decimal("8")), ("2003", Decimal("9"))):
        rec = _per_record(code, multiple=multiple, source_version_id=f"SV_{code}")
        ev = latest_reported_fy_per_to_evidence_v2(
            rec, source_authority_class=_AUTH, originating_source=_ORIG, delivery_provider=_DELIV
        )
        registry.register(ev)
        obs = latest_reported_fy_per_record_to_peer_observation(rec, evidence=ev, as_of=_AS_OF)
        comparisons.append(
            build_peer_comparison_record(
                target_entity_code="7203",
                accepted_peer=_accepted_peer(code),
                metric_type=PeerMetricType.LATEST_REPORTED_FY_PER,
                comparison_as_of=_AS_OF,
                target_observation=target_obs,
                peer_observation=obs,
            )
        )
    context = build_peer_aggregate_context(
        target_entity_code="7203",
        metric_type=PeerMetricType.LATEST_REPORTED_FY_PER,
        as_of=_AS_OF,
        target_observation=target_obs,
        comparison_records=comparisons,
    )
    assert context is not None
    context_evidence = peer_valuation_context_to_evidence(
        context, source_authority_class=_AUTH, originating_source=_ORIG, delivery_provider=_DELIV
    )
    return target_evidence, context_evidence


def test_peer_context_evidence_included_confidence_unchanged(tmp_path: Path) -> None:
    _target_evidence, context_evidence = _build_context_evidence(tmp_path)

    artifact, packet = build_research_artifact(
        artifact_id="ART_D0095_TEST_7203_PEER_V1",
        entity_code="7203",
        question=ResearchQuestion(
            question_id="RQ_D0095_TEST_0001",
            text="Peer Comparison Foundation Integration Test",
            as_of=_AS_OF,
            related_codes=("7203",),
        ),
        evidence_pool=[context_evidence],
        relations={context_evidence.evidence_id: EvidenceRelation.NEUTRAL},
        bull_case=NarrativeCase(summary="方向性のあるBull Caseは主張しない。"),
        base_case=NarrativeCase(
            summary="Peer Context Evidenceを含む観測Evidence群。",
            supporting_evidence_ids=(context_evidence.evidence_id,),
        ),
        bear_case=NarrativeCase(summary="方向性のあるBear Caseも主張しない。"),
        data_confidence=ConfidenceLevel.LOW,
        evidence_confidence=ConfidenceLevel.MEDIUM,
        research_confidence=ConfidenceLevel.LOW,
        conclusion=ResearchConclusion.INCONCLUSIVE,
        conclusion_rationale="D0095 Peer Comparison Foundation Integration Test。",
        allowed_capabilities=_ALLOWED,
    )

    assert context_evidence.evidence_id in artifact.included_evidence_ids
    # Peer Evidence追加だけでは、明示的に渡した既存Confidence/Conclusionを変更しない。
    assert artifact.data_confidence == ConfidenceLevel.LOW
    assert artifact.evidence_confidence == ConfidenceLevel.MEDIUM
    assert artifact.research_confidence == ConfidenceLevel.LOW
    assert artifact.conclusion == ResearchConclusion.INCONCLUSIVE

    # Default Relation = NEUTRAL -> unknowns bucket (自動SUPPORTS/CONTRADICTS付与なし)。
    assert context_evidence.evidence_id in packet.unknowns
    assert context_evidence.evidence_id not in packet.positive_evidence
    assert context_evidence.evidence_id not in packet.negative_evidence


def test_peer_evidence_rejected_without_capability_allowlist(tmp_path: Path) -> None:
    """`DataCapability.PEER_COMPARISON`が`allowed_capabilities`へ明示的に
    含まれない場合(既定`DEFAULT_ALLOWED_CAPABILITIES`のまま)、Stage 3.15の
    既存Guardがfail closedで拒否することを確認する(Production Semantics
    無変更の直接証拠)。"""
    _target_evidence, context_evidence = _build_context_evidence(tmp_path)

    with pytest.raises(ValueError):
        build_research_artifact(
            artifact_id="ART_D0095_TEST_7203_PEER_REJECTED_V1",
            entity_code="7203",
            question=ResearchQuestion(
                question_id="RQ_D0095_TEST_0002",
                text="Peer Comparison Foundation Integration Test (no allowlist)",
                as_of=_AS_OF,
                related_codes=("7203",),
            ),
            evidence_pool=[context_evidence],
            relations={context_evidence.evidence_id: EvidenceRelation.NEUTRAL},
            bull_case=NarrativeCase(summary="N/A"),
            base_case=NarrativeCase(summary="N/A", supporting_evidence_ids=(context_evidence.evidence_id,)),
            bear_case=NarrativeCase(summary="N/A"),
            data_confidence=ConfidenceLevel.LOW,
            evidence_confidence=ConfidenceLevel.MEDIUM,
            research_confidence=ConfidenceLevel.LOW,
            conclusion=ResearchConclusion.INCONCLUSIVE,
            conclusion_rationale="N/A",
        )
