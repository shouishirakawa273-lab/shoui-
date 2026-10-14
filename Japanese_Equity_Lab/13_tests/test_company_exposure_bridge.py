"""Synthetic company-labelled foundation: never actual SMM sensitivity values."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal, localcontext
from pathlib import Path

import pytest
from lib.company_exposure.bridge import baseline_input_hash, compute_exposure_bridge, increment_key
from lib.company_exposure.model import (
    DRIVER_UNITS,
    BaselineCoverage,
    BridgeRequest,
    BridgeStatus,
    CompanyExposure,
    CompositionDeclaration,
    DriverAssumption,
    ExposureCondition,
    ExposureSchemaError,
    ExposureSource,
)
from lib.company_exposure.store import CompanyExposureInputStore, CompanyExposureStore
from lib.errors import AppendOnlyViolationError
from lib.evaluation.integrity import verify_record_integrity
from lib.evidence.model import DataLayer, EvidenceRecord, EvidenceType
from lib.evidence.thesis_impact import ThesisScenario
from lib.forecasting.model import (
    AssumptionSource,
    ForecastAssumption,
    ForecastStatus,
    HistoricalFundamentalBase,
    ScenarioAssumptions,
)
from lib.sources.catalog import DataCapability, PrimaryOrSecondary, SourceAuthorityClass, SourceMetadata

T = datetime(2026, 10, 14, tzinfo=UTC)
OLD = T - timedelta(days=1)
START = T + timedelta(days=1)
END = START + timedelta(days=365)
D = Decimal


def evidence() -> EvidenceRecord:
    return EvidenceRecord(
        evidence_id="SYNTHETIC_E1",
        evidence_type=EvidenceType.CLAIM,
        layer=DataLayer.RAW,
        capability=DataCapability.FUNDAMENTAL,
        content="Synthetic company-labelled sensitivity; not actual disclosure",
        related_codes=("5713",),
        source=SourceMetadata(
            source_id="SYNTHETIC_SOURCE",
            source_type="COMPANY_IR",
            provider_name="synthetic",
            source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
            primary_or_secondary=PrimaryOrSecondary.PRIMARY,
            retrieved_at=OLD,
            published_at=OLD,
            available_at=OLD,
            source_url="https://example.invalid/fixture",
        ),
    )


def condition(driver: str, level: str = "100") -> ExposureCondition:
    return ExposureCondition(driver=driver, level=D(level), unit=DRIVER_UNITS[driver])


def exposure(driver: str = "COPPER", **kwargs: object) -> CompanyExposure:
    result = CompanyExposure(
        exposure_id=f"SYNTHETIC_{driver}",
        version="1",
        entity_id="5713",
        driver=driver,
        driver_unit=DRIVER_UNITS[driver],
        driver_step=D("10"),
        sensitivity_amount=D("20"),
        profit_unit="JPY",
        currency="JPY",
        profit_metric="OPERATING_INCOME",
        scope="CONSOLIDATED",
        forecast_period="FY_SYNTHETIC",
        applicable_from=START,
        applicable_until=END,
        minimum_level=D("1"),
        maximum_level=D("1000"),
        base_conditions=(condition(driver),),
        other_base_assumptions=(("hedging", "synthetic fixed"),),
        source_type=ExposureSource.COMPANY_DISCLOSED,
        source_id="SYNTHETIC_SOURCE",
        source_url="https://example.invalid/fixture",
        source_locator="synthetic table 1",
        evidence_ids=("SYNTHETIC_E1",),
        disclosed_at=OLD,
        available_at=OLD,
        interaction_group="synthetic-metals-fx",
        coverage_keys=(f"profit-effect:{driver}",),
        limitations="Synthetic linear fixture only; no real company evidence",
    )
    return replace(result, **kwargs, record_hash="") if kwargs else result


def assumption(name: str, value: str, *, evidence_derived: bool = False) -> ForecastAssumption:
    return ForecastAssumption(
        name=name,
        value=D(value),
        unit="PERCENT" if name != "OPERATING_INCOME" else "JPY",
        source=AssumptionSource.EVIDENCE_DERIVED if evidence_derived else AssumptionSource.RESEARCH_JUDGMENT,
        evidence_ids=("SYNTHETIC_E1",) if evidence_derived else (),
        rationale="synthetic baseline",
        created_at=OLD,
    )


def request(*, driver_names: tuple[str, ...] = ("COPPER",), evidence_derived: bool = False, **kwargs: object) -> BridgeRequest:
    exposures = tuple(exposure(d) for d in driver_names)
    drivers = tuple(
        DriverAssumption(
            assumption_id=f"D_{d}",
            entity_id="5713",
            forecast_period="FY_SYNTHETIC",
            scenario=ThesisScenario.BASE,
            driver=d,
            unit=DRIVER_UNITS[d],
            baseline_level=D("100"),
            scenario_level=D("110"),
            available_at=OLD,
            created_at=OLD,
            evidence_ids=("SYNTHETIC_E1",),
            rationale="synthetic explicit period level",
        )
        for d in driver_names
    )
    coverage = BaselineCoverage(
        entity_id="5713",
        forecast_period="FY_SYNTHETIC",
        scenario=ThesisScenario.BASE,
        levels=tuple(condition(d) for d in sorted(driver_names)),
        other_base_assumptions=(("hedging", "synthetic fixed"),),
        applied_increment_keys=(),
        complete=True,
        evidence_ids=("SYNTHETIC_E1",),
        rationale="synthetic complete baseline ledger",
        available_at=OLD,
        created_at=OLD,
    )
    scenarios = tuple(
        ScenarioAssumptions(
            scenario=s,
            assumptions=(
                assumption("REVENUE_GROWTH", "0", evidence_derived=evidence_derived),
                assumption("OPERATING_MARGIN", "10", evidence_derived=evidence_derived),
            ),
        )
        for s in ThesisScenario
        if s.value in ("BULL", "BASE", "BEAR")
    )
    base = HistoricalFundamentalBase(
        entity_id="5713",
        metric="REVENUE",
        period="PRIOR_SYNTHETIC",
        value=D("1000"),
        unit="JPY",
        currency="JPY",
        source_id="SYNTHETIC_SOURCE",
        available_at=OLD,
        provenance_ref="SYNTHETIC_E1",
    )
    result = BridgeRequest(
        request_id="BR1",
        entity_id="5713",
        forecast_period="FY_SYNTHETIC",
        scenario=ThesisScenario.BASE,
        period_start=START,
        period_end=END,
        evidence_cutoff=T,
        created_at=T,
        research_snapshot_id="SYNTHETIC_SNAPSHOT",
        exposures=exposures,
        drivers=drivers,
        coverage=coverage,
        baseline_scenarios=scenarios,
        historical_bases=(base,),
        evidence_records=(evidence(),),
    )
    result = replace(
        result,
        coverage=replace(coverage, baseline_input_hash=baseline_input_hash(scenarios, (base,)), record_hash=""),
        record_hash="",
    )
    return change(result, **kwargs) if kwargs else result


def change(req: BridgeRequest, **kwargs: object) -> BridgeRequest:
    updated = replace(req, **kwargs, record_hash="")
    if ("baseline_scenarios" in kwargs or "historical_bases" in kwargs) and "coverage" not in kwargs:
        updated = replace(
            updated,
            coverage=replace(
                updated.coverage,
                baseline_input_hash=baseline_input_hash(updated.baseline_scenarios, updated.historical_bases),
                record_hash="",
            ),
            record_hash="",
        )
    return updated


@pytest.mark.parametrize("driver", ["GOLD", "COPPER", "USDJPY"])
@pytest.mark.parametrize("level,expected", [("110", "120"), ("90", "80"), ("100", "100")])
def test_single_driver_actual_d0109_replay(driver: str, level: str, expected: str) -> None:
    req = request(driver_names=(driver,))
    req = change(req, drivers=(replace(req.drivers[0], scenario_level=D(level), record_hash=""),))
    original = req.record_hash
    result = compute_exposure_bridge(req)
    assert result.status is BridgeStatus.SUCCESS, result.reason
    assert result.target_operating_income_jpy == D(expected)
    assert result.replay_operating_income_jpy == D(expected)
    assert result.baseline_operating_income_jpy == D("100")
    assert result.replay_forecast is not None and result.replay_forecast.status is ForecastStatus.SUCCESS
    assert req.record_hash == original and verify_record_integrity(req) and verify_record_integrity(result)
    for scenario in result.adjusted_scenarios:
        if scenario.scenario is not ThesisScenario.BASE:
            assert scenario in req.baseline_scenarios


def test_evidence_derived_and_judgment_are_not_conflated() -> None:
    req = request(evidence_derived=True)
    result = compute_exposure_bridge(req)
    margin = next(
        a
        for s in result.adjusted_scenarios
        if s.scenario is ThesisScenario.BASE
        for a in s.assumptions
        if a.name == "OPERATING_MARGIN"
    )
    assert margin.source is AssumptionSource.EVIDENCE_DERIVED and margin.evidence_ids
    req = change(req, drivers=(replace(req.drivers[0], is_research_judgment=True, evidence_ids=(), record_hash=""),))
    result = compute_exposure_bridge(req)
    margin = next(
        a
        for s in result.adjusted_scenarios
        if s.scenario is ThesisScenario.BASE
        for a in s.assumptions
        if a.name == "OPERATING_MARGIN"
    )
    assert margin.source is AssumptionSource.RESEARCH_JUDGMENT and not margin.evidence_ids
    assert any(i.startswith("evidence:") for i, _ in result.input_refs)


@pytest.mark.parametrize("unit,amount", [("JPY", "20"), ("JPY_MILLION", "0.00002"), ("JPY_BILLION", "0.00000002")])
def test_explicit_money_scale(unit: str, amount: str) -> None:
    result = compute_exposure_bridge(request(exposures=(exposure(profit_unit=unit, sensitivity_amount=D(amount)),)))
    assert result.status is BridgeStatus.SUCCESS and result.target_operating_income_jpy == D("120")


@pytest.mark.parametrize(
    "field,value,status",
    [
        ("profit_metric", "PRETAX_INCOME", BridgeStatus.UNSUPPORTED_METRIC),
        ("profit_metric", "NET_INCOME", BridgeStatus.UNSUPPORTED_METRIC),
        ("scope", "SEGMENT", BridgeStatus.UNSUPPORTED_METRIC),
        ("entity_id", "OTHER", BridgeStatus.IDENTITY_MISMATCH),
        ("forecast_period", "OTHER", BridgeStatus.IDENTITY_MISMATCH),
        ("affects_revenue", True, BridgeStatus.UNSUPPORTED_REVENUE_EFFECT),
        ("source_type", ExposureSource.STATISTICALLY_ESTIMATED, BridgeStatus.UNSUPPORTED_SOURCE),
        ("source_type", ExposureSource.RESEARCH_JUDGMENT, BridgeStatus.UNSUPPORTED_SOURCE),
        ("available_at", T + timedelta(seconds=1), BridgeStatus.PIT_INVALID),
        ("applicable_from", START + timedelta(seconds=1), BridgeStatus.IDENTITY_MISMATCH),
        ("applicable_until", END - timedelta(seconds=1), BridgeStatus.IDENTITY_MISMATCH),
        ("maximum_level", D("105"), BridgeStatus.OUTSIDE_SENSITIVITY_RANGE),
        ("source_id", "WRONG", BridgeStatus.UNSUPPORTED_SOURCE),
    ],
)
def test_exposure_failures_keep_audit(field: str, value: object, status: BridgeStatus) -> None:
    req = request(exposures=(exposure(**{field: value}),))
    result = compute_exposure_bridge(req)
    assert result.status is status, result.reason
    assert result.audit and not result.adjusted_scenarios and result.replay_forecast is None


@pytest.mark.parametrize("kind", ["request", "driver", "coverage", "evidence", "baseline"])
def test_pit_future_inputs_rejected(kind: str) -> None:
    req = request()
    future = T + timedelta(seconds=1)
    if kind == "request":
        req = change(req, created_at=future)
    elif kind == "driver":
        req = change(req, drivers=(replace(req.drivers[0], created_at=future, record_hash=""),))
    elif kind == "coverage":
        req = change(req, coverage=replace(req.coverage, available_at=future, record_hash=""))
    elif kind == "evidence":
        req = change(req, evidence_records=(replace(evidence(), source=replace(evidence().source, retrieved_at=future)),))
    else:
        scenarios = tuple(
            replace(s, assumptions=tuple(replace(a, created_at=future) for a in s.assumptions)) for s in req.baseline_scenarios
        )
        req = change(req, baseline_scenarios=scenarios)
    assert compute_exposure_bridge(req).status is BridgeStatus.PIT_INVALID


@pytest.mark.parametrize("kind", ["none", "future", "duplicate", "wrong-company", "secondary"])
def test_source_evidence_fail_closed(kind: str) -> None:
    ev = evidence()
    if kind == "none":
        records = ()
    elif kind == "future":
        records = (replace(ev, source=replace(ev.source, published_at=None)),)
    elif kind == "duplicate":
        records = (ev, ev)
    elif kind == "wrong-company":
        records = (replace(ev, related_codes=("OTHER",)),)
    else:
        records = (replace(ev, source=replace(ev.source, primary_or_secondary=PrimaryOrSecondary.SECONDARY)),)
    result = compute_exposure_bridge(request(evidence_records=records))
    assert result.status is not BridgeStatus.SUCCESS
    assert result.audit and not result.adjusted_scenarios


def test_unknown_baseline_is_not_zero_and_reapplication_rejected() -> None:
    req = request()
    incomplete = change(req, coverage=replace(req.coverage, complete=False, record_hash=""))
    assert compute_exposure_bridge(incomplete).status is BridgeStatus.UNKNOWN_BASELINE_COVERAGE
    key = increment_key(req, req.exposures[0], req.drivers[0])
    already = change(req, coverage=replace(req.coverage, applied_increment_keys=(key,), record_hash=""))
    assert compute_exposure_bridge(already).status is BridgeStatus.DOUBLE_COUNT_RISK


def test_multiple_drivers_need_exact_source_backed_composition() -> None:
    req = request(driver_names=("GOLD", "COPPER", "USDJPY"))
    assert compute_exposure_bridge(req).status is BridgeStatus.DOUBLE_COUNT_RISK
    composition = CompositionDeclaration(
        exposure_ids=tuple(sorted(e.exposure_id for e in req.exposures)),
        joint_conditions=tuple(condition(d, "110") for d in sorted(DRIVER_UNITS)),
        evidence_ids=("SYNTHETIC_E1",),
        rationale="synthetic explicit joint applicability",
        available_at=OLD,
        created_at=OLD,
    )
    req = change(req, composition=composition)
    result = compute_exposure_bridge(req)
    assert result.status is BridgeStatus.SUCCESS and result.target_operating_income_jpy == D("160")
    incomplete = change(req, composition=replace(composition, exposure_ids=("OTHER",), record_hash=""))
    assert compute_exposure_bridge(incomplete).status is BridgeStatus.IDENTITY_MISMATCH
    overlapping = change(req, exposures=tuple(replace(e, coverage_keys=("same-effect",), record_hash="") for e in req.exposures))
    assert compute_exposure_bridge(overlapping).status is BridgeStatus.DOUBLE_COUNT_RISK


def test_conditional_fx_requires_joint_contract() -> None:
    req = request(driver_names=("COPPER", "USDJPY"))
    metals = replace(req.exposures[0], base_conditions=(condition("COPPER"), condition("USDJPY")), record_hash="")
    comp = CompositionDeclaration(
        exposure_ids=tuple(sorted(e.exposure_id for e in req.exposures)),
        joint_conditions=(),
        evidence_ids=("SYNTHETIC_E1",),
        rationale="not enough joint applicability",
        available_at=OLD,
        created_at=OLD,
    )
    result = compute_exposure_bridge(change(req, exposures=(metals, req.exposures[1]), composition=comp))
    assert result.status is BridgeStatus.DOUBLE_COUNT_RISK
    comp = replace(comp, joint_conditions=(condition("USDJPY", "110"),), record_hash="")
    assert (
        compute_exposure_bridge(change(req, exposures=(metals, req.exposures[1]), composition=comp)).status
        is BridgeStatus.SUCCESS
    )


@pytest.mark.parametrize(
    "kind", ["missing-scenario", "bad-override", "zero-revenue", "negative-income", "over100", "bad-base-condition"]
)
def test_invalid_baselines_and_targets_fail_closed(kind: str) -> None:
    req = request()
    if kind == "missing-scenario":
        req = change(req, baseline_scenarios=req.baseline_scenarios[:1])
    elif kind == "bad-override":
        scenarios = tuple(
            replace(s, assumptions=(*s.assumptions, assumption("OPERATING_INCOME", "999"))) for s in req.baseline_scenarios
        )
        req = change(req, baseline_scenarios=scenarios)
    elif kind == "zero-revenue":
        req = change(req, historical_bases=(replace(req.historical_bases[0], value=D(0)),))
    elif kind == "negative-income":
        req = change(req, exposures=(exposure(sensitivity_amount=D("-1000")),))
    elif kind == "over100":
        req = change(req, exposures=(exposure(sensitivity_amount=D("1000")),))
    else:
        req = change(req, coverage=replace(req.coverage, levels=(condition("COPPER", "99"),), record_hash=""))
    result = compute_exposure_bridge(req)
    assert result.status is not BridgeStatus.SUCCESS and not result.adjusted_scenarios


def test_matching_override_is_replaced_alongside_margin() -> None:
    req = request()
    scenarios = tuple(
        replace(s, assumptions=(*s.assumptions, assumption("OPERATING_INCOME", "100"))) for s in req.baseline_scenarios
    )
    result = compute_exposure_bridge(change(req, baseline_scenarios=scenarios))
    assert result.status is BridgeStatus.SUCCESS, result.reason
    assert result.replay_forecast is not None and result.replay_forecast.status is ForecastStatus.SUCCESS


def test_context_independence_and_rounding_audit() -> None:
    req = request(historical_bases=(replace(request().historical_bases[0], value=D("997")),))
    results = []
    for precision in (6, 28, 90):
        with localcontext() as context:
            context.prec = precision
            results.append(compute_exposure_bridge(req))
    assert all(r == results[0] for r in results)
    assert results[0].status is BridgeStatus.SUCCESS and results[0].rounding_difference_jpy is not None


def test_order_independence_and_observation_refs_do_not_set_period_levels() -> None:
    req = request(driver_names=("GOLD", "COPPER"))
    reverse = change(
        req,
        exposures=tuple(reversed(req.exposures)),
        drivers=tuple(reversed(req.drivers)),
        baseline_scenarios=tuple(reversed(req.baseline_scenarios)),
    )
    assert req.record_hash == reverse.record_hash
    req = request(observed_response_refs=(("OBS1", "hash-audit-only"),))
    result = compute_exposure_bridge(req)
    assert result.target_operating_income_jpy == D("120")
    assert ("observed_audit_only:OBS1", "hash-audit-only") in result.input_refs


def test_constructed_tampering_is_not_repaired() -> None:
    req = request()
    old_hash = req.exposures[0].record_hash
    object.__setattr__(req.exposures[0], "sensitivity_amount", D("300"))
    result = compute_exposure_bridge(req)
    assert result.status is BridgeStatus.INTEGRITY_ERROR
    assert req.exposures[0].record_hash == old_hash
    assert result.audit[0].disposition == "NOT_EVALUATED"


@pytest.mark.parametrize(
    "field,value",
    [
        ("driver_step", D(0)),
        ("sensitivity_amount", D("NaN")),
        ("profit_unit", "USD"),
        ("driver_unit", "percent"),
        ("disclosed_at", T.replace(tzinfo=None)),
    ],
)
def test_schema_invalid_input_rejected(field: str, value: object) -> None:
    with pytest.raises(ExposureSchemaError):
        exposure(**{field: value})


def test_store_roundtrip_idempotency_and_explicit_correction(tmp_path: Path) -> None:
    inputs = CompanyExposureInputStore(tmp_path / "inputs.jsonl")
    store = CompanyExposureStore(tmp_path / "results.jsonl", input_store=inputs)
    req = request()
    inputs.record(req)
    result = compute_exposure_bridge(req)
    assert store.record(result) == result
    assert store.record(result) == result and len(store.all()) == 1
    correction_req = change(req, request_id="BR2", supersedes_result_id="BR1")
    inputs.record(correction_req)
    correction = compute_exposure_bridge(correction_req)
    assert store.record(correction) == correction and len(store.all()) == 2
    with pytest.raises(ExposureSchemaError):
        store.record(replace(result, reason="different", record_hash=""))
    missing = change(req, request_id="BR3", supersedes_result_id="MISSING")
    inputs.record(missing)
    with pytest.raises(AppendOnlyViolationError):
        store.record(compute_exposure_bridge(missing))


@pytest.mark.parametrize("kind", ["empty-hash", "numeric", "nested-hash"])
def test_store_rejects_raw_payload_tampering(tmp_path: Path, kind: str) -> None:
    path = tmp_path / "results.jsonl"
    inputs = CompanyExposureInputStore(tmp_path / "inputs.jsonl")
    store = CompanyExposureStore(path, input_store=inputs)
    req = request()
    inputs.record(req)
    store.record(compute_exposure_bridge(req))
    data = json.loads(path.read_text(encoding="utf-8"))
    if kind == "empty-hash":
        data["record_hash"] = ""
    elif kind == "numeric":
        data["audit"][0]["delta_jpy"] = "999"
    else:
        data["replay_forecast"]["record_hash"] = ""
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ExposureSchemaError):
        store.all()


def test_stale_coverage_cannot_attach_to_another_baseline() -> None:
    req = request()
    changed_base = replace(req.historical_bases[0], value=D("2000"))
    # Deliberately preserve the old ledger instead of attesting a new one.
    stale = replace(req, historical_bases=(changed_base,), record_hash="")
    assert compute_exposure_bridge(stale).status is BridgeStatus.UNKNOWN_BASELINE_COVERAGE


def test_decimal_display_scale_does_not_allow_reapplication() -> None:
    req = request()
    key = increment_key(req, req.exposures[0], req.drivers[0])
    rescaled = replace(req.drivers[0], baseline_level=D("100.000"), scenario_level=D("110.0"), record_hash="")
    req = change(req, drivers=(rescaled,), coverage=replace(req.coverage, applied_increment_keys=(key,), record_hash=""))
    assert increment_key(req, req.exposures[0], rescaled) == key
    assert compute_exposure_bridge(req).status is BridgeStatus.DOUBLE_COUNT_RISK


@pytest.mark.parametrize("amount,expected", [("20", BridgeStatus.SUCCESS), ("21", BridgeStatus.UNSUPPORTED_SOURCE)])
def test_unit_derivation_requires_numeric_original(amount: str, expected: BridgeStatus) -> None:
    derived = exposure(
        source_type=ExposureSource.DETERMINISTIC_DERIVED,
        conversion_rule="EXPLICIT_DECIMAL_UNIT_SCALE_ONLY",
        sensitivity_amount=D(amount),
        disclosed_sensitivity_amount=D("0.00002"),
        disclosed_profit_unit="JPY_MILLION",
    )
    assert compute_exposure_bridge(request(exposures=(derived,))).status is expected


def test_quantum_precision_failure_has_no_successful_assumptions() -> None:
    req = request()
    req = change(
        req,
        historical_bases=(replace(req.historical_bases[0], value=D("1e40")),),
        exposures=(exposure(sensitivity_amount=D("2e11")),),
    )
    result = compute_exposure_bridge(req)
    assert result.status is BridgeStatus.PRECISION_INCOMPATIBLE and not result.adjusted_scenarios
    assert result.audit[0].delta_jpy == D("2e11")
    assert result.target_operating_income_jpy is not None and result.replay_operating_income_jpy is not None
    assert result.rounding_difference_jpy == D("-2e11")


def test_partial_adoption_audit_survives_later_rejection() -> None:
    req = request(driver_names=("COPPER", "GOLD"))
    composition = CompositionDeclaration(
        exposure_ids=tuple(e.exposure_id for e in req.exposures),
        joint_conditions=(),
        evidence_ids=("SYNTHETIC_E1",),
        rationale="synthetic composition",
        available_at=OLD,
        created_at=OLD,
    )
    req = change(
        req, composition=composition, exposures=(req.exposures[0], replace(req.exposures[1], scope="SEGMENT", record_hash=""))
    )
    result = compute_exposure_bridge(req)
    assert result.status is BridgeStatus.UNSUPPORTED_METRIC
    assert [a.disposition for a in result.audit] == ["ADOPTED", "REJECTED"]


@pytest.mark.parametrize("kind", ["driver-before-evidence", "driver-creation", "naive-evidence"])
def test_input_chronology_is_not_backdated(kind: str) -> None:
    req = request()
    if kind == "driver-before-evidence":
        req = change(req, drivers=(replace(req.drivers[0], available_at=OLD - timedelta(seconds=1), record_hash=""),))
    elif kind == "driver-creation":
        req = change(req, drivers=(replace(req.drivers[0], created_at=OLD - timedelta(seconds=1), record_hash=""),))
    else:
        with pytest.raises(ValueError):
            replace(evidence().source, available_at=OLD.replace(tzinfo=None))
        return
    assert compute_exposure_bridge(req).status is BridgeStatus.PIT_INVALID


def test_inputs_and_results_are_reconstructable_and_bound(tmp_path: Path) -> None:
    inputs = CompanyExposureInputStore(tmp_path / "inputs.jsonl")
    results = CompanyExposureStore(tmp_path / "results.jsonl", input_store=inputs)
    req = request()
    result = compute_exposure_bridge(req)
    with pytest.raises(ExposureSchemaError):
        results.record(result)
    assert inputs.record(req) == req and inputs.record(req) == req
    assert inputs.get(req.request_id) == req
    results.record(result)
    with pytest.raises(AppendOnlyViolationError):
        inputs.record(change(req, drivers=(replace(req.drivers[0], scenario_level=D("120"), record_hash=""),)))
    data = json.loads((tmp_path / "results.jsonl").read_text(encoding="utf-8"))
    data["target_operating_income_jpy"] = "121"
    from lib.evaluation.integrity import compute_record_hash

    data["record_hash"] = compute_record_hash(data)
    (tmp_path / "results.jsonl").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ExposureSchemaError, match="reproduce"):
        results.all()


def test_request_restore_rejects_nested_order_repair(tmp_path: Path) -> None:
    inputs = CompanyExposureInputStore(tmp_path / "inputs.jsonl")
    inputs.record(request())
    data = json.loads((tmp_path / "inputs.jsonl").read_text(encoding="utf-8"))
    data["baseline_scenarios"].reverse()
    (tmp_path / "inputs.jsonl").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ExposureSchemaError, match="hash"):
        inputs.get("BR1")


def test_correction_with_different_entity_or_earlier_time_is_rejected(tmp_path: Path) -> None:
    inputs = CompanyExposureInputStore(tmp_path / "inputs.jsonl")
    results = CompanyExposureStore(tmp_path / "results.jsonl", input_store=inputs)
    req = request()
    inputs.record(req)
    results.record(compute_exposure_bridge(req))
    for req2 in (
        change(req, request_id="BR_EARLY", created_at=OLD, supersedes_result_id="BR1"),
        change(req, request_id="BR_OTHER", entity_id="OTHER", supersedes_result_id="BR1"),
    ):
        inputs.record(req2)
        with pytest.raises(AppendOnlyViolationError):
            results.record(compute_exposure_bridge(req2))


@pytest.mark.parametrize("kind", ["wrong-url", "opinion"])
def test_company_source_reference_cannot_be_substituted(kind: str) -> None:
    ev = evidence()
    ev = (
        replace(ev, source=replace(ev.source, source_url="https://example.invalid/other"))
        if kind == "wrong-url"
        else replace(ev, evidence_type=EvidenceType.OPINION)
    )
    assert compute_exposure_bridge(request(evidence_records=(ev,))).status is BridgeStatus.UNSUPPORTED_SOURCE


@pytest.mark.parametrize("target", ["inputs", "results"])
def test_stored_duplicate_ids_are_not_silently_selected(tmp_path: Path, target: str) -> None:
    inputs = CompanyExposureInputStore(tmp_path / "inputs.jsonl")
    results = CompanyExposureStore(tmp_path / "results.jsonl", input_store=inputs)
    req = request()
    inputs.record(req)
    results.record(compute_exposure_bridge(req))
    path = tmp_path / f"{target}.jsonl"
    content = path.read_text(encoding="utf-8")
    path.write_text(content + content, encoding="utf-8")
    with pytest.raises(ExposureSchemaError, match="duplicate"):
        results.get("BR1")


def test_decimal_overflow_is_a_typed_failure() -> None:
    result = compute_exposure_bridge(request(exposures=(exposure(sensitivity_amount=D("1e999999")),)))
    assert result.status is BridgeStatus.PRECISION_INCOMPATIBLE and result.audit and not result.adjusted_scenarios
