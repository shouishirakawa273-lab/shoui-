"""Stage 3 v1: ResearchArtifactRegistryの追記専用永続化Test(要件v1-9)。

既存の`ExperimentRegistry`/`PreregistrationRegistry`と同じAppend-only
Patternであることを確認する(重複ID拒否・全件round-trip・後方互換読み込み)。
"""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from lib.errors import AppendOnlyViolationError
from lib.evidence.research_artifact import (
    ConfidenceLevel,
    DataGap,
    DataGapStatus,
    NarrativeCase,
    ResearchArtifact,
    ResearchConclusion,
)
from lib.registry.research_artifact_registry import ResearchArtifactRegistry

_ENTITY = "7203"


def _artifact(*, artifact_id: str, as_of: datetime, evidence_ids: tuple[str, ...] = ("EVID_1",)) -> ResearchArtifact:
    return ResearchArtifact(
        artifact_id=artifact_id,
        entity_code=_ENTITY,
        as_of=as_of,
        research_question_id="RQ_TEST_0001",
        evidence_packet_id=f"PKT_{artifact_id}",
        included_evidence_ids=evidence_ids,
        bull_case=NarrativeCase(summary="Bull", supporting_evidence_ids=evidence_ids),
        base_case=NarrativeCase(summary="Base"),
        bear_case=NarrativeCase(summary="Bear"),
        data_gaps=(DataGap(topic="Consensus予想", status=DataGapStatus.MISSING, note="v1では取得しない"),),
        data_confidence=ConfidenceLevel.MEDIUM,
        evidence_confidence=ConfidenceLevel.MEDIUM,
        research_confidence=ConfidenceLevel.MEDIUM,
        conclusion=ResearchConclusion.PARTIALLY_SUPPORTED,
        conclusion_rationale="test",
    )


def test_record_and_read_back_roundtrip(tmp_path: Path) -> None:
    registry = ResearchArtifactRegistry(tmp_path / "research_artifacts.jsonl")
    as_of = datetime(2026, 6, 1, tzinfo=UTC)
    artifact = _artifact(artifact_id="ART_0001", as_of=as_of)
    registry.record(artifact)

    loaded = registry.all()
    assert len(loaded) == 1
    assert loaded[0].artifact_id == "ART_0001"
    assert loaded[0].as_of == as_of
    assert loaded[0].bull_case.supporting_evidence_ids == ("EVID_1",)
    assert loaded[0].data_gaps == (DataGap(topic="Consensus予想", status=DataGapStatus.MISSING, note="v1では取得しない"),)
    assert loaded[0].conclusion == ResearchConclusion.PARTIALLY_SUPPORTED


def test_duplicate_artifact_id_is_rejected(tmp_path: Path) -> None:
    registry = ResearchArtifactRegistry(tmp_path / "research_artifacts.jsonl")
    as_of = datetime(2026, 6, 1, tzinfo=UTC)
    artifact = _artifact(artifact_id="ART_0002", as_of=as_of)
    registry.record(artifact)
    with pytest.raises(AppendOnlyViolationError):
        registry.record(artifact)


def test_registry_exposes_no_delete_or_update_method() -> None:
    """Phase5 VAL-025(`test_val025_preregistration_registry_exposes_no_delete_or_update_method`)
    と同じパターン。"""
    public_methods = {name for name in dir(ResearchArtifactRegistry) if not name.startswith("_")}
    assert "delete" not in public_methods
    assert "update" not in public_methods
    assert "overwrite" not in public_methods


def test_latest_for_returns_highest_artifact_version(tmp_path: Path) -> None:
    registry = ResearchArtifactRegistry(tmp_path / "research_artifacts.jsonl")
    as_of = datetime(2026, 6, 1, tzinfo=UTC)
    v1 = _artifact(artifact_id="ART_0003_V1", as_of=as_of)
    registry.record(v1)
    v2 = replace(v1, artifact_id="ART_0003_V2", artifact_version=2, supersedes_artifact_id=v1.artifact_id)
    registry.record(v2)

    latest = registry.latest_for(_ENTITY, as_of)
    assert latest is not None
    assert latest.artifact_id == "ART_0003_V2"
    assert latest.supersedes_artifact_id == "ART_0003_V1"


def test_old_records_without_data_gaps_key_still_load(tmp_path: Path) -> None:
    """data_gapsフィールド追加前の既存Record(仮に旧Version)が、キー自体を
    持たなくても引き続き読み込める(後方互換、既存Lab Registryと同じ慣行)。"""
    storage_path = tmp_path / "research_artifacts.jsonl"
    registry = ResearchArtifactRegistry(storage_path)
    as_of = datetime(2026, 6, 1, tzinfo=UTC)
    registry.record(_artifact(artifact_id="ART_OLD", as_of=as_of))

    lines = storage_path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[0])
    del record["data_gaps"]
    storage_path.write_text(json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8")

    loaded = ResearchArtifactRegistry(storage_path).all()[0]
    assert loaded.data_gaps == ()
    assert loaded.artifact_id == "ART_OLD"
