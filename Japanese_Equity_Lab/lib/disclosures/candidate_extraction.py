"""Semantic Candidate Extraction Boundary(Stage 3.18.5、D0102.3.1)。

D0102.3(DECISIONS.md)で承認されたArchitectureをそのままcode化する。
LLM/Modelとの実接続(Vendor SDK・Prompt本体・実API呼び出し)はこの
Moduleの責務外であり、`CandidateExtractionModel` Protocol経由で
Caller側からAdapter注入する(D0102.3 §13)。Faithfulness Verification
(8軸Check、`FaithfulnessOutcome`の実際の判定)はこのModuleでは一切
実装しない(将来Round、D0102.4)。

## Core Architecture(D0102.3で承認された順序、変更なし)

    NormalizedDisclosureDocument (D0101.1、不変)
            |
    Caller が正確に1 NormalizedTextBlock を選択
            |
    EvidenceSpan.from_text_block() で Trusted EvidenceSpan を構築
            |
    revalidate_evidence_span(...) == VALID を Model呼び出し直前に必須確認
    (NEEDS_REVALIDATION・Exception等、VALID以外は一切Model呼び出しを行わない)
            |
    Model は claim_type / normalized_claim_text / direction のみ提案
            |
    Deterministic Schema Validation(禁止Field検出・Enum検証・
    BUSINESS_RISK Allowlist Gate・重複Collapse)
            |
    SemanticClaimCandidate(evidence_spanは常に上記の同一Instance)
            |
    (将来Round、D0102.4) Faithfulness Verification
            |
    SemanticClaim

    SOURCE_IDENTITY_AUTHORITY = CALLER_PINNED_NON_LLM
    ONE_SOURCE_TEXTBLOCK_PER_EXTRACTION_CALL = REQUIRED_V1
    TRUSTED_EVIDENCE_REQUIRED_BEFORE_MODEL_CALL = TRUE
    EVIDENCE_BINDING_DEPENDS_ON_SOURCE_NOT_CLAIM = TRUE
    CANDIDATE_GENERATION_IS_NOT_FAITHFULNESS_CERTIFICATION = TRUE
    EXTRACTION_TIMESTAMP_IS_NOT_PIT_AVAILABILITY = TRUE

## D0102.2-A01のIntegration Boundary Closure

D0102.2 Auditで持ち越されたResidual Finding(EvidenceSpanは直接構築
可能で、Revalidationは呼び出し側の任意判断に依存していた)を、この
Moduleの`extract_candidates()`という**唯一の公開Entrypoint**で
Neutralizeする——このModule内で`model.extract(...)`を呼び出す経路は
`extract_candidates()`の内部にしか存在せず、その内部では
`revalidate_evidence_span(...) == VALID`の確認が構造的にModel呼び出し
より必ず先に実行される。EvidenceSpanがどう構築されたか(正規の
`from_text_block()`経由か、Fabricatedな直接構築か)に関わらず、
Revalidationに失敗すればModelは一切呼び出されない
(`SOURCE_REVALIDATION_FAILED`を返し、`model.extract()`呼び出し回数は
常に0のまま)。

## Model Authority Boundary(D0102.3 §4)

Model出力Schemaは`{"candidates": [{"claim_type", "normalized_claim_
text", "direction"}]}`の3 Fieldのみを許可する。Document ID・Member
Path・Taxonomy要素名・Occurrence Index・Offset・Quote・Raw Hash・
Normalizer Version・Claim ID・Semantic Identity Key・Schema/
Extraction Version・Timestamp・EvidenceSpan相当のFieldがModel出力に
含まれていた場合は、その1 Candidateだけでなく**Response全体**を
`MODEL_CONTRACT_VIOLATION`としてRejectする(Silent Ignoreしない)。

## Candidate ≠ 確定したSemanticClaim(D0102.3 §15)

`SemanticClaimCandidate`は`claim_id`/`semantic_identity_key`を持たず、
`FaithfulnessOutcome`も一切保持しない——将来のFaithfulness
Verification(D0102.4)がACCEPT/REVIEW_REQUIREDを判定した後にのみ、
`lib.disclosures.semantic_claims.build_semantic_claim()`へ渡されて
初めて`SemanticClaim`になる。このModule自身はFaithfulness判定を
偽装・代行しない。

## BUSINESS_RISK Allowlist(Substring Heuristic不使用、D0102.3 §7)

`taxonomy_element_name`に"Risk"という文字列が含まれるかどうかという
Substring Heuristicは使わない(既存原則、D0045: 「Provider固有Codeから
のmappingは明示的Mapping Tableのみで行い、substring heuristicは
使わない」)。実測済みTaxonomy要素名のみを含む明示的Allowlistを使う。

## WHOLE_RESPONSE_FATAL vs CANDIDATE_LOCAL(D0102.3.2、Boundary Hardening)

Codex Adversarial Audit(D0102.3.1-F01〜F04)を受け、以下の分類を本
Moduleの確定Contractとして明文化する:

**WHOLE_RESPONSE_FATAL**(Response全体を`MODEL_CONTRACT_VIOLATION`で
Reject。Candidate単位のSkipではない):
    - Top-level構造不正(dict以外、`{"candidates"}`以外のKey、
      非文字列Key)
    - `candidates`がlist以外、上限超過
    - Candidate Dictが非文字列Keyを含む
    - 禁止Field(Identity/Provenance系)の混入
    - Candidate Dictの許可Key集合との不一致(過不足)
    - BUSINESS_RISK Hard Constraint違反(非対象Taxonomyへの付与)

**CANDIDATE_LOCAL**(該当Candidateのみをrejected_candidate_countへ
計上してSkip、Response全体は継続処理):
    - `claim_type`/`direction`の値が不正なEnum文字列
    - `normalized_claim_text`が空・空白のみ・制御文字を含む
      (`validate_claim_text()`失敗)
    - `normalized_claim_text`の長さ超過(`MAX_CLAIM_TEXT_LENGTH`)
    - 値の型不正(str以外のField値)

`SemanticClaimCandidate.__post_init__()`は`validate_claim_text()`が
送出する`SemanticClaimSchemaError`を`CandidateExtractionSchemaError`
へこの1箇所で変換する(Narrow Boundary、D0102.3.1-F01)——`_validate_
and_build_candidates()`側は`CandidateExtractionSchemaError`のみを
Catchすれば良く、例外型の重複管理をしない。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from lib.disclosures.normalization import NormalizedDisclosureDocument
from lib.disclosures.semantic_claims import (
    ClaimDirection,
    EvidenceSpan,
    RevalidationResult,
    SemanticClaimSchemaError,
    SemanticClaimType,
    revalidate_evidence_span,
    validate_claim_text,
)
from lib.evidence.model import AiDerivedProvenance

SCHEMA_VERSION = "CANDIDATE_EXTRACTION_SCHEMA_V1"

# D0102.3 §7: BUSINESS_RISKをModel出力として許容するTaxonomy要素名の
# 明示的Allowlist。実測済み(Toyota S100UP32、D0101.1/D0102.2)の値のみを
# 含む。新しい値を追加する場合も、実際に観測されたExact Nameのみを
# 追加すること(Substring/Pattern Matchへの変更は禁止)。
BUSINESS_RISK_ELIGIBLE_TAXONOMY_NAMES: frozenset[str] = frozenset({"jpcrp_cor:BusinessRisksTextBlock"})

# D0102.3 §7/§4: Model出力Candidate 1件が持てるKeyの完全な集合(過不足を
# 許さない、これ以外のKeyが1つでもあればResponse全体をReject)。
_ALLOWED_CANDIDATE_KEYS: frozenset[str] = frozenset({"claim_type", "normalized_claim_text", "direction"})

# D0102.3 §4: Model出力に含まれていてはならないIdentity/Provenance系
# Field名(Candidate Dict内・Response Top-level問わず、1つでも検出した
# 時点でResponse全体をMODEL_CONTRACT_VIOLATIONとする)。
FORBIDDEN_MODEL_OUTPUT_FIELDS: frozenset[str] = frozenset(
    {
        "document_id",
        "member_path",
        "taxonomy_element_name",
        "occurrence_index",
        "char_start",
        "char_end",
        "supporting_quote",
        "source_raw_canonical_content_hash",
        "source_normalizer_version",
        "claim_id",
        "semantic_identity_key",
        "schema_version",
        "extraction_version",
        "generated_at",
        "market_public_at",
        "provider_available_at",
        "evidence_span",
        "EvidenceSpan",
    }
)

# D0102.3 §7: 1 Response内で許容するCandidate数の上限。超過はResponse
# 全体のMODEL_CONTRACT_VIOLATION(先頭N件を無言採用する部分信頼はしない)。
MAX_CANDIDATES_PER_TEXTBLOCK = 20

# D0102.3 §13/§9: normalized_claim_text 1件あたりの最大文字数(1つの
# 独立して評価可能なPropositionを表す短いTextを想定、段落ではない)。
MAX_CLAIM_TEXT_LENGTH = 300

# D0102.3 §11/§19: Source TextをModelへ渡す上での既定文字数上限
# (Model非依存のCharacter-based簡易Proxy、Model固有のToken Budgetへの
# 決め打ちは避ける、呼び出し側で上書き可能)。
DEFAULT_MAX_SOURCE_CHARS = 8_000


def _is_string_keyed_dict(value: dict[object, object]) -> bool:
    """D0102.3.2 F02: Model出力Dictへの`sorted(dict.keys())`等を安全に
    行える前提(全Keyがstr)を、実際に使う前に必ず確認する。`int`/
    `float`等が混在するKeyに対して`sorted()`を呼ぶと`TypeError`になる
    ため、比較を一切行わずに`isinstance`のみで判定する。"""
    return all(isinstance(key, str) for key in value.keys())


class CandidateExtractionSchemaError(ValueError):
    """本Module固有のSchema/Provenance Invariant違反(呼び出し側の
    Programming Errorに相当するもの)で送出する。Model出力自体の
    不正はException化せず`CandidateExtractionResult`のTyped Outcomeで
    表現する(D0102.3 §14、区別を明示的に保つ)。"""


class CandidateExtractionStatus(StrEnum):
    """D0102.3 §14の主要Outcome。"""

    SUCCESS = "SUCCESS"
    NO_CANDIDATES = "NO_CANDIDATES"
    SOURCE_REVALIDATION_FAILED = "SOURCE_REVALIDATION_FAILED"
    TOO_LONG_FOR_EXTRACTION = "TOO_LONG_FOR_EXTRACTION"
    MODEL_CONTRACT_VIOLATION = "MODEL_CONTRACT_VIOLATION"
    MODEL_ERROR = "MODEL_ERROR"


class CandidateExtractionModel(Protocol):
    """D0102.3 §13: Vendor SDKへ直接結合しない、最小限のNarrow
    Protocol。実装(Production Adapter・Test用Fake、いずれも同じ形)は
    `taxonomy_element_name`+`source_text`のみを入力として受け取り、
    Schema検証前のRaw構造化出力(通常`dict`)を返す——Schema検証自体は
    この関数の呼び出し側(`extract_candidates()`)が一元的に行う。"""

    def extract(self, *, taxonomy_element_name: str, source_text: str) -> object:
        """`source_text`はCaller-pinned TextBlockの`normalized_text`
        そのもの(D0102.3 §5: 会社名・銘柄コード・Filing種別・期間等の
        Contextは一切含めない)。実装はこの2引数以外のいかなる情報
        (他のTextBlock・後続Filing・市場データ・外部知識)にもAccess
        すべきではない(D0102.3 §17 PIT Safety)。"""
        ...


@dataclass(kw_only=True, frozen=True)
class SemanticClaimCandidate:
    """D0102.3 §6/§15: 未確定(Non-persisted)なSemantic Claim候補。
    `claim_id`/`semantic_identity_key`/`FaithfulnessOutcome`のいずれも
    持たない——Faithfulness Verification(将来Round、D0102.4)が
    ACCEPT/REVIEW_REQUIREDを判定した後にのみ、`lib.disclosures.
    semantic_claims.build_semantic_claim()`へ渡されて`SemanticClaim`に
    昇格する。それまでは`SemanticClaim`として永続化してはならない。"""

    claim_type: SemanticClaimType
    normalized_claim_text: str
    direction: ClaimDirection
    evidence_span: EvidenceSpan
    extraction_version: str
    extraction_provenance: AiDerivedProvenance
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        # D0102.3.2 F04: Public Constructorであるため、Enum/Provenance/
        # EvidenceSpanのRuntime型をここで厳格に検証する(Type Hintのみに
        # 依存しない——D0102.4がこのDataclassの上に構築される前に、直接
        # 構築されたInvalid Instanceを構造的に排除しておく)。
        if not isinstance(self.claim_type, SemanticClaimType):
            raise CandidateExtractionSchemaError(f"claim_type は SemanticClaimType である必要があります: {self.claim_type!r}")
        if not isinstance(self.direction, ClaimDirection):
            raise CandidateExtractionSchemaError(f"direction は ClaimDirection である必要があります: {self.direction!r}")
        if not isinstance(self.evidence_span, EvidenceSpan):
            raise CandidateExtractionSchemaError("evidence_span は単一のEvidenceSpanである必要があります")
        # D0102.3.2 F01: validate_claim_text()自体のSemantics/Errorは
        # 変更しない。送出されるSemanticClaimSchemaErrorをこの1箇所
        # (Narrow Boundary)でCandidateExtractionSchemaErrorへ変換する
        # ことで、Module外へ`lib.disclosures.semantic_claims`固有の
        # 例外型が漏れることを構造的に防ぐ。
        try:
            validate_claim_text(self.normalized_claim_text)
        except SemanticClaimSchemaError as exc:
            raise CandidateExtractionSchemaError(str(exc)) from exc
        if len(self.normalized_claim_text) > MAX_CLAIM_TEXT_LENGTH:
            raise CandidateExtractionSchemaError(f"normalized_claim_text が上限({MAX_CLAIM_TEXT_LENGTH}文字)を超えています")
        if not isinstance(self.extraction_version, str) or not self.extraction_version:
            raise CandidateExtractionSchemaError("extraction_version は空でないstrである必要があります")
        if not isinstance(self.schema_version, str) or not self.schema_version:
            raise CandidateExtractionSchemaError("schema_version は空でないstrである必要があります")
        if not isinstance(self.extraction_provenance, AiDerivedProvenance):
            raise CandidateExtractionSchemaError(
                "extraction_provenance は AiDerivedProvenance である必要があります(D0102.3.2、Optional廃止)"
            )


@dataclass(kw_only=True, frozen=True)
class CandidateExtractionResult:
    """`extract_candidates()`の戻り値。`status`がSUCCESS/NO_CANDIDATES
    以外の場合、`candidates`は常に空Tupleである(D0102.3 §14、Typed
    Outcomeで表現、Exceptionを使わない)。"""

    status: CandidateExtractionStatus
    candidates: tuple[SemanticClaimCandidate, ...] = field(default_factory=tuple)
    rejected_candidate_count: int = 0
    reason: str | None = None


def _reject(status: CandidateExtractionStatus, reason: str) -> CandidateExtractionResult:
    return CandidateExtractionResult(status=status, candidates=(), reason=reason)


def _validate_and_build_candidates(
    raw_response: object,
    *,
    evidence_span: EvidenceSpan,
    extraction_version: str,
    schema_version: str,
    provenance: AiDerivedProvenance,
) -> CandidateExtractionResult:
    """D0102.3 §4/§13: Model Raw出力をDeterministicにSchema検証する。
    `model.extract()`が呼ばれた**後**にのみ実行され、EvidenceSpan/
    Identity構築には一切関与しない(既にRevalidation済みの
    `evidence_span`をそのままCopyするのみ)。"""
    if not isinstance(raw_response, dict):
        return _reject(CandidateExtractionStatus.MODEL_CONTRACT_VIOLATION, "response is not a JSON object")
    # D0102.3.2 F02: sorted()等でKeyを比較する前に、全Keyがstrである
    # ことを必ず先に確認する(int/float混在Keyに対するsorted()は
    # TypeErrorになるため、比較そのものを行う前にRejectする)。
    if not _is_string_keyed_dict(raw_response):
        return _reject(CandidateExtractionStatus.MODEL_CONTRACT_VIOLATION, "top-level response contains non-string keys")
    if set(raw_response.keys()) != {"candidates"}:
        return _reject(
            CandidateExtractionStatus.MODEL_CONTRACT_VIOLATION,
            f"unexpected top-level keys: {sorted(raw_response.keys())}",
        )

    raw_candidates = raw_response["candidates"]
    if not isinstance(raw_candidates, list):
        return _reject(CandidateExtractionStatus.MODEL_CONTRACT_VIOLATION, "'candidates' is not a list")
    if len(raw_candidates) > MAX_CANDIDATES_PER_TEXTBLOCK:
        return _reject(
            CandidateExtractionStatus.MODEL_CONTRACT_VIOLATION,
            f"too many candidates ({len(raw_candidates)} > {MAX_CANDIDATES_PER_TEXTBLOCK})",
        )
    if not raw_candidates:
        return CandidateExtractionResult(status=CandidateExtractionStatus.NO_CANDIDATES)

    # D0102.3 §4: 構造的Violation(禁止Field・不明Key・欠落Key)は
    # Candidate単位ではなくResponse全体をRejectする(Silent Ignore禁止)。
    for raw_candidate in raw_candidates:
        if not isinstance(raw_candidate, dict):
            return _reject(CandidateExtractionStatus.MODEL_CONTRACT_VIOLATION, "candidate entry is not a JSON object")
        # D0102.3.2 F02: Candidate Dict自体もsorted()前にstr-only Keyを確認する。
        if not _is_string_keyed_dict(raw_candidate):
            return _reject(CandidateExtractionStatus.MODEL_CONTRACT_VIOLATION, "candidate entry contains non-string keys")
        keys = set(raw_candidate.keys())
        forbidden_present = keys & FORBIDDEN_MODEL_OUTPUT_FIELDS
        if forbidden_present:
            return _reject(
                CandidateExtractionStatus.MODEL_CONTRACT_VIOLATION,
                f"forbidden identity/provenance field(s) in model output: {sorted(forbidden_present)}",
            )
        if keys != _ALLOWED_CANDIDATE_KEYS:
            return _reject(
                CandidateExtractionStatus.MODEL_CONTRACT_VIOLATION,
                f"candidate has unexpected keys: {sorted(keys)} (expected exactly {sorted(_ALLOWED_CANDIDATE_KEYS)})",
            )

    built: list[SemanticClaimCandidate] = []
    rejected_count = 0
    for raw_candidate in raw_candidates:
        assert isinstance(raw_candidate, dict)  # noqa: S101 -- 直前のLoopで既に検証済み(mypy Narrowing用)
        claim_type_raw = raw_candidate["claim_type"]
        direction_raw = raw_candidate["direction"]
        text_raw = raw_candidate["normalized_claim_text"]

        if not isinstance(claim_type_raw, str) or not isinstance(direction_raw, str) or not isinstance(text_raw, str):
            rejected_count += 1
            continue

        try:
            claim_type = SemanticClaimType(claim_type_raw)
        except ValueError:
            rejected_count += 1
            continue
        try:
            direction = ClaimDirection(direction_raw)
        except ValueError:
            rejected_count += 1
            continue

        # D0102.3 §7: BUSINESS_RISK Allowlist Gate。Modelが非対象
        # TextBlockに対してBUSINESS_RISKを返した場合はResponse全体を
        # Rejectする(1 Candidateだけの問題として片付けない、Hard
        # Constraintの無視は深刻なContract Violationとして扱う)。
        if (
            claim_type == SemanticClaimType.BUSINESS_RISK
            and evidence_span.taxonomy_element_name not in BUSINESS_RISK_ELIGIBLE_TAXONOMY_NAMES
        ):
            return _reject(
                CandidateExtractionStatus.MODEL_CONTRACT_VIOLATION,
                f"BUSINESS_RISK returned for non-eligible taxonomy_element_name={evidence_span.taxonomy_element_name!r}",
            )

        try:
            candidate = SemanticClaimCandidate(
                claim_type=claim_type,
                normalized_claim_text=text_raw,
                direction=direction,
                evidence_span=evidence_span,
                extraction_version=extraction_version,
                schema_version=schema_version,
                extraction_provenance=provenance,
            )
        except CandidateExtractionSchemaError:
            rejected_count += 1
            continue
        built.append(candidate)

    # D0102.3 §15/D0102.1 Philosophy: 同一Response内のExact Duplicate
    # (claim_type + text + direction完全一致)のみCollapseする。Fuzzy
    # Semantic Dedupeは行わない。
    deduped: list[SemanticClaimCandidate] = []
    seen: set[tuple[str, str, str]] = set()
    for candidate in built:
        key = (candidate.claim_type.value, candidate.normalized_claim_text, candidate.direction.value)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)

    if not deduped:
        return CandidateExtractionResult(status=CandidateExtractionStatus.NO_CANDIDATES, rejected_candidate_count=rejected_count)
    return CandidateExtractionResult(
        status=CandidateExtractionStatus.SUCCESS,
        candidates=tuple(deduped),
        rejected_candidate_count=rejected_count,
    )


def extract_candidates(
    *,
    evidence_span: EvidenceSpan,
    document: NormalizedDisclosureDocument,
    model: CandidateExtractionModel,
    extraction_version: str,
    model_provider: str,
    model_name: str,
    model_version: str | None = None,
    prompt_version: str | None = None,
    prompt_hash: str,
    schema_version: str = SCHEMA_VERSION,
    max_source_chars: int = DEFAULT_MAX_SOURCE_CHARS,
) -> CandidateExtractionResult:
    """D0102.3で承認されたCandidate Extraction Boundaryの唯一の公開
    Entrypoint(D0102.3.1)。

    `model.extract(...)`を呼び出す経路はこの関数の内部にしか存在しない
    ため、以下の全チェックを通過しない限りModelは一度も呼び出されない
    (`TRUSTED_EVIDENCE_REQUIRED_BEFORE_MODEL_CALL = TRUE`、D0102.2-A01
    のIntegration Boundaryでの Closure):

    1. `extraction_version`/`prompt_hash`が空でないこと、`max_source_
       chars`が厳密な正のint(`bool`は不可、D0102.3.2 F03)であること
       (D0102.3 §16、ModelにVersioningを自己申告させない——いずれも
       Callerの Programming Errorとして`CandidateExtractionSchemaError`
       をRaiseする、Model呼び出し前)。
    2. `revalidate_evidence_span(evidence_span, document=document) ==
       RevalidationResult.VALID`(NEEDS_REVALIDATION・Exceptionいずれも
       `SOURCE_REVALIDATION_FAILED`として扱い、Model呼び出しを行わない)。
    3. `evidence_span.supporting_quote`の長さが`max_source_chars`以内
       (超過時は`TOO_LONG_FOR_EXTRACTION`、Chunkingはしない)。

    Model呼び出しが実際に発生するのは上記3条件を全て満たした場合のみ。
    """
    if not extraction_version:
        raise CandidateExtractionSchemaError("extraction_version は空にできません")
    if not prompt_hash:
        raise CandidateExtractionSchemaError("prompt_hash は空にできません(D0102.3 §16、Promptの決定論的Versioningが必須)")
    # D0102.3.2 F03: `bool`は`int`のSubclassのため`isinstance(x, int)`
    # では`True`/`False`を排除できない。`type(x) is int`による厳密な
    # 型一致のみを許可する。
    if type(max_source_chars) is not int or max_source_chars <= 0:
        raise CandidateExtractionSchemaError(f"max_source_chars は正のintである必要があります: {max_source_chars!r}")

    try:
        revalidation = revalidate_evidence_span(evidence_span, document=document)
    except SemanticClaimSchemaError as exc:
        return _reject(CandidateExtractionStatus.SOURCE_REVALIDATION_FAILED, str(exc))
    if revalidation != RevalidationResult.VALID:
        return _reject(CandidateExtractionStatus.SOURCE_REVALIDATION_FAILED, f"revalidation result={revalidation.value}")

    if len(evidence_span.supporting_quote) > max_source_chars:
        return _reject(
            CandidateExtractionStatus.TOO_LONG_FOR_EXTRACTION,
            f"source length {len(evidence_span.supporting_quote)} exceeds max_source_chars={max_source_chars}",
        )

    generated_at = datetime.now(UTC)
    try:
        raw_response = model.extract(
            taxonomy_element_name=evidence_span.taxonomy_element_name,
            source_text=evidence_span.supporting_quote,
        )
    except Exception as exc:
        # D0102.3.2 §18: Vendor SDKの生Exception文言(Credential/Token/
        # 内部URL等を含み得る)をそのままreasonへ保存しない。Exception
        # 種別名のみを記録し、詳細調査はCaller側のLoggingに委ねる。
        return _reject(CandidateExtractionStatus.MODEL_ERROR, f"model raised {type(exc).__name__}")

    provenance = AiDerivedProvenance(
        model_provider=model_provider,
        model_name=model_name,
        model_version=model_version,
        prompt_version=prompt_version,
        prompt_hash=prompt_hash,
        generated_at=generated_at,
    )
    return _validate_and_build_candidates(
        raw_response,
        evidence_span=evidence_span,
        extraction_version=extraction_version,
        schema_version=schema_version,
        provenance=provenance,
    )


__all__ = [
    "BUSINESS_RISK_ELIGIBLE_TAXONOMY_NAMES",
    "DEFAULT_MAX_SOURCE_CHARS",
    "FORBIDDEN_MODEL_OUTPUT_FIELDS",
    "MAX_CANDIDATES_PER_TEXTBLOCK",
    "MAX_CLAIM_TEXT_LENGTH",
    "SCHEMA_VERSION",
    "CandidateExtractionModel",
    "CandidateExtractionResult",
    "CandidateExtractionSchemaError",
    "CandidateExtractionStatus",
    "SemanticClaimCandidate",
    "extract_candidates",
]
