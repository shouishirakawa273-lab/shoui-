"""Input snapshots and reconstructed outcomes over D0107, single writer only."""

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

from .calculation import compute_profit_impact, validate_tree
from .model import ImpactSchemaError, ProfitImpactRequest, ProfitImpactResult, SourceDisclosureRecord


def _decode(value: object, annotation: Any) -> Any:
    origin, args = get_origin(annotation), get_args(annotation)
    if origin is types.UnionType:
        if value is None and type(None) in args:
            return None
        return _decode(value, next(a for a in args if a is not type(None)))
    if origin is tuple:
        if not isinstance(value, list):
            raise ImpactSchemaError("stored tuple requires array")
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(_decode(v, args[0]) for v in value)
        if len(args) != len(value):
            raise ImpactSchemaError("stored tuple shape mismatch")
        return tuple(_decode(v, a) for v, a in zip(value, args, strict=True))
    if annotation in (date, datetime, Decimal):
        if not isinstance(value, str):
            raise ImpactSchemaError("stored date/time/decimal requires string")
        if annotation is datetime:
            return datetime.fromisoformat(value)
        return date.fromisoformat(value) if annotation is date else Decimal(value)
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return annotation(value)
    if isinstance(annotation, type) and is_dataclass(annotation):
        if not isinstance(value, dict) or set(value) != {f.name for f in fields(annotation)}:
            raise ImpactSchemaError("stored record fields mismatch")
        if "record_hash" in value and compute_record_hash(value) != value["record_hash"]:
            raise ImpactSchemaError("raw stored integrity failure")
        hints = get_type_hints(annotation)
        return annotation(**{name: _decode(value[name], a) for name, a in hints.items()})
    if annotation in (str, int, bool) and type(value) is annotation:
        return value
    raise ImpactSchemaError("stored scalar type mismatch")


class ProfitImpactInputStore:
    def __init__(self, path: Path) -> None:
        def decode(data: dict[str, object]) -> ProfitImpactRequest:
            request = cast(ProfitImpactRequest, _decode(data, ProfitImpactRequest))
            validate_tree(request)
            return request

        self._store: AppendOnlyRecordStore[ProfitImpactRequest] = AppendOnlyRecordStore(
            path,
            id_of=lambda r: r.request_id,
            to_dict=lambda r: cast(dict[str, object], to_hashable(r)),
            from_dict=decode,
        )

    def get(self, request_id: str) -> ProfitImpactRequest | None:
        records = self._store.all()
        self._verify_components(records)
        if len({r.request_id for r in records}) != len(records):
            raise ImpactSchemaError("ambiguous stored request IDs")
        return next((r for r in records if r.request_id == request_id), None)

    def record(self, request: ProfitImpactRequest) -> ProfitImpactRequest:
        if not isinstance(request, ProfitImpactRequest):
            raise ImpactSchemaError("ProfitImpactRequest required")
        validate_tree(request)
        existing = self.get(request.request_id)
        if existing is not None:
            if existing != request:
                raise AppendOnlyViolationError("same ID with different request content")
            return existing
        self._verify_components([*self._store.all(), request])
        self._store.record(request)
        return request

    @staticmethod
    def _verify_components(records: list[ProfitImpactRequest]) -> None:
        """A source/artifact/sensitivity ID cannot acquire new content in another snapshot."""
        seen: dict[tuple[str, str], str] = {}
        sources: dict[str, SourceDisclosureRecord] = {}
        for request in records:
            for collection, id_field in (
                ("artifacts", "artifact_id"),
                ("disclosures", "disclosure_id"),
                ("sensitivities", "sensitivity_id"),
            ):
                for component in getattr(request, collection):
                    key = (collection, str(getattr(component, id_field)))
                    if key in seen and seen[key] != component.record_hash:
                        raise AppendOnlyViolationError("component ID changed across immutable snapshots")
                    seen[key] = component.record_hash
            sources.update({s.disclosure_id: s for s in request.disclosures})
        for source in sources.values():
            parent_id = source.supersedes_disclosure_id
            chain = {source.disclosure_id}
            while parent_id is not None:
                if parent_id in chain:
                    raise AppendOnlyViolationError("cyclic disclosure correction")
                chain.add(parent_id)
                parent = sources.get(parent_id)
                if parent is None or (
                    parent.entity_id,
                    parent.forecast_period,
                    parent.driver,
                    parent.profit_metric,
                ) != (source.entity_id, source.forecast_period, source.driver, source.profit_metric):
                    raise AppendOnlyViolationError("disclosure correction requires matching archived parent")
                if parent.scope not in ("UNKNOWN", "UNKNOWN_NOT_VERIFIED_BY_THIS_FIXTURE") and parent.scope != source.scope:
                    raise AppendOnlyViolationError("disclosure correction cannot change a known economic scope")
                if (
                    parent.normalized_created_at is not None
                    and source.normalized_created_at is not None
                    and (parent.normalized_created_at > source.normalized_created_at)
                ):
                    raise AppendOnlyViolationError("disclosure correction precedes parent normalization")
                parent_id = parent.supersedes_disclosure_id


class ProfitImpactStore:
    def __init__(self, path: Path, *, input_store: ProfitImpactInputStore) -> None:
        self._inputs = input_store

        def decode(data: dict[str, object]) -> ProfitImpactResult:
            result = cast(ProfitImpactResult, _decode(data, ProfitImpactResult))
            validate_tree(result)
            self._verify_replay(result)
            return result

        self._store: AppendOnlyRecordStore[ProfitImpactResult] = AppendOnlyRecordStore(
            path,
            id_of=lambda r: r.result_id,
            to_dict=lambda r: cast(dict[str, object], to_hashable(r)),
            from_dict=decode,
        )

    def _verify_replay(self, result: ProfitImpactResult) -> None:
        request = self._inputs.get(result.result_id)
        if request is None or request.record_hash != result.request_hash or compute_profit_impact(request) != result:
            raise ImpactSchemaError("result requires stored exact request and reproducible outcome")

    def all(self) -> list[ProfitImpactResult]:
        results = self._store.all()
        if len({r.result_id for r in results}) != len(results):
            raise ImpactSchemaError("ambiguous stored result IDs")
        return results

    def get(self, result_id: str) -> ProfitImpactResult | None:
        return next((r for r in self.all() if r.result_id == result_id), None)

    def record(self, result: ProfitImpactResult) -> ProfitImpactResult:
        if not isinstance(result, ProfitImpactResult):
            raise ImpactSchemaError("ProfitImpactResult required")
        validate_tree(result)
        self._verify_replay(result)
        existing = self.get(result.result_id)
        if existing is not None:
            if existing != result:
                raise AppendOnlyViolationError("same ID with different result content")
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
            if (parent.entity_id, parent.forecast_period, parent.forecast_version, parent.scenario) != (
                result.entity_id,
                result.forecast_period,
                result.forecast_version,
                result.scenario,
            ) or parent.created_at > result.created_at:
                raise AppendOnlyViolationError("correction identity/time mismatch")
            parent_id = parent.supersedes_result_id
        self._store.record(result)
        return result
