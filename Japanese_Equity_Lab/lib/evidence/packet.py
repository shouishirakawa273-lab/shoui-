"""EvidencePacket: 将来Agentへ渡すEvidenceの単位(D0040)。

## Anti-Confirmation設計

DEFAULT STANCE = DISCONFIRM, NOT CONFIRM。研究所は候補銘柄・仮説・既存Knowledgeを
肯定するために情報を探索してはならない。「買える理由を探す」のではなく、
「この仮説を壊そうとした結果、それでも残るか」を評価する。

- **情報件数の多数決を禁止する**: `build_evidence_packet()`はEvidenceの個数を
  一切集計・比較しない(Positive/Negativeの割り当ては、呼び出し側が
  `EvidenceRelation`で明示的に1件ずつ判定した結果を受け取るだけであり、
  「多い方を採用する」ロジックはこのモジュールのどこにも存在しない)。
- **自動でPositive/Negativeへ昇格させない**: `EvidencePacket`はConclusion/Verdict
  フィールドを意図的に持たない。Evidence不足の場合に「SUPPORTED」等へ自動昇格する
  経路そのものが存在しない(Schemaにそのフィールドが無い)。
- **Conflicting Sourcesを自動統合しない**: 同じEvidenceが複数カテゴリへ重複して
  分類されることを`build_evidence_packet()`が拒否する(`ValueError`)。ある
  Evidenceを`negative_evidence`に置くか`positive_evidence`に置くかは呼び出し側の
  判断であり、両方に矛盾する情報がある場合は`contradictory_evidence`へ置くことで
  「どちらか一方を機械的に選ばない」ことを表現する(自動での勝敗判定はしない)。

Phase3DではLLMにPositive/Negative判定させる本格実装は不要。Schemaとfixtureでよい。
重要なのは、「何をAIに見せたか」だけでなく「何を見せなかったか」も後から
追跡可能にすること(`excluded_candidate_sources`/`missing_expected_sources`)。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime

from lib.evidence.model import EvidenceRecord, EvidenceRelation
from lib.evidence.retrieval import RetrievalPlan


@dataclass(kw_only=True, frozen=True)
class EvidencePacket:
    """将来Agentへ渡すEvidenceの単位。Conclusion/Verdictフィールドは意図的に持たない
    (Positive/Negativeへの自動昇格を構造的に禁止するため)。"""

    packet_id: str
    research_question: str
    as_of: datetime
    included_evidence_ids: tuple[str, ...] = field(default_factory=tuple)
    excluded_candidate_sources: tuple[str, ...] = field(default_factory=tuple)
    retrieval_reason: str = ""
    missing_expected_sources: tuple[str, ...] = field(default_factory=tuple)
    positive_evidence: tuple[str, ...] = field(default_factory=tuple)
    negative_evidence: tuple[str, ...] = field(default_factory=tuple)
    alternative_explanation_evidence: tuple[str, ...] = field(default_factory=tuple)
    contradictory_evidence: tuple[str, ...] = field(default_factory=tuple)
    unknowns: tuple[str, ...] = field(default_factory=tuple)
    provenance_id: str | None = None

    def __post_init__(self) -> None:
        if self.as_of.tzinfo is None:
            raise ValueError("as_of はtz-awareである必要があります")


_RELATION_TO_FIELD: dict[EvidenceRelation, str] = {
    EvidenceRelation.SUPPORTS: "positive_evidence",
    EvidenceRelation.CONTRADICTS: "negative_evidence",
    EvidenceRelation.ALTERNATIVE_EXPLANATION: "alternative_explanation_evidence",
    EvidenceRelation.NEUTRAL: "unknowns",
    EvidenceRelation.UNKNOWN: "unknowns",
}


def build_evidence_packet(
    *,
    packet_id: str,
    research_question: str,
    as_of: datetime,
    evidence_pool: Sequence[EvidenceRecord],
    relations: Mapping[str, EvidenceRelation],
    retrieval_plan: RetrievalPlan | None = None,
    conflicting_evidence_ids: Sequence[str] = (),
    excluded_candidate_sources: Sequence[str] = (),
    missing_expected_sources: Sequence[str] = (),
) -> EvidencePacket:
    """EvidenceRecordの集合と、呼び出し側が明示的に与えたRelation判定から
    EvidencePacketを組み立てる。

    **多数決ロジックは存在しない**: `relations`は呼び出し側(人間または将来Agent)が
    Evidence 1件ずつに割り当てたHypothesisとの関係であり、この関数はそれを
    そのままカテゴリへ振り分けるだけで、件数による判定・上書きは一切行わない。

    `conflicting_evidence_ids`に指定したEvidenceは、`relations`での分類に関わらず
    `contradictory_evidence`へ入れる(Conflicting Sourcesの自動統合を避けるため、
    呼び出し側が明示的に「これは対立している」と示す経路)。

    `relations`に含まれないevidence_id(=関係が未判定)は`unknowns`へ入れる
    (INSUFFICIENT_EVIDENCEを黙ってPositive/Negativeへ倒さない)。
    """
    evidence_by_id = {e.evidence_id: e for e in evidence_pool}
    unknown_relation_ids = {e.evidence_id for e in evidence_pool} - set(relations)
    for evidence_id in relations:
        if evidence_id not in evidence_by_id:
            raise ValueError(f"relationsに含まれるevidence_id={evidence_id} がevidence_poolに存在しません")

    buckets: dict[str, list[str]] = {
        "positive_evidence": [],
        "negative_evidence": [],
        "alternative_explanation_evidence": [],
        "contradictory_evidence": [],
        "unknowns": [],
    }

    conflicting_set = set(conflicting_evidence_ids)
    for evidence_id in conflicting_set:
        if evidence_id not in evidence_by_id:
            raise ValueError(f"conflicting_evidence_idsに含まれるevidence_id={evidence_id} がevidence_poolに存在しません")
        buckets["contradictory_evidence"].append(evidence_id)

    for evidence_id, relation in relations.items():
        if evidence_id in conflicting_set:
            continue  # 対立指定を優先し、Relationによる分類は行わない(二重分類の防止)
        buckets[_RELATION_TO_FIELD[relation]].append(evidence_id)

    for evidence_id in unknown_relation_ids:
        if evidence_id not in conflicting_set:
            buckets["unknowns"].append(evidence_id)

    return EvidencePacket(
        packet_id=packet_id,
        research_question=research_question,
        as_of=as_of,
        included_evidence_ids=tuple(evidence_by_id),
        excluded_candidate_sources=tuple(excluded_candidate_sources),
        retrieval_reason=(
            f"RetrievalPlan(included={[c.value for c in retrieval_plan.included_capabilities]})"
            if retrieval_plan is not None
            else ""
        ),
        missing_expected_sources=tuple(missing_expected_sources),
        positive_evidence=tuple(buckets["positive_evidence"]),
        negative_evidence=tuple(buckets["negative_evidence"]),
        alternative_explanation_evidence=tuple(buckets["alternative_explanation_evidence"]),
        contradictory_evidence=tuple(buckets["contradictory_evidence"]),
        unknowns=tuple(buckets["unknowns"]),
    )
