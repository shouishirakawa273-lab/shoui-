"""Faithfulness Verification: Deterministic Core(Stage 3.18.6、D0102.4.1)。

D0102.4/D0102.4A(DECISIONS.md、`READY_FOR_IMPLEMENTATION`)で確定した
設計をそのままcode化する。本Moduleは`SemanticClaimCandidate` +
`EvidenceSpan`を受け取り、Deterministic(Marker Word List/Decimal
比較/文字列一致)のみでFaithfulnessを判定する。**実Model/Vendor SDKへの
接続はこのModuleに一切存在しない**(`MODEL_CALL_SITES = 0`)。Semantic
Judgmentが必要なCase(一般的なParaphraseの同一性判断・Subject/Scope
判定・多くのClaim TypeのStructural Eligibility)は、Silent ACCEPTせず
必ず`FaithfulnessOutcome.REVIEW_REQUIRED`側へFail Closedする
(D0102.4.1 §26「Model-required cases: REVIEW_REQUIRED」)。

## Core Architecture(D0102.4/D0102.4Aで承認された順序、変更なし)

    SemanticClaimCandidate + NormalizedDisclosureDocument
            |
    Candidate Integrity Gate(型・Enum Runtime検証)
            |
    Source Revalidation Gate(revalidate_evidence_span() == VALID、
    Verification直前に必須再確認、Extraction時点のValidationを信頼しない)
            |
    Deterministic Dimension Checks(8軸、Model呼び出し無し)
            |
    Deterministic Aggregation(Hard-Fail優先、Model呼び出し無し)
            |
    FaithfulnessVerificationResult(status/overall_outcome/
    dimension_results/verification_version/verified_at)

    GENERATOR_VERIFIER_INDEPENDENCE = STRUCTURAL_SEPARATION_V1
    (D0102.4.2でModel-assisted Verifierを別途追加、本Roundでは未実装)
    VERIFICATION_TIMESTAMP_IS_NOT_PIT_AVAILABILITY = TRUE

## Direction Faithfulness(D0102.4A 修正1)

9番目のDimensionは追加しない。増減方向の食い違いは`PROPOSITION_
IDENTITY`の一部として検証する(「増加した」と「減少した」はProposition
そのものが異なるため)。`_check_direction_consistency()`参照。

## Promotion(D0102.4A 修正2、本Roundでは未実装)

本Moduleは`build_semantic_claim()`を一切呼び出さない
(`PROMOTION_IMPLEMENTED = NO`、D0102.4.2のScope)。`ACCEPT`のみが
将来のPromotionに適格、という制約は既存`SemanticClaim` Schema
(`REVIEW_REQUIRED`も構築可能)を変更せず、将来のOrchestration Boundary
側の規律として実装される予定(D0102.4A修正2参照)。

## Re-Verification(D0102.4A 修正3、本Roundでは未実装)

`verification_version`は`extraction_version`を偽造しない
(Verifierが変わっただけでは`extraction_version`も`supersedes_
claim_id`も一切書き換えない)。本Moduleの`candidate_reference`は
`claim_id`/`semantic_identity_key`とは別の新しいIdentity概念であり、
既存Identity Algorithmを一切変更しない(§candidate_reference参照)。

## Claim-Type Structural Eligibility(D0102.4A 修正5)

`BUSINESS_RISK`のみ既存`BUSINESS_RISK_ELIGIBLE_TAXONOMY_NAMES`
(`candidate_extraction.py`、再利用のみ)によるDeterministic
Eligibility判定が可能。他5 Claim Typeには本Round時点でDeterministicな
Structural Eligibility判定手段が無いため、Exact Quote一致であっても
`PROPOSITION_IDENTITY`は`AMBIGUOUS`(`SEMANTIC_VERIFICATION_REQUIRED`)
に倒れ、Overallは`REVIEW_REQUIRED`までしか到達しない(D0102.4.1時点の
既知の制約、D0102.4.2でModel-assisted Verifierが追加されて初めて
これらのClaim Typeも`ACCEPT`へ到達しうる)。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum

from lib.disclosures.candidate_extraction import BUSINESS_RISK_ELIGIBLE_TAXONOMY_NAMES, SemanticClaimCandidate
from lib.disclosures.normalization import NormalizedDisclosureDocument
from lib.disclosures.semantic_claims import (
    ClaimDirection,
    FaithfulnessOutcome,
    RevalidationResult,
    SemanticClaimSchemaError,
    SemanticClaimType,
    evidence_span_identity_fields,
    revalidate_evidence_span,
)
from lib.evidence.model import AiDerivedProvenance
from lib.reproducibility import hash_json_safe

# D0102.4.1 §27: Deterministic-Only Verificationの実装Versionを一意に
# 識別する定数(Marker Word List・Tier定義・QUANTITY Parser実装を含む、
# D0102.4A修正4)。この文字列を変更する場合は実際にDeterministic Logic
# 自体を変更した時のみとする(無関係な変更でVersionを進めない)。
DETERMINISTIC_FAITHFULNESS_VERSION = "faithfulness-det-v1"


class FaithfulnessSchemaError(ValueError):
    """本Module固有のSchema/Provenance Invariant違反で送出する
    (`SemanticClaimSchemaError`/`CandidateExtractionSchemaError`と
    同じ「構造的に不正な入力はValueErrorで拒否する」方針を踏襲する)。"""


class FaithfulnessDimension(StrEnum):
    """D0102(DECISIONS.md)で確定済みの8軸(D0102.4で再確認、本Round
    では追加・削除しない)。"""

    PROPOSITION_IDENTITY = "PROPOSITION_IDENTITY"
    SUBJECT_ATTRIBUTION = "SUBJECT_ATTRIBUTION"
    SCOPE = "SCOPE"
    CAUSAL_STRENGTH = "CAUSAL_STRENGTH"
    CERTAINTY_AND_COMMITMENT = "CERTAINTY_AND_COMMITMENT"
    TEMPORAL_SCOPE = "TEMPORAL_SCOPE"
    QUANTITY = "QUANTITY"
    NEGATION = "NEGATION"


class FaithfulnessDimensionOutcome(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class FaithfulnessCheckMethod(StrEnum):
    """D0102.4.1時点では`DETERMINISTIC`のみが実際に生成される
    (`MODEL`はD0102.4.2、本Roundでは一切使用しない、`MODEL_CALL_SITES
    = 0`)。"""

    DETERMINISTIC = "DETERMINISTIC"
    MODEL = "MODEL"


class FaithfulnessReasonCode(StrEnum):
    """Closed StrEnumのみ(D0102.4 §7「No unrestricted string reason as
    authoritative decision logic」)。本Roundで実際に使用する値のみを
    含める(投機的な値は追加しない)。"""

    EXACT_QUOTE_MATCH = "EXACT_QUOTE_MATCH"
    NO_ISSUE_DETECTED = "NO_ISSUE_DETECTED"
    DIRECTION_MISMATCH_DETECTED = "DIRECTION_MISMATCH_DETECTED"
    DIRECTION_UNSPECIFIED_WITH_EXPLICIT_SOURCE = "DIRECTION_UNSPECIFIED_WITH_EXPLICIT_SOURCE"
    DIRECTION_REQUIRES_SEMANTIC_REVIEW = "DIRECTION_REQUIRES_SEMANTIC_REVIEW"
    QUANTITY_VALUE_MISMATCH = "QUANTITY_VALUE_MISMATCH"
    QUANTITY_UNIT_MISMATCH = "QUANTITY_UNIT_MISMATCH"
    QUANTITY_SIGN_MISMATCH = "QUANTITY_SIGN_MISMATCH"
    QUANTITY_INVENTED = "QUANTITY_INVENTED"
    NEGATION_INVERTED = "NEGATION_INVERTED"
    NEGATION_AMBIGUOUS = "NEGATION_AMBIGUOUS"
    CAUSAL_TIER_UPGRADED = "CAUSAL_TIER_UPGRADED"
    CAUSAL_REQUIRES_SEMANTIC_REVIEW = "CAUSAL_REQUIRES_SEMANTIC_REVIEW"
    CERTAINTY_TIER_UPGRADED = "CERTAINTY_TIER_UPGRADED"
    COMMITMENT_TIER_UPGRADED = "COMMITMENT_TIER_UPGRADED"
    CERTAINTY_REQUIRES_SEMANTIC_REVIEW = "CERTAINTY_REQUIRES_SEMANTIC_REVIEW"
    TEMPORAL_CATEGORY_MISMATCH = "TEMPORAL_CATEGORY_MISMATCH"
    TEMPORAL_REQUIRES_SEMANTIC_REVIEW = "TEMPORAL_REQUIRES_SEMANTIC_REVIEW"
    SEMANTIC_VERIFICATION_REQUIRED = "SEMANTIC_VERIFICATION_REQUIRED"
    NOT_APPLICABLE_NO_RELEVANT_CONTENT = "NOT_APPLICABLE_NO_RELEVANT_CONTENT"
    # D0102.4.1 §13/§29(Test #24): BUSINESS_RISK Allowlist違反専用の
    # 追加Reason Code(D0102.4の最小列挙には無いが、production/testで
    # 実際に使用するため追加する、D0102.4.1 §3「Add more only where
    # implementation exposes meaningful boundaries」)。
    BUSINESS_RISK_TAXONOMY_INELIGIBLE = "BUSINESS_RISK_TAXONOMY_INELIGIBLE"


class FaithfulnessVerificationStatus(StrEnum):
    """`CandidateExtractionStatus`と同型のPattern(D0102.4 §5)。
    D0102.4.1は`SUCCESS`/`CANDIDATE_INTEGRITY_FAILED`/`SOURCE_
    REVALIDATION_FAILED`のみを実際に生成する。`VERIFIER_CONTRACT_
    VIOLATION`/`VERIFIER_ERROR`はD0102.4.2向けにSchemaへ既に含める
    (未使用、本Roundでは到達しない)。"""

    SUCCESS = "SUCCESS"
    CANDIDATE_INTEGRITY_FAILED = "CANDIDATE_INTEGRITY_FAILED"
    SOURCE_REVALIDATION_FAILED = "SOURCE_REVALIDATION_FAILED"
    VERIFIER_CONTRACT_VIOLATION = "VERIFIER_CONTRACT_VIOLATION"
    VERIFIER_ERROR = "VERIFIER_ERROR"


# D0102.4 §16: PROPOSITION_IDENTITY/SUBJECT_ATTRIBUTION/NEGATIONの
# 3軸はNOT_APPLICABLEを一切許可しない(構造的に「該当なし」が存在しない)。
_NEVER_NOT_APPLICABLE: frozenset[FaithfulnessDimension] = frozenset(
    {
        FaithfulnessDimension.PROPOSITION_IDENTITY,
        FaithfulnessDimension.SUBJECT_ATTRIBUTION,
        FaithfulnessDimension.NEGATION,
    }
)

# D0102.4 §16: Hard-Fail軸(いずれかがFAILならOverall=REJECT、他の結果に
# 関わらず最優先)。
_HARD_FAIL_DIMENSIONS: frozenset[FaithfulnessDimension] = frozenset(
    {
        FaithfulnessDimension.PROPOSITION_IDENTITY,
        FaithfulnessDimension.SUBJECT_ATTRIBUTION,
        FaithfulnessDimension.NEGATION,
        FaithfulnessDimension.QUANTITY,
    }
)

# D0102.4 §25: Claim TypeごとのNOT_APPLICABLE禁止(追加)軸。
_REQUIRED_DIMENSIONS_BY_CLAIM_TYPE: dict[SemanticClaimType, frozenset[FaithfulnessDimension]] = {
    SemanticClaimType.PERFORMANCE_CHANGE: frozenset({FaithfulnessDimension.QUANTITY, FaithfulnessDimension.TEMPORAL_SCOPE}),
    SemanticClaimType.PERFORMANCE_DRIVER: frozenset({FaithfulnessDimension.CAUSAL_STRENGTH}),
    SemanticClaimType.BUSINESS_RISK: frozenset({FaithfulnessDimension.CERTAINTY_AND_COMMITMENT, FaithfulnessDimension.NEGATION}),
    SemanticClaimType.MANAGEMENT_EXPLANATION: frozenset(
        {FaithfulnessDimension.SUBJECT_ATTRIBUTION, FaithfulnessDimension.CERTAINTY_AND_COMMITMENT}
    ),
    SemanticClaimType.OUTLOOK: frozenset({FaithfulnessDimension.TEMPORAL_SCOPE, FaithfulnessDimension.CERTAINTY_AND_COMMITMENT}),
    SemanticClaimType.CAPITAL_ALLOCATION: frozenset(
        {
            FaithfulnessDimension.QUANTITY,
            FaithfulnessDimension.SUBJECT_ATTRIBUTION,
            FaithfulnessDimension.CERTAINTY_AND_COMMITMENT,
        }
    ),
}

# 必須軸がNOT_APPLICABLEになった場合に上書きするReason Code
# (Dimension固有の"_REQUIRES_SEMANTIC_REVIEW"が無いQUANTITYのみ
# 汎用のSEMANTIC_VERIFICATION_REQUIREDへFallbackする)。
_REQUIRED_OVERRIDE_REASON: dict[FaithfulnessDimension, FaithfulnessReasonCode] = {
    FaithfulnessDimension.QUANTITY: FaithfulnessReasonCode.SEMANTIC_VERIFICATION_REQUIRED,
    FaithfulnessDimension.CAUSAL_STRENGTH: FaithfulnessReasonCode.CAUSAL_REQUIRES_SEMANTIC_REVIEW,
    FaithfulnessDimension.CERTAINTY_AND_COMMITMENT: FaithfulnessReasonCode.CERTAINTY_REQUIRES_SEMANTIC_REVIEW,
    FaithfulnessDimension.TEMPORAL_SCOPE: FaithfulnessReasonCode.TEMPORAL_REQUIRES_SEMANTIC_REVIEW,
}


@dataclass(kw_only=True, frozen=True)
class FaithfulnessDimensionResult:
    """1 Dimensionの判定結果(D0102.4 §7)。全FieldがClosed Enumのみ
    (自由文字列のAuthoritative Reasonは持たない、D0102.4.1 §28)。"""

    dimension: FaithfulnessDimension
    outcome: FaithfulnessDimensionOutcome
    reason_code: FaithfulnessReasonCode
    checked_by: FaithfulnessCheckMethod

    def __post_init__(self) -> None:
        if not isinstance(self.dimension, FaithfulnessDimension):
            raise FaithfulnessSchemaError(f"dimension は FaithfulnessDimension である必要があります: {self.dimension!r}")
        if not isinstance(self.outcome, FaithfulnessDimensionOutcome):
            raise FaithfulnessSchemaError(f"outcome は FaithfulnessDimensionOutcome である必要があります: {self.outcome!r}")
        if not isinstance(self.reason_code, FaithfulnessReasonCode):
            raise FaithfulnessSchemaError(f"reason_code は FaithfulnessReasonCode である必要があります: {self.reason_code!r}")
        if not isinstance(self.checked_by, FaithfulnessCheckMethod):
            raise FaithfulnessSchemaError(f"checked_by は FaithfulnessCheckMethod である必要があります: {self.checked_by!r}")
        if self.outcome == FaithfulnessDimensionOutcome.NOT_APPLICABLE and self.dimension in _NEVER_NOT_APPLICABLE:
            raise FaithfulnessSchemaError(
                f"{self.dimension.value} は NOT_APPLICABLE を許可しません(D0102.4 §16、構造的に該当なしが存在しない軸)"
            )


@dataclass(kw_only=True, frozen=True)
class FaithfulnessVerificationResult:
    """`verify_candidate_deterministically()`の戻り値(D0102.4 §26、
    D0102.4A修正4でverified_atを追加)。"""

    status: FaithfulnessVerificationStatus
    overall_outcome: FaithfulnessOutcome | None
    dimension_results: tuple[FaithfulnessDimensionResult, ...] = field(default_factory=tuple)
    candidate_reference: str = ""
    verification_version: str
    verified_at: datetime
    verification_provenance: AiDerivedProvenance | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, FaithfulnessVerificationStatus):
            raise FaithfulnessSchemaError(f"status は FaithfulnessVerificationStatus である必要があります: {self.status!r}")
        if not self.verification_version:
            raise FaithfulnessSchemaError("verification_version は空にできません")
        if self.verified_at.tzinfo is None or self.verified_at.utcoffset() is None:
            raise FaithfulnessSchemaError("verified_at はtz-awareである必要があります")
        if self.verified_at.utcoffset() != timedelta(0):
            raise FaithfulnessSchemaError("verified_at はUTCである必要があります(他Timezoneは許可しません)")

        if self.status == FaithfulnessVerificationStatus.SUCCESS:
            if self.overall_outcome is None:
                raise FaithfulnessSchemaError("status=SUCCESS の場合 overall_outcome は None にできません")
            if not isinstance(self.overall_outcome, FaithfulnessOutcome):
                raise FaithfulnessSchemaError(
                    f"overall_outcome は FaithfulnessOutcome である必要があります: {self.overall_outcome!r}"
                )
        elif self.overall_outcome is not None:
            raise FaithfulnessSchemaError(
                f"status={self.status.value} の場合 overall_outcome は必ず None である必要があります"
                "(D0102.4 §26/§33、Verificationが完走しなかったことを明示するため)"
            )

        # D0102.4A修正2: Deterministic-Only Success時はverification_provenanceを持たない
        # (D0102.4A修正4、Model-assisted Checkが無ければAiDerivedProvenanceは意味的に不適切)。
        if self.status == FaithfulnessVerificationStatus.SUCCESS and self.verification_provenance is not None:
            checked_by_methods = {r.checked_by for r in self.dimension_results}
            if FaithfulnessCheckMethod.MODEL not in checked_by_methods:
                raise FaithfulnessSchemaError(
                    "Model-assisted Checkが1件も無いのに verification_provenance が設定されています"
                    "(D0102.4A修正4、Deterministic-Onlyの場合は None である必要があります)"
                )

        # D0102.4A修正2: CANDIDATE_INTEGRITY_FAILED以外は candidate_reference が必須
        # (Candidate自体がInvalidな場合のみ、有効なReferenceを計算できないため許容する)。
        if self.status != FaithfulnessVerificationStatus.CANDIDATE_INTEGRITY_FAILED and not self.candidate_reference:
            raise FaithfulnessSchemaError(f"status={self.status.value} の場合 candidate_reference は空にできません")


def compute_candidate_reference(candidate: SemanticClaimCandidate) -> str:
    """D0102.4 §26/D0102.4A修正3: Candidateを一意に指すReference
    (`claim_id`/`semantic_identity_key`とは別のIdentity概念、既存
    Identity Algorithmは一切変更しない)。EvidenceSpan Identity Fields
    (既存`evidence_span_identity_fields()`を再利用)+`claim_type`+
    `normalized_claim_text`+`direction`から決定論的に導出する。
    `verification_version`/`verified_at`/`verification_provenance`は
    一切含めない(D0102.4A修正3)。"""
    payload: dict[str, object] = {
        **evidence_span_identity_fields(candidate.evidence_span),
        "claim_type": candidate.claim_type.value,
        "normalized_claim_text": candidate.normalized_claim_text,
        "direction": candidate.direction.value,
    }
    return f"CANDREF_{hash_json_safe(payload)}"


def _dim(
    dimension: FaithfulnessDimension,
    outcome: FaithfulnessDimensionOutcome,
    reason_code: FaithfulnessReasonCode,
    *,
    checked_by: FaithfulnessCheckMethod = FaithfulnessCheckMethod.DETERMINISTIC,
) -> FaithfulnessDimensionResult:
    return FaithfulnessDimensionResult(dimension=dimension, outcome=outcome, reason_code=reason_code, checked_by=checked_by)


def _apply_required_dimension_override(
    result: FaithfulnessDimensionResult, *, claim_type: SemanticClaimType
) -> FaithfulnessDimensionResult:
    """D0102.4 §25/D0102.4.1 §24: Claim Typeが当該軸を必須としている場合、
    NOT_APPLICABLEをAMBIGUOUSへ上書きする(「表を満たすためだけにPASSを
    捏造しない」、AMBIGUOUSのみへ倒す)。"""
    if result.outcome != FaithfulnessDimensionOutcome.NOT_APPLICABLE:
        return result
    required = _REQUIRED_DIMENSIONS_BY_CLAIM_TYPE.get(claim_type, frozenset())
    if result.dimension not in required:
        return result
    override_reason = _REQUIRED_OVERRIDE_REASON[result.dimension]
    return _dim(result.dimension, FaithfulnessDimensionOutcome.AMBIGUOUS, override_reason)


# ============================================================
# Direction Consistency(D0102.4A 修正1、PROPOSITION_IDENTITYの一部)
# ============================================================

# D0102.4A 修正1/D0102.4.1 §14: 意図的に小さいMarker語彙のみ(汎用日本語
# NLPを作らない)。「改善」は含めない(単体でINCREASEへ自動変換しない、
# D0102.4A明示要件)。
_INCREASE_MARKERS: tuple[str, ...] = ("増加", "増収", "上昇")
_DECREASE_MARKERS: tuple[str, ...] = ("減少", "減収", "低下")


def _explicit_movement_marker(text: str) -> ClaimDirection | None:
    """Textから明示的な増減Markerを検出する。増加/減少Markerが両方
    存在する(混在)場合は「単一の明確なMarker」とは言えないため`None`
    を返す(D0102.4.1の保守的な単純化)。"""
    has_increase = any(marker in text for marker in _INCREASE_MARKERS)
    has_decrease = any(marker in text for marker in _DECREASE_MARKERS)
    if has_increase and not has_decrease:
        return ClaimDirection.INCREASE
    if has_decrease and not has_increase:
        return ClaimDirection.DECREASE
    return None


def _check_direction_consistency(*, evidence_text: str, candidate: SemanticClaimCandidate) -> FaithfulnessDimensionResult:
    """D0102.4A 修正1: PROPOSITION_IDENTITYの一部としてDirection
    Consistencyを検証する(9番目のDimensionは追加しない)。"""
    evidence_marker = _explicit_movement_marker(evidence_text)
    direction = candidate.direction

    if evidence_marker == ClaimDirection.INCREASE and direction == ClaimDirection.DECREASE:
        return _dim(
            FaithfulnessDimension.PROPOSITION_IDENTITY,
            FaithfulnessDimensionOutcome.FAIL,
            FaithfulnessReasonCode.DIRECTION_MISMATCH_DETECTED,
        )
    if evidence_marker == ClaimDirection.DECREASE and direction == ClaimDirection.INCREASE:
        return _dim(
            FaithfulnessDimension.PROPOSITION_IDENTITY,
            FaithfulnessDimensionOutcome.FAIL,
            FaithfulnessReasonCode.DIRECTION_MISMATCH_DETECTED,
        )
    if evidence_marker is not None and direction == ClaimDirection.UNSPECIFIED:
        return _dim(
            FaithfulnessDimension.PROPOSITION_IDENTITY,
            FaithfulnessDimensionOutcome.AMBIGUOUS,
            FaithfulnessReasonCode.DIRECTION_UNSPECIFIED_WITH_EXPLICIT_SOURCE,
        )
    if evidence_marker is None and direction in (ClaimDirection.INCREASE, ClaimDirection.DECREASE):
        return _dim(
            FaithfulnessDimension.PROPOSITION_IDENTITY,
            FaithfulnessDimensionOutcome.AMBIGUOUS,
            FaithfulnessReasonCode.DIRECTION_REQUIRES_SEMANTIC_REVIEW,
        )
    # evidence_marker == direction(両方Increase/Decreaseで一致)、または
    # 両方 None/UNSPECIFIED(いずれも主張なし)のいずれか——Trivially一致。
    return _dim(
        FaithfulnessDimension.PROPOSITION_IDENTITY, FaithfulnessDimensionOutcome.PASS, FaithfulnessReasonCode.NO_ISSUE_DETECTED
    )


def _check_claim_type_structural_eligibility(candidate: SemanticClaimCandidate) -> FaithfulnessDimensionResult:
    """D0102.4A 修正5: BUSINESS_RISKのみDeterministic Eligibility判定
    可能(既存Allowlist再利用)。他5 Claim TypeはD0102.4.1時点では
    Deterministicに判定できないため常にAMBIGUOUS(SEMANTIC_VERIFICATION_
    REQUIRED)。"""
    if candidate.claim_type == SemanticClaimType.BUSINESS_RISK:
        if candidate.evidence_span.taxonomy_element_name in BUSINESS_RISK_ELIGIBLE_TAXONOMY_NAMES:
            return _dim(
                FaithfulnessDimension.PROPOSITION_IDENTITY,
                FaithfulnessDimensionOutcome.PASS,
                FaithfulnessReasonCode.NO_ISSUE_DETECTED,
            )
        return _dim(
            FaithfulnessDimension.PROPOSITION_IDENTITY,
            FaithfulnessDimensionOutcome.FAIL,
            FaithfulnessReasonCode.BUSINESS_RISK_TAXONOMY_INELIGIBLE,
        )
    return _dim(
        FaithfulnessDimension.PROPOSITION_IDENTITY,
        FaithfulnessDimensionOutcome.AMBIGUOUS,
        FaithfulnessReasonCode.SEMANTIC_VERIFICATION_REQUIRED,
    )


def _check_proposition_identity(*, evidence_text: str, candidate: SemanticClaimCandidate) -> FaithfulnessDimensionResult:
    """D0102.4A修正1(Direction)+D0102.4A修正5(Claim-Type Eligibility)+
    D0102.4 §22(一般的なProposition同一性、Exact Match以外はAMBIGUOUS)を
    合成する。優先順位: Eligibility → Direction → Content(いずれかが
    FAILなら即FAIL、次にAMBIGUOUS、最後にPASS)。"""
    eligibility = _check_claim_type_structural_eligibility(candidate)
    direction = _check_direction_consistency(evidence_text=evidence_text, candidate=candidate)

    if eligibility.outcome == FaithfulnessDimensionOutcome.FAIL:
        return eligibility
    if direction.outcome == FaithfulnessDimensionOutcome.FAIL:
        return direction

    if eligibility.outcome == FaithfulnessDimensionOutcome.AMBIGUOUS:
        return eligibility
    if direction.outcome == FaithfulnessDimensionOutcome.AMBIGUOUS:
        return direction

    # Eligibility=PASS かつ Direction=PASS。残りはContent自体の同一性
    # (Paraphrase判定、D0102.4.1にはModelが無いためExact Match以外は
    # AMBIGUOUS、D0102.4 §22)。
    if candidate.normalized_claim_text in evidence_text:
        return _dim(
            FaithfulnessDimension.PROPOSITION_IDENTITY,
            FaithfulnessDimensionOutcome.PASS,
            FaithfulnessReasonCode.EXACT_QUOTE_MATCH,
        )
    return _dim(
        FaithfulnessDimension.PROPOSITION_IDENTITY,
        FaithfulnessDimensionOutcome.AMBIGUOUS,
        FaithfulnessReasonCode.SEMANTIC_VERIFICATION_REQUIRED,
    )


# ============================================================
# Subject Attribution / Scope(D0102.4.1 §21: 疑似Deterministic化しない)
# ============================================================


def _check_subject_attribution(*, evidence_text: str, candidate: SemanticClaimCandidate) -> FaithfulnessDimensionResult:
    """D0102.4.1 §21: Exact Substring一致の場合のみTrivial PASS、それ
    以外は常にAMBIGUOUS(Semantic Verification必須、D0102.4.2待ち)。
    NOT_APPLICABLEはこの軸では構造的に許可されない(常にPASS/FAIL/
    AMBIGUOUSのいずれか)。"""
    if candidate.normalized_claim_text in evidence_text:
        return _dim(
            FaithfulnessDimension.SUBJECT_ATTRIBUTION, FaithfulnessDimensionOutcome.PASS, FaithfulnessReasonCode.EXACT_QUOTE_MATCH
        )
    return _dim(
        FaithfulnessDimension.SUBJECT_ATTRIBUTION,
        FaithfulnessDimensionOutcome.AMBIGUOUS,
        FaithfulnessReasonCode.SEMANTIC_VERIFICATION_REQUIRED,
    )


def _check_scope(*, evidence_text: str, candidate: SemanticClaimCandidate) -> FaithfulnessDimensionResult:
    """D0102.4.1 §21: SUBJECT_ATTRIBUTIONと同型(Exact Match以外は常に
    AMBIGUOUS)。D0102.4の一般NOT_APPLICABLE原則(両側にScope修飾語が
    無い場合)は、「Scope修飾語の有無」自体の判定にSemantic Judgmentが
    必要なため、D0102.4.1では意図的に適用しない(D0102.4.2でSemantic
    Verifierが揃ってから導入する、Scope不足を理由にNOT_APPLICABLEを
    Modelに自己申告させない)。"""
    if candidate.normalized_claim_text in evidence_text:
        return _dim(FaithfulnessDimension.SCOPE, FaithfulnessDimensionOutcome.PASS, FaithfulnessReasonCode.EXACT_QUOTE_MATCH)
    return _dim(
        FaithfulnessDimension.SCOPE, FaithfulnessDimensionOutcome.AMBIGUOUS, FaithfulnessReasonCode.SEMANTIC_VERIFICATION_REQUIRED
    )


# ============================================================
# Quantity(D0102.4.1 §15/§16、Decimal専用、Source Text非変更)
# ============================================================


@dataclass(frozen=True)
class _ParsedQuantity:
    """比較専用の一時表現(D0102.4.1 §15)。EvidenceSpan/Claim Text
    自体は一切変更しない。"""

    value: Decimal
    is_percent: bool
    unit: str
    source_text: str


_SCALE_KANJI: dict[str, Decimal] = {
    "兆": Decimal("1e12"),
    "億": Decimal("1e8"),
    "万": Decimal("1e4"),
    "千": Decimal("1e3"),
}
_ALLOWED_QUANTITY_UNIT_SUFFIXES: tuple[str, ...] = ("円", "台")
_NUMERAL_SEGMENT_RE = re.compile(r"[0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?(?:兆|億|万|千)?")
# D0102.4.1 §15: Percent/円/台で終わる「数量らしい部分文字列」を検出する
# 粗いSpan(この後 _try_parse_quantity() で厳密Parseする)。
_QUANTITY_SPAN_RE = re.compile(r"△?(?:[0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?(?:兆|億|万|千)?)+(?:%|％|円|台)")


def _parse_numeral(text: str) -> Decimal | None:
    pos = 0
    total = Decimal(0)
    matched_any = False
    while pos < len(text):
        m = _NUMERAL_SEGMENT_RE.match(text, pos)
        if not m or m.start() != pos or m.end() == pos:
            return None
        num_str = m.group(0)
        scale_char = None
        for kanji in _SCALE_KANJI:
            if num_str.endswith(kanji):
                scale_char = kanji
                num_str = num_str[: -len(kanji)]
                break
        try:
            num = Decimal(num_str.replace(",", ""))
        except InvalidOperation:
            return None
        scale = _SCALE_KANJI[scale_char] if scale_char else Decimal(1)
        total += num * scale
        matched_any = True
        pos = m.end()
    if not matched_any or pos != len(text):
        return None
    return total


def _try_parse_quantity(text: str) -> _ParsedQuantity | None:
    body = text
    is_percent = False
    unit = ""
    if body.endswith("%") or body.endswith("％"):
        is_percent = True
        unit = "%"
        body = body[:-1]
    else:
        for suffix in _ALLOWED_QUANTITY_UNIT_SUFFIXES:
            if body.endswith(suffix):
                unit = suffix
                body = body[: -len(suffix)]
                break
        if not unit:
            return None
    sign = Decimal(1)
    if body.startswith("△"):
        sign = Decimal(-1)
        body = body[1:]
    magnitude = _parse_numeral(body)
    if magnitude is None:
        return None
    return _ParsedQuantity(value=sign * magnitude, is_percent=is_percent, unit=unit, source_text=text)


def _find_quantities(text: str) -> list[_ParsedQuantity | None]:
    """Textから数量らしいSpanを全て検出しParseする。粗いSpan検出には
    一致したがParseできなかった場合は`None`を要素として含める
    (D0102.4.1 §16「Never silently discard unparsed numeric text」)。"""
    results: list[_ParsedQuantity | None] = []
    for m in _QUANTITY_SPAN_RE.finditer(text):
        results.append(_try_parse_quantity(m.group(0)))
    return results


def _match_quantity_against_evidence(
    candidate_q: _ParsedQuantity, evidence_parsed: list[_ParsedQuantity]
) -> FaithfulnessReasonCode | None:
    """`None`は一致(PASS相当)を意味する。"""
    same_category = [e for e in evidence_parsed if e.is_percent == candidate_q.is_percent and e.unit == candidate_q.unit]
    for e in same_category:
        if e.value == candidate_q.value:
            return None
    for e in same_category:
        if abs(e.value) == abs(candidate_q.value):
            return FaithfulnessReasonCode.QUANTITY_SIGN_MISMATCH
    if same_category:
        return FaithfulnessReasonCode.QUANTITY_VALUE_MISMATCH
    for e in evidence_parsed:
        if e.value == candidate_q.value:
            return FaithfulnessReasonCode.QUANTITY_UNIT_MISMATCH
    return FaithfulnessReasonCode.QUANTITY_INVENTED


def _check_quantity(*, evidence_text: str, candidate: SemanticClaimCandidate) -> FaithfulnessDimensionResult:
    evidence_tokens = _find_quantities(evidence_text)
    candidate_tokens = _find_quantities(candidate.normalized_claim_text)

    if not evidence_tokens and not candidate_tokens:
        return _dim(
            FaithfulnessDimension.QUANTITY,
            FaithfulnessDimensionOutcome.NOT_APPLICABLE,
            FaithfulnessReasonCode.NOT_APPLICABLE_NO_RELEVANT_CONTENT,
        )
    if any(t is None for t in candidate_tokens):
        return _dim(
            FaithfulnessDimension.QUANTITY,
            FaithfulnessDimensionOutcome.AMBIGUOUS,
            FaithfulnessReasonCode.SEMANTIC_VERIFICATION_REQUIRED,
        )

    evidence_parsed = [t for t in evidence_tokens if t is not None]
    for cq in candidate_tokens:
        assert cq is not None  # noqa: S101 -- 直前のAny(None)Checkで既に排除済み(mypy Narrowing用)
        mismatch_reason = _match_quantity_against_evidence(cq, evidence_parsed)
        if mismatch_reason is not None:
            return _dim(FaithfulnessDimension.QUANTITY, FaithfulnessDimensionOutcome.FAIL, mismatch_reason)

    return _dim(FaithfulnessDimension.QUANTITY, FaithfulnessDimensionOutcome.PASS, FaithfulnessReasonCode.NO_ISSUE_DETECTED)


# ============================================================
# Negation(D0102.4.1 §17)
# ============================================================

_NEGATION_MARKERS: tuple[str, ...] = ("ない", "ありません", "なかった", "認められない", "変更はない")


def _negation_marker_count(text: str) -> int:
    return sum(text.count(marker) for marker in _NEGATION_MARKERS)


def _check_negation(*, evidence_text: str, candidate: SemanticClaimCandidate) -> FaithfulnessDimensionResult:
    evidence_count = _negation_marker_count(evidence_text)
    candidate_count = _negation_marker_count(candidate.normalized_claim_text)

    if evidence_count >= 2 or candidate_count >= 2:
        return _dim(
            FaithfulnessDimension.NEGATION, FaithfulnessDimensionOutcome.AMBIGUOUS, FaithfulnessReasonCode.NEGATION_AMBIGUOUS
        )

    evidence_negated = evidence_count == 1
    candidate_negated = candidate_count == 1
    if evidence_negated != candidate_negated:
        return _dim(FaithfulnessDimension.NEGATION, FaithfulnessDimensionOutcome.FAIL, FaithfulnessReasonCode.NEGATION_INVERTED)
    return _dim(FaithfulnessDimension.NEGATION, FaithfulnessDimensionOutcome.PASS, FaithfulnessReasonCode.NO_ISSUE_DETECTED)


# ============================================================
# Causal Strength(D0102.4.1 §18、Marker Tier)
# ============================================================

_CAUSAL_TIER_MARKERS: tuple[tuple[int, str], ...] = (
    (4, "唯一の原因"),
    (3, "主に"),
    (2, "一因"),
    (2, "寄与"),
    (1, "などにより"),
    (1, "影響"),
)


def _causal_tier(text: str) -> int:
    """Textに含まれるMarkerのうち最大Tierを返す(未検出は0)。"""
    return max((tier for tier, marker in _CAUSAL_TIER_MARKERS if marker in text), default=0)


def _check_causal_strength(*, evidence_text: str, candidate: SemanticClaimCandidate) -> FaithfulnessDimensionResult:
    evidence_tier = _causal_tier(evidence_text)
    candidate_tier = _causal_tier(candidate.normalized_claim_text)

    if evidence_tier == 0 and candidate_tier == 0:
        return _dim(
            FaithfulnessDimension.CAUSAL_STRENGTH,
            FaithfulnessDimensionOutcome.NOT_APPLICABLE,
            FaithfulnessReasonCode.NOT_APPLICABLE_NO_RELEVANT_CONTENT,
        )
    if evidence_tier == 0 and candidate_tier > 0:
        return _dim(
            FaithfulnessDimension.CAUSAL_STRENGTH,
            FaithfulnessDimensionOutcome.AMBIGUOUS,
            FaithfulnessReasonCode.CAUSAL_REQUIRES_SEMANTIC_REVIEW,
        )
    if candidate_tier > evidence_tier:
        return _dim(
            FaithfulnessDimension.CAUSAL_STRENGTH, FaithfulnessDimensionOutcome.FAIL, FaithfulnessReasonCode.CAUSAL_TIER_UPGRADED
        )
    return _dim(
        FaithfulnessDimension.CAUSAL_STRENGTH, FaithfulnessDimensionOutcome.PASS, FaithfulnessReasonCode.NO_ISSUE_DETECTED
    )


# ============================================================
# Certainty and Commitment(D0102.4.1 §19、D0102(D0102.1)既定Mechanism)
# ============================================================

_EPISTEMIC_TIER_MARKERS: tuple[tuple[int, str], ...] = (
    (1, "可能性がある"),
    (2, "見込み"),
    (2, "予想"),
)
_EPISTEMIC_REPORTED_FACT_TIER = 3  # Marker不在時の既定Tier(Hedge無し=断定)

_COMMITMENT_TIER_MARKERS: tuple[tuple[int, str], ...] = (
    (1, "検討"),
    (2, "予定"),
    (3, "決定"),
    (4, "実施"),
)


def _epistemic_tier_or_none(text: str) -> int | None:
    tiers = [tier for tier, marker in _EPISTEMIC_TIER_MARKERS if marker in text]
    return max(tiers) if tiers else None


def _commitment_tier_or_none(text: str) -> int | None:
    tiers = [tier for tier, marker in _COMMITMENT_TIER_MARKERS if marker in text]
    return max(tiers) if tiers else None


def _check_certainty_and_commitment(*, evidence_text: str, candidate: SemanticClaimCandidate) -> FaithfulnessDimensionResult:
    evidence_epistemic = _epistemic_tier_or_none(evidence_text)
    candidate_epistemic = _epistemic_tier_or_none(candidate.normalized_claim_text)
    evidence_commitment = _commitment_tier_or_none(evidence_text)
    candidate_commitment = _commitment_tier_or_none(candidate.normalized_claim_text)

    if (
        evidence_epistemic is None
        and candidate_epistemic is None
        and evidence_commitment is None
        and candidate_commitment is None
    ):
        return _dim(
            FaithfulnessDimension.CERTAINTY_AND_COMMITMENT,
            FaithfulnessDimensionOutcome.NOT_APPLICABLE,
            FaithfulnessReasonCode.NOT_APPLICABLE_NO_RELEVANT_CONTENT,
        )

    # D0102(D0102.1既定): Marker不在側はEpistemicでは「Hedge無し=REPORTED_FACT
    # (最高Tier)」、CommitmentではMarker自体が存在しない場合のみ0として扱う
    # (Commitment言及が無いことは「弱いCommitment」ではなく「言及自体が無い」ため)。
    if evidence_epistemic is not None or candidate_epistemic is not None:
        e_tier = evidence_epistemic if evidence_epistemic is not None else _EPISTEMIC_REPORTED_FACT_TIER
        c_tier = candidate_epistemic if candidate_epistemic is not None else _EPISTEMIC_REPORTED_FACT_TIER
        if c_tier > e_tier:
            return _dim(
                FaithfulnessDimension.CERTAINTY_AND_COMMITMENT,
                FaithfulnessDimensionOutcome.FAIL,
                FaithfulnessReasonCode.CERTAINTY_TIER_UPGRADED,
            )

    if evidence_commitment is not None or candidate_commitment is not None:
        e_tier = evidence_commitment if evidence_commitment is not None else 0
        c_tier = candidate_commitment if candidate_commitment is not None else 0
        if c_tier > e_tier:
            return _dim(
                FaithfulnessDimension.CERTAINTY_AND_COMMITMENT,
                FaithfulnessDimensionOutcome.FAIL,
                FaithfulnessReasonCode.COMMITMENT_TIER_UPGRADED,
            )

    return _dim(
        FaithfulnessDimension.CERTAINTY_AND_COMMITMENT,
        FaithfulnessDimensionOutcome.PASS,
        FaithfulnessReasonCode.NO_ISSUE_DETECTED,
    )


# ============================================================
# Temporal Scope(D0102.4.1 §20)
# ============================================================

_TEMPORAL_CATEGORY_MARKERS: tuple[tuple[str, str], ...] = (
    ("HISTORICAL", "当中間連結会計期間"),
    ("HISTORICAL", "当連結会計年度"),
    ("HISTORICAL", "前年同期"),
    ("HISTORICAL", "現在"),
    ("FUTURE", "今後"),
    ("FUTURE", "翌期"),
    ("FUTURE", "将来"),
    ("FUTURE", "継続的"),
)
# HISTORICAL/CURRENT系は同一Rank(0)、FUTURE/RECURRING系は同一Rank(1)。
_TEMPORAL_RANK: dict[str, int] = {"HISTORICAL": 0, "FUTURE": 1}


def _temporal_category(text: str) -> str | None:
    for category, marker in _TEMPORAL_CATEGORY_MARKERS:
        if marker in text:
            return category
    return None


def _check_temporal_scope(*, evidence_text: str, candidate: SemanticClaimCandidate) -> FaithfulnessDimensionResult:
    evidence_category = _temporal_category(evidence_text)
    candidate_category = _temporal_category(candidate.normalized_claim_text)

    if evidence_category is None and candidate_category is None:
        return _dim(
            FaithfulnessDimension.TEMPORAL_SCOPE,
            FaithfulnessDimensionOutcome.NOT_APPLICABLE,
            FaithfulnessReasonCode.NOT_APPLICABLE_NO_RELEVANT_CONTENT,
        )
    if evidence_category is None or candidate_category is None:
        return _dim(
            FaithfulnessDimension.TEMPORAL_SCOPE,
            FaithfulnessDimensionOutcome.AMBIGUOUS,
            FaithfulnessReasonCode.TEMPORAL_REQUIRES_SEMANTIC_REVIEW,
        )
    if _TEMPORAL_RANK[evidence_category] != _TEMPORAL_RANK[candidate_category]:
        return _dim(
            FaithfulnessDimension.TEMPORAL_SCOPE,
            FaithfulnessDimensionOutcome.FAIL,
            FaithfulnessReasonCode.TEMPORAL_CATEGORY_MISMATCH,
        )
    return _dim(FaithfulnessDimension.TEMPORAL_SCOPE, FaithfulnessDimensionOutcome.PASS, FaithfulnessReasonCode.NO_ISSUE_DETECTED)


# ============================================================
# Aggregation(D0102.4 §15/§16)
# ============================================================

_SOFT_FAIL_DIMENSIONS: frozenset[FaithfulnessDimension] = frozenset(
    {
        FaithfulnessDimension.SCOPE,
        FaithfulnessDimension.CAUSAL_STRENGTH,
        FaithfulnessDimension.CERTAINTY_AND_COMMITMENT,
        FaithfulnessDimension.TEMPORAL_SCOPE,
    }
)


def _aggregate(dimension_results: tuple[FaithfulnessDimensionResult, ...]) -> FaithfulnessOutcome:
    """D0102.4 §15の4段階Ruleをそのまま実装する(Hidden Weighting無し、
    Deterministic Hard-Fail優先)。"""
    by_dimension = {r.dimension: r for r in dimension_results}

    for dimension in _HARD_FAIL_DIMENSIONS:
        r = by_dimension[dimension]
        if r.outcome == FaithfulnessDimensionOutcome.FAIL:
            return FaithfulnessOutcome.REJECT

    for dimension in _SOFT_FAIL_DIMENSIONS:
        r = by_dimension[dimension]
        if r.outcome == FaithfulnessDimensionOutcome.FAIL and r.checked_by == FaithfulnessCheckMethod.DETERMINISTIC:
            return FaithfulnessOutcome.REJECT

    if any(r.outcome == FaithfulnessDimensionOutcome.AMBIGUOUS for r in dimension_results):
        return FaithfulnessOutcome.REVIEW_REQUIRED
    if any(r.outcome == FaithfulnessDimensionOutcome.FAIL and r.dimension in _SOFT_FAIL_DIMENSIONS for r in dimension_results):
        # Deterministic以外(Model-Only FAIL)のSoft Dimension FAIL、
        # D0102.4.1ではModelを使わないため到達しないが、Aggregation
        # Ruleの完全性のためにここへ含める。
        return FaithfulnessOutcome.REVIEW_REQUIRED

    return FaithfulnessOutcome.ACCEPT


def _run_all_dimension_checks(
    *, evidence_text: str, candidate: SemanticClaimCandidate
) -> tuple[FaithfulnessDimensionResult, ...]:
    raw_results = (
        _check_proposition_identity(evidence_text=evidence_text, candidate=candidate),
        _check_subject_attribution(evidence_text=evidence_text, candidate=candidate),
        _check_scope(evidence_text=evidence_text, candidate=candidate),
        _check_causal_strength(evidence_text=evidence_text, candidate=candidate),
        _check_certainty_and_commitment(evidence_text=evidence_text, candidate=candidate),
        _check_temporal_scope(evidence_text=evidence_text, candidate=candidate),
        _check_quantity(evidence_text=evidence_text, candidate=candidate),
        _check_negation(evidence_text=evidence_text, candidate=candidate),
    )
    return tuple(_apply_required_dimension_override(r, claim_type=candidate.claim_type) for r in raw_results)


# ============================================================
# Public Entrypoint(D0102.4 §8/§9/§10)
# ============================================================


def verify_candidate_deterministically(
    *,
    candidate: object,
    document: NormalizedDisclosureDocument,
    verification_version: str = DETERMINISTIC_FAITHFULNESS_VERSION,
    verified_at: datetime,
) -> FaithfulnessVerificationResult:
    """D0102.4.1唯一の公開Entrypoint(D0102.4 §8)。Model呼び出しは
    一切行わない(`MODEL_CALL_SITES = 0`)。Semantic Judgmentが必要な
    Caseは常に`REVIEW_REQUIRED`側へFail Closedする。"""
    # Candidate Integrity Gate(D0102.4 §9/§10、既存SemanticClaimCandidate
    # の型・Runtime検証をそのまま信頼する、独自のCoercionは行わない)。
    if not isinstance(candidate, SemanticClaimCandidate):
        return FaithfulnessVerificationResult(
            status=FaithfulnessVerificationStatus.CANDIDATE_INTEGRITY_FAILED,
            overall_outcome=None,
            dimension_results=(),
            candidate_reference="",
            verification_version=verification_version,
            verified_at=verified_at,
            verification_provenance=None,
            reason="candidate は SemanticClaimCandidate である必要があります",
        )

    candidate_reference = compute_candidate_reference(candidate)

    # Source Revalidation Gate(D0102.4 §9、Verification直前に必須再確認、
    # Extraction時点のValidationを信頼しない)。
    try:
        revalidation = revalidate_evidence_span(candidate.evidence_span, document=document)
    except SemanticClaimSchemaError as exc:
        return FaithfulnessVerificationResult(
            status=FaithfulnessVerificationStatus.SOURCE_REVALIDATION_FAILED,
            overall_outcome=None,
            dimension_results=(),
            candidate_reference=candidate_reference,
            verification_version=verification_version,
            verified_at=verified_at,
            verification_provenance=None,
            reason=str(exc),
        )
    if revalidation != RevalidationResult.VALID:
        return FaithfulnessVerificationResult(
            status=FaithfulnessVerificationStatus.SOURCE_REVALIDATION_FAILED,
            overall_outcome=None,
            dimension_results=(),
            candidate_reference=candidate_reference,
            verification_version=verification_version,
            verified_at=verified_at,
            verification_provenance=None,
            reason=f"revalidation result={revalidation.value}",
        )

    evidence_text = candidate.evidence_span.supporting_quote
    dimension_results = _run_all_dimension_checks(evidence_text=evidence_text, candidate=candidate)
    overall_outcome = _aggregate(dimension_results)

    return FaithfulnessVerificationResult(
        status=FaithfulnessVerificationStatus.SUCCESS,
        overall_outcome=overall_outcome,
        dimension_results=dimension_results,
        candidate_reference=candidate_reference,
        verification_version=verification_version,
        verified_at=verified_at,
        verification_provenance=None,
    )


__all__ = [
    "DETERMINISTIC_FAITHFULNESS_VERSION",
    "FaithfulnessCheckMethod",
    "FaithfulnessDimension",
    "FaithfulnessDimensionOutcome",
    "FaithfulnessDimensionResult",
    "FaithfulnessReasonCode",
    "FaithfulnessSchemaError",
    "FaithfulnessVerificationResult",
    "FaithfulnessVerificationStatus",
    "compute_candidate_reference",
    "verify_candidate_deterministically",
]
