"""Strict external JSON boundary around the existing five record codecs."""

from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path
from types import UnionType
from typing import Any, get_args, get_origin, get_type_hints

from lib.evaluation.integrity import verify_record_integrity
from lib.evaluation.model import PredictionRecord, ResearchSnapshot
from lib.evaluation.store import _prediction_from_dict, _research_snapshot_from_dict
from lib.macro_events.model import MacroConsensusSnapshot, MacroEvent, MacroFirstRelease
from lib.macro_events.store import (
    _macro_consensus_snapshot_from_dict,
    _macro_event_from_dict,
    _macro_first_release_from_dict,
)
from lib.macro_experiments.comparison import MacroComparisonSample
from lib.macro_experiments.store import strict_object, timestamp, unique_object


def _validate(value: Any, annotation: Any) -> None:
    """Validate wire types before legacy codecs can coerce any values.

    Strings remain lossless, including optional empty/whitespace strings. Decimal
    values use strings, timestamps use aware ISO strings, tuples use JSON arrays.
    Economic identity and temporal ordering remain the comparison API's job.
    """
    if get_origin(annotation) is UnionType:
        for member in get_args(annotation):
            try:
                _validate(value, member)
                return
            except ValueError:
                pass
        raise ValueError("value does not match declared optional type")
    if annotation is type(None):
        if value is not None:
            raise ValueError("expected null")
    elif annotation in (str, int, bool):
        if type(value) is not annotation:
            raise ValueError(f"expected {annotation.__name__}")
    elif annotation is datetime:
        timestamp(value)
    elif annotation is Decimal:
        if type(value) is not str:
            raise ValueError("decimal must be a string")
        try:
            finite = Decimal(value).is_finite()
        except InvalidOperation as exc:
            raise ValueError("invalid decimal string") from exc
        if not finite:
            raise ValueError("finite decimal required")
    elif get_origin(annotation) is tuple:
        if type(value) is not list:
            raise ValueError("expected JSON array")
        for item in value:
            _validate(item, get_args(annotation)[0])
    elif isinstance(annotation, type) and issubclass(annotation, Enum):
        if type(value) is not str:
            raise ValueError("enum must be a string")
        annotation(value)
    elif isinstance(annotation, type) and is_dataclass(annotation):
        raw = strict_object(value, {f.name for f in fields(annotation)})
        for name, declared in get_type_hints(annotation).items():
            _validate(raw[name], declared)
    else:
        raise ValueError("unsupported record field type")


def samples_from_dict(data: Any) -> tuple[MacroComparisonSample, ...]:
    raw = strict_object(data, {"schema_version", "samples"})
    if type(raw["schema_version"]) is not int or raw["schema_version"] != 1:
        raise ValueError("schema_version must be integer 1")
    if type(raw["samples"]) is not list:
        raise ValueError("samples must be array")
    codecs = {
        "event": (MacroEvent, _macro_event_from_dict),
        "consensus": (MacroConsensusSnapshot, _macro_consensus_snapshot_from_dict),
        "release": (MacroFirstRelease, _macro_first_release_from_dict),
        "prediction": (PredictionRecord, _prediction_from_dict),
        "snapshot": (ResearchSnapshot, _research_snapshot_from_dict),
    }
    samples = []
    for sample in raw["samples"]:
        item = strict_object(sample, {*codecs, "synthetic"})
        _validate(item["synthetic"], bool)
        records: dict[str, Any] = {}
        for name, (cls, decode) in codecs.items():
            value = item[name]
            if value is None and name != "event":
                records[name] = None
                continue
            _validate(value, cls)
            record = decode(value)
            if not verify_record_integrity(record):
                raise ValueError(f"{name} integrity failure")
            records[name] = record
        samples.append(MacroComparisonSample(**records, synthetic=item["synthetic"]))
    return tuple(samples)


def read_samples(path: Path) -> tuple[MacroComparisonSample, ...]:
    with path.open(encoding="utf-8") as stream:
        return samples_from_dict(json.load(stream, object_pairs_hook=unique_object))
