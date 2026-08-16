"""Provenance / Data Lineage。

YouTube URL -> Comment -> Idea -> Hypothesis -> Backtest -> Paper Test -> Knowledge
のような参照チェーンを追記専用(append-only)で記録し、起点まで遡って追跡可能にする。
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from lib.errors import AppendOnlyViolationError


@dataclass(frozen=True)
class ProvenanceLink:
    link_id: str
    from_type: str
    from_id: str
    to_type: str
    to_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class ProvenanceStore:
    """追記専用のリンクストア(JSON Lines)。1エンティティにつき直接の親1系統を遡る。

    複数の親を持つ知見(例: 複数のExperimentから導かれたKnowledge)を網羅的に調べる場合は
    all() で全リンクを確認すること。
    """

    def __init__(self, storage_path: Path) -> None:
        self._storage_path = storage_path
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)

    def add_link(self, link: ProvenanceLink) -> None:
        existing_ids = {existing.link_id for existing in self.all()}
        if link.link_id in existing_ids:
            raise AppendOnlyViolationError(f"link_id={link.link_id} は既に記録されています(上書き不可)")
        payload = asdict(link)
        payload["created_at"] = link.created_at.isoformat()
        with self._storage_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def all(self) -> list[ProvenanceLink]:
        if not self._storage_path.exists():
            return []
        links = []
        with self._storage_path.open(encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line:
                    continue
                data = json.loads(line)
                data["created_at"] = datetime.fromisoformat(data["created_at"])
                links.append(ProvenanceLink(**data))
        return links

    def trace_to_origin(self, entity_type: str, entity_id: str) -> list[ProvenanceLink]:
        """entity_idを終点(to_id)とするリンクを起点まで遡ってchainを返す(先頭が起源)。"""
        links_by_target = {(link.to_type, link.to_id): link for link in self.all()}
        chain: list[ProvenanceLink] = []
        current: tuple[str, str] | None = (entity_type, entity_id)
        visited: set[tuple[str, str]] = set()
        while current is not None and current in links_by_target:
            if current in visited:
                raise ValueError(f"Provenanceチェーンに循環参照が検出されました: {current}")
            visited.add(current)
            link = links_by_target[current]
            chain.append(link)
            current = (link.from_type, link.from_id)
        chain.reverse()
        return chain
