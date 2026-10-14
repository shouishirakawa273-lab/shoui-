"""Read-only, partial prerequisites inventory; never a calculation acceptance gate."""

from __future__ import annotations

import json
from typing import cast

from lib.evidence.model import AvailabilityBasis

from .calculation import validate_tree
from .model import (
    DRIVER_UNITS,
    MONEY_SCALES,
    Applicability,
    Direction,
    ImpactSchemaError,
    ProfitImpactRequest,
    SourceDisclosureRecord,
)
from .store import _decode


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ImpactSchemaError("duplicate JSON key")
        result[key] = value
    return result


def _constant(value: str) -> object:
    raise ImpactSchemaError(f"nonstandard JSON constant: {value}")


def decode_request(text: str) -> ProfitImpactRequest:
    """Reuse the immutable store's raw-hash-before-constructor strict decoder."""
    data = json.loads(text, object_pairs_hook=_object, parse_constant=_constant)
    request = cast(ProfitImpactRequest, _decode(data, ProfitImpactRequest))
    validate_tree(request)
    return request


def inspect_request(request: ProfitImpactRequest) -> dict[str, object]:
    validate_tree(request)
    findings: list[dict[str, str]] = []

    def note(scope: str, code: str, disclosure_id: str = "") -> None:
        findings.append({"scope": scope, "code": code, "disclosure_id": disclosure_id})

    artifacts = {a.artifact_id: a for a in request.artifacts}
    for records, field in (
        (request.artifacts, "artifact_id"),
        (request.disclosures, "disclosure_id"),
        (request.sensitivities, "sensitivity_id"),
        (request.shocks, "sensitivity_id"),
    ):
        identifiers = [getattr(record, field) for record in records]
        if len(identifiers) != len(set(identifiers)):
            note("ARCHIVE", f"DUPLICATE_{field.upper()}")
    if not request.disclosures:
        note("ARCHIVE", "SOURCE_DISCLOSURE_MISSING")
    if request.record_only and (
        request.sensitivities or request.shocks or request.baseline or request.coverage or request.composition
    ):
        note("ARCHIVE", "RECORD_ONLY_HAS_CALCULATION_INPUTS")
    source: SourceDisclosureRecord | None
    for source in request.disclosures:
        sid = source.disclosure_id
        artifact = artifacts.get(source.artifact_id)
        if artifact is None or artifact.record_hash != source.artifact_hash or artifact.source_url != source.source_url:
            note("ARCHIVE", "ARTIFACT_REFERENCE_MISMATCH", sid)
        if (source.entity_id, source.forecast_period, source.forecast_version) != (
            request.entity_id,
            request.forecast_period,
            request.forecast_version,
        ):
            note("ARCHIVE", "DISCLOSURE_IDENTITY_MISMATCH", sid)
        if not source.values_verified:
            note("CALCULATION", "VALUES_VERIFICATION_NOT_DECLARED", sid)
        if source.source_authority_class is None or source.source_authority_class.value != "PRIMARY_OFFICIAL":
            note("CALCULATION", "OFFICIAL_AUTHORITY_NOT_DECLARED", sid)
        if source.primary_or_secondary is None or source.primary_or_secondary.value != "PRIMARY":
            note("CALCULATION", "PRIMARY_SOURCE_NOT_DECLARED", sid)
        if source.profit_metric != "PRETAX_INCOME" or source.scope != "CONSOLIDATED":
            note("CALCULATION", "SUPPORTED_METRIC_SCOPE_UNCONFIRMED", sid)
        if (
            source.currency != "JPY"
            or source.profit_unit not in MONEY_SCALES
            or source.driver_unit != DRIVER_UNITS.get(source.driver)
        ):
            note("CALCULATION", "SUPPORTED_UNITS_UNCONFIRMED", sid)
        if source.driver_step is None or source.impact_magnitude is None:
            note("CALCULATION", "SOURCE_NUMERIC_FIELDS_MISSING", sid)
        if source.applicability is Applicability.UNKNOWN or not source.applicability_basis:
            note("CALCULATION", "APPLICABILITY_UNCONFIRMED", sid)
        if source.direction is Direction.UNKNOWN:
            note("SIGNED_DELTA", "DIRECTION_UNKNOWN", sid)
        if source.exact_public_at is None:
            note("HISTORICAL_REPLAY", "EXACT_PUBLIC_TIME_UNKNOWN", sid)
        times = (source.retrieved_at, source.normalized_created_at, source.system_available_at)
        if any(t is None for t in times) or source.availability_basis is not AvailabilityBasis.OBSERVED:
            note("CALCULATION", "SYSTEM_OBSERVED_AVAILABILITY_UNCONFIRMED", sid)
        else:
            retrieved, normalized, available = times
            assert retrieved is not None and normalized is not None and available is not None
            if not retrieved <= normalized <= available <= request.created_at <= request.evidence_cutoff:
                note("CALCULATION", "SOURCE_CHRONOLOGY_INVALID", sid)
            if source.exact_public_at is not None and source.exact_public_at > retrieved:
                note("CALCULATION", "PUBLIC_TIME_AFTER_RETRIEVAL", sid)
        if source.disclosed_on is not None and source.publication_timezone is None:
            note("CALCULATION", "PUBLICATION_TIMEZONE_MISSING", sid)
    if not request.sensitivities:
        note("CALCULATION", "SENSITIVITIES_MISSING")
    if not request.shocks:
        note("CALCULATION", "SHOCKS_MISSING")
    if {s.sensitivity_id for s in request.sensitivities} != {s.sensitivity_id for s in request.shocks}:
        note("CALCULATION", "SENSITIVITY_SHOCK_SET_MISMATCH")
    sources = {s.disclosure_id: s for s in request.disclosures}
    sensitivities = {s.sensitivity_id: s for s in request.sensitivities}
    for shock in request.shocks:
        sensitivity = sensitivities.get(shock.sensitivity_id)
        source = sources.get(sensitivity.disclosure_id) if sensitivity is not None else None
        if not shock.available_at <= shock.created_at <= request.created_at <= request.evidence_cutoff:
            note("CALCULATION", "SHOCK_CHRONOLOGY_INVALID", shock.sensitivity_id)
        if sensitivity is None or source is None:
            note("CALCULATION", "SENSITIVITY_SOURCE_REFERENCE_MISSING", shock.sensitivity_id)
            continue
        if sensitivity.disclosure_hash != source.record_hash:
            note("CALCULATION", "SENSITIVITY_SOURCE_HASH_MISMATCH", source.disclosure_id)
        if (shock.driver, shock.unit) != (source.driver, source.driver_unit):
            note("CALCULATION", "SHOCK_DRIVER_UNIT_MISMATCH", source.disclosure_id)
        if source.applicability is Applicability.DISCLOSED_UNIT_ONLY and source.driver_step is not None:
            if shock.change != 0 and abs(shock.change) != source.driver_step:
                note("CALCULATION", "SHOCK_OUTSIDE_DISCLOSED_UNIT", source.disclosure_id)
        if source.applicability is Applicability.VERIFIED_LINEAR_RANGE:
            if shock.baseline_level is None or shock.scenario_level is None:
                note("CALCULATION", "ABSOLUTE_DRIVER_LEVELS_MISSING", source.disclosure_id)
            elif source.minimum_level is not None and source.maximum_level is not None:
                if not (
                    source.minimum_level <= shock.baseline_level <= source.maximum_level
                    and source.minimum_level <= shock.scenario_level <= source.maximum_level
                ):
                    note("CALCULATION", "SHOCK_OUTSIDE_VERIFIED_RANGE", source.disclosure_id)
    if len(request.sensitivities) > 1 and request.composition is None:
        note("CALCULATION", "JOINT_COMPOSITION_MISSING")
    if request.baseline is None:
        note("TARGET", "PRETAX_BASELINE_MISSING")
    if request.coverage is None or not request.coverage.complete:
        note("TARGET", "COMPLETE_COVERAGE_MISSING")
    findings.sort(key=lambda item: (item["scope"], item["disclosure_id"], item["code"]))
    return {
        "request_id": request.request_id,
        "request_hash": request.record_hash,
        "input_integrity": "VERIFIED_PAYLOAD_HASH",
        "archive_status": "BLOCKED" if any(f["scope"] == "ARCHIVE" for f in findings) else "STRUCTURALLY_READY",
        "calculation_status": "NOT_EVALUATED",
        "original_source_bytes_verified": "NOT_CHECKED",
        "source_semantic_truth": "NOT_CHECKED_CALLER_DECLARATIONS_ONLY",
        "history_duplicate_ids_and_correction_parents": "NOT_ASSESSED",
        "source_claims": [
            {
                "disclosure_id": s.disclosure_id,
                "scope": s.scope,
                "direction": s.direction.value,
                "applicability": s.applicability.value,
                "exact_public_time_known": s.exact_public_at is not None,
                "system_available_time_known": s.system_available_at is not None,
                "limitations": s.limitations,
                "declared_values_verified": s.values_verified,
                "declared_source_authority": s.source_authority_class.value if s.source_authority_class else None,
                "declared_primary_or_secondary": s.primary_or_secondary.value if s.primary_or_secondary else None,
            }
            for s in request.disclosures
        ],
        "findings": findings,
        "limitations": (
            "Partial prerequisite inventory; archive structure is not store-history compatibility. "
            "No forecast, calculation acceptance, persistence or numeric output."
        ),
    }
