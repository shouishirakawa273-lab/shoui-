"""Phase4A(D0043): Fundamental Data Pipelineの統合テスト。

Raw Snapshot -> Normalized(DisclosureEnvelope/FundamentalMetric) -> Evidence ->
Data Catalog / Provenanceの各接続点を確認する(20項目Testのうち#17〜#20、
および未Formal化だったCatalog/Evidence接続を補う)。

外部API呼び出しは一切行わない(D0042 Offline原則)。RawSnapshotStore/
parse_financial_summary_payload/build_revision_histories/fundamentals_as_of/
disclosure_metric_to_evidence はいずれも与えられたデータのみで完結する。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from lib.data_sources.base import RawFetchResult
from lib.evidence.model import AvailabilitySemantics, EvidenceType
from lib.fundamentals.catalog import build_financial_summary_dataset_descriptor
from lib.fundamentals.evidence import disclosure_metric_to_evidence
from lib.fundamentals.normalize import build_revision_histories, parse_financial_summary_payload
from lib.fundamentals.view import fundamentals_as_of
from lib.registry.provenance import ProvenanceLink, ProvenanceStore
from lib.reproducibility import dataset_hash_from_snapshots, hash_json_safe
from lib.snapshot import RawSnapshotStore
from lib.sources.catalog import DataCapability, ImplementationStatus, SourceCatalog

_FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "financial_summary_v2.json"
_RETRIEVED_AT = datetime(2026, 1, 1, tzinfo=UTC)


def _load_payload() -> list[dict[str, object]]:
    return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))["data"]


def _fetch_result() -> RawFetchResult:
    return RawFetchResult(
        source="jquants",
        endpoint="/v2/fins/summary",
        request_parameters={"codes": ["7203", "6758", "8056", "3626"], "from": "2024-01-01", "to": "2024-12-31"},
        retrieved_at=_RETRIEVED_AT,
        data_period="2024-01-01/2024-12-31",
        response_schema_version="v2",
        payload=_load_payload(),
    )


# --- Catalog統合 ---


def test_financial_summary_dataset_is_registered_in_catalog_under_fundamental_capability() -> None:
    catalog = SourceCatalog([build_financial_summary_dataset_descriptor()])
    found = catalog.find(capability=DataCapability.FUNDAMENTAL)
    assert [d.dataset_id for d in found] == ["jquants_fins_summary"]
    assert found[0].implementation_status == ImplementationStatus.CONNECTED  # 4銘柄Local Real Data Validation済み(D0043)
    assert found[0].pit_available is True


def test_financial_summary_dataset_not_found_under_unrelated_capability() -> None:
    catalog = SourceCatalog([build_financial_summary_dataset_descriptor()])
    assert catalog.find(capability=DataCapability.NEWS) == ()


# --- Evidence統合(#20: FACTのみ、解釈語・Relationを持たない) ---

_FORBIDDEN_INTERPRETATION_WORDS = ("bullish", "bearish", "buy", "sell", "好調", "悪化", "割安", "割高", "強気", "弱気")


def test_disclosure_metric_to_evidence_is_fact_only_with_no_interpretation_language() -> None:
    envelopes, metrics = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    envelopes_by_id = {e.envelope_id: e for e in envelopes}
    forecast_metrics = [m for m in metrics if m.metric_type == "operating_profit_current_year_forecast"]
    assert forecast_metrics

    for metric in forecast_metrics:
        evidence = disclosure_metric_to_evidence(envelopes_by_id[metric.envelope_id], metric)
        assert evidence.evidence_type == EvidenceType.FACT
        lowered_content = evidence.content.lower()
        for forbidden_word in _FORBIDDEN_INTERPRETATION_WORDS:
            assert forbidden_word not in lowered_content


def test_disclosure_metric_to_evidence_carries_source_authority_and_pit_fields() -> None:
    envelopes, metrics = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
    envelope = next(e for e in envelopes if e.internal_code == "7203")
    metric = next(m for m in metrics if m.envelope_id == envelope.envelope_id and m.metric_type == "operating_profit")
    evidence = disclosure_metric_to_evidence(envelope, metric)

    assert evidence.source.originating_source == "JQUANTS_SOURCE_DATA"
    assert evidence.source.delivery_provider == "JQUANTS"
    assert evidence.source.available_at is not None
    assert evidence.related_codes == ("7203",)


# --- Provenance Chain(#17: Raw Snapshot -> Normalized -> Evidence が遡れる) ---


def test_raw_snapshot_to_evidence_provenance_chain_is_traceable(tmp_path: Path) -> None:
    fetch_result = _fetch_result()
    snapshot_store = RawSnapshotStore(tmp_path / "raw")
    manifest = snapshot_store.save(fetch_result, snapshot_id="SNAP_FINS_1")

    _, loaded_payload = snapshot_store.load("jquants", "SNAP_FINS_1")
    envelopes, metrics = parse_financial_summary_payload(
        loaded_payload, retrieved_at=_RETRIEVED_AT, source_snapshot_id=manifest.snapshot_id
    )
    envelope = next(e for e in envelopes if e.internal_code == "7203")
    metric = next(
        m for m in metrics if m.envelope_id == envelope.envelope_id and m.metric_type == "operating_profit_current_year_forecast"
    )
    evidence = disclosure_metric_to_evidence(envelope, metric)

    store = ProvenanceStore(tmp_path / "provenance.jsonl")
    store.add_link(
        ProvenanceLink(
            link_id="L1",
            from_type="raw_snapshot",
            from_id=manifest.snapshot_id,
            to_type="disclosure_envelope",
            to_id=envelope.envelope_id,
        )
    )
    store.add_link(
        ProvenanceLink(
            link_id="L2",
            from_type="disclosure_envelope",
            from_id=envelope.envelope_id,
            to_type="fundamental_metric",
            to_id=metric.metric_id,
        )
    )
    store.add_link(
        ProvenanceLink(
            link_id="L3", from_type="fundamental_metric", from_id=metric.metric_id, to_type="evidence", to_id=evidence.evidence_id
        )
    )

    chain = store.trace_to_origin("evidence", evidence.evidence_id)
    assert [link.from_type for link in chain] == ["raw_snapshot", "disclosure_envelope", "fundamental_metric"]
    assert chain[0].from_id == manifest.snapshot_id
    assert chain[-1].to_id == evidence.evidence_id
    assert envelope.source_snapshot_id == manifest.snapshot_id


# --- Offline再現性(#18: Frozen Datasetは外部呼び出し無しで再現できる) ---


def test_full_pipeline_is_reproducible_offline_from_saved_snapshot(tmp_path: Path) -> None:
    """Snapshot保存 -> (Session再起動を模した)再読み込み -> 正規化 -> As-of Viewまで、
    一切ネットワークへ触れずに再現できることを確認する(D0042 Offline原則)。
    """
    fetch_result = _fetch_result()
    snapshot_store = RawSnapshotStore(tmp_path / "raw")
    manifest = snapshot_store.save(fetch_result, snapshot_id="SNAP_FINS_OFFLINE")

    def _run_pipeline_from_snapshot() -> dict[str, str | None]:
        _, payload = snapshot_store.load("jquants", "SNAP_FINS_OFFLINE")
        envelopes, metrics = parse_financial_summary_payload(payload, retrieved_at=_RETRIEVED_AT)
        histories = build_revision_histories(envelopes, metrics)
        sid = next(s for s in histories if s.startswith("7203|operating_profit_current_year_forecast|CURRENT_FISCAL_YEAR|FY|"))
        result = fundamentals_as_of(
            histories, datetime(2024, 9, 1, tzinfo=UTC), availability_semantics=AvailabilitySemantics.MARKET_PUBLIC_AT
        )
        version = result[sid]
        return {sid: version.value if version is not None else None}

    run_1 = _run_pipeline_from_snapshot()
    run_2 = _run_pipeline_from_snapshot()
    assert run_1 == run_2
    assert list(run_1.values()) == ["120000"]

    # 同じcontent_hashから導出したdataset_hashも再現する(Experiment.dataset_hash相当)。
    dataset_hash_1 = dataset_hash_from_snapshots([manifest.content_hash])
    dataset_hash_2 = dataset_hash_from_snapshots([manifest.content_hash])
    assert dataset_hash_1 == dataset_hash_2


def test_normalized_dataset_hash_is_stable_for_same_raw_payload_and_normalizer_version() -> None:
    """同一Raw Snapshot + 同一normalizer_versionなら、同一のNormalized Dataset Hashに
    なる(Property/Invariant、#26要件の一部)。"""

    def _normalized_hash() -> str:
        envelopes, metrics = parse_financial_summary_payload(_load_payload(), retrieved_at=_RETRIEVED_AT)
        serialized = {
            "envelopes": sorted(e.envelope_id for e in envelopes),
            "metrics": sorted(f"{m.metric_id}:{m.raw_value}:{m.value_availability.value}" for m in metrics),
            "normalizer_versions": sorted({e.normalizer_version for e in envelopes}),
        }
        return hash_json_safe(serialized)

    assert _normalized_hash() == _normalized_hash()
