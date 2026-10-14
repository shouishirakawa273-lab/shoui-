"""Semantic Claim Provenance Schema(Stage 3.18.4、D0102.2)。

D0102.1(DECISIONS.md)で確定したDeterministic Contractをそのままcode化
する。本Moduleが提供するのはSchema/Provenance Infrastructureのみで
あり、LLMによるCandidate生成・8軸Faithfulness Verification Algorithm
はいずれも実装しない(将来Round、D0102.1 §Implementation Scope参照)。

## Core Architecture Invariant(D0102.1)

    NormalizedDisclosureDocument (D0101.1、不変)
            |
    Deterministic Orchestration が正確に1 NormalizedTextBlock を選択
            |
    Caller が全Source Identityを確定(LLM呼び出し前)
            |
    (将来Round) LLMはclaim_type/normalized_claim_text/directionのみ提案
            |
    EvidenceSpan.from_text_block() -- 純粋なCopy、検索なし
            |
    (将来Round) Faithfulness Verification
            |
    SemanticClaim

    SOURCE_IDENTITY_AUTHORITY = CALLER_PINNED_NON_LLM
    ONE_SOURCE_TEXTBLOCK_PER_EXTRACTION_CALL = REQUIRED_V1
    EVIDENCE_BINDING_DEPENDS_ON_SOURCE_NOT_CLAIM = TRUE
    EXTRACTION_TIMESTAMP_IS_NOT_PIT_AVAILABILITY = TRUE

上記4つのInvariant名自体はD0102.1の設計記録(DECISIONS.md)との対応を
明示するためのDocumentation Commentであり、本Module内でLLM呼び出し・
Orchestration自体は行わない(D0102.2はSchemaのみ)。

## v1 Evidence Granularity(D0102.1 §B/§6)

`EvidenceSpan`は常にCaller-pinned `NormalizedTextBlock`全体そのもの
である。`char_start`/`char_end`/`supporting_quote`は該当TextBlockから
逐語copyのみで、独自の再計算・substring re-resolution・fuzzy matchは
一切行わない(`EvidenceSpan.from_text_block()`参照)。`SemanticClaim`は
`EvidenceSpan`を単数(tupleではない)で持ち、Cross-TextBlock Composition
はこのSchema上構造的に表現不可能である(D0102.1 B02修正)。

## PIT境界(D0102.1 §G、変更なし)

`document_id`は既存`lib.disclosures.model.DisclosureDocument.
internal_document_id`と同一Identity空間であることを前提とする(この
Join Keyの整合性はCaller側の責務、本Module自身は`DisclosureDocument`
への依存を持たない)。本Moduleはいかなる意味でもPIT判定
(`market_public_at`等)を行わない。`AiDerivedProvenance.generated_at`は
Extraction Run自体のMetadataであり、PIT可用性の判定に一切使用しない
(`revalidate_evidence_span()`はgenerated_atを一切参照しない)。

## Identity Model(D0102.1 §F)

`semantic_identity_key`(「この特定のEvidenceから、この特定の
Propositionが」を表す、`extraction_version`を含まない)と`claim_id`
(`semantic_identity_key`+`extraction_version`、Extraction Run単位で
一意)を分離する。Canonical Hashは既存`lib.reproducibility.
hash_json_safe()`(JSON `sort_keys=True`によるKey名Alphabetical Order、
SHA-256)をそのまま再利用し、新しいHash Algorithmは作らない——Key名の
辞書順がCanonical Orderであり、呼び出し側の引数順・Dict構築順には
一切依存しない。

## REVIEW_REQUIRED Contract(D0102.1 §8)

`SemanticClaim`は`faithfulness_outcome`(`FaithfulnessOutcome`)を
Authoritativeな状態として保持し、`faithfulness_review_required`
(bool)はそこから機械的に導出される値として`__post_init__`で相互検証
する(Booleanのみを保持するよりも、`REVIEW_REQUIRED`の理由を後から
拡張しやすく、矛盾したState[Outcome=ACCEPTなのにreview_required=True
等]をConstructor Levelで構造的に排除できるため、両方保持する設計を
選んだ)。`faithfulness_outcome=REJECT`のCandidateは`SemanticClaim`を
構築できない(REJECTされたCandidateは永続化しない、D0102.1の
Architecture図の通り「discarded, logged」であり「SemanticClaim」には
ならない)。本Module自身は`FaithfulnessOutcome`の判定Algorithmを一切
実装しない(D0102.1 §16「Do NOT invent semantic verification
behavior」)。
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from enum import StrEnum

from lib.disclosures.normalization import (
    NormalizedDisclosureDocument,
    NormalizedDisclosureMember,
    NormalizedTextBlock,
)
from lib.evidence.model import AiDerivedProvenance
from lib.reproducibility import hash_json_safe

SCHEMA_VERSION = "SEMANTIC_CLAIM_SCHEMA_V1"

# D0102.1 §9: Claim Text内で許容する制御文字相当(既存D0101.1の空白畳み込み
# Policyとは別軸——本Roundはevidenceの再正規化を一切行わない、Claim Text
# 自体の入力Sanitizeのみ)。
_ALLOWED_WHITESPACE_CONTROL_CHARS = frozenset({"\n", "\t"})


class SemanticClaimSchemaError(ValueError):
    """本Module固有のSchema/Provenance Invariant違反で送出する。
    `ValueError`のSubclassであり、既存Code(`lib.disclosures.
    normalization.DisclosureNormalizationError`等)と同じ「構造的に
    不正な入力はValueErrorで拒否する」方針を踏襲する。"""


class SemanticClaimType(StrEnum):
    """D0102.1で確定したv1 Taxonomy(6種、`OTHER_MATERIAL_DISCLOSURE`は
    Catch-all化によるSemantic Overreach Riskのため意図的に除外)。
    Investment判断語(BULLISH/BEARISH/POSITIVE_CATALYST等)は一切含め
    ない。"""

    PERFORMANCE_CHANGE = "PERFORMANCE_CHANGE"
    PERFORMANCE_DRIVER = "PERFORMANCE_DRIVER"
    BUSINESS_RISK = "BUSINESS_RISK"
    MANAGEMENT_EXPLANATION = "MANAGEMENT_EXPLANATION"
    OUTLOOK = "OUTLOOK"
    CAPITAL_ALLOCATION = "CAPITAL_ALLOCATION"


class ClaimDirection(StrEnum):
    """Sourceの語彙をそのまま反映するのみのDescriptive Direction。
    Investment Polarity(強気/弱気)ではない(D0102.1)。"""

    INCREASE = "INCREASE"
    DECREASE = "DECREASE"
    UNSPECIFIED = "UNSPECIFIED"


class FaithfulnessOutcome(StrEnum):
    """D0102.1 §11の3値Outcome。本Module自身はこの値をどう決定するかの
    Algorithmを持たない(Enum/Data Contractのみ)。"""

    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class RevalidationResult(StrEnum):
    """`revalidate_evidence_span()`の結果(D0102.1 §14)。"""

    VALID = "VALID"
    NEEDS_REVALIDATION = "NEEDS_REVALIDATION"


@dataclass(kw_only=True, frozen=True)
class EvidenceSpan:
    """Caller-pinned `NormalizedTextBlock` 1件への、逐語copyによる
    Provenance参照(D0102.1)。

    `EvidenceSpan.from_text_block()`経由での構築を推奨するが、
    Constructor自体を直接呼び出した場合も`__post_init__`のInvariantは
    常に検証される(`lib.disclosures.normalization`の既存Constructor-
    level Validation Patternを踏襲、構築経路に依らない検証)。

    `char_start`/`char_end`はMember-relative(`NormalizedTextBlock`と
    同じ座標系、Block-relativeという第2の座標系は存在しない)。
    """

    document_id: str
    source_raw_canonical_content_hash: str
    source_normalizer_version: str
    member_path: str
    taxonomy_element_name: str
    occurrence_index: int
    char_start: int
    char_end: int
    supporting_quote: str

    def __post_init__(self) -> None:
        if not self.document_id:
            raise SemanticClaimSchemaError("document_id は空にできません")
        if not self.source_raw_canonical_content_hash:
            raise SemanticClaimSchemaError("source_raw_canonical_content_hash は空にできません")
        if not self.source_normalizer_version:
            raise SemanticClaimSchemaError("source_normalizer_version は空にできません")
        if not self.member_path:
            raise SemanticClaimSchemaError("member_path は空にできません")
        if not self.taxonomy_element_name:
            raise SemanticClaimSchemaError("taxonomy_element_name は空にできません")
        if self.occurrence_index < 0:
            raise SemanticClaimSchemaError("occurrence_index は0以上である必要があります")
        if self.char_start < 0 or self.char_end < self.char_start:
            raise SemanticClaimSchemaError("char_start/char_end が不正です")
        if len(self.supporting_quote) != (self.char_end - self.char_start):
            raise SemanticClaimSchemaError("supporting_quote の長さがchar_start/char_endと整合しません")

    @staticmethod
    def from_text_block(
        *,
        document: NormalizedDisclosureDocument,
        member: NormalizedDisclosureMember,
        text_block: NormalizedTextBlock,
    ) -> EvidenceSpan:
        """D0102.1 §4: `document`/`member`/`text_block`はCallerが既に
        確定させたAuthoritative D0101.1 Source Objectそのものである
        こと(LLM出力から構築してはならない、
        `EVIDENCE_BINDING_DEPENDS_ON_SOURCE_NOT_CLAIM = TRUE`)。
        `char_start`/`char_end`/`supporting_quote`はtext_blockから逐語
        copyするのみで、検索・再計算・Fuzzy Matchは一切行わない。

        `text_block`が実際に`member`に属し、`member`が実際に`document`
        に属することをここで確認する(Caller側の取り違え・偽装Object
        混入をFail Closedで検知する、D0102.1 §5「Whole-TextBlock v1
        Policy」)。
        """
        if member not in document.members:
            raise SemanticClaimSchemaError(f"member({member.member_path!r}) はdocument({document.document_id!r})に属していません")
        if text_block not in member.text_blocks:
            raise SemanticClaimSchemaError(
                f"text_block({text_block.taxonomy_element_name!r}, occurrence="
                f"{text_block.occurrence_index}) はmember({member.member_path!r})に属していません"
            )

        span = EvidenceSpan(
            document_id=document.document_id,
            source_raw_canonical_content_hash=document.raw_canonical_content_hash,
            source_normalizer_version=document.normalizer_version,
            member_path=member.member_path,
            taxonomy_element_name=text_block.taxonomy_element_name,
            occurrence_index=text_block.occurrence_index,
            char_start=text_block.char_start,
            char_end=text_block.char_end,
            supporting_quote=text_block.normalized_text,
        )
        # Defense in depth(D0101.1と同じ方針): NormalizedDisclosureMember
        # 自身が既に同種のInvariantを検証済みだが、EvidenceSpanへのCopy
        # 結果に対しても独立に再検証する。
        if member.normalized_text[span.char_start : span.char_end] != span.supporting_quote:
            raise SemanticClaimSchemaError(
                "EvidenceSpanのsupporting_quoteがmember.normalized_textのSliceと一致しません(Exact Quote Invariant違反)"
            )
        return span


def validate_claim_text(text: str) -> None:
    """Claim Text(`normalized_claim_text`)自体のSchema Safety Check
    (D0102.1 §9)。空/空白のみ/制御文字を拒否する。Evidence自体の
    再正規化ではない。

    D0102.3.1(Candidate Extraction Layer)からも再利用される公開関数
    ——同種のValidation LogicをModule間で重複実装しない(D0102.3.1
    §1「Do not duplicate these models」の精神を、この1関数についても
    そのまま適用する)。"""
    if not text:
        raise SemanticClaimSchemaError("normalized_claim_text は空にできません")
    if not text.strip():
        raise SemanticClaimSchemaError("normalized_claim_text は空白のみにできません")
    for ch in text:
        if ch in _ALLOWED_WHITESPACE_CONTROL_CHARS:
            continue
        # Unicode General Category "C*"(Control/Format/Surrogate/Private
        # Use/Unassigned)を許可しない保守的なSanitize Check(D0102.1
        # §9)。Evidence自体の再正規化ではなく、Claim Text入力自体の
        # Schema Safety Checkに限定する。
        if unicodedata.category(ch).startswith("C"):
            raise SemanticClaimSchemaError(f"normalized_claim_text に許可されない制御文字が含まれています: {ch!r}")


@dataclass(kw_only=True, frozen=True)
class SemanticClaim:
    """Deterministic Provenance Layer上のSemantic Claim 1件(D0102.1)。

    `evidence_span`は単数(tupleではない)——Cross-TextBlock Composition
    はこのSchema上構造的に表現不可能である(D0102.1 B02修正)。
    """

    claim_id: str
    semantic_identity_key: str
    claim_type: SemanticClaimType
    normalized_claim_text: str
    direction: ClaimDirection
    evidence_span: EvidenceSpan
    faithfulness_outcome: FaithfulnessOutcome
    faithfulness_review_required: bool
    extraction_version: str
    schema_version: str = SCHEMA_VERSION
    extraction_provenance: AiDerivedProvenance | None = None
    supersedes_claim_id: str | None = None

    def __post_init__(self) -> None:
        # D0102.1 §7: evidence_spanは単数(EvidenceSpanそのもの)のみ許可
        # する。Tuple/List等を渡された場合はここでRuntime Rejectする
        # (Type Hintだけではdataclassは強制しないため、Cross-Block
        # Compositionが「構造的に表現不可能」であることをRuntimeでも
        # 保証する)。
        if not isinstance(self.evidence_span, EvidenceSpan):
            raise SemanticClaimSchemaError(
                "evidence_span は単一のEvidenceSpanである必要があります"
                "(Tuple/List等の複数EvidenceSpanはv1では許可されません、D0102.1 B02修正)"
            )
        validate_claim_text(self.normalized_claim_text)
        if not self.claim_id:
            raise SemanticClaimSchemaError("claim_id は空にできません")
        if not self.semantic_identity_key:
            raise SemanticClaimSchemaError("semantic_identity_key は空にできません")
        if not self.extraction_version:
            raise SemanticClaimSchemaError("extraction_version は空にできません")
        if not self.schema_version:
            raise SemanticClaimSchemaError("schema_version は空にできません")

        if self.faithfulness_outcome == FaithfulnessOutcome.REJECT:
            raise SemanticClaimSchemaError(
                "faithfulness_outcome=REJECTのSemanticClaimは構築できません"
                "(REJECTされたCandidateはSemanticClaimとして永続化しない、D0102.1のArchitectureの通り)"
            )

        # D0102.1 §8 REVIEW_REQUIRED Contract: 矛盾したState
        # (Outcome=ACCEPTなのにreview_required=True等)をConstructor
        # Levelで拒否する。
        expected_review_required = self.faithfulness_outcome == FaithfulnessOutcome.REVIEW_REQUIRED
        if self.faithfulness_review_required != expected_review_required:
            raise SemanticClaimSchemaError(
                f"faithfulness_review_required({self.faithfulness_review_required}) が "
                f"faithfulness_outcome({self.faithfulness_outcome}) と整合しません"
                "(REVIEW_REQUIRED時のみTrueである必要があります)"
            )


def evidence_span_identity_fields(span: EvidenceSpan) -> dict[str, str | int]:
    """`EvidenceSpan`から`compute_semantic_identity_key()`が必要とする
    Identity Field群のみを取り出す(呼び出し側がField名を書き間違える
    リスクを減らすための小さなHelper)。"""
    return {
        "document_id": span.document_id,
        "source_raw_canonical_content_hash": span.source_raw_canonical_content_hash,
        "source_normalizer_version": span.source_normalizer_version,
        "member_path": span.member_path,
        "taxonomy_element_name": span.taxonomy_element_name,
        "occurrence_index": span.occurrence_index,
        "char_start": span.char_start,
        "char_end": span.char_end,
    }


def compute_semantic_identity_key(
    *,
    document_id: str,
    source_raw_canonical_content_hash: str,
    source_normalizer_version: str,
    member_path: str,
    taxonomy_element_name: str,
    occurrence_index: int,
    char_start: int,
    char_end: int,
    claim_type: SemanticClaimType,
    normalized_claim_text: str,
    schema_version: str,
) -> str:
    """D0102.1 §F: 「この特定のEvidenceから、この特定のPropositionが」を
    表す`semantic_identity_key`(`extraction_version`を含まない)。既存
    `lib.reproducibility.hash_json_safe()`(JSON `sort_keys=True`に
    よるKey名Alphabetical Order、SHA-256)をそのまま再利用する——Key名の
    辞書順がCanonical Orderであり、この関数の引数順・呼び出し順・Dict
    構築順のいずれにも依存しない(D0102.1要件I: Creation Order
    Independence)。
    """
    payload: dict[str, str | int] = {
        "document_id": document_id,
        "source_raw_canonical_content_hash": source_raw_canonical_content_hash,
        "source_normalizer_version": source_normalizer_version,
        "member_path": member_path,
        "taxonomy_element_name": taxonomy_element_name,
        "occurrence_index": occurrence_index,
        "char_start": char_start,
        "char_end": char_end,
        "claim_type": claim_type.value,
        "normalized_claim_text": normalized_claim_text,
        "schema_version": schema_version,
    }
    return f"SEMID_{hash_json_safe(payload)}"


def compute_claim_id(*, semantic_identity_key: str, extraction_version: str) -> str:
    """D0102.1 §F: `claim_id` = `semantic_identity_key` + `extraction_
    version`のHash(Extraction Run単位で一意、Append-Only)。"""
    payload = {"semantic_identity_key": semantic_identity_key, "extraction_version": extraction_version}
    return f"CLAIM_{hash_json_safe(payload)}"


def build_semantic_claim(
    *,
    claim_type: SemanticClaimType,
    normalized_claim_text: str,
    direction: ClaimDirection,
    evidence_span: EvidenceSpan,
    faithfulness_outcome: FaithfulnessOutcome,
    extraction_version: str,
    schema_version: str = SCHEMA_VERSION,
    extraction_provenance: AiDerivedProvenance | None = None,
    supersedes_claim_id: str | None = None,
) -> SemanticClaim:
    """`semantic_identity_key`/`claim_id`を`evidence_span`とClaim
    Fieldsから決定論的に導出しつつ`SemanticClaim`を構築するHelper
    (D0102.1 §F)。呼び出し側がHashを手計算する必要をなくす。

    `supersedes_claim_id`はこの関数が推測することはない
    (D0102.1 §13、常にCaller明示指定、既定`None`)。
    """
    semantic_identity_key = compute_semantic_identity_key(
        document_id=evidence_span.document_id,
        source_raw_canonical_content_hash=evidence_span.source_raw_canonical_content_hash,
        source_normalizer_version=evidence_span.source_normalizer_version,
        member_path=evidence_span.member_path,
        taxonomy_element_name=evidence_span.taxonomy_element_name,
        occurrence_index=evidence_span.occurrence_index,
        char_start=evidence_span.char_start,
        char_end=evidence_span.char_end,
        claim_type=claim_type,
        normalized_claim_text=normalized_claim_text,
        schema_version=schema_version,
    )
    claim_id = compute_claim_id(semantic_identity_key=semantic_identity_key, extraction_version=extraction_version)
    return SemanticClaim(
        claim_id=claim_id,
        semantic_identity_key=semantic_identity_key,
        claim_type=claim_type,
        normalized_claim_text=normalized_claim_text,
        direction=direction,
        evidence_span=evidence_span,
        faithfulness_outcome=faithfulness_outcome,
        faithfulness_review_required=(faithfulness_outcome == FaithfulnessOutcome.REVIEW_REQUIRED),
        extraction_version=extraction_version,
        schema_version=schema_version,
        extraction_provenance=extraction_provenance,
        supersedes_claim_id=supersedes_claim_id,
    )


def revalidate_evidence_span(
    span: EvidenceSpan,
    *,
    document: NormalizedDisclosureDocument,
) -> RevalidationResult:
    """D0102.1 §14: 永続化済み`EvidenceSpan`を、現在Loadされている
    `NormalizedDisclosureDocument`に対して検証する。

    Offset Remap・旧Quote Textの再探索・Fuzzy Matchはいずれも行わない
    (`str.find`/`str.index`等の使用は一切ない)。`generated_at`等の
    Extraction Timestampも一切参照しない(`EXTRACTION_TIMESTAMP_IS_
    NOT_PIT_AVAILABILITY = TRUE`、このRevalidation自体もPIT判定では
    ない)。

    - document_id不一致: 呼び出し側の取り違え、SemanticClaimSchemaError
    - raw_canonical_content_hash/normalizer_versionいずれかが不一致:
      `NEEDS_REVALIDATION`(Version自体が変わっているだけなので、
      Silent RemapもSilent Trustもしない)
    - Version一致にもかかわらずMember/TextBlock自体が見つからない、
      またはOffset/Content自体が食い違う: より深刻な構造的不整合
      (Tampering/Corruption疑い)としてSemanticClaimSchemaErrorで
      Fail Closedする(Versionが同じならD0101.1の決定論的挙動により
      同一Contentになるはずのため)。
    """
    if span.document_id != document.document_id:
        raise SemanticClaimSchemaError(f"document_id不一致: span={span.document_id!r} document={document.document_id!r}")

    if (
        span.source_raw_canonical_content_hash != document.raw_canonical_content_hash
        or span.source_normalizer_version != document.normalizer_version
    ):
        return RevalidationResult.NEEDS_REVALIDATION

    member = next((m for m in document.members if m.member_path == span.member_path), None)
    if member is None:
        raise SemanticClaimSchemaError(f"member({span.member_path!r}) が現在のdocument内に存在しません")

    text_block = next(
        (
            b
            for b in member.text_blocks
            if b.taxonomy_element_name == span.taxonomy_element_name and b.occurrence_index == span.occurrence_index
        ),
        None,
    )
    if text_block is None:
        raise SemanticClaimSchemaError(
            f"TextBlock({span.taxonomy_element_name!r}, occurrence={span.occurrence_index}) が "
            f"member({span.member_path!r})内に存在しません"
        )

    if text_block.char_start != span.char_start or text_block.char_end != span.char_end:
        raise SemanticClaimSchemaError("char_start/char_endが現在のTextBlockと一致しません(構造的不整合)")
    if span.char_end > len(member.normalized_text):
        raise SemanticClaimSchemaError("char_endが現在のmember.normalized_textの範囲を超えています")
    if member.normalized_text[span.char_start : span.char_end] != span.supporting_quote:
        raise SemanticClaimSchemaError(
            "supporting_quoteが現在のmember.normalized_textのSliceと一致しません(Tampering/Corruption疑い)"
        )
    if text_block.normalized_text != span.supporting_quote:
        raise SemanticClaimSchemaError("supporting_quoteが現在のTextBlock.normalized_textと一致しません")

    return RevalidationResult.VALID


__all__ = [
    "SCHEMA_VERSION",
    "ClaimDirection",
    "EvidenceSpan",
    "FaithfulnessOutcome",
    "RevalidationResult",
    "SemanticClaim",
    "SemanticClaimSchemaError",
    "SemanticClaimType",
    "build_semantic_claim",
    "compute_claim_id",
    "compute_semantic_identity_key",
    "evidence_span_identity_fields",
    "revalidate_evidence_span",
    "validate_claim_text",
]
