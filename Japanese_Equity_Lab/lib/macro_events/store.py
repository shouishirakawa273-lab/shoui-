"""Macro Event & Surprise: Append-Only Persistence(D0110.1)。

既存`lib.evaluation.store.AppendOnlyRecordStore`(D0107、Generic)を
そのまま再利用する——新しいPersistence機構は作らない(D0110.1 §34
「reuse existing append-only patterns. No general database」)。
D0110.1の4Record型それぞれに専用Classを作らず、`to_dict`/`from_dict`
の変換Functionのみを型ごとに注入する。

**重複ID Policy(D0107以降の既存Policyを継続)**: 既存Registry群と
同じPolicy(Content同一か否かを問わず、同一IDのRecordを無条件で
Rejectする)をそのまま踏襲する——Silent Dedupe/Overwriteは行わない
(D0110.1 §29 Test C「duplicate same ID + different content fails
closed」)。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path

from lib.evaluation.store import AppendOnlyRecordStore
from lib.macro_events.model import MacroConsensusSnapshot, MacroEvent, MacroFirstRelease
from lib.macro_events.surprise import MacroSurprise


def _opt_str(value: object) -> str | None:
    return str(value) if value is not None else None


def _opt_int(value: object) -> int | None:
    return int(value) if value is not None else None  # type: ignore[call-overload]


def _opt_decimal(value: object) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None


# ============================================================
# MacroEvent
# ============================================================


def _macro_event_to_dict(event: MacroEvent) -> dict[str, object]:
    return {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "jurisdiction": event.jurisdiction,
        "scheduled_at": event.scheduled_at.isoformat(),
        "event_period": event.event_period,
        "source_id": event.source_id,
        "schedule_available_at": event.schedule_available_at.isoformat(),
        "event_version": event.event_version,
        "created_at": event.created_at.isoformat(),
        "record_hash": event.record_hash,
    }


def _macro_event_from_dict(data: dict[str, object]) -> MacroEvent:
    return MacroEvent(
        event_id=str(data["event_id"]),
        event_type=str(data["event_type"]),
        jurisdiction=str(data["jurisdiction"]),
        scheduled_at=datetime.fromisoformat(str(data["scheduled_at"])),
        event_period=str(data["event_period"]),
        source_id=str(data["source_id"]),
        schedule_available_at=datetime.fromisoformat(str(data["schedule_available_at"])),
        event_version=int(data["event_version"]),  # type: ignore[call-overload]
        created_at=datetime.fromisoformat(str(data["created_at"])),
        record_hash=str(data["record_hash"]),
    )


def _macro_event_composite_id(event: MacroEvent) -> str:
    """`event_id`単独ではなく`(event_id, event_version)`をIdentityと
    する。`MacroEvent.event_version`は予定の改訂(延期等)を新しい
    Immutable Snapshotとして表現する設計(`lib.macro_events.model`
    Docstring参照)であり、`event_id`単独Keyでは同一IDの新Versionを
    追記するたびAppendOnlyViolationErrorになってしまい、この設計
    そのものと矛盾する(D0107 EvaluationContractの`_evaluation_
    contract_composite_id()`と同じ理由・同じ解法、/code-review high
    Finding)。"""
    return f"{event.event_id}::v{event.event_version}"


def new_macro_event_store(storage_path: Path) -> AppendOnlyRecordStore[MacroEvent]:
    return AppendOnlyRecordStore(
        storage_path, id_of=_macro_event_composite_id, to_dict=_macro_event_to_dict, from_dict=_macro_event_from_dict
    )


# ============================================================
# MacroConsensusSnapshot
# ============================================================


def _macro_consensus_snapshot_to_dict(snapshot: MacroConsensusSnapshot) -> dict[str, object]:
    return {
        "consensus_snapshot_id": snapshot.consensus_snapshot_id,
        "event_id": snapshot.event_id,
        "dimension": snapshot.dimension,
        "value": str(snapshot.value),
        "unit": snapshot.unit,
        "consensus_snapshot_at": snapshot.consensus_snapshot_at.isoformat(),
        "available_at": snapshot.available_at.isoformat(),
        "provider": snapshot.provider,
        "source_id": snapshot.source_id,
        "provider_version": snapshot.provider_version,
        "estimate_count": snapshot.estimate_count,
        "dispersion": _opt_str(snapshot.dispersion),
        "created_at": snapshot.created_at.isoformat(),
        "record_hash": snapshot.record_hash,
    }


def _macro_consensus_snapshot_from_dict(data: dict[str, object]) -> MacroConsensusSnapshot:
    return MacroConsensusSnapshot(
        consensus_snapshot_id=str(data["consensus_snapshot_id"]),
        event_id=str(data["event_id"]),
        dimension=str(data["dimension"]),
        value=Decimal(str(data["value"])),
        unit=str(data["unit"]),
        consensus_snapshot_at=datetime.fromisoformat(str(data["consensus_snapshot_at"])),
        available_at=datetime.fromisoformat(str(data["available_at"])),
        provider=str(data["provider"]),
        source_id=str(data["source_id"]),
        provider_version=_opt_str(data["provider_version"]),
        estimate_count=_opt_int(data["estimate_count"]),
        dispersion=_opt_decimal(data["dispersion"]),
        created_at=datetime.fromisoformat(str(data["created_at"])),
        record_hash=str(data["record_hash"]),
    )


def new_macro_consensus_snapshot_store(storage_path: Path) -> AppendOnlyRecordStore[MacroConsensusSnapshot]:
    return AppendOnlyRecordStore(
        storage_path,
        id_of=lambda r: r.consensus_snapshot_id,
        to_dict=_macro_consensus_snapshot_to_dict,
        from_dict=_macro_consensus_snapshot_from_dict,
    )


# ============================================================
# MacroFirstRelease
# ============================================================


def _macro_first_release_to_dict(release: MacroFirstRelease) -> dict[str, object]:
    return {
        "release_id": release.release_id,
        "event_id": release.event_id,
        "dimension": release.dimension,
        "actual_first_release": str(release.actual_first_release),
        "previous_as_published": _opt_str(release.previous_as_published),
        "unit": release.unit,
        "actual_public_at": release.actual_public_at.isoformat(),
        "available_at": release.available_at.isoformat(),
        "source_id": release.source_id,
        "source_version": release.source_version,
        "created_at": release.created_at.isoformat(),
        "record_hash": release.record_hash,
    }


def _macro_first_release_from_dict(data: dict[str, object]) -> MacroFirstRelease:
    return MacroFirstRelease(
        release_id=str(data["release_id"]),
        event_id=str(data["event_id"]),
        dimension=str(data["dimension"]),
        actual_first_release=Decimal(str(data["actual_first_release"])),
        previous_as_published=_opt_decimal(data["previous_as_published"]),
        unit=str(data["unit"]),
        actual_public_at=datetime.fromisoformat(str(data["actual_public_at"])),
        available_at=datetime.fromisoformat(str(data["available_at"])),
        source_id=str(data["source_id"]),
        source_version=_opt_str(data["source_version"]),
        created_at=datetime.fromisoformat(str(data["created_at"])),
        record_hash=str(data["record_hash"]),
    )


def new_macro_first_release_store(storage_path: Path) -> AppendOnlyRecordStore[MacroFirstRelease]:
    return AppendOnlyRecordStore(
        storage_path,
        id_of=lambda r: r.release_id,
        to_dict=_macro_first_release_to_dict,
        from_dict=_macro_first_release_from_dict,
    )


# ============================================================
# MacroSurprise
# ============================================================


def _macro_surprise_to_dict(surprise: MacroSurprise) -> dict[str, object]:
    return {
        "surprise_id": surprise.surprise_id,
        "event_id": surprise.event_id,
        "dimension": surprise.dimension,
        "consensus_snapshot_id": surprise.consensus_snapshot_id,
        "first_release_id": surprise.first_release_id,
        "expected_value": str(surprise.expected_value),
        "actual_value": str(surprise.actual_value),
        "surprise_value": str(surprise.surprise_value),
        "surprise_unit": surprise.surprise_unit,
        "calculation_rule_id": surprise.calculation_rule_id,
        "calculated_at": surprise.calculated_at.isoformat(),
        "available_at": surprise.available_at.isoformat(),
        "record_hash": surprise.record_hash,
    }


def _macro_surprise_from_dict(data: dict[str, object]) -> MacroSurprise:
    return MacroSurprise(
        surprise_id=str(data["surprise_id"]),
        event_id=str(data["event_id"]),
        dimension=str(data["dimension"]),
        consensus_snapshot_id=str(data["consensus_snapshot_id"]),
        first_release_id=str(data["first_release_id"]),
        expected_value=Decimal(str(data["expected_value"])),
        actual_value=Decimal(str(data["actual_value"])),
        surprise_value=Decimal(str(data["surprise_value"])),
        surprise_unit=str(data["surprise_unit"]),
        calculation_rule_id=str(data["calculation_rule_id"]),
        calculated_at=datetime.fromisoformat(str(data["calculated_at"])),
        available_at=datetime.fromisoformat(str(data["available_at"])),
        record_hash=str(data["record_hash"]),
    )


def new_macro_surprise_store(storage_path: Path) -> AppendOnlyRecordStore[MacroSurprise]:
    return AppendOnlyRecordStore(
        storage_path, id_of=lambda r: r.surprise_id, to_dict=_macro_surprise_to_dict, from_dict=_macro_surprise_from_dict
    )


__all__ = [
    "new_macro_consensus_snapshot_store",
    "new_macro_event_store",
    "new_macro_first_release_store",
    "new_macro_surprise_store",
]
