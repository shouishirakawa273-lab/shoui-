"""Evidence Registry: `EvidenceRecord`を追記専用(append-only)で永続化し、
Fresh Processからevidence_id経由でLosslessに再解決できるようにする
(Stage 3.15.1、D0090)。

既存`ProvenanceStore`/`ResearchArtifactRegistry`と同じAppend-only JSON
Linesパターンをそのまま踏襲する(新しいPersistence Frameworkは作らない)。
`evidence_id`の重複登録は`AppendOnlyViolationError`にする(既存2Registryと
同じく、Payloadが同一かどうかに関わらず無条件でReject——Upsert Semanticsは
作らない)。

Stage 3.15(D0089)のHistorical Valuation Context実装は、Historical/Current
PER Observationを「Evidence ID文字列」としてのみ参照し、実際の
`EvidenceRecord`をどこにも永続化していなかった(Codex-style Post-
Implementation Reviewで指摘された欠落)。このRegistryは、その欠落
——「参照されるNodeが実在し、Fresh Processから解決可能であること」——を
埋めるための最小基盤である。
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

from lib.errors import AppendOnlyViolationError
from lib.evidence.model import AiDerivedProvenance, DataLayer, EvidenceRecord, EvidenceType
from lib.sources.catalog import DataCapability, PrimaryOrSecondary, SourceAuthorityClass, SourceMetadata


def _source_metadata_to_dict(source: SourceMetadata) -> dict[str, Any]:
    payload = asdict(source)
    payload["source_authority_class"] = source.source_authority_class.value
    payload["primary_or_secondary"] = source.primary_or_secondary.value
    payload["retrieved_at"] = source.retrieved_at.isoformat()
    payload["published_at"] = source.published_at.isoformat() if source.published_at is not None else None
    payload["available_at"] = source.available_at.isoformat()
    payload["effective_at"] = source.effective_at.isoformat() if source.effective_at is not None else None
    return payload


def _source_metadata_from_dict(data: dict[str, Any]) -> SourceMetadata:
    d: dict[str, Any] = dict(data)
    d["source_authority_class"] = SourceAuthorityClass(d["source_authority_class"])
    d["primary_or_secondary"] = PrimaryOrSecondary(d["primary_or_secondary"])
    d["retrieved_at"] = datetime.fromisoformat(d["retrieved_at"])
    d["published_at"] = datetime.fromisoformat(d["published_at"]) if d.get("published_at") is not None else None
    d["available_at"] = datetime.fromisoformat(d["available_at"])
    d["effective_at"] = date.fromisoformat(d["effective_at"]) if d.get("effective_at") is not None else None
    return SourceMetadata(**d)


def _ai_derived_provenance_to_dict(prov: AiDerivedProvenance) -> dict[str, Any]:
    payload = asdict(prov)
    payload["generated_at"] = prov.generated_at.isoformat()
    payload["input_evidence_ids"] = list(prov.input_evidence_ids)
    return payload


def _ai_derived_provenance_from_dict(data: dict[str, Any]) -> AiDerivedProvenance:
    d: dict[str, Any] = dict(data)
    d["generated_at"] = datetime.fromisoformat(d["generated_at"])
    d["input_evidence_ids"] = tuple(d.get("input_evidence_ids") or ())
    return AiDerivedProvenance(**d)


def _evidence_to_dict(record: EvidenceRecord) -> dict[str, Any]:
    return {
        "evidence_id": record.evidence_id,
        "evidence_type": record.evidence_type.value,
        "layer": record.layer.value,
        "capability": record.capability.value,
        "content": record.content,
        "source": _source_metadata_to_dict(record.source),
        "value_date": record.value_date.isoformat() if record.value_date is not None else None,
        "related_codes": list(record.related_codes),
        "related_sectors": list(record.related_sectors),
        "ai_derived_provenance": (
            _ai_derived_provenance_to_dict(record.ai_derived_provenance) if record.ai_derived_provenance is not None else None
        ),
        "provenance_id": record.provenance_id,
    }


def _evidence_from_dict(data: dict[str, Any]) -> EvidenceRecord:
    ai_prov_data = data.get("ai_derived_provenance")
    return EvidenceRecord(
        evidence_id=data["evidence_id"],
        evidence_type=EvidenceType(data["evidence_type"]),
        layer=DataLayer(data["layer"]),
        capability=DataCapability(data["capability"]),
        content=data["content"],
        source=_source_metadata_from_dict(data["source"]),
        value_date=date.fromisoformat(data["value_date"]) if data.get("value_date") is not None else None,
        related_codes=tuple(data.get("related_codes") or ()),
        related_sectors=tuple(data.get("related_sectors") or ()),
        ai_derived_provenance=(_ai_derived_provenance_from_dict(ai_prov_data) if ai_prov_data is not None else None),
        provenance_id=data.get("provenance_id"),
    )


class EvidenceRegistry:
    """JSON Lines形式で追記専用に記録するEvidence Registry(Genericな
    `EvidenceRecord`用、DB/Frameworkは持たない最小実装)。"""

    def __init__(self, storage_path: Path) -> None:
        self._storage_path = storage_path
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)

    def register(self, record: EvidenceRecord) -> None:
        existing_ids = {r.evidence_id for r in self.all()}
        if record.evidence_id in existing_ids:
            raise AppendOnlyViolationError(f"evidence_id={record.evidence_id} は既に登録されています(上書き不可)")
        line = json.dumps(_evidence_to_dict(record), ensure_ascii=False)
        with self._storage_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def all(self) -> list[EvidenceRecord]:
        if not self._storage_path.exists():
            return []
        records = []
        with self._storage_path.open(encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if line:
                    records.append(_evidence_from_dict(json.loads(line)))
        return records

    def get(self, evidence_id: str) -> EvidenceRecord | None:
        for record in self.all():
            if record.evidence_id == evidence_id:
                return record
        return None

    def require(self, evidence_id: str) -> EvidenceRecord:
        """`get()`同様だが、存在しない場合は`None`を返さずfail closedで`KeyError`を送出する
        (Parent Existence検証等、値が無いことを許容しない呼び出し元向け)。"""
        record = self.get(evidence_id)
        if record is None:
            raise KeyError(f"evidence_id={evidence_id} はEvidenceRegistryに存在しません")
        return record


__all__ = ["EvidenceRegistry"]
