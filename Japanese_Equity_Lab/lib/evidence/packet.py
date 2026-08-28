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
class EvidenceRelationAssignment:
    """1件のEvidenceへ明示的に割り当てられたExact Relation(Stage 3.15.2、D0091)。

    既存のBucket表現(`positive_evidence`/`negative_evidence`/...)は
    `NEUTRAL`と`UNKNOWN`の両方を`unknowns`へ収束させてしまい、さらに
    `relations`Mappingへそもそも指定が無かったEvidence(Omitted/Unassigned)
    とも区別できない。この型は「呼び出し側が実際に何を指定したか」を
    Bucket変換前の状態でLosslessに保持する——`relation_assignments`に
    Entryが存在しないEvidence(Omitted)と、Entryが存在し値が`UNKNOWN`の
    Evidence(Explicit Unknown)は明確に別の状態として区別される。

    **`conflicting_evidence_ids`との関係(Critical Fix、D0091)**: Conflict
    Overrideは`relation`とは直交する別軸であり、Callerが`relations`へ
    明示的に指定したExact Relation(`SUPPORTS`等)を消去しない。Conflict
    Override対象のEvidenceは、`relation`はCallerが指定した元の値のまま、
    最終的なBucketだけが`contradictory_evidence`へ上書きされる(`lib.
    evidence.packet.build_evidence_packet()`のDocstring参照)。`relations`
    に一切指定が無く、かつ`conflicting_evidence_ids`にのみ存在する
    Evidenceは、Assignment自体を持たない(Relationとして指定された事実が
    無いため)。
    """

    evidence_id: str
    relation: EvidenceRelation


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
    relation_assignments: tuple[EvidenceRelationAssignment, ...] = field(default_factory=tuple)
    """Exact Relation Assignment(Stage 3.15.2、D0091)。空Tuple(既定)は
    「Assignment自体をTrackしていないLegacy Packet」を表し、Consistency
    Guardを一切実行しない(既存呼び出し・既存Testとの後方互換)。1件でも
    含む場合、以下を全てfail closedで検証する: (1) `evidence_id`重複無し、
    (2) 各`evidence_id`が`included_evidence_ids`に存在、(3) 各Assignmentの
    `relation`に対応するBucket(`_RELATION_TO_FIELD`)へその`evidence_id`が
    実際に含まれている、(4) Assignmentが無い`included_evidence_id`は
    `unknowns`以外のBucketに存在しない(Omitted Evidenceが勝手にPositive/
    Negative等へ紛れ込むことを防ぐ)。"""

    def __post_init__(self) -> None:
        if self.as_of.tzinfo is None:
            raise ValueError("as_of はtz-awareである必要があります")
        if not self.relation_assignments:
            return

        assigned_ids = [a.evidence_id for a in self.relation_assignments]
        if len(set(assigned_ids)) != len(assigned_ids):
            duplicates = sorted({eid for eid in assigned_ids if assigned_ids.count(eid) > 1})
            raise ValueError(f"packet_id={self.packet_id}: relation_assignmentsに重複したevidence_idがあります: {duplicates}")

        included = set(self.included_evidence_ids)
        # `contradictory_evidence`は`_RELATION_TO_FIELD`のいかなる値からも到達しない
        # (`conflicting_evidence_ids`専用の別経路、`EvidenceRelation`とは直交する概念)。
        # したがってこのBucketへのMembershipはAssignment Omission Checkの対象外とする
        # (Conflicting Sourcesの側は元々Relation Assignmentを持たない場合がある、要件v1 §4)。
        non_unknown_buckets: dict[str, tuple[str, ...]] = {
            "positive_evidence": self.positive_evidence,
            "negative_evidence": self.negative_evidence,
            "alternative_explanation_evidence": self.alternative_explanation_evidence,
        }
        for assignment in self.relation_assignments:
            if assignment.evidence_id not in included:
                raise ValueError(
                    f"packet_id={self.packet_id}: relation_assignmentsのevidence_id="
                    f"{assignment.evidence_id}がincluded_evidence_idsに存在しません"
                )
            if assignment.evidence_id in self.contradictory_evidence:
                # Conflict Override(要件v1 §2): Callerが元々指定したExact Relationは
                # そのままAssignmentへ保持するが、最終的なBucketはConflict Overrideにより
                # `contradictory_evidence`が優先されるため、Relationの自然なBucket
                # (`_RELATION_TO_FIELD`)との一致は要求しない。
                continue
            expected_bucket = _RELATION_TO_FIELD[assignment.relation]
            if assignment.evidence_id not in getattr(self, expected_bucket):
                raise ValueError(
                    f"packet_id={self.packet_id}: evidence_id={assignment.evidence_id}のrelation="
                    f"{assignment.relation.value}は{expected_bucket}に対応しますが、実際にはそこに"
                    "存在しません(Assignment/Bucket不整合、fail closed)"
                )

        unassigned = included - set(assigned_ids)
        for evidence_id in unassigned:
            for bucket_name, bucket_values in non_unknown_buckets.items():
                if evidence_id in bucket_values:
                    raise ValueError(
                        f"packet_id={self.packet_id}: evidence_id={evidence_id}はrelation_assignments"
                        f"に対応するEntryが無いにもかかわらず{bucket_name}に存在します"
                        "(Omitted EvidenceがUnknowns以外のBucketへ紛れ込んでいます、fail closed)"
                    )


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

    **Exact Relation Assignment(Stage 3.15.2、D0091、Critical Fix済み)**:
    戻り値の`EvidencePacket.relation_assignments`には、`relations`で明示
    指定された全Evidenceがその値(`NEUTRAL`/`UNKNOWN`含む)をそのまま
    記録する——**`conflicting_evidence_ids`による上書きの有無に関わらない**
    (Conflict Overrideは`relation`とは直交する別軸であり、Callerが指定した
    Exact Relationを消去しない)。Conflict Override対象のEvidenceは、
    Assignment上のRelationはCallerが指定した元の値のまま、最終的な
    Bucketだけが`contradictory_evidence`へ上書きされる。`relations`に
    一切指定が無く、かつ`conflicting_evidence_ids`にのみ存在するEvidenceは
    Assignment自体を持たない(Relationとして指定された事実自体が無いため)。
    `relations`にもConflictにも一切現れない(Omitted)Evidenceも同様に
    Assignmentを持たない——Explicit `UNKNOWN`とOmittedを同一視しない。
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
    assignments: list[EvidenceRelationAssignment] = []

    conflicting_set = set(conflicting_evidence_ids)
    for evidence_id in conflicting_set:
        if evidence_id not in evidence_by_id:
            raise ValueError(f"conflicting_evidence_idsに含まれるevidence_id={evidence_id} がevidence_poolに存在しません")
        buckets["contradictory_evidence"].append(evidence_id)
        # Bucketのみ Conflict Override により contradictory_evidence へ強制する。
        # relations側にCallerが指定したExact RelationはAssignmentとして消さない
        # (Critical Fix、D0091 §CRITICAL FIX): 下のrelations.items()ループで
        # Conflict対象かどうかに関わらずAssignmentへ記録する。

    for evidence_id, relation in relations.items():
        # Exact Relation AssignmentはConflict Overrideの有無に関わらず、Callerが
        # 指定した値をそのまま保持する(Losslessness、D0091 Critical Fix)。
        assignments.append(EvidenceRelationAssignment(evidence_id=evidence_id, relation=relation))
        if evidence_id in conflicting_set:
            continue  # Bucketの割り当てだけは対立指定を優先する(二重分類の防止)
        buckets[_RELATION_TO_FIELD[relation]].append(evidence_id)

    for evidence_id in unknown_relation_ids:
        if evidence_id not in conflicting_set:
            buckets["unknowns"].append(evidence_id)
            # Omitted(relations・conflicting_evidence_idsいずれにも一切指定が無い):
            # Assignmentは追加しない(Explicit UNKNOWNとの区別、要件v1 §4/§5)。
        # else: relationsに指定が無くconflicting_evidence_idsにのみ存在する場合、
        # 既にbuckets["contradictory_evidence"]へ追加済み・Assignmentは追加しない
        # (要件v1 §4: relation assignment = none, contradictory_evidence = yes)。

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
        relation_assignments=tuple(assignments),
    )
