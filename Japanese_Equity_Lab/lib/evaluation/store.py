"""Append-Only Record Store: Minimal Repository-Local Persistence(D0107 §20)。

既存`lib.registry.research_artifact_registry.ResearchArtifactRegistry`/
`lib.registry.experiment_registry.ExperimentRegistry`/`lib.registry.
provenance.ProvenanceStore`と同じJSON Lines Append-Only Patternを
そのまま踏襲する(新しいPersistence機構は作らない)。D0107の6種類の
Record型それぞれに専用Classを作らず、`to_dict`/`from_dict`の変換
Functionのみを型ごとに注入する1つの汎用Classとして実装する
(「汎用的なDatabaseは作らない」という要件と、「6回の重複実装を避ける」
という既存の`lib.registry`群自体には無いが望ましい方針を両立させる)。

**重複ID Policy(D0107 §20)**: 既存3つのRegistry全てが採用する
Policy(Content同一か否かを問わず、同一IDのRecordを無条件でRejectする)
をそのまま踏襲する——Silent Dedupeは行わない(既存の明文化された
Policyを再利用するのみで、新しいPolicyは発明しない)。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Generic, TypeVar

from lib.errors import AppendOnlyViolationError
from lib.evaluation.model import (
    BullBaseBearForecast,
    DecisionRecord,
    DecisionStatus,
    EvaluationContract,
    EvaluationMetric,
    EvaluationRecord,
    ExperimentSpec,
    ForecastShape,
    PredictionRecord,
    ResearchSnapshot,
    ScalarForecast,
    ThesisImpactReference,
)
from lib.evidence.thesis_impact import ThesisScenario

T = TypeVar("T")


def _opt_iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _opt_dt(value: object) -> datetime | None:
    return datetime.fromisoformat(value) if isinstance(value, str) else None


class AppendOnlyRecordStore(Generic[T]):
    """JSON Lines形式で追記専用に記録する、汎用Append-Only Store。

    `id_of`/`to_dict`/`from_dict`を型ごとに注入することで、D0107の
    6種類のImmutable Record型(`ResearchSnapshot`/`PredictionRecord`/
    `DecisionRecord`/`EvaluationContract`/`EvaluationRecord`/
    `ExperimentSpec`)全てに同じStore実装を再利用する。Update/Overwrite
    Methodは一切提供しない(D0107 §20)。
    """

    def __init__(
        self,
        storage_path: Path,
        *,
        id_of: Callable[[T], str],
        to_dict: Callable[[T], dict[str, object]],
        from_dict: Callable[[dict[str, object]], T],
    ) -> None:
        self._storage_path = storage_path
        self._id_of = id_of
        self._to_dict = to_dict
        self._from_dict = from_dict
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, record: T) -> None:
        """`record`を追記する。同一IDが既に存在する場合は、Content
        同一か否かを問わず無条件で`AppendOnlyViolationError`にする
        (既存`lib.registry`群と同じPolicy、D0107 §20)。"""
        record_id = self._id_of(record)
        existing_ids = {self._id_of(r) for r in self.all()}
        if record_id in existing_ids:
            raise AppendOnlyViolationError(f"id={record_id!r} は既に記録されています(上書き不可)")
        line = json.dumps(self._to_dict(record), ensure_ascii=False)
        with self._storage_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def all(self) -> list[T]:
        if not self._storage_path.exists():
            return []
        records: list[T] = []
        with self._storage_path.open(encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if line:
                    records.append(self._from_dict(json.loads(line)))
        return records

    def get(self, record_id: str) -> T | None:
        for record in self.all():
            if self._id_of(record) == record_id:
                return record
        return None


# ============================================================
# ResearchSnapshot
# ============================================================


def _research_snapshot_to_dict(snapshot: ResearchSnapshot) -> dict[str, object]:
    return {
        "snapshot_id": snapshot.snapshot_id,
        "entity_id": snapshot.entity_id,
        "evidence_cutoff": snapshot.evidence_cutoff.isoformat(),
        "research_artifact_id": snapshot.research_artifact_id,
        "research_artifact_version": snapshot.research_artifact_version,
        "evidence_ids": list(snapshot.evidence_ids),
        "thesis_impact_references": [
            {"research_node_id": r.research_node_id, "scenario": r.scenario.value, "evidence_id": r.evidence_id}
            for r in snapshot.thesis_impact_references
        ],
        "research_schema_version": snapshot.research_schema_version,
        "created_at": snapshot.created_at.isoformat(),
        "record_hash": snapshot.record_hash,
    }


def _research_snapshot_from_dict(data: dict[str, object]) -> ResearchSnapshot:
    assert isinstance(data["evidence_ids"], list)  # noqa: S101 -- 自前Storeの既知Formatに対するNarrowing
    assert isinstance(data["thesis_impact_references"], list)  # noqa: S101
    return ResearchSnapshot(
        snapshot_id=str(data["snapshot_id"]),
        entity_id=str(data["entity_id"]),
        evidence_cutoff=datetime.fromisoformat(str(data["evidence_cutoff"])),
        research_artifact_id=str(data["research_artifact_id"]),
        research_artifact_version=int(data["research_artifact_version"]),  # type: ignore[call-overload]
        evidence_ids=tuple(data["evidence_ids"]),
        thesis_impact_references=tuple(
            ThesisImpactReference(
                research_node_id=str(r["research_node_id"]),
                scenario=ThesisScenario(r["scenario"]),
                evidence_id=str(r["evidence_id"]),
            )
            for r in data["thesis_impact_references"]
        ),
        research_schema_version=str(data["research_schema_version"]),
        created_at=datetime.fromisoformat(str(data["created_at"])),
        record_hash=str(data["record_hash"]),
    )


def new_research_snapshot_store(storage_path: Path) -> AppendOnlyRecordStore[ResearchSnapshot]:
    return AppendOnlyRecordStore(
        storage_path,
        id_of=lambda r: r.snapshot_id,
        to_dict=_research_snapshot_to_dict,
        from_dict=_research_snapshot_from_dict,
    )


# ============================================================
# PredictionRecord
# ============================================================


def _prediction_to_dict(prediction: PredictionRecord) -> dict[str, object]:
    return {
        "prediction_id": prediction.prediction_id,
        "entity_id": prediction.entity_id,
        "target": prediction.target,
        "target_period": prediction.target_period,
        "forecast_shape": prediction.forecast_shape.value,
        "scalar_forecast": (
            {"value": str(prediction.scalar_forecast.value), "unit": prediction.scalar_forecast.unit}
            if prediction.scalar_forecast is not None
            else None
        ),
        "bull_base_bear_forecast": (
            {
                "bull": str(prediction.bull_base_bear_forecast.bull),
                "base": str(prediction.bull_base_bear_forecast.base),
                "bear": str(prediction.bull_base_bear_forecast.bear),
                "unit": prediction.bull_base_bear_forecast.unit,
            }
            if prediction.bull_base_bear_forecast is not None
            else None
        ),
        "created_at": prediction.created_at.isoformat(),
        "evidence_cutoff": prediction.evidence_cutoff.isoformat(),
        "research_snapshot_id": prediction.research_snapshot_id,
        "model_version": prediction.model_version,
        "research_pipeline_version": prediction.research_pipeline_version,
        "prompt_version": prediction.prompt_version,
        "parent_prediction_id": prediction.parent_prediction_id,
        "evaluation_contract_id": prediction.evaluation_contract_id,
        "target_resolution_at": _opt_iso(prediction.target_resolution_at),
        "record_hash": prediction.record_hash,
    }


def _prediction_from_dict(data: dict[str, object]) -> PredictionRecord:
    scalar_raw = data["scalar_forecast"]
    bbb_raw = data["bull_base_bear_forecast"]
    scalar_forecast = (
        ScalarForecast(value=Decimal(str(scalar_raw["value"])), unit=str(scalar_raw["unit"]))  # type: ignore[index]
        if scalar_raw is not None
        else None
    )
    bull_base_bear_forecast = (
        BullBaseBearForecast(
            bull=Decimal(str(bbb_raw["bull"])),  # type: ignore[index]
            base=Decimal(str(bbb_raw["base"])),  # type: ignore[index]
            bear=Decimal(str(bbb_raw["bear"])),  # type: ignore[index]
            unit=str(bbb_raw["unit"]),  # type: ignore[index]
        )
        if bbb_raw is not None
        else None
    )
    return PredictionRecord(
        prediction_id=str(data["prediction_id"]),
        entity_id=str(data["entity_id"]),
        target=str(data["target"]),
        target_period=str(data["target_period"]),
        forecast_shape=ForecastShape(str(data["forecast_shape"])),
        scalar_forecast=scalar_forecast,
        bull_base_bear_forecast=bull_base_bear_forecast,
        created_at=datetime.fromisoformat(str(data["created_at"])),
        evidence_cutoff=datetime.fromisoformat(str(data["evidence_cutoff"])),
        research_snapshot_id=str(data["research_snapshot_id"]),
        model_version=str(data["model_version"]),
        research_pipeline_version=str(data["research_pipeline_version"]),
        prompt_version=(str(data["prompt_version"]) if data["prompt_version"] is not None else None),
        parent_prediction_id=(str(data["parent_prediction_id"]) if data["parent_prediction_id"] is not None else None),
        evaluation_contract_id=(str(data["evaluation_contract_id"]) if data["evaluation_contract_id"] is not None else None),
        target_resolution_at=_opt_dt(data["target_resolution_at"]),
        record_hash=str(data["record_hash"]),
    )


def new_prediction_store(storage_path: Path) -> AppendOnlyRecordStore[PredictionRecord]:
    return AppendOnlyRecordStore(
        storage_path, id_of=lambda r: r.prediction_id, to_dict=_prediction_to_dict, from_dict=_prediction_from_dict
    )


# ============================================================
# DecisionRecord
# ============================================================


def _decision_to_dict(decision: DecisionRecord) -> dict[str, object]:
    return {
        "decision_id": decision.decision_id,
        "created_at": decision.created_at.isoformat(),
        "entity_id": decision.entity_id,
        "research_snapshot_id": decision.research_snapshot_id,
        "prediction_ids": list(decision.prediction_ids),
        "decision_status": decision.decision_status.value,
        "decision_policy_version": decision.decision_policy_version,
        "record_hash": decision.record_hash,
    }


def _decision_from_dict(data: dict[str, object]) -> DecisionRecord:
    assert isinstance(data["prediction_ids"], list)  # noqa: S101
    return DecisionRecord(
        decision_id=str(data["decision_id"]),
        created_at=datetime.fromisoformat(str(data["created_at"])),
        entity_id=str(data["entity_id"]),
        research_snapshot_id=str(data["research_snapshot_id"]),
        prediction_ids=tuple(data["prediction_ids"]),
        decision_status=DecisionStatus(str(data["decision_status"])),
        decision_policy_version=str(data["decision_policy_version"]),
        record_hash=str(data["record_hash"]),
    )


def new_decision_store(storage_path: Path) -> AppendOnlyRecordStore[DecisionRecord]:
    return AppendOnlyRecordStore(
        storage_path, id_of=lambda r: r.decision_id, to_dict=_decision_to_dict, from_dict=_decision_from_dict
    )


# ============================================================
# EvaluationContract
# ============================================================


def _evaluation_contract_to_dict(contract: EvaluationContract) -> dict[str, object]:
    return {
        "evaluation_contract_id": contract.evaluation_contract_id,
        "evaluation_contract_version": contract.evaluation_contract_version,
        "target": contract.target,
        "target_period": contract.target_period,
        "actual_truth_description": contract.actual_truth_description,
        "metric": contract.metric.value,
        "evaluable_at_policy": contract.evaluable_at_policy,
        "horizon_rule": contract.horizon_rule,
        "created_at": contract.created_at.isoformat(),
        "record_hash": contract.record_hash,
    }


def _evaluation_contract_from_dict(data: dict[str, object]) -> EvaluationContract:
    return EvaluationContract(
        evaluation_contract_id=str(data["evaluation_contract_id"]),
        evaluation_contract_version=int(data["evaluation_contract_version"]),  # type: ignore[call-overload]
        target=str(data["target"]),
        target_period=str(data["target_period"]),
        actual_truth_description=str(data["actual_truth_description"]),
        metric=EvaluationMetric(str(data["metric"])),
        evaluable_at_policy=str(data["evaluable_at_policy"]),
        horizon_rule=(str(data["horizon_rule"]) if data["horizon_rule"] is not None else None),
        created_at=datetime.fromisoformat(str(data["created_at"])),
        record_hash=str(data["record_hash"]),
    )


def _evaluation_contract_composite_id(contract: EvaluationContract) -> str:
    """`evaluation_contract_id`単独ではなく`(evaluation_contract_id,
    evaluation_contract_version)`をIdentityとする。EvaluationContract
    はVersion間の共存(v1がv2作成後も生存し続けること)がD0107 §C/§18
    の必須要件であり、`evaluation_contract_id`単独Keyでは同一IDの
    新Versionを追記するたびAppendOnlyViolationErrorになってしまう
    (Versioningという本Recordの存在意義そのものと矛盾する)。"""
    return f"{contract.evaluation_contract_id}::v{contract.evaluation_contract_version}"


def new_evaluation_contract_store(storage_path: Path) -> AppendOnlyRecordStore[EvaluationContract]:
    return AppendOnlyRecordStore(
        storage_path,
        id_of=_evaluation_contract_composite_id,
        to_dict=_evaluation_contract_to_dict,
        from_dict=_evaluation_contract_from_dict,
    )


# ============================================================
# EvaluationRecord
# ============================================================


def _evaluation_record_to_dict(evaluation: EvaluationRecord) -> dict[str, object]:
    return {
        "evaluation_id": evaluation.evaluation_id,
        "prediction_id": evaluation.prediction_id,
        "evaluation_contract_id": evaluation.evaluation_contract_id,
        "evaluation_contract_version": evaluation.evaluation_contract_version,
        "evaluated_at": evaluation.evaluated_at.isoformat(),
        "actual_reference": evaluation.actual_reference,
        "actual_value": str(evaluation.actual_value),
        "result_value": str(evaluation.result_value),
        "record_hash": evaluation.record_hash,
    }


def _evaluation_record_from_dict(data: dict[str, object]) -> EvaluationRecord:
    return EvaluationRecord(
        evaluation_id=str(data["evaluation_id"]),
        prediction_id=str(data["prediction_id"]),
        evaluation_contract_id=str(data["evaluation_contract_id"]),
        evaluation_contract_version=int(data["evaluation_contract_version"]),  # type: ignore[call-overload]
        evaluated_at=datetime.fromisoformat(str(data["evaluated_at"])),
        actual_reference=str(data["actual_reference"]),
        actual_value=Decimal(str(data["actual_value"])),
        result_value=Decimal(str(data["result_value"])),
        record_hash=str(data["record_hash"]),
    )


def new_evaluation_record_store(storage_path: Path) -> AppendOnlyRecordStore[EvaluationRecord]:
    return AppendOnlyRecordStore(
        storage_path, id_of=lambda r: r.evaluation_id, to_dict=_evaluation_record_to_dict, from_dict=_evaluation_record_from_dict
    )


# ============================================================
# ExperimentSpec
# ============================================================


def _experiment_spec_to_dict(spec: ExperimentSpec) -> dict[str, object]:
    return {
        "experiment_id": spec.experiment_id,
        "universe_definition_id": spec.universe_definition_id,
        "information_cutoff_policy": spec.information_cutoff_policy,
        "evaluation_contract_ids": list(spec.evaluation_contract_ids),
        "benchmark_definition_id": spec.benchmark_definition_id,
        "execution_policy_reference": spec.execution_policy_reference,
        "transaction_cost_policy_reference": spec.transaction_cost_policy_reference,
        "earliest_executable_time_policy_reference": spec.earliest_executable_time_policy_reference,
        "liquidity_eligibility_policy_reference": spec.liquidity_eligibility_policy_reference,
        "corporate_action_handling_version": spec.corporate_action_handling_version,
        "variant_ids": list(spec.variant_ids),
        "evaluation_window_start": _opt_iso(spec.evaluation_window_start),
        "evaluation_window_end": _opt_iso(spec.evaluation_window_end),
        "created_at": spec.created_at.isoformat(),
        "record_hash": spec.record_hash,
    }


def _experiment_spec_from_dict(data: dict[str, object]) -> ExperimentSpec:
    assert isinstance(data["evaluation_contract_ids"], list)  # noqa: S101
    assert isinstance(data["variant_ids"], list)  # noqa: S101
    return ExperimentSpec(
        experiment_id=str(data["experiment_id"]),
        universe_definition_id=str(data["universe_definition_id"]),
        information_cutoff_policy=str(data["information_cutoff_policy"]),
        evaluation_contract_ids=tuple(data["evaluation_contract_ids"]),
        benchmark_definition_id=str(data["benchmark_definition_id"]),
        execution_policy_reference=str(data["execution_policy_reference"]),
        transaction_cost_policy_reference=str(data["transaction_cost_policy_reference"]),
        earliest_executable_time_policy_reference=str(data["earliest_executable_time_policy_reference"]),
        liquidity_eligibility_policy_reference=str(data["liquidity_eligibility_policy_reference"]),
        corporate_action_handling_version=str(data["corporate_action_handling_version"]),
        variant_ids=tuple(data["variant_ids"]),
        evaluation_window_start=_opt_dt(data["evaluation_window_start"]),
        evaluation_window_end=_opt_dt(data["evaluation_window_end"]),
        created_at=datetime.fromisoformat(str(data["created_at"])),
        record_hash=str(data["record_hash"]),
    )


def new_experiment_spec_store(storage_path: Path) -> AppendOnlyRecordStore[ExperimentSpec]:
    return AppendOnlyRecordStore(
        storage_path, id_of=lambda r: r.experiment_id, to_dict=_experiment_spec_to_dict, from_dict=_experiment_spec_from_dict
    )


__all__ = [
    "AppendOnlyRecordStore",
    "new_decision_store",
    "new_evaluation_contract_store",
    "new_evaluation_record_store",
    "new_experiment_spec_store",
    "new_prediction_store",
    "new_research_snapshot_store",
]
