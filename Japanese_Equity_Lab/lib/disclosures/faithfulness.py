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
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Protocol

from lib.disclosures.candidate_extraction import BUSINESS_RISK_ELIGIBLE_TAXONOMY_NAMES, SemanticClaimCandidate
from lib.disclosures.normalization import NormalizedDisclosureDocument
from lib.disclosures.semantic_claims import (
    ClaimDirection,
    FaithfulnessOutcome,
    RevalidationResult,
    SemanticClaim,
    SemanticClaimSchemaError,
    SemanticClaimType,
    build_semantic_claim,
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

# D0102.4.2: Model-Assisted Verification(Deterministic Checks +
# `FaithfulnessVerifier` Protocol経由のModel-Assisted Checksの組合せ)の
# 実装Versionを一意に識別する定数。Deterministic-Only Callには引き続き
# `DETERMINISTIC_FAITHFULNESS_VERSION`を使う(`verify_candidate_
# deterministically()`は本Roundでも無変更)。
MODEL_ASSISTED_FAITHFULNESS_VERSION = "faithfulness-model-v1"


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
    # D0102.4.1.2 F02 Closure(§3A): 数量らしいTextは検出できたが厳密Parser
    # では安全にParseしきれなかった場合専用のReason Code(Malformed Comma
    # 区切り・全角数字・未対応Scale Kanji等、Silent Partial Extraction/
    # Silent Disappearの禁止)。
    UNPARSED_NUMERIC_CONTENT = "UNPARSED_NUMERIC_CONTENT"
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
    # D0102.4.2: Model-Assisted Check専用の追加Reason Code(D0102.4 §3の
    # 設計Noteに例示されていた名称をそのまま採用、実装で実際に使用する
    # 分のみ追加する)。
    # PROPOSITION_IDENTITY: ModelがPASSを提案し、かつ小さな事前承認済み
    # Paraphrase Pair Table(`_APPROVED_PROPOSITION_PARAPHRASES`)で
    # Deterministicに Ratify できた場合のみ使用する(Model単独のPASS宣言
    # を最終権威にしない、D0102設計方針)。
    PARAPHRASE_EQUIVALENT_CONFIRMED = "PARAPHRASE_EQUIVALENT_CONFIRMED"
    # PROPOSITION_IDENTITY: Model-Assisted Checkが、Paraphrase自体が
    # 同一Propositionを表していない、またはclaim_typeがEvidence内容と
    # Semanticに矛盾すると判定した場合(D0102.4A修正5のClaim-Type
    # Semantic Compatibility判定を含む)。
    PROPOSITION_SEMANTIC_MISMATCH_DETECTED = "PROPOSITION_SEMANTIC_MISMATCH_DETECTED"
    # SUBJECT_ATTRIBUTION: Model-Assisted CheckがCandidateの主張する
    # Subject/Entity/SegmentがSupporting Quoteと異なると判定した場合。
    SUBJECT_MISMATCH_DETECTED = "SUBJECT_MISMATCH_DETECTED"
    # SCOPE: Model-Assisted Checkが重要なScope修飾語(全社/Segment・
    # 地域・製品・連結/単独・期間等)の脱落または追加を検出した場合。
    SCOPE_QUALIFIER_DROPPED = "SCOPE_QUALIFIER_DROPPED"


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

# D0102.4.2.1 D42-N01 Closure: dimension/outcome/reason_codeは個別には
# 正当なEnum値でも、その組合せ自体が無意味な場合(例:
# SUBJECT_ATTRIBUTION+PASS+QUANTITY_INVENTED)を拒否するための閉じた
# Mapping。既存Code(上記各`_check_*()`の`_dim()`呼び出し・
# `_REQUIRED_OVERRIDE_REASON`)が実際に生成する組合せのみを機械的に
# 抽出したもの(推測・汎用Rules Engineは作らない)。`FaithfulnessDimension
# Result.__post_init__()`から参照され、Deterministic Path・
# Model-Assisted Path双方の全Construction経路に一貫適用される
# (Model Response Validationはこの同じExceptionをCatchしてWhole-
# Response-Fatalへ変換する、§5B)。
_REASON_CODE_ALLOWED_DIMENSIONS: dict[FaithfulnessReasonCode, frozenset[FaithfulnessDimension]] = {
    FaithfulnessReasonCode.EXACT_QUOTE_MATCH: frozenset(
        {FaithfulnessDimension.PROPOSITION_IDENTITY, FaithfulnessDimension.SUBJECT_ATTRIBUTION, FaithfulnessDimension.SCOPE}
    ),
    # NO_ISSUE_DETECTEDは全軸のPASS(Deterministic/Model-Assisted問わず)で
    # 共通使用する汎用Reason Code(既存Deterministic Code+D0102.4.2
    # Toyota Fixtureの両方で実際に使用されている)。
    FaithfulnessReasonCode.NO_ISSUE_DETECTED: frozenset(FaithfulnessDimension),
    FaithfulnessReasonCode.DIRECTION_MISMATCH_DETECTED: frozenset({FaithfulnessDimension.PROPOSITION_IDENTITY}),
    FaithfulnessReasonCode.DIRECTION_UNSPECIFIED_WITH_EXPLICIT_SOURCE: frozenset({FaithfulnessDimension.PROPOSITION_IDENTITY}),
    FaithfulnessReasonCode.DIRECTION_REQUIRES_SEMANTIC_REVIEW: frozenset({FaithfulnessDimension.PROPOSITION_IDENTITY}),
    FaithfulnessReasonCode.BUSINESS_RISK_TAXONOMY_INELIGIBLE: frozenset({FaithfulnessDimension.PROPOSITION_IDENTITY}),
    FaithfulnessReasonCode.PARAPHRASE_EQUIVALENT_CONFIRMED: frozenset({FaithfulnessDimension.PROPOSITION_IDENTITY}),
    FaithfulnessReasonCode.PROPOSITION_SEMANTIC_MISMATCH_DETECTED: frozenset({FaithfulnessDimension.PROPOSITION_IDENTITY}),
    FaithfulnessReasonCode.SUBJECT_MISMATCH_DETECTED: frozenset({FaithfulnessDimension.SUBJECT_ATTRIBUTION}),
    FaithfulnessReasonCode.SCOPE_QUALIFIER_DROPPED: frozenset({FaithfulnessDimension.SCOPE}),
    FaithfulnessReasonCode.QUANTITY_VALUE_MISMATCH: frozenset({FaithfulnessDimension.QUANTITY}),
    FaithfulnessReasonCode.QUANTITY_UNIT_MISMATCH: frozenset({FaithfulnessDimension.QUANTITY}),
    FaithfulnessReasonCode.QUANTITY_SIGN_MISMATCH: frozenset({FaithfulnessDimension.QUANTITY}),
    FaithfulnessReasonCode.QUANTITY_INVENTED: frozenset({FaithfulnessDimension.QUANTITY}),
    FaithfulnessReasonCode.UNPARSED_NUMERIC_CONTENT: frozenset({FaithfulnessDimension.QUANTITY}),
    FaithfulnessReasonCode.NEGATION_INVERTED: frozenset({FaithfulnessDimension.NEGATION}),
    FaithfulnessReasonCode.NEGATION_AMBIGUOUS: frozenset({FaithfulnessDimension.NEGATION}),
    FaithfulnessReasonCode.CAUSAL_TIER_UPGRADED: frozenset({FaithfulnessDimension.CAUSAL_STRENGTH}),
    FaithfulnessReasonCode.CAUSAL_REQUIRES_SEMANTIC_REVIEW: frozenset({FaithfulnessDimension.CAUSAL_STRENGTH}),
    FaithfulnessReasonCode.CERTAINTY_TIER_UPGRADED: frozenset({FaithfulnessDimension.CERTAINTY_AND_COMMITMENT}),
    FaithfulnessReasonCode.COMMITMENT_TIER_UPGRADED: frozenset({FaithfulnessDimension.CERTAINTY_AND_COMMITMENT}),
    FaithfulnessReasonCode.CERTAINTY_REQUIRES_SEMANTIC_REVIEW: frozenset({FaithfulnessDimension.CERTAINTY_AND_COMMITMENT}),
    FaithfulnessReasonCode.TEMPORAL_CATEGORY_MISMATCH: frozenset({FaithfulnessDimension.TEMPORAL_SCOPE}),
    FaithfulnessReasonCode.TEMPORAL_REQUIRES_SEMANTIC_REVIEW: frozenset({FaithfulnessDimension.TEMPORAL_SCOPE}),
    FaithfulnessReasonCode.SEMANTIC_VERIFICATION_REQUIRED: frozenset(
        {
            FaithfulnessDimension.PROPOSITION_IDENTITY,
            FaithfulnessDimension.SUBJECT_ATTRIBUTION,
            FaithfulnessDimension.SCOPE,
            FaithfulnessDimension.QUANTITY,
        }
    ),
    FaithfulnessReasonCode.NOT_APPLICABLE_NO_RELEVANT_CONTENT: frozenset(
        {
            FaithfulnessDimension.QUANTITY,
            FaithfulnessDimension.CAUSAL_STRENGTH,
            FaithfulnessDimension.CERTAINTY_AND_COMMITMENT,
            FaithfulnessDimension.TEMPORAL_SCOPE,
        }
    ),
}

_REASON_CODE_ALLOWED_OUTCOMES: dict[FaithfulnessReasonCode, frozenset[FaithfulnessDimensionOutcome]] = {
    FaithfulnessReasonCode.EXACT_QUOTE_MATCH: frozenset({FaithfulnessDimensionOutcome.PASS}),
    FaithfulnessReasonCode.NO_ISSUE_DETECTED: frozenset({FaithfulnessDimensionOutcome.PASS}),
    FaithfulnessReasonCode.PARAPHRASE_EQUIVALENT_CONFIRMED: frozenset({FaithfulnessDimensionOutcome.PASS}),
    FaithfulnessReasonCode.DIRECTION_MISMATCH_DETECTED: frozenset({FaithfulnessDimensionOutcome.FAIL}),
    FaithfulnessReasonCode.QUANTITY_VALUE_MISMATCH: frozenset({FaithfulnessDimensionOutcome.FAIL}),
    FaithfulnessReasonCode.QUANTITY_UNIT_MISMATCH: frozenset({FaithfulnessDimensionOutcome.FAIL}),
    FaithfulnessReasonCode.QUANTITY_SIGN_MISMATCH: frozenset({FaithfulnessDimensionOutcome.FAIL}),
    FaithfulnessReasonCode.QUANTITY_INVENTED: frozenset({FaithfulnessDimensionOutcome.FAIL}),
    FaithfulnessReasonCode.NEGATION_INVERTED: frozenset({FaithfulnessDimensionOutcome.FAIL}),
    FaithfulnessReasonCode.CAUSAL_TIER_UPGRADED: frozenset({FaithfulnessDimensionOutcome.FAIL}),
    FaithfulnessReasonCode.CERTAINTY_TIER_UPGRADED: frozenset({FaithfulnessDimensionOutcome.FAIL}),
    FaithfulnessReasonCode.COMMITMENT_TIER_UPGRADED: frozenset({FaithfulnessDimensionOutcome.FAIL}),
    FaithfulnessReasonCode.TEMPORAL_CATEGORY_MISMATCH: frozenset({FaithfulnessDimensionOutcome.FAIL}),
    FaithfulnessReasonCode.BUSINESS_RISK_TAXONOMY_INELIGIBLE: frozenset({FaithfulnessDimensionOutcome.FAIL}),
    FaithfulnessReasonCode.PROPOSITION_SEMANTIC_MISMATCH_DETECTED: frozenset({FaithfulnessDimensionOutcome.FAIL}),
    FaithfulnessReasonCode.SUBJECT_MISMATCH_DETECTED: frozenset({FaithfulnessDimensionOutcome.FAIL}),
    FaithfulnessReasonCode.SCOPE_QUALIFIER_DROPPED: frozenset({FaithfulnessDimensionOutcome.FAIL}),
    FaithfulnessReasonCode.DIRECTION_UNSPECIFIED_WITH_EXPLICIT_SOURCE: frozenset({FaithfulnessDimensionOutcome.AMBIGUOUS}),
    FaithfulnessReasonCode.DIRECTION_REQUIRES_SEMANTIC_REVIEW: frozenset({FaithfulnessDimensionOutcome.AMBIGUOUS}),
    FaithfulnessReasonCode.NEGATION_AMBIGUOUS: frozenset({FaithfulnessDimensionOutcome.AMBIGUOUS}),
    FaithfulnessReasonCode.CAUSAL_REQUIRES_SEMANTIC_REVIEW: frozenset({FaithfulnessDimensionOutcome.AMBIGUOUS}),
    FaithfulnessReasonCode.CERTAINTY_REQUIRES_SEMANTIC_REVIEW: frozenset({FaithfulnessDimensionOutcome.AMBIGUOUS}),
    FaithfulnessReasonCode.TEMPORAL_REQUIRES_SEMANTIC_REVIEW: frozenset({FaithfulnessDimensionOutcome.AMBIGUOUS}),
    FaithfulnessReasonCode.SEMANTIC_VERIFICATION_REQUIRED: frozenset({FaithfulnessDimensionOutcome.AMBIGUOUS}),
    FaithfulnessReasonCode.UNPARSED_NUMERIC_CONTENT: frozenset({FaithfulnessDimensionOutcome.AMBIGUOUS}),
    FaithfulnessReasonCode.NOT_APPLICABLE_NO_RELEVANT_CONTENT: frozenset({FaithfulnessDimensionOutcome.NOT_APPLICABLE}),
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

        # D0102.4.2.1 D42-N01 Closure: dimension/outcome/reason_codeは
        # 個別にはEnumとして正当でも、その組合せ自体が無意味な場合
        # (例: SUBJECT_ATTRIBUTION+PASS+QUANTITY_INVENTED)を拒否する。
        allowed_dimensions_for_reason = _REASON_CODE_ALLOWED_DIMENSIONS.get(self.reason_code)
        if allowed_dimensions_for_reason is not None and self.dimension not in allowed_dimensions_for_reason:
            raise FaithfulnessSchemaError(
                f"reason_code={self.reason_code.value} は dimension={self.dimension.value} では使用できません"
                f"(許可されるDimension: {sorted(d.value for d in allowed_dimensions_for_reason)})"
            )
        allowed_outcomes_for_reason = _REASON_CODE_ALLOWED_OUTCOMES.get(self.reason_code)
        if allowed_outcomes_for_reason is not None and self.outcome not in allowed_outcomes_for_reason:
            raise FaithfulnessSchemaError(
                f"reason_code={self.reason_code.value} は outcome={self.outcome.value} では使用できません"
                f"(許可されるOutcome: {sorted(o.value for o in allowed_outcomes_for_reason)})"
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
        # D0102.4.1.1 F06 Closure: Truthy Checkのみ(`not self.field`)では
        # 型不正な値(例: 数値やList等、Type Hintを無視した直接構築)を
        # 検出できない。Constructor Level(Public API境界)でRuntime型
        # 検証を行う既存Pattern(`SemanticClaimCandidate.__post_init__()`
        # 等)をこのSchemaにも一貫適用する。
        if not isinstance(self.status, FaithfulnessVerificationStatus):
            raise FaithfulnessSchemaError(f"status は FaithfulnessVerificationStatus である必要があります: {self.status!r}")
        if not isinstance(self.verification_version, str) or not self.verification_version:
            raise FaithfulnessSchemaError("verification_version は空でないstrである必要があります")
        if self.verified_at.tzinfo is None or self.verified_at.utcoffset() is None:
            raise FaithfulnessSchemaError("verified_at はtz-awareである必要があります")
        if self.verified_at.utcoffset() != timedelta(0):
            raise FaithfulnessSchemaError("verified_at はUTCである必要があります(他Timezoneは許可しません)")
        if not isinstance(self.candidate_reference, str):
            raise FaithfulnessSchemaError(f"candidate_reference は str である必要があります: {self.candidate_reference!r}")
        if self.reason is not None and not isinstance(self.reason, str):
            raise FaithfulnessSchemaError(f"reason は str または None である必要があります: {self.reason!r}")
        if self.verification_provenance is not None and not isinstance(self.verification_provenance, AiDerivedProvenance):
            raise FaithfulnessSchemaError(
                f"verification_provenance は AiDerivedProvenance または None である必要があります: "
                f"{self.verification_provenance!r}"
            )

        # D0102.4.1.1 F06 Closure: dimension_resultsがTuple以外
        # (List/Generator等)で渡された場合、または要素の一部が
        # FaithfulnessDimensionResultでない場合を検出する。既存
        # `SemanticClaim.__post_init__()`のEvidenceSpan単数性検証と
        # 同じ「Type Hintだけに頼らずRuntimeでも保証する」方針を踏襲。
        if not isinstance(self.dimension_results, tuple):
            raise FaithfulnessSchemaError(
                f"dimension_results は tuple である必要があります: {type(self.dimension_results).__name__}"
            )
        for r in self.dimension_results:
            if not isinstance(r, FaithfulnessDimensionResult):
                raise FaithfulnessSchemaError(
                    f"dimension_results の各要素は FaithfulnessDimensionResult である必要があります: {r!r}"
                )
        dimensions_seen = [r.dimension for r in self.dimension_results]
        if len(dimensions_seen) != len(set(dimensions_seen)):
            duplicates = sorted({d.value for d in dimensions_seen if dimensions_seen.count(d) > 1})
            raise FaithfulnessSchemaError(f"dimension_results に同一Dimensionの重複Entryがあります: {duplicates}")

        if self.status == FaithfulnessVerificationStatus.SUCCESS:
            if self.overall_outcome is None:
                raise FaithfulnessSchemaError("status=SUCCESS の場合 overall_outcome は None にできません")
            if not isinstance(self.overall_outcome, FaithfulnessOutcome):
                raise FaithfulnessSchemaError(
                    f"overall_outcome は FaithfulnessOutcome である必要があります: {self.overall_outcome!r}"
                )

            # D0102.4.2.1 D42-F01 Closure(§2A): status=SUCCESSの場合、
            # dimension_resultsは全8軸を過不足無く含む「完全な」検証結果
            # である必要がある(片手落ちのResultをSUCCESSとして構築
            # できてしまうと、次のAggregation Invariant Checkが誤った
            # 前提[欠落軸]の上で動いてしまう)。
            dimensions_present = {r.dimension for r in self.dimension_results}
            if dimensions_present != set(FaithfulnessDimension):
                missing = sorted(d.value for d in set(FaithfulnessDimension) - dimensions_present)
                raise FaithfulnessSchemaError(
                    f"status=SUCCESS の場合 dimension_results は全{len(FaithfulnessDimension)}軸を"
                    f"含む必要があります(欠落: {missing})"
                )

            # D0102.4.2.1 D42-F01 Closure(§2A): overall_outcomeは呼び出し側が
            # 自由に指定できるFieldではなく、dimension_resultsから既存の
            # 正準Aggregator(`_aggregate()`、Aggregation Logic自体は
            # 一切複製しない)で機械的に導出される値と厳密に一致しなければ
            # ならない。外部から与えられたoverall_outcomeを無条件に信頼
            # しない(SCOPE=AMBIGUOUSなのにACCEPT、NEGATION=FAILなのに
            # ACCEPT等のForged/Internally-Inconsistent Resultを構造的に
            # 拒否する)。
            expected_overall_outcome = _aggregate(self.dimension_results)
            if self.overall_outcome != expected_overall_outcome:
                raise FaithfulnessSchemaError(
                    f"overall_outcome({self.overall_outcome.value}) が dimension_results から導出される"
                    f"正しいAggregation結果({expected_overall_outcome.value})と一致しません"
                    "(Forged/Internally-Inconsistent Result、D0102.4.2.1 D42-F01 Closure)"
                )

            # D0102.4.2.1 D42-F01 Closure(§2B): MODEL Provenance双方向
            # Invariant。MODEL Checkが1件でもあれば`verification_
            # provenance`は必須(Model呼び出しの事実を証明できない
            # Forged Resultを拒否する)、逆にMODEL Checkが1件も無ければ
            # `verification_provenance`は必ずNone(D0102.4A修正4、既存
            # 挙動を維持)。
            has_model_dimension = any(r.checked_by == FaithfulnessCheckMethod.MODEL for r in self.dimension_results)
            if has_model_dimension and self.verification_provenance is None:
                raise FaithfulnessSchemaError(
                    "dimension_results に MODEL Checkが含まれるのに verification_provenance が None です"
                    "(D0102.4.2.1 D42-F01 Closure、Model-Assisted Checkの実施をAiDerivedProvenanceで"
                    "証明できないForged Resultを拒否する)"
                )
            if not has_model_dimension and self.verification_provenance is not None:
                raise FaithfulnessSchemaError(
                    "Model-assisted Checkが1件も無いのに verification_provenance が設定されています"
                    "(D0102.4A修正4、Deterministic-Onlyの場合は None である必要があります)"
                )
        elif self.overall_outcome is not None:
            raise FaithfulnessSchemaError(
                f"status={self.status.value} の場合 overall_outcome は必ず None である必要があります"
                "(D0102.4 §26/§33、Verificationが完走しなかったことを明示するため)"
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
    捏造しない」、AMBIGUOUSのみへ倒す)。

    D0102.4.2.1 D42-F03 Closure: 上書き後も`result.checked_by`をそのまま
    引き継ぐ(以前はDeterministic既定[`_dim()`の既定引数]に無条件で
    固定していたため、Model-Assisted Checkが`NOT_APPLICABLE`を返した
    必須軸を上書きした結果が誤って`checked_by=DETERMINISTIC`に
    Relabelされ、Model呼び出しの事実[Provenance整合性]がSilentに
    失われていた。判定の出所[Model-Assistedか否か]はOverride Rule
    自体の決定論性とは独立した情報であり、保持する)。Deterministic
    Pathでは`result.checked_by`は元々常にDETERMINISTICのため、この
    変更はDeterministic-Only挙動には一切影響しない。"""
    if result.outcome != FaithfulnessDimensionOutcome.NOT_APPLICABLE:
        return result
    required = _REQUIRED_DIMENSIONS_BY_CLAIM_TYPE.get(claim_type, frozenset())
    if result.dimension not in required:
        return result
    override_reason = _REQUIRED_OVERRIDE_REASON[result.dimension]
    return _dim(result.dimension, FaithfulnessDimensionOutcome.AMBIGUOUS, override_reason, checked_by=result.checked_by)


# ============================================================
# Direction Consistency(D0102.4A 修正1、PROPOSITION_IDENTITYの一部)
# ============================================================

# D0102.4A 修正1/D0102.4.1 §14: 意図的に小さいMarker語彙のみ(汎用日本語
# NLPを作らない)。「改善」は含めない(単体でINCREASEへ自動変換しない、
# D0102.4A明示要件)。
_INCREASE_MARKERS: tuple[str, ...] = ("増加", "増収", "上昇")
_DECREASE_MARKERS: tuple[str, ...] = ("減少", "減収", "低下")

# D0102.4.1.1 F04 Closure: 「増加した」だけでなく「増加しなかった」の
# ような否定接続もMarker文字列自体には含まれるため、単純なSubstring
# Searchでは否定形(Marker自体は逆方向を意味しない)を誤って肯定的な
# 方向Markerとして検出していた(例:「売上高は増加しなかった。」を
# `has_increase=True`と誤判定)。Marker直後にこれらの否定Suffixが続く
# 出現のみを除外する狭いChecker(汎用日本語NLPではなく、Marker語彙+
# 隣接する既知の否定活用形のみを見る決定論的Pattern)。
_NEGATED_MOVEMENT_SUFFIXES: tuple[str, ...] = ("しなかった", "しない", "しませんでした", "しません")


def _has_unnegated_marker(text: str, marker: str) -> bool:
    """`marker`が出現するが、直後に既知の否定Suffixが続く箇所は
    「その出現は否定されている」として除外する。少なくとも1件、
    否定されていない出現があれば`True`(D0102.4.1.1 F04)。"""
    start = 0
    while True:
        idx = text.find(marker, start)
        if idx == -1:
            return False
        after = text[idx + len(marker) :]
        if any(after.startswith(suffix) for suffix in _NEGATED_MOVEMENT_SUFFIXES):
            start = idx + len(marker)
            continue
        return True


class _MovementState(StrEnum):
    """D0102.4.1.2 F04 Closure: 旧`_explicit_movement_marker()`は「Marker
    無し」と「増加/減少Marker双方が存在(混在)」の2つの意味的に異なる
    状態をどちらも`None`へ Collapseしており、`direction=UNSPECIFIED`の
    候補に対してはどちらも同じ「Trivially一致(PASS)」経路へ落ちていた
    (混在Evidenceには実際にはDeterministicなProposition-to-Direction
    Bindingが存在しないにもかかわらず、Silent PASSしていた)。この内部
    専用State(新しいFaithfulnessDimensionは追加しない)で両状態を区別する。"""

    NONE = "NONE"
    INCREASE = "INCREASE"
    DECREASE = "DECREASE"
    MIXED = "MIXED"


def _movement_state(text: str) -> _MovementState:
    """Textから増減Markerの状態を検出する(否定形の出現は除外、F04
    Closure)。増加/減少Markerが両方存在する場合はMIXEDを返す(単一の
    明確なMarkerとしてCollapseしない、D0102.4.1.2)。"""
    has_increase = any(_has_unnegated_marker(text, marker) for marker in _INCREASE_MARKERS)
    has_decrease = any(_has_unnegated_marker(text, marker) for marker in _DECREASE_MARKERS)
    if has_increase and has_decrease:
        return _MovementState.MIXED
    if has_increase:
        return _MovementState.INCREASE
    if has_decrease:
        return _MovementState.DECREASE
    return _MovementState.NONE


def _check_direction_consistency(*, evidence_text: str, candidate: SemanticClaimCandidate) -> FaithfulnessDimensionResult:
    """D0102.4A 修正1: PROPOSITION_IDENTITYの一部としてDirection
    Consistencyを検証する(9番目のDimensionは追加しない)。"""
    movement = _movement_state(evidence_text)
    direction = candidate.direction

    if movement == _MovementState.INCREASE and direction == ClaimDirection.DECREASE:
        return _dim(
            FaithfulnessDimension.PROPOSITION_IDENTITY,
            FaithfulnessDimensionOutcome.FAIL,
            FaithfulnessReasonCode.DIRECTION_MISMATCH_DETECTED,
        )
    if movement == _MovementState.DECREASE and direction == ClaimDirection.INCREASE:
        return _dim(
            FaithfulnessDimension.PROPOSITION_IDENTITY,
            FaithfulnessDimensionOutcome.FAIL,
            FaithfulnessReasonCode.DIRECTION_MISMATCH_DETECTED,
        )
    if movement == _MovementState.MIXED:
        # D0102.4.1.2 F04 Closure: Evidenceに増加/減少Markerが両方存在する
        # =複数のMovement Propositionが同一Span内に混在しており、
        # Deterministic Subject-to-Direction Bindingが存在しない。
        # `candidate.direction`(UNSPECIFIED/INCREASE/DECREASEいずれでも)
        # によらず、Trivial PASSへ倒さずAMBIGUOUSへFail Closedする。
        return _dim(
            FaithfulnessDimension.PROPOSITION_IDENTITY,
            FaithfulnessDimensionOutcome.AMBIGUOUS,
            FaithfulnessReasonCode.DIRECTION_REQUIRES_SEMANTIC_REVIEW,
        )
    if movement != _MovementState.NONE and direction == ClaimDirection.UNSPECIFIED:
        return _dim(
            FaithfulnessDimension.PROPOSITION_IDENTITY,
            FaithfulnessDimensionOutcome.AMBIGUOUS,
            FaithfulnessReasonCode.DIRECTION_UNSPECIFIED_WITH_EXPLICIT_SOURCE,
        )
    if movement == _MovementState.NONE and direction in (ClaimDirection.INCREASE, ClaimDirection.DECREASE):
        return _dim(
            FaithfulnessDimension.PROPOSITION_IDENTITY,
            FaithfulnessDimensionOutcome.AMBIGUOUS,
            FaithfulnessReasonCode.DIRECTION_REQUIRES_SEMANTIC_REVIEW,
        )
    # movement == direction(両方Increase/Decreaseで一致)、または
    # 両方 NONE/UNSPECIFIED(いずれも主張なし)のいずれか——Trivially一致。
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
# D0102.4.1.1 F02 Closure: 旧Regexは負号として`△`のみを認識しており、
# ASCII/全角のMinus(`-`/`－`)がSign無しのまま数字の直前に現れると、
# Regex Engineがその負号を単に読み飛ばして残りの数字部分だけを
# 「符号無しの正の数量」として抽出していた(例:「-950億円」から符号を
# 落として`950億円`[正]を誤抽出、実際の値の符号を静かに破棄する
# Unsafe Partial Extraction)。`-`/`－`を`△`と同じSign文字として明示的に
# Pattern化し、かつ「認識済みのSign/数字文字の直後から始まるMatch」を
# 否定Lookbehindで拒否することで、認識できないPrefixを黙って読み飛ばして
# 部分一致することを構造的に防ぐ(Match全体が失敗すれば、後段の
# `_try_parse_quantity()`が`None`を返し、Ambiguous経路[§16「Never
# silently discard unparsed numeric text」]で扱われる)。
_QUANTITY_SIGN_CHARS = "△\\-－"
# D0102.4.1 §15: Percent/円/台で終わる「数量らしい部分文字列」を検出する
# 粗いSpan(この後 _try_parse_quantity() で厳密Parseする)。
_QUANTITY_SPAN_RE = re.compile(
    rf"(?<![0-9{_QUANTITY_SIGN_CHARS}])[{_QUANTITY_SIGN_CHARS}]?"
    r"(?:[0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?(?:兆|億|万|千)?)+(?:%|％|円|台)"
)

# D0102.4.1.2 F02 Closure(§3A/§3B、Unsafe Partial Numeric Extraction Guard):
# 上記`_QUANTITY_SPAN_RE`(厳密Parser用)はComma区切りが厳密に3桁でない・
# 全角数字・未対応Scale Kanji(百/十等)を含むMalformed Numeric Textに対して
# Regex Engineが内部から部分一致してしまう(例:「1,23円」で先頭の「1,」を
# 黙って読み飛ばし「23円」だけを一致させる)。この`_NUMERIC_LOOKING_SPAN_RE`
# は同じLeading Sign/Unit Suffix構造を維持しつつ、本文字列(桁区切り・
# 小数点・未対応Scale Kanjiも含む)をより緩いCharacter Classで検出する
# 「数量らしいSpan全体」検出専用Regexである(値のParseは一切行わない、
# 検出専用)。この緩いSpanが厳密Parserの一致Spanと完全一致しない場合、
# その数値らしいTextの一部がSilentに読み飛ばされたことを意味する
# (`_has_unparsed_numeric_content()`参照、汎用Locale数値Parserは実装しない)。
_NUMERIC_LOOKING_CONTINUATION_CHARS = f"0-9０-９{_QUANTITY_SIGN_CHARS}，,"
_NUMERIC_LOOKING_BODY_CHARS = "0-9０-９，,．.兆億万千百十"
_NUMERIC_LOOKING_SPAN_RE = re.compile(
    rf"(?<![{_NUMERIC_LOOKING_CONTINUATION_CHARS}])[{_QUANTITY_SIGN_CHARS}]?"
    rf"[0-9０-９][{_NUMERIC_LOOKING_BODY_CHARS}]*(?:%|％|円|台)"
)


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
    if body[:1] in ("△", "-", "－"):
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


def _has_unparsed_numeric_content(text: str) -> bool:
    """D0102.4.1.2 F02 Closure(§3A): `_NUMERIC_LOOKING_SPAN_RE`(緩い検出用)
    が見つけた「数量らしいSpan」のうち、厳密`_QUANTITY_SPAN_RE`+
    `_try_parse_quantity()`が**全く同じSpan**を安全にParseできていない
    ものが1件でもあれば`True`を返す。Malformed Comma区切り(`1,23円`)・
    全角数字(`４.０％`)・未対応Scale Kanji(`3百万円`)のいずれも、
    厳密Parserが部分一致で「一部だけ」を信頼できる数量として扱うことを
    防ぐ(Silent Partial Extraction/Silent Disappearをどちらも禁止する、
    汎用Locale数値Parserは実装しない)。"""
    strict_spans = {(m.start(), m.end()) for m in _QUANTITY_SPAN_RE.finditer(text) if _try_parse_quantity(m.group(0)) is not None}
    return any((m.start(), m.end()) not in strict_spans for m in _NUMERIC_LOOKING_SPAN_RE.finditer(text))


def _match_quantity_against_evidence(
    candidate_q: _ParsedQuantity, evidence_parsed: list[_ParsedQuantity]
) -> tuple[FaithfulnessDimensionOutcome, FaithfulnessReasonCode]:
    """候補の数量1件をEvidence中の数量群と比較する。

    D0102.4.1.1 F03 Closure(Cross-Proposition Quantity Borrowing):
    Evidenceが同一Category(単位/Percent種別)内に複数の異なる値を含む
    場合(例:「売上高は4.0%増加し、営業利益は12.0%減少した。」)、
    候補の値がそのうちの1件と一致しているだけでは、その数字が実際に
    候補のPropositionに属するものか(=正しい数値をBorrowしたのではなく
    別の数値を無断でBorrowしていないか)をDeterministicには確認できない。
    このため、同一Category内に**複数の異なる値**が存在する場合は、値が
    一致していても`AMBIGUOUS`(Semantic Verification必須)へ倒す。
    Category内の値が単一(または全て同一)であれば、一致は曖昧さなく
    `PASS`にできる。
    """
    same_category = [e for e in evidence_parsed if e.is_percent == candidate_q.is_percent and e.unit == candidate_q.unit]
    distinct_same_category_values = {e.value for e in same_category}
    for e in same_category:
        if e.value == candidate_q.value:
            if len(distinct_same_category_values) > 1:
                return FaithfulnessDimensionOutcome.AMBIGUOUS, FaithfulnessReasonCode.SEMANTIC_VERIFICATION_REQUIRED
            return FaithfulnessDimensionOutcome.PASS, FaithfulnessReasonCode.NO_ISSUE_DETECTED
    for e in same_category:
        if abs(e.value) == abs(candidate_q.value):
            return FaithfulnessDimensionOutcome.FAIL, FaithfulnessReasonCode.QUANTITY_SIGN_MISMATCH
    if same_category:
        return FaithfulnessDimensionOutcome.FAIL, FaithfulnessReasonCode.QUANTITY_VALUE_MISMATCH
    for e in evidence_parsed:
        if e.value == candidate_q.value:
            return FaithfulnessDimensionOutcome.FAIL, FaithfulnessReasonCode.QUANTITY_UNIT_MISMATCH
    return FaithfulnessDimensionOutcome.FAIL, FaithfulnessReasonCode.QUANTITY_INVENTED


def _check_quantity(*, evidence_text: str, candidate: SemanticClaimCandidate) -> FaithfulnessDimensionResult:
    evidence_tokens = _find_quantities(evidence_text)
    candidate_tokens = _find_quantities(candidate.normalized_claim_text)
    # D0102.4.1.2 F02 Closure(§3A): 厳密Tokenとは別に、緩い検出で
    # 見つかった数量らしいSpanが厳密Parserで完全にCoverされていない
    # 箇所(Malformed Comma区切り・全角数字・未対応Scale Kanji等)が
    # Evidence/Candidateのどちらかに存在するかを独立して判定する。
    has_unparsed_numeric = _has_unparsed_numeric_content(evidence_text) or _has_unparsed_numeric_content(
        candidate.normalized_claim_text
    )

    if not evidence_tokens and not candidate_tokens:
        if has_unparsed_numeric:
            return _dim(
                FaithfulnessDimension.QUANTITY,
                FaithfulnessDimensionOutcome.AMBIGUOUS,
                FaithfulnessReasonCode.UNPARSED_NUMERIC_CONTENT,
            )
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
    token_results = []
    for cq in candidate_tokens:
        assert cq is not None  # noqa: S101 -- 直前のAny(None)Checkで既に排除済み(mypy Narrowing用)
        token_results.append(_match_quantity_against_evidence(cq, evidence_parsed))

    # FAILがAMBIGUOUSより優先(D0102.4 §15 Deterministic Hard-Fail
    # Precedenceの精神をDimension内部の複数Token集約にも一貫適用する)。
    for outcome, reason in token_results:
        if outcome == FaithfulnessDimensionOutcome.FAIL:
            return _dim(FaithfulnessDimension.QUANTITY, FaithfulnessDimensionOutcome.FAIL, reason)

    # D0102.4.1.2 F02 Closure(§3A): 認識できたTokenが偶然一致していても、
    # 同じEvidence/Candidate中にParseしきれなかった数量らしいTextが
    # 残っている場合、それを黙って無視してPASSへ倒さない(Unsafe Partial
    # Extraction、FAIL Precedenceの直後・既存AMBIGUOUS集約の直前に置く)。
    if has_unparsed_numeric:
        return _dim(
            FaithfulnessDimension.QUANTITY,
            FaithfulnessDimensionOutcome.AMBIGUOUS,
            FaithfulnessReasonCode.UNPARSED_NUMERIC_CONTENT,
        )

    for outcome, reason in token_results:
        if outcome == FaithfulnessDimensionOutcome.AMBIGUOUS:
            return _dim(FaithfulnessDimension.QUANTITY, FaithfulnessDimensionOutcome.AMBIGUOUS, reason)

    return _dim(FaithfulnessDimension.QUANTITY, FaithfulnessDimensionOutcome.PASS, FaithfulnessReasonCode.NO_ISSUE_DETECTED)


# ============================================================
# Negation(D0102.4.1 §17)
# ============================================================

# D0102.4.1.1 F01 Closure: 短いMarker(`ない`)が長いMarker(`変更はない`/
# `認められない`)の部分文字列であるため、単純な`str.count()`合算は同一の
# 実際の否定表現を2重にCountしていた(例:「重要な変更はない。」は`ない`と
# `変更はない`の両方に一致し、実際には1件の否定しか無いのにCount=2となり
# 誤ってNEGATION_AMBIGUOUSへ倒れていた)。より長いMarkerを先に試す1本の
# 結合Regex + `finditer()`(Non-Overlapping Match)へ置き換え、同一箇所の
# 二重Countを構造的に防ぐ。
_NEGATION_MARKERS: tuple[str, ...] = ("ない", "ありません", "なかった", "認められない", "変更はない")
_NEGATION_MARKER_RE = re.compile("|".join(re.escape(m) for m in sorted(_NEGATION_MARKERS, key=len, reverse=True)))


def _negation_marker_count(text: str) -> int:
    return len(_NEGATION_MARKER_RE.findall(text))


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


def _temporal_ranks_present(text: str) -> frozenset[int]:
    """D0102.4.1.1 F05 Closure(Multi-Temporal False Rejection):
    旧実装は最初に一致したCategoryのみを返しており、EvidenceがHISTORICAL
    とFUTURE双方のMarkerを同時に含む(例:「当中間連結会計期間の実績を
    踏まえ、今後も同様の傾向が続く見通しである。」のような、実績報告+
    先行き言及が同一Text内に共存する一般的なPattern)場合に、実際には
    Evidence自身がFUTURE言及も含んでいるにもかかわらず、Candidateの
    FUTURE言及がHISTORICALとのRank不一致として誤ってFAIL(False
    Rejection)していた。Textに現れる**全ての**Rankを集合として返し、
    呼び出し側でRank集合同士のIntersectionによって判定する(単一
    Categoryへの安易な収斂をやめる、汎用NLPは追加しない——既存Marker
    Listをそのまま複数一致させるのみ)。"""
    return frozenset(_TEMPORAL_RANK[category] for category, marker in _TEMPORAL_CATEGORY_MARKERS if marker in text)


# D0102.4.1.2 F05 Closure(§5B): 句点(。)のみを安全な境界として使う
# Conservative Sentence-Level Split(依存構造解析・汎用日本語NLPは実装
# しない)。句点の直後で分割し、句点自体は直前のClauseへ残す。
_CLAUSE_SPLIT_RE = re.compile(r"(?<=。)")


def _split_into_clauses(text: str) -> list[str]:
    parts = [p for p in _CLAUSE_SPLIT_RE.split(text) if p]
    return parts if parts else [text]


def _find_containing_clause(*, evidence_text: str, candidate_text: str) -> str | None:
    """D0102.4.1.2 F05 Closure(§5B)で導入、D0102.4.2 §13でCERTAINTY_AND_
    COMMITMENTのModel-Routing判定にも再利用する共有Boundary Helper。
    `candidate_text`が Evidence の単一Sentence-Level Clause内に文字通り
    Containされている場合、そのClauseを返す(既存`in`によるExact
    Substring Containment、他Dimension[PROPOSITION_IDENTITY等]と同じ
    機構の再利用、独自のFuzzy/数値内部開始判定は行わない)。見つからない
    場合は`None`(Local Bindingが証明できないことを表す)。"""
    if not candidate_text:
        return None
    for clause in _split_into_clauses(evidence_text):
        if candidate_text in clause:
            return clause
    return None


def _locally_bound_temporal_ranks(*, evidence_text: str, candidate_text: str) -> frozenset[int] | None:
    """D0102.4.1.2 F05 Closure(§5B、Temporal Borrowing対策): Candidateが
    単一Clauseへ安全にLocal Bindingできる場合のみ、そのClause内
    (Evidence全体ではない)のTemporal Rankを返す。Local Bindingが証明
    できない場合は`None`を返し、呼び出し側でAMBIGUOUSへFail Closedする
    (無関係なClauseからのMarker借用を構造的に禁止する)。"""
    clause = _find_containing_clause(evidence_text=evidence_text, candidate_text=candidate_text)
    if clause is None:
        return None
    return _temporal_ranks_present(clause)


def _check_temporal_scope(*, evidence_text: str, candidate: SemanticClaimCandidate) -> FaithfulnessDimensionResult:
    candidate_text = candidate.normalized_claim_text
    evidence_ranks = _temporal_ranks_present(evidence_text)
    candidate_ranks = _temporal_ranks_present(candidate_text)

    if not evidence_ranks and not candidate_ranks:
        return _dim(
            FaithfulnessDimension.TEMPORAL_SCOPE,
            FaithfulnessDimensionOutcome.NOT_APPLICABLE,
            FaithfulnessReasonCode.NOT_APPLICABLE_NO_RELEVANT_CONTENT,
        )
    if not evidence_ranks or not candidate_ranks:
        return _dim(
            FaithfulnessDimension.TEMPORAL_SCOPE,
            FaithfulnessDimensionOutcome.AMBIGUOUS,
            FaithfulnessReasonCode.TEMPORAL_REQUIRES_SEMANTIC_REVIEW,
        )
    if not (evidence_ranks & candidate_ranks):
        return _dim(
            FaithfulnessDimension.TEMPORAL_SCOPE,
            FaithfulnessDimensionOutcome.FAIL,
            FaithfulnessReasonCode.TEMPORAL_CATEGORY_MISMATCH,
        )

    # D0102.4.1.2 F05 Closure(§5A、PRESENCE_IS_NOT_PROPOSITION_BINDING):
    # EvidenceにTemporal Categoryが複数存在する場合、全体Intersectionが
    # 非空というだけでは「Candidateが主張するTemporal Scopeが実際に
    # 無関係な別Propositionの Marker を借用しているだけではないか」を
    # 排除できない。この場合はClause-Local Bindingが証明できた場合のみ
    # PASSする(証明できなければAMBIGUOUS、Borrowを禁止する)。
    if len(evidence_ranks) > 1:
        local_ranks = _locally_bound_temporal_ranks(evidence_text=evidence_text, candidate_text=candidate_text)
        if local_ranks is None or not (local_ranks & candidate_ranks):
            return _dim(
                FaithfulnessDimension.TEMPORAL_SCOPE,
                FaithfulnessDimensionOutcome.AMBIGUOUS,
                FaithfulnessReasonCode.TEMPORAL_REQUIRES_SEMANTIC_REVIEW,
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
        # Deterministic以外(Model-Only FAIL)のSoft Dimension FAIL。
        # D0102.4.1ではModelを使わないため到達しなかったが、D0102.4.2の
        # Model-Assisted Verification経路では実際に到達しうる
        # (`verify_candidate_faithfulness()`参照、Model単独のFAILは
        # REJECTではなくREVIEW_REQUIREDに留める、Aggregation Rule自体は
        # 本Roundでも無変更)。
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


# ============================================================
# D0102.4.2 — Model-Assisted Verification(FaithfulnessVerifier Protocol)
#
# `verify_candidate_deterministically()`(上記)は本Roundでも一切
# 変更しない。ここから下は、Deterministic Checksが`AMBIGUOUS`のまま
# 残した軸のみをModel-Assisted Verifierへ委ねる、別の公開Entrypoint
# (`verify_candidate_faithfulness()`)を追加する(D0102.4/D0102.4A
# `READY_FOR_IMPLEMENTATION`)。`MODEL_CALL_SITES`は本Module内では
# `FaithfulnessVerifier.verify()`のCall Site 1箇所のみであり、Vendor
# SDK・実Network呼び出しは一切含まない。
# ============================================================


@dataclass(kw_only=True, frozen=True)
class FaithfulnessVerifierInput:
    """D0102.4 §12: Model-Assisted Verifierへ渡す入力のNarrow Allowlist
    (`candidate`/`evidence_span`をそのまま丸ごと渡さない)。Ticker・
    企業名・市場価格・Valuation・Bull/Base/Bear・期待Return・投資
    Thesis・外部News・EvidenceSpanのIdentity Field(document_id等)、
    いずれも含めない——この5 Fieldのみが唯一のAuthoritative Input。"""

    claim_type: SemanticClaimType
    normalized_claim_text: str
    direction: ClaimDirection
    supporting_quote: str
    taxonomy_element_name: str

    def __post_init__(self) -> None:
        if not isinstance(self.claim_type, SemanticClaimType):
            raise FaithfulnessSchemaError(f"claim_type は SemanticClaimType である必要があります: {self.claim_type!r}")
        if not isinstance(self.direction, ClaimDirection):
            raise FaithfulnessSchemaError(f"direction は ClaimDirection である必要があります: {self.direction!r}")
        if not isinstance(self.normalized_claim_text, str) or not self.normalized_claim_text:
            raise FaithfulnessSchemaError("normalized_claim_text は空でないstrである必要があります")
        if not isinstance(self.supporting_quote, str) or not self.supporting_quote:
            raise FaithfulnessSchemaError("supporting_quote は空でないstrである必要があります")
        if not isinstance(self.taxonomy_element_name, str) or not self.taxonomy_element_name:
            raise FaithfulnessSchemaError("taxonomy_element_name は空でないstrである必要があります")


class FaithfulnessVerifier(Protocol):
    """D0102.4 §11: Vendor SDKへ直接結合しない、最小限のNarrow
    Protocol(`CandidateExtractionModel`と同型のAdapter Injection
    Pattern)。実装(Production Adapter・Test用Fake、いずれも同じ形)は
    `verifier_input`のみを入力として受け取り、Model Output Contract
    検証前のRaw構造化出力(通常`dict`)を返す——Schema検証自体は呼び出し
    側(`verify_candidate_faithfulness()`)が一元的に行う。"""

    def verify(self, *, verifier_input: FaithfulnessVerifierInput) -> object:
        """`verifier_input`はNarrow Allowlist Fieldのみを持つ(上記
        `FaithfulnessVerifierInput`参照)。実装はこの引数以外のいかなる
        情報(他のTextBlock・後続Filing・市場データ・外部知識)にも
        Accessすべきではない(PIT Safety、`CandidateExtractionModel`と
        同じ制約)。"""
        ...


# D0102.4 §4: QUANTITY/NEGATIONはDeterministic中心の軸であり、本Round
# でもModelへ送らない(既にDeterministicにHard-Fail/Ambiguousを判定
# できる、Marker Word Listで十分)。残り6軸のみがModel-Assisted Check
# の対象になりうる。
_MODEL_ROUTABLE_DIMENSIONS: frozenset[FaithfulnessDimension] = frozenset(
    {
        FaithfulnessDimension.PROPOSITION_IDENTITY,
        FaithfulnessDimension.SUBJECT_ATTRIBUTION,
        FaithfulnessDimension.SCOPE,
        FaithfulnessDimension.CAUSAL_STRENGTH,
        FaithfulnessDimension.CERTAINTY_AND_COMMITMENT,
        FaithfulnessDimension.TEMPORAL_SCOPE,
    }
)


def _certainty_requires_model_routing(*, evidence_text: str, candidate_text: str) -> bool:
    """D0102.4.2 §13(D0102.4.1.2で記録したResidual Riskの解消):
    `_check_certainty_and_commitment()`(Frozen、無変更)はEvidence
    全体からEpistemic/Commitment Markerを走査しており、Evidenceが
    複数Clauseを含む場合、検出したMarkerが実際にはCandidateの
    Propositionとは無関係な別Clauseに属する可能性を排除できない
    (PRESENCE_IS_NOT_PROPOSITION_BINDING = TRUE、TEMPORAL_SCOPEの
    F05 Closureと同種のRisk)。汎用日本語NLPを追加する代わりに、既存の
    Clause分割+Exact Substring Containment Helper(`_find_containing_
    clause()`)を再利用し、「Evidenceが複数Clauseを含み、かつCandidateが
    単一Clauseへ安全にLocal Bindingできない」場合のみ、Deterministic
    結果(PASS/FAILいずれでも)をModel-Assisted Verificationが必要な
    Unresolved Dimensionとして扱う。`_check_certainty_and_commitment()`
    自体は一切変更しない(`verify_candidate_deterministically()`の
    挙動は無変更のまま)。"""
    if len(_split_into_clauses(evidence_text)) <= 1:
        return False
    return _find_containing_clause(evidence_text=evidence_text, candidate_text=candidate_text) is None


def _is_proper_substring_quote(*, normalized_claim_text: str, evidence_text: str) -> bool:
    """D0102.4.2 §11(SCOPE Qualifier-Drop Detection、D0102 §24の既存
    懸念「北米事業限定を落とした一般化はSilent ACCEPT禁止」への対応):
    `_check_scope()`(Frozen、無変更)はCandidate TextがEvidence Textの
    厳密な部分文字列であれば無条件にTrivial PASSする。しかし**完全
    一致ではない**部分文字列一致は、先頭/末尾のScope修飾語(地域・
    Segment・連結/単独等)をSilentに落としている可能性を構造的に排除
    できない——完全一致(Verbatim Quote全体)はQualifierを一切落とし
    得ないため区別する。"""
    return normalized_claim_text != evidence_text and normalized_claim_text in evidence_text


def _determine_model_required_dimensions(
    deterministic_results: tuple[FaithfulnessDimensionResult, ...],
    *,
    evidence_text: str,
    candidate: SemanticClaimCandidate,
) -> frozenset[FaithfulnessDimension]:
    """D0102.4 §32「When Model Verification Required」: Deterministic
    Checksが`AMBIGUOUS`のまま残した`_MODEL_ROUTABLE_DIMENSIONS`のみを
    収集する。追加で(a)CERTAINTY_AND_COMMITMENTがPASSの場合のみ
    `_certainty_requires_model_routing()`のProposition-Binding判定を
    適用する(§13)、(b)SCOPEは`_check_scope()`が完全一致ではない部分
    文字列一致でTrivial PASSした場合でも、Qualifier脱落の可能性を
    排除するためModel-Assisted Verificationへ回す(§11)。

    D0102.4.2.1 D42-F02 Closure(DETERMINISTIC_HARD_FAIL_PRECEDENCE /
    DETERMINISTIC_SOFT_FAIL_PRECEDENCE): 既に確立したDeterministic
    `FAIL`は、いかなる追加TriggerによってもModel-Replaceable対象へ
    絶対に含めない。個々のSpecial Trigger(Certainty Local-Binding・
    Scope Qualifier-Drop等)がこの制約を各自Reimplementするのではなく、
    末尾で`FAIL`を一括除外する1本のExplicit Guardとして強制する
    (将来のTriggerが追加されてもこの不変条件を独立に守る必要が無い)。
    """
    by_dimension = {r.dimension: r for r in deterministic_results}
    required = {
        dimension
        for dimension in _MODEL_ROUTABLE_DIMENSIONS
        if by_dimension[dimension].outcome == FaithfulnessDimensionOutcome.AMBIGUOUS
    }
    certainty_result = by_dimension[FaithfulnessDimension.CERTAINTY_AND_COMMITMENT]
    if certainty_result.outcome == FaithfulnessDimensionOutcome.PASS and _certainty_requires_model_routing(
        evidence_text=evidence_text, candidate_text=candidate.normalized_claim_text
    ):
        required.add(FaithfulnessDimension.CERTAINTY_AND_COMMITMENT)
    scope_result = by_dimension[FaithfulnessDimension.SCOPE]
    if scope_result.outcome == FaithfulnessDimensionOutcome.PASS and _is_proper_substring_quote(
        normalized_claim_text=candidate.normalized_claim_text, evidence_text=evidence_text
    ):
        required.add(FaithfulnessDimension.SCOPE)

    # D42-F02 Explicit Guard: 上記いずれのTriggerを経由したかに関わらず、
    # Deterministic FAILが確立している軸は最終的に一切Model-Required
    # 対象へ含めない(Defense in Depth、単一の強制Point)。
    required = {dimension for dimension in required if by_dimension[dimension].outcome != FaithfulnessDimensionOutcome.FAIL}
    return frozenset(required)


# D0102 §22/D0102.4.2 §9: PROPOSITION_IDENTITYのParaphrase Equivalenceは
# Model単独のPASS宣言を最終権威にしない。この極小の事前承認済みPair
# Table(正規化Claim Text, Evidence Supporting Quote)に含まれる場合のみ
# Deterministicに Ratify する——v1は意図的に極小(Toyota Acceptance
# Fixture Case B専用の1件のみ)、汎用Ontologyは構築しない。未収載の
# Pairは常にAMBIGUOUSへ倒れ、Silent ACCEPTは発生しない。
_APPROVED_PROPOSITION_PARAPHRASES: frozenset[tuple[str, str]] = frozenset(
    {
        ("海外事業の販売が伸びた可能性がある。", "海外事業の販売が拡大した可能性がある。"),
    }
)


def _is_approved_proposition_paraphrase(*, normalized_claim_text: str, supporting_quote: str) -> bool:
    return (normalized_claim_text, supporting_quote) in _APPROVED_PROPOSITION_PARAPHRASES


# D0102.4 §14: Model Output Contractの許可Key集合(過不足を許さない、
# これ以外のKeyが1つでもあればResponse全体をReject——Confidence Score・
# Rewritten Claim・Summary・投資Sentiment・Source Identity Field等は
# 構造的に受理不可能)。
_VERIFIER_ALLOWED_TOP_LEVEL_KEYS: frozenset[str] = frozenset({"dimensions"})
_VERIFIER_ALLOWED_ITEM_KEYS: frozenset[str] = frozenset({"dimension", "outcome", "reason_code"})


def _is_string_keyed_mapping(value: object) -> bool:
    """D0102.3.2 F02と同型の防御的Check: `sorted()`/`set()`等でKeyを
    比較する前に、全Keyがstrであることを必ず先に確認する。"""
    return isinstance(value, dict) and all(isinstance(key, str) for key in value.keys())


def _validate_verifier_response(
    raw_response: object,
    *,
    requested_dimensions: frozenset[FaithfulnessDimension],
) -> tuple[tuple[FaithfulnessDimensionResult, ...] | None, str | None]:
    """D0102.4 §14: `candidate_extraction.py`と同型のWhole-Response-
    Fatal判定(Candidate単位のSkipではない、1件でも契約違反があれば
    Response全体を拒否する)。成功時は`(results, None)`、失敗時は
    `(None, reason)`を返す。"""
    if not _is_string_keyed_mapping(raw_response):
        return None, "response is not a string-keyed JSON object"
    assert isinstance(raw_response, dict)  # noqa: S101 -- 直前のCheckで既に確認済み(mypy Narrowing用)
    if set(raw_response.keys()) != _VERIFIER_ALLOWED_TOP_LEVEL_KEYS:
        return None, f"unexpected top-level keys: {sorted(raw_response.keys())}"

    raw_items = raw_response["dimensions"]
    if not isinstance(raw_items, list):
        return None, "'dimensions' is not a list"

    seen: set[FaithfulnessDimension] = set()
    results: list[FaithfulnessDimensionResult] = []
    for raw_item in raw_items:
        if not _is_string_keyed_mapping(raw_item):
            return None, "dimension entry is not a string-keyed JSON object"
        assert isinstance(raw_item, dict)  # noqa: S101 -- 直前のCheckで既に確認済み(mypy Narrowing用)
        if set(raw_item.keys()) != _VERIFIER_ALLOWED_ITEM_KEYS:
            return None, f"dimension entry has unexpected keys: {sorted(raw_item.keys())}"

        dimension_raw = raw_item["dimension"]
        outcome_raw = raw_item["outcome"]
        reason_code_raw = raw_item["reason_code"]
        if not isinstance(dimension_raw, str) or not isinstance(outcome_raw, str) or not isinstance(reason_code_raw, str):
            return None, "dimension entry field(s) are not strings"

        try:
            dimension = FaithfulnessDimension(dimension_raw)
        except ValueError:
            return None, f"unknown dimension: {dimension_raw!r}"
        try:
            outcome = FaithfulnessDimensionOutcome(outcome_raw)
        except ValueError:
            return None, f"unknown outcome: {outcome_raw!r}"
        try:
            reason_code = FaithfulnessReasonCode(reason_code_raw)
        except ValueError:
            return None, f"unknown reason_code: {reason_code_raw!r}"

        if dimension not in requested_dimensions:
            return None, f"unrequested dimension in response: {dimension.value}"
        if dimension in seen:
            return None, f"duplicate dimension in response: {dimension.value}"
        seen.add(dimension)

        try:
            results.append(
                FaithfulnessDimensionResult(
                    dimension=dimension,
                    outcome=outcome,
                    reason_code=reason_code,
                    checked_by=FaithfulnessCheckMethod.MODEL,
                )
            )
        except FaithfulnessSchemaError as exc:
            # 例: NOT_APPLICABLEを許可しないDimension(PROPOSITION_IDENTITY等)に
            # ModelがNOT_APPLICABLEを返した場合、ここでReject する。
            return None, str(exc)

    missing = requested_dimensions - seen
    if missing:
        return None, f"missing requested dimension(s): {sorted(d.value for d in missing)}"

    return tuple(results), None


def _merge_deterministic_and_model(
    deterministic_results: tuple[FaithfulnessDimensionResult, ...],
    model_results: tuple[FaithfulnessDimensionResult, ...],
    *,
    candidate: SemanticClaimCandidate,
    evidence_text: str,
) -> tuple[FaithfulnessDimensionResult, ...]:
    """D0102.4 §15: Deterministic結果を破棄しない——Model-Requiredだった
    軸のみを置き換える(既存の`PASS`/`FAIL`/`NOT_APPLICABLE`はそのまま
    保持する)。PROPOSITION_IDENTITYのModel PASSのみ、事前承認済み
    Paraphrase Pair Tableで Ratify できない限り`AMBIGUOUS`へ格下げする
    (§9、Model単独のPASS宣言を最終権威にしない)。"""
    model_by_dimension = {r.dimension: r for r in model_results}

    proposition_result = model_by_dimension.get(FaithfulnessDimension.PROPOSITION_IDENTITY)
    if proposition_result is not None and proposition_result.outcome == FaithfulnessDimensionOutcome.PASS:
        if _is_approved_proposition_paraphrase(
            normalized_claim_text=candidate.normalized_claim_text, supporting_quote=evidence_text
        ):
            model_by_dimension[FaithfulnessDimension.PROPOSITION_IDENTITY] = _dim(
                FaithfulnessDimension.PROPOSITION_IDENTITY,
                FaithfulnessDimensionOutcome.PASS,
                FaithfulnessReasonCode.PARAPHRASE_EQUIVALENT_CONFIRMED,
                checked_by=FaithfulnessCheckMethod.MODEL,
            )
        else:
            model_by_dimension[FaithfulnessDimension.PROPOSITION_IDENTITY] = _dim(
                FaithfulnessDimension.PROPOSITION_IDENTITY,
                FaithfulnessDimensionOutcome.AMBIGUOUS,
                FaithfulnessReasonCode.SEMANTIC_VERIFICATION_REQUIRED,
                checked_by=FaithfulnessCheckMethod.MODEL,
            )

    return tuple(model_by_dimension.get(r.dimension, r) for r in deterministic_results)


def verify_candidate_faithfulness(
    *,
    candidate: object,
    document: NormalizedDisclosureDocument,
    verifier: FaithfulnessVerifier,
    model_provider: str,
    model_name: str,
    model_version: str | None = None,
    prompt_version: str | None = None,
    prompt_hash: str,
    verification_version: str = MODEL_ASSISTED_FAITHFULNESS_VERSION,
    verified_at: datetime,
) -> FaithfulnessVerificationResult:
    """D0102.4.2の公開Entrypoint。Deterministic Checks(`verify_
    candidate_deterministically()`と同じ8軸Logicを内部関数経由で再利用、
    そちら自体は一切変更しない)を実行した上で、AMBIGUOUSのまま残った
    軸のみを`FaithfulnessVerifier`へ委ねる。Deterministic Hard-Fail
    (PROPOSITION_IDENTITY/SUBJECT_ATTRIBUTION/NEGATION/QUANTITY)が
    既に確定していればModel呼び出しをSkipする(§37コスト最適化、Model
    PASSがDeterministic FAILを上書きすることは構造的に無い)。

    `model_provider`/`model_name`/`prompt_hash`は`extract_candidates()`
    と同型のCaller Contract(呼び出し側がModelにVersioningを自己申告
    させず、常に明示指定する、D0102.3 §16と同じ方針)。
    """
    if not prompt_hash:
        raise FaithfulnessSchemaError("prompt_hash は空にできません(D0102.4.2、Verifierの決定論的Versioningが必須)")

    # Candidate Integrity Gate(既存`verify_candidate_deterministically()`と同型)。
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

    # Source Revalidation Gate(Verification開始直後、既存と同型)。
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
    deterministic_results = _run_all_dimension_checks(evidence_text=evidence_text, candidate=candidate)
    by_dimension = {r.dimension: r for r in deterministic_results}

    # Hard-Fail軸が既にDeterministic FAIL確定 → Model呼び出しをSkipして
    # Overall=REJECT(§37コスト最適化、DETERMINISTIC_HARD_FAIL > MODEL_PASS)。
    if any(by_dimension[dimension].outcome == FaithfulnessDimensionOutcome.FAIL for dimension in _HARD_FAIL_DIMENSIONS):
        return FaithfulnessVerificationResult(
            status=FaithfulnessVerificationStatus.SUCCESS,
            overall_outcome=_aggregate(deterministic_results),
            dimension_results=deterministic_results,
            candidate_reference=candidate_reference,
            verification_version=verification_version,
            verified_at=verified_at,
            verification_provenance=None,
        )

    model_required = _determine_model_required_dimensions(deterministic_results, evidence_text=evidence_text, candidate=candidate)

    if not model_required:
        # 全軸がDeterministicに解決済み(Exact Match等)——Model呼び出し不要。
        return FaithfulnessVerificationResult(
            status=FaithfulnessVerificationStatus.SUCCESS,
            overall_outcome=_aggregate(deterministic_results),
            dimension_results=deterministic_results,
            candidate_reference=candidate_reference,
            verification_version=verification_version,
            verified_at=verified_at,
            verification_provenance=None,
        )

    # D0102.4 §9: Model呼び出し「直前」に再度Revalidationを必須実行する
    # (上記のGateから時間が経過していなくても、Contractとして毎回明示的に
    # 再確認する——Extraction時点/Gate通過時点のValidationを信頼しない)。
    try:
        pre_model_revalidation = revalidate_evidence_span(candidate.evidence_span, document=document)
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
    if pre_model_revalidation != RevalidationResult.VALID:
        return FaithfulnessVerificationResult(
            status=FaithfulnessVerificationStatus.SOURCE_REVALIDATION_FAILED,
            overall_outcome=None,
            dimension_results=(),
            candidate_reference=candidate_reference,
            verification_version=verification_version,
            verified_at=verified_at,
            verification_provenance=None,
            reason=f"pre-model revalidation result={pre_model_revalidation.value}",
        )

    verifier_input = FaithfulnessVerifierInput(
        claim_type=candidate.claim_type,
        normalized_claim_text=candidate.normalized_claim_text,
        direction=candidate.direction,
        supporting_quote=candidate.evidence_span.supporting_quote,
        taxonomy_element_name=candidate.evidence_span.taxonomy_element_name,
    )

    try:
        raw_response = verifier.verify(verifier_input=verifier_input)
    except Exception as exc:
        # D0102.3.2 §18と同型: Vendor SDKの生Exception文言をそのまま
        # reasonへ保存しない。Exception種別名のみを記録する。
        return FaithfulnessVerificationResult(
            status=FaithfulnessVerificationStatus.VERIFIER_ERROR,
            overall_outcome=None,
            dimension_results=(),
            candidate_reference=candidate_reference,
            verification_version=verification_version,
            verified_at=verified_at,
            verification_provenance=None,
            reason=f"verifier raised {type(exc).__name__}",
        )

    model_results, contract_violation_reason = _validate_verifier_response(raw_response, requested_dimensions=model_required)
    if model_results is None:
        return FaithfulnessVerificationResult(
            status=FaithfulnessVerificationStatus.VERIFIER_CONTRACT_VIOLATION,
            overall_outcome=None,
            dimension_results=(),
            candidate_reference=candidate_reference,
            verification_version=verification_version,
            verified_at=verified_at,
            verification_provenance=None,
            reason=contract_violation_reason,
        )

    merged_results = _merge_deterministic_and_model(
        deterministic_results, model_results, candidate=candidate, evidence_text=evidence_text
    )
    # D0102.4 §25のClaim-Type別必須軸Overrideは、Model結果で置き換えた
    # 後にも再適用する(Modelが必須軸へNOT_APPLICABLEを返すことで
    # `_apply_required_dimension_override()`をSilentに迂回することを
    # 防ぐ、既存Overrideの意図をDETERMINISTIC/MODELいずれの出所でも
    # 一貫して守る)。
    merged_results = tuple(_apply_required_dimension_override(r, claim_type=candidate.claim_type) for r in merged_results)
    overall_outcome = _aggregate(merged_results)

    verification_provenance = AiDerivedProvenance(
        model_provider=model_provider,
        model_name=model_name,
        model_version=model_version,
        prompt_version=prompt_version,
        prompt_hash=prompt_hash,
        generated_at=datetime.now(UTC),
    )

    return FaithfulnessVerificationResult(
        status=FaithfulnessVerificationStatus.SUCCESS,
        overall_outcome=overall_outcome,
        dimension_results=merged_results,
        candidate_reference=candidate_reference,
        verification_version=verification_version,
        verified_at=verified_at,
        verification_provenance=verification_provenance,
    )


# ============================================================
# D0102.4.2 — ACCEPT-only Promotion Gate(§28修正2)
# ============================================================


def promote_verified_candidate(
    *,
    candidate: SemanticClaimCandidate,
    verification_result: FaithfulnessVerificationResult,
) -> SemanticClaim | None:
    """D0102.4A修正2: 既存`SemanticClaim.__post_init__`は`REVIEW_
    REQUIRED`の構築を技術的に許容するが、それは「新設するPromotion
    Boundaryが実際にそれを行ってよい」という許可ではない。この
    Orchestration Boundary自身の規律として、`status=SUCCESS`かつ
    `overall_outcome=ACCEPT`の場合のみ`build_semantic_claim()`を
    呼び出す(唯一の資格Case)。`REVIEW_REQUIRED`/`REJECT`/non-SUCCESS
    はいずれも`None`を返し、`build_semantic_claim()`を一切呼び出さない
    (REVIEW_PROMOTION_ALLOWED = NO、REJECT_PROMOTION_ALLOWED = NO)。

    `candidate`のField(`claim_type`/`normalized_claim_text`/
    `direction`/`evidence_span`/`extraction_version`/`schema_version`/
    `extraction_provenance`)はVerification開始時点の値をそのまま渡す
    (Verifierは書き換え不可、Silent Mutationの余地が構造的に無い、
    §13/§19)。

    D0102.4.2.1 D42-F01 Closure(§2C、Defense in Depth): `Faithfulness
    VerificationResult.__post_init__`が既にCanonical Aggregation
    Invariantを強制しているため、この関数へ到達する時点で`overall_
    outcome`は`dimension_results`と既に整合しているはずである。ただし
    Promotionは唯一のACCEPT Gateであるため、その前提を無条件に信頼せず
    ここでも独立に`_aggregate()`を再実行して確認する(Silent Repairは
    行わない、不整合ならPromotionをFail Closedで拒否する)。"""
    if verification_result.status != FaithfulnessVerificationStatus.SUCCESS:
        return None
    if verification_result.overall_outcome != FaithfulnessOutcome.ACCEPT:
        return None

    recomputed_outcome = _aggregate(verification_result.dimension_results)
    if recomputed_outcome != FaithfulnessOutcome.ACCEPT:
        raise FaithfulnessSchemaError(
            "verification_result.overall_outcome=ACCEPT ですが、dimension_results から再計算した"
            f"Aggregation結果は {recomputed_outcome.value} です"
            "(Forged/Internally-Inconsistent Result、D0102.4.2.1 D42-F01 Closure、Promotionを拒否します)"
        )

    expected_reference = compute_candidate_reference(candidate)
    if verification_result.candidate_reference != expected_reference:
        raise FaithfulnessSchemaError(
            "verification_result.candidate_reference が candidate と一致しません"
            "(異なるCandidateのVerificationResultを誤って渡していないか確認してください)"
        )

    return build_semantic_claim(
        claim_type=candidate.claim_type,
        normalized_claim_text=candidate.normalized_claim_text,
        direction=candidate.direction,
        evidence_span=candidate.evidence_span,
        faithfulness_outcome=verification_result.overall_outcome,
        extraction_version=candidate.extraction_version,
        schema_version=candidate.schema_version,
        extraction_provenance=candidate.extraction_provenance,
    )


__all__ = [
    "DETERMINISTIC_FAITHFULNESS_VERSION",
    "MODEL_ASSISTED_FAITHFULNESS_VERSION",
    "FaithfulnessCheckMethod",
    "FaithfulnessDimension",
    "FaithfulnessDimensionOutcome",
    "FaithfulnessDimensionResult",
    "FaithfulnessReasonCode",
    "FaithfulnessSchemaError",
    "FaithfulnessVerificationResult",
    "FaithfulnessVerificationStatus",
    "FaithfulnessVerifier",
    "FaithfulnessVerifierInput",
    "compute_candidate_reference",
    "promote_verified_candidate",
    "verify_candidate_deterministically",
    "verify_candidate_faithfulness",
]
