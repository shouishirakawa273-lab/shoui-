"""Synthetic calculations plus company table facts without fabricated PIT times."""

from __future__ import annotations

import ast
import json
from dataclasses import fields, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, localcontext
from pathlib import Path

import pytest
from lib.errors import AppendOnlyViolationError
from lib.evaluation.integrity import compute_record_hash, verify_record_integrity
from lib.evidence.model import AvailabilityBasis
from lib.evidence.thesis_impact import ThesisScenario
from lib.profit_impact.calculation import compute_profit_impact, increment_key, normalize_sensitivity, request_context_hash
from lib.profit_impact.model import (
    ADAPTER_UNAVAILABLE,
    DRIVER_UNITS,
    Applicability,
    Direction,
    DriverShock,
    ImpactComposition,
    ImpactCoverage,
    ImpactSchemaError,
    ImpactStage,
    ImpactStatus,
    PretaxBaseline,
    ProfitImpactRequest,
    SourceArtifact,
    SourceDisclosureRecord,
)
from lib.profit_impact.store import ProfitImpactInputStore, ProfitImpactStore
from lib.sources.catalog import PrimaryOrSecondary, SourceAuthorityClass

D = Decimal
T = datetime(2026, 10, 14, tzinfo=UTC)
OLD = T - timedelta(days=1)
SOURCE_URL = "https://example.invalid/synthetic-disclosure"


def artifact() -> SourceArtifact:
    return SourceArtifact(
        artifact_id="A1",
        source_url=SOURCE_URL,
        content="Synthetic company sensitivity and composition statement; NOT an actual company disclosure.",
    )


def source(driver: str = "COPPER", **kwargs: object) -> SourceDisclosureRecord:
    result = SourceDisclosureRecord(
        disclosure_id=f"SOURCE_{driver}",
        entity_id="5713",
        title="SYNTHETIC DISCLOSURE",
        forecast_period="SYNTHETIC_FY",
        forecast_version="SYNTHETIC_VERSION",
        scope="CONSOLIDATED",
        source_url=SOURCE_URL,
        pdf_page_index=0,
        printed_page="1",
        table_locator="synthetic table",
        artifact_id="A1",
        artifact_hash=artifact().record_hash,
        profit_metric="PRETAX_INCOME",
        profit_unit="JPY",
        currency="JPY",
        driver=driver,
        driver_unit=DRIVER_UNITS[driver],
        driver_step=D("10"),
        impact_magnitude=D("20"),
        direction=Direction.POSITIVE,
        direction_basis="synthetic source says higher driver increases pretax profit",
        applicability=Applicability.DISCLOSED_UNIT_ONLY,
        applicability_basis="synthetic disclosed one-unit shock",
        minimum_level=None,
        maximum_level=None,
        base_level=D("100"),
        inventory_treatment="EXCLUDED",
        fx_coverage="SYNTHETIC_FIXED",
        other_base_conditions=(("hedge", "unchanged"),),
        limitations="synthetic fixed conditions only",
        disclosed_on=date(2026, 8, 10),
        exact_public_at=None,
        retrieved_at=OLD,
        normalized_created_at=OLD,
        system_available_at=OLD,
        availability_basis=AvailabilityBasis.OBSERVED,
        values_verified=True,
        extraction_method_version="MANUAL_SYNTHETIC_V1",
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        primary_or_secondary=PrimaryOrSecondary.PRIMARY,
        publication_timezone="Asia/Tokyo",
    )
    return replace(result, **kwargs, record_hash="") if kwargs else result


def request(*, drivers: tuple[str, ...] = ("COPPER",), **kwargs: object) -> ProfitImpactRequest:
    sources = tuple(source(d) for d in drivers)
    sensitivities = tuple(
        normalize_sensitivity(s, sensitivity_id=f"S_{s.driver}", coverage_keys=(f"effect:{s.driver}",)) for s in sources
    )
    shocks = tuple(
        DriverShock(
            sensitivity_id=s.sensitivity_id,
            driver=s.driver,
            unit=s.driver_unit,
            change=D("10"),
            origin="RESEARCH_JUDGMENT",
            rationale="synthetic explicit annual assumption change",
            available_at=OLD,
            created_at=OLD,
            baseline_level=D("100"),
            scenario_level=D("110"),
        )
        for s in sensitivities
    )
    result = ProfitImpactRequest(
        request_id="R1",
        entity_id="5713",
        forecast_period="SYNTHETIC_FY",
        forecast_version="SYNTHETIC_VERSION",
        scenario=ThesisScenario.BASE,
        evidence_cutoff=T,
        created_at=T,
        artifacts=(artifact(),),
        disclosures=sources,
        sensitivities=sensitivities,
        shocks=shocks,
    )
    return change(result, **kwargs) if kwargs else result


def change(req: ProfitImpactRequest, **kwargs: object) -> ProfitImpactRequest:
    return replace(req, **kwargs, record_hash="")


def with_source(req: ProfitImpactRequest, new: SourceDisclosureRecord) -> ProfitImpactRequest:
    sensitivity = normalize_sensitivity(
        new, sensitivity_id=req.sensitivities[0].sensitivity_id, coverage_keys=req.sensitivities[0].coverage_keys
    )
    return change(req, disclosures=(new,), sensitivities=(sensitivity,))


def with_target(req: ProfitImpactRequest) -> ProfitImpactRequest:
    baseline = PretaxBaseline(
        baseline_id="B1",
        entity_id=req.entity_id,
        forecast_period=req.forecast_period,
        forecast_version=req.forecast_version,
        scope="CONSOLIDATED",
        profit_metric="PRETAX_INCOME",
        value_jpy=D("1000"),
        origin="COMPANY_GUIDANCE",
        driver_levels=tuple((s.driver, D("100")) for s in req.sensitivities),
        other_base_conditions=(("hedge", "unchanged"),),
        inventory_treatment="EXCLUDED",
        fx_coverage="SYNTHETIC_FIXED",
        source_ref="A1",
        available_at=OLD,
        created_at=OLD,
    )
    req = change(req, baseline=baseline)
    coverage = ImpactCoverage(
        baseline_hash=baseline.record_hash,
        request_context_hash=request_context_hash(req),
        applied_increment_keys=(),
        complete=True,
        source_ref="A1",
        rationale="synthetic complete baseline coverage",
        available_at=OLD,
        created_at=OLD,
    )
    return change(req, coverage=coverage)


@pytest.mark.parametrize("driver", ["GOLD", "COPPER", "USDJPY"])
@pytest.mark.parametrize(
    "direction,shock,expected",
    [
        (Direction.POSITIVE, "10", "20"),
        (Direction.POSITIVE, "-10", "-20"),
        (Direction.NEGATIVE, "10", "-20"),
        (Direction.NEGATIVE, "-10", "20"),
        (Direction.POSITIVE, "0", "0"),
    ],
)
def test_single_period_signed_delta(driver: str, direction: Direction, shock: str, expected: str) -> None:
    req = request(drivers=(driver,))
    req = with_source(req, source(driver, direction=direction))
    req = change(req, shocks=(replace(req.shocks[0], change=D(shock), scenario_level=D("100") + D(shock)),))
    original = req.record_hash
    result = compute_profit_impact(req)
    assert result.status is ImpactStatus.SUCCESS_SIGNED_DELTA, result.reason
    assert result.signed_delta_jpy == D(expected) and result.magnitude_delta_jpy == abs(D(expected))
    assert result.conditional_target_pretax_jpy is None and result.adapter_status == ADAPTER_UNAVAILABLE
    assert req.record_hash == original and verify_record_integrity(req) and verify_record_integrity(result)


def test_unknown_direction_withholds_signed_delta_and_target() -> None:
    req = with_source(request(), source(direction=Direction.UNKNOWN, direction_basis=None))
    result = compute_profit_impact(req)
    assert result.status is ImpactStatus.SUCCESS_MAGNITUDE_ONLY and result.stage is ImpactStage.MAGNITUDE
    assert result.magnitude_delta_jpy == D("20") and result.signed_delta_jpy is None
    assert result.conditional_target_pretax_jpy is None


def test_signed_target_is_same_metric_and_requires_exact_coverage() -> None:
    req = with_target(request())
    result = compute_profit_impact(req)
    assert result.status is ImpactStatus.SUCCESS_CONDITIONAL_TARGET and result.conditional_target_pretax_jpy == D("1020")
    assert result.baseline_pretax_jpy == D("1000") and result.signed_delta_jpy == D("20")
    assert result.baseline_origin == "COMPANY_GUIDANCE" and result.audit[0].shock_origin == "RESEARCH_JUDGMENT"
    assert compute_profit_impact(change(req, coverage=None)).status is ImpactStatus.DOUBLE_COUNT_RISK
    assert req.coverage is not None
    stale = change(req, coverage=replace(req.coverage, baseline_hash="stale"))
    assert compute_profit_impact(stale).status is ImpactStatus.DOUBLE_COUNT_RISK


@pytest.mark.parametrize(
    "unit,magnitude", [("JPY", "20"), ("JPY_MILLION", "0.00002"), ("JPY_BILLION", "0.00000002"), ("JPY_100_MILLION", "0.0000002")]
)
def test_explicit_money_scale_preserves_original(unit: str, magnitude: str) -> None:
    src = source(profit_unit=unit, impact_magnitude=D(magnitude))
    result = compute_profit_impact(with_source(request(), src))
    assert result.signed_delta_jpy == D("20")
    assert src.profit_unit == unit and src.impact_magnitude == D(magnitude)


@pytest.mark.parametrize(
    "field,value,expected",
    [
        ("profit_metric", "OPERATING_INCOME", ImpactStatus.IDENTITY_MISMATCH),
        ("profit_metric", "NET_INCOME", ImpactStatus.IDENTITY_MISMATCH),
        ("scope", "SEGMENT", ImpactStatus.IDENTITY_MISMATCH),
        ("entity_id", "OTHER", ImpactStatus.IDENTITY_MISMATCH),
        ("forecast_period", "OTHER", ImpactStatus.IDENTITY_MISMATCH),
        ("forecast_version", "OLD", ImpactStatus.IDENTITY_MISMATCH),
        ("values_verified", False, ImpactStatus.SOURCE_NOT_VERIFIED),
        ("primary_or_secondary", PrimaryOrSecondary.SECONDARY, ImpactStatus.SOURCE_NOT_VERIFIED),
        ("source_authority_class", None, ImpactStatus.SOURCE_NOT_VERIFIED),
        ("system_available_at", T + timedelta(seconds=1), ImpactStatus.PIT_INVALID),
        ("retrieved_at", None, ImpactStatus.PIT_INVALID),
        ("availability_basis", AvailabilityBasis.UNKNOWN, ImpactStatus.PIT_INVALID),
        ("applicability", Applicability.UNKNOWN, ImpactStatus.APPLICABILITY_UNKNOWN),
    ],
)
def test_source_incompatibility_has_no_numeric_outcome(field: str, value: object, expected: ImpactStatus) -> None:
    result = compute_profit_impact(with_source(request(), source(**{field: value})))
    assert result.status is expected, result.reason
    assert result.signed_delta_jpy is None and result.conditional_target_pretax_jpy is None and result.audit


@pytest.mark.parametrize("delta", ["1", "5", "20", "-20"])
def test_unit_step_is_not_an_unbounded_linear_range(delta: str) -> None:
    req = request()
    req = change(req, shocks=(replace(req.shocks[0], change=D(delta), scenario_level=D("100") + D(delta)),))
    assert compute_profit_impact(req).status is ImpactStatus.OUTSIDE_DISCLOSED_APPLICATION


def test_verified_linear_range_needs_absolute_levels() -> None:
    src = source(
        applicability=Applicability.VERIFIED_LINEAR_RANGE,
        applicability_basis="synthetic verified range",
        minimum_level=D("80"),
        maximum_level=D("120"),
    )
    req = with_source(request(), src)
    req = change(req, shocks=(replace(req.shocks[0], change=D("5"), scenario_level=D("105")),))
    assert compute_profit_impact(req).signed_delta_jpy == D("10")
    missing = change(req, shocks=(replace(req.shocks[0], baseline_level=None, scenario_level=None),))
    assert compute_profit_impact(missing).status is ImpactStatus.INSUFFICIENT_INPUT
    outside = change(req, shocks=(replace(req.shocks[0], change=D("30"), scenario_level=D("130")),))
    assert compute_profit_impact(outside).status is ImpactStatus.OUTSIDE_DISCLOSED_APPLICATION


def test_published_date_is_not_a_pipeline_timestamp() -> None:
    req = request()
    assert req.disclosures[0].exact_public_at is None
    assert compute_profit_impact(req).status is ImpactStatus.SUCCESS_SIGNED_DELTA
    historical = change(req, created_at=OLD - timedelta(days=1), evidence_cutoff=OLD - timedelta(days=1))
    assert compute_profit_impact(historical).status is ImpactStatus.PIT_INVALID
    unknown = source(
        retrieved_at=None, system_available_at=None, normalized_created_at=None, availability_basis=AvailabilityBasis.UNKNOWN
    )
    req = change(req, disclosures=(unknown,), record_only=True, sensitivities=(), shocks=())
    result = compute_profit_impact(req)
    assert result.status is ImpactStatus.SOURCE_RECORDED and result.signed_delta_jpy is None


@pytest.mark.parametrize("kind", ["request-future", "source-before-normalization", "exact-public-future", "shock-creation"])
def test_time_chronology_is_fail_closed(kind: str) -> None:
    req = request()
    if kind == "request-future":
        req = change(req, created_at=T + timedelta(seconds=1))
    elif kind == "source-before-normalization":
        req = with_source(req, source(normalized_created_at=OLD + timedelta(seconds=1)))
    elif kind == "exact-public-future":
        req = with_source(req, source(exact_public_at=T + timedelta(seconds=1)))
    else:
        req = change(req, shocks=(replace(req.shocks[0], created_at=OLD - timedelta(seconds=1)),))
    assert compute_profit_impact(req).status is ImpactStatus.PIT_INVALID


def test_normalized_numbers_and_directions_cannot_override_source() -> None:
    req = request()
    wrong = replace(req.sensitivities[0], magnitude_jpy=D("999"), record_hash="")
    assert compute_profit_impact(change(req, sensitivities=(wrong,))).status is ImpactStatus.INTEGRITY_ERROR
    wrong = replace(req.sensitivities[0], direction=Direction.NEGATIVE, record_hash="")
    assert compute_profit_impact(change(req, sensitivities=(wrong,))).status is ImpactStatus.INTEGRITY_ERROR


def test_joint_impacts_require_exact_composition_and_no_overlapping_effect() -> None:
    req = request(drivers=("COPPER", "GOLD"))
    assert compute_profit_impact(req).status is ImpactStatus.DOUBLE_COUNT_RISK
    comp = ImpactComposition(
        sensitivity_refs=tuple((s.sensitivity_id, s.record_hash) for s in req.sensitivities),
        request_context_hash=request_context_hash(req),
        source_ref="A1",
        rationale="synthetic explicit additivity",
        available_at=OLD,
        created_at=OLD,
    )
    req = change(req, composition=comp)
    assert compute_profit_impact(req).signed_delta_jpy == D("40")
    stale = change(req, composition=replace(comp, request_context_hash="stale"))
    assert compute_profit_impact(stale).status is ImpactStatus.IDENTITY_MISMATCH
    unknown = replace(req.disclosures[1], direction=Direction.UNKNOWN, direction_basis=None, record_hash="")
    sens = normalize_sensitivity(
        unknown, sensitivity_id=req.sensitivities[1].sensitivity_id, coverage_keys=req.sensitivities[1].coverage_keys
    )
    req2 = change(req, disclosures=(req.disclosures[0], unknown), sensitivities=(req.sensitivities[0], sens), composition=None)
    comp2 = replace(
        comp,
        sensitivity_refs=tuple((s.sensitivity_id, s.record_hash) for s in req2.sensitivities),
        request_context_hash=request_context_hash(req2),
    )
    assert compute_profit_impact(change(req2, composition=comp2)).status is ImpactStatus.INSUFFICIENT_INPUT


@pytest.mark.parametrize("kind", ["metric", "period", "version", "scope", "fx", "inventory", "base-level"])
def test_baseline_mismatch_is_not_a_target(kind: str) -> None:
    req = with_target(request())
    assert req.baseline is not None and req.coverage is not None
    edits = {
        "metric": {"profit_metric": "OPERATING_INCOME"},
        "period": {"forecast_period": "OLD"},
        "version": {"forecast_version": "OLD"},
        "scope": {"scope": "SEGMENT"},
        "fx": {"fx_coverage": "OTHER"},
        "inventory": {"inventory_treatment": "INCLUDED"},
        "base-level": {"driver_levels": (("COPPER", D("99")),)},
    }
    baseline = replace(req.baseline, **edits[kind], record_hash="")
    changed = change(req, baseline=baseline)
    coverage = replace(req.coverage, baseline_hash=baseline.record_hash, request_context_hash=request_context_hash(changed))
    result = compute_profit_impact(change(changed, coverage=coverage))
    assert result.status not in (ImpactStatus.SUCCESS_CONDITIONAL_TARGET, ImpactStatus.SUCCESS_SIGNED_DELTA)
    assert result.conditional_target_pretax_jpy is None


def test_reapplication_ignores_decimal_display_scale() -> None:
    req = with_target(request())
    assert req.coverage is not None
    key = increment_key(req, req.sensitivities[0])
    req = change(req, shocks=(replace(req.shocks[0], change=D("10.00"), baseline_level=D("100.0")),))
    assert increment_key(req, req.sensitivities[0]) == key
    coverage = replace(req.coverage, request_context_hash=request_context_hash(req), applied_increment_keys=(key,))
    assert compute_profit_impact(change(req, coverage=coverage)).status is ImpactStatus.DOUBLE_COUNT_RISK


def test_context_independence_and_explicit_display_quantum() -> None:
    req = with_source(request(), source(impact_magnitude=D("20.125")))
    results = []
    for precision in (6, 28, 90):
        with localcontext() as context:
            context.prec = precision
            results.append(compute_profit_impact(req))
    assert all(r == results[0] for r in results)
    assert results[0].signed_delta_jpy == D("20.125") and results[0].displayed_delta_jpy == D("20")


def test_tampered_input_is_not_repaired() -> None:
    req = request()
    old_hash = req.disclosures[0].record_hash
    object.__setattr__(req.disclosures[0], "impact_magnitude", D("999"))
    result = compute_profit_impact(req)
    assert result.status is ImpactStatus.INTEGRITY_ERROR and result.audit[0].disposition == "NOT_EVALUATED"
    assert req.disclosures[0].record_hash == old_hash


def test_request_order_and_unknown_source_storage_are_stable() -> None:
    req = request(drivers=("GOLD", "COPPER"))
    reverse = change(
        req,
        disclosures=tuple(reversed(req.disclosures)),
        sensitivities=tuple(reversed(req.sensitivities)),
        shocks=tuple(reversed(req.shocks)),
    )
    assert req.record_hash == reverse.record_hash


def test_storage_reconstructs_inputs_and_rejects_rehashed_false_result(tmp_path: Path) -> None:
    inputs = ProfitImpactInputStore(tmp_path / "inputs.jsonl")
    results = ProfitImpactStore(tmp_path / "results.jsonl", input_store=inputs)
    req = request()
    outcome = compute_profit_impact(req)
    with pytest.raises(ImpactSchemaError):
        results.record(outcome)
    assert inputs.record(req) == req and inputs.record(req) == req
    assert results.record(outcome) == outcome and results.record(outcome) == outcome
    assert results.get("R1") == outcome and len(results.all()) == 1
    with pytest.raises(AppendOnlyViolationError):
        inputs.record(change(req, created_at=OLD))
    data = json.loads((tmp_path / "results.jsonl").read_text(encoding="utf-8"))
    data["signed_delta_jpy"] = "999"
    data["record_hash"] = compute_record_hash(data)
    (tmp_path / "results.jsonl").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ImpactSchemaError, match="reproducible"):
        results.all()


@pytest.mark.parametrize("kind", ["empty-hash", "nested-hash", "reordered"])
def test_raw_input_payload_is_verified_before_restore(tmp_path: Path, kind: str) -> None:
    inputs = ProfitImpactInputStore(tmp_path / "inputs.jsonl")
    req = request(drivers=("COPPER", "GOLD"))
    inputs.record(req)
    data = json.loads((tmp_path / "inputs.jsonl").read_text(encoding="utf-8"))
    if kind == "empty-hash":
        data["record_hash"] = ""
    elif kind == "nested-hash":
        data["disclosures"][0]["record_hash"] = ""
    else:
        data["sensitivities"].reverse()
    (tmp_path / "inputs.jsonl").write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ImpactSchemaError):
        inputs.get("R1")


def test_corrections_are_append_only_and_keep_economic_identity(tmp_path: Path) -> None:
    inputs = ProfitImpactInputStore(tmp_path / "inputs.jsonl")
    results = ProfitImpactStore(tmp_path / "results.jsonl", input_store=inputs)
    req = request()
    inputs.record(req)
    results.record(compute_profit_impact(req))
    correction = change(req, request_id="R2", supersedes_result_id="R1")
    inputs.record(correction)
    results.record(compute_profit_impact(correction))
    assert len(results.all()) == 2
    bad = change(req, request_id="R3", supersedes_result_id="MISSING")
    inputs.record(bad)
    with pytest.raises(AppendOnlyViolationError):
        results.record(compute_profit_impact(bad))


def test_no_operating_income_or_valuation_adapter_is_generated() -> None:
    import lib.profit_impact.calculation as calculation

    tree = ast.parse(Path(calculation.__file__).read_text(encoding="utf-8"))
    imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert not any(name and (name.startswith("lib.forecasting") or name.startswith("lib.valuation")) for name in imports)
    names = {f.name for f in fields(compute_profit_impact(request()))}
    assert not {"forecast_assumptions", "operating_income", "equity_value", "expected_return"}.intersection(names)


def test_company_table_fixture_retains_unknown_historical_times(tmp_path: Path) -> None:
    data = json.loads((Path(__file__).parent / "fixtures/smm_pretax_sensitivity_20260810.json").read_text(encoding="utf-8"))
    assert data["profit_metric"] == "PRETAX_INCOME"
    assert data["exact_public_at"] is None and data["historical_pipeline_available_at"] is None
    assert data["verified_joint_composition"] is None and data["verified_linear_range"] is None
    archived = SourceArtifact(
        artifact_id="SMM_FACT_EXCERPT", source_url=data["source_url"], content=json.dumps(data, ensure_ascii=False)
    )
    sources = []
    for row in data["rows"]:
        sources.append(
            source(
                row["driver"],
                disclosure_id=f"SMM_{row['driver']}",
                artifact_id=archived.artifact_id,
                artifact_hash=archived.record_hash,
                source_url=data["source_url"],
                title=data["title"],
                forecast_period=data["forecast_period"],
                forecast_version=data["forecast_version"],
                scope=data["scope"],
                pdf_page_index=data["pdf_page_index"],
                printed_page=data["printed_page"],
                table_locator=data["table_locator"],
                extraction_method_version="MANUAL_COMPANY_FACT_FIXTURE_V1",
                profit_unit=data["profit_unit"],
                impact_magnitude=D(row["magnitude"]),
                driver_step=D(row["driver_step"]),
                direction=Direction.UNKNOWN,
                direction_basis=None,
                applicability=Applicability.UNKNOWN,
                applicability_basis=None,
                base_level=None,
                inventory_treatment=data["inventory_treatment"],
                fx_coverage=data["fx_coverage"],
                other_base_conditions=(),
                retrieved_at=None,
                normalized_created_at=None,
                system_available_at=None,
                availability_basis=AvailabilityBasis.UNKNOWN,
            )
        )
    req = ProfitImpactRequest(
        request_id="SMM_SOURCE_ARCHIVE",
        entity_id="5713",
        forecast_period=data["forecast_period"],
        forecast_version=data["forecast_version"],
        scenario=ThesisScenario.BASE,
        evidence_cutoff=T,
        created_at=T,
        artifacts=(archived,),
        disclosures=tuple(sources),
        sensitivities=(),
        shocks=(),
        record_only=True,
    )
    result = compute_profit_impact(req)
    assert result.status is ImpactStatus.SOURCE_RECORDED and result.conditional_target_pretax_jpy is None
    inputs = ProfitImpactInputStore(tmp_path / "company_inputs.jsonl")
    results = ProfitImpactStore(tmp_path / "company_results.jsonl", input_store=inputs)
    inputs.record(req)
    assert results.record(result) == result and results.get(req.request_id) == result
    restored = inputs.get(req.request_id)
    assert restored is not None and all(d.system_available_at is None and d.exact_public_at is None for d in restored.disclosures)
    assert [
        normalize_sensitivity(s, sensitivity_id=s.disclosure_id, coverage_keys=(s.driver,)).magnitude_jpy for s in sources
    ] == [D("3200000000"), D("3600000000"), D("2200000000")]


@pytest.mark.parametrize(
    "field,value",
    [("driver_step", D(0)), ("impact_magnitude", D("NaN")), ("retrieved_at", T.replace(tzinfo=None)), ("values_verified", "yes")],
)
def test_schema_rejects_invalid_values(field: str, value: object) -> None:
    with pytest.raises(ImpactSchemaError):
        source(**{field: value})


def test_same_driver_cannot_be_counted_twice_under_aliases() -> None:
    req = request()
    second = replace(req.sensitivities[0], sensitivity_id="S_ALIAS", coverage_keys=("different-label",), record_hash="")
    shock = replace(req.shocks[0], sensitivity_id="S_ALIAS")
    req = change(req, sensitivities=(*req.sensitivities, second), shocks=(*req.shocks, shock))
    composition = ImpactComposition(
        sensitivity_refs=tuple((s.sensitivity_id, s.record_hash) for s in req.sensitivities),
        request_context_hash=request_context_hash(req),
        source_ref="A1",
        rationale="cannot override duplicate",
        available_at=OLD,
        created_at=OLD,
    )
    assert compute_profit_impact(change(req, composition=composition)).status is ImpactStatus.DOUBLE_COUNT_RISK


def test_renaming_coverage_cannot_make_a_new_economic_increment() -> None:
    req = with_target(request())
    assert req.coverage is not None
    key = increment_key(req, req.sensitivities[0])
    sensitivity = replace(req.sensitivities[0], coverage_keys=("renamed",), record_hash="")
    req = change(req, sensitivities=(sensitivity,))
    assert increment_key(req, sensitivity) == key
    coverage = replace(req.coverage, request_context_hash=request_context_hash(req), applied_increment_keys=(key,))
    assert compute_profit_impact(change(req, coverage=coverage)).status is ImpactStatus.DOUBLE_COUNT_RISK


@pytest.mark.parametrize("kind", ["future-date", "unknown-timezone", "wrong-exact-date"])
def test_publication_calendar_constraints_do_not_invent_timestamps(kind: str) -> None:
    kwargs = {
        "future-date": {"disclosed_on": date(2030, 1, 1)},
        "unknown-timezone": {"publication_timezone": None},
        "wrong-exact-date": {"exact_public_at": OLD},
    }
    req = with_source(request(), source(**kwargs[kind]))
    assert compute_profit_impact(req).status is ImpactStatus.PIT_INVALID


def test_power_of_ten_unit_normalization_does_not_round_source_digits() -> None:
    raw = D("1." + "1234567890" * 9)
    src = source(impact_magnitude=raw, profit_unit="JPY_BILLION")
    result = normalize_sensitivity(src, sensitivity_id="S1", coverage_keys=("single",))
    sign, digits, exponent = raw.as_tuple()
    assert isinstance(exponent, int)
    assert result.magnitude_jpy.as_tuple() == (sign, digits, exponent + 9)


def test_global_source_ids_are_immutable_across_snapshots(tmp_path: Path) -> None:
    inputs = ProfitImpactInputStore(tmp_path / "inputs.jsonl")
    req = request()
    inputs.record(req)
    altered = with_source(req, source(impact_magnitude=D("21")))
    with pytest.raises(AppendOnlyViolationError, match="component ID"):
        inputs.record(change(altered, request_id="R2"))
    altered = source(
        disclosure_id="SOURCE_CORRECTION", impact_magnitude=D("21"), supersedes_disclosure_id=req.disclosures[0].disclosure_id
    )
    sensitivity = normalize_sensitivity(altered, sensitivity_id="S_CORRECTION", coverage_keys=("effect:COPPER",))
    correction = change(
        req,
        request_id="R2",
        disclosures=(altered,),
        sensitivities=(sensitivity,),
        shocks=(replace(req.shocks[0], sensitivity_id=sensitivity.sensitivity_id),),
    )
    assert inputs.record(correction) == correction
    results = ProfitImpactStore(tmp_path / "results.jsonl", input_store=inputs)
    assert results.record(compute_profit_impact(correction)).signed_delta_jpy == D("21")


def test_missing_disclosure_correction_parent_is_rejected(tmp_path: Path) -> None:
    inputs = ProfitImpactInputStore(tmp_path / "inputs.jsonl")
    req = with_source(request(), source(supersedes_disclosure_id="MISSING"))
    with pytest.raises(AppendOnlyViolationError, match="matching archived parent"):
        inputs.record(req)


def test_unknown_scope_can_be_resolved_by_a_new_disclosure_record(tmp_path: Path) -> None:
    inputs = ProfitImpactInputStore(tmp_path / "inputs.jsonl")
    raw_source = source(scope="UNKNOWN")
    raw = change(with_source(request(), raw_source), record_only=True, sensitivities=(), shocks=())
    inputs.record(raw)
    resolved = source(disclosure_id="RESOLVED_SOURCE", supersedes_disclosure_id=raw_source.disclosure_id)
    req = change(
        request(),
        request_id="RESOLVED_INPUT",
        disclosures=(resolved,),
        sensitivities=(normalize_sensitivity(resolved, sensitivity_id="RESOLVED_SENSITIVITY", coverage_keys=("effect:COPPER",)),),
        shocks=(replace(request().shocks[0], sensitivity_id="RESOLVED_SENSITIVITY"),),
    )
    assert inputs.record(req) == req


@pytest.mark.parametrize("target", ["inputs", "results"])
def test_duplicate_stored_ids_are_not_selected(tmp_path: Path, target: str) -> None:
    inputs = ProfitImpactInputStore(tmp_path / "inputs.jsonl")
    results = ProfitImpactStore(tmp_path / "results.jsonl", input_store=inputs)
    req = request()
    inputs.record(req)
    results.record(compute_profit_impact(req))
    path = tmp_path / f"{target}.jsonl"
    data = path.read_text(encoding="utf-8")
    path.write_text(data + data, encoding="utf-8")
    with pytest.raises(ImpactSchemaError, match="ambiguous"):
        results.get("R1")


def test_rounding_or_delta_fields_cannot_leak_into_disclosure_only() -> None:
    req = change(request(), record_only=True, sensitivities=(), shocks=())
    result = compute_profit_impact(req)
    with pytest.raises(ImpactSchemaError):
        replace(result, displayed_delta_jpy=D(0), record_hash="")


def test_declared_context_overflow_is_a_typed_failure() -> None:
    src = source(impact_magnitude=D("1e999999"), profit_unit="JPY_BILLION")
    req = with_source(request(), src)
    result = compute_profit_impact(req)
    assert result.status is ImpactStatus.CALCULATION_ERROR and result.signed_delta_jpy is None


def test_record_only_does_not_silently_discard_a_calculation_request() -> None:
    assert compute_profit_impact(change(request(), record_only=True)).status is ImpactStatus.INSUFFICIENT_INPUT
