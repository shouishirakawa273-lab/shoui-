"""EvidenceRegistry(Stage 3.15.1、D0090): `EvidenceRecord`をLosslessに
永続化・Fresh Process再解決できることを検証する。

D0089(Stage 3.15)は、Historical/Current PER Observationを「Evidence ID
文字列」としてのみ参照し、実際の`EvidenceRecord`をどこにも永続化して
いなかった(Post-Implementation Reviewで指摘された欠落)。この欠落を
埋めるための最小基盤が実際にLossless Round-Tripすることを確認する。
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from lib.errors import AppendOnlyViolationError
from lib.evidence.model import AiDerivedProvenance, DataLayer, EvidenceRecord, EvidenceType
from lib.registry.evidence_registry import EvidenceRegistry
from lib.sources.catalog import DataCapability, PrimaryOrSecondary, SourceAuthorityClass, SourceMetadata

_JST = ZoneInfo("Asia/Tokyo")


def _full_evidence(evidence_id: str = "EVID_TEST_1") -> EvidenceRecord:
    source = SourceMetadata(
        source_id="SRC_1",
        source_type="LATEST_REPORTED_FY_PER",
        provider_name="LATEST_REPORTED_FY_PER",
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        primary_or_secondary=PrimaryOrSecondary.PRIMARY,
        retrieved_at=datetime(2024, 11, 14, 15, 30, tzinfo=_JST),
        published_at=datetime(2024, 5, 8, 13, 55, tzinfo=_JST),
        available_at=datetime(2024, 11, 14, 15, 30, tzinfo=_JST),
        effective_at=date(2024, 4, 1),
        source_url="https://example.invalid/disclosure/1",
        license_or_usage_note="test license note",
        content_hash="abc123",
        provenance_id="PROV_1",
        originating_source="JQUANTS_SOURCE_DATA",
        delivery_provider="JQUANTS",
    )
    ai_prov = AiDerivedProvenance(
        model_provider="anthropic",
        model_name="claude-test",
        model_version="v1",
        prompt_version="p1",
        prompt_hash="hash1",
        input_evidence_ids=("EVID_A", "EVID_B"),
        retrieval_plan_hash="plan1",
        generated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    return EvidenceRecord(
        evidence_id=evidence_id,
        evidence_type=EvidenceType.FACT,
        layer=DataLayer.DERIVED,
        capability=DataCapability.VALUATION,
        content="7203: price_close(2024-11-14)=2666 / fy_actual_eps=365.94",
        source=source,
        value_date=date(2024, 11, 14),
        related_codes=("7203", "7203_ALT"),
        related_sectors=("3700",),
        ai_derived_provenance=ai_prov,
        provenance_id="PROV_TOP",
    )


def _minimal_evidence(evidence_id: str = "EVID_MINIMAL_1") -> EvidenceRecord:
    """Optional Fieldが全てNone/空のEvidence(published_at/effective_at/
    ai_derived_provenance等がNoneでもLosslessに保持できることを確認する用)。"""
    source = SourceMetadata(
        source_id="SRC_MIN",
        source_type="LATEST_REPORTED_FY_PER",
        provider_name="LATEST_REPORTED_FY_PER",
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        primary_or_secondary=PrimaryOrSecondary.PRIMARY,
        retrieved_at=datetime(2024, 11, 14, 15, 30, tzinfo=_JST),
        published_at=None,
        available_at=datetime(2024, 11, 14, 15, 30, tzinfo=_JST),
    )
    return EvidenceRecord(
        evidence_id=evidence_id,
        evidence_type=EvidenceType.FACT,
        layer=DataLayer.DERIVED,
        capability=DataCapability.VALUATION,
        content="minimal content",
        source=source,
    )


def test_register_and_get(tmp_path: Path) -> None:
    registry = EvidenceRegistry(tmp_path / "evidence.jsonl")
    record = _full_evidence()
    registry.register(record)
    resolved = registry.get(record.evidence_id)
    assert resolved is not None
    assert resolved.evidence_id == record.evidence_id


def test_get_returns_none_for_unknown_id(tmp_path: Path) -> None:
    registry = EvidenceRegistry(tmp_path / "evidence.jsonl")
    assert registry.get("EVID_UNKNOWN") is None


def test_require_raises_for_unknown_id(tmp_path: Path) -> None:
    registry = EvidenceRegistry(tmp_path / "evidence.jsonl")
    with pytest.raises(KeyError):
        registry.require("EVID_UNKNOWN")


def test_require_returns_record_for_known_id(tmp_path: Path) -> None:
    registry = EvidenceRegistry(tmp_path / "evidence.jsonl")
    record = _full_evidence()
    registry.register(record)
    assert registry.require(record.evidence_id).evidence_id == record.evidence_id


def test_all_returns_every_registered_record(tmp_path: Path) -> None:
    registry = EvidenceRegistry(tmp_path / "evidence.jsonl")
    registry.register(_full_evidence("EVID_A"))
    registry.register(_full_evidence("EVID_B"))
    registry.register(_minimal_evidence("EVID_C"))
    ids = {r.evidence_id for r in registry.all()}
    assert ids == {"EVID_A", "EVID_B", "EVID_C"}


def test_fresh_instance_reload_resolves_same_record(tmp_path: Path) -> None:
    """同一Processでも、EvidenceRegistryを新しいObjectとして再構築(=Freshな
    Instance、内部キャッシュ等に依存していないことの最小確認)しても解決できる。
    真のFresh Process境界はReal Acceptance Scriptで別途検証する。"""
    path = tmp_path / "evidence.jsonl"
    registry_a = EvidenceRegistry(path)
    record = _full_evidence()
    registry_a.register(record)

    registry_b = EvidenceRegistry(path)  # 新しいInstance、同一Storage Path
    resolved = registry_b.get(record.evidence_id)
    assert resolved is not None
    assert resolved == record  # dataclass equality、完全なSemantic Equality


def test_datetime_timezone_round_trips(tmp_path: Path) -> None:
    registry = EvidenceRegistry(tmp_path / "evidence.jsonl")
    record = _full_evidence()
    registry.register(record)
    resolved = registry.require(record.evidence_id)
    assert resolved.source.retrieved_at == record.source.retrieved_at
    assert resolved.source.retrieved_at.tzinfo is not None
    assert resolved.source.available_at == record.source.available_at
    assert resolved.source.published_at == record.source.published_at
    assert resolved.source.published_at.utcoffset() == record.source.published_at.utcoffset()


def test_enum_fields_round_trip_to_correct_type(tmp_path: Path) -> None:
    registry = EvidenceRegistry(tmp_path / "evidence.jsonl")
    record = _full_evidence()
    registry.register(record)
    resolved = registry.require(record.evidence_id)
    assert resolved.evidence_type is EvidenceType.FACT
    assert resolved.layer is DataLayer.DERIVED
    assert resolved.capability is DataCapability.VALUATION
    assert resolved.source.source_authority_class is SourceAuthorityClass.PRIMARY_OFFICIAL
    assert resolved.source.primary_or_secondary is PrimaryOrSecondary.PRIMARY


def test_date_fields_round_trip(tmp_path: Path) -> None:
    registry = EvidenceRegistry(tmp_path / "evidence.jsonl")
    record = _full_evidence()
    registry.register(record)
    resolved = registry.require(record.evidence_id)
    assert resolved.value_date == record.value_date
    assert isinstance(resolved.value_date, date)
    assert resolved.source.effective_at == record.source.effective_at
    assert isinstance(resolved.source.effective_at, date)


def test_tuple_fields_round_trip_as_tuple_not_list(tmp_path: Path) -> None:
    registry = EvidenceRegistry(tmp_path / "evidence.jsonl")
    record = _full_evidence()
    registry.register(record)
    resolved = registry.require(record.evidence_id)
    assert resolved.related_codes == record.related_codes
    assert isinstance(resolved.related_codes, tuple)
    assert resolved.related_sectors == record.related_sectors
    assert isinstance(resolved.related_sectors, tuple)
    assert resolved.ai_derived_provenance is not None
    assert resolved.ai_derived_provenance.input_evidence_ids == record.ai_derived_provenance.input_evidence_ids
    assert isinstance(resolved.ai_derived_provenance.input_evidence_ids, tuple)


def test_source_metadata_round_trips_fully(tmp_path: Path) -> None:
    registry = EvidenceRegistry(tmp_path / "evidence.jsonl")
    record = _full_evidence()
    registry.register(record)
    resolved = registry.require(record.evidence_id)
    assert resolved.source == record.source


def test_optional_fields_none_round_trip_as_none(tmp_path: Path) -> None:
    registry = EvidenceRegistry(tmp_path / "evidence.jsonl")
    record = _minimal_evidence()
    registry.register(record)
    resolved = registry.require(record.evidence_id)
    assert resolved.source.published_at is None
    assert resolved.source.effective_at is None
    assert resolved.value_date is None
    assert resolved.ai_derived_provenance is None
    assert resolved.provenance_id is None
    assert resolved.related_codes == ()
    assert resolved.related_sectors == ()


def test_full_record_semantic_equality_after_round_trip(tmp_path: Path) -> None:
    registry = EvidenceRegistry(tmp_path / "evidence.jsonl")
    record = _full_evidence()
    registry.register(record)
    resolved = registry.require(record.evidence_id)
    assert resolved == record


def test_duplicate_evidence_id_registration_is_rejected(tmp_path: Path) -> None:
    registry = EvidenceRegistry(tmp_path / "evidence.jsonl")
    record = _full_evidence()
    registry.register(record)
    with pytest.raises(AppendOnlyViolationError):
        registry.register(record)


def test_duplicate_evidence_id_with_different_payload_is_also_rejected(tmp_path: Path) -> None:
    """同一ID・異なるPayloadは無条件でReject(Upsert Semanticsを作らない、
    既存ProvenanceStore/ResearchArtifactRegistryと同じ設計)。"""
    registry = EvidenceRegistry(tmp_path / "evidence.jsonl")
    record_1 = _full_evidence("EVID_SAME_ID")
    record_2 = _minimal_evidence("EVID_SAME_ID")
    registry.register(record_1)
    with pytest.raises(AppendOnlyViolationError):
        registry.register(record_2)


def test_malformed_json_line_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "evidence.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not valid json\n", encoding="utf-8")
    registry = EvidenceRegistry(path)
    with pytest.raises(Exception):  # noqa: B017 - 既存ProvenanceStore/ResearchArtifactRegistryと同じ、json.loadsをそのまま伝播
        registry.all()
