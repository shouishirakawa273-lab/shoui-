"""D0110.4 paired arithmetic, preregistration, denominator and PIT tests."""

from __future__ import annotations

from dataclasses import fields, replace
from datetime import UTC, datetime, timedelta
from decimal import ROUND_DOWN, ROUND_UP, Decimal, getcontext, localcontext

import pytest
from lib.evaluation.integrity import compute_record_hash, verify_record_integrity
from lib.evaluation.model import (
    EvaluationMetric,
    ForecastShape,
    ScalarForecast,
    build_evaluation_contract,
    build_prediction_record,
    build_research_snapshot,
)
from lib.macro_events.model import build_macro_consensus_snapshot, build_macro_event, build_macro_first_release
from lib.macro_experiments.comparison import (
    MacroComparisonSample,
    compare_macro_forecasts,
    register_macro_plan,
)

T = datetime(2026, 1, 1, tzinfo=UTC)
H = timedelta(hours=1)


def rehash(record, **changes):
    updated = replace(record, **changes)
    payload = {f.name: getattr(updated, f.name) for f in fields(updated) if f.name != "record_hash"}
    return replace(updated, record_hash=compute_record_hash(payload))


def fixture(*, minimum=1, event_ids=("cpi",), synthetic=True):
    contract = build_evaluation_contract(
        evaluation_contract_id="c",
        evaluation_contract_version=1,
        target="HEADLINE_YOY",
        target_period="2026-01",
        actual_truth_description="Caller declared first release",
        metric=EvaluationMetric.ABSOLUTE_ERROR,
        evaluable_at_policy="release available and recorded",
        created_at=T,
    )
    plan = register_macro_plan(
        experiment_id="x",
        event_type="CPI",
        dimension="HEADLINE_YOY",
        unit="PERCENT",
        entity_id="US",
        model_version="v1",
        event_ids=event_ids,
        contracts=(contract,),
        minimum_samples=minimum,
        synthetic=synthetic,
        registered_at=T,
        window_start=T + H,
        window_end=T + 10 * H,
    )
    event = build_macro_event(
        event_id="cpi",
        event_type="CPI",
        jurisdiction="US",
        scheduled_at=T + 5 * H,
        event_period="2026-01",
        source_id="synthetic",
        schedule_available_at=T,
        created_at=T,
    )
    consensus = build_macro_consensus_snapshot(
        consensus_snapshot_id="cs",
        event_id="cpi",
        dimension="HEADLINE_YOY",
        value=Decimal("3.1"),
        unit="PERCENT",
        consensus_snapshot_at=T + 2 * H,
        available_at=T + 2 * H,
        created_at=T + 2 * H,
        provider="synthetic",
        source_id="synthetic",
    )
    release = build_macro_first_release(
        release_id="r",
        event_id="cpi",
        dimension="HEADLINE_YOY",
        actual_first_release=Decimal("3.3"),
        unit="PERCENT",
        actual_public_at=T + 5 * H,
        available_at=T + 5 * H,
        created_at=T + 5 * H,
        source_id="synthetic",
    )
    snapshot = build_research_snapshot(
        snapshot_id="s",
        entity_id="US",
        evidence_cutoff=T + 2 * H,
        research_artifact_id="a",
        research_artifact_version=1,
        created_at=T + 2 * H,
    )
    prediction = build_prediction_record(
        prediction_id="p",
        entity_id="US",
        target="HEADLINE_YOY",
        target_period="2026-01",
        forecast_shape=ForecastShape.SCALAR,
        scalar_forecast=ScalarForecast(value=Decimal("3.2"), unit="PERCENT"),
        created_at=T + 3 * H,
        evidence_cutoff=T + 2 * H,
        research_snapshot_id="s",
        model_version="v1",
        research_pipeline_version="synthetic",
        evaluation_contract_id="c",
    )
    return plan, MacroComparisonSample(
        event=event, consensus=consensus, release=release, prediction=prediction, snapshot=snapshot, synthetic=synthetic
    )


def test_paired_same_actual_arithmetic_and_provenance():
    plan, sample = fixture()
    original = (plan.record_hash, sample.prediction.record_hash)
    result = compare_macro_forecasts(plan=plan, samples=(sample,), evaluated_at=T + 6 * H)
    assert result.status == "DESCRIPTIVE_ONLY"
    assert (result.own_mae, result.consensus_mae, result.own_minus_consensus_mae) == (
        Decimal("0.1"),
        Decimal("0.2"),
        Decimal("-0.1"),
    )
    assert result.expected_samples == result.paired_samples == 1
    pair = result.samples[0]
    assert pair.own_evaluation.actual_reference == pair.consensus_evaluation.actual_reference == "r"
    assert pair.own_evaluation.actual_value == pair.consensus_evaluation.actual_value == Decimal("3.3")
    assert verify_record_integrity(result) and verify_record_integrity(pair.own_evaluation)
    assert pair.consensus_prediction.research_snapshot_id == pair.consensus_audit_snapshot.snapshot_id
    assert pair.consensus_prediction.research_snapshot_id != sample.snapshot.snapshot_id
    assert pair.consensus_audit_snapshot.research_artifact_id == sample.consensus.consensus_snapshot_id
    assert "NOT_INDEPENDENTLY_VERIFIED" in result.provenance_label
    assert "NO_PROMOTION" in result.interpretation
    assert original == (plan.record_hash, sample.prediction.record_hash)
    assert result == compare_macro_forecasts(plan=plan, samples=(sample,), evaluated_at=T + 6 * H)


def test_missing_event_remains_in_denominator_and_partial_is_not_complete():
    plan, sample = fixture(event_ids=("cpi", "missing"))
    result = compare_macro_forecasts(plan=plan, samples=(sample,), evaluated_at=T + 6 * H)
    assert result.expected_samples == 2 and result.paired_samples == 1
    assert result.samples[1].reasons == ("MISSING_EVENT",)
    assert result.status == "INSUFFICIENT_HISTORY"


def test_empty_history_and_minimum_are_explicit_policy():
    plan, sample = fixture(minimum=2)
    partial = compare_macro_forecasts(plan=plan, samples=(sample,), evaluated_at=T + 6 * H)
    empty = compare_macro_forecasts(plan=plan, samples=(), evaluated_at=T + 6 * H)
    assert partial.status == empty.status == "INSUFFICIENT_HISTORY"
    assert empty.own_mae is empty.consensus_mae is empty.own_minus_consensus_mae is None


def test_duplicate_event_is_rejected_not_double_counted():
    plan, sample = fixture()
    result = compare_macro_forecasts(plan=plan, samples=(sample, sample), evaluated_at=T + 6 * H)
    assert result.paired_samples == 0 and result.samples[0].reasons == ("DUPLICATE_EVENT",)


@pytest.mark.parametrize("name", ["consensus", "release", "prediction", "snapshot"])
def test_missing_records_have_explicit_reasons(name):
    plan, sample = fixture()
    sample = replace(sample, **{name: None})
    result = compare_macro_forecasts(plan=plan, samples=(sample,), evaluated_at=T + 6 * H)
    assert f"MISSING_{name.upper()}" in result.samples[0].reasons
    assert result.paired_samples == 0


def test_all_missing_reasons_are_retained():
    plan, sample = fixture()
    sample = replace(sample, consensus=None, release=None, prediction=None, snapshot=None)
    result = compare_macro_forecasts(plan=plan, samples=(sample,), evaluated_at=T + 6 * H)
    assert len(result.samples[0].reasons) == 4


@pytest.mark.parametrize(
    ("record", "changes", "reason"),
    [
        ("consensus", {"available_at": T + 5 * H}, "PRE_RELEASE_PIT_INVALID"),
        ("consensus", {"created_at": T + 5 * H}, "PRE_RELEASE_PIT_INVALID"),
        ("consensus", {"consensus_snapshot_at": T}, "FORECAST_PRECEDES_REGISTRATION"),
        ("prediction", {"created_at": T + 5 * H}, "PRE_RELEASE_PIT_INVALID"),
        ("prediction", {"created_at": T}, "FORECAST_PRECEDES_REGISTRATION"),
        ("prediction", {"model_version": "other"}, "MODEL_VERSION_MISMATCH"),
        ("prediction", {"research_snapshot_id": "other"}, "IDENTITY_MISMATCH"),
        ("prediction", {"target_period": "other"}, "IDENTITY_MISMATCH"),
        ("prediction", {"entity_id": "other"}, "IDENTITY_MISMATCH"),
        ("prediction", {"evaluation_contract_id": "other"}, "CONTRACT_MISMATCH"),
        ("prediction", {"parent_prediction_id": "parent"}, "REVISION_NOT_ALLOWED"),
        ("snapshot", {"evidence_cutoff": T + 3 * H}, "PRE_RELEASE_PIT_INVALID"),
        ("snapshot", {"created_at": T + 4 * H}, "PRE_RELEASE_PIT_INVALID"),
        ("release", {"created_at": T + 7 * H}, "ACTUAL_NOT_MATURE"),
        ("release", {"available_at": T + 7 * H}, "ACTUAL_NOT_MATURE"),
        ("release", {"available_at": T + 4 * H}, "ACTUAL_NOT_MATURE"),
        ("release", {"event_id": "other"}, "IDENTITY_MISMATCH"),
        ("release", {"dimension": "other"}, "IDENTITY_MISMATCH"),
        ("release", {"unit": "BASIS_POINT"}, "UNIT_MISMATCH"),
        ("release", {"actual_first_release": Decimal("NaN")}, "NONFINITE_VALUE"),
        ("consensus", {"value": Decimal("Infinity")}, "NONFINITE_VALUE"),
        ("event", {"event_type": "FOMC"}, "EVENT_TYPE_MISMATCH"),
    ],
)
def test_independent_failure_boundaries(record, changes, reason):
    plan, sample = fixture()
    sample = replace(sample, **{record: rehash(getattr(sample, record), **changes)})
    result = compare_macro_forecasts(plan=plan, samples=(sample,), evaluated_at=T + 6 * H)
    assert reason in result.samples[0].reasons
    assert result.paired_samples == 0


def test_tamper_and_mixed_modes_fail_closed():
    plan, sample = fixture()
    sample = replace(sample, synthetic=False, prediction=replace(sample.prediction, model_version="tampered"))
    result = compare_macro_forecasts(plan=plan, samples=(sample,), evaluated_at=T + 6 * H)
    assert {"INTEGRITY_PREDICTION", "MIXED_DATA_MODE"} <= set(result.samples[0].reasons)
    assert result.paired_samples == 0
    with pytest.raises(ValueError, match="integrity"):
        compare_macro_forecasts(plan=replace(plan, minimum_samples=100), samples=(), evaluated_at=T + 6 * H)


def test_naive_evaluation_rejected():
    plan, sample = fixture()
    with pytest.raises(ValueError, match="timezone"):
        compare_macro_forecasts(plan=plan, samples=(sample,), evaluated_at=datetime(2026, 1, 2))


def test_outside_roster_and_pre_registration_evaluation_rejected():
    plan, sample = fixture()
    with pytest.raises(ValueError, match="roster"):
        compare_macro_forecasts(
            plan=plan, samples=(replace(sample, event=rehash(sample.event, event_id="other")),), evaluated_at=T + 6 * H
        )
    with pytest.raises(ValueError, match="before registration"):
        compare_macro_forecasts(plan=plan, samples=(), evaluated_at=T - H)


def test_individual_forecast_nonfinite_and_wrong_unit():
    plan, sample = fixture()
    prediction = rehash(sample.prediction, scalar_forecast=ScalarForecast(value=Decimal("sNaN"), unit="BASIS_POINT"))
    result = compare_macro_forecasts(plan=plan, samples=(replace(sample, prediction=prediction),), evaluated_at=T + 6 * H)
    assert {"NONFINITE_VALUE", "UNIT_MISMATCH"} <= set(result.samples[0].reasons)


def test_release_outside_registered_window():
    plan, sample = fixture()
    experiment = rehash(plan.experiment, evaluation_window_end=T + 4 * H)
    plan = rehash(plan, experiment=experiment)
    result = compare_macro_forecasts(plan=plan, samples=(sample,), evaluated_at=T + 6 * H)
    assert "OUTSIDE_REGISTERED_WINDOW" in result.samples[0].reasons


@pytest.mark.parametrize("kwargs", [{"minimum": 0}, {"minimum": True}, {"event_ids": ("cpi", "cpi")}, {"synthetic": None}])
def test_invalid_registration(kwargs):
    with pytest.raises(ValueError):
        fixture(**kwargs)


@pytest.mark.parametrize("rounding", [ROUND_DOWN, ROUND_UP])
def test_fixed_context_controls_d0107_error_and_repeating_mae_without_mutating_caller(rounding):
    plan, original = fixture(event_ids=("cpi", "cpi2", "cpi3"))
    samples = []
    for i, event_id in enumerate(plan.event_ids):
        prediction = rehash(
            original.prediction,
            prediction_id=f"p{i}",
            scalar_forecast=ScalarForecast(value=Decimal("3.123456789") if i == 0 else Decimal("3.1"), unit="PERCENT"),
        )
        samples.append(
            replace(
                original,
                event=rehash(original.event, event_id=event_id),
                consensus=rehash(original.consensus, event_id=event_id, consensus_snapshot_id=f"c{i}"),
                release=rehash(original.release, event_id=event_id, release_id=f"r{i}"),
                prediction=prediction,
            )
        )
    baseline = compare_macro_forecasts(plan=plan, samples=tuple(samples), evaluated_at=T + 6 * H)
    assert baseline.samples[0].own_evaluation.result_value == Decimal("0.176543211")
    with localcontext() as caller:
        caller.prec = 2
        caller.rounding = rounding
        caller.Emin, caller.Emax, caller.capitals, caller.clamp = -2, 2, 0, 1
        for signal in caller.traps:
            caller.traps[signal] = True
        for signal in caller.flags:
            caller.flags[signal] = True
        before = (
            caller.prec,
            caller.rounding,
            caller.Emin,
            caller.Emax,
            caller.capitals,
            caller.clamp,
            dict(caller.traps),
            dict(caller.flags),
        )
        changed = compare_macro_forecasts(plan=plan, samples=tuple(samples), evaluated_at=T + 6 * H)
        after = getcontext()
        assert before == (
            after.prec,
            after.rounding,
            after.Emin,
            after.Emax,
            after.capitals,
            after.clamp,
            dict(after.traps),
            dict(after.flags),
        )
    assert changed == baseline and changed.record_hash == baseline.record_hash
    assert changed.calculation_contract_version == "D0110_4_DECIMAL_50_HALF_EVEN_E999999_V1"
