"""Explicit-input paired comparison; no data fetching or automatic promotion.

Hashes establish internal integrity, not the truth of caller-provided provenance.
First-release authenticity and historical system observation require external evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from lib.evaluation.integrity import compute_record_hash, verify_record_integrity
from lib.evaluation.model import (
    EvaluationContract,
    EvaluationMetric,
    EvaluationRecord,
    ExperimentSpec,
    ForecastShape,
    PredictionRecord,
    ResearchSnapshot,
    ScalarForecast,
    build_experiment_spec,
    build_prediction_record,
    build_research_snapshot,
    evaluate_scalar_absolute_error,
)
from lib.macro_events.model import SUPPORTED_EVENT_TYPES, MacroConsensusSnapshot, MacroEvent, MacroFirstRelease


def _aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone-aware timestamp required")


@dataclass(frozen=True, kw_only=True)
class RegisteredMacroPlan:
    experiment: ExperimentSpec
    event_type: str
    dimension: str
    unit: str
    entity_id: str
    model_version: str
    event_ids: tuple[str, ...]
    contracts: tuple[EvaluationContract, ...]
    minimum_samples: int
    synthetic: bool
    record_hash: str


def register_macro_plan(
    *,
    experiment_id: str,
    event_type: str,
    dimension: str,
    unit: str,
    entity_id: str,
    model_version: str,
    event_ids: tuple[str, ...],
    contracts: tuple[EvaluationContract, ...],
    minimum_samples: int,
    synthetic: bool,
    registered_at: datetime,
    window_start: datetime,
    window_end: datetime,
) -> RegisteredMacroPlan:
    """Freeze roster and user-selected sample policy before any forecasts exist."""
    for stamp in (registered_at, window_start, window_end):
        _aware(stamp)
    if not registered_at < window_start <= window_end:
        raise ValueError("registration must precede ordered evaluation window")
    if event_type not in SUPPORTED_EVENT_TYPES or any(not x for x in (dimension, unit, entity_id, model_version)):
        raise ValueError("unsupported event type or empty identity")
    if type(synthetic) is not bool or type(minimum_samples) is not int or minimum_samples < 1:
        raise ValueError("explicit synthetic flag and positive sample policy required")
    if not event_ids or len(set(event_ids)) != len(event_ids) or any(not x for x in event_ids):
        raise ValueError("nonempty unique event roster required")
    if not contracts or len({c.target_period for c in contracts}) != len(contracts):
        raise ValueError("one contract per target period required")
    if len({c.evaluation_contract_id for c in contracts}) != len(contracts):
        raise ValueError("duplicate contract identity")
    for contract in contracts:
        _aware(contract.created_at)
        if (
            not verify_record_integrity(contract)
            or contract.target != dimension
            or contract.metric is not EvaluationMetric.ABSOLUTE_ERROR
            or contract.created_at > registered_at
        ):
            raise ValueError("contract integrity, metric, target or preregistration mismatch")
    experiment = build_experiment_spec(
        experiment_id=experiment_id,
        universe_definition_id="EXPLICIT_EVENT_ROSTER",
        information_cutoff_policy="STRICTLY_BEFORE_FIRST_PUBLIC_RELEASE",
        benchmark_definition_id="EXPLICIT_CONSENSUS_SNAPSHOT",
        execution_policy_reference="NOT_APPLICABLE",
        transaction_cost_policy_reference="NOT_APPLICABLE",
        earliest_executable_time_policy_reference="NOT_APPLICABLE",
        liquidity_eligibility_policy_reference="NOT_APPLICABLE",
        corporate_action_handling_version="NOT_APPLICABLE",
        created_at=registered_at,
        evaluation_window_start=window_start,
        evaluation_window_end=window_end,
        evaluation_contract_ids=tuple(c.evaluation_contract_id for c in contracts),
        variant_ids=(model_version, "CONSENSUS"),
    )
    payload = dict(
        experiment=experiment,
        event_type=event_type,
        dimension=dimension,
        unit=unit,
        entity_id=entity_id,
        model_version=model_version,
        event_ids=tuple(sorted(event_ids)),
        contracts=tuple(sorted(contracts, key=lambda c: c.target_period)),
        minimum_samples=minimum_samples,
        synthetic=synthetic,
    )
    return RegisteredMacroPlan(**payload, record_hash=compute_record_hash(payload))  # type: ignore[arg-type]


@dataclass(frozen=True, kw_only=True)
class MacroComparisonSample:
    event: MacroEvent
    consensus: MacroConsensusSnapshot | None
    release: MacroFirstRelease | None
    prediction: PredictionRecord | None
    snapshot: ResearchSnapshot | None
    synthetic: bool


@dataclass(frozen=True, kw_only=True)
class SampleComparison:
    event_id: str
    reasons: tuple[str, ...]
    own_evaluation: EvaluationRecord | None = None
    consensus_evaluation: EvaluationRecord | None = None
    consensus_audit_snapshot: ResearchSnapshot | None = None
    consensus_prediction: PredictionRecord | None = None


@dataclass(frozen=True, kw_only=True)
class MacroComparisonResult:
    plan_hash: str
    evaluated_at: datetime
    status: str
    samples: tuple[SampleComparison, ...]
    expected_samples: int
    paired_samples: int
    own_mae: Decimal | None
    consensus_mae: Decimal | None
    own_minus_consensus_mae: Decimal | None
    synthetic: bool
    provenance_label: str
    interpretation: str
    record_hash: str


def _sample_reasons(plan: RegisteredMacroPlan, sample: MacroComparisonSample, at: datetime) -> list[str]:
    event, consensus, release, prediction, snapshot = (
        sample.event,
        sample.consensus,
        sample.release,
        sample.prediction,
        sample.snapshot,
    )
    reasons: list[str] = []
    for name, record in (
        ("EVENT", event),
        ("CONSENSUS", consensus),
        ("RELEASE", release),
        ("PREDICTION", prediction),
        ("SNAPSHOT", snapshot),
    ):
        if record is None:
            reasons.append(f"MISSING_{name}")
        elif not verify_record_integrity(record):
            reasons.append(f"INTEGRITY_{name}")
    if type(sample.synthetic) is not bool or sample.synthetic != plan.synthetic:
        reasons.append("MIXED_DATA_MODE")
    if event.event_type != plan.event_type:
        reasons.append("EVENT_TYPE_MISMATCH")
    if any(x is None for x in (consensus, release, prediction, snapshot)):
        return reasons
    assert consensus is not None and release is not None and prediction is not None and snapshot is not None
    stamps = (
        event.schedule_available_at,
        event.created_at,
        event.scheduled_at,
        consensus.consensus_snapshot_at,
        consensus.available_at,
        consensus.created_at,
        release.actual_public_at,
        release.available_at,
        release.created_at,
        prediction.created_at,
        prediction.evidence_cutoff,
        snapshot.created_at,
        snapshot.evidence_cutoff,
    )
    try:
        for stamp in stamps:
            _aware(stamp)
    except ValueError:
        return reasons + ["NAIVE_TIMESTAMP"]
    if (
        consensus.event_id != event.event_id
        or release.event_id != event.event_id
        or prediction.entity_id != plan.entity_id
        or snapshot.entity_id != prediction.entity_id
        or prediction.research_snapshot_id != snapshot.snapshot_id
        or prediction.target != plan.dimension
        or consensus.dimension != plan.dimension
        or release.dimension != plan.dimension
        or prediction.target_period != event.event_period
    ):
        reasons.append("IDENTITY_MISMATCH")
    if prediction.model_version != plan.model_version:
        reasons.append("MODEL_VERSION_MISMATCH")
    if prediction.parent_prediction_id is not None:
        reasons.append("REVISION_NOT_ALLOWED")
    scalar = prediction.scalar_forecast
    if prediction.forecast_shape is not ForecastShape.SCALAR or scalar is None:
        reasons.append("SCALAR_REQUIRED")
    if consensus.unit != plan.unit or release.unit != plan.unit or (scalar is not None and scalar.unit != plan.unit):
        reasons.append("UNIT_MISMATCH")
    values = [consensus.value, release.actual_first_release]
    if scalar is not None:
        values.append(scalar.value)
    if any(not isinstance(x, Decimal) or not x.is_finite() for x in values):
        reasons.append("NONFINITE_VALUE")
    registered = plan.experiment.created_at
    if not (registered < prediction.created_at and registered < consensus.consensus_snapshot_at):
        reasons.append("FORECAST_PRECEDES_REGISTRATION")
    public = release.actual_public_at
    if not (
        max(event.schedule_available_at, event.created_at) <= prediction.evidence_cutoff <= prediction.created_at < public
        and snapshot.evidence_cutoff == prediction.evidence_cutoff
        and snapshot.evidence_cutoff <= snapshot.created_at <= prediction.created_at
        and consensus.consensus_snapshot_at <= consensus.available_at < public
        and consensus.consensus_snapshot_at <= consensus.created_at < public
    ):
        reasons.append("PRE_RELEASE_PIT_INVALID")
    if release.available_at < public or release.created_at < public or max(release.available_at, release.created_at) > at:
        reasons.append("ACTUAL_NOT_MATURE")
    start, end = plan.experiment.evaluation_window_start, plan.experiment.evaluation_window_end
    assert start is not None and end is not None
    if not start <= public <= end:
        reasons.append("OUTSIDE_REGISTERED_WINDOW")
    contracts = [c for c in plan.contracts if c.target_period == event.event_period]
    if not contracts or prediction.evaluation_contract_id != contracts[0].evaluation_contract_id:
        reasons.append("CONTRACT_MISMATCH")
    return reasons


def compare_macro_forecasts(
    *,
    plan: RegisteredMacroPlan,
    samples: tuple[MacroComparisonSample, ...],
    evaluated_at: datetime,
) -> MacroComparisonResult:
    """Return every roster failure; never silently drop incomplete pairs.

    D0107 evaluates both arms against the same explicitly injected first-release
    record. Evidence records are not injected here, so no real PIT certification
    is issued, even if all timestamp and identity checks succeed.
    """
    _aware(evaluated_at)
    if not verify_record_integrity(plan) or not verify_record_integrity(plan.experiment):
        raise ValueError("plan integrity failure")
    if any(not verify_record_integrity(c) for c in plan.contracts):
        raise ValueError("contract integrity failure")
    if evaluated_at < plan.experiment.created_at:
        raise ValueError("evaluation before registration")
    if any(s.event.event_id not in plan.event_ids for s in samples):
        raise ValueError("sample outside registered roster")
    results: list[SampleComparison] = []
    for event_id in plan.event_ids:
        matches = [s for s in samples if s.event.event_id == event_id]
        if len(matches) != 1:
            results.append(SampleComparison(event_id=event_id, reasons=("MISSING_EVENT" if not matches else "DUPLICATE_EVENT",)))
            continue
        sample = matches[0]
        reasons = _sample_reasons(plan, sample, evaluated_at)
        if reasons:
            results.append(SampleComparison(event_id=event_id, reasons=tuple(reasons)))
            continue
        prediction, consensus, release = sample.prediction, sample.consensus, sample.release
        assert prediction is not None and consensus is not None and release is not None
        contract = next(c for c in plan.contracts if c.target_period == sample.event.event_period)
        # Derived reference to injected consensus, not own-model evidence.
        benchmark_snapshot = build_research_snapshot(
            snapshot_id=f"{plan.experiment.experiment_id}:derived-consensus:{consensus.consensus_snapshot_id}",
            entity_id=prediction.entity_id,
            evidence_cutoff=consensus.available_at,
            research_artifact_id=consensus.consensus_snapshot_id,
            research_artifact_version=1,
            created_at=max(consensus.created_at, consensus.available_at),
            research_schema_version="DERIVED_CONSENSUS_AUDIT_REFERENCE_V1",
        )
        benchmark = build_prediction_record(
            prediction_id=f"{plan.experiment.experiment_id}:consensus:{consensus.consensus_snapshot_id}",
            entity_id=prediction.entity_id,
            target=prediction.target,
            target_period=prediction.target_period,
            forecast_shape=ForecastShape.SCALAR,
            scalar_forecast=ScalarForecast(value=consensus.value, unit=consensus.unit),
            created_at=benchmark_snapshot.created_at,
            evidence_cutoff=benchmark_snapshot.evidence_cutoff,
            research_snapshot_id=benchmark_snapshot.snapshot_id,
            model_version="CONSENSUS",
            research_pipeline_version="D0110_4_EXPLICIT_CONSENSUS",
            evaluation_contract_id=contract.evaluation_contract_id,
        )
        evaluations = tuple(
            evaluate_scalar_absolute_error(
                evaluation_id=f"{plan.experiment.experiment_id}:{event_id}:{arm}",
                prediction=p,
                contract=contract,
                actual_value=release.actual_first_release,
                actual_reference=release.release_id,
                evaluated_at=evaluated_at,
            ).evaluation
            for arm, p in (("own", prediction), ("consensus", benchmark))
        )
        results.append(
            SampleComparison(
                event_id=event_id,
                reasons=(),
                own_evaluation=evaluations[0],
                consensus_evaluation=evaluations[1],
                consensus_audit_snapshot=benchmark_snapshot,
                consensus_prediction=benchmark,
            )
        )
    paired = [r for r in results if r.own_evaluation is not None and r.consensus_evaluation is not None]
    own = sum((r.own_evaluation.result_value for r in paired if r.own_evaluation is not None), Decimal(0))
    consensus_total = sum((r.consensus_evaluation.result_value for r in paired if r.consensus_evaluation is not None), Decimal(0))
    n = len(paired)
    payload = dict(
        plan_hash=plan.record_hash,
        evaluated_at=evaluated_at,
        status="DESCRIPTIVE_ONLY" if n >= plan.minimum_samples and n == len(plan.event_ids) else "INSUFFICIENT_HISTORY",
        samples=tuple(results),
        expected_samples=len(plan.event_ids),
        paired_samples=n,
        own_mae=own / n if n else None,
        consensus_mae=consensus_total / n if n else None,
        own_minus_consensus_mae=(own - consensus_total) / n if n else None,
        synthetic=plan.synthetic,
        provenance_label="EVIDENCE_NOT_INDEPENDENTLY_VERIFIED",
        interpretation="OBSERVATIONAL_ONLY; MINIMUM_SAMPLES_IS_USER_POLICY; NO_PROMOTION",
    )
    return MacroComparisonResult(**payload, record_hash=compute_record_hash(payload))  # type: ignore[arg-type]
