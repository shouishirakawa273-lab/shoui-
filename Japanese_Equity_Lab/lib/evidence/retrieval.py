"""Relevant Retrieval: 「Dataが多いほど全部AIに渡す」設計を禁止する(D0040)。

ResearchQuestionを受け、必要なDataだけを取得するRetrieval Interfaceを用意する。
例えば「BIPROGYのQ1決算後下落は構造的減速か、一時的な期ずれか」という問いには
Earnings/Guidance/Prior Earnings/TDnet Disclosure/IR Material/Pre-Post Earnings
Price/Volume/関連Japan IT/DX News/Consensus等が必要だが、明確に関連しない
Data(例: Copper price)はDefaultでは渡さない。

**Retrieverの選択自体も後から監査できるようにする**: `plan_retrieval()`は採用・除外
それぞれについて理由(`RetrievalDecision.reason`)を必ず記録する(暗黙の除外をしない)。

Phase3DではLLMによるRetrieval Selection(「関連しそうなCapabilityをAIが選ぶ」)は
実装しない。呼び出し側が明示的に指定した`requested_capabilities`に基づいて
機械的に判定するのみ(将来Agentがここへ差し込む余地を残す設計)。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime

from lib.evidence.model import EvidenceRecord, filter_usable_at
from lib.sources.catalog import DataCapability


@dataclass(kw_only=True, frozen=True)
class ResearchQuestion:
    question_id: str
    text: str
    as_of: datetime
    related_codes: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.as_of.tzinfo is None:
            raise ValueError("as_of はtz-awareである必要があります")


@dataclass(frozen=True)
class RetrievalDecision:
    capability: DataCapability
    included: bool
    reason: str


@dataclass(frozen=True)
class RetrievalPlan:
    research_question_id: str
    as_of: datetime
    decisions: tuple[RetrievalDecision, ...]

    @property
    def included_capabilities(self) -> tuple[DataCapability, ...]:
        return tuple(d.capability for d in self.decisions if d.included)

    @property
    def excluded_capabilities(self) -> tuple[DataCapability, ...]:
        return tuple(d.capability for d in self.decisions if not d.included)


def plan_retrieval(
    question: ResearchQuestion,
    *,
    requested_capabilities: frozenset[DataCapability],
    exclusion_reason: str = "ResearchQuestionが要求していないため除外",
    inclusion_reason: str = "ResearchQuestionが明示的に要求したCapability",
) -> RetrievalPlan:
    """`DataCapability`全種について、含める/除外するを監査可能な形で判定する。

    `requested_capabilities`は呼び出し側(人間または将来のAgent)が明示的に
    指定する。ここではAIによる自動選定は行わない(D0040のScope境界)。
    """
    decisions = tuple(
        RetrievalDecision(
            capability=capability,
            included=capability in requested_capabilities,
            reason=inclusion_reason if capability in requested_capabilities else exclusion_reason,
        )
        for capability in DataCapability
    )
    return RetrievalPlan(research_question_id=question.question_id, as_of=question.as_of, decisions=decisions)


def retrieve_evidence(
    plan: RetrievalPlan,
    evidence_pool: Sequence[EvidenceRecord],
    *,
    decision_at: datetime,
) -> tuple[EvidenceRecord, ...]:
    """RetrievalPlanで採用されたCapability(`EvidenceRecord.capability`)かつ
    decision_at時点で利用可能なEvidenceのみ返す。"""
    included = set(plan.included_capabilities)
    usable = filter_usable_at(evidence_pool, decision_at)
    return tuple(e for e in usable if e.capability in included)
