"""Single-writer adapter over the frozen D0107 append-only store."""

from __future__ import annotations

import types
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, cast, get_args, get_origin, get_type_hints

from lib.errors import AppendOnlyViolationError
from lib.evaluation.integrity import compute_record_hash, to_hashable
from lib.evaluation.store import AppendOnlyRecordStore

from .bridge import compute_exposure_bridge, validate_tree
from .model import BridgeRequest, BridgeResult, ExposureSchemaError


def _decode(value: object, annotation: Any) -> Any:
    origin, args = get_origin(annotation), get_args(annotation)
    if origin is types.UnionType:
        if value is None and type(None) in args:
            return None
        return _decode(value, next(t for t in args if t is not type(None)))
    if origin is tuple:
        if not isinstance(value, list):
            raise ExposureSchemaError("stored tuple requires array")
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_decode(v, args[0]) for v in value)
        if len(value) != len(args):
            raise ExposureSchemaError("stored tuple length mismatch")
        return tuple(_decode(v, t) for v, t in zip(value, args, strict=True))
    if annotation in (date, datetime, Decimal):
        if not isinstance(value, str):
            raise ExposureSchemaError("stored decimal/time must be string")
        if annotation is datetime:
            return datetime.fromisoformat(value)
        return date.fromisoformat(value) if annotation is date else Decimal(value)
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return annotation(value)
    if isinstance(annotation, type) and is_dataclass(annotation):
        if not isinstance(value, dict) or set(value) != {f.name for f in fields(annotation)}:
            raise ExposureSchemaError("stored record fields mismatch")
        if "record_hash" in value and compute_record_hash(value) != value["record_hash"]:
            raise ExposureSchemaError("raw stored hash mismatch")
        hints = get_type_hints(annotation)
        return annotation(**{name: _decode(value[name], hint) for name, hint in hints.items()})
    if annotation in (str, bool, int) and type(value) is annotation:
        return value
    raise ExposureSchemaError("stored scalar type mismatch")


class CompanyExposureInputStore:
    """Retain full immutable request snapshots for deterministic result reconstruction."""

    def __init__(self, path: Path) -> None:
        def decode(data: dict[str, object]) -> BridgeRequest:
            request = cast(BridgeRequest, _decode(data, BridgeRequest))
            validate_tree(request)
            return request

        self._store: AppendOnlyRecordStore[BridgeRequest] = AppendOnlyRecordStore(
            path,
            id_of=lambda r: r.request_id,
            to_dict=lambda r: cast(dict[str, object], to_hashable(r)),
            from_dict=decode,
        )

    def get(self, request_id: str) -> BridgeRequest | None:
        records = self._store.all()
        if len({r.request_id for r in records}) != len(records):
            raise ExposureSchemaError("duplicate request IDs in stored input")
        return next((r for r in records if r.request_id == request_id), None)

    def record(self, request: BridgeRequest) -> BridgeRequest:
        if not isinstance(request, BridgeRequest):
            raise ExposureSchemaError("BridgeRequest required")
        validate_tree(request)
        existing = self.get(request.request_id)
        if existing is not None:
            if existing != request:
                raise AppendOnlyViolationError("same request ID with different content")
            return existing
        self._store.record(request)
        return request


class CompanyExposureStore:
    """No concurrent writers; same-ID same-content retries are idempotent."""

    def __init__(self, path: Path, *, input_store: CompanyExposureInputStore) -> None:
        self._inputs = input_store

        def encode(record: BridgeResult) -> dict[str, object]:
            return cast(dict[str, object], to_hashable(record))

        def decode(data: dict[str, object]) -> BridgeResult:
            result = cast(BridgeResult, _decode(data, BridgeResult))
            validate_tree(result)
            self._verify_replay(result)
            return result

        self._store: AppendOnlyRecordStore[BridgeResult] = AppendOnlyRecordStore(
            path,
            id_of=lambda r: r.result_id,
            to_dict=encode,
            from_dict=decode,
        )

    def all(self) -> list[BridgeResult]:
        records = self._store.all()
        if len({r.result_id for r in records}) != len(records):
            raise ExposureSchemaError("duplicate result IDs in stored output")
        return records

    def get(self, result_id: str) -> BridgeResult | None:
        return next((r for r in self.all() if r.result_id == result_id), None)

    def record(self, result: BridgeResult) -> BridgeResult:
        if not isinstance(result, BridgeResult):
            raise ExposureSchemaError("BridgeResult required")
        validate_tree(result)
        self._verify_replay(result)
        existing = self.get(result.result_id)
        if existing is not None:
            if existing != result:
                raise AppendOnlyViolationError("same ID with different content")
            return existing
        parent_id = result.supersedes_result_id
        seen = {result.result_id}
        while parent_id is not None:
            if parent_id in seen:
                raise AppendOnlyViolationError("cyclic correction")
            seen.add(parent_id)
            parent = self.get(parent_id)
            if parent is None:
                raise AppendOnlyViolationError("correction parent must exist")
            if (parent.entity_id, parent.forecast_period, parent.scenario) != (
                result.entity_id,
                result.forecast_period,
                result.scenario,
            ):
                raise AppendOnlyViolationError("correction economic identity mismatch")
            if parent.created_at > result.created_at:
                raise AppendOnlyViolationError("correction predates parent")
            parent_id = parent.supersedes_result_id
        self._store.record(result)
        return result

    def _verify_replay(self, result: BridgeResult) -> None:
        request = self._inputs.get(result.result_id)
        if request is None or request.record_hash != result.request_hash:
            raise ExposureSchemaError("result requires its stored exact input snapshot")
        if compute_exposure_bridge(request) != result:
            raise ExposureSchemaError("result does not reproduce from stored input snapshot")
