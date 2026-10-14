"""Immutable point observations and explicit event-window contracts (D0110.2).

All hashes reuse D0107. An economic observation, a measurement revision,
and a stored calculation are deliberately separate identities.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum

from lib.evaluation.integrity import compute_record_hash

RULE_VERSION = "EVENT_RESPONSE_DECIMAL_V1"
NON_CAUSAL = "OBSERVED_ASSOCIATION_ONLY"


class EventResponseSchemaError(ValueError):
    """Malformed input structure, distinct from typed measurement outcomes."""


class MeasureKind(StrEnum):
    PRICE = "PRICE"
    YIELD = "YIELD"


class WindowKind(StrEnum):
    FIVE_MINUTES = "5M"
    THIRTY_MINUTES = "30M"
    TWENTY_FOUR_HOURS = "24H"
    JAPAN_NEXT_SESSION = "JAPAN_NEXT_SESSION"


class ResponseStatus(StrEnum):
    SUCCESS = "SUCCESS"
    MISSING_OBSERVATION = "MISSING_OBSERVATION"
    WINDOW_NOT_COMPLETE = "WINDOW_NOT_COMPLETE"
    PIT_INVALID = "PIT_INVALID"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    UNIT_MISMATCH = "UNIT_MISMATCH"
    AMBIGUOUS_INPUT = "AMBIGUOUS_INPUT"
    INVALID_INPUT = "INVALID_INPUT"
    UNSUPPORTED_WINDOW = "UNSUPPORTED_WINDOW"
    INTEGRITY_FAILURE = "INTEGRITY_FAILURE"


def require_string(value: object, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise EventResponseSchemaError(f"{label} must be a nonempty string")


def require_time(value: object, label: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise EventResponseSchemaError(f"{label} must be a timezone-aware datetime")


def seal(record: object) -> None:
    """Compute a hash only for a newly constructed record, never repair a hash."""
    if getattr(record, "record_hash") == "":
        payload = {f.name: getattr(record, f.name) for f in fields(record)}  # type: ignore[arg-type]
        object.__setattr__(record, "record_hash", compute_record_hash(payload))


@dataclass(frozen=True, kw_only=True)
class ObservationSeriesKey:
    instrument_id: str
    instrument_definition: tuple[tuple[str, str], ...]
    measure_kind: MeasureKind
    unit: str
    quote_convention: str
    source_id: str

    def __post_init__(self) -> None:
        for name in ("instrument_id", "unit", "quote_convention", "source_id"):
            require_string(getattr(self, name), name)
        if not isinstance(self.measure_kind, MeasureKind):
            raise EventResponseSchemaError("measure_kind must be MeasureKind")
        if not isinstance(self.instrument_definition, tuple) or not self.instrument_definition:
            raise EventResponseSchemaError("instrument_definition must be a nonempty tuple")
        for pair in self.instrument_definition:
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise EventResponseSchemaError("instrument_definition requires (name, value) pairs")
            require_string(pair[0], "definition name")
            require_string(pair[1], "definition value")
        names = [p[0] for p in self.instrument_definition]
        if len(names) != len(set(names)):
            raise EventResponseSchemaError("duplicate definition name")
        object.__setattr__(self, "instrument_definition", tuple(sorted(self.instrument_definition)))


@dataclass(frozen=True, kw_only=True)
class MarketObservation:
    observation_id: str
    series: ObservationSeriesKey
    value: Decimal
    observed_at: datetime
    available_at: datetime
    source_version: str | None = None
    record_hash: str = ""

    def __post_init__(self) -> None:
        require_string(self.observation_id, "observation_id")
        if not isinstance(self.series, ObservationSeriesKey):
            raise EventResponseSchemaError("series must be ObservationSeriesKey")
        if not isinstance(self.value, Decimal):
            raise EventResponseSchemaError("value must be Decimal")
        require_time(self.observed_at, "observed_at")
        require_time(self.available_at, "available_at")
        if self.source_version is not None:
            require_string(self.source_version, "source_version")
        seal(self)


@dataclass(frozen=True, kw_only=True)
class EventWindowSpec:
    window_id: str
    kind: WindowKind
    policy_version: str
    pre_max_age: timedelta
    post_max_lag: timedelta
    record_hash: str = ""

    def __post_init__(self) -> None:
        require_string(self.window_id, "window_id")
        require_string(self.policy_version, "policy_version")
        if not isinstance(self.kind, WindowKind):
            raise EventResponseSchemaError("kind must be WindowKind")
        if not isinstance(self.pre_max_age, timedelta) or not isinstance(self.post_max_lag, timedelta):
            raise EventResponseSchemaError("window distances must be timedelta")
        # D0107 hash serialization has no timedelta support: hash explicit integer microseconds.
        if not self.record_hash:
            object.__setattr__(self, "record_hash", compute_record_hash(self.hash_payload()))

    def hash_payload(self) -> dict[str, object]:
        return {
            "window_id": self.window_id,
            "kind": self.kind,
            "policy_version": self.policy_version,
            "pre_max_age_us": duration_us(self.pre_max_age),
            "post_max_lag_us": duration_us(self.post_max_lag),
        }

    @property
    def offset(self) -> timedelta | None:
        return {
            WindowKind.FIVE_MINUTES: timedelta(minutes=5),
            WindowKind.THIRTY_MINUTES: timedelta(minutes=30),
            WindowKind.TWENTY_FOUR_HOURS: timedelta(hours=24),
        }.get(self.kind)


def duration_us(value: timedelta) -> int:
    return (value.days * 86400 + value.seconds) * 1000000 + value.microseconds


@dataclass(frozen=True, kw_only=True)
class SelectionAudit:
    observation_id: str
    observation_hash: str
    pre_reason: str
    post_reason: str


@dataclass(frozen=True, kw_only=True)
class ObservedEventWindowResponse:
    response_id: str
    economic_observation_key: str
    measurement_revision_key: str | None
    supersedes_response_id: str | None
    event_id: str
    event_version: int
    event_hash: str
    release_id: str
    release_hash: str
    actual_public_at: datetime
    series: ObservationSeriesKey
    window_id: str
    window_kind: WindowKind
    window_policy_hash: str
    target_post_at: datetime | None
    pre: MarketObservation | None
    post: MarketObservation | None
    pre_age_us: int | None
    post_lag_us: int | None
    selection_audit: tuple[SelectionAudit, ...]
    measurement_rule_id: str
    change_value: Decimal | None
    change_unit: str | None
    relative_change_percent: Decimal | None
    relative_change_unit: str | None
    evaluation_cutoff: datetime
    calculated_at: datetime
    available_at: datetime
    status: ResponseStatus
    reason: str | None
    non_causal_label: str = NON_CAUSAL
    record_hash: str = ""

    def __post_init__(self) -> None:
        require_string(self.response_id, "response_id")
        if not isinstance(self.status, ResponseStatus):
            raise EventResponseSchemaError("status must be ResponseStatus")
        for name in ("actual_public_at", "evaluation_cutoff", "calculated_at", "available_at"):
            require_time(getattr(self, name), name)
        if self.status is ResponseStatus.SUCCESS:
            if self.pre is None or self.post is None or self.change_value is None or self.change_unit is None:
                raise EventResponseSchemaError("SUCCESS requires selected observations and change")
        elif any(
            v is not None for v in (self.change_value, self.change_unit, self.relative_change_percent, self.relative_change_unit)
        ):
            raise EventResponseSchemaError("failure cannot carry measurement values")
        if self.non_causal_label != NON_CAUSAL:
            raise EventResponseSchemaError("response must retain its non-causal label")
        seal(self)


@dataclass(frozen=True, kw_only=True)
class SurpriseResponseLink:
    link_id: str
    response_id: str
    response_hash: str
    event_id: str
    event_hash: str
    anchor_release_id: str
    anchor_release_hash: str
    surprise_id: str
    surprise_hash: str
    consensus_snapshot_id: str
    consensus_hash: str
    first_release_id: str
    first_release_hash: str
    dimension: str
    link_cutoff: datetime
    linked_at: datetime
    available_at: datetime
    record_hash: str = ""

    def __post_init__(self) -> None:
        for name in ("link_id", "response_id", "event_id", "surprise_id", "consensus_snapshot_id", "dimension"):
            require_string(getattr(self, name), name)
        for name in ("link_cutoff", "linked_at", "available_at"):
            require_time(getattr(self, name), name)
        seal(self)


@dataclass(frozen=True, kw_only=True)
class LinkResult:
    status: ResponseStatus
    link: SurpriseResponseLink | None
    reason: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.status, ResponseStatus) or (self.status is ResponseStatus.SUCCESS) != (self.link is not None):
            raise EventResponseSchemaError("invalid LinkResult")
