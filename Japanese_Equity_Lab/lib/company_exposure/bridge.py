"""Fail-closed exposure increments, source lineage and frozen D0109 replay."""

from __future__ import annotations

from dataclasses import fields, is_dataclass, replace
from decimal import ROUND_HALF_EVEN, Context, Decimal, DecimalException, localcontext

from lib.evaluation.integrity import compute_record_hash, verify_record_integrity
from lib.evidence.model import EvidenceRecord, EvidenceType
from lib.forecasting.engine import compute_fundamental_forecast
from lib.forecasting.model import (
    ASSUMPTION_OPERATING_INCOME_OVERRIDE,
    ASSUMPTION_OPERATING_MARGIN,
    METRIC_OPERATING_INCOME,
    METRIC_REVENUE,
    AssumptionSource,
    ForecastAssumption,
    ForecastStatus,
    FundamentalForecastResult,
    HistoricalFundamentalBase,
    ScenarioAssumptions,
)
from lib.sources.catalog import PrimaryOrSecondary, SourceAuthorityClass

from .model import (
    MONEY_SCALES,
    BaselineCoverage,
    BridgeRequest,
    BridgeResult,
    BridgeStatus,
    CandidateAudit,
    CompanyExposure,
    CompositionDeclaration,
    DriverAssumption,
    ExposureSchemaError,
    ExposureSource,
    time,
)


def validate_tree(value: object) -> None:
    """Validate without repairing caller data; reject tampering before reconstruction."""
    if isinstance(value, tuple):
        for item in value:
            validate_tree(item)
    elif is_dataclass(value) and not isinstance(value, type):
        if hasattr(value, "record_hash") and not verify_record_integrity(value):
            raise ExposureSchemaError("record integrity failure")
        data = {f.name: getattr(value, f.name) for f in fields(value)}
        for item in data.values():
            validate_tree(item)
        # Existing constructors perform their own schema checks; no __post_init__
        # calls on original instances and no automatic normalization of input.
        rebuilt = type(value)(**data)
        if rebuilt != value:
            raise ExposureSchemaError("noncanonical record")
    elif isinstance(value, Decimal) and not value.is_finite():
        raise ExposureSchemaError("nonfinite input")


def _hash(record: object) -> str:
    return compute_record_hash({"payload": record})


def baseline_input_hash(scenarios: tuple[ScenarioAssumptions, ...], bases: tuple[HistoricalFundamentalBase, ...]) -> str:
    """Bind the coverage declaration to the exact frozen-engine inputs."""
    return compute_record_hash(
        {
            "scenarios": tuple(sorted(scenarios, key=lambda s: s.scenario.value)),
            "bases": tuple(sorted(bases, key=lambda b: (b.metric, b.source_id))),
        }
    )


def _decimal_identity(value: Decimal) -> tuple[int, tuple[int, ...], int]:
    """Numeric identity independent of display scale and Decimal context."""
    sign, digits, exponent = value.as_tuple()
    assert isinstance(exponent, int)
    if not any(digits):
        return 0, (0,), 0
    while digits[-1] == 0:
        digits, exponent = digits[:-1], exponent + 1
    return sign, digits, exponent


def _forecast(request: BridgeRequest, scenarios: tuple[ScenarioAssumptions, ...], suffix: str) -> FundamentalForecastResult:
    with localcontext(Context(prec=28, rounding=ROUND_HALF_EVEN)):
        return compute_fundamental_forecast(
            result_id=f"{request.request_id}:{suffix}",
            entity_id=request.entity_id,
            target_period=request.forecast_period,
            requested_metrics=(METRIC_REVENUE, METRIC_OPERATING_INCOME),
            scenario_assumptions=scenarios,
            historical_bases=request.historical_bases,
            evidence_cutoff=request.evidence_cutoff,
            research_snapshot_id=request.research_snapshot_id,
            forecast_created_at=request.created_at,
            evidence_records=request.evidence_records,
        )


def _money(forecast: FundamentalForecastResult, request: BridgeRequest, metric: str) -> Decimal:
    scenario = next(s for s in forecast.scenarios if s.scenario is request.scenario)
    value = next(v for v in scenario.metric_values if v.metric == metric)
    return value.value * MONEY_SCALES[value.unit]


def increment_key(request: BridgeRequest, exposure: CompanyExposure, driver: DriverAssumption) -> str:
    """Economic increment identity excludes correction IDs and publication metadata."""
    return compute_record_hash(
        {
            "entity": request.entity_id,
            "period": request.forecast_period,
            "scenario": request.scenario,
            "driver": driver.driver,
            "baseline": _decimal_identity(driver.baseline_level),
            "level": _decimal_identity(driver.scenario_level),
            "unit": driver.unit,
            "coverage": exposure.coverage_keys,
        }
    )


def _evidence_valid(evidence: EvidenceRecord, request: BridgeRequest) -> bool:
    # System-simulation contract: availability, retrieval and publication must
    # all be known and no later than cutoff. SourceMetadata has no unknown-time enum.
    source = evidence.source
    for value in (source.available_at, source.retrieved_at):
        time(value)
    if source.published_at is not None:
        time(source.published_at)
    return (
        evidence.is_usable_at(request.evidence_cutoff)
        and source.published_at is not None
        and source.published_at <= request.evidence_cutoff
        and source.retrieved_at <= request.evidence_cutoff
    )


def compute_exposure_bridge(request: BridgeRequest) -> BridgeResult:
    """One explicit scenario per request; full D0109 replay remains atomic."""
    if not isinstance(request, BridgeRequest):
        raise ExposureSchemaError("BridgeRequest required")
    audit = tuple(
        CandidateAudit(
            exposure_id=e.exposure_id, exposure_hash=e.record_hash, disposition="NOT_EVALUATED", reason="pending validation"
        )
        for e in request.exposures
    )
    refs = tuple(
        sorted(
            [("request", request.record_hash), ("coverage", request.coverage.record_hash)]
            + [(f"exposure:{e.exposure_id}", e.record_hash) for e in request.exposures]
            + [(f"driver:{d.assumption_id}", d.record_hash) for d in request.drivers]
            + [(f"evidence:{e.evidence_id}", _hash(e)) for e in request.evidence_records]
            + [("baseline_scenarios", _hash(request.baseline_scenarios)), ("historical_bases", _hash(request.historical_bases))]
            + ([("composition", request.composition.record_hash)] if request.composition is not None else [])
            + [(f"observed_audit_only:{i}", h) for i, h in request.observed_response_refs]
        )
    )
    baseline: FundamentalForecastResult | None = None
    income: Decimal | None = None
    target: Decimal | None = None
    replay_value: Decimal | None = None
    rounding_difference: Decimal | None = None

    def fail(status: BridgeStatus, reason: str) -> BridgeResult:
        return BridgeResult(
            result_id=request.request_id,
            entity_id=request.entity_id,
            forecast_period=request.forecast_period,
            scenario=request.scenario,
            request_hash=request.record_hash,
            input_refs=refs,
            status=status,
            reason=reason,
            audit=audit,
            created_at=request.created_at,
            baseline_forecast=baseline,
            replay_forecast=None,
            adjusted_scenarios=(),
            baseline_operating_income_jpy=income,
            target_operating_income_jpy=target,
            replay_operating_income_jpy=replay_value,
            rounding_difference_jpy=rounding_difference,
            money_quantum=request.money_quantum,
            supersedes_result_id=request.supersedes_result_id,
        )

    try:
        validate_tree(request)
    except (ValueError, TypeError, AttributeError, DecimalException) as exc:
        return fail(BridgeStatus.INTEGRITY_ERROR, str(exc))
    if not request.exposures or not request.drivers:
        return fail(BridgeStatus.INSUFFICIENT_INPUT, "explicit exposures and period drivers required")
    if request.created_at > request.evidence_cutoff:
        return fail(BridgeStatus.PIT_INVALID, "system-simulation created_at after cutoff")
    coverage = request.coverage
    if (coverage.entity_id, coverage.forecast_period, coverage.scenario) != (
        request.entity_id,
        request.forecast_period,
        request.scenario,
    ):
        return fail(BridgeStatus.IDENTITY_MISMATCH, "coverage identity mismatch")
    if not coverage.complete:
        return fail(BridgeStatus.UNKNOWN_BASELINE_COVERAGE, "baseline coverage is not complete")
    if coverage.baseline_input_hash != baseline_input_hash(request.baseline_scenarios, request.historical_bases):
        return fail(BridgeStatus.UNKNOWN_BASELINE_COVERAGE, "coverage does not bind exact baseline inputs")
    ids = [e.evidence_id for e in request.evidence_records]
    if len(ids) != len(set(ids)):
        return fail(BridgeStatus.INSUFFICIENT_INPUT, "ambiguous evidence references")
    evidence_by_id = {e.evidence_id: e for e in request.evidence_records}
    try:
        if not all(_evidence_valid(e, request) for e in request.evidence_records):
            return fail(BridgeStatus.PIT_INVALID, "unknown/future evidence timestamp")
    except (ValueError, TypeError):
        return fail(BridgeStatus.PIT_INVALID, "malformed evidence timestamp")

    def refs_ok(evidence_ids: tuple[str, ...]) -> bool:
        return all(i in evidence_by_id and _evidence_valid(evidence_by_id[i], request) for i in evidence_ids)

    records: tuple[CompanyExposure | DriverAssumption | BaselineCoverage | CompositionDeclaration, ...] = (
        *request.exposures,
        *request.drivers,
        coverage,
        *((request.composition,) if request.composition is not None else ()),
    )
    for record in records:
        if record.available_at > request.evidence_cutoff or not refs_ok(record.evidence_ids):
            return fail(BridgeStatus.PIT_INVALID, "missing/unavailable source evidence or record")
        if any(evidence_by_id[i].source.available_at > record.available_at for i in record.evidence_ids):
            return fail(BridgeStatus.PIT_INVALID, "record predates its evidence availability")
        if isinstance(record, CompanyExposure):
            if record.disclosed_at > request.evidence_cutoff:
                return fail(BridgeStatus.PIT_INVALID, "exposure disclosed after cutoff")
        elif (
            record.created_at > request.evidence_cutoff
            or record.created_at < record.available_at
            or any(evidence_by_id[i].source.retrieved_at > record.created_at for i in record.evidence_ids)
        ):
            return fail(BridgeStatus.PIT_INVALID, "input creation/availability chronology invalid")
    for scenario in request.baseline_scenarios:
        for assumption in scenario.assumptions:
            if assumption.created_at > request.evidence_cutoff:
                return fail(BridgeStatus.PIT_INVALID, "baseline assumption created after cutoff")
            if assumption.source is AssumptionSource.EVIDENCE_DERIVED and (
                not refs_ok(assumption.evidence_ids)
                or any(evidence_by_id[i].source.retrieved_at > assumption.created_at for i in assumption.evidence_ids)
            ):
                return fail(BridgeStatus.PIT_INVALID, "baseline evidence lineage/creation chronology invalid")
            if assumption.source in (AssumptionSource.COMPANY_GUIDANCE, AssumptionSource.MARKET_PROXY):
                return fail(BridgeStatus.UNSUPPORTED_SOURCE, "baseline guidance/proxy observation resolution outside v1")
    for base in request.historical_bases:
        if base.entity_id != request.entity_id or base.currency != "JPY" or base.unit not in MONEY_SCALES:
            return fail(BridgeStatus.IDENTITY_MISMATCH, "baseline entity/currency/unit mismatch")
        if not isinstance(base.value, Decimal) or base.available_at > request.evidence_cutoff:
            return fail(BridgeStatus.PIT_INVALID, "baseline amount/type/availability invalid")
    if len({d.driver for d in request.drivers}) != len(request.drivers) or len({d.assumption_id for d in request.drivers}) != len(
        request.drivers
    ):
        return fail(BridgeStatus.INSUFFICIENT_INPUT, "duplicate/ambiguous driver")
    if len({e.exposure_id for e in request.exposures}) != len(request.exposures) or len(
        {e.driver for e in request.exposures}
    ) != len(request.exposures):
        return fail(BridgeStatus.DOUBLE_COUNT_RISK, "duplicate exposure/driver")
    drivers = {d.driver: d for d in request.drivers}
    levels = {c.driver: c for c in coverage.levels}
    if set(drivers) != {e.driver for e in request.exposures}:
        return fail(BridgeStatus.INSUFFICIENT_INPUT, "driver/exposure set must match exactly")
    composition = request.composition
    exposure_ids = tuple(sorted(e.exposure_id for e in request.exposures))
    if composition is not None and composition.exposure_ids != exposure_ids:
        return fail(BridgeStatus.IDENTITY_MISMATCH, "composition does not name exact exposure set")
    if len(request.exposures) > 1 and composition is None:
        return fail(BridgeStatus.DOUBLE_COUNT_RISK, "multiple drivers require source-backed composition")
    joint = {c.driver: c for c in composition.joint_conditions} if composition else {}
    if composition is not None:
        if not all(
            request.entity_id in evidence_by_id[i].related_codes
            and evidence_by_id[i].source.primary_or_secondary is PrimaryOrSecondary.PRIMARY
            and evidence_by_id[i].source.source_authority_class is SourceAuthorityClass.PRIMARY_OFFICIAL
            for i in composition.evidence_ids
        ):
            return fail(BridgeStatus.UNSUPPORTED_SOURCE, "composition requires company primary evidence")
        for condition in joint.values():
            expected = (
                drivers[condition.driver].scenario_level
                if condition.driver in drivers
                else (levels[condition.driver].level if condition.driver in levels else None)
            )
            if expected is None or condition.level != expected:
                return fail(BridgeStatus.DOUBLE_COUNT_RISK, "composition conditions do not match scenario")
    adopted: list[CandidateAudit] = []
    coverage_keys: set[str] = set()
    with localcontext(Context(prec=80, rounding=ROUND_HALF_EVEN)):
        for exposure in request.exposures:
            driver = drivers[exposure.driver]

            def reject(status: BridgeStatus, reason: str) -> BridgeResult:
                nonlocal audit
                audit = tuple(
                    replace(a, disposition="REJECTED", reason=reason) if a.exposure_id == exposure.exposure_id else a
                    for a in audit
                )
                return fail(status, reason)

            if (exposure.entity_id, exposure.forecast_period, driver.entity_id, driver.forecast_period, driver.scenario) != (
                request.entity_id,
                request.forecast_period,
                request.entity_id,
                request.forecast_period,
                request.scenario,
            ):
                return reject(BridgeStatus.IDENTITY_MISMATCH, "exposure/driver entity, period or scenario mismatch")
            if exposure.profit_metric != METRIC_OPERATING_INCOME or exposure.scope != "CONSOLIDATED":
                return reject(BridgeStatus.UNSUPPORTED_METRIC, "only consolidated operating income supported")
            if exposure.affects_revenue:
                return reject(BridgeStatus.UNSUPPORTED_REVENUE_EFFECT, "revenue effects outside margin-only bridge")
            if exposure.source_type not in (ExposureSource.COMPANY_DISCLOSED, ExposureSource.DETERMINISTIC_DERIVED):
                return reject(BridgeStatus.UNSUPPORTED_SOURCE, "estimated/judgment sensitivity not supported")
            if exposure.source_type is ExposureSource.DETERMINISTIC_DERIVED:
                assert exposure.disclosed_sensitivity_amount is not None and exposure.disclosed_profit_unit is not None
                try:
                    equal_origin = exposure.sensitivity_amount * MONEY_SCALES[exposure.profit_unit] == (
                        exposure.disclosed_sensitivity_amount * MONEY_SCALES[exposure.disclosed_profit_unit]
                    )
                except DecimalException:
                    return reject(BridgeStatus.PRECISION_INCOMPATIBLE, "unit conversion exceeds declared context")
                if not equal_origin:
                    return reject(BridgeStatus.UNSUPPORTED_SOURCE, "unit-derived amount does not match disclosed origin")
            source_records = [evidence_by_id[i] for i in exposure.evidence_ids]
            if not any(
                e.source.source_id == exposure.source_id
                and e.source.source_url == exposure.source_url
                and e.evidence_type in (EvidenceType.FACT, EvidenceType.CLAIM)
                and request.entity_id in e.related_codes
                and e.source.primary_or_secondary is PrimaryOrSecondary.PRIMARY
                and e.source.source_authority_class is SourceAuthorityClass.PRIMARY_OFFICIAL
                and e.source.published_at is not None
                and e.source.published_at <= exposure.disclosed_at
                and e.source.available_at <= exposure.available_at
                for e in source_records
            ):
                return reject(BridgeStatus.UNSUPPORTED_SOURCE, "company primary source/identity/time reference not verified")
            if exposure.applicable_from > request.period_start or exposure.applicable_until < request.period_end:
                return reject(BridgeStatus.IDENTITY_MISMATCH, "sensitivity does not cover full forecast period")
            if not (
                exposure.minimum_level <= driver.baseline_level <= exposure.maximum_level
                and exposure.minimum_level <= driver.scenario_level <= exposure.maximum_level
            ):
                return reject(BridgeStatus.OUTSIDE_SENSITIVITY_RANGE, "linear extrapolation outside disclosed range")
            for condition in exposure.base_conditions:
                base_level = levels.get(condition.driver)
                if base_level is None or base_level.level != condition.level or base_level.unit != condition.unit:
                    return reject(BridgeStatus.IDENTITY_MISMATCH, "exposure baseline condition mismatch")
                if condition.driver == exposure.driver:
                    if driver.baseline_level != condition.level:
                        return reject(BridgeStatus.IDENTITY_MISMATCH, "driver baseline mismatch")
                elif condition.driver in drivers and drivers[condition.driver].scenario_level != condition.level:
                    if condition.driver not in joint:
                        return reject(BridgeStatus.DOUBLE_COUNT_RISK, "changed conditional driver lacks joint disclosure")
            if exposure.other_base_assumptions != coverage.other_base_assumptions:
                return reject(BridgeStatus.IDENTITY_MISMATCH, "other base assumptions mismatch")
            if coverage_keys.intersection(exposure.coverage_keys):
                return reject(BridgeStatus.DOUBLE_COUNT_RISK, "economic coverage overlap")
            coverage_keys.update(exposure.coverage_keys)
            key = increment_key(request, exposure, driver)
            if key in coverage.applied_increment_keys:
                return reject(BridgeStatus.DOUBLE_COUNT_RISK, "increment already included in baseline")
            try:
                delta = (
                    exposure.sensitivity_amount
                    * MONEY_SCALES[exposure.profit_unit]
                    * (driver.scenario_level - driver.baseline_level)
                    / exposure.driver_step
                )
            except DecimalException:
                return reject(BridgeStatus.PRECISION_INCOMPATIBLE, "exposure arithmetic exceeds declared context")
            adopted.append(
                CandidateAudit(
                    exposure_id=exposure.exposure_id,
                    exposure_hash=exposure.record_hash,
                    disposition="ADOPTED",
                    reason="validated period increment",
                    increment_key=key,
                    delta_jpy=delta,
                )
            )
            audit = tuple(next((chosen for chosen in adopted if chosen.exposure_id == a.exposure_id), a) for a in audit)
        audit = tuple(adopted)
        try:
            baseline = _forecast(request, request.baseline_scenarios, "baseline")
            if baseline.status is not ForecastStatus.SUCCESS:
                return fail(BridgeStatus.INVALID_BASELINE, f"D0109 baseline: {baseline.status}: {baseline.reason}")
            income, revenue = _money(baseline, request, METRIC_OPERATING_INCOME), _money(baseline, request, METRIC_REVENUE)
            target = income + sum((a.delta_jpy for a in audit if a.delta_jpy is not None), Decimal(0))
            if revenue <= 0 or not Decimal(0) <= target <= revenue:
                return fail(BridgeStatus.INVALID_BASELINE, "nonpositive revenue or operating margin outside 0..100")
            margin = target / revenue * Decimal(100)
            selected = next(s for s in request.baseline_scenarios if s.scenario is request.scenario)
            # Lineage includes baseline dependencies; judgment anywhere prevents
            # relabelling a mixed calculation as evidence-derived fact.
            judgment = any(d.is_research_judgment for d in request.drivers) or any(
                a.source is not AssumptionSource.EVIDENCE_DERIVED for a in selected.assumptions
            )
            output_evidence = tuple(
                sorted(
                    set(coverage.evidence_ids).union(
                        *(e.evidence_ids for e in request.exposures),
                        *(d.evidence_ids for d in request.drivers),
                        *(a.evidence_ids for a in selected.assumptions),
                        composition.evidence_ids if composition else (),
                    )
                )
            )
            if not judgment and not refs_ok(output_evidence):
                return fail(BridgeStatus.PIT_INVALID, "unavailable combined baseline evidence")
            with localcontext(Context(prec=28, rounding=ROUND_HALF_EVEN)):
                raw_revenue = next(
                    v.value
                    for s in baseline.scenarios
                    if s.scenario is request.scenario
                    for v in s.metric_values
                    if v.metric == METRIC_REVENUE
                )
                replay_income = raw_revenue * (margin / Decimal(100))

            def changed(name: str, value: Decimal, unit: str) -> ForecastAssumption:
                return ForecastAssumption(
                    name=name,
                    value=value,
                    unit=unit,
                    source=AssumptionSource.RESEARCH_JUDGMENT if judgment else AssumptionSource.EVIDENCE_DERIVED,
                    rationale=f"Conditional exposure bridge {request.request_id}; not a causal forecast",
                    evidence_ids=() if judgment else output_evidence,
                    created_at=request.created_at,
                )

            assumptions = tuple(
                changed(a.name, margin, "PERCENT")
                if a.name == ASSUMPTION_OPERATING_MARGIN
                else changed(a.name, replay_income, a.unit)
                if a.name == ASSUMPTION_OPERATING_INCOME_OVERRIDE
                else a
                for a in selected.assumptions
            )
            updated = ScenarioAssumptions(scenario=request.scenario, assumptions=assumptions)
            scenarios = tuple(updated if s.scenario is request.scenario else s for s in request.baseline_scenarios)
            replay = _forecast(request, scenarios, "replay")
            if replay.status is not ForecastStatus.SUCCESS:
                return fail(BridgeStatus.INVALID_BASELINE, f"D0109 replay: {replay.status}: {replay.reason}")
            replay_value = _money(replay, request, METRIC_OPERATING_INCOME)
            rounding_difference = replay_value - target
            quantum = request.money_quantum
            rounded_target = (target / quantum).to_integral_value(rounding=ROUND_HALF_EVEN)
            rounded_replay = (replay_value / quantum).to_integral_value(rounding=ROUND_HALF_EVEN)
            if rounded_target != rounded_replay:
                return fail(BridgeStatus.PRECISION_INCOMPATIBLE, "D0109 replay differs at explicit money quantum")
            return BridgeResult(
                result_id=request.request_id,
                entity_id=request.entity_id,
                forecast_period=request.forecast_period,
                scenario=request.scenario,
                request_hash=request.record_hash,
                input_refs=refs,
                status=BridgeStatus.SUCCESS,
                reason="conditional exposure increment; synthetic foundation only",
                audit=audit,
                created_at=request.created_at,
                baseline_forecast=baseline,
                replay_forecast=replay,
                adjusted_scenarios=scenarios,
                baseline_operating_income_jpy=income,
                target_operating_income_jpy=target,
                replay_operating_income_jpy=replay_value,
                rounding_difference_jpy=rounding_difference,
                money_quantum=quantum,
                supersedes_result_id=request.supersedes_result_id,
            )
        except (ValueError, TypeError, DecimalException, StopIteration, KeyError) as exc:
            return fail(BridgeStatus.INVALID_BASELINE, f"D0109 input/calculation failure: {exc}")
