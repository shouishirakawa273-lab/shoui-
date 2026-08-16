"""Phase4B-1(D0045): Disclosure Common Coreの統合テスト。

Raw Snapshot -> DisclosureDocument -> Evidence -> Catalog/Provenanceの
各接続点、およびOffline再現性を確認する。外部呼び出しは一切行わない。
"""

from __future__ import annotations

import dataclasses
import json
from datetime import UTC, datetime
from pathlib import Path

from lib.data_sources.base import RawFetchResult
from lib.disclosures.catalog import build_disclosure_common_core_dataset_descriptor
from lib.disclosures.evidence import disclosure_document_to_evidence
from lib.disclosures.normalize import parse_disclosure_payload
from lib.evidence.model import EvidenceRecord, EvidenceType
from lib.registry.provenance import ProvenanceLink, ProvenanceStore
from lib.reproducibility import hash_json_safe
from lib.snapshot import RawSnapshotStore
from lib.sources.catalog import DataCapability, ImplementationStatus, SourceAuthorityClass, SourceCatalog

_FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "disclosure_common_core_v1.json"
_RETRIEVED_AT = datetime(2026, 1, 1, tzinfo=UTC)


def _load_payload() -> list[dict[str, object]]:
    return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))["data"]


def _fetch_result() -> RawFetchResult:
    return RawFetchResult(
        source="disclosure_fixture",
        endpoint="fixture:disclosure_common_core",
        request_parameters={"codes": ["7203", "6758", "8056", "3626"]},
        retrieved_at=_RETRIEVED_AT,
        data_period="requested_research_window=2024-01-01/2024-12-31",
        response_schema_version="disclosure-common-core-fixture-v1",
        payload=_load_payload(),
    )


# --- Catalog統合 ---


def test_disclosure_common_core_registered_under_disclosure_capability() -> None:
    catalog = SourceCatalog([build_disclosure_common_core_dataset_descriptor()])
    found = catalog.find(capability=DataCapability.DISCLOSURE)
    assert [d.dataset_id for d in found] == ["disclosure_common_core"]
    assert found[0].implementation_status == ImplementationStatus.FIXTURE_ONLY
    assert found[0].pit_available is True


def test_disclosure_common_core_not_found_under_unrelated_capability() -> None:
    catalog = SourceCatalog([build_disclosure_common_core_dataset_descriptor()])
    assert catalog.find(capability=DataCapability.NEWS) == ()


# --- Evidence統合(#23/#24/#25) ---

_FORBIDDEN_INTERPRETATION_WORDS = ("bullish", "bearish", "buy", "sell", "好調", "悪化", "割安", "割高", "強気", "弱気")


def test_disclosure_document_to_evidence_is_fact_only() -> None:
    documents = parse_disclosure_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    for document in documents:
        evidence = disclosure_document_to_evidence(document, source_authority_class=SourceAuthorityClass.COMPANY_PRIMARY)
        assert evidence.evidence_type == EvidenceType.FACT
        lowered = evidence.content.lower()
        for forbidden_word in _FORBIDDEN_INTERPRETATION_WORDS:
            assert forbidden_word not in lowered


def test_disclosure_document_to_evidence_content_only_mentions_publication_metadata() -> None:
    """本文の内容(会社予想等)は一切Evidence Contentへ混入しない: Titleと
    DocumentKindと公開Metadataのみで構成される(Core Principleの確認)。"""
    documents = parse_disclosure_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    document = next(d for d in documents if d.source_document_id == "FIX-D-001")
    evidence = disclosure_document_to_evidence(document, source_authority_class=SourceAuthorityClass.COMPANY_PRIMARY)
    assert document.title in evidence.content
    assert document.document_kind.value in evidence.content
    assert "公開" in evidence.content


def test_evidence_record_has_no_relation_or_sentiment_field() -> None:
    """EvidenceRecordはEvidenceRelation(SUPPORTS/CONTRADICTS等)やBullish/
    Bearish分類のFieldを一切持たない(既存Schema設計、D0040のまま)。"""
    field_names = {f.name for f in dataclasses.fields(EvidenceRecord)}
    assert "relation" not in field_names
    assert "sentiment" not in field_names
    assert "classification" not in field_names


def test_disclosure_evidence_preserves_origin_vs_delivery_distinction() -> None:
    documents = parse_disclosure_payload(
        _load_payload(),
        retrieved_at=_RETRIEVED_AT,
        originating_source="TDNET_FIXTURE",
        delivery_provider="AGGREGATOR_FIXTURE",
    )
    evidence = disclosure_document_to_evidence(documents[0], source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL)
    assert evidence.source.originating_source == "TDNET_FIXTURE"
    assert evidence.source.delivery_provider == "AGGREGATOR_FIXTURE"


# --- Provenance Chain(Raw Snapshot -> Normalized -> Evidence) ---


def test_raw_snapshot_to_evidence_provenance_chain_is_traceable(tmp_path: Path) -> None:
    fetch_result = _fetch_result()
    snapshot_store = RawSnapshotStore(tmp_path / "raw")
    manifest = snapshot_store.save(fetch_result, snapshot_id="SNAP_DISCLOSURE_1")

    _, loaded_payload = snapshot_store.load("disclosure_fixture", "SNAP_DISCLOSURE_1")
    documents = parse_disclosure_payload(loaded_payload, retrieved_at=_RETRIEVED_AT, source_snapshot_id=manifest.snapshot_id)
    document = next(d for d in documents if d.source_document_id == "FIX-D-001")
    evidence = disclosure_document_to_evidence(document, source_authority_class=SourceAuthorityClass.COMPANY_PRIMARY)

    store = ProvenanceStore(tmp_path / "provenance.jsonl")
    store.add_link(
        ProvenanceLink(
            link_id="L1",
            from_type="raw_snapshot",
            from_id=manifest.snapshot_id,
            to_type="disclosure_document",
            to_id=document.internal_document_id,
        )
    )
    store.add_link(
        ProvenanceLink(
            link_id="L2",
            from_type="disclosure_document",
            from_id=document.internal_document_id,
            to_type="evidence",
            to_id=evidence.evidence_id,
        )
    )

    chain = store.trace_to_origin("evidence", evidence.evidence_id)
    assert [link.from_type for link in chain] == ["raw_snapshot", "disclosure_document"]
    assert chain[0].from_id == manifest.snapshot_id
    assert document.raw_snapshot_ref == manifest.snapshot_id


# --- Offline再現性 ---


def test_full_pipeline_is_reproducible_offline_from_saved_snapshot(tmp_path: Path) -> None:
    fetch_result = _fetch_result()
    snapshot_store = RawSnapshotStore(tmp_path / "raw")
    snapshot_store.save(fetch_result, snapshot_id="SNAP_DISCLOSURE_OFFLINE")

    def _run_pipeline_from_snapshot() -> list[str]:
        _, payload = snapshot_store.load("disclosure_fixture", "SNAP_DISCLOSURE_OFFLINE")
        documents = parse_disclosure_payload(payload, retrieved_at=_RETRIEVED_AT)
        return sorted(d.internal_document_id for d in documents)

    run_1 = _run_pipeline_from_snapshot()
    run_2 = _run_pipeline_from_snapshot()
    assert run_1 == run_2
    assert len(run_1) > 0


def test_normalized_dataset_hash_is_stable_for_same_raw_payload() -> None:
    """同一Raw Payload + 同一normalizer_versionなら、同一のNormalized Dataset
    Hashになる(Property/Invariant、Fundamentals Phase4Aと同じ検証パターン)。"""

    def _normalized_hash() -> str:
        documents = parse_disclosure_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
        serialized = {
            "documents": sorted(f"{d.internal_document_id}:{d.document_kind.value}:{d.title}" for d in documents),
            "normalizer_versions": sorted({d.normalizer_version for d in documents}),
        }
        return hash_json_safe(serialized)

    assert _normalized_hash() == _normalized_hash()
