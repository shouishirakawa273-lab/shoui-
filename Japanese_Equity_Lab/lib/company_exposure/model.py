"""Explicit immutable exposure, period assumptions and coverage contracts."""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from lib.evaluation.integrity import compute_record_hash
from lib.evidence.model import EvidenceRecord
from lib.evidence.thesis_impact import ThesisScenario
from lib.forecasting.model import FundamentalForecastResult, HistoricalFundamentalBase, ScenarioAssumptions

RULE_VERSION = "COMPANY_EXPOSURE_BRIDGE_V1_P80_REPLAY28"
DRIVER_UNITS = {"GOLD": "USD/troy_oz", "COPPER": "USD/metric_tonne", "USDJPY": "JPY/USD"}
MONEY_SCALES = {"JPY": Decimal(1), "JPY_MILLION": Decimal("1000000"), "JPY_BILLION": Decimal("1000000000")}


class ExposureSchemaError(ValueError):
    """Malformed record, distinct from an economic or PIT failure."""


class ExposureSource(StrEnum):
    COMPANY_DISCLOSED = "COMPANY_DISCLOSED"
    DETERMINISTIC_DERIVED = "DETERMINISTIC_DERIVED"
    STATISTICALLY_ESTIMATED = "STATISTICALLY_ESTIMATED"
    RESEARCH_JUDGMENT = "RESEARCH_JUDGMENT"


class BridgeStatus(StrEnum):
    SUCCESS = "SUCCESS"
    INSUFFICIENT_INPUT = "INSUFFICIENT_INPUT"
    PIT_INVALID = "PIT_INVALID"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    UNSUPPORTED_METRIC = "UNSUPPORTED_METRIC"
    UNSUPPORTED_SOURCE = "UNSUPPORTED_SOURCE"
    UNSUPPORTED_REVENUE_EFFECT = "UNSUPPORTED_REVENUE_EFFECT"
    UNKNOWN_BASELINE_COVERAGE = "UNKNOWN_BASELINE_COVERAGE"
    DOUBLE_COUNT_RISK = "DOUBLE_COUNT_RISK"
    OUTSIDE_SENSITIVITY_RANGE = "OUTSIDE_SENSITIVITY_RANGE"
    INVALID_BASELINE = "INVALID_BASELINE"
    PRECISION_INCOMPATIBLE = "PRECISION_INCOMPATIBLE"
    INTEGRITY_ERROR = "INTEGRITY_ERROR"


def text(value: object, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ExposureSchemaError(f"{name}: nonempty string required")


def decimal(value: object, name: str, *, positive: bool = False) -> None:
    if not isinstance(value, Decimal) or not value.is_finite() or (positive and value <= 0):
        raise ExposureSchemaError(f"{name}: finite Decimal{' > 0' if positive else ''} required")


def time(value: object) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ExposureSchemaError("timezone-aware timestamp required")


def names(values: tuple[str, ...], *, empty: bool = False) -> None:
    if not isinstance(values, tuple) or (not empty and not values):
        raise ExposureSchemaError("nonempty immutable tuple required")
    for value in values:
        text(value, "reference")
    if tuple(sorted(set(values))) != values:
        raise ExposureSchemaError("references must be unique and sorted")


def seal(record: object) -> None:
    if getattr(record, "record_hash") == "":
        object.__setattr__(record, "record_hash", compute_record_hash({f.name: getattr(record, f.name) for f in fields(record)}))  # type: ignore[arg-type]


@dataclass(frozen=True, kw_only=True)
class ExposureCondition:
    driver: str
    level: Decimal
    unit: str

    def __post_init__(self) -> None:
        if DRIVER_UNITS.get(self.driver) != self.unit:
            raise ExposureSchemaError("unknown condition driver/unit")
        decimal(self.level, "condition level", positive=True)


@dataclass(frozen=True, kw_only=True)
class CompanyExposure:
    exposure_id: str
    version: str
    entity_id: str
    driver: str
    driver_unit: str
    driver_step: Decimal
    sensitivity_amount: Decimal
    profit_unit: str
    currency: str
    profit_metric: str
    scope: str
    forecast_period: str
    applicable_from: datetime
    applicable_until: datetime
    minimum_level: Decimal
    maximum_level: Decimal
    base_conditions: tuple[ExposureCondition, ...]
    other_base_assumptions: tuple[tuple[str, str], ...]
    source_type: ExposureSource
    source_id: str
    source_url: str
    source_locator: str
    evidence_ids: tuple[str, ...]
    disclosed_at: datetime
    available_at: datetime
    interaction_group: str
    coverage_keys: tuple[str, ...]
    limitations: str
    affects_revenue: bool = False
    conversion_rule: str | None = None
    disclosed_sensitivity_amount: Decimal | None = None
    disclosed_profit_unit: str | None = None
    record_hash: str = ""

    def __post_init__(self) -> None:
        for name in (
            "exposure_id",
            "version",
            "entity_id",
            "profit_metric",
            "scope",
            "forecast_period",
            "source_id",
            "source_url",
            "source_locator",
            "interaction_group",
            "limitations",
        ):
            text(getattr(self, name), name)
        if self.currency != "JPY" or self.profit_unit not in MONEY_SCALES or DRIVER_UNITS.get(self.driver) != self.driver_unit:
            raise ExposureSchemaError("unsupported unit/currency")
        decimal(self.driver_step, "driver_step", positive=True)
        decimal(self.sensitivity_amount, "sensitivity")
        decimal(self.minimum_level, "minimum", positive=True)
        decimal(self.maximum_level, "maximum", positive=True)
        if self.minimum_level > self.maximum_level:
            raise ExposureSchemaError("reversed sensitivity range")
        for value in (self.applicable_from, self.applicable_until, self.disclosed_at, self.available_at):
            time(value)
        if self.applicable_from > self.applicable_until or self.disclosed_at > self.available_at:
            raise ExposureSchemaError("reversed exposure time range")
        if not isinstance(self.source_type, ExposureSource) or type(self.affects_revenue) is not bool:
            raise ExposureSchemaError("source/bool type mismatch")
        if not isinstance(self.base_conditions, tuple) or not self.base_conditions:
            raise ExposureSchemaError("explicit base conditions required")
        for condition in self.base_conditions:
            if not isinstance(condition, ExposureCondition):
                raise ExposureSchemaError("invalid condition")
        if tuple(c.driver for c in self.base_conditions) != tuple(sorted({c.driver for c in self.base_conditions})):
            raise ExposureSchemaError("base conditions must be unique and sorted")
        if self.driver not in {c.driver for c in self.base_conditions}:
            raise ExposureSchemaError("own driver base condition required")
        if not isinstance(self.other_base_assumptions, tuple):
            raise ExposureSchemaError("immutable base assumptions required")
        for pair in self.other_base_assumptions:
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise ExposureSchemaError("base assumption pair required")
            text(pair[0], "base assumption name")
            text(pair[1], "base assumption value")
        if tuple(k for k, _ in self.other_base_assumptions) != tuple(sorted({k for k, _ in self.other_base_assumptions})):
            raise ExposureSchemaError("base assumption names must be unique and sorted")
        names(self.evidence_ids)
        names(self.coverage_keys)
        if (
            self.source_type is ExposureSource.DETERMINISTIC_DERIVED
            and self.conversion_rule != "EXPLICIT_DECIMAL_UNIT_SCALE_ONLY"
        ):
            raise ExposureSchemaError("derived exposure requires explicit unit-only conversion rule")
        if self.source_type is ExposureSource.DETERMINISTIC_DERIVED:
            decimal(self.disclosed_sensitivity_amount, "original disclosed sensitivity")
            if self.disclosed_profit_unit not in MONEY_SCALES:
                raise ExposureSchemaError("original disclosed profit unit required")
        elif self.disclosed_sensitivity_amount is not None or self.disclosed_profit_unit is not None:
            raise ExposureSchemaError("unit conversion origin belongs only to derived exposure")
        seal(self)


@dataclass(frozen=True, kw_only=True)
class DriverAssumption:
    assumption_id: str
    entity_id: str
    forecast_period: str
    scenario: ThesisScenario
    driver: str
    unit: str
    baseline_level: Decimal
    scenario_level: Decimal
    available_at: datetime
    created_at: datetime
    evidence_ids: tuple[str, ...]
    rationale: str
    is_research_judgment: bool = False
    semantics: str = "PERIOD_LEVEL"
    record_hash: str = ""

    def __post_init__(self) -> None:
        for name in ("assumption_id", "entity_id", "forecast_period", "rationale"):
            text(getattr(self, name), name)
        if DRIVER_UNITS.get(self.driver) != self.unit or self.semantics != "PERIOD_LEVEL":
            raise ExposureSchemaError("only explicit period-level drivers supported")
        if not isinstance(self.scenario, ThesisScenario) or type(self.is_research_judgment) is not bool:
            raise ExposureSchemaError("scenario/source type mismatch")
        decimal(self.baseline_level, "baseline_level", positive=True)
        decimal(self.scenario_level, "scenario_level", positive=True)
        time(self.available_at)
        time(self.created_at)
        names(self.evidence_ids, empty=self.is_research_judgment)
        seal(self)


@dataclass(frozen=True, kw_only=True)
class BaselineCoverage:
    """Verified baseline levels and effects already included; no implicit completeness."""

    entity_id: str
    forecast_period: str
    scenario: ThesisScenario
    levels: tuple[ExposureCondition, ...]
    other_base_assumptions: tuple[tuple[str, str], ...]
    applied_increment_keys: tuple[str, ...]
    complete: bool
    evidence_ids: tuple[str, ...]
    rationale: str
    available_at: datetime
    created_at: datetime
    baseline_input_hash: str = "UNBOUND"
    record_hash: str = ""

    def __post_init__(self) -> None:
        text(self.entity_id, "entity")
        text(self.forecast_period, "period")
        text(self.rationale, "rationale")
        text(self.baseline_input_hash, "baseline input hash")
        if not isinstance(self.scenario, ThesisScenario) or type(self.complete) is not bool:
            raise ExposureSchemaError("invalid coverage scenario/complete")
        if not isinstance(self.levels, tuple) or not all(isinstance(c, ExposureCondition) for c in self.levels):
            raise ExposureSchemaError("immutable levels required")
        if tuple(c.driver for c in self.levels) != tuple(sorted({c.driver for c in self.levels})):
            raise ExposureSchemaError("unique sorted coverage levels required")
        for pair in self.other_base_assumptions:
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise ExposureSchemaError("coverage base assumption pair required")
            text(pair[0], "condition name")
            text(pair[1], "condition value")
        if not isinstance(self.other_base_assumptions, tuple) or tuple(k for k, _ in self.other_base_assumptions) != tuple(
            sorted({k for k, _ in self.other_base_assumptions})
        ):
            raise ExposureSchemaError("unique sorted coverage conditions required")
        names(self.applied_increment_keys, empty=True)
        names(self.evidence_ids)
        time(self.available_at)
        time(self.created_at)
        seal(self)


@dataclass(frozen=True, kw_only=True)
class CompositionDeclaration:
    """Source-backed permission for this exact exposure set, never inferred by group name."""

    exposure_ids: tuple[str, ...]
    joint_conditions: tuple[ExposureCondition, ...]
    evidence_ids: tuple[str, ...]
    rationale: str
    available_at: datetime
    created_at: datetime
    record_hash: str = ""

    def __post_init__(self) -> None:
        names(self.exposure_ids)
        names(self.evidence_ids)
        text(self.rationale, "composition rationale")
        time(self.available_at)
        time(self.created_at)
        if not isinstance(self.joint_conditions, tuple) or not all(
            isinstance(c, ExposureCondition) for c in self.joint_conditions
        ):
            raise ExposureSchemaError("joint conditions must be immutable")
        if tuple(c.driver for c in self.joint_conditions) != tuple(sorted({c.driver for c in self.joint_conditions})):
            raise ExposureSchemaError("joint conditions must be unique and sorted")
        seal(self)


@dataclass(frozen=True, kw_only=True)
class BridgeRequest:
    request_id: str
    entity_id: str
    forecast_period: str
    scenario: ThesisScenario
    period_start: datetime
    period_end: datetime
    evidence_cutoff: datetime
    created_at: datetime
    research_snapshot_id: str
    exposures: tuple[CompanyExposure, ...]
    drivers: tuple[DriverAssumption, ...]
    coverage: BaselineCoverage
    baseline_scenarios: tuple[ScenarioAssumptions, ...]
    historical_bases: tuple[HistoricalFundamentalBase, ...]
    evidence_records: tuple[EvidenceRecord, ...]
    money_quantum: Decimal = Decimal(1)
    composition: CompositionDeclaration | None = None
    observed_response_refs: tuple[tuple[str, str], ...] = ()
    supersedes_result_id: str | None = None
    record_hash: str = ""

    def __post_init__(self) -> None:
        for name in ("request_id", "entity_id", "forecast_period", "research_snapshot_id"):
            text(getattr(self, name), name)
        if not isinstance(self.scenario, ThesisScenario) or not isinstance(self.coverage, BaselineCoverage):
            raise ExposureSchemaError("scenario/coverage type mismatch")
        for value in (self.period_start, self.period_end, self.evidence_cutoff, self.created_at):
            time(value)
        if self.period_start > self.period_end:
            raise ExposureSchemaError("reversed forecast period")
        decimal(self.money_quantum, "money_quantum", positive=True)
        for name, record_type in (
            ("exposures", CompanyExposure),
            ("drivers", DriverAssumption),
            ("baseline_scenarios", ScenarioAssumptions),
            ("historical_bases", HistoricalFundamentalBase),
            ("evidence_records", EvidenceRecord),
        ):
            value = getattr(self, name)
            if not isinstance(value, tuple) or not all(isinstance(item, record_type) for item in value):
                raise ExposureSchemaError(f"{name}: immutable typed tuple required")
        if self.composition is not None and not isinstance(self.composition, CompositionDeclaration):
            raise ExposureSchemaError("composition type mismatch")
        if not isinstance(self.observed_response_refs, tuple):
            raise ExposureSchemaError("immutable audit references required")
        for pair in self.observed_response_refs:
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise ExposureSchemaError("observed audit reference requires ID/hash")
            text(pair[0], "response ID")
            text(pair[1], "response hash")
        if self.supersedes_result_id is not None:
            text(self.supersedes_result_id, "supersedes")
        # Candidate order is canonicalized at construction, never by validation or reads.
        object.__setattr__(self, "exposures", tuple(sorted(self.exposures, key=lambda e: (e.exposure_id, e.record_hash))))
        object.__setattr__(self, "drivers", tuple(sorted(self.drivers, key=lambda d: (d.driver, d.assumption_id))))
        object.__setattr__(self, "baseline_scenarios", tuple(sorted(self.baseline_scenarios, key=lambda s: s.scenario.value)))
        object.__setattr__(self, "historical_bases", tuple(sorted(self.historical_bases, key=lambda b: (b.metric, b.source_id))))
        object.__setattr__(self, "evidence_records", tuple(sorted(self.evidence_records, key=lambda e: e.evidence_id)))
        object.__setattr__(self, "observed_response_refs", tuple(sorted(self.observed_response_refs)))
        seal(self)


@dataclass(frozen=True, kw_only=True)
class CandidateAudit:
    exposure_id: str
    exposure_hash: str
    disposition: str
    reason: str
    increment_key: str | None = None
    delta_jpy: Decimal | None = None


@dataclass(frozen=True, kw_only=True)
class BridgeResult:
    result_id: str
    entity_id: str
    forecast_period: str
    scenario: ThesisScenario
    request_hash: str
    input_refs: tuple[tuple[str, str], ...]
    status: BridgeStatus
    reason: str
    audit: tuple[CandidateAudit, ...]
    created_at: datetime
    baseline_forecast: FundamentalForecastResult | None
    replay_forecast: FundamentalForecastResult | None
    adjusted_scenarios: tuple[ScenarioAssumptions, ...]
    baseline_operating_income_jpy: Decimal | None
    target_operating_income_jpy: Decimal | None
    replay_operating_income_jpy: Decimal | None
    rounding_difference_jpy: Decimal | None
    money_quantum: Decimal
    supersedes_result_id: str | None
    rule_version: str = RULE_VERSION
    record_hash: str = ""

    def __post_init__(self) -> None:
        for name in ("result_id", "entity_id", "forecast_period", "request_hash", "reason"):
            text(getattr(self, name), name)
        time(self.created_at)
        decimal(self.money_quantum, "quantum", positive=True)
        if (
            not isinstance(self.status, BridgeStatus)
            or not isinstance(self.scenario, ThesisScenario)
            or self.rule_version != RULE_VERSION
        ):
            raise ExposureSchemaError("result status/scenario/version mismatch")
        if self.status is BridgeStatus.SUCCESS:
            if not self.adjusted_scenarios or self.baseline_forecast is None or self.replay_forecast is None:
                raise ExposureSchemaError("success requires actual D0109 replay")
            for name in (
                "baseline_operating_income_jpy",
                "target_operating_income_jpy",
                "replay_operating_income_jpy",
                "rounding_difference_jpy",
            ):
                decimal(getattr(self, name), name)
        elif self.adjusted_scenarios or self.replay_forecast is not None:
            raise ExposureSchemaError("failure cannot emit successful forecast assumptions")
        seal(self)
