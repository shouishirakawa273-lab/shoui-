"""Evidence Lineage: Deterministic Backward/Forward Provenance Traversal(D0104)。

D0103(`lib.disclosures.evidence_integration.integrate_accepted_semantic_claim()`)
が構築した`EvidenceRecord`を、元のDisclosure Provenanceへ機械的に遡る
唯一の公開Entrypointを提供する。

    EvidenceRecord
        -> SemanticClaim
        -> SemanticClaimCandidate
        -> TextBlock(EvidenceSpanのLocator)
        -> DisclosureDocument

**本Moduleは新しいScoring System・ResearchArtifact生成・NarrativeCase
生成・Bull/Base/Bear判定・SUPPORTS/CONTRADICTS判定・Confidence計算・
期待Return計算・BUY/SELLのいずれも行わない(Infrastructure Only)。**
将来の`ResearchArtifact`/`NarrativeCase`層がこのModuleの戻り値を
参照する想定だが、そのLayerとの境界はこのModule自身では越えない。

## Determinism(D0104 §2)

LLM/Model呼び出しはこのModule内に一切存在しない(`MODEL_CALL_SITES = 0`)。
全てのLink判定は既存Schemaの構造的Equality・既存Deterministic Hash
(`compute_candidate_reference()`、`lib.disclosures.faithfulness`を
そのまま再利用、新しいHash Algorithmは作らない)・既存Revalidation
(`revalidate_evidence_span()`、`lib.disclosures.semantic_claims`をそのまま
再利用)のみで行う。Text類似度・Fuzzy Match・推測によるLink補完は一切
行わない——必要なLinkが見つからない場合は常にTyped Failure
(`EvidenceLineageStatus`)を返す(Silent Repair禁止)。

## Candidate Identity(既存Schemaの再利用のみ、新IDは追加しない)

`SemanticClaimCandidate`はD0102.3 §15により意図的にNon-Persistedであり、
`candidate_id`等の専用識別子を持たない。本Module自身もこの不在を補う
新しい識別子Fieldを追加しない(D0104 §6「Do not silently retrofit IDs
across frozen Phase 1 schemas」)。代わりに`promote_verified_candidate()`
(`lib.disclosures.faithfulness`)が`SemanticClaim`を`candidate.claim_type`/
`normalized_claim_text`/`direction`/`evidence_span`から**そのままCopy**で
構築するという既存Invariantを再利用し、`SemanticClaim`から同じ4 Fieldの
構造的Equalityで元の`SemanticClaimCandidate`を一意に再特定する。一致した
Candidateに対しては既存`compute_candidate_reference()`(`CANDREF_`
Hash、D0102.4で既に確立済みのCandidate Identity概念)を呼び出し、
Lineage結果へそのまま転記する——新しいHash構築はここでは一切行わない。

一致するCandidateが0件の場合(例: `build_semantic_claim()`を直接呼び出し
Candidate Pipelineを経由しなかったClaim)は`MISSING_LINK`を返す。これは
D0103 Reviewer Finding(D0103-R-01、`run-1c62448c7c51`)が指摘した
「Candidate Pipelineを経由しないACCEPT Claimが存在しうる」という既知の
境界強度上の限界を、本Moduleが機械的に検出可能にする(Silent Trustしない)。

## TextBlock Identity(既存Schemaの再利用のみ)

`NormalizedTextBlock`自身にも専用IDは無い——`EvidenceSpan`
(`document_id`/`member_path`/`taxonomy_element_name`/`occurrence_index`/
`char_start`/`char_end`)がそのTextBlock位置への完全な構造的Locatorで
あり、これ自体が既存Architecture上のTextBlock Identityである(新しい
IDは不要)。TextBlockがそのDisclosureDocumentに実在することの確認は
既存`revalidate_evidence_span()`をそのまま呼び出すのみで、独自の
再Parse・再Searchは一切行わない。

## PIT Policy(D0049/D0050、D0103と完全に同一のAlgorithm)

`_resolve_available_at()`は`lib.disclosures.evidence_integration.
_resolve_available_at()`と完全に同一のPriority(`provider_available_at`
がConfirmed[`basis != UNKNOWN`]ならそれ、そうでなければ`retrieved_at`、
`market_public_at`へは決してFallbackしない)である。D0103自身がこの
2行のLogicを(既存の`lib.disclosures.evidence.disclosure_document_to_
evidence()`から)Private Functionとしてそのまま再実装した前例を踏襲し、
本ModuleもPrivate Importに依存せず同じ2行をここでも再実装する——新しい
Availability Algorithmはここでも作らない。EvidenceRecord側の
`source.available_at`と、この関数でDisclosureDocumentから再計算した
値が一致しない場合は`PIT_MISMATCH`とする(Lineage上でPIT Timestampが
Drift していないことを機械的に保証する)。既知のTrade-off(Code
Review、D0104): この2行はD0103側のCoupled Private Copyであり、将来
PIT Priority自体を修正する場合は両方のCopyを同時に更新する必要がある
(共有Public Helperへの切り出しはD0103 Frozen Fileの変更を要するため
本Roundでは行わない)。

## 既知のPerformance Trade-off(Code Review、D0104)

`resolve_evidence_lineage()`は`semantic_claims`/`candidates`/
`normalized_documents`/`disclosure_documents`各Sequenceを単発Linear
Scanする(O(n)×4)。単一`EvidenceRecord`解決には十分だが、将来大量の
`EvidenceRecord`を同じCorpusに対して繰り返し解決する場合(例:
Incremental Research Update)は、呼び出し側が事前にID別Dictへ
Index化してから本関数を複数回呼ぶ最適化を検討すること(本Module自身は
Keep It Simpleの方針により、Graph DatabaseやCaching層を持たない)。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from lib.disclosures.candidate_extraction import SemanticClaimCandidate
from lib.disclosures.faithfulness import compute_candidate_reference
from lib.disclosures.model import DisclosureDocument
from lib.disclosures.normalization import NormalizedDisclosureDocument
from lib.disclosures.semantic_claims import (
    EvidenceSpan,
    FaithfulnessOutcome,
    RevalidationResult,
    SemanticClaim,
    SemanticClaimSchemaError,
    revalidate_evidence_span,
)
from lib.evidence.model import AiDerivedProvenance, AvailabilityBasis, EvidenceRecord, EvidenceType

# D0104: EvidenceRecord.evidence_id はD0103(`integrate_accepted_semantic_
# claim()`)が常にこの形式で構築する(`evidence_id=f"EVID_CLAIM_{claim.
# claim_id}"`)。本Moduleはこれを「唯一の」Join Keyとしては使わない
# (Join Key自体はD0103の docstring通り`evidence.source.source_id ==
# claim.claim_id`が Authoritative)——ここでは逆方向の整合性再確認
# (Tampering/取り違え検出)にのみ使う。
_EVIDENCE_ID_PREFIX = "EVID_CLAIM_"


class EvidenceLineageSchemaError(ValueError):
    """本Module固有のSchema Invariant違反(呼び出し側のProgramming
    Errorに相当するもの)で送出する。Forged/Internally-Inconsistentな
    `SemanticClaim`(型違反・`faithfulness_review_required`矛盾)は
    `lib.disclosures.evidence_integration.EvidenceIntegrationSchemaError`
    と同じ方針でException化する——「必要なLinkが見つからない」という
    正当なDomain上のOutcome(`EvidenceLineageStatus`のTyped Outcomeで
    表現)とは区別する。"""


class EvidenceLineageStatus(StrEnum):
    """`resolve_evidence_lineage()`の主要Outcome(D0104 §8)。"""

    SUCCESS = "SUCCESS"
    MISSING_LINK = "MISSING_LINK"
    AMBIGUOUS_LINK = "AMBIGUOUS_LINK"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    PIT_MISMATCH = "PIT_MISMATCH"
    UNSUPPORTED_PROVENANCE = "UNSUPPORTED_PROVENANCE"


@dataclass(kw_only=True, frozen=True)
class EvidenceLineage:
    """`resolve_evidence_lineage()`が`SUCCESS`時に返すLineage本体
    (D0104 §3)。EvidenceRecord -> SemanticClaim -> SemanticClaimCandidate
    -> TextBlock -> DisclosureDocumentの各段の識別子・Locator・PIT
    Timestamp・Verification Statusを保持する(数値推測・補完は一切
    行わない、全Fieldは既存Schemaからの逐語転記のみ)。"""

    evidence_id: str
    claim_id: str
    semantic_identity_key: str
    candidate_reference: str
    document_id: str
    entity_id: str | None
    document_title: str
    source_document_id: str | None
    raw_snapshot_ref: str | None
    originating_source: str | None
    delivery_provider: str | None
    member_path: str
    taxonomy_element_name: str
    occurrence_index: int
    char_start: int
    char_end: int
    supporting_quote: str
    available_at: datetime
    faithfulness_outcome: FaithfulnessOutcome
    extraction_provenance: AiDerivedProvenance | None

    def __post_init__(self) -> None:
        for field_name in ("evidence_id", "claim_id", "semantic_identity_key", "candidate_reference", "document_id"):
            if not getattr(self, field_name):
                raise EvidenceLineageSchemaError(f"{field_name} は空にできません")
        if self.available_at.tzinfo is None:
            raise EvidenceLineageSchemaError("available_at はtz-awareである必要があります")
        if not isinstance(self.faithfulness_outcome, FaithfulnessOutcome):
            raise EvidenceLineageSchemaError(
                f"faithfulness_outcome は FaithfulnessOutcome である必要があります: {self.faithfulness_outcome!r}"
            )


@dataclass(kw_only=True, frozen=True)
class EvidenceLineageResult:
    """`resolve_evidence_lineage()`の戻り値。`status`が`SUCCESS`以外の
    場合、`lineage`は常に`None`である(D0102.3/D0102.4/D0103と同型の
    Typed Outcome、Exceptionを使わない)。"""

    status: EvidenceLineageStatus
    lineage: EvidenceLineage | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, EvidenceLineageStatus):
            raise EvidenceLineageSchemaError(f"status は EvidenceLineageStatus である必要があります: {self.status!r}")
        if self.reason is not None and not isinstance(self.reason, str):
            raise EvidenceLineageSchemaError(f"reason は str または None である必要があります: {self.reason!r}")
        if self.status == EvidenceLineageStatus.SUCCESS:
            if self.lineage is None:
                raise EvidenceLineageSchemaError("status=SUCCESS の場合 lineage は None にできません")
            if not isinstance(self.lineage, EvidenceLineage):
                raise EvidenceLineageSchemaError(f"lineage は EvidenceLineage である必要があります: {self.lineage!r}")
        elif self.lineage is not None:
            raise EvidenceLineageSchemaError(
                f"status={self.status.value} の場合 lineage は必ず None である必要があります"
                "(Lineage Resolutionが完走しなかったことを明示するため)"
            )


def _fail(status: EvidenceLineageStatus, reason: str) -> EvidenceLineageResult:
    return EvidenceLineageResult(status=status, reason=reason)


def _resolve_available_at(document: DisclosureDocument) -> datetime:
    """D0049/D0050のAvailability優先順位(`lib.disclosures.evidence_
    integration._resolve_available_at()`と完全に同一のLogic、新しい
    Algorithmはここでは作らない、`market_public_at`へは決してFallback
    しない)。D0103自身がこの2行を独立したPrivate Functionとして再実装
    した前例をそのまま踏襲する(Private Importに依存しない)。"""
    if document.provider_available_at is not None and document.provider_available_at_basis != AvailabilityBasis.UNKNOWN:
        return document.provider_available_at
    return document.retrieved_at


def _assert_claim_not_forged(claim: SemanticClaim) -> None:
    """D0103の`integrate_accepted_semantic_claim()`と同じDefense in
    Depth: `faithfulness_outcome`が`FaithfulnessOutcome`のMember
    そのものでない、または`faithfulness_review_required`がOutcomeと
    矛盾する(`__post_init__`を迂回したForged State)場合は
    `EvidenceLineageSchemaError`でFail Closedする(Silent Repairしない)。"""
    if not isinstance(claim.faithfulness_outcome, FaithfulnessOutcome):
        raise EvidenceLineageSchemaError(
            f"claim.faithfulness_outcome は FaithfulnessOutcome である必要があります: {claim.faithfulness_outcome!r}"
        )
    expected_review_required = claim.faithfulness_outcome is FaithfulnessOutcome.REVIEW_REQUIRED
    if claim.faithfulness_review_required is not expected_review_required:
        raise EvidenceLineageSchemaError(
            f"claim.faithfulness_review_required({claim.faithfulness_review_required!r}) が "
            f"faithfulness_outcome({claim.faithfulness_outcome.value}) と整合しません"
            "(Forged/Internally-Inconsistent SemanticClaim、Lineage Resolutionを拒否します)"
        )


def _candidate_matches_claim(candidate: SemanticClaimCandidate, claim: SemanticClaim) -> bool:
    """`promote_verified_candidate()`(`lib.disclosures.faithfulness`)が
    `SemanticClaim`を`candidate`のこの4 Fieldからそのまま(値を変更せず)
    構築するという既存Invariantの逆方向判定。全Field値の構造的Equality
    のみを使う(Hash再計算・Fuzzy Match・部分一致は一切行わない)。"""
    return (
        candidate.evidence_span == claim.evidence_span
        and candidate.claim_type == claim.claim_type
        and candidate.normalized_claim_text == claim.normalized_claim_text
        and candidate.direction == claim.direction
    )


def resolve_evidence_lineage(
    evidence: EvidenceRecord,
    *,
    semantic_claims: Sequence[SemanticClaim],
    candidates: Sequence[SemanticClaimCandidate],
    normalized_documents: Sequence[NormalizedDisclosureDocument],
    disclosure_documents: Sequence[DisclosureDocument],
) -> EvidenceLineageResult:
    """`EvidenceRecord`を元のDisclosure Provenanceへ Deterministicに
    遡る唯一の公開Entrypoint(D0104)。

    呼び出し側は4つのCandidate Source(`semantic_claims`/`candidates`/
    `normalized_documents`/`disclosure_documents`)を明示的にDependency
    Injectionする——隠れたGlobal Registry・自動Discoveryは一切行わない
    (D0104 §5)。各段で一致するEntryが0件なら`MISSING_LINK`、2件以上
    (重複/曖昧なID)なら`AMBIGUOUS_LINK`を返す(任意のEntryを無言で
    選択することは無い、D0104 §7G)。

    - `evidence.evidence_type`が`EvidenceType.CLAIM`でない場合は
      `UNSUPPORTED_PROVENANCE`(本Resolverは`integrate_accepted_
      semantic_claim()`境界が生成したEvidenceのみを対象とする)。
    - `evidence.source.source_id == claim.claim_id`(D0103の既存
      Docstringが明示するAuthoritative Join Key)でSemanticClaimへ
      遡る。見つかったClaimの`evidence_id`が期待されるPattern
      (`EVID_CLAIM_{claim_id}`)と一致しない場合は`IDENTITY_MISMATCH`
      (Tamper/取り違え検出)。
    - `claim.faithfulness_outcome`が`ACCEPT`でない場合は
      `UNSUPPORTED_PROVENANCE`(型違反・Forged Stateは例外、ACCEPT以外
      の正当なOutcomeはTyped Outcome)。
    - `claim`の`evidence_span`/`claim_type`/`normalized_claim_text`/
      `direction`の4 Fieldが完全一致する`SemanticClaimCandidate`を
      `candidates`から一意に特定する(Candidate自身はNon-Persistedで
      専用IDが無いため、これが既存Architecture上唯一のCandidate
      Identity、D0104 §6)。
    - `claim.evidence_span`を、その`document_id`に一致する
      `NormalizedDisclosureDocument`に対して既存`revalidate_evidence_
      span()`で再検証する(`VALID`以外、または構造的不整合の
      Exceptionはいずれも`IDENTITY_MISMATCH`)。
    - 同じ`document_id`(`DisclosureDocument.internal_document_id`と
      同一Identity空間)に一致する`DisclosureDocument`を一意に特定し、
      `evidence.related_codes`/`evidence.provenance_id`との整合性も
      確認する(他Documentからの取り違えをFail Closedで検知する、
      D0104 §14 Reviewer Focus #3への対応)。
    - 最後に`_resolve_available_at(document)`を`evidence.source.
      available_at`と比較し、不一致なら`PIT_MISMATCH`。
    """
    if not isinstance(evidence, EvidenceRecord):
        raise EvidenceLineageSchemaError(f"evidence は EvidenceRecord である必要があります: {evidence!r}")

    if evidence.evidence_type is not EvidenceType.CLAIM:
        return _fail(
            EvidenceLineageStatus.UNSUPPORTED_PROVENANCE,
            f"evidence_type={evidence.evidence_type.value} はSemanticClaim Integration Boundary"
            "(D0103, integrate_accepted_semantic_claim())由来のEvidenceのみ対応します",
        )

    claim_matches = [c for c in semantic_claims if c.claim_id == evidence.source.source_id]
    if len(claim_matches) == 0:
        return _fail(
            EvidenceLineageStatus.MISSING_LINK,
            f"claim_id={evidence.source.source_id!r} に一致するSemanticClaimがsemantic_claimsに存在しません",
        )
    if len(claim_matches) > 1:
        return _fail(
            EvidenceLineageStatus.AMBIGUOUS_LINK,
            f"claim_id={evidence.source.source_id!r} に一致するSemanticClaimが{len(claim_matches)}件あります(重複ID)",
        )
    claim = claim_matches[0]

    expected_evidence_id = f"{_EVIDENCE_ID_PREFIX}{claim.claim_id}"
    if evidence.evidence_id != expected_evidence_id:
        return _fail(
            EvidenceLineageStatus.IDENTITY_MISMATCH,
            f"evidence.evidence_id={evidence.evidence_id!r} は期待される{expected_evidence_id!r}と一致しません",
        )

    _assert_claim_not_forged(claim)
    if claim.faithfulness_outcome is not FaithfulnessOutcome.ACCEPT:
        return _fail(
            EvidenceLineageStatus.UNSUPPORTED_PROVENANCE,
            f"claim.faithfulness_outcome={claim.faithfulness_outcome.value} はACCEPTではありません",
        )

    candidate_matches = [c for c in candidates if _candidate_matches_claim(c, claim)]
    if len(candidate_matches) == 0:
        return _fail(
            EvidenceLineageStatus.MISSING_LINK,
            "claimのevidence_span/claim_type/normalized_claim_text/directionに完全一致するSemanticClaimCandidateが"
            "candidatesに存在しません(build_semantic_claim()直接呼び出し等、Candidate Pipelineを経由しなかった"
            "可能性、D0103 Reviewer Finding D0103-R-01参照)",
        )
    if len(candidate_matches) > 1:
        return _fail(
            EvidenceLineageStatus.AMBIGUOUS_LINK,
            f"claimに完全一致するSemanticClaimCandidateが{len(candidate_matches)}件あります(重複Candidate)",
        )
    candidate = candidate_matches[0]
    candidate_reference = compute_candidate_reference(candidate)

    span: EvidenceSpan = claim.evidence_span

    norm_doc_matches = [d for d in normalized_documents if d.document_id == span.document_id]
    if len(norm_doc_matches) == 0:
        return _fail(
            EvidenceLineageStatus.MISSING_LINK,
            f"document_id={span.document_id!r} に一致するNormalizedDisclosureDocumentがnormalized_documentsに存在しません",
        )
    if len(norm_doc_matches) > 1:
        return _fail(
            EvidenceLineageStatus.AMBIGUOUS_LINK,
            f"document_id={span.document_id!r} に一致するNormalizedDisclosureDocumentが{len(norm_doc_matches)}件あります",
        )
    normalized_document = norm_doc_matches[0]

    try:
        revalidation = revalidate_evidence_span(span, document=normalized_document)
    except SemanticClaimSchemaError as exc:
        return _fail(EvidenceLineageStatus.IDENTITY_MISMATCH, str(exc))
    if revalidation != RevalidationResult.VALID:
        return _fail(
            EvidenceLineageStatus.IDENTITY_MISMATCH,
            f"revalidate_evidence_span()結果={revalidation.value}(TextBlockがDocumentと整合しません)",
        )

    disclosure_doc_matches = [d for d in disclosure_documents if d.internal_document_id == span.document_id]
    if len(disclosure_doc_matches) == 0:
        return _fail(
            EvidenceLineageStatus.MISSING_LINK,
            f"internal_document_id={span.document_id!r} に一致するDisclosureDocumentがdisclosure_documentsに存在しません",
        )
    if len(disclosure_doc_matches) > 1:
        return _fail(
            EvidenceLineageStatus.AMBIGUOUS_LINK,
            f"internal_document_id={span.document_id!r} に一致するDisclosureDocumentが{len(disclosure_doc_matches)}件あります",
        )
    document = disclosure_doc_matches[0]

    # Code Review Finding(D0104)Closure: `evidence.related_codes`/
    # `evidence.provenance_id`のいずれかが空/Noneの場合に無条件でCheckを
    # Skipしていた旧実装は、両者が揃って欠落しているCaller-Supplied
    # DisclosureDocumentが「別Documentからの取り違え」であってもSilently
    # SUCCESSしてしまう(`document.internal_document_id`文字列一致のみに
    # 依存するため)。`integrate_accepted_semantic_claim()`自身の構築式
    # (`related_codes = () if document.entity_id is None else
    # (document.entity_id,)`、`evidence.provenance_id =
    # document.provenance_id`)をそのまま再利用し、`document`から同じ式で
    # 再計算した期待値とEvidence側の値をBidirectionalに厳密Equalityで
    # 比較する——いずれかがNone/空であることそのものもMismatchの対象にする
    # (新しいAlgorithmは作らない、既存の構築式を逆方向に適用するのみ)。
    expected_related_codes = () if document.entity_id is None else (document.entity_id,)
    if evidence.related_codes != expected_related_codes:
        return _fail(
            EvidenceLineageStatus.IDENTITY_MISMATCH,
            f"evidence.related_codes={evidence.related_codes!r} は document.entity_id={document.entity_id!r} から"
            f"期待される{expected_related_codes!r}と一致しません(別Documentからの取り違えの可能性)",
        )
    if evidence.provenance_id != document.provenance_id:
        return _fail(
            EvidenceLineageStatus.IDENTITY_MISMATCH,
            f"evidence.provenance_id={evidence.provenance_id!r} != document.provenance_id={document.provenance_id!r}",
        )

    expected_available_at = _resolve_available_at(document)
    if evidence.source.available_at != expected_available_at:
        return _fail(
            EvidenceLineageStatus.PIT_MISMATCH,
            f"evidence.source.available_at={evidence.source.available_at!r} は再計算された"
            f"available_at={expected_available_at!r}と一致しません(D0049/D0050 Priority Drift)",
        )

    lineage = EvidenceLineage(
        evidence_id=evidence.evidence_id,
        claim_id=claim.claim_id,
        semantic_identity_key=claim.semantic_identity_key,
        candidate_reference=candidate_reference,
        document_id=span.document_id,
        entity_id=document.entity_id,
        document_title=document.title,
        source_document_id=document.source_document_id,
        raw_snapshot_ref=document.raw_snapshot_ref,
        originating_source=document.originating_source,
        delivery_provider=document.delivery_provider,
        member_path=span.member_path,
        taxonomy_element_name=span.taxonomy_element_name,
        occurrence_index=span.occurrence_index,
        char_start=span.char_start,
        char_end=span.char_end,
        supporting_quote=span.supporting_quote,
        available_at=expected_available_at,
        faithfulness_outcome=claim.faithfulness_outcome,
        extraction_provenance=claim.extraction_provenance,
    )
    return EvidenceLineageResult(status=EvidenceLineageStatus.SUCCESS, lineage=lineage)


def evidence_ids_for_document(
    document_id: str,
    *,
    evidence_records: Sequence[EvidenceRecord],
    semantic_claims: Sequence[SemanticClaim],
) -> tuple[str, ...]:
    """Forward Impact Query(D0104 §10): 指定した`DisclosureDocument`
    (`document_id`、`internal_document_id`/`NormalizedDisclosureDocument.
    document_id`と同一Identity空間)から派生した`EvidenceRecord`のID
    一覧を返す。将来のIncremental Research Updateが「このFilingから
    既にどのEvidenceが作られているか」を問い合わせるための最小限の
    Query(D0104 §10、Research Update Logic自体はここでは実装しない)。

    各`EvidenceRecord`は`resolve_evidence_lineage()`と同じAuthoritative
    Join Key(`evidence.source.source_id == claim.claim_id`)+
    `evidence_id`Pattern一致で対応する`SemanticClaim`を一意に特定でき、
    かつそのClaimが`faithfulness_outcome=ACCEPT`(Forged/Internally-
    Inconsistentでない)場合のみ含める——Join先が存在しない・複数存在
    する(曖昧)・`EvidenceType.CLAIM`以外・ACCEPT以外のEvidenceはいずれも
    無言でExcludeする(Fail Closed、過剰Includeしない、D0104 §14
    Reviewer Focus #6)。Code Review Finding(D0104)Closure:
    `resolve_evidence_lineage()`は非ACCEPTを`UNSUPPORTED_PROVENANCE`
    として拒否するが、`claim_id`は`faithfulness_outcome`を含まずに決定論
    的に導出されるため、同じ`claim_id`を持つACCEPT/REVIEW_REQUIRED
    双方のClaimが`semantic_claims`に混在しうる——このForward Queryが
    Backward Resolverより緩い基準でEvidenceを含めてしまうことを防ぐため、
    同じACCEPT-only Gateをここでも独立に適用する。
    """
    if not document_id:
        raise EvidenceLineageSchemaError("document_id は空にできません")

    claims_by_id: dict[str, list[SemanticClaim]] = {}
    for claim in semantic_claims:
        claims_by_id.setdefault(claim.claim_id, []).append(claim)

    matched_evidence_ids: list[str] = []
    for evidence in evidence_records:
        if evidence.evidence_type is not EvidenceType.CLAIM:
            continue
        candidates_for_claim = claims_by_id.get(evidence.source.source_id, [])
        if len(candidates_for_claim) != 1:
            continue
        claim = candidates_for_claim[0]
        _assert_claim_not_forged(claim)
        if claim.faithfulness_outcome is not FaithfulnessOutcome.ACCEPT:
            continue
        if evidence.evidence_id != f"{_EVIDENCE_ID_PREFIX}{claim.claim_id}":
            continue
        if claim.evidence_span.document_id == document_id:
            matched_evidence_ids.append(evidence.evidence_id)
    return tuple(matched_evidence_ids)


__all__ = [
    "EvidenceLineage",
    "EvidenceLineageResult",
    "EvidenceLineageSchemaError",
    "EvidenceLineageStatus",
    "evidence_ids_for_document",
    "resolve_evidence_lineage",
]
