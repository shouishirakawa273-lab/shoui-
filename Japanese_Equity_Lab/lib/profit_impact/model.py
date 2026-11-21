"""Immutable disclosure and conditional impact contracts, including unknowns."""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from zoneinfo import ZoneInfo

from lib.evaluation.integrity import compute_record_hash
from lib.evidence.model import AvailabilityBasis
from lib.evidence.thesis_impact import ThesisScenario
from lib.sources.catalog import PrimaryOrSecondary, SourceAuthorityClass

RULE_VERSION = "PRETAX_IMPACT_V1_P80_HALF_EVEN"
ADAPTER_UNAVAILABLE = "D0109_OPERATING_INCOME_ADAPTER_UNAVAILABLE"
DRIVER_UNITS = {"GOLD": "USD/troy_oz", "COPPER": "USD/metric_tonne", "USDJPY": "JPY/USD"}
MONEY_SCALES = {
    "JPY": Decimal(1),
    "JPY_MILLION": Decimal("1e6"),
    "JPY_BILLION": Decimal("1e9"),
    "JPY_100_MILLION": Decimal("1e8"),
}


class ImpactSchemaError(ValueError):
    """Structural errors; economic/availability failures are typed results."""


class Direction(StrEnum):
    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"
    UNKNOWN = "UNKNOWN"


class Applicability(StrEnum):
    DISCLOSED_UNIT_ONLY = "DISCLOSED_UNIT_ONLY"
    VERIFIED_LINEAR_RANGE = "VERIFIED_LINEAR_RANGE"
    UNKNOWN = "UNKNOWN"


class ImpactStatus(StrEnum):
    SOURCE_RECORDED = "SOURCE_RECORDED"
    SUCCESS_MAGNITUDE_ONLY = "SUCCESS_MAGNITUDE_ONLY"
    SUCCESS_SIGNED_DELTA = "SUCCESS_SIGNED_DELTA"
    SUCCESS_CONDITIONAL_TARGET = "SUCCESS_CONDITIONAL_TARGET"
    INSUFFICIENT_INPUT = "INSUFFICIENT_INPUT"
    SOURCE_NOT_VERIFIED = "SOURCE_NOT_VERIFIED"
    PIT_INVALID = "PIT_INVALID"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    UNIT_MISMATCH = "UNIT_MISMATCH"
    APPLICABILITY_UNKNOWN = "APPLICABILITY_UNKNOWN"
    OUTSIDE_DISCLOSED_APPLICATION = "OUTSIDE_DISCLOSED_APPLICATION"
    DOUBLE_COUNT_RISK = "DOUBLE_COUNT_RISK"
    INTEGRITY_ERROR = "INTEGRITY_ERROR"
    CALCULATION_ERROR = "CALCULATION_ERROR"


class ImpactStage(StrEnum):
    DISCLOSURE = "DISCLOSURE"
    MAGNITUDE = "MAGNITUDE"
    SIGNED_DELTA = "SIGNED_DELTA"
    TARGET = "TARGET"


def require_text(value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ImpactSchemaError("nonempty string required")


def require_decimal(value: object, *, positive: bool = False, nonnegative: bool = False) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ImpactSchemaError("finite Decimal required")
    if positive and value <= 0 or nonnegative and value < 0:
        raise ImpactSchemaError("invalid Decimal sign")


def require_time(value: object) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ImpactSchemaError("aware timestamp required")


def require_refs(values: tuple[str, ...], *, empty: bool = False) -> None:
    if not isinstance(values, tuple) or not empty and not values:
        raise ImpactSchemaError("immutable reference tuple required")
    for value in values:
        require_text(value)
    if tuple(sorted(set(values))) != values:
        raise ImpactSchemaError("references must be unique and sorted")


def seal(record: object) -> None:
    if getattr(record, "record_hash") == "":
        object.__setattr__(record, "record_hash", compute_record_hash({f.name: getattr(record, f.name) for f in fields(record)}))  # type: ignore[arg-type]


@dataclass(frozen=True, kw_only=True)
class SourceArtifact:
    """Caller-supplied source evidence excerpt, never a fetched/PDF-parsed claim."""

    artifact_id: str
    source_url: str
    content: str
    record_hash: str = ""

    def __post_init__(self) -> None:
        value: object
        for value in (self.artifact_id, self.source_url, self.content):
            require_text(value)
        seal(self)


@dataclass(frozen=True, kw_only=True)
class SourceDisclosureRecord:
    disclosure_id: str
    entity_id: str
    title: str
    forecast_period: str
    forecast_version: str
    scope: str
    source_url: str
    pdf_page_index: int
    printed_page: str
    table_locator: str
    artifact_id: str
    artifact_hash: str
    profit_metric: str
    profit_unit: str | None
    currency: str | None
    driver: str
    driver_unit: str | None
    driver_step: Decimal | None
    impact_magnitude: Decimal | None
    direction: Direction
    direction_basis: str | None
    applicability: Applicability
    applicability_basis: str | None
    minimum_level: Decimal | None
    maximum_level: Decimal | None
    base_level: Decimal | None
    inventory_treatment: str
    fx_coverage: str
    other_base_conditions: tuple[tuple[str, str], ...]
    limitations: str
    disclosed_on: date | None
    exact_public_at: datetime | None
    retrieved_at: datetime | None
    normalized_created_at: datetime | None
    system_available_at: datetime | None
    availability_basis: AvailabilityBasis
    values_verified: bool
    extraction_method_version: str
    source_authority_class: SourceAuthorityClass | None = None
    primary_or_secondary: PrimaryOrSecondary | None = None
    publication_timezone: str | None = None
    supersedes_disclosure_id: str | None = None
    record_hash: str = ""

    def __post_init__(self) -> None:
        value: object
        for name in (
            "disclosure_id",
            "entity_id",
            "title",
            "forecast_period",
            "forecast_version",
            "scope",
            "source_url",
            "printed_page",
            "table_locator",
            "artifact_id",
            "artifact_hash",
            "profit_metric",
            "driver",
            "inventory_treatment",
            "fx_coverage",
            "limitations",
            "extraction_method_version",
        ):
            require_text(getattr(self, name))
        if type(self.pdf_page_index) is not int or self.pdf_page_index < 0 or type(self.values_verified) is not bool:
            raise ImpactSchemaError("invalid page/verification flag")
        if not isinstance(self.direction, Direction) or not isinstance(self.applicability, Applicability):
            raise ImpactSchemaError("direction/applicability type mismatch")
        if not isinstance(self.availability_basis, AvailabilityBasis):
            raise ImpactSchemaError("availability basis type mismatch")
        if self.source_authority_class is not None and not isinstance(self.source_authority_class, SourceAuthorityClass):
            raise ImpactSchemaError("source authority type mismatch")
        if self.primary_or_secondary is not None and not isinstance(self.primary_or_secondary, PrimaryOrSecondary):
            raise ImpactSchemaError("primary/secondary type mismatch")
        for value in (self.exact_public_at, self.retrieved_at, self.normalized_created_at, self.system_available_at):
            if value is not None:
                require_time(value)
        if self.disclosed_on is not None and type(self.disclosed_on) is not date:
            raise ImpactSchemaError("publication date must not be a guessed timestamp")
        if self.publication_timezone is not None:
            require_text(self.publication_timezone)
            try:
                ZoneInfo(self.publication_timezone)
            except (KeyError, ValueError) as exc:
                raise ImpactSchemaError("known publication timezone required") from exc
        for value in (self.driver_step, self.minimum_level, self.maximum_level, self.base_level):
            if value is not None:
                require_decimal(value, positive=True)
        if self.impact_magnitude is not None:
            require_decimal(self.impact_magnitude, nonnegative=True)
        if self.direction is not Direction.UNKNOWN and not self.direction_basis:
            raise ImpactSchemaError("signed sensitivity requires explicit source basis")
        if self.applicability is Applicability.VERIFIED_LINEAR_RANGE:
            if self.minimum_level is None or self.maximum_level is None or not self.applicability_basis:
                raise ImpactSchemaError("verified range requires source bounds/basis")
            if self.minimum_level > self.maximum_level:
                raise ImpactSchemaError("reversed source range")
        for value in (self.direction_basis, self.applicability_basis, self.supersedes_disclosure_id):
            if value is not None:
                require_text(value)
        if not isinstance(self.other_base_conditions, tuple):
            raise ImpactSchemaError("immutable base conditions required")
        for pair in self.other_base_conditions:
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise ImpactSchemaError("condition pair required")
            require_text(pair[0])
            require_text(pair[1])
        if tuple(k for k, _ in self.other_base_conditions) != tuple(sorted({k for k, _ in self.other_base_conditions})):
            raise ImpactSchemaError("base conditions must have unique sorted names")
        seal(self)


@dataclass(frozen=True, kw_only=True)
class NormalizedSensitivity:
    sensitivity_id: str
    disclosure_id: str
    disclosure_hash: str
    entity_id: str
    forecast_period: str
    forecast_version: str
    profit_metric: str
    driver: str
    driver_step: Decimal
    driver_unit: str
    magnitude_jpy: Decimal
    direction: Direction
    coverage_keys: tuple[str, ...]
    record_hash: str = ""

    def __post_init__(self) -> None:
        for name in (
            "sensitivity_id",
            "disclosure_id",
            "disclosure_hash",
            "entity_id",
            "forecast_period",
            "forecast_version",
            "profit_metric",
            "driver",
            "driver_unit",
        ):
            require_text(getattr(self, name))
        require_decimal(self.driver_step, positive=True)
        require_decimal(self.magnitude_jpy, nonnegative=True)
        if not isinstance(self.direction, Direction):
            raise ImpactSchemaError("direction enum required")
        require_refs(self.coverage_keys)
        seal(self)


@dataclass(frozen=True, kw_only=True)
class DriverShock:
    sensitivity_id: str
    driver: str
    unit: str
    change: Decimal
    origin: str
    rationale: str
    available_at: datetime
    created_at: datetime
    baseline_level: Decimal | None = None
    scenario_level: Decimal | None = None
    semantics: str = "DISCLOSED_PERIOD_ASSUMPTION_CHANGE"

    def __post_init__(self) -> None:
        value: object
        for value in (self.sensitivity_id, self.driver, self.unit, self.rationale):
            require_text(value)
        require_decimal(self.change)
        for value in (self.baseline_level, self.scenario_level):
            if value is not None:
                require_decimal(value, positive=True)
        if (self.baseline_level is None) != (self.scenario_level is None):
            raise ImpactSchemaError("absolute driver levels must be supplied together")
        if (
            self.origin not in ("COMPANY_DISCLOSED", "RESEARCH_JUDGMENT")
            or self.semantics != "DISCLOSED_PERIOD_ASSUMPTION_CHANGE"
        ):
            raise ImpactSchemaError("explicit period shock and origin required")
        require_time(self.available_at)
        require_time(self.created_at)


@dataclass(frozen=True, kw_only=True)
class PretaxBaseline:
    baseline_id: str
    entity_id: str
    forecast_period: str
    forecast_version: str
    scope: str
    profit_metric: str
    value_jpy: Decimal
    origin: str
    driver_levels: tuple[tuple[str, Decimal], ...]
    other_base_conditions: tuple[tuple[str, str], ...]
    inventory_treatment: str
    fx_coverage: str
    source_ref: str
    available_at: datetime
    created_at: datetime
    record_hash: str = ""

    def __post_init__(self) -> None:
        value: object
        for name in (
            "baseline_id",
            "entity_id",
            "forecast_period",
            "forecast_version",
            "scope",
            "profit_metric",
            "source_ref",
            "inventory_treatment",
            "fx_coverage",
        ):
            require_text(getattr(self, name))
        require_decimal(self.value_jpy)
        if self.origin not in ("COMPANY_GUIDANCE", "OBSERVED_HISTORICAL", "RESEARCH_JUDGMENT"):
            raise ImpactSchemaError("baseline origin must be explicit")
        if not isinstance(self.driver_levels, tuple) or not isinstance(self.other_base_conditions, tuple):
            raise ImpactSchemaError("immutable baseline conditions required")
        for driver, value in self.driver_levels:
            require_text(driver)
            require_decimal(value, positive=True)
        if tuple(d for d, _ in self.driver_levels) != tuple(sorted({d for d, _ in self.driver_levels})):
            raise ImpactSchemaError("unique sorted baseline driver levels required")
        for key, value in self.other_base_conditions:
            require_text(key)
            require_text(value)
        if tuple(k for k, _ in self.other_base_conditions) != tuple(sorted({k for k, _ in self.other_base_conditions})):
            raise ImpactSchemaError("unique sorted baseline conditions required")
        require_time(self.available_at)
        require_time(self.created_at)
        seal(self)


@dataclass(frozen=True, kw_only=True)
class ImpactCoverage:
    baseline_hash: str
    request_context_hash: str
    applied_increment_keys: tuple[str, ...]
    complete: bool
    source_ref: str
    rationale: str
    available_at: datetime
    created_at: datetime

    def __post_init__(self) -> None:
        value: object
        for value in (self.baseline_hash, self.request_context_hash, self.source_ref, self.rationale):
            require_text(value)
        require_refs(self.applied_increment_keys, empty=True)
        if type(self.complete) is not bool:
            raise ImpactSchemaError("coverage completeness must be explicit")
        require_time(self.available_at)
        require_time(self.created_at)


@dataclass(frozen=True, kw_only=True)
class ImpactComposition:
    sensitivity_refs: tuple[tuple[str, str], ...]
    request_context_hash: str
    source_ref: str
    rationale: str
    available_at: datetime
    created_at: datetime

    def __post_init__(self) -> None:
        value: object
        for value in (self.request_context_hash, self.source_ref, self.rationale):
            require_text(value)
        if not isinstance(self.sensitivity_refs, tuple) or not self.sensitivity_refs:
            raise ImpactSchemaError("exact immutable sensitivity references required")
        for pair in self.sensitivity_refs:
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise ImpactSchemaError("sensitivity ID/hash pair required")
            require_text(pair[0])
            require_text(pair[1])
        if tuple(sorted(set(self.sensitivity_refs))) != self.sensitivity_refs:
            raise ImpactSchemaError("sensitivity references must be unique sorted pairs")
        require_time(self.available_at)
        require_time(self.created_at)


@dataclass(frozen=True, kw_only=True)
class ProfitImpactRequest:
    request_id: str
    entity_id: str
    forecast_period: str
    forecast_version: str
    scenario: ThesisScenario
    evidence_cutoff: datetime
    created_at: datetime
    artifacts: tuple[SourceArtifact, ...]
    disclosures: tuple[SourceDisclosureRecord, ...]
    sensitivities: tuple[NormalizedSensitivity, ...]
    shocks: tuple[DriverShock, ...]
    record_only: bool = False
    baseline: PretaxBaseline | None = None
    coverage: ImpactCoverage | None = None
    composition: ImpactComposition | None = None
    money_quantum_jpy: Decimal = Decimal(1)
    supersedes_result_id: str | None = None
    record_hash: str = ""

    def __post_init__(self) -> None:
        value: object
        kind: type[object]
        for value in (self.request_id, self.entity_id, self.forecast_period, self.forecast_version):
            require_text(value)
        if not isinstance(self.scenario, ThesisScenario) or type(self.record_only) is not bool:
            raise ImpactSchemaError("scenario and record-only type mismatch")
        require_time(self.evidence_cutoff)
        require_time(self.created_at)
        require_decimal(self.money_quantum_jpy, positive=True)
        for name, kind, id_field in (
            ("artifacts", SourceArtifact, "artifact_id"),
            ("disclosures", SourceDisclosureRecord, "disclosure_id"),
            ("sensitivities", NormalizedSensitivity, "sensitivity_id"),
            ("shocks", DriverShock, "sensitivity_id"),
        ):
            values = getattr(self, name)
            if not isinstance(values, tuple) or not all(isinstance(v, kind) for v in values):
                raise ImpactSchemaError(f"{name}: immutable typed tuple required")
            object.__setattr__(
                self, name, tuple(sorted(values, key=lambda v: (getattr(v, id_field), compute_record_hash({"v": v}))))
            )
        for value, kind in (
            (self.baseline, PretaxBaseline),
            (self.coverage, ImpactCoverage),
            (self.composition, ImpactComposition),
        ):
            if value is not None and not isinstance(value, kind):
                raise ImpactSchemaError("optional baseline/coverage/composition type mismatch")
        if self.supersedes_result_id is not None:
            require_text(self.supersedes_result_id)
        seal(self)


@dataclass(frozen=True, kw_only=True)
class ImpactAudit:
    sensitivity_id: str
    input_hash: str
    disposition: str
    reason: str
    shock_origin: str = "NOT_EVALUATED"
    increment_key: str | None = None
    magnitude_delta_jpy: Decimal | None = None
    signed_delta_jpy: Decimal | None = None


@dataclass(frozen=True, kw_only=True)
class ProfitImpactResult:
    result_id: str
    entity_id: str
    forecast_period: str
    forecast_version: str
    scenario: ThesisScenario
    request_hash: str
    status: ImpactStatus
    stage: ImpactStage
    reason: str
    audit: tuple[ImpactAudit, ...]
    magnitude_delta_jpy: Decimal | None
    signed_delta_jpy: Decimal | None
    baseline_pretax_jpy: Decimal | None
    conditional_target_pretax_jpy: Decimal | None
    displayed_delta_jpy: Decimal | None
    displayed_target_jpy: Decimal | None
    money_quantum_jpy: Decimal
    created_at: datetime
    supersedes_result_id: str | None
    baseline_origin: str | None = None
    adapter_status: str = ADAPTER_UNAVAILABLE
    rule_version: str = RULE_VERSION
    conditional_label: str = "CONDITIONAL_COMPANY_MODEL_IMPACT_NOT_ACTUAL_OR_CAUSAL"
    record_hash: str = ""

    def __post_init__(self) -> None:
        value: object
        for value in (
            self.result_id,
            self.entity_id,
            self.forecast_period,
            self.forecast_version,
            self.request_hash,
            self.reason,
        ):
            require_text(value)
        if (
            not isinstance(self.status, ImpactStatus)
            or not isinstance(self.stage, ImpactStage)
            or not isinstance(self.scenario, ThesisScenario)
        ):
            raise ImpactSchemaError("result enum type mismatch")
        if (
            self.adapter_status != ADAPTER_UNAVAILABLE
            or self.rule_version != RULE_VERSION
            or self.conditional_label != ("CONDITIONAL_COMPANY_MODEL_IMPACT_NOT_ACTUAL_OR_CAUSAL")
        ):
            raise ImpactSchemaError("output boundary/version label mismatch")
        require_time(self.created_at)
        require_decimal(self.money_quantum_jpy, positive=True)
        for value in (
            self.magnitude_delta_jpy,
            self.signed_delta_jpy,
            self.baseline_pretax_jpy,
            self.conditional_target_pretax_jpy,
            self.displayed_delta_jpy,
            self.displayed_target_jpy,
        ):
            if value is not None:
                require_decimal(value)
        if self.magnitude_delta_jpy is not None:
            require_decimal(self.magnitude_delta_jpy, nonnegative=True)
        expected = {
            ImpactStatus.SOURCE_RECORDED: ImpactStage.DISCLOSURE,
            ImpactStatus.SUCCESS_MAGNITUDE_ONLY: ImpactStage.MAGNITUDE,
            ImpactStatus.SUCCESS_SIGNED_DELTA: ImpactStage.SIGNED_DELTA,
            ImpactStatus.SUCCESS_CONDITIONAL_TARGET: ImpactStage.TARGET,
        }
        if self.status in expected:
            if self.stage is not expected[self.status]:
                raise ImpactSchemaError("successful status/stage mismatch")
            if self.stage is ImpactStage.DISCLOSURE:
                if any(
                    v is not None
                    for v in (
                        self.magnitude_delta_jpy,
                        self.signed_delta_jpy,
                        self.baseline_pretax_jpy,
                        self.conditional_target_pretax_jpy,
                        self.displayed_delta_jpy,
                        self.displayed_target_jpy,
                    )
                ):
                    raise ImpactSchemaError("disclosure-only cannot emit calculation")
            elif self.stage is ImpactStage.MAGNITUDE:
                if (
                    self.magnitude_delta_jpy is None
                    or self.signed_delta_jpy is not None
                    or self.conditional_target_pretax_jpy is not None
                ):
                    raise ImpactSchemaError("magnitude-only boundary violated")
            elif self.signed_delta_jpy is None or self.magnitude_delta_jpy is None:
                raise ImpactSchemaError("signed/target success requires signed delta")
            if self.stage is ImpactStage.SIGNED_DELTA and self.conditional_target_pretax_jpy is not None:
                raise ImpactSchemaError("delta-only cannot emit absolute target")
            if self.stage is ImpactStage.TARGET and (
                self.baseline_pretax_jpy is None or self.conditional_target_pretax_jpy is None
            ):
                raise ImpactSchemaError("target requires verified baseline")
            if self.stage is ImpactStage.TARGET and self.baseline_origin not in (
                "COMPANY_GUIDANCE",
                "OBSERVED_HISTORICAL",
                "RESEARCH_JUDGMENT",
            ):
                raise ImpactSchemaError("target requires explicit baseline origin")
            if self.stage is not ImpactStage.TARGET and self.baseline_origin is not None:
                raise ImpactSchemaError("baseline origin only belongs to a computed target")
        elif any(
            v is not None
            for v in (
                self.magnitude_delta_jpy,
                self.signed_delta_jpy,
                self.baseline_pretax_jpy,
                self.conditional_target_pretax_jpy,
                self.displayed_delta_jpy,
                self.displayed_target_jpy,
            )
        ):
            raise ImpactSchemaError("failure cannot emit a successful numeric outcome")
        seal(self)
