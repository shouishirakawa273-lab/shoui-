"""Period-conditioned pretax impacts; disclosure dates are never backdated times."""

from __future__ import annotations

from dataclasses import fields, is_dataclass, replace
from decimal import ROUND_HALF_EVEN, Context, Decimal, DecimalException, localcontext
from zoneinfo import ZoneInfo

from lib.evaluation.integrity import compute_record_hash, verify_record_integrity
from lib.evidence.model import AvailabilityBasis
from lib.sources.catalog import PrimaryOrSecondary, SourceAuthorityClass

from .model import (
    DRIVER_UNITS,
    MONEY_SCALES,
    Applicability,
    Direction,
    ImpactAudit,
    ImpactSchemaError,
    ImpactStage,
    ImpactStatus,
    NormalizedSensitivity,
    ProfitImpactRequest,
    ProfitImpactResult,
    SourceDisclosureRecord,
)


def validate_tree(value: object) -> None:
    if isinstance(value, tuple):
        for item in value:
            validate_tree(item)
    elif is_dataclass(value) and not isinstance(value, type):
        if hasattr(value, "record_hash") and not verify_record_integrity(value):
            raise ImpactSchemaError("record hash mismatch")
        data = {f.name: getattr(value, f.name) for f in fields(value)}
        for item in data.values():
            validate_tree(item)
        if type(value)(**data) != value:
            raise ImpactSchemaError("noncanonical input")
    elif isinstance(value, Decimal) and not value.is_finite():
        raise ImpactSchemaError("nonfinite input")


def normalize_sensitivity(
    source: SourceDisclosureRecord, *, sensitivity_id: str, coverage_keys: tuple[str, ...]
) -> NormalizedSensitivity:
    """Exact money-unit normalization only; never change source metric or direction."""
    validate_tree(source)
    if source.profit_unit not in MONEY_SCALES or source.currency != "JPY" or source.driver_unit is None:
        raise ImpactSchemaError("unknown source units")
    if source.driver_step is None or source.impact_magnitude is None:
        raise ImpactSchemaError("source numeric values are unknown")
    # Decimal exponent shifts by a known power of ten are exact even for more
    # than 80 significant digits; calculation rounding is a separate contract.
    sign, digits, exponent = source.impact_magnitude.as_tuple()
    shift = MONEY_SCALES[source.profit_unit].as_tuple().exponent
    assert isinstance(exponent, int) and isinstance(shift, int)
    magnitude = Decimal((sign, digits, exponent + shift))
    return NormalizedSensitivity(
        sensitivity_id=sensitivity_id,
        disclosure_id=source.disclosure_id,
        disclosure_hash=source.record_hash,
        entity_id=source.entity_id,
        forecast_period=source.forecast_period,
        forecast_version=source.forecast_version,
        profit_metric=source.profit_metric,
        driver=source.driver,
        driver_step=source.driver_step,
        driver_unit=source.driver_unit,
        magnitude_jpy=magnitude,
        direction=source.direction,
        coverage_keys=coverage_keys,
    )


def request_context_hash(request: ProfitImpactRequest) -> str:
    """Bind coverage/composition to the exact scenario, shocks, sources and baseline."""
    return compute_record_hash(
        {
            "entity": request.entity_id,
            "period": request.forecast_period,
            "version": request.forecast_version,
            "scenario": request.scenario,
            "sensitivities": request.sensitivities,
            "shocks": request.shocks,
            "baseline": request.baseline,
        }
    )


def _decimal_identity(value: Decimal) -> tuple[int, tuple[int, ...], int]:
    sign, digits, exponent = value.as_tuple()
    assert isinstance(exponent, int)
    if not any(digits):
        return 0, (0,), 0
    while digits[-1] == 0:
        digits, exponent = digits[:-1], exponent + 1
    return sign, digits, exponent


def increment_key(request: ProfitImpactRequest, sensitivity: NormalizedSensitivity) -> str:
    shock = next(s for s in request.shocks if s.sensitivity_id == sensitivity.sensitivity_id)
    source = next(d for d in request.disclosures if d.disclosure_id == sensitivity.disclosure_id)
    baseline_level = shock.baseline_level if shock.baseline_level is not None else source.base_level
    return compute_record_hash(
        {
            "entity": request.entity_id,
            "period": request.forecast_period,
            "version": request.forecast_version,
            "scenario": request.scenario,
            "driver": sensitivity.driver,
            "unit": sensitivity.driver_unit,
            "change": _decimal_identity(shock.change),
            "baseline_level": _decimal_identity(baseline_level) if baseline_level is not None else None,
        }
    )


def _source_time_ok(source: SourceDisclosureRecord, request: ProfitImpactRequest) -> bool:
    retrieved, normalized, available = source.retrieved_at, source.normalized_created_at, source.system_available_at
    if (
        retrieved is None
        or normalized is None
        or available is None
        or source.availability_basis is not AvailabilityBasis.OBSERVED
    ):
        return False
    if not retrieved <= normalized <= available <= request.evidence_cutoff or available > request.created_at:
        return False
    if source.disclosed_on is not None:
        if source.publication_timezone is None:
            return False
        zone = ZoneInfo(source.publication_timezone)
        if source.disclosed_on > retrieved.astimezone(zone).date():
            return False
        if source.exact_public_at is not None and source.exact_public_at.astimezone(zone).date() != source.disclosed_on:
            return False
    # A known exact public timestamp constrains chronology, but an unknown one
    # remains None. No date-to-midnight conversion or historical availability inference.
    return source.exact_public_at is None or source.exact_public_at <= retrieved


def _verified_company_source(source: SourceDisclosureRecord) -> bool:
    return (
        source.values_verified
        and source.source_authority_class is SourceAuthorityClass.PRIMARY_OFFICIAL
        and (source.primary_or_secondary is PrimaryOrSecondary.PRIMARY)
    )


def compute_profit_impact(request: ProfitImpactRequest) -> ProfitImpactResult:
    if not isinstance(request, ProfitImpactRequest):
        raise ImpactSchemaError("ProfitImpactRequest required")
    audit = tuple(
        ImpactAudit(
            sensitivity_id=s.sensitivity_id, input_hash=s.record_hash, disposition="NOT_EVALUATED", reason="pending validation"
        )
        for s in request.sensitivities
    )

    def outcome(
        status: ImpactStatus,
        reason: str,
        *,
        magnitude: Decimal | None = None,
        delta: Decimal | None = None,
        baseline: Decimal | None = None,
        target: Decimal | None = None,
    ) -> ProfitImpactResult:
        stages = {
            ImpactStatus.SUCCESS_MAGNITUDE_ONLY: ImpactStage.MAGNITUDE,
            ImpactStatus.SUCCESS_SIGNED_DELTA: ImpactStage.SIGNED_DELTA,
            ImpactStatus.SUCCESS_CONDITIONAL_TARGET: ImpactStage.TARGET,
        }
        with localcontext(Context(prec=80, rounding=ROUND_HALF_EVEN)):
            q = request.money_quantum_jpy
            shown_delta = delta if delta is not None else magnitude
            shown_delta = (shown_delta / q).to_integral_value(rounding=ROUND_HALF_EVEN) * q if shown_delta is not None else None
            shown_target = (target / q).to_integral_value(rounding=ROUND_HALF_EVEN) * q if target is not None else None
        return ProfitImpactResult(
            result_id=request.request_id,
            entity_id=request.entity_id,
            forecast_period=request.forecast_period,
            forecast_version=request.forecast_version,
            scenario=request.scenario,
            request_hash=request.record_hash,
            status=status,
            stage=stages.get(status, ImpactStage.DISCLOSURE),
            reason=reason,
            audit=audit,
            magnitude_delta_jpy=magnitude,
            signed_delta_jpy=delta,
            baseline_pretax_jpy=baseline,
            conditional_target_pretax_jpy=target,
            displayed_delta_jpy=shown_delta,
            displayed_target_jpy=shown_target,
            money_quantum_jpy=q,
            created_at=request.created_at,
            supersedes_result_id=request.supersedes_result_id,
            baseline_origin=request.baseline.origin if target is not None and request.baseline is not None else None,
        )

    try:
        validate_tree(request)
    except (ValueError, TypeError, AttributeError, DecimalException) as exc:
        return outcome(ImpactStatus.INTEGRITY_ERROR, str(exc))
    if not request.disclosures:
        return outcome(ImpactStatus.INSUFFICIENT_INPUT, "at least one source disclosure required")
    for records, field in (
        (request.disclosures, "disclosure_id"),
        (request.artifacts, "artifact_id"),
        (request.sensitivities, "sensitivity_id"),
        (request.shocks, "sensitivity_id"),
    ):
        ids = [getattr(r, field) for r in records]
        if len(set(ids)) != len(ids):
            return outcome(ImpactStatus.INSUFFICIENT_INPUT, "ambiguous/duplicate input IDs")
    artifacts = {a.artifact_id: a for a in request.artifacts}
    sources = {d.disclosure_id: d for d in request.disclosures}
    source: SourceDisclosureRecord | None
    for source in request.disclosures:
        artifact = artifacts.get(source.artifact_id)
        if artifact is None or artifact.record_hash != source.artifact_hash or artifact.source_url != source.source_url:
            return outcome(ImpactStatus.INTEGRITY_ERROR, "exact source artifact reference missing/mismatched")
        if (source.entity_id, source.forecast_period, source.forecast_version) != (
            request.entity_id,
            request.forecast_period,
            request.forecast_version,
        ):
            return outcome(ImpactStatus.IDENTITY_MISMATCH, "disclosure entity/period/version mismatch")
    if request.record_only:
        if request.sensitivities or request.shocks or request.baseline or request.coverage or request.composition:
            return outcome(ImpactStatus.INSUFFICIENT_INPUT, "record-only cannot silently ignore calculation inputs")
        return outcome(ImpactStatus.SOURCE_RECORDED, "archived disclosure only; unknown conditions retained, no numeric outcome")
    if request.created_at > request.evidence_cutoff:
        return outcome(ImpactStatus.PIT_INVALID, "request created after cutoff")
    if not request.sensitivities or {s.sensitivity_id for s in request.sensitivities} != {
        s.sensitivity_id for s in request.shocks
    }:
        return outcome(ImpactStatus.INSUFFICIENT_INPUT, "exact sensitivity/shock set required")
    if len({s.driver for s in request.sensitivities}) != len(request.sensitivities) or len(
        {s.disclosure_id for s in request.sensitivities}
    ) != len(request.sensitivities):
        return outcome(
            ImpactStatus.DOUBLE_COUNT_RISK, "same consolidated driver/source cannot be added twice under different IDs"
        )
    context = request_context_hash(request)
    composition = request.composition
    refs = tuple((s.sensitivity_id, s.record_hash) for s in request.sensitivities)
    if len(request.sensitivities) > 1 and composition is None:
        return outcome(ImpactStatus.DOUBLE_COUNT_RISK, "joint effects require source-backed composition")
    for proof in (request.baseline, request.coverage, composition):
        if proof is not None:
            if not proof.available_at <= proof.created_at <= request.created_at <= request.evidence_cutoff:
                return outcome(ImpactStatus.PIT_INVALID, "optional input creation/availability chronology invalid")
            if proof.source_ref not in artifacts:
                return outcome(ImpactStatus.SOURCE_NOT_VERIFIED, "baseline/coverage/composition evidence artifact missing")
            # Proof references must refer to an archive with a disclosure in the
            # same snapshot and with usable observed-time verification.
            if not any(
                d.artifact_id == proof.source_ref
                and _verified_company_source(d)
                and _source_time_ok(d, request)
                and d.system_available_at is not None
                and d.system_available_at <= proof.available_at
                for d in request.disclosures
            ):
                return outcome(ImpactStatus.SOURCE_NOT_VERIFIED, "proof source unavailable/unverified")
    if composition is not None and (composition.sensitivity_refs != refs or composition.request_context_hash != context):
        return outcome(ImpactStatus.IDENTITY_MISMATCH, "composition does not bind exact scenario/source set")
    if request.coverage is not None and request.baseline is None:
        return outcome(ImpactStatus.INSUFFICIENT_INPUT, "coverage requires an exact pretax baseline")
    shocks = {s.sensitivity_id: s for s in request.shocks}
    signed: list[Decimal] = []
    magnitudes: list[Decimal] = []
    covered: set[str] = set()
    adopted: list[ImpactAudit] = []
    with localcontext(Context(prec=80, rounding=ROUND_HALF_EVEN)):
        try:
            for sensitivity in request.sensitivities:

                def reject(status: ImpactStatus, reason: str) -> ProfitImpactResult:
                    nonlocal audit
                    audit = tuple(
                        replace(a, disposition="REJECTED", reason=reason) if a.sensitivity_id == sensitivity.sensitivity_id else a
                        for a in audit
                    )
                    return outcome(status, reason)

                source = sources.get(sensitivity.disclosure_id)
                shock = shocks[sensitivity.sensitivity_id]
                if source is None or source.record_hash != sensitivity.disclosure_hash:
                    return reject(ImpactStatus.INTEGRITY_ERROR, "exact disclosure reference missing")
                if not _verified_company_source(source):
                    return reject(ImpactStatus.SOURCE_NOT_VERIFIED, "source values not verified")
                if not _source_time_ok(source, request) or not shock.available_at <= shock.created_at <= request.created_at:
                    return reject(ImpactStatus.PIT_INVALID, "source/shock unavailable under SYSTEM_OBSERVED cutoff")
                if (
                    (sensitivity.entity_id, sensitivity.forecast_period, sensitivity.forecast_version, sensitivity.profit_metric)
                    != (request.entity_id, request.forecast_period, request.forecast_version, "PRETAX_INCOME")
                    or source.profit_metric != "PRETAX_INCOME"
                    or source.scope != "CONSOLIDATED"
                ):
                    return reject(ImpactStatus.IDENTITY_MISMATCH, "only same-period consolidated pretax income supported")
                if (
                    source.driver not in DRIVER_UNITS
                    or source.driver_unit != DRIVER_UNITS[source.driver]
                    or source.currency != "JPY"
                ):
                    return reject(ImpactStatus.UNIT_MISMATCH, "unknown source currency/driver unit")
                if (sensitivity.driver, sensitivity.driver_unit, shock.driver, shock.unit) != (
                    source.driver,
                    source.driver_unit,
                    source.driver,
                    source.driver_unit,
                ):
                    return reject(ImpactStatus.UNIT_MISMATCH, "driver/unit mismatch")
                expected = normalize_sensitivity(
                    source, sensitivity_id=sensitivity.sensitivity_id, coverage_keys=sensitivity.coverage_keys
                )
                if sensitivity != expected:
                    return reject(ImpactStatus.INTEGRITY_ERROR, "normalized value/metric/direction differs from original source")
                if source.applicability is Applicability.UNKNOWN or not source.applicability_basis:
                    return reject(ImpactStatus.APPLICABILITY_UNKNOWN, "source applicability is unknown")
                if shock.baseline_level is not None and shock.scenario_level is not None:
                    if shock.scenario_level - shock.baseline_level != shock.change:
                        return reject(ImpactStatus.IDENTITY_MISMATCH, "shock differs from absolute level difference")
                    if source.base_level is not None and source.base_level != shock.baseline_level:
                        return reject(ImpactStatus.IDENTITY_MISMATCH, "shock baseline differs from company source assumptions")
                if source.applicability is Applicability.DISCLOSED_UNIT_ONLY:
                    if shock.change != 0 and abs(shock.change) != sensitivity.driver_step:
                        return reject(
                            ImpactStatus.OUTSIDE_DISCLOSED_APPLICATION, "only exact disclosed one-unit or zero shock allowed"
                        )
                else:
                    if shock.baseline_level is None or shock.scenario_level is None:
                        return reject(ImpactStatus.INSUFFICIENT_INPUT, "verified range requires absolute levels")
                    assert source.minimum_level is not None and source.maximum_level is not None
                    if not (
                        source.minimum_level <= shock.baseline_level <= source.maximum_level
                        and source.minimum_level <= shock.scenario_level <= source.maximum_level
                    ):
                        return reject(ImpactStatus.OUTSIDE_DISCLOSED_APPLICATION, "shock outside verified linear range")
                if covered.intersection(sensitivity.coverage_keys):
                    return reject(ImpactStatus.DOUBLE_COUNT_RISK, "economic coverage overlaps")
                covered.update(sensitivity.coverage_keys)
                key = increment_key(request, sensitivity)
                if request.coverage is not None and key in request.coverage.applied_increment_keys:
                    return reject(ImpactStatus.DOUBLE_COUNT_RISK, "same increment already applied")
                magnitude = sensitivity.magnitude_jpy * abs(shock.change) / sensitivity.driver_step
                delta = (
                    None
                    if sensitivity.direction is Direction.UNKNOWN
                    else (
                        sensitivity.magnitude_jpy
                        * shock.change
                        / sensitivity.driver_step
                        * (Decimal(1) if sensitivity.direction is Direction.POSITIVE else Decimal(-1))
                    )
                )
                magnitudes.append(magnitude)
                if delta is not None:
                    signed.append(delta)
                adopted.append(
                    ImpactAudit(
                        sensitivity_id=sensitivity.sensitivity_id,
                        input_hash=sensitivity.record_hash,
                        disposition="ADOPTED",
                        reason="conditional disclosed period impact",
                        shock_origin=shock.origin,
                        increment_key=key,
                        magnitude_delta_jpy=magnitude,
                        signed_delta_jpy=delta,
                    )
                )
                audit = tuple(
                    next((a for a in adopted if a.sensitivity_id == original.sensitivity_id), original) for original in audit
                )
            if len(signed) != len(request.sensitivities):
                if len(request.sensitivities) != 1:
                    return outcome(ImpactStatus.INSUFFICIENT_INPUT, "unknown directions cannot be combined as a net magnitude")
                return outcome(
                    ImpactStatus.SUCCESS_MAGNITUDE_ONLY,
                    "direction unknown; signed impact/absolute target withheld",
                    magnitude=magnitudes[0],
                )
            delta = sum(signed, Decimal(0))
            if request.baseline is None:
                return outcome(
                    ImpactStatus.SUCCESS_SIGNED_DELTA,
                    "conditional signed pretax delta; no verified baseline target",
                    magnitude=abs(delta),
                    delta=delta,
                )
            baseline = request.baseline
            if (
                baseline.entity_id,
                baseline.forecast_period,
                baseline.forecast_version,
                baseline.profit_metric,
                baseline.scope,
            ) != (request.entity_id, request.forecast_period, request.forecast_version, "PRETAX_INCOME", "CONSOLIDATED"):
                return outcome(ImpactStatus.IDENTITY_MISMATCH, "pretax baseline identity/version/scope mismatch")
            if (
                request.coverage is None
                or not request.coverage.complete
                or request.coverage.baseline_hash != baseline.record_hash
                or (request.coverage.request_context_hash != context)
            ):
                return outcome(ImpactStatus.DOUBLE_COUNT_RISK, "complete exact baseline/context coverage required for target")
            levels = dict(baseline.driver_levels)
            for sensitivity in request.sensitivities:
                source = sources[sensitivity.disclosure_id]
                shock = shocks[sensitivity.sensitivity_id]
                if source.base_level is None or shock.baseline_level is None or levels.get(source.driver) != source.base_level:
                    return outcome(
                        ImpactStatus.INSUFFICIENT_INPUT, "absolute target requires verified company baseline driver levels"
                    )
                if (baseline.other_base_conditions, baseline.inventory_treatment, baseline.fx_coverage) != (
                    source.other_base_conditions,
                    source.inventory_treatment,
                    source.fx_coverage,
                ):
                    return outcome(ImpactStatus.DOUBLE_COUNT_RISK, "baseline/disclosure condition or scope mismatch")
            target = baseline.value_jpy + delta
            return outcome(
                ImpactStatus.SUCCESS_CONDITIONAL_TARGET,
                "conditional same-metric target, not actual forecast performance",
                magnitude=abs(delta),
                delta=delta,
                baseline=baseline.value_jpy,
                target=target,
            )
        except (DecimalException, ValueError, TypeError) as exc:
            return outcome(ImpactStatus.CALCULATION_ERROR, f"declared arithmetic/source contract failed: {exc}")
