"""Immutable Prediction & Evaluation Foundation: Core Record Types(D0107)。

将来の全Forecast/Expectations/Valuation/Decision System(D0108+)を
公平に評価するための最小限の計測基盤。**本Moduleはそれ自体を証明しない**
(Alpha証明・Backtest Engine・Valuation Engine・Portfolio Logicのいずれ
でもない、D0107 §0/§2)。「将来のPrediction・Revision・実験条件・評価
Ruleを、Immutable・Reconstructable・Comparableにする」ことのみが目的。

## Core Object分離(D0107 §3)

`ResearchSnapshot`/`PredictionRecord`/`DecisionRecord`/
`EvaluationContract`/`EvaluationRecord`/`ExperimentSpec`を明確に分離
する。**DecisionをPredictionRecordの中に置かない**——正しいForecastで
あってもValuation/市場条件が魅力的でなければNO_ACTIONになりうるため
(D0107 §3)。同様に`NO_ACTION`と`INSUFFICIENT_DATA`も区別する
(D0107 §11)。

## Tamper Evidence(D0107 §18)

全Recordは`record_hash`(`lib.evaluation.integrity.compute_record_
hash()`、既存`hash_json_safe()`をそのまま再利用、新しいHash
Algorithmは作らない)を持つ。各`build_*()`関数が構築時に1度だけHashを
計算し、以降Recordは`frozen=True`により不変——`record_hash`自身は
計算対象から除外される。Tuple系Fieldは構築時に`sorted()`でCanonical
Orderへ正規化し、入力順序に依存しないHashを保証する(D0107 §18
TEST K)。

## Prediction Revision(D0107 §6)

`parent_prediction_id`による明示的な改訂Edgeのみを許可し、Heuristicな
推測は一切行わない。`build_prediction_record()`は`existing_predictions`
(呼び出し側が明示的に注入するPool)に対して、親の実在・Entity/Target/
Target Period一致・循環の不在を検証する——いずれかに違反すれば
`EvaluationFoundationSchemaError`でFail Closedする(親を書き換える
経路はどこにも存在しない)。

## PIT Reconstruction(D0107 §9)

`build_research_snapshot()`は、参照する全`evidence_id`に対応する
`EvidenceRecord`が`evidence_cutoff`時点でPIT利用可能であることを
既存`EvidenceRecord.is_usable_at()`(D0103、新しいPIT Algorithmは
作らない)で検証する。違反時は既存`lib.errors.LookAheadBiasError`
(`lib.evidence.research_artifact.build_research_artifact()`と同じ
既存Exception、`market_public_at`へのFallbackは一切行わない)で
Fail Closedする。

## ResearchArtifact Identity(既存Primitiveの再利用のみ、Gap無し)

`ResearchArtifact`は既に`artifact_id`+`artifact_version`+
`supersedes_artifact_id`というImmutable Identity/Versionの既存
Primitiveを持つ(D0107 §4が要求する「If existing ResearchArtifact
has no immutable identity/version primitive」というGapは存在しない)。
`ResearchSnapshot`はこの既存Identityをそのまま参照し、新しいIdentity
機構は追加しない。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from lib.errors import LookAheadBiasError
from lib.evaluation.integrity import compute_record_hash
from lib.evidence.model import EvidenceRecord
from lib.evidence.thesis_impact import ThesisScenario


class EvaluationFoundationSchemaError(ValueError):
    """本Module固有のSchema/Invariant違反(呼び出し側のProgramming
    Errorに相当するもの)で送出する(D0103-D0106と同じ方針)。PIT
    違反は専用の既存`lib.errors.LookAheadBiasError`を使う(本Error
    とは区別する)。"""


class ForecastShape(StrEnum):
    """`PredictionRecord`のForecast表現形式(D0107 §5/§24)。将来の
    EPS/Revenue/Margin/FCF/市場Implied Assumption/Valuation Output等
    (D0108+)を、新しいSchema変更無しで表現できるよう、`target`
    (Section内の対象指標名)自体は固定Enumにせず自由文字列とし、
    この2形式(Scalar/Bull-Base-Bear)のみを型として区別する。"""

    SCALAR = "SCALAR"
    BULL_BASE_BEAR = "BULL_BASE_BEAR"


class DecisionStatus(StrEnum):
    """`DecisionRecord.decision_status`(D0107 §11)。`NO_ACTION`
    (魅力的でないため見送り)と`INSUFFICIENT_DATA`(判断材料が無い)を
    明確に区別する(両者を1つにMergeしない)。`ACTION`は将来の
    Decision Layerにおける実行可能Candidateを意味するのみで、自動
    発注を意味しない。"""

    ACTION = "ACTION"
    WATCH = "WATCH"
    NO_ACTION = "NO_ACTION"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class EvaluationMetric(StrEnum):
    """D0107が提供する唯一の最小限Deterministic Metric(§13「D0107
    needs only one minimal working deterministic evaluation example」、
    大きなMetric Libraryは作らない)。"""

    ABSOLUTE_ERROR = "ABSOLUTE_ERROR"


@dataclass(kw_only=True, frozen=True)
class ScalarForecast:
    """Scalar(単一数値)形式のForecast(D0107 §5)。"""

    value: Decimal
    unit: str

    def __post_init__(self) -> None:
        if not isinstance(self.unit, str) or not self.unit:
            raise EvaluationFoundationSchemaError("ScalarForecast.unit は空でないstrである必要があります")


@dataclass(kw_only=True, frozen=True)
class BullBaseBearForecast:
    """Bull/Base/Bear構造化Forecast(D0107 §5)。"""

    bull: Decimal
    base: Decimal
    bear: Decimal
    unit: str

    def __post_init__(self) -> None:
        if not isinstance(self.unit, str) or not self.unit:
            raise EvaluationFoundationSchemaError("BullBaseBearForecast.unit は空でないstrである必要があります")


@dataclass(kw_only=True, frozen=True)
class ThesisImpactReference:
    """D0106 `ThesisImpactAssessment`(専用IDを持たない)への参照
    (D0107 §4「ThesisImpact assessment references where available」)。
    `(research_node_id, scenario, evidence_id)`の3つ組がD0106自身の
    Assessment Identityであり、新しいID機構は追加しない。"""

    research_node_id: str
    scenario: ThesisScenario
    evidence_id: str


def _require_nonempty_str(value: str, *, label: str) -> None:
    if not isinstance(value, str) or not value:
        raise EvaluationFoundationSchemaError(f"{label} は空でないstrである必要があります: {value!r}")


def _require_tz_aware(value: datetime, *, label: str) -> None:
    if value.tzinfo is None:
        raise EvaluationFoundationSchemaError(f"{label} はtz-awareである必要があります")


@dataclass(kw_only=True, frozen=True)
class ResearchSnapshot:
    """Predictionが利用可能だったResearch状態への、Immutableな参照
    (D0107 §4)。`ResearchArtifact`全体をCopyせず、既存Identity
    (`artifact_id`+`artifact_version`)のみを参照する。"""

    snapshot_id: str
    entity_id: str
    evidence_cutoff: datetime
    research_artifact_id: str
    research_artifact_version: int
    evidence_ids: tuple[str, ...] = field(default_factory=tuple)
    thesis_impact_references: tuple[ThesisImpactReference, ...] = field(default_factory=tuple)
    research_schema_version: str = "RESEARCH_SNAPSHOT_SCHEMA_V1"
    created_at: datetime
    record_hash: str

    def __post_init__(self) -> None:
        for name, value in (
            ("snapshot_id", self.snapshot_id),
            ("entity_id", self.entity_id),
            ("research_artifact_id", self.research_artifact_id),
            ("research_schema_version", self.research_schema_version),
            ("record_hash", self.record_hash),
        ):
            _require_nonempty_str(value, label=name)
        if self.research_artifact_version < 1:
            raise EvaluationFoundationSchemaError("research_artifact_version は1以上である必要があります")
        _require_tz_aware(self.evidence_cutoff, label="evidence_cutoff")
        _require_tz_aware(self.created_at, label="created_at")


def build_research_snapshot(
    *,
    snapshot_id: str,
    entity_id: str,
    evidence_cutoff: datetime,
    research_artifact_id: str,
    research_artifact_version: int,
    created_at: datetime,
    evidence_records: Sequence[EvidenceRecord] = (),
    evidence_ids: Sequence[str] = (),
    thesis_impact_references: Sequence[ThesisImpactReference] = (),
    research_schema_version: str = "RESEARCH_SNAPSHOT_SCHEMA_V1",
) -> ResearchSnapshot:
    """`ResearchSnapshot`を構築する唯一のEntrypoint(D0107 §4/§9)。

    `evidence_ids`で参照される各`EvidenceRecord`(`evidence_records`
    Poolから検索)が`evidence_cutoff`時点でPIT利用可能であること
    (`EvidenceRecord.is_usable_at()`、既存Method再利用)を検証する。
    違反(Future Evidence参照)は`LookAheadBiasError`でFail Closedする
    (`market_public_at`へのFallbackは無い、D0107 §9)。`evidence_
    records`に該当する`evidence_id`が見つからない場合は
    `EvaluationFoundationSchemaError`(Caller Programming Error)。
    """
    if evidence_cutoff.tzinfo is None:
        raise EvaluationFoundationSchemaError("evidence_cutoff はtz-awareである必要があります")
    evidence_by_id = {e.evidence_id: e for e in evidence_records}
    for evidence_id in evidence_ids:
        evidence = evidence_by_id.get(evidence_id)
        if evidence is None:
            raise EvaluationFoundationSchemaError(
                f"evidence_id={evidence_id!r} に対応するEvidenceRecordがevidence_recordsに存在しません"
            )
        if not evidence.is_usable_at(evidence_cutoff):
            raise LookAheadBiasError(
                f"evidence_id={evidence_id!r}(available_at={evidence.source.available_at!r})は"
                f"evidence_cutoff={evidence_cutoff!r}時点でまだ利用可能ではありません(Future Information Leakage)"
            )

    canonical_evidence_ids = tuple(sorted(evidence_ids))
    canonical_thesis_refs = tuple(
        sorted(thesis_impact_references, key=lambda r: (r.research_node_id, r.scenario.value, r.evidence_id))
    )
    payload = {
        "snapshot_id": snapshot_id,
        "entity_id": entity_id,
        "evidence_cutoff": evidence_cutoff,
        "research_artifact_id": research_artifact_id,
        "research_artifact_version": research_artifact_version,
        "evidence_ids": canonical_evidence_ids,
        "thesis_impact_references": canonical_thesis_refs,
        "research_schema_version": research_schema_version,
        "created_at": created_at,
    }
    return ResearchSnapshot(
        snapshot_id=snapshot_id,
        entity_id=entity_id,
        evidence_cutoff=evidence_cutoff,
        research_artifact_id=research_artifact_id,
        research_artifact_version=research_artifact_version,
        evidence_ids=canonical_evidence_ids,
        thesis_impact_references=canonical_thesis_refs,
        research_schema_version=research_schema_version,
        created_at=created_at,
        record_hash=compute_record_hash(payload),
    )


@dataclass(kw_only=True, frozen=True)
class PredictionRecord:
    """Append-only/Immutable Prediction(D0107 §5)。Revision(`parent_
    prediction_id`)は常に新しい`prediction_id`を発行し、親Recordを
    一切書き換えない(D0107 §6)。Decision Statusはここには置かない
    (D0107 §3)。"""

    prediction_id: str
    entity_id: str
    target: str
    target_period: str
    forecast_shape: ForecastShape
    scalar_forecast: ScalarForecast | None = None
    bull_base_bear_forecast: BullBaseBearForecast | None = None
    created_at: datetime
    evidence_cutoff: datetime
    research_snapshot_id: str
    model_version: str
    research_pipeline_version: str
    prompt_version: str | None = None
    parent_prediction_id: str | None = None
    evaluation_contract_id: str | None = None
    target_resolution_at: datetime | None = None
    record_hash: str

    def __post_init__(self) -> None:
        for name, value in (
            ("prediction_id", self.prediction_id),
            ("entity_id", self.entity_id),
            ("target", self.target),
            ("target_period", self.target_period),
            ("research_snapshot_id", self.research_snapshot_id),
            ("model_version", self.model_version),
            ("research_pipeline_version", self.research_pipeline_version),
            ("record_hash", self.record_hash),
        ):
            _require_nonempty_str(value, label=name)
        if not isinstance(self.forecast_shape, ForecastShape):
            raise EvaluationFoundationSchemaError(
                f"forecast_shape は ForecastShape である必要があります: {self.forecast_shape!r}"
            )
        if self.forecast_shape is ForecastShape.SCALAR:
            if self.scalar_forecast is None or self.bull_base_bear_forecast is not None:
                raise EvaluationFoundationSchemaError(
                    "forecast_shape=SCALAR の場合、scalar_forecast のみを設定する必要があります"
                )
        else:
            if self.bull_base_bear_forecast is None or self.scalar_forecast is not None:
                raise EvaluationFoundationSchemaError(
                    "forecast_shape=BULL_BASE_BEAR の場合、bull_base_bear_forecast のみを設定する必要があります"
                )
        _require_tz_aware(self.created_at, label="created_at")
        _require_tz_aware(self.evidence_cutoff, label="evidence_cutoff")
        if self.target_resolution_at is not None:
            _require_tz_aware(self.target_resolution_at, label="target_resolution_at")
        if self.prediction_id == self.parent_prediction_id:
            raise EvaluationFoundationSchemaError("parent_prediction_id は自身のprediction_idと同一にできません")


def _validate_parent_prediction(
    *,
    entity_id: str,
    target: str,
    target_period: str,
    parent_prediction_id: str | None,
    existing_predictions: Sequence[PredictionRecord],
) -> None:
    """D0107 §6: 親Predictionの実在・Entity/Target/Target Period一致・
    循環の不在を検証する。Heuristicな推測は一切行わない——`existing_
    predictions`(呼び出し側が明示的に注入するPool)への厳密な参照の
    みで判定する。"""
    if parent_prediction_id is None:
        return
    matches = [p for p in existing_predictions if p.prediction_id == parent_prediction_id]
    if len(matches) == 0:
        raise EvaluationFoundationSchemaError(
            f"parent_prediction_id={parent_prediction_id!r} がexisting_predictionsに存在しません(Missing Parent)"
        )
    if len(matches) > 1:
        raise EvaluationFoundationSchemaError(
            f"parent_prediction_id={parent_prediction_id!r} がexisting_predictions内で複数件に一致します(Ambiguous Prediction ID)"
        )
    parent = matches[0]
    if parent.entity_id != entity_id or parent.target != target or parent.target_period != target_period:
        raise EvaluationFoundationSchemaError(
            f"parent_prediction_id={parent_prediction_id!r} は異なるentity_id/target/target_periodを持ちます"
            f"(parent: {parent.entity_id!r}/{parent.target!r}/{parent.target_period!r}, "
            f"new: {entity_id!r}/{target!r}/{target_period!r})"
        )

    by_id = {p.prediction_id: p for p in existing_predictions}
    visited: set[str] = set()
    current: str | None = parent_prediction_id
    while current is not None:
        if current in visited:
            raise EvaluationFoundationSchemaError(f"parent_prediction_id={parent_prediction_id!r} は循環しています")
        visited.add(current)
        current_record = by_id.get(current)
        current = current_record.parent_prediction_id if current_record is not None else None


def build_prediction_record(
    *,
    prediction_id: str,
    entity_id: str,
    target: str,
    target_period: str,
    forecast_shape: ForecastShape,
    created_at: datetime,
    evidence_cutoff: datetime,
    research_snapshot_id: str,
    model_version: str,
    research_pipeline_version: str,
    scalar_forecast: ScalarForecast | None = None,
    bull_base_bear_forecast: BullBaseBearForecast | None = None,
    prompt_version: str | None = None,
    parent_prediction_id: str | None = None,
    evaluation_contract_id: str | None = None,
    target_resolution_at: datetime | None = None,
    existing_predictions: Sequence[PredictionRecord] = (),
) -> PredictionRecord:
    """`PredictionRecord`を構築する唯一のEntrypoint(D0107 §5)。

    `parent_prediction_id`が指定された場合、`existing_predictions`
    (呼び出し側が明示的に注入するPool)に対して親の実在・Entity/Target/
    Target Period一致・循環の不在を検証する(D0107 §6)。D0107自身は
    Forecastを生成しない(値はCaller指定、Storeのみ)。

    `existing_predictions`が注入されている場合、新しい`prediction_id`
    がPool内の既存Recordと衝突していないことも検証する(`parent_
    prediction_id`の有無を問わない)——Silent Overwriteを防ぐため
    (D0107 forbidden_actions「no silent overwrite of an existing
    PredictionRecord」、In-Memory段階でも成立させる)。
    """
    if any(p.prediction_id == prediction_id for p in existing_predictions):
        raise EvaluationFoundationSchemaError(
            f"prediction_id={prediction_id!r} はexisting_predictions内の既存Recordと衝突します(Silent Overwrite)"
        )
    _validate_parent_prediction(
        entity_id=entity_id,
        target=target,
        target_period=target_period,
        parent_prediction_id=parent_prediction_id,
        existing_predictions=existing_predictions,
    )
    payload = {
        "prediction_id": prediction_id,
        "entity_id": entity_id,
        "target": target,
        "target_period": target_period,
        "forecast_shape": forecast_shape,
        "scalar_forecast": scalar_forecast,
        "bull_base_bear_forecast": bull_base_bear_forecast,
        "created_at": created_at,
        "evidence_cutoff": evidence_cutoff,
        "research_snapshot_id": research_snapshot_id,
        "model_version": model_version,
        "research_pipeline_version": research_pipeline_version,
        "prompt_version": prompt_version,
        "parent_prediction_id": parent_prediction_id,
        "evaluation_contract_id": evaluation_contract_id,
        "target_resolution_at": target_resolution_at,
    }
    return PredictionRecord(
        prediction_id=prediction_id,
        entity_id=entity_id,
        target=target,
        target_period=target_period,
        forecast_shape=forecast_shape,
        scalar_forecast=scalar_forecast,
        bull_base_bear_forecast=bull_base_bear_forecast,
        created_at=created_at,
        evidence_cutoff=evidence_cutoff,
        research_snapshot_id=research_snapshot_id,
        model_version=model_version,
        research_pipeline_version=research_pipeline_version,
        prompt_version=prompt_version,
        parent_prediction_id=parent_prediction_id,
        evaluation_contract_id=evaluation_contract_id,
        target_resolution_at=target_resolution_at,
        record_hash=compute_record_hash(payload),
    )


def forecast_family_key(prediction: PredictionRecord) -> tuple[str, str, str]:
    """D0107 §7: `(entity_id, target, target_period)`——同一Underlying
    Targetに対する相関したRevision群をGroupingするための決定論的Key
    (Metadataのみ、統計的Evaluationはここでは行わない)。"""
    return (prediction.entity_id, prediction.target, prediction.target_period)


@dataclass(kw_only=True, frozen=True)
class DecisionRecord:
    """Predictionとは別のImmutable Decision Event(D0107 §11)。
    D0107自身はDecision Engineではなく、Decision Eventの定義/永続化
    のみを行う。`ACTION`は将来のDecision Layerにおける実行可能
    Candidateを意味するのみで、自動発注ではない。"""

    decision_id: str
    created_at: datetime
    entity_id: str
    research_snapshot_id: str
    prediction_ids: tuple[str, ...] = field(default_factory=tuple)
    decision_status: DecisionStatus
    decision_policy_version: str
    record_hash: str

    def __post_init__(self) -> None:
        for name, value in (
            ("decision_id", self.decision_id),
            ("entity_id", self.entity_id),
            ("research_snapshot_id", self.research_snapshot_id),
            ("decision_policy_version", self.decision_policy_version),
            ("record_hash", self.record_hash),
        ):
            _require_nonempty_str(value, label=name)
        if not isinstance(self.decision_status, DecisionStatus):
            raise EvaluationFoundationSchemaError(
                f"decision_status は DecisionStatus である必要があります: {self.decision_status!r}"
            )
        _require_tz_aware(self.created_at, label="created_at")


def build_decision_record(
    *,
    decision_id: str,
    created_at: datetime,
    entity_id: str,
    research_snapshot_id: str,
    decision_status: DecisionStatus,
    decision_policy_version: str,
    prediction_ids: Sequence[str] = (),
) -> DecisionRecord:
    """`DecisionRecord`を構築する唯一のEntrypoint(D0107 §11)。"""
    canonical_prediction_ids = tuple(sorted(prediction_ids))
    payload = {
        "decision_id": decision_id,
        "created_at": created_at,
        "entity_id": entity_id,
        "research_snapshot_id": research_snapshot_id,
        "prediction_ids": canonical_prediction_ids,
        "decision_status": decision_status,
        "decision_policy_version": decision_policy_version,
    }
    return DecisionRecord(
        decision_id=decision_id,
        created_at=created_at,
        entity_id=entity_id,
        research_snapshot_id=research_snapshot_id,
        prediction_ids=canonical_prediction_ids,
        decision_status=decision_status,
        decision_policy_version=decision_policy_version,
        record_hash=compute_record_hash(payload),
    )


@dataclass(kw_only=True, frozen=True)
class EvaluationContract:
    """評価前に確定するEvaluation Rule(D0107 §12)。Evaluation自体は
    持たず、「何を・何に対して・いつ・どう比較するか」をVersion付きで
    持つのみ——Target/Evaluation Category不一致を防ぐ。"""

    evaluation_contract_id: str
    evaluation_contract_version: int
    target: str
    target_period: str
    actual_truth_description: str
    metric: EvaluationMetric
    evaluable_at_policy: str
    horizon_rule: str | None = None
    created_at: datetime
    record_hash: str

    def __post_init__(self) -> None:
        for name, value in (
            ("evaluation_contract_id", self.evaluation_contract_id),
            ("target", self.target),
            ("target_period", self.target_period),
            ("actual_truth_description", self.actual_truth_description),
            ("evaluable_at_policy", self.evaluable_at_policy),
            ("record_hash", self.record_hash),
        ):
            _require_nonempty_str(value, label=name)
        if self.evaluation_contract_version < 1:
            raise EvaluationFoundationSchemaError("evaluation_contract_version は1以上である必要があります")
        if not isinstance(self.metric, EvaluationMetric):
            raise EvaluationFoundationSchemaError(f"metric は EvaluationMetric である必要があります: {self.metric!r}")
        _require_tz_aware(self.created_at, label="created_at")


def build_evaluation_contract(
    *,
    evaluation_contract_id: str,
    evaluation_contract_version: int,
    target: str,
    target_period: str,
    actual_truth_description: str,
    metric: EvaluationMetric,
    evaluable_at_policy: str,
    created_at: datetime,
    horizon_rule: str | None = None,
) -> EvaluationContract:
    """`EvaluationContract`を構築する唯一のEntrypoint(D0107 §12)。"""
    payload = {
        "evaluation_contract_id": evaluation_contract_id,
        "evaluation_contract_version": evaluation_contract_version,
        "target": target,
        "target_period": target_period,
        "actual_truth_description": actual_truth_description,
        "metric": metric,
        "evaluable_at_policy": evaluable_at_policy,
        "horizon_rule": horizon_rule,
        "created_at": created_at,
    }
    return EvaluationContract(
        evaluation_contract_id=evaluation_contract_id,
        evaluation_contract_version=evaluation_contract_version,
        target=target,
        target_period=target_period,
        actual_truth_description=actual_truth_description,
        metric=metric,
        evaluable_at_policy=evaluable_at_policy,
        horizon_rule=horizon_rule,
        created_at=created_at,
        record_hash=compute_record_hash(payload),
    )


@dataclass(kw_only=True, frozen=True)
class EvaluationRecord:
    """1件のEvaluation結果(D0107 §13)。PredictionRecordを一切変更せず
    別Recordとして保持する。Evaluation Rule(`EvaluationContract`)が
    Version更新されても、以前のEvaluationRecordは上書きされず
    独立に残る(D0107 §13、v1/v2は共存する)。"""

    evaluation_id: str
    prediction_id: str
    evaluation_contract_id: str
    evaluation_contract_version: int
    evaluated_at: datetime
    actual_reference: str
    actual_value: Decimal
    result_value: Decimal
    record_hash: str

    def __post_init__(self) -> None:
        for name, value in (
            ("evaluation_id", self.evaluation_id),
            ("prediction_id", self.prediction_id),
            ("evaluation_contract_id", self.evaluation_contract_id),
            ("actual_reference", self.actual_reference),
            ("record_hash", self.record_hash),
        ):
            _require_nonempty_str(value, label=name)
        if self.evaluation_contract_version < 1:
            raise EvaluationFoundationSchemaError("evaluation_contract_version は1以上である必要があります")
        _require_tz_aware(self.evaluated_at, label="evaluated_at")


class EvaluationComputationStatus(StrEnum):
    """`evaluate_scalar_absolute_error()`の主要Outcome(D0107 §13、
    「Can a prediction be evaluated against the wrong category of
    actual?」というReviewer Focusに対応するTyped Outcome)。"""

    COMPUTED = "COMPUTED"
    TARGET_MISMATCH = "TARGET_MISMATCH"
    SHAPE_MISMATCH = "SHAPE_MISMATCH"
    METRIC_UNSUPPORTED = "METRIC_UNSUPPORTED"


@dataclass(kw_only=True, frozen=True)
class EvaluationComputationResult:
    """`evaluate_scalar_absolute_error()`の戻り値。`status`が
    `COMPUTED`以外の場合`evaluation`は`None`である(D0103-D0106と
    同型のTyped Outcome)。"""

    status: EvaluationComputationStatus
    reason: str | None = None
    evaluation: EvaluationRecord | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, EvaluationComputationStatus):
            raise EvaluationFoundationSchemaError(f"status は EvaluationComputationStatus である必要があります: {self.status!r}")
        if self.status == EvaluationComputationStatus.COMPUTED:
            if self.evaluation is None:
                raise EvaluationFoundationSchemaError("status=COMPUTED の場合 evaluation は None にできません")
        elif self.evaluation is not None:
            raise EvaluationFoundationSchemaError(f"status={self.status.value} の場合 evaluation は None である必要があります")


def evaluate_scalar_absolute_error(
    *,
    evaluation_id: str,
    prediction: PredictionRecord,
    contract: EvaluationContract,
    actual_value: Decimal,
    actual_reference: str,
    evaluated_at: datetime,
) -> EvaluationComputationResult:
    """D0107が提供する唯一の最小限Deterministic Evaluation例
    (`ABSOLUTE_ERROR`、D0107 §13「D0107 needs only one minimal
    working deterministic evaluation example」、大きなMetric
    Libraryはここでは作らない)。

    `prediction.target`/`target_period`が`contract`のそれと一致しない
    場合は`TARGET_MISMATCH`、`prediction.forecast_shape`が`SCALAR`で
    ない場合は`SHAPE_MISMATCH`、`contract.metric`が`ABSOLUTE_ERROR`
    でない場合は`METRIC_UNSUPPORTED`を返す(間違ったCategoryのActualと
    照合することをFail Closedで防ぐ、D0107 §29 Reviewer Focus #10)。
    """
    if prediction.target != contract.target or prediction.target_period != contract.target_period:
        return EvaluationComputationResult(
            status=EvaluationComputationStatus.TARGET_MISMATCH,
            reason=(
                f"prediction target/target_period({prediction.target!r}/{prediction.target_period!r}) が"
                f"contract({contract.target!r}/{contract.target_period!r})と一致しません"
            ),
        )
    if prediction.forecast_shape is not ForecastShape.SCALAR or prediction.scalar_forecast is None:
        return EvaluationComputationResult(
            status=EvaluationComputationStatus.SHAPE_MISMATCH,
            reason="evaluate_scalar_absolute_error() はforecast_shape=SCALARのPredictionのみ対応します",
        )
    if contract.metric is not EvaluationMetric.ABSOLUTE_ERROR:
        return EvaluationComputationResult(
            status=EvaluationComputationStatus.METRIC_UNSUPPORTED,
            reason=f"contract.metric={contract.metric.value} はevaluate_scalar_absolute_error()では未対応です",
        )

    result_value = abs(prediction.scalar_forecast.value - actual_value)
    payload = {
        "evaluation_id": evaluation_id,
        "prediction_id": prediction.prediction_id,
        "evaluation_contract_id": contract.evaluation_contract_id,
        "evaluation_contract_version": contract.evaluation_contract_version,
        "evaluated_at": evaluated_at,
        "actual_reference": actual_reference,
        "actual_value": actual_value,
        "result_value": result_value,
    }
    evaluation = EvaluationRecord(
        evaluation_id=evaluation_id,
        prediction_id=prediction.prediction_id,
        evaluation_contract_id=contract.evaluation_contract_id,
        evaluation_contract_version=contract.evaluation_contract_version,
        evaluated_at=evaluated_at,
        actual_reference=actual_reference,
        actual_value=actual_value,
        result_value=result_value,
        record_hash=compute_record_hash(payload),
    )
    return EvaluationComputationResult(status=EvaluationComputationStatus.COMPUTED, evaluation=evaluation)


@dataclass(kw_only=True, frozen=True)
class ExperimentSpec:
    """将来のA/B/Ablation比較が同一条件を共有するための表現のみの
    Record(D0107 §14、Backtest Engine自体はここでは作らない)。
    Trading/Execution Constraint(§15)・Benchmark Contract(§16)は
    いずれもOpaqueなPolicy Reference文字列として保持する(実データ
    Fetch・Portfolio Logicは一切持たない)。"""

    experiment_id: str
    universe_definition_id: str
    information_cutoff_policy: str
    evaluation_contract_ids: tuple[str, ...] = field(default_factory=tuple)
    benchmark_definition_id: str
    execution_policy_reference: str
    transaction_cost_policy_reference: str
    earliest_executable_time_policy_reference: str
    liquidity_eligibility_policy_reference: str
    corporate_action_handling_version: str
    variant_ids: tuple[str, ...] = field(default_factory=tuple)
    evaluation_window_start: datetime | None = None
    evaluation_window_end: datetime | None = None
    created_at: datetime
    record_hash: str

    def __post_init__(self) -> None:
        for name, value in (
            ("experiment_id", self.experiment_id),
            ("universe_definition_id", self.universe_definition_id),
            ("information_cutoff_policy", self.information_cutoff_policy),
            ("benchmark_definition_id", self.benchmark_definition_id),
            ("execution_policy_reference", self.execution_policy_reference),
            ("transaction_cost_policy_reference", self.transaction_cost_policy_reference),
            ("earliest_executable_time_policy_reference", self.earliest_executable_time_policy_reference),
            ("liquidity_eligibility_policy_reference", self.liquidity_eligibility_policy_reference),
            ("corporate_action_handling_version", self.corporate_action_handling_version),
            ("record_hash", self.record_hash),
        ):
            _require_nonempty_str(value, label=name)
        _require_tz_aware(self.created_at, label="created_at")
        if self.evaluation_window_start is not None:
            _require_tz_aware(self.evaluation_window_start, label="evaluation_window_start")
        if self.evaluation_window_end is not None:
            _require_tz_aware(self.evaluation_window_end, label="evaluation_window_end")


def build_experiment_spec(
    *,
    experiment_id: str,
    universe_definition_id: str,
    information_cutoff_policy: str,
    benchmark_definition_id: str,
    execution_policy_reference: str,
    transaction_cost_policy_reference: str,
    earliest_executable_time_policy_reference: str,
    liquidity_eligibility_policy_reference: str,
    corporate_action_handling_version: str,
    created_at: datetime,
    evaluation_contract_ids: Sequence[str] = (),
    variant_ids: Sequence[str] = (),
    evaluation_window_start: datetime | None = None,
    evaluation_window_end: datetime | None = None,
) -> ExperimentSpec:
    """`ExperimentSpec`を構築する唯一のEntrypoint(D0107 §14)。"""
    canonical_contract_ids = tuple(sorted(evaluation_contract_ids))
    canonical_variant_ids = tuple(sorted(variant_ids))
    payload = {
        "experiment_id": experiment_id,
        "universe_definition_id": universe_definition_id,
        "information_cutoff_policy": information_cutoff_policy,
        "evaluation_contract_ids": canonical_contract_ids,
        "benchmark_definition_id": benchmark_definition_id,
        "execution_policy_reference": execution_policy_reference,
        "transaction_cost_policy_reference": transaction_cost_policy_reference,
        "earliest_executable_time_policy_reference": earliest_executable_time_policy_reference,
        "liquidity_eligibility_policy_reference": liquidity_eligibility_policy_reference,
        "corporate_action_handling_version": corporate_action_handling_version,
        "variant_ids": canonical_variant_ids,
        "evaluation_window_start": evaluation_window_start,
        "evaluation_window_end": evaluation_window_end,
        "created_at": created_at,
    }
    return ExperimentSpec(
        experiment_id=experiment_id,
        universe_definition_id=universe_definition_id,
        information_cutoff_policy=information_cutoff_policy,
        evaluation_contract_ids=canonical_contract_ids,
        benchmark_definition_id=benchmark_definition_id,
        execution_policy_reference=execution_policy_reference,
        transaction_cost_policy_reference=transaction_cost_policy_reference,
        earliest_executable_time_policy_reference=earliest_executable_time_policy_reference,
        liquidity_eligibility_policy_reference=liquidity_eligibility_policy_reference,
        corporate_action_handling_version=corporate_action_handling_version,
        variant_ids=canonical_variant_ids,
        evaluation_window_start=evaluation_window_start,
        evaluation_window_end=evaluation_window_end,
        created_at=created_at,
        record_hash=compute_record_hash(payload),
    )


__all__ = [
    "BullBaseBearForecast",
    "DecisionRecord",
    "DecisionStatus",
    "EvaluationComputationResult",
    "EvaluationComputationStatus",
    "EvaluationContract",
    "EvaluationFoundationSchemaError",
    "EvaluationMetric",
    "EvaluationRecord",
    "ExperimentSpec",
    "ForecastShape",
    "PredictionRecord",
    "ResearchSnapshot",
    "ScalarForecast",
    "ThesisImpactReference",
    "build_decision_record",
    "build_evaluation_contract",
    "build_experiment_spec",
    "build_prediction_record",
    "build_research_snapshot",
    "evaluate_scalar_absolute_error",
    "forecast_family_key",
]
