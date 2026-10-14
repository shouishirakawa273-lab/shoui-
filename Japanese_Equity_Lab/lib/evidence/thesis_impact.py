"""Thesis Break Monitor: Deterministic Gate + Narrow Model-Assisted Semantic
Interpretation of Research Thesis Impact(D0106)。

D0105(`lib.evidence.incremental_update`)が識別した変化Evidence
(NEW/POTENTIALLY_SUPERSEDED/REMOVED_OR_MISSING)を、既存の
`ResearchArtifact`(Bull/Base/Bearの各`NarrativeCase`)に対して
Scenario単位で評価し、`lib.evidence.model.EvidenceRelation`
(SUPPORTS/CONTRADICTS/ALTERNATIVE_EXPLANATION/NEUTRAL/UNKNOWN、既存
Enumをそのまま再利用・新しいSynonymは追加しない)のいずれかへ分類する
唯一の公開Entrypoint`assess_thesis_impact()`を提供する。

**本Moduleは次のいずれでもない(D0106 §2 Core Principle)**: 「新しい
最終Thesisは何か」には一切答えない。EVIDENCE(事実)・INTERPRETATION
(本Moduleが生成する唯一の出力)・DECISION(人間/将来Layerの責務)を
明確に分離する。BUY/SELL・期待Return・Valuation・Portfolio Logicは
いずれも存在しない。

## Deterministic Gate が Semantic Interpretationより常に先行する(D0106 §6)

Model(存在する場合)が呼び出されるのは、以下の決定論的Gateを**全て**
通過した後のみである。いずれかのGateが失敗した場合、Model呼び出しは
一切発生しない(Model PASSがDeterministic FAILを上書きすることは
構造的に無い、`lib.disclosures.faithfulness.verify_candidate_
faithfulness()`と同じ設計原則):

1. `evidence_id`がD0105の`IncrementalResearchUpdateResult`内の
   いずれかのBucketに実在すること(`MISSING_REFERENCE`)。
2. `UNCHANGED`Evidenceは本Moduleの主要対象ではない
   (`UNSUPPORTED_INPUT`、D0105 §5)。
3. `REMOVED_OR_MISSING`の場合、当該Scenarioの`NarrativeCase.
   supporting_evidence_ids`に実際に参照されていること(`NOT_MATERIAL`、
   D0106 §17のMateriality境界=既存Referenceのみ再利用)。
4. (`NEW`/`POTENTIALLY_SUPERSEDED`の場合)`evidence_records`内に
   一意に存在すること(`MISSING_REFERENCE`/`AMBIGUOUS_REFERENCE`)。
5. `EvidenceType.CLAIM`であること(`UNSUPPORTED_INPUT`)。
6. `decision_at`時点でPIT利用可能であること(`EvidenceRecord.
   is_usable_at()`、既存Method再利用、`PIT_MISMATCH`)。
7. `lib.disclosures.evidence_lineage.resolve_evidence_lineage()`
   (D0104、Traversal Logicを複製しない)が`SUCCESS`であること
   (`LINEAGE_FAILURE`、ACCEPT以外のEvidenceもこのGateで検知される
   ——`resolve_evidence_lineage()`自身がFaithfulness-ACCEPTEDのみを
   `SUCCESS`とするため)。

`REMOVED_OR_MISSING`は上記4-7を一切実行しない(対応する`EvidenceRecord`
自体がCurrent Snapshotに存在しないため、評価するContent自体が無い)。
この場合Modelは一切呼び出されず、`relation=UNKNOWN`・
`requires_review=True`・`reason="EVIDENCE_MISSING"`を決定論的に
直接返す——**REMOVED_OR_MISSINGが自動的にCONTRADICTSやFALSEを意味する
ことは無い**(D0106 §12)。

## Model-Assisted Semantic Interpretation(Narrow Input/Narrow Output)

Modelは`ThesisRelationModel` Protocol(`lib.disclosures.candidate_
extraction.CandidateExtractionModel`/`lib.disclosures.faithfulness.
FaithfulnessVerifier`と同型のAdapter Injection Pattern)経由でCaller
側からOptionalに注入する。入力は`ThesisRelationModelInput`
(Narrow Allowlist)のみ——本Module自身が市場価格・Valuation・他の
EvidenceRecord・Research History全体を新たに追加送信することはない
(`research_node_id`は既存`ResearchArtifact.artifact_id`をそのまま
渡す、D0106 §8がHypothesis Identifierを許可Fieldとして明示している
ため——これ自体がCaller側のID発行Conventionにより企業識別子を含む
場合があるが、それは既存Identity空間の性質であり、本Moduleが新たに
Ticker/企業名Fieldを追加するものではない)。
出力はDict形式のRaw構造化出力を期待し、`relation`(`EvidenceRelation`
の値そのもの、自由形式のSynonymは一切許可しない)・`reason`(str)・
`uncertainty`(`ConfidenceLevel`、既存Enumを再利用・新しい0-100 Score
は作らない)の3 Keyのみを許可する——未知のKey(Thesis書き換え・
BUY/SELL・Target Price等の密輸)が1つでもあれば、Candidate単位では
なくResponse全体を`MODEL_CONTRACT_VIOLATION`としてReject する
(`lib.disclosures.candidate_extraction`のForbidden Field/Allowed Key
Allowlist Patternと同じ設計)。

Modelが`None`の場合(Semantic Interpretationが未設定)は、`relation=
UNKNOWN`・`requires_review=True`・`reason="NO_MODEL_CONFIGURED"`を
返す(推測で埋めない、Fail Conservative)。

## Scenario Isolation(D0106 §14)

1件のEvidenceは、Bull/Base/Bearへ独立に評価される——1つのGlobal
Relationを強制しない。`assess_thesis_impact()`はArtifact全体ではなく
単一(ResearchArtifact, Scenario, Evidence)の3つ組に対して呼ぶ最小
単位のPure Functionであり、呼び出し側がBull/Base/Bear全てを評価する
場合は3回個別に呼ぶ(隠れたLoop・自動全Scenario評価はしない)。

## ResearchArtifact Boundary(D0106 §24、本Moduleが越えない境界)

本Moduleは`ResearchArtifact`/`NarrativeCase`を一切構築・Mutateしない
(Read-Onlyの引数としてのみ受け取る)。新しい`EvidenceRelation`の
Artifact自体への書き込み・Bull/Base/Bear・Conclusion・Confidenceの
変更はいずれも行わない——本Moduleは`ThesisImpactResult`(Assessment
Output)を返すのみで、それをArtifactへ反映するかどうかの判断は人間/
将来のLayerに委ねる(Append-Only Assessment Storeは本Repositoryに
現時点で存在しないため、新設しない、D0106 §24)。

## D0107 Readiness(Provenance、D0106 §19/§25)

`ThesisImpactAssessment`は、Model呼び出しが発生した場合
`assessment_provenance`(既存`lib.evidence.model.AiDerivedProvenance`
をそのまま再利用、新しいProvenance Schemaは作らない)を保持する。
`assessed_at`(本Assessmentが生成された時刻)と`evidence_available_at`
(当該EvidenceのPIT `available_at`)・`decision_at`(PIT判定基準時刻)
を明確に分離して保持する——Assessment Timestampと Evidence
Availabilityを混同しない(D0106 §19)。将来のD0107(Lock機構)が
「時刻Tにどのような評価が存在したか」を再構成できるよう、全Fieldは
Immutable Dataclassとして保持するのみで、Persistence自体は本Round
では実装しない(D0107は構築しない、D0106 §25)。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from lib.disclosures.candidate_extraction import SemanticClaimCandidate
from lib.disclosures.evidence_lineage import EvidenceLineageStatus, resolve_evidence_lineage
from lib.disclosures.model import DisclosureDocument
from lib.disclosures.normalization import NormalizedDisclosureDocument
from lib.disclosures.semantic_claims import ClaimDirection, SemanticClaim, SemanticClaimType
from lib.evidence.incremental_update import IncrementalResearchUpdateResult
from lib.evidence.model import AiDerivedProvenance, EvidenceRecord, EvidenceRelation, EvidenceType
from lib.evidence.research_artifact import ConfidenceLevel, NarrativeCase, ResearchArtifact

# D0106 §11: このRelationはHuman ReviewをRequireする(Section 11の表を
# そのままEncodeする)。NEUTRAL/SUPPORTSは強制Reviewしない。
_REVIEW_REQUIRED_RELATIONS: frozenset[EvidenceRelation] = frozenset(
    {EvidenceRelation.CONTRADICTS, EvidenceRelation.ALTERNATIVE_EXPLANATION, EvidenceRelation.UNKNOWN}
)

# D0106 §9: Modelの生Output Dictが持てるKeyの完全な集合(過不足を許さない、
# `lib.disclosures.candidate_extraction._ALLOWED_CANDIDATE_KEYS`と同じ
# Whole-Response-Fatal Pattern)。
_ALLOWED_MODEL_OUTPUT_KEYS: frozenset[str] = frozenset({"relation", "reason", "uncertainty"})


class ThesisImpactSchemaError(ValueError):
    """本Module固有のSchema Invariant違反(呼び出し側のProgramming
    Errorに相当するもの)で送出する。「必要なReferenceが見つからない」
    「Modelが契約に違反した」等の正当なDomain上のOutcomeは
    `ThesisAssessmentStatus`のTyped Outcomeで表現し、区別する
    (D0103-D0105と同じ方針)。"""


class ThesisScenario(StrEnum):
    """Bull/Base/Bearの3 Scenario(D0106 §14、Scenario Isolation)。"""

    BULL = "BULL"
    BASE = "BASE"
    BEAR = "BEAR"


class EvidenceChangeKind(StrEnum):
    """D0105(`IncrementalResearchUpdateResult`)が既に確立した4分類を
    そのまま再利用する(新しいSynonymではなく、D0105の同じ語彙を型安全に
    扱うためのEnum化のみ)。"""

    NEW = "NEW"
    UNCHANGED = "UNCHANGED"
    REMOVED_OR_MISSING = "REMOVED_OR_MISSING"
    POTENTIALLY_SUPERSEDED = "POTENTIALLY_SUPERSEDED"


class ThesisAssessmentStatus(StrEnum):
    """`assess_thesis_impact()`の主要Outcome(D0106 §29)。`ASSESSED`
    以外は呼び出し側の入力・Model出力が構造的に信頼できないことを示し、
    `ThesisImpactResult.assessment`は`None`になる(D0103-D0105と同じ
    Typed Outcome Pattern)。"""

    ASSESSED = "ASSESSED"
    UNSUPPORTED_INPUT = "UNSUPPORTED_INPUT"
    MISSING_REFERENCE = "MISSING_REFERENCE"
    AMBIGUOUS_REFERENCE = "AMBIGUOUS_REFERENCE"
    LINEAGE_FAILURE = "LINEAGE_FAILURE"
    PIT_MISMATCH = "PIT_MISMATCH"
    NOT_MATERIAL = "NOT_MATERIAL"
    MODEL_CONTRACT_VIOLATION = "MODEL_CONTRACT_VIOLATION"


@dataclass(kw_only=True, frozen=True)
class ThesisRelationModelInput:
    """Model-Assisted Semantic Interpretationへ渡す入力のNarrow
    Allowlist(D0106 §8、`lib.disclosures.faithfulness.
    FaithfulnessVerifierInput`と同じ設計)。市場価格・Valuation・他の
    EvidenceRecord・Research History全体はいずれも含めない——この
    7 Fieldのみが唯一のAuthoritative Inputであり、全FieldがCaller
    側から実際に値を渡される(`evidence_claim_type`/`evidence_
    direction`を含めて固定Noneで埋めない、Code Review Finding
    D0106 Closure)。"""

    research_node_id: str
    scenario: ThesisScenario
    hypothesis_summary: str
    evidence_normalized_text: str
    evidence_claim_type: SemanticClaimType | None = None
    evidence_direction: ClaimDirection | None = None
    evidence_supporting_quote: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.scenario, ThesisScenario):
            raise ThesisImpactSchemaError(f"scenario は ThesisScenario である必要があります: {self.scenario!r}")
        if not isinstance(self.research_node_id, str) or not self.research_node_id:
            raise ThesisImpactSchemaError("research_node_id は空でないstrである必要があります")
        if not isinstance(self.hypothesis_summary, str) or not self.hypothesis_summary:
            raise ThesisImpactSchemaError("hypothesis_summary は空でないstrである必要があります")
        if not isinstance(self.evidence_normalized_text, str) or not self.evidence_normalized_text:
            raise ThesisImpactSchemaError("evidence_normalized_text は空でないstrである必要があります")


class ThesisRelationModel(Protocol):
    """Vendor SDKへ直接結合しない、最小限のNarrow Protocol
    (`CandidateExtractionModel`/`FaithfulnessVerifier`と同型の
    Adapter Injection Pattern)。実装(Production Adapter・Test用Fake、
    いずれも同じ形)は`model_input`のみを入力として受け取り、Schema
    検証前のRaw構造化出力(通常`dict`)を返す——Schema検証自体は呼び出し
    側(`assess_thesis_impact()`)が一元的に行う。"""

    def classify(self, *, model_input: ThesisRelationModelInput) -> object:
        """`model_input`はNarrow Allowlist Fieldのみを持つ(上記
        `ThesisRelationModelInput`参照)。実装はこの引数以外のいかなる
        情報にもAccessすべきではない(PIT Safety、`CandidateExtraction
        Model`と同じ制約)。Hypothesis書き換え・BUY/SELL・Target
        Price・期待Return・Confidence直接変更はいずれも返してはならない
        (呼び出し側がAllowed Key以外を一切受理しないため、構造的に
        拒否される)。"""
        ...


@dataclass(kw_only=True, frozen=True)
class ThesisImpactAssessment:
    """`assess_thesis_impact()`が`ASSESSED`時に返すAssessment本体
    (D0106 §10)。数値Impact Score・0-100 Materiality Scoreは一切
    持たない(2値`requires_review`のみ)。"""

    research_node_id: str
    scenario: ThesisScenario
    evidence_id: str
    evidence_change_kind: EvidenceChangeKind
    relation: EvidenceRelation
    requires_review: bool
    reason: str
    lineage_reference: str | None
    evidence_available_at: datetime | None
    decision_at: datetime
    assessed_at: datetime
    uncertainty: ConfidenceLevel | None = None
    assessment_provenance: AiDerivedProvenance | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.relation, EvidenceRelation):
            raise ThesisImpactSchemaError(f"relation は EvidenceRelation である必要があります: {self.relation!r}")
        expected_review = self.relation in _REVIEW_REQUIRED_RELATIONS
        if self.requires_review is not expected_review:
            raise ThesisImpactSchemaError(
                f"requires_review({self.requires_review!r}) が relation({self.relation.value})から"
                f"導出される期待値({expected_review!r})と一致しません(D0106 §11、Forged/Inconsistent State)"
            )
        if self.decision_at.tzinfo is None:
            raise ThesisImpactSchemaError("decision_at はtz-awareである必要があります")
        if self.assessed_at.tzinfo is None:
            raise ThesisImpactSchemaError("assessed_at はtz-awareである必要があります")
        if self.evidence_available_at is not None and self.evidence_available_at.tzinfo is None:
            raise ThesisImpactSchemaError("evidence_available_at はtz-awareである必要があります")


@dataclass(kw_only=True, frozen=True)
class ThesisImpactResult:
    """`assess_thesis_impact()`の戻り値。`status`が`ASSESSED`以外の
    場合、`assessment`は常に`None`である(D0103-D0105と同型のTyped
    Outcome、Exceptionを使わない)。"""

    status: ThesisAssessmentStatus
    reason: str | None = None
    assessment: ThesisImpactAssessment | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, ThesisAssessmentStatus):
            raise ThesisImpactSchemaError(f"status は ThesisAssessmentStatus である必要があります: {self.status!r}")
        if self.reason is not None and not isinstance(self.reason, str):
            raise ThesisImpactSchemaError(f"reason は str または None である必要があります: {self.reason!r}")
        if self.status == ThesisAssessmentStatus.ASSESSED:
            if self.assessment is None:
                raise ThesisImpactSchemaError("status=ASSESSED の場合 assessment は None にできません")
            if not isinstance(self.assessment, ThesisImpactAssessment):
                raise ThesisImpactSchemaError(f"assessment は ThesisImpactAssessment である必要があります: {self.assessment!r}")
        elif self.assessment is not None:
            raise ThesisImpactSchemaError(
                f"status={self.status.value} の場合 assessment は必ず None である必要があります"
                "(Assessmentが完走しなかったことを明示するため)"
            )


def _fail(status: ThesisAssessmentStatus, reason: str) -> ThesisImpactResult:
    return ThesisImpactResult(status=status, reason=reason)


def _scenario_narrative_case(research_artifact: ResearchArtifact, scenario: ThesisScenario) -> NarrativeCase:
    mapping = {
        ThesisScenario.BULL: research_artifact.bull_case,
        ThesisScenario.BASE: research_artifact.base_case,
        ThesisScenario.BEAR: research_artifact.bear_case,
    }
    return mapping[scenario]


def _evidence_change_kind(evidence_id: str, incremental_update: IncrementalResearchUpdateResult) -> EvidenceChangeKind | None:
    """D0105の`new_evidence_ids`は、Supersession Pairの新側Evidenceも
    引き続き含む(`potentially_superseded_pairs`はNEWの部分集合に対する
    追加分類であり、NEWという所属自体を取り除くものではない、D0105の
    既存Semantics)。D0106にとっては`POTENTIALLY_SUPERSEDED`がより
    具体的な分類であるため、`new_evidence_ids`より先にこちらを確認
    する(優先順位の逆転Bugを防ぐ)。"""
    if evidence_id in {pair.new_evidence_id for pair in incremental_update.potentially_superseded_pairs}:
        return EvidenceChangeKind.POTENTIALLY_SUPERSEDED
    if evidence_id in incremental_update.new_evidence_ids:
        return EvidenceChangeKind.NEW
    if evidence_id in incremental_update.removed_or_missing_evidence_ids:
        return EvidenceChangeKind.REMOVED_OR_MISSING
    if evidence_id in incremental_update.unchanged_evidence_ids:
        return EvidenceChangeKind.UNCHANGED
    return None


@dataclass(frozen=True)
class _ValidatedModelOutput:
    relation_raw: str
    reason: str
    uncertainty_raw: str | None


def _validate_model_output(raw: object) -> _ValidatedModelOutput | str:
    """Modelの生Output Dictを検証する。問題が無ければ型付き`_Validated
    ModelOutput`を、問題があれば人間可読なErrorメッセージ(str)を返す
    (D0106 §9、`lib.disclosures.candidate_extraction._validate_and_
    build_candidates()`と同じWhole-Response-Fatal Pattern)。"""
    if not isinstance(raw, dict):
        return "Model出力がJSON Object(dict)ではありません"
    if not all(isinstance(key, str) for key in raw.keys()):
        return "Model出力のTop-levelが非文字列Keyを含んでいます"
    keys = set(raw.keys())
    if keys != _ALLOWED_MODEL_OUTPUT_KEYS:
        return f"Model出力のKeyが許可Set{sorted(_ALLOWED_MODEL_OUTPUT_KEYS)}と一致しません: {sorted(keys)}"
    relation_raw = raw["relation"]
    reason = raw["reason"]
    uncertainty_raw = raw["uncertainty"]
    if not isinstance(relation_raw, str):
        return "relation はstrである必要があります"
    if not isinstance(reason, str) or not reason:
        return "reason は空でないstrである必要があります"
    if uncertainty_raw is not None and not isinstance(uncertainty_raw, str):
        return "uncertainty はstrまたはNoneである必要があります"
    return _ValidatedModelOutput(relation_raw=relation_raw, reason=reason, uncertainty_raw=uncertainty_raw)


def assess_thesis_impact(
    *,
    research_artifact: ResearchArtifact,
    scenario: ThesisScenario,
    evidence_id: str,
    incremental_update: IncrementalResearchUpdateResult,
    decision_at: datetime,
    assessed_at: datetime,
    evidence_records: Sequence[EvidenceRecord] = (),
    semantic_claims: Sequence[SemanticClaim] = (),
    candidates: Sequence[SemanticClaimCandidate] = (),
    normalized_documents: Sequence[NormalizedDisclosureDocument] = (),
    disclosure_documents: Sequence[DisclosureDocument] = (),
    model: ThesisRelationModel | None = None,
    model_provider: str = "",
    model_name: str = "",
    model_version: str | None = None,
    prompt_version: str | None = None,
    prompt_hash: str = "",
) -> ThesisImpactResult:
    """単一(`research_artifact`, `scenario`, `evidence_id`)の3つ組に
    対し、Deterministic Gateを経てから(合格した場合のみ)Model-Assisted
    Semantic Interpretationを行う唯一の公開Entrypoint(D0106)。

    Bull/Base/Bear全てを評価する場合は、呼び出し側が本関数を3回個別に
    呼ぶ(隠れたLoop・自動全Scenario評価は行わない、D0106 §14 Scenario
    Isolation)。`evidence_id`がD0105の`incremental_update`で`NEW`/
    `POTENTIALLY_SUPERSEDED`/`REMOVED_OR_MISSING`のいずれかに分類
    されていない場合(`UNCHANGED`含む)は、Model呼び出し前にFail
    Closedする。詳細な各Gateの説明はModule Docstring参照。
    """
    if not isinstance(research_artifact, ResearchArtifact):
        raise ThesisImpactSchemaError(f"research_artifact は ResearchArtifact である必要があります: {research_artifact!r}")
    if not isinstance(scenario, ThesisScenario):
        raise ThesisImpactSchemaError(f"scenario は ThesisScenario である必要があります: {scenario!r}")
    if not isinstance(evidence_id, str) or not evidence_id:
        raise ThesisImpactSchemaError("evidence_id は空でないstrである必要があります")
    if not isinstance(incremental_update, IncrementalResearchUpdateResult):
        raise ThesisImpactSchemaError(
            f"incremental_update は IncrementalResearchUpdateResult である必要があります: {incremental_update!r}"
        )
    if decision_at.tzinfo is None:
        raise ThesisImpactSchemaError("decision_at はtz-awareである必要があります")
    if assessed_at.tzinfo is None:
        raise ThesisImpactSchemaError("assessed_at はtz-awareである必要があります")
    # Code Review Finding(D0106)Closure: `candidates`/`normalized_
    # documents`/`disclosure_documents`も他の引数と同様にElement型を
    # 検証する——未検証のまま`resolve_evidence_lineage()`へ渡すと、
    # 不正な要素(dict等)に対して生の`AttributeError`が漏れ、「Caller
    # Programming Errorと正当なDomain Outcomeを区別する」既存契約
    # (D0105の`_require_type`と同じ方針)が破れる。
    for record in evidence_records:
        if not isinstance(record, EvidenceRecord):
            raise ThesisImpactSchemaError(f"evidence_recordsの各要素は EvidenceRecord である必要があります: {record!r}")
    for claim in semantic_claims:
        if not isinstance(claim, SemanticClaim):
            raise ThesisImpactSchemaError(f"semantic_claimsの各要素は SemanticClaim である必要があります: {claim!r}")
    for candidate in candidates:
        if not isinstance(candidate, SemanticClaimCandidate):
            raise ThesisImpactSchemaError(f"candidatesの各要素は SemanticClaimCandidate である必要があります: {candidate!r}")
    for normalized_document in normalized_documents:
        if not isinstance(normalized_document, NormalizedDisclosureDocument):
            raise ThesisImpactSchemaError(
                f"normalized_documentsの各要素は NormalizedDisclosureDocument である必要があります: {normalized_document!r}"
            )
    for disclosure_document in disclosure_documents:
        if not isinstance(disclosure_document, DisclosureDocument):
            raise ThesisImpactSchemaError(
                f"disclosure_documentsの各要素は DisclosureDocument である必要があります: {disclosure_document!r}"
            )

    change_kind = _evidence_change_kind(evidence_id, incremental_update)
    if change_kind is None:
        return _fail(
            ThesisAssessmentStatus.MISSING_REFERENCE,
            f"evidence_id={evidence_id!r} はincremental_update内のいずれのBucketにも存在しません",
        )
    if change_kind is EvidenceChangeKind.UNCHANGED:
        return _fail(
            ThesisAssessmentStatus.UNSUPPORTED_INPUT,
            f"evidence_id={evidence_id!r} はUNCHANGEDであり、D0106の主要対象ではありません(D0105 §5)",
        )

    narrative_case = _scenario_narrative_case(research_artifact, scenario)

    if change_kind is EvidenceChangeKind.REMOVED_OR_MISSING:
        if evidence_id not in narrative_case.supporting_evidence_ids:
            return _fail(
                ThesisAssessmentStatus.NOT_MATERIAL,
                f"evidence_id={evidence_id!r} はscenario={scenario.value}のsupporting_evidence_idsに"
                "参照されておらず、このScenarioにとってMaterialではありません(D0106 §17)",
            )
        assessment = ThesisImpactAssessment(
            research_node_id=research_artifact.artifact_id,
            scenario=scenario,
            evidence_id=evidence_id,
            evidence_change_kind=change_kind,
            relation=EvidenceRelation.UNKNOWN,
            requires_review=True,
            reason="EVIDENCE_MISSING: 旧EvidenceがPrior Snapshotに存在したがCurrent Snapshotから"
            "見当たらない(D0105 REMOVED_OR_MISSING)。これは自動的にCONTRADICTS/FALSEを意味しない(D0106 §12)。",
            lineage_reference=None,
            evidence_available_at=None,
            decision_at=decision_at,
            assessed_at=assessed_at,
            assessment_provenance=None,
        )
        return ThesisImpactResult(status=ThesisAssessmentStatus.ASSESSED, assessment=assessment)

    # NEW / POTENTIALLY_SUPERSEDED: 実EvidenceRecordが存在するはずであり、
    # 以下のDeterministic Gateを全て通過しなければModelを呼び出さない。
    matches = [r for r in evidence_records if r.evidence_id == evidence_id]
    if len(matches) == 0:
        return _fail(
            ThesisAssessmentStatus.MISSING_REFERENCE,
            f"evidence_id={evidence_id!r} がevidence_recordsに存在しません",
        )
    if len(matches) > 1:
        return _fail(
            ThesisAssessmentStatus.AMBIGUOUS_REFERENCE,
            f"evidence_id={evidence_id!r} がevidence_recordsに複数件存在します(重複ID)",
        )
    evidence = matches[0]

    if evidence.evidence_type is not EvidenceType.CLAIM:
        return _fail(
            ThesisAssessmentStatus.UNSUPPORTED_INPUT,
            f"evidence_type={evidence.evidence_type.value} はSemanticClaim Integration Boundary"
            "(D0103)由来のEvidenceのみ対応します",
        )

    if not evidence.is_usable_at(decision_at):
        return _fail(
            ThesisAssessmentStatus.PIT_MISMATCH,
            f"evidence.source.available_at={evidence.source.available_at!r} はdecision_at={decision_at!r}"
            "時点でまだ利用可能ではありません(D0106 §13、PIT Safety)",
        )

    lineage_result = resolve_evidence_lineage(
        evidence,
        semantic_claims=semantic_claims,
        candidates=candidates,
        normalized_documents=normalized_documents,
        disclosure_documents=disclosure_documents,
    )
    if lineage_result.status != EvidenceLineageStatus.SUCCESS:
        return _fail(
            ThesisAssessmentStatus.LINEAGE_FAILURE,
            f"resolve_evidence_lineage()が{lineage_result.status.value}を返しました"
            f"(ACCEPT以外のEvidence・Provenance不整合いずれも含む): {lineage_result.reason}",
        )
    lineage = lineage_result.lineage
    assert lineage is not None  # noqa: S101 -- SUCCESS時はEvidenceLineageResult.__post_init__がこれを保証する

    # Code Review Finding(D0106)Closure: `evidence.source.source_id ==
    # claim.claim_id`(D0103/D0104の既存Authoritative Join Key)で、
    # このEvidenceを生成した実際のSemanticClaimを再特定する——Lineage
    # がSUCCESSした時点で、D0104自身のAMBIGUOUS_LINK/MISSING_LINK Check
    # により一意性は既に保証されている。`claim_type`/`direction`を
    # Narrow Model Inputへ実際に渡すために使う(以前はNoneで固定して
    # おり、Allowlist Fieldが宣言されているのに実質未使用だった)。
    matching_claims_for_model = [c for c in semantic_claims if c.claim_id == evidence.source.source_id]
    claim_for_model = matching_claims_for_model[0] if len(matching_claims_for_model) == 1 else None

    if model is None:
        assessment = ThesisImpactAssessment(
            research_node_id=research_artifact.artifact_id,
            scenario=scenario,
            evidence_id=evidence_id,
            evidence_change_kind=change_kind,
            relation=EvidenceRelation.UNKNOWN,
            requires_review=True,
            reason="NO_MODEL_CONFIGURED: Semantic Interpretation用のThesisRelationModelが供給されていないため、"
            "Relationを推測せずUNKNOWNとして返します(D0106、Fail Conservative)。",
            lineage_reference=lineage.claim_id,
            evidence_available_at=evidence.source.available_at,
            decision_at=decision_at,
            assessed_at=assessed_at,
            assessment_provenance=None,
        )
        return ThesisImpactResult(status=ThesisAssessmentStatus.ASSESSED, assessment=assessment)

    if not prompt_hash:
        raise ThesisImpactSchemaError("prompt_hash は空にできません(D0102.3/D0102.4と同じ方針、Promptの決定論的Versioningが必須)")

    # Code Review Finding(D0106)Closure: 空の`NarrativeCase.summary`は
    # `ResearchArtifact`側で構造的に禁止されていない(Legitimate Domain
    # State)ため、`ThesisRelationModelInput.__post_init__`の空文字
    # Validationに到達させてException化せず、ここでTyped Outcomeとして
    # Fail Closedする(「Caller Programming Errorと正当なDomain
    # Outcomeを区別する」既存契約の違反を修正)。
    if not narrative_case.summary:
        return _fail(
            ThesisAssessmentStatus.UNSUPPORTED_INPUT,
            f"scenario={scenario.value}のNarrativeCase.summaryが空のため、Semantic Interpretationに"
            "必要なHypothesis Textがありません",
        )

    model_input = ThesisRelationModelInput(
        research_node_id=research_artifact.artifact_id,
        scenario=scenario,
        hypothesis_summary=narrative_case.summary,
        evidence_normalized_text=evidence.content,
        evidence_claim_type=claim_for_model.claim_type if claim_for_model is not None else None,
        evidence_direction=claim_for_model.direction if claim_for_model is not None else None,
        evidence_supporting_quote=lineage.supporting_quote,
    )
    raw_output = model.classify(model_input=model_input)
    validated = _validate_model_output(raw_output)
    if isinstance(validated, str):
        return _fail(ThesisAssessmentStatus.MODEL_CONTRACT_VIOLATION, validated)

    try:
        relation = EvidenceRelation(validated.relation_raw)
    except ValueError:
        return _fail(
            ThesisAssessmentStatus.MODEL_CONTRACT_VIOLATION,
            f"relation={validated.relation_raw!r} は EvidenceRelation の有効な値ではありません",
        )
    uncertainty: ConfidenceLevel | None = None
    if validated.uncertainty_raw is not None:
        try:
            uncertainty = ConfidenceLevel(validated.uncertainty_raw)
        except ValueError:
            return _fail(
                ThesisAssessmentStatus.MODEL_CONTRACT_VIOLATION,
                f"uncertainty={validated.uncertainty_raw!r} は ConfidenceLevel の有効な値ではありません",
            )

    provenance = AiDerivedProvenance(
        model_provider=model_provider,
        model_name=model_name,
        model_version=model_version,
        prompt_version=prompt_version,
        prompt_hash=prompt_hash,
        input_evidence_ids=(evidence_id,),
        generated_at=assessed_at,
    )
    assessment = ThesisImpactAssessment(
        research_node_id=research_artifact.artifact_id,
        scenario=scenario,
        evidence_id=evidence_id,
        evidence_change_kind=change_kind,
        relation=relation,
        requires_review=relation in _REVIEW_REQUIRED_RELATIONS,
        reason=validated.reason,
        lineage_reference=lineage.claim_id,
        evidence_available_at=evidence.source.available_at,
        decision_at=decision_at,
        assessed_at=assessed_at,
        uncertainty=uncertainty,
        assessment_provenance=provenance,
    )
    return ThesisImpactResult(status=ThesisAssessmentStatus.ASSESSED, assessment=assessment)


__all__ = [
    "EvidenceChangeKind",
    "ThesisAssessmentStatus",
    "ThesisImpactAssessment",
    "ThesisImpactResult",
    "ThesisImpactSchemaError",
    "ThesisRelationModel",
    "ThesisRelationModelInput",
    "ThesisScenario",
    "assess_thesis_impact",
]
