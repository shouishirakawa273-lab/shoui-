"""Research Artifact Registry: 追記専用(append-only)でResearchArtifactを記録する
(Stage 3 v1、要件v1-9)。

既存の`ExperimentRegistry`/`PreregistrationRegistry`/`ProvenanceStore`と
同じAppend-only JSON Linesパターンをそのまま踏襲する(新しいPersistence
機構は作らない)。`artifact_id`の重複は`AppendOnlyViolationError`にする。
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from lib.errors import AppendOnlyViolationError
from lib.evidence.research_artifact import (
    ConfidenceLevel,
    DataGap,
    DataGapStatus,
    NarrativeCase,
    ResearchArtifact,
    ResearchConclusion,
)

# JSON Lines <-> dataclass の変換は実行時にしか型を検証できない(JSONにはenum/datetime
# が無いため)。ここだけ dict[str, Any] を使い、以降のコードはdataclass経由で型付きに戻す
# (`lib/registry/experiment_registry.py`と同じ方針)。


def _artifact_to_dict(artifact: ResearchArtifact) -> dict[str, Any]:
    payload = asdict(artifact)
    payload["as_of"] = artifact.as_of.isoformat()
    payload["created_at"] = artifact.created_at.isoformat()
    payload["updated_at"] = artifact.updated_at.isoformat()
    payload["data_confidence"] = artifact.data_confidence.value
    payload["evidence_confidence"] = artifact.evidence_confidence.value
    payload["research_confidence"] = artifact.research_confidence.value
    payload["conclusion"] = artifact.conclusion.value
    return payload


def _narrative_case_from_dict(data: dict[str, Any]) -> NarrativeCase:
    return NarrativeCase(summary=data["summary"], supporting_evidence_ids=tuple(data.get("supporting_evidence_ids") or ()))


def _data_gap_from_dict(data: dict[str, Any]) -> DataGap:
    return DataGap(topic=data["topic"], status=DataGapStatus(data["status"]), note=data.get("note", ""))


def _artifact_from_dict(data: dict[str, Any]) -> ResearchArtifact:
    d: dict[str, Any] = dict(data)
    d["as_of"] = datetime.fromisoformat(d["as_of"])
    d["created_at"] = datetime.fromisoformat(d["created_at"])
    d["updated_at"] = datetime.fromisoformat(d["updated_at"])
    d["data_confidence"] = ConfidenceLevel(d["data_confidence"])
    d["evidence_confidence"] = ConfidenceLevel(d["evidence_confidence"])
    d["research_confidence"] = ConfidenceLevel(d["research_confidence"])
    d["conclusion"] = ResearchConclusion(d["conclusion"])
    d["bull_case"] = _narrative_case_from_dict(d["bull_case"])
    d["base_case"] = _narrative_case_from_dict(d["base_case"])
    d["bear_case"] = _narrative_case_from_dict(d["bear_case"])
    d["data_gaps"] = tuple(_data_gap_from_dict(g) for g in (d.get("data_gaps") or []))
    d["included_evidence_ids"] = tuple(d.get("included_evidence_ids") or ())
    return ResearchArtifact(**d)


class ResearchArtifactRegistry:
    """JSON Lines形式で追記専用に記録するResearch Artifact Registry。"""

    def __init__(self, storage_path: Path) -> None:
        self._storage_path = storage_path
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, artifact: ResearchArtifact) -> None:
        existing_ids = {a.artifact_id for a in self.all()}
        if artifact.artifact_id in existing_ids:
            raise AppendOnlyViolationError(f"artifact_id={artifact.artifact_id} は既に記録されています(上書き不可)")
        line = json.dumps(_artifact_to_dict(artifact), ensure_ascii=False)
        with self._storage_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def all(self) -> list[ResearchArtifact]:
        if not self._storage_path.exists():
            return []
        artifacts = []
        with self._storage_path.open(encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.strip()
                if line:
                    artifacts.append(_artifact_from_dict(json.loads(line)))
        return artifacts

    def latest_for(self, entity_code: str, as_of: datetime) -> ResearchArtifact | None:
        """同一entity_code・同一as_ofの中で最新Version(最大artifact_version)を返す
        (`supersedes_artifact_id`によるLineageのうち「今読むべき版」を選ぶ用途)。"""
        candidates = [a for a in self.all() if a.entity_code == entity_code and a.as_of == as_of]
        if not candidates:
            return None
        return max(candidates, key=lambda a: a.artifact_version)


__all__ = ["ResearchArtifactRegistry"]
