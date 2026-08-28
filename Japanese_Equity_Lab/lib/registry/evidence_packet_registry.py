"""Evidence Packet Registry: `EvidencePacket`を追記専用(append-only)で
永続化し、Fresh Processからexact relation assignments(`NEUTRAL`/`UNKNOWN`/
Omitted等)まで含めて再解決できるようにする(Stage 3.15.2、D0091)。

既存`EvidenceRegistry`/`ProvenanceStore`/`ResearchArtifactRegistry`と
同じAppend-only JSON Linesパターンをそのまま踏襲する(新しいPersistence
Frameworkは作らない)。`packet_id`の重複登録は`AppendOnlyViolationError`
にする(既存3 Registryと同じく、Payloadが同一かどうかに関わらず無条件で
Reject——Upsert Semanticsは作らない)。

`ResearchArtifact.evidence_packet_id`は既にPacketへの参照IDを持つ
(Schema変更不要)。呼び出し側が`build_research_artifact()`の戻り値
`(artifact, packet)`のうち`packet`をこのRegistryへ`record()`することで、
Fresh Processから`artifact.evidence_packet_id`→このRegistry→Packetの
`relation_assignments`という経路でExact Relationを再解決できるようになる。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from lib.errors import AppendOnlyViolationError
from lib.evidence.model import EvidenceRelation
from lib.evidence.packet import EvidencePacket, EvidenceRelationAssignment


def _packet_to_dict(packet: EvidencePacket) -> dict[str, Any]:
    return {
        "packet_id": packet.packet_id,
        "research_question": packet.research_question,
        "as_of": packet.as_of.isoformat(),
        "included_evidence_ids": list(packet.included_evidence_ids),
        "excluded_candidate_sources": list(packet.excluded_candidate_sources),
        "retrieval_reason": packet.retrieval_reason,
        "missing_expected_sources": list(packet.missing_expected_sources),
        "positive_evidence": list(packet.positive_evidence),
        "negative_evidence": list(packet.negative_evidence),
        "alternative_explanation_evidence": list(packet.alternative_explanation_evidence),
        "contradictory_evidence": list(packet.contradictory_evidence),
        "unknowns": list(packet.unknowns),
        "provenance_id": packet.provenance_id,
        "relation_assignments": [
            {"evidence_id": a.evidence_id, "relation": a.relation.value} for a in packet.relation_assignments
        ],
    }


def _packet_from_dict(data: dict[str, Any]) -> EvidencePacket:
    d: dict[str, Any] = dict(data)
    return EvidencePacket(
        packet_id=d["packet_id"],
        research_question=d["research_question"],
        as_of=datetime.fromisoformat(d["as_of"]),
        included_evidence_ids=tuple(d.get("included_evidence_ids") or ()),
        excluded_candidate_sources=tuple(d.get("excluded_candidate_sources") or ()),
        retrieval_reason=d.get("retrieval_reason", ""),
        missing_expected_sources=tuple(d.get("missing_expected_sources") or ()),
        positive_evidence=tuple(d.get("positive_evidence") or ()),
        negative_evidence=tuple(d.get("negative_evidence") or ()),
        alternative_explanation_evidence=tuple(d.get("alternative_explanation_evidence") or ()),
        contradictory_evidence=tuple(d.get("contradictory_evidence") or ()),
        unknowns=tuple(d.get("unknowns") or ()),
        provenance_id=d.get("provenance_id"),
        relation_assignments=tuple(
            EvidenceRelationAssignment(evidence_id=a["evidence_id"], relation=EvidenceRelation(a["relation"]))
            for a in (d.get("relation_assignments") or ())
        ),
    )


class EvidencePacketRegistry:
    """JSON Lines形式で追記専用に記録するEvidence Packet Registry。"""

    def __init__(self, storage_path: Path) -> None:
        self._storage_path = storage_path
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, packet: EvidencePacket) -> None:
        existing_ids = {p.packet_id for p in self.all()}
        if packet.packet_id in existing_ids:
            raise AppendOnlyViolationError(f"packet_id={packet.packet_id} は既に記録されています(上書き不可)")
        line = json.dumps(_packet_to_dict(packet), ensure_ascii=False)
        with self._storage_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def all(self) -> list[EvidencePacket]:
        if not self._storage_path.exists():
            return []
        packets = []
        with self._storage_path.open(encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if line:
                    packets.append(_packet_from_dict(json.loads(line)))
        return packets

    def get(self, packet_id: str) -> EvidencePacket | None:
        for packet in self.all():
            if packet.packet_id == packet_id:
                return packet
        return None

    def require(self, packet_id: str) -> EvidencePacket:
        """`get()`同様だが、存在しない場合は`None`を返さずfail closedで`KeyError`を送出する。"""
        packet = self.get(packet_id)
        if packet is None:
            raise KeyError(f"packet_id={packet_id} はEvidencePacketRegistryに存在しません")
        return packet


__all__ = ["EvidencePacketRegistry"]
