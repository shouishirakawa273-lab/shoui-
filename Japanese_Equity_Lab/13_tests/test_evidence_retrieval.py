"""Phase3D(D0040): Relevant Retrieval Interfaceのテスト。

「Dataが多いほど全部AIに渡す」設計を禁止する。ResearchQuestionが要求していない
Capabilityは、Defaultでは渡さない(不要なData、例: Copper price)。
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from lib.evidence.model import DataLayer, EvidenceRecord, EvidenceType
from lib.evidence.retrieval import ResearchQuestion, plan_retrieval, retrieve_evidence
from lib.sources.catalog import DataCapability, PrimaryOrSecondary, SourceAuthorityClass, SourceMetadata


def _source(available_at: datetime) -> SourceMetadata:
    return SourceMetadata(
        source_id="s1",
        source_type="TDNET",
        provider_name="TDnet",
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        primary_or_secondary=PrimaryOrSecondary.PRIMARY,
        retrieved_at=available_at,
        published_at=available_at,
        available_at=available_at,
    )


def _record(evidence_id: str, capability: DataCapability, *, available_at: datetime) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id=evidence_id,
        evidence_type=EvidenceType.FACT,
        layer=DataLayer.NORMALIZED,
        capability=capability,
        content="内容",
        source=_source(available_at),
    )


_AS_OF = datetime(2024, 6, 1, tzinfo=UTC)


# --- Test 11: RetrieverがResearch Questionに不要なCapabilityをDefaultで渡さない ---


def test_plan_retrieval_excludes_unrequested_capabilities() -> None:
    """例: BIPROGYのQ1決算後下落の分析にCopper price(GLOBAL_MARKET)は含めない。"""
    question = ResearchQuestion(question_id="Q1", text="BIPROGYのQ1決算後下落は構造的減速か一時的な期ずれか", as_of=_AS_OF)
    requested = frozenset({DataCapability.DISCLOSURE, DataCapability.FUNDAMENTAL, DataCapability.MARKET_PRICE})
    plan = plan_retrieval(question, requested_capabilities=requested)
    assert set(plan.included_capabilities) == requested
    assert DataCapability.GLOBAL_MARKET not in plan.included_capabilities
    assert DataCapability.GLOBAL_MARKET in plan.excluded_capabilities


def test_retrieve_evidence_excludes_evidence_outside_requested_capabilities() -> None:
    question = ResearchQuestion(question_id="Q1", text="q", as_of=_AS_OF)
    plan = plan_retrieval(question, requested_capabilities=frozenset({DataCapability.DISCLOSURE}))
    pool = [
        _record("E_DISCLOSURE", DataCapability.DISCLOSURE, available_at=datetime(2024, 1, 1, tzinfo=UTC)),
        _record("E_COPPER", DataCapability.GLOBAL_MARKET, available_at=datetime(2024, 1, 1, tzinfo=UTC)),
    ]
    result = retrieve_evidence(plan, pool, decision_at=_AS_OF)
    assert {e.evidence_id for e in result} == {"E_DISCLOSURE"}


def test_retrieve_evidence_still_enforces_pit_within_requested_capability() -> None:
    """Capabilityが一致していても、decision_at時点で未入手のEvidenceは含めない。"""
    question = ResearchQuestion(question_id="Q1", text="q", as_of=_AS_OF)
    plan = plan_retrieval(question, requested_capabilities=frozenset({DataCapability.DISCLOSURE}))
    pool = [
        _record("E_PAST", DataCapability.DISCLOSURE, available_at=datetime(2024, 1, 1, tzinfo=UTC)),
        _record("E_FUTURE", DataCapability.DISCLOSURE, available_at=datetime(2024, 12, 1, tzinfo=UTC)),
    ]
    result = retrieve_evidence(plan, pool, decision_at=_AS_OF)
    assert {e.evidence_id for e in result} == {"E_PAST"}


# --- Test 12: included/excludedの理由を監査可能 ---


def test_retrieval_plan_records_reason_for_every_capability_decision() -> None:
    question = ResearchQuestion(question_id="Q1", text="q", as_of=_AS_OF)
    plan = plan_retrieval(question, requested_capabilities=frozenset({DataCapability.MARKET_PRICE}))
    assert len(plan.decisions) == len(DataCapability)
    for decision in plan.decisions:
        assert decision.reason  # 空文字列の理由は許容しない(暗黙の除外をしない)
    included_decisions = [d for d in plan.decisions if d.capability == DataCapability.MARKET_PRICE]
    excluded_decisions = [d for d in plan.decisions if d.capability == DataCapability.NEWS]
    assert included_decisions[0].included is True
    assert excluded_decisions[0].included is False
    assert included_decisions[0].reason != excluded_decisions[0].reason


def test_research_question_requires_tz_aware_as_of() -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        ResearchQuestion(question_id="Q1", text="q", as_of=datetime(2024, 1, 1))
