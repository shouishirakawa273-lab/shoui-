"""Incremental Research Update: Deterministic Evidence Delta Engine(D0105)。

新たに受理された(D0103/D0104で構築済みの)`EvidenceRecord`集合を、
事前のResearch Evidence Snapshotと比較し、以下を機械的に報告する唯一の
公開Entrypoint`build_incremental_research_update()`を提供する:

- どのEvidenceがNEW(新規)か
- どのEvidenceがUNCHANGED(既知のまま)か
- どのEvidenceがREMOVED_OR_MISSING(以前存在したが現在見当たらない)か
- どのEvidenceがPOTENTIALLY_SUPERSEDED(既存Evidenceを置き換える可能性)か
- どの`ResearchArtifact`がReview対象か

**本Moduleは次のいずれでもない(D0105 §2 Core Principle)**:
新しいResearch Generator・Thesis Writer・Valuation Model・Scoring
System・BUY/SELL Model・期待Return Model。「Evidence集合に何が
変わったか、既存Researchのどの参照がHuman Reviewを要するか」のみに
答える——「新しいThesisは何であるべきか」には一切答えない。

## Determinism(D0105 §18、MODEL_CALL_SITES = 0)

LLM/Model呼び出しはこのModule内に一切存在しない。全てのClassificationは
既存Schemaの構造的Equality・既存の明示的Relationship Field
(`SemanticClaim.supersedes_claim_id`)・既存のLineage Resolver
(`lib.disclosures.evidence_lineage.resolve_evidence_lineage()`、
D0104、そのまま再利用・Traversal Logicを複製しない)のみで行う。
Text類似度・Embedding・LLM Matchingはいずれも使わない(D0105 §4)。
出力の全ID系列は`sorted()`でCanonical Orderへ正規化し、入力Listの
順序・重複順序には一切依存しない(D0105 §18)。

## Authoritative Evidence Identity(新しいID機構は作らない)

`EvidenceRecord.evidence_id`(D0103、`EVID_CLAIM_{claim_id}`形式)を
唯一のAuthoritative Identityとして使う。同一`evidence_id`がPrior/
Current両Snapshotに存在する場合、`EvidenceRecord`全Field(Frozen
Dataclassの構造的Equality)が完全一致していなければ
`IDENTITY_MISMATCH`でFail Closedする——「同じIDなら同じ内容のはず」
という前提(`evidence_id`はClaim内容のHashから導出される、D0103/
D0102.1)が破られた場合、Silent Trustせず即座にWhole-Call Abortする
(Section 6「Do not treat same normalized claim text as sufficient」に
対応、同一ID下でのContent DriftをこのModule独自の判断では一切解釈
しない)。

## POTENTIALLY_SUPERSEDED(D0105 §8、最も慎重な区分)

既存の明示的Relationship Fieldのみを根拠にする:
`SemanticClaim.supersedes_claim_id`(D0102.1 §13、「常にCaller明示
指定、既定None」)。これは「同じ会社」「似た文言」「反対の方向」
「より新しい日付」のいずれでもなく、Extraction/Verification時点で
Caller(Writer Agent/Orchestrator)が明示的に「このClaimは、この
claim_idのClaimを置き換える」と記録した唯一の既存Field である。
この関係が存在しない場合、D0105は一切Supersessionを推測しない
(Fail Conservative、新規Evidenceは常に独立したNEWのまま)。

タスク仕様が列挙する他の「Acceptable Basis」(同一Taxonomy要素・
同一Disclosure Lineage Family等)は、現在のRepository Schemaに
対応する明示的Relationship Fieldが存在しないため、v1では実装しない
(Heuristic Proxyで代替することを明示的に拒否する、D0105 §8
「If no explicit deterministic key exists: do not classify as
superseded」)。

`supersedes_claim_id`で関連付けられたPairは、追加でPIT Order
(`new.available_at >= old.available_at`)を検証する——違反した
Pairは`potentially_superseded_pairs`に含めず、`pit_failures`へ
記録する(Pair単位のFail Closed、Call全体のAbortではない、D0105 §13)。
Lineage Resolutionが失敗したNEW Evidenceは、Supersession Candidateとして
一切扱わない(D0105 §12「Do not silently continue as though
provenance is valid」)。

## Research Impact Mapping(既存Referenceのみ再利用)

`ResearchArtifact.included_evidence_ids`(既存Field、Bull/Base/Bearの
`supporting_evidence_ids`は既にこの部分集合であることが`ResearchArtifact.
__post_init__`で保証されている)を唯一のExplicit Referenceとして使う。
新しいReference機構・Embedding類似度によるImplicit Linkingはいずれも
作らない。NEW Evidenceが単独で既存のResearchArtifactを無条件に
REVIEW_REQUIREDにすることは一切ない(「新しいEvidenceがある → 全て
Reviewすべき」を明示的に回避する、D0105 §10)。

## ResearchArtifact Boundary(D0105 §17、本Moduleが越えない境界)

本Moduleは`ResearchArtifact`/`NarrativeCase`を一切Mutateしない
(Read-Onlyの引数としてのみ受け取る)。Bull/Base/Bear・Conclusion・
Confidenceの変更・新しい`EvidenceRelation`の割当・SUPPORTS/CONTRADICTS
判定・Thesis方向の決定・Valuation・期待Return計算・BUY/SELL生成は
いずれも行わない。Thesis-Impact Interpretation自体は将来のD0106
Thesis Break Monitorの責務であり、本Moduleはその入力となる
Deterministic Deltaのみを提供する。
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum

from lib.disclosures.candidate_extraction import SemanticClaimCandidate
from lib.disclosures.evidence_lineage import EvidenceLineageStatus, resolve_evidence_lineage
from lib.disclosures.model import DisclosureDocument
from lib.disclosures.normalization import NormalizedDisclosureDocument
from lib.disclosures.semantic_claims import SemanticClaim
from lib.evidence.model import EvidenceRecord, EvidenceType
from lib.evidence.research_artifact import ResearchArtifact


class IncrementalResearchUpdateSchemaError(ValueError):
    """本Module固有のSchema Invariant違反(呼び出し側のProgramming
    Errorに相当するもの)で送出する。「必要なLinkが見つからない」
    「参照が不整合」等の正当なDomain上のOutcomeは`EvidenceDeltaStatus`の
    Typed Outcomeで表現し、区別する(D0103/D0104と同じ方針)。"""


class EvidenceDeltaStatus(StrEnum):
    """`build_incremental_research_update()`の主要Outcome(D0105 §16)。
    `SUCCESS`以外は呼び出し側の入力が構造的に信頼できないことを示し、
    `IncrementalResearchUpdateResult`の全Delta/Impact Fieldは空になる
    (D0103/D0104と同じTyped Outcome Pattern、非SUCCESS時は中身を
    返さずReasonのみ返す)。

    `LINEAGE_FAILURE`/`PIT_MISMATCH`はEnumとしてここに定義するが、v1では
    Global Abort Triggerとして使わない——個別のLineage/PIT不整合は
    `lineage_failures`/`pit_failures`(Item単位のStructured Finding)で
    `status=SUCCESS`のまま報告する(1件のBad Itemが、無関係な残り全件の
    Deltaを無効化しないようにする設計判断、D0105 DECISIONS参照)。"""

    SUCCESS = "SUCCESS"
    MISSING_REFERENCE = "MISSING_REFERENCE"
    AMBIGUOUS_REFERENCE = "AMBIGUOUS_REFERENCE"
    LINEAGE_FAILURE = "LINEAGE_FAILURE"
    PIT_MISMATCH = "PIT_MISMATCH"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    UNSUPPORTED_INPUT = "UNSUPPORTED_INPUT"


class ResearchImpactStatus(StrEnum):
    """`ResearchNodeImpact.status`(D0105 §10)。数値Severity Scoreは
    導入しない(2値のみ)。"""

    UNAFFECTED = "UNAFFECTED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


@dataclass(kw_only=True, frozen=True)
class SupersededPair:
    """`SemanticClaim.supersedes_claim_id`(既存Field)のみを根拠とする
    明示的Supersession Candidate。PIT Order検証済み(`new.available_at
    >= old.available_at`)のPairのみがここに含まれる。"""

    new_evidence_id: str
    old_evidence_id: str
    new_claim_id: str
    old_claim_id: str


@dataclass(kw_only=True, frozen=True)
class LineageFailure:
    """NEW Evidenceの`resolve_evidence_lineage()`(D0104)結果が`SUCCESS`
    でなかった場合のItem単位Finding(Silent Trust禁止、D0105 §12)。"""

    evidence_id: str
    lineage_status: EvidenceLineageStatus
    reason: str | None


@dataclass(kw_only=True, frozen=True)
class PitFailure:
    """Supersession Candidate Pairが`new.available_at >= old.
    available_at`を満たさなかった場合のPair単位Finding(D0105 §13、
    Pair単位Fail Closed、Call全体のAbortではない)。"""

    new_evidence_id: str
    old_evidence_id: str
    reason: str


@dataclass(kw_only=True, frozen=True)
class ResearchNodeImpact:
    """1件の`ResearchArtifact`(`artifact_id`で識別)に対するImpact
    判定結果。`reasons`は人間が読むための短い説明文であり、本Module
    自身のDecision Logicではない(ResearchArtifactの`conclusion`等は
    一切変更しない、D0105 §17)。"""

    artifact_id: str
    status: ResearchImpactStatus
    reasons: tuple[str, ...] = field(default_factory=tuple)
    affected_evidence_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass(kw_only=True, frozen=True)
class IncrementalResearchUpdateResult:
    """`build_incremental_research_update()`の戻り値。`status`が
    `SUCCESS`以外の場合、Delta/Impact系の全Fieldは空Tupleである
    (D0102.3/D0102.4/D0103/D0104と同型のTyped Outcome、Exceptionを
    使わない)。全Tupleは`sorted()`によりCanonical Orderへ正規化済み
    (D0105 §18、入力順序非依存)。"""

    status: EvidenceDeltaStatus
    reason: str | None = None
    new_evidence_ids: tuple[str, ...] = field(default_factory=tuple)
    unchanged_evidence_ids: tuple[str, ...] = field(default_factory=tuple)
    removed_or_missing_evidence_ids: tuple[str, ...] = field(default_factory=tuple)
    potentially_superseded_pairs: tuple[SupersededPair, ...] = field(default_factory=tuple)
    affected_research_nodes: tuple[ResearchNodeImpact, ...] = field(default_factory=tuple)
    unassigned_new_evidence_ids: tuple[str, ...] = field(default_factory=tuple)
    lineage_failures: tuple[LineageFailure, ...] = field(default_factory=tuple)
    pit_failures: tuple[PitFailure, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.status, EvidenceDeltaStatus):
            raise IncrementalResearchUpdateSchemaError(f"status は EvidenceDeltaStatus である必要があります: {self.status!r}")
        if self.reason is not None and not isinstance(self.reason, str):
            raise IncrementalResearchUpdateSchemaError(f"reason は str または None である必要があります: {self.reason!r}")
        if self.status != EvidenceDeltaStatus.SUCCESS:
            non_empty = [
                name
                for name, value in (
                    ("new_evidence_ids", self.new_evidence_ids),
                    ("unchanged_evidence_ids", self.unchanged_evidence_ids),
                    ("removed_or_missing_evidence_ids", self.removed_or_missing_evidence_ids),
                    ("potentially_superseded_pairs", self.potentially_superseded_pairs),
                    ("affected_research_nodes", self.affected_research_nodes),
                    ("unassigned_new_evidence_ids", self.unassigned_new_evidence_ids),
                    ("lineage_failures", self.lineage_failures),
                    ("pit_failures", self.pit_failures),
                )
                if value
            ]
            if non_empty:
                raise IncrementalResearchUpdateSchemaError(
                    f"status={self.status.value} の場合、Delta/Impact系Fieldは全て空である必要があります"
                    f"(Updateが完走しなかったことを明示するため): {non_empty}"
                )


def _validate_claim_evidence_type(records: Sequence[EvidenceRecord], *, label: str) -> str | None:
    non_claim = sorted({r.evidence_id for r in records if r.evidence_type is not EvidenceType.CLAIM})
    if non_claim:
        return (
            f"{label}に EvidenceType.CLAIM 以外の EvidenceRecord が含まれています"
            "(D0105はSemanticClaim Integration Boundary[D0103]由来のEvidenceのみ対応します): "
            f"{non_claim}"
        )
    return None


def _duplicate_ids(items: Sequence[str]) -> list[str]:
    # Code Review Finding(D0105)Closure: `items.count(item)`をSet
    # Comprehension内で呼ぶとO(n^2)になる(D0104 evidence_lineage.pyの
    # 既知Performance Trade-offと同種のRisk)。`Counter`で単発O(n)に
    # する——Semanticsは変更しない。
    counts = Counter(items)
    return sorted(item for item, count in counts.items() if count > 1)


def _require_type(value: object, expected: type, *, label: str) -> None:
    if not isinstance(value, expected):
        raise IncrementalResearchUpdateSchemaError(f"{label} は {expected.__name__} である必要があります: {value!r}")


def build_incremental_research_update(
    *,
    prior_evidence_records: Sequence[EvidenceRecord],
    current_evidence_records: Sequence[EvidenceRecord],
    research_artifacts: Sequence[ResearchArtifact] = (),
    semantic_claims: Sequence[SemanticClaim] = (),
    candidates: Sequence[SemanticClaimCandidate] = (),
    normalized_documents: Sequence[NormalizedDisclosureDocument] = (),
    disclosure_documents: Sequence[DisclosureDocument] = (),
) -> IncrementalResearchUpdateResult:
    """2つのEvidence Snapshot(`prior_evidence_records`/`current_
        evidence_records`)間のDeterministic Deltaと、既存`research_
        artifacts`へのImpactを計算する唯一の公開Entrypoint(D0105)。

        呼び出し側は全ての依存(2つのSnapshot・ResearchArtifact集合・
        D0104 Lineage Resolution用の4集合)を明示的にDependency Injection
        する——隠れたGlobal Registry・隠れたDatabase・Model呼び出しは一切
        行わない(D0105 §3/§18)。

    `semantic_claims`はSupersession Lookup自体にも必要なため、`candidates`/
        `normalized_documents`/`disclosure_documents`が全て空の場合(`semantic_
        claims`のみ供給、またはいずれも未供給)はLineage Verification自体を
        Skipする(「D0104 Full Lineage Bundleを要求されていない」として扱う、
        Section 14「Prefer less architecture」——Supersession-Only Modeを
        意図的に許容する)。上記3集合のいずれかが1件以上供給された場合のみ
        NEW Evidence全件に対して`resolve_evidence_lineage()`(D0104、
        そのまま再利用)を実行し、失敗したEvidenceは`lineage_failures`へ
        記録しSupersession Candidateから除外する。

        - `prior_evidence_records`/`current_evidence_records`に
          `EvidenceType.CLAIM`以外が含まれる場合は`UNSUPPORTED_INPUT`。
        - いずれかのSnapshot内で`evidence_id`が重複する場合、`semantic_
          claims`内で`claim_id`が重複する場合、`research_artifacts`内で
          `artifact_id`が重複する場合は、いずれも`AMBIGUOUS_REFERENCE`
          (Silent Dedupeしない、D0105 §18)。
        - 同一`evidence_id`がPrior/Current両方に存在するが、`EvidenceRecord`
          の内容(構造的Equality)が一致しない場合は`IDENTITY_MISMATCH`
          (同一IDは同一内容であるという前提の違反、Section 6)。
        - いずれかの`ResearchArtifact.included_evidence_ids`が、Prior/
          Current両Snapshotのいずれにも存在しないEvidence IDを参照している
          場合は`MISSING_REFERENCE`(Section 23F)。
    """
    if not isinstance(prior_evidence_records, Sequence) or not isinstance(current_evidence_records, Sequence):
        raise IncrementalResearchUpdateSchemaError(
            "prior_evidence_records/current_evidence_records は Sequence である必要があります"
        )
    # Code Review Finding(D0105)Closure: Top-level Container型だけでなく
    # 各Elementの型もここで検証する——検証せずに`r.evidence_type`等へ
    # 直接Accessすると、不正な要素(例: dict/None)に対して生の
    # AttributeErrorが漏れてしまい、「Caller Programming Error(Exception)
    # と正当なDomain Outcome(Typed Result)を区別する」既存契約
    # (D0103/D0104と同じ方針)が破れる。
    for record in (*prior_evidence_records, *current_evidence_records):
        _require_type(record, EvidenceRecord, label="prior_evidence_records/current_evidence_recordsの各要素")
    for claim in semantic_claims:
        _require_type(claim, SemanticClaim, label="semantic_claimsの各要素")
    for candidate in candidates:
        _require_type(candidate, SemanticClaimCandidate, label="candidatesの各要素")
    for normalized_document in normalized_documents:
        _require_type(normalized_document, NormalizedDisclosureDocument, label="normalized_documentsの各要素")
    for disclosure_document in disclosure_documents:
        _require_type(disclosure_document, DisclosureDocument, label="disclosure_documentsの各要素")
    for artifact in research_artifacts:
        _require_type(artifact, ResearchArtifact, label="research_artifactsの各要素")

    type_error = _validate_claim_evidence_type(
        prior_evidence_records, label="prior_evidence_records"
    ) or _validate_claim_evidence_type(current_evidence_records, label="current_evidence_records")
    if type_error is not None:
        return IncrementalResearchUpdateResult(status=EvidenceDeltaStatus.UNSUPPORTED_INPUT, reason=type_error)

    prior_ids_raw = [r.evidence_id for r in prior_evidence_records]
    current_ids_raw = [r.evidence_id for r in current_evidence_records]
    claim_ids_raw = [c.claim_id for c in semantic_claims]
    artifact_ids_raw = [a.artifact_id for a in research_artifacts]

    duplicate_findings: list[str] = []
    if dup := _duplicate_ids(prior_ids_raw):
        duplicate_findings.append(f"prior_evidence_records内でevidence_idが重複しています: {dup}")
    if dup := _duplicate_ids(current_ids_raw):
        duplicate_findings.append(f"current_evidence_records内でevidence_idが重複しています: {dup}")
    if dup := _duplicate_ids(claim_ids_raw):
        duplicate_findings.append(f"semantic_claims内でclaim_idが重複しています: {dup}")
    if dup := _duplicate_ids(artifact_ids_raw):
        duplicate_findings.append(f"research_artifacts内でartifact_idが重複しています: {dup}")
    if duplicate_findings:
        return IncrementalResearchUpdateResult(
            status=EvidenceDeltaStatus.AMBIGUOUS_REFERENCE, reason=" / ".join(duplicate_findings)
        )

    prior_by_id: dict[str, EvidenceRecord] = {r.evidence_id: r for r in prior_evidence_records}
    current_by_id: dict[str, EvidenceRecord] = {r.evidence_id: r for r in current_evidence_records}

    overlapping_ids = set(prior_by_id) & set(current_by_id)
    mismatched = sorted(eid for eid in overlapping_ids if prior_by_id[eid] != current_by_id[eid])
    if mismatched:
        return IncrementalResearchUpdateResult(
            status=EvidenceDeltaStatus.IDENTITY_MISMATCH,
            reason=(
                "同一evidence_idがPrior/Current両Snapshotに存在しますが、EvidenceRecordの内容が"
                f"一致しません(同一IDは同一内容であるという前提の違反): {mismatched}"
            ),
        )

    # Code Review Finding(D0105)Closure: `evidence.source.source_id ==
    # claim.claim_id`(D0103/D0104のAuthoritative Join Key)は、個々の
    # evidence_idの重複検査(上記)だけでは「claim_id -> evidence_id」が
    # 関数であること(1つのclaim_idに2つ以上の異なるevidence_idが
    # 対応しないこと)を保証しない。Supersession Pair構築時にこの逆引き
    # (claim_id -> old_evidence)を行うため、ここでFunction性を事前に
    # 検証し、違反時は`AMBIGUOUS_REFERENCE`でWhole-Call Abortする——
    # 違反を検知せず「最初に見つかったEvidenceを無言で採用する」ことは
    # 本Module自身の「Silent Trust禁止」方針(D0105 §18、他の全Identity
    # Checkと同じ基準)に反する。
    source_id_owners: dict[str, set[str]] = {}
    for record in (*prior_by_id.values(), *current_by_id.values()):
        source_id_owners.setdefault(record.source.source_id, set()).add(record.evidence_id)
    ambiguous_source_ids = sorted(sid for sid, eids in source_id_owners.items() if len(eids) > 1)
    if ambiguous_source_ids:
        return IncrementalResearchUpdateResult(
            status=EvidenceDeltaStatus.AMBIGUOUS_REFERENCE,
            reason=(
                "同一のevidence.source.source_id(claim_id)に複数の異なるevidence_idが対応しています"
                f"(Authoritative Join Keyの一意性違反、Silent First-Matchを拒否): {ambiguous_source_ids}"
            ),
        )
    evidence_by_source_id: dict[str, EvidenceRecord] = {
        record.source.source_id: record for record in (*prior_by_id.values(), *current_by_id.values())
    }

    new_ids = sorted(set(current_by_id) - set(prior_by_id))
    unchanged_ids = sorted(overlapping_ids)
    removed_ids = sorted(set(prior_by_id) - set(current_by_id))

    all_known_ids = set(prior_by_id) | set(current_by_id)
    missing_refs: list[str] = []
    for artifact in research_artifacts:
        unknown = sorted(set(artifact.included_evidence_ids) - all_known_ids)
        if unknown:
            missing_refs.append(f"artifact_id={artifact.artifact_id} が未知のevidence_idを参照しています: {unknown}")
    if missing_refs:
        return IncrementalResearchUpdateResult(status=EvidenceDeltaStatus.MISSING_REFERENCE, reason=" / ".join(missing_refs))

    claims_by_id: dict[str, SemanticClaim] = {c.claim_id: c for c in semantic_claims}
    # `semantic_claims`はSupersession Lookup(直下の`claims_by_id`)自体にも
    # 必要なため、その存在だけでは「Lineage Verificationを要求されている」
    # とは判定しない——D0104の完全なLineage Bundle(candidates/normalized_
    # documents/disclosure_documents)のうち1つでも供給された場合のみ、
    # NEW Evidence全件に対する`resolve_evidence_lineage()`を実行する
    # (`semantic_claims`単独供給はSupersession-Only Modeとして扱う、
    # Section 14「Prefer less architecture」)。
    lineage_inputs_supplied = bool(candidates or normalized_documents or disclosure_documents)

    lineage_failures: list[LineageFailure] = []
    lineage_failed_new_ids: set[str] = set()
    if lineage_inputs_supplied:
        for new_id in new_ids:
            lineage_result = resolve_evidence_lineage(
                current_by_id[new_id],
                semantic_claims=semantic_claims,
                candidates=candidates,
                normalized_documents=normalized_documents,
                disclosure_documents=disclosure_documents,
            )
            if lineage_result.status != EvidenceLineageStatus.SUCCESS:
                lineage_failures.append(
                    LineageFailure(evidence_id=new_id, lineage_status=lineage_result.status, reason=lineage_result.reason)
                )
                lineage_failed_new_ids.add(new_id)

    superseded_pairs: list[SupersededPair] = []
    pit_failures: list[PitFailure] = []
    in_scope_old_ids = set(unchanged_ids) | set(removed_ids)
    for new_id in new_ids:
        if new_id in lineage_failed_new_ids:
            continue  # D0105 §12: Lineage未検証のEvidenceはSupersession Candidateにしない
        new_evidence = current_by_id[new_id]
        new_claim = claims_by_id.get(new_evidence.source.source_id)
        if new_claim is None or new_claim.supersedes_claim_id is None:
            continue
        old_claim = claims_by_id.get(new_claim.supersedes_claim_id)
        if old_claim is None:
            continue  # 明示的Keyが解決できない -> Fail Conservative、Pairを作らない
        # `evidence_by_source_id`はclaim_id->evidence_idがFunctionである
        # ことを既に検証済み(上記ambiguous_source_idsチェック)のため、
        # ここでのLookupは常に0件または1件のみであり、Silent First-Match
        # Riskは無い(Code Review Finding D0105 Closure)。
        old_evidence = evidence_by_source_id.get(old_claim.claim_id)
        if old_evidence is None or old_evidence.evidence_id not in in_scope_old_ids:
            continue  # 旧Evidenceがこのdeltaの対象範囲に存在しない -> Pairを作らない

        if new_evidence.source.available_at >= old_evidence.source.available_at:
            superseded_pairs.append(
                SupersededPair(
                    new_evidence_id=new_id,
                    old_evidence_id=old_evidence.evidence_id,
                    new_claim_id=new_claim.claim_id,
                    old_claim_id=old_claim.claim_id,
                )
            )
        else:
            pit_failures.append(
                PitFailure(
                    new_evidence_id=new_id,
                    old_evidence_id=old_evidence.evidence_id,
                    reason=(
                        f"new.available_at({new_evidence.source.available_at.isoformat()}) < "
                        f"old.available_at({old_evidence.source.available_at.isoformat()})"
                        "(PIT Order違反、Supersession Candidateから除外)"
                    ),
                )
            )

    superseded_old_ids = {pair.old_evidence_id for pair in superseded_pairs}
    pit_failure_old_ids = {pf.old_evidence_id for pf in pit_failures}
    lineage_failure_ids = {lf.evidence_id for lf in lineage_failures}

    affected_nodes: list[ResearchNodeImpact] = []
    for artifact in research_artifacts:
        referenced = set(artifact.included_evidence_ids)
        reasons: list[str] = []
        affected_evidence: set[str] = set()

        removed_refs = sorted(referenced & set(removed_ids))
        if removed_refs:
            reasons.append(f"参照Evidenceが除去/不在(REMOVED_OR_MISSING): {removed_refs}")
            affected_evidence.update(removed_refs)

        superseded_refs = sorted(referenced & superseded_old_ids)
        if superseded_refs:
            reasons.append(f"参照Evidenceが別Evidenceにより置換される可能性(POTENTIALLY_SUPERSEDED): {superseded_refs}")
            affected_evidence.update(superseded_refs)

        pit_refs = sorted(referenced & pit_failure_old_ids)
        if pit_refs:
            reasons.append(f"参照EvidenceについてSupersession CandidateのPIT不整合を検出: {pit_refs}")
            affected_evidence.update(pit_refs)

        lineage_refs = sorted(referenced & lineage_failure_ids)
        if lineage_refs:
            reasons.append(f"参照EvidenceでLineage不整合を検出: {lineage_refs}")
            affected_evidence.update(lineage_refs)

        status = ResearchImpactStatus.REVIEW_REQUIRED if reasons else ResearchImpactStatus.UNAFFECTED
        affected_nodes.append(
            ResearchNodeImpact(
                artifact_id=artifact.artifact_id,
                status=status,
                reasons=tuple(reasons),
                affected_evidence_ids=tuple(sorted(affected_evidence)),
            )
        )
    affected_nodes.sort(key=lambda node: node.artifact_id)

    referenced_by_any_artifact = {eid for artifact in research_artifacts for eid in artifact.included_evidence_ids}
    unassigned_new_ids = sorted(set(new_ids) - referenced_by_any_artifact)

    return IncrementalResearchUpdateResult(
        status=EvidenceDeltaStatus.SUCCESS,
        new_evidence_ids=tuple(new_ids),
        unchanged_evidence_ids=tuple(unchanged_ids),
        removed_or_missing_evidence_ids=tuple(removed_ids),
        potentially_superseded_pairs=tuple(
            sorted(superseded_pairs, key=lambda pair: (pair.new_evidence_id, pair.old_evidence_id))
        ),
        affected_research_nodes=tuple(affected_nodes),
        unassigned_new_evidence_ids=tuple(unassigned_new_ids),
        lineage_failures=tuple(sorted(lineage_failures, key=lambda lf: lf.evidence_id)),
        pit_failures=tuple(sorted(pit_failures, key=lambda pf: (pf.new_evidence_id, pf.old_evidence_id))),
    )


__all__ = [
    "EvidenceDeltaStatus",
    "IncrementalResearchUpdateResult",
    "IncrementalResearchUpdateSchemaError",
    "LineageFailure",
    "PitFailure",
    "ResearchImpactStatus",
    "ResearchNodeImpact",
    "SupersededPair",
    "build_incremental_research_update",
]
