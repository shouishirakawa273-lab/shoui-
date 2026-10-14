"""Single-writer D0107 append-only adapters; no new persistence mechanism.

Do not concurrently write a store from multiple processes: the underlying
repository store has no locking/transaction protocol. All reads verify hashes.
"""

from __future__ import annotations

import types
from dataclasses import fields, is_dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Generic, TypeVar, cast, get_args, get_origin, get_type_hints

from lib.errors import AppendOnlyViolationError
from lib.evaluation.integrity import compute_record_hash, to_hashable, verify_record_integrity
from lib.evaluation.store import AppendOnlyRecordStore

from .measurement import economic_key, revision_key
from .model import EventResponseSchemaError, ObservedEventWindowResponse, ResponseStatus, SurpriseResponseLink

T = TypeVar("T", ObservedEventWindowResponse, SurpriseResponseLink)


def _decode(value: object, annotation: Any) -> Any:
    """Decode only the statically supplied record schema; no type names from disk."""
    origin, args = get_origin(annotation), get_args(annotation)
    if origin is types.UnionType:
        if value is None and type(None) in args:
            return None
        return _decode(value, next(t for t in args if t is not type(None)))
    if origin is tuple:
        if not isinstance(value, list):
            raise EventResponseSchemaError("stored tuple must be an array")
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_decode(item, args[0]) for item in value)
        if len(value) != len(args):
            raise EventResponseSchemaError("stored tuple length mismatch")
        return tuple(_decode(item, t) for item, t in zip(value, args, strict=True))
    if annotation in (datetime, Decimal):
        if not isinstance(value, str):
            raise EventResponseSchemaError("stored time/decimal must be a string")
        return datetime.fromisoformat(value) if annotation is datetime else Decimal(value)
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return annotation(value)
    if isinstance(annotation, type) and is_dataclass(annotation):
        if not isinstance(value, dict):
            raise EventResponseSchemaError("stored record must be an object")
        # Verify the original serialized payload before any constructor canonicalization.
        # Otherwise a reordered nested definition or empty hash could be silently repaired.
        if "record_hash" in value and compute_record_hash(value) != value["record_hash"]:
            raise EventResponseSchemaError("serialized record integrity failure")
        hints = get_type_hints(annotation)
        if set(value) != {f.name for f in fields(annotation)}:
            raise EventResponseSchemaError("stored record fields mismatch")
        return annotation(**{name: _decode(value[name], t) for name, t in hints.items()})
    if annotation in (str, int, bool) and type(value) is annotation:
        return value
    raise EventResponseSchemaError("stored scalar type mismatch")


def validate_record(record: ObservedEventWindowResponse | SurpriseResponseLink) -> None:
    if not verify_record_integrity(record):
        raise EventResponseSchemaError("stored record integrity failure")
    if isinstance(record, ObservedEventWindowResponse):
        for quote in (record.pre, record.post):
            if quote is not None and not verify_record_integrity(quote):
                raise EventResponseSchemaError("stored observation integrity failure")
        economic = economic_key(record.event_id, record.series, record.window_kind)
        if record.economic_observation_key != economic:
            raise EventResponseSchemaError("economic observation key mismatch")
        if record.status is ResponseStatus.SUCCESS:
            assert record.pre is not None and record.post is not None
            expected = revision_key(
                economic=economic,
                event_hash=record.event_hash,
                release_id=record.release_id,
                release_hash=record.release_hash,
                window_hash=record.window_policy_hash,
                pre_hash=record.pre.record_hash,
                post_hash=record.post.record_hash,
            )
            if record.measurement_revision_key != expected:
                raise EventResponseSchemaError("measurement revision key mismatch")


class EventResponseStore(Generic[T]):
    """Idempotent same-content append, explicit correction lineage, verified reads."""

    def __init__(
        self, path: Path, record_type: type[T], *, response_store: EventResponseStore[ObservedEventWindowResponse] | None = None
    ) -> None:
        self._record_type: type[T] = record_type
        self._response_store = response_store

        def encode(record: T) -> dict[str, object]:
            return cast(dict[str, object], to_hashable(record))

        def decode(data: dict[str, object]) -> T:
            record = cast(T, _decode(data, record_type))
            validate_record(record)
            return record

        self._store: AppendOnlyRecordStore[T] = AppendOnlyRecordStore(path, id_of=self._id, to_dict=encode, from_dict=decode)

    def _id(self, record: T) -> str:
        return record.response_id if isinstance(record, ObservedEventWindowResponse) else record.link_id

    def all(self) -> list[T]:
        return self._store.all()

    def get(self, record_id: str) -> T | None:
        return self._store.get(record_id)

    def record(self, record: T) -> T:
        if not isinstance(record, self._record_type):
            raise EventResponseSchemaError("wrong store record type")
        validate_record(record)
        existing = self.get(self._id(record))
        if existing is not None:
            if existing != record:
                raise AppendOnlyViolationError("same ID with different content")
            return existing
        if isinstance(record, ObservedEventWindowResponse) and record.supersedes_response_id is not None:
            seen = {record.response_id}
            parent_id: str | None = record.supersedes_response_id
            while parent_id is not None:
                if parent_id in seen:
                    raise AppendOnlyViolationError("cyclic correction reference")
                seen.add(parent_id)
                parent = self.get(parent_id)
                if not isinstance(parent, ObservedEventWindowResponse):
                    raise AppendOnlyViolationError("correction parent must already exist")
                if parent.economic_observation_key != record.economic_observation_key:
                    raise AppendOnlyViolationError("correction parent has different economic identity")
                if parent.calculated_at > record.calculated_at:
                    raise AppendOnlyViolationError("correction cannot precede parent calculation")
                parent_id = parent.supersedes_response_id
        if isinstance(record, SurpriseResponseLink):
            if self._response_store is None:
                raise EventResponseSchemaError("link storage requires the response store")
            response = self._response_store.get(record.response_id)
            if response is None or response.record_hash != record.response_hash:
                raise AppendOnlyViolationError("link must reference a stored exact response")
        self._store.record(record)
        return record


def new_response_store(path: Path) -> EventResponseStore[ObservedEventWindowResponse]:
    return EventResponseStore(path, ObservedEventWindowResponse)


def new_link_store(
    path: Path,
    response_store: EventResponseStore[ObservedEventWindowResponse],
) -> EventResponseStore[SurpriseResponseLink]:
    return EventResponseStore(path, SurpriseResponseLink, response_store=response_store)


def select_measurement_revision(
    records: list[ObservedEventWindowResponse],
    *,
    economic_observation_key: str,
    response_id: str,
) -> ObservedEventWindowResponse:
    """Explicit selection only: never pick the newest correction automatically."""
    matches = [r for r in records if r.economic_observation_key == economic_observation_key and r.response_id == response_id]
    if len(matches) != 1:
        raise EventResponseSchemaError("explicit revision must resolve uniquely")
    validate_record(matches[0])
    return matches[0]


def observation_counts(records: list[ObservedEventWindowResponse]) -> tuple[int, int, int]:
    """Stored calculations, successful economic observations, distinct successful events."""
    for record in records:
        validate_record(record)
    successful = [r for r in records if r.status is ResponseStatus.SUCCESS]
    return len(records), len({r.economic_observation_key for r in successful}), len({r.event_id for r in successful})
