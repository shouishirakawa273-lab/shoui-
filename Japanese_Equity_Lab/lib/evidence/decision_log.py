"""Decision Evidence Log: 将来のAI判断について、使ったEvidence/使わなかったEvidence/
主な根拠/矛盾/未解決点を保存できるSchema(D0040)。

Prediction -> Actual Result -> Which Evidence Helped? -> Which Evidence Misled? ->
Missing Evidence? -> Knowledge Updateという検証を将来行うための土台。

**ここではまだBUY/SELL Agentを実装しない。** `predicted_outcome`/`actual_outcome`は
将来の検証用に空のまま保存できるフィールドとして用意するのみで、このモジュール自体は
何かを予測・判断する機能を一切持たない。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(kw_only=True, frozen=True)
class DecisionEvidenceLog:
    log_id: str
    decision_at: datetime
    evidence_packet_id: str
    used_evidence_ids: tuple[str, ...] = field(default_factory=tuple)
    not_used_or_unavailable_evidence_ids: tuple[str, ...] = field(default_factory=tuple)
    main_drivers: tuple[str, ...] = field(default_factory=tuple)
    contradictions: tuple[str, ...] = field(default_factory=tuple)
    unknowns: tuple[str, ...] = field(default_factory=tuple)
    predicted_outcome: str | None = None
    actual_outcome: str | None = None
    provenance_id: str | None = None

    def __post_init__(self) -> None:
        if self.decision_at.tzinfo is None:
            raise ValueError("decision_at はtz-awareである必要があります")
        overlap = set(self.used_evidence_ids) & set(self.not_used_or_unavailable_evidence_ids)
        if overlap:
            raise ValueError(f"used_evidence_idsとnot_used_or_unavailable_evidence_idsが重複しています: {overlap}")
