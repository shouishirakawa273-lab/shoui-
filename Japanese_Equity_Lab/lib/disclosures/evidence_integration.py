"""SemanticClaim -> Evidence Integration Boundary(D0103、DEV-AUTO-02.1 Pilot)。

Faithfulness Verificationで`FaithfulnessOutcome.ACCEPT`と判定された
`SemanticClaim`のみを、既存Evidence境界(`lib.evidence.model.
EvidenceRecord`)へ接続する唯一の公開Entrypointを提供する。
`REVIEW_REQUIRED`のSemanticClaim(`SemanticClaim`Schema自体は構築可能)は
このBoundaryでは一切Evidenceへ昇格しない(ACCEPT-only Gate、
`lib.disclosures.faithfulness.promote_verified_candidate()`のACCEPT-only
Promotion Gateと同じ規律をこのBoundaryにも一貫適用する、
`REJECT`のSemanticClaimはSchema自体が構築を拒否するため、ここでは
`ACCEPT`/`REVIEW_REQUIRED`の2値のみを区別すれば良い)。

## Provenance/Identity Join(既存境界の再利用のみ、新Hash Algorithmは作らない)

`SemanticClaim.evidence_span.document_id`は既存`lib.disclosures.model.
DisclosureDocument.internal_document_id`と同一Identity空間である
(`lib.disclosures.semantic_claims`のModule Docstring参照)。このModuleは
Caller起因の取り違え(誤ったDocumentへの紐付け)をFail Closedで検知する
ため、渡された`document`の`internal_document_id`が`claim.evidence_span.
document_id`と一致することを必須確認する。

## Source Timestamp Policy(D0049/D0050のBugfixをそのまま再利用)

`published_at`/`available_at`/`retrieved_at`の決定方針は既存
`lib.disclosures.evidence.disclosure_document_to_evidence()`と
Availability優先順位を完全に同一にする——`market_public_at`
(市場公表時刻、A系統)へは決してFallbackしない(Future Leakage回避)。
新しいAvailability Algorithmはこの Module では作らない。

## Evidence Type(D0040)

`SemanticClaim`はDisclosure本文が実際に述べている内容の抽出結果であり、
その内容の真偽(将来見通し等)自体を検証するものではない
(`lib.evidence.model.EvidenceType`のCLAIM定義: 「主体が述べたことそのもの
はFACTだが、その内容の真偽は別」)。したがって本Moduleが生成する
`EvidenceRecord`は常に`EvidenceType.CLAIM`とする(FACTへ昇格しない)。

## Layer/Provenance(D0040 Anti-Overwrite Invariant)

SemanticClaimはAI/Deterministic Extraction Pipelineの出力であるため、
`layer`は常に`DataLayer.DERIVED`とする。`claim.extraction_provenance`が
存在すればそのまま`EvidenceRecord.ai_derived_provenance`へCopyする
(Provenance Chainを切らない、値を書き換えない)。

## Relation Semantics(D0040)

`EvidenceRecord`自身はHypothesisに対するPositive/Negativeの評価
(`EvidenceRelation`)を一切保持しない(既存Schema通り)。本Moduleも
`EvidenceRelation`をこのBoundaryでは一切割り当てない(将来
`lib.evidence.packet.build_evidence_packet()`側の責務のまま)。このModule
が転記する「関係」は`SemanticClaim`自身が既に持つDescriptive Relation
(`claim_type`/`direction`)のみであり、これらをInvestment Polarityへ
変換せずContent文字列へそのまま転記する(BUY/SELL相当の解釈を加えない、
`lib.disclosures.semantic_claims.ClaimDirection`のDocstring「Investment
Polarityではない」を尊重する)。

## Evidence Span Locator(Provenance Chainを切らない)

`EvidenceRecord`には`EvidenceSpan`を保持する専用Fieldが無い(既存Schema
通り、`lib.evidence.model`は変更しない)。そのため`claim_id`
(`evidence_id`/`source.source_id`)をJoin Keyとして元の`SemanticClaim`へ
遡れるようにした上で、`EvidenceSpan`のLocator(`member_path`/
`taxonomy_element_name`/`occurrence_index`/`char_start`/`char_end`/
`source_raw_canonical_content_hash`/`source_normalizer_version`)も
Content文字列へ逐語転記する(再計算・検索は一切行わない)。

## Extraction TimestampはPIT可用性ではない(D0102.1 §G)

`claim.extraction_provenance.generated_at`(Extraction Run自体の
Metadata)は`available_at`の決定に一切使用しない
(`EXTRACTION_TIMESTAMP_IS_NOT_PIT_AVAILABILITY = TRUE`、
`lib.disclosures.semantic_claims`のModule Docstring参照)。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from lib.disclosures.model import DisclosureDocument
from lib.disclosures.semantic_claims import FaithfulnessOutcome, SemanticClaim
from lib.evidence.model import AvailabilityBasis, DataLayer, EvidenceRecord, EvidenceType
from lib.sources.catalog import DataCapability, PrimaryOrSecondary, SourceAuthorityClass, SourceMetadata


class EvidenceIntegrationSchemaError(ValueError):
    """本Module固有のSchema Invariant違反(呼び出し側のProgramming Error
    に相当するもの)で送出する。`SemanticClaim`がFaithfulness-ACCEPTEDで
    ない、というのは正当なDomain上のOutcomeでありExceptionにしない
    (`SemanticClaimEvidenceIntegrationResult`のTyped Outcomeで表現する、
    D0102.3/D0102.4と同じ「呼び出し側の構造的誤り」と「入力データの正当な
    却下」を区別する方針)。"""


class SemanticClaimIntegrationStatus(StrEnum):
    """`integrate_accepted_semantic_claim()`の主要Outcome。"""

    SUCCESS = "SUCCESS"
    NOT_ACCEPTED = "NOT_ACCEPTED"
    DOCUMENT_IDENTITY_MISMATCH = "DOCUMENT_IDENTITY_MISMATCH"


@dataclass(kw_only=True, frozen=True)
class SemanticClaimEvidenceIntegrationResult:
    """`integrate_accepted_semantic_claim()`の戻り値。`status`が
    `SUCCESS`以外の場合、`evidence`は常に`None`である(D0102.3の
    `CandidateExtractionResult`/D0102.4の`FaithfulnessVerificationResult`
    と同型のTyped Outcome、Exceptionを使わない)。"""

    status: SemanticClaimIntegrationStatus
    evidence: EvidenceRecord | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, SemanticClaimIntegrationStatus):
            raise EvidenceIntegrationSchemaError(
                f"status は SemanticClaimIntegrationStatus である必要があります: {self.status!r}"
            )
        if self.reason is not None and not isinstance(self.reason, str):
            raise EvidenceIntegrationSchemaError(f"reason は str または None である必要があります: {self.reason!r}")

        if self.status == SemanticClaimIntegrationStatus.SUCCESS:
            if self.evidence is None:
                raise EvidenceIntegrationSchemaError("status=SUCCESS の場合 evidence は None にできません")
            if not isinstance(self.evidence, EvidenceRecord):
                raise EvidenceIntegrationSchemaError(f"evidence は EvidenceRecord である必要があります: {self.evidence!r}")
        elif self.evidence is not None:
            raise EvidenceIntegrationSchemaError(
                f"status={self.status.value} の場合 evidence は必ず None である必要があります"
                "(Integrationが完走しなかったことを明示するため)"
            )


def _resolve_available_at(document: DisclosureDocument) -> datetime:
    """D0049/D0050のAvailability優先順位をそのまま再利用する(既存
    `lib.disclosures.evidence.disclosure_document_to_evidence()`と完全に
    同一のLogic、新しいAlgorithmはここでは作らない、`market_public_at`
    へは決してFallbackしない)。"""
    if document.provider_available_at is not None and document.provider_available_at_basis != AvailabilityBasis.UNKNOWN:
        return document.provider_available_at
    return document.retrieved_at


def integrate_accepted_semantic_claim(
    *,
    claim: SemanticClaim,
    document: DisclosureDocument,
    source_authority_class: SourceAuthorityClass,
) -> SemanticClaimEvidenceIntegrationResult:
    """Faithfulness-ACCEPTEDな`SemanticClaim`のみをEvidence境界へ接続する
    唯一の公開Entrypoint(D0103 Pilot)。

    - `claim`が`SemanticClaim`でない場合は呼び出し側のProgramming Error
      として`EvidenceIntegrationSchemaError`をRaiseする(D0102.4の
      Candidate Integrity Gateと異なり、この引数はModel出力ではなく既に
      型で保証されたInternal Objectのみを受け取る契約のため)。
    - `document`が`DisclosureDocument`でない、`source_authority_class`が
      `SourceAuthorityClass`でない場合も同様にRaiseする。
    - `claim.faithfulness_outcome`が`FaithfulnessOutcome`のMemberそのもの
      でない場合(例: 生の文字列`"ACCEPT"`——`StrEnum`は文字列と`==`で
      一致してしまうため、Gateは`is`で判定する)、および
      `faithfulness_review_required`が`faithfulness_outcome`と矛盾する
      場合(`SemanticClaim.__post_init__`を迂回したForged State)は
      `EvidenceIntegrationSchemaError`でFail Closedする(Silent Repairは
      行わない、`promote_verified_candidate()`のDefense in Depthと同じ
      方針)。
    - `claim.faithfulness_outcome`が`FaithfulnessOutcome.ACCEPT`でない
      場合(`REVIEW_REQUIRED`を含む)は`NOT_ACCEPTED`、`EvidenceRecord`は
      一切構築しない。
    - `document.internal_document_id`が`claim.evidence_span.document_id`
      と一致しない場合は`DOCUMENT_IDENTITY_MISMATCH`(Caller起因の
      取り違えをFail Closedで検知する)。

    `document`(`lib.disclosures.model.DisclosureDocument`、Source非依存の
    Common Core Raw Model)は`lib.disclosures.normalization.
    NormalizedDisclosureDocument`とは別Objectである——PIT Timestamp
    (`market_public_at`/`provider_available_at`/`retrieved_at`)と
    `source_authority_class`はNormalized Layerには存在しないため、
    これらを保持するCommon Core Documentを別途要求する
    (`lib.disclosures.evidence.disclosure_document_to_evidence()`と同じ
    引数設計を踏襲する)。
    """
    if not isinstance(claim, SemanticClaim):
        raise EvidenceIntegrationSchemaError(f"claim は SemanticClaim である必要があります: {claim!r}")
    if not isinstance(document, DisclosureDocument):
        raise EvidenceIntegrationSchemaError(f"document は DisclosureDocument である必要があります: {document!r}")
    if not isinstance(source_authority_class, SourceAuthorityClass):
        raise EvidenceIntegrationSchemaError(
            f"source_authority_class は SourceAuthorityClass である必要があります: {source_authority_class!r}"
        )
    if not isinstance(claim.faithfulness_outcome, FaithfulnessOutcome):
        raise EvidenceIntegrationSchemaError(
            f"claim.faithfulness_outcome は FaithfulnessOutcome である必要があります: {claim.faithfulness_outcome!r}"
        )
    expected_review_required = claim.faithfulness_outcome is FaithfulnessOutcome.REVIEW_REQUIRED
    if claim.faithfulness_review_required is not expected_review_required:
        raise EvidenceIntegrationSchemaError(
            f"claim.faithfulness_review_required({claim.faithfulness_review_required!r}) が "
            f"faithfulness_outcome({claim.faithfulness_outcome.value}) と整合しません"
            "(Forged/Internally-Inconsistent SemanticClaim、Integrationを拒否します)"
        )

    if claim.faithfulness_outcome is not FaithfulnessOutcome.ACCEPT:
        return SemanticClaimEvidenceIntegrationResult(
            status=SemanticClaimIntegrationStatus.NOT_ACCEPTED,
            reason=f"faithfulness_outcome={claim.faithfulness_outcome.value}",
        )

    if claim.evidence_span.document_id != document.internal_document_id:
        return SemanticClaimEvidenceIntegrationResult(
            status=SemanticClaimIntegrationStatus.DOCUMENT_IDENTITY_MISMATCH,
            reason=(
                f"claim.evidence_span.document_id={claim.evidence_span.document_id!r} != "
                f"document.internal_document_id={document.internal_document_id!r}"
            ),
        )

    available_at = _resolve_available_at(document)
    entity_label = document.entity_id or document.internal_document_id
    span = claim.evidence_span
    content = (
        f"{entity_label}: 「{claim.normalized_claim_text}」"
        f"(claim_type={claim.claim_type.value}, direction={claim.direction.value}, "
        f"faithfulness_outcome={claim.faithfulness_outcome.value}, "
        f"source_document={document.internal_document_id}, "
        f"member_path={span.member_path}, taxonomy_element_name={span.taxonomy_element_name}, "
        f"occurrence_index={span.occurrence_index}, char_start={span.char_start}, char_end={span.char_end}, "
        f"source_raw_canonical_content_hash={span.source_raw_canonical_content_hash}, "
        f"source_normalizer_version={span.source_normalizer_version}, "
        f"extraction_version={claim.extraction_version})"
    )
    source = SourceMetadata(
        source_id=claim.claim_id,
        source_type="DISCLOSURE_SEMANTIC_CLAIM",
        provider_name=document.delivery_provider or document.originating_source or "UNKNOWN",
        source_authority_class=source_authority_class,
        primary_or_secondary=PrimaryOrSecondary.PRIMARY,
        retrieved_at=document.retrieved_at,
        published_at=document.market_public_at,
        available_at=available_at,
        originating_source=document.originating_source,
        delivery_provider=document.delivery_provider,
        provenance_id=document.provenance_id,
    )
    related_codes = () if document.entity_id is None else (document.entity_id,)
    evidence = EvidenceRecord(
        evidence_id=f"EVID_CLAIM_{claim.claim_id}",
        evidence_type=EvidenceType.CLAIM,
        layer=DataLayer.DERIVED,
        capability=DataCapability.DISCLOSURE,
        content=content,
        source=source,
        related_codes=related_codes,
        ai_derived_provenance=claim.extraction_provenance,
        provenance_id=document.provenance_id,
    )
    return SemanticClaimEvidenceIntegrationResult(status=SemanticClaimIntegrationStatus.SUCCESS, evidence=evidence)


__all__ = [
    "EvidenceIntegrationSchemaError",
    "SemanticClaimEvidenceIntegrationResult",
    "SemanticClaimIntegrationStatus",
    "integrate_accepted_semantic_claim",
]
