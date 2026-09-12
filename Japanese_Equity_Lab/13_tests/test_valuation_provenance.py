"""`lib.valuation.provenance`(Stage 3.15.3、D0092): PER→Price/EPS Provenance
Edgeを実際に`ProvenanceStore`へ永続化するProduction Helperの検証。

31件(30 Historical + 1 Current)のFull Bundle Wiringを、D0077 1件だけの
既存Testでは代用せず、専用のCommitted Deterministic Integration Testで
確認する(要件v1 §17)。
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from lib.market_calendar import session_close_at
from lib.registry.evidence_registry import EvidenceRegistry
from lib.registry.provenance import ProvenanceStore
from lib.sources.catalog import SourceAuthorityClass
from lib.valuation.evidence import latest_reported_fy_per_to_evidence_v2
from lib.valuation.historical_context_builder import build_latest_reported_fy_per_historical_context
from lib.valuation.historical_context_evidence import latest_reported_fy_per_historical_context_to_evidence
from lib.valuation.model import CorporateActionBasisStatus, LatestReportedFyPerRecord
from lib.valuation.provenance import (
    register_historical_context_provenance_bundle,
    register_latest_reported_fy_per_upstream_provenance,
)

_JST = ZoneInfo("Asia/Tokyo")
_ENTITY = "7203"
_CURRENT_REFERENCE_AS_OF = datetime(2024, 11, 15, 15, 0, tzinfo=_JST)
_AUTH = SourceAuthorityClass.PRIMARY_OFFICIAL
_ORIG = "JQUANTS_SOURCE_DATA"
_DELIV = "JQUANTS"


def _per_record(
    *,
    as_of: datetime,
    price_date: date,
    price_value: Decimal,
    eps_value: Decimal,
    fiscal_period_end: date,
    published_at: datetime,
    source_version_id: str,
) -> LatestReportedFyPerRecord:
    return LatestReportedFyPerRecord(
        entity_code=_ENTITY,
        as_of=as_of,
        price_date=price_date,
        price_value=price_value,
        price_available_at=session_close_at(price_date),
        denominator_type="FY_ACTUAL_EPS_CONSOLIDATED",
        eps_value=eps_value,
        fiscal_period_end=fiscal_period_end,
        published_at=published_at,
        source_version_id=source_version_id,
        consolidation_scope="CONSOLIDATED",
        accounting_standard="IFRS",
        calculation_expression=f"price_close({price_date.isoformat()})={price_value} / fy_actual_eps={eps_value}",
        multiple=price_value / eps_value,
        corporate_action_basis_status=CorporateActionBasisStatus.CONFIRMED_NO_ACTION,
    )


def _current_record() -> LatestReportedFyPerRecord:
    return _per_record(
        as_of=_CURRENT_REFERENCE_AS_OF,
        price_date=date(2024, 11, 14),
        price_value=Decimal("2666"),
        eps_value=Decimal("365.94"),
        fiscal_period_end=date(2024, 3, 31),
        published_at=datetime(2024, 5, 8, 13, 55, tzinfo=_JST),
        source_version_id="SV_FY2024",
    )


def _thirty_historical_records() -> list[LatestReportedFyPerRecord]:
    records: list[LatestReportedFyPerRecord] = []
    regime_specs = [
        (date(2022, 3, 31), Decimal("205.23"), "SV_FY2022", 12),
        (date(2023, 3, 31), Decimal("179.47"), "SV_FY2023", 12),
        (date(2024, 3, 31), Decimal("365.94"), "SV_FY2024", 6),
    ]
    month_index = 0
    for fiscal_period_end, eps_value, source_version_id, count in regime_specs:
        for _ in range(count):
            year = 2022 + (month_index // 12)
            month = (month_index % 12) + 5
            while month > 12:
                month -= 12
                year += 1
            price_date = date(year, month, 28)
            records.append(
                _per_record(
                    as_of=session_close_at(price_date),
                    price_date=price_date,
                    price_value=Decimal("2000") + Decimal(month_index),
                    eps_value=eps_value,
                    fiscal_period_end=fiscal_period_end,
                    published_at=datetime(fiscal_period_end.year, 5, 10, 13, 55, tzinfo=_JST),
                    source_version_id=source_version_id,
                )
            )
            month_index += 1
    assert len(records) == 30
    return records


def _build_context_and_evidences():
    historical = _thirty_historical_records()
    current = _current_record()
    context_record = build_latest_reported_fy_per_historical_context(
        entity_code=_ENTITY,
        current_reference_as_of=_CURRENT_REFERENCE_AS_OF,
        current_record=current,
        historical_records=historical,
        attempted_anchor_count=len(historical) + 9,
        excluded_future_anchor_count=2,
        unavailable_denominator_count=7,
        corporate_action_excluded_count=0,
        minimum_sample_count=12,
    )
    assert context_record is not None
    context_evidence = latest_reported_fy_per_historical_context_to_evidence(
        context_record, source_authority_class=_AUTH, originating_source=_ORIG, delivery_provider=_DELIV
    )
    current_evidence = latest_reported_fy_per_to_evidence_v2(
        current, source_authority_class=_AUTH, originating_source=_ORIG, delivery_provider=_DELIV
    )
    historical_evidences = [
        latest_reported_fy_per_to_evidence_v2(r, source_authority_class=_AUTH, originating_source=_ORIG, delivery_provider=_DELIV)
        for r in historical
    ]
    return context_record, context_evidence, current, current_evidence, historical, historical_evidences


def _registered_registry(tmp_path: Path, current_evidence, historical_evidences) -> EvidenceRegistry:
    registry = EvidenceRegistry(tmp_path / "evidence.jsonl")
    registry.register(current_evidence)
    for e in historical_evidences:
        registry.register(e)
    return registry


# --- §17: 31-Record Committed Test ----------------------------------------------------------


def test_full_bundle_persists_31_context_31_price_31_eps_edges(tmp_path: Path) -> None:
    context_record, context_evidence, current, current_evidence, historical, historical_evidences = _build_context_and_evidences()
    evidence_registry = _registered_registry(tmp_path, current_evidence, historical_evidences)
    provenance_store = ProvenanceStore(tmp_path / "provenance.jsonl")

    register_historical_context_provenance_bundle(
        context_record=context_record,
        context_evidence=context_evidence,
        current_record=current,
        current_evidence=current_evidence,
        historical_records=historical,
        historical_evidences=historical_evidences,
        evidence_registry=evidence_registry,
        provenance_store=provenance_store,
    )

    # Fresh instance reload(同一Process内だが新規Object、内部キャッシュに依存しないことの確認)
    fresh_store = ProvenanceStore(tmp_path / "provenance.jsonl")
    fresh_registry = EvidenceRegistry(tmp_path / "evidence.jsonl")

    context_parents = fresh_store.parents_of("valuation_evidence", context_evidence.evidence_id)
    assert len(context_parents) == 31

    price_edges = 0
    eps_edges = 0
    for per_id in [current_evidence.evidence_id, *(e.evidence_id for e in historical_evidences)]:
        parents = fresh_store.parents_of("valuation_evidence", per_id)
        price_edges += sum(1 for link in parents if link.from_type == "price_bar")
        eps_edges += sum(1 for link in parents if link.from_type == "fundamental_source_version")
        assert fresh_registry.get(per_id) is not None

    assert price_edges == 31
    assert eps_edges == 31


# --- §18: Edge Failure Tests -----------------------------------------------------------------


def test_historical_count_mismatch_is_rejected(tmp_path: Path) -> None:
    context_record, context_evidence, current, current_evidence, historical, historical_evidences = _build_context_and_evidences()
    evidence_registry = _registered_registry(tmp_path, current_evidence, historical_evidences)
    provenance_store = ProvenanceStore(tmp_path / "provenance.jsonl")

    with pytest.raises(ValueError, match="Historical Count Mismatch"):
        register_historical_context_provenance_bundle(
            context_record=context_record,
            context_evidence=context_evidence,
            current_record=current,
            current_evidence=current_evidence,
            historical_records=historical[:-1],
            historical_evidences=historical_evidences[:-1],
            evidence_registry=evidence_registry,
            provenance_store=provenance_store,
        )


def test_wrong_current_per_evidence_id_is_rejected(tmp_path: Path) -> None:
    """Currentとして、実際にはHistorical[0]から構築されたEvidence(=別Price Date、
    別evidence_id)を渡す——重複登録を避けるためHistorical Evidence Listには含めない。"""
    context_record, context_evidence, current, _current_evidence, historical, historical_evidences = (
        _build_context_and_evidences()
    )
    wrong_current_evidence = latest_reported_fy_per_to_evidence_v2(
        historical[0], source_authority_class=_AUTH, originating_source=_ORIG, delivery_provider=_DELIV
    )
    evidence_registry = EvidenceRegistry(tmp_path / "evidence.jsonl")
    evidence_registry.register(wrong_current_evidence)
    for e in historical_evidences[1:]:
        evidence_registry.register(e)
    provenance_store = ProvenanceStore(tmp_path / "provenance.jsonl")

    with pytest.raises(ValueError, match="Wrong PER Evidence ID"):
        register_historical_context_provenance_bundle(
            context_record=context_record,
            context_evidence=context_evidence,
            current_record=current,
            current_evidence=wrong_current_evidence,
            historical_records=historical,
            historical_evidences=historical_evidences,
            evidence_registry=evidence_registry,
            provenance_store=provenance_store,
        )


def test_wrong_entity_is_rejected(tmp_path: Path) -> None:
    """entity_codeはv2 Identityに含まれるため、entity不一致は自動的にID不一致としても
    検知される(fail closedであること自体を確認する、Error文言はID/Entityいずれの
    表現でもよい)。"""
    context_record, context_evidence, current, current_evidence, historical, historical_evidences = _build_context_and_evidences()
    from dataclasses import replace

    tampered_current = replace(current, entity_code="9999")
    evidence_registry = _registered_registry(tmp_path, current_evidence, historical_evidences)
    provenance_store = ProvenanceStore(tmp_path / "provenance.jsonl")

    with pytest.raises(ValueError, match="一致しません"):
        register_historical_context_provenance_bundle(
            context_record=context_record,
            context_evidence=context_evidence,
            current_record=tampered_current,
            current_evidence=current_evidence,
            historical_records=historical,
            historical_evidences=historical_evidences,
            evidence_registry=evidence_registry,
            provenance_store=provenance_store,
        )


def test_wrong_capability_evidence_is_rejected(tmp_path: Path) -> None:
    context_record, context_evidence, current, current_evidence, historical, historical_evidences = _build_context_and_evidences()
    from dataclasses import replace

    from lib.sources.catalog import DataCapability

    tampered_current_evidence = replace(current_evidence, capability=DataCapability.FUNDAMENTAL)
    evidence_registry = _registered_registry(tmp_path, tampered_current_evidence, historical_evidences)
    provenance_store = ProvenanceStore(tmp_path / "provenance.jsonl")

    with pytest.raises(ValueError, match="capability"):
        register_historical_context_provenance_bundle(
            context_record=context_record,
            context_evidence=context_evidence,
            current_record=current,
            current_evidence=tampered_current_evidence,
            historical_records=historical,
            historical_evidences=historical_evidences,
            evidence_registry=evidence_registry,
            provenance_store=provenance_store,
        )


def test_duplicate_historical_evidence_is_rejected(tmp_path: Path) -> None:
    context_record, context_evidence, current, current_evidence, historical, historical_evidences = _build_context_and_evidences()
    dup_historical = [*historical[:-1], historical[0]]
    dup_evidences = [*historical_evidences[:-1], historical_evidences[0]]
    evidence_registry = _registered_registry(tmp_path, current_evidence, historical_evidences)
    provenance_store = ProvenanceStore(tmp_path / "provenance.jsonl")

    with pytest.raises(ValueError, match="Duplicate Historical Evidence"):
        register_historical_context_provenance_bundle(
            context_record=context_record,
            context_evidence=context_evidence,
            current_record=current,
            current_evidence=current_evidence,
            historical_records=dup_historical,
            historical_evidences=dup_evidences,
            evidence_registry=evidence_registry,
            provenance_store=provenance_store,
        )


def test_fake_parent_evidence_not_in_registry_is_rejected(tmp_path: Path) -> None:
    context_record, context_evidence, current, current_evidence, historical, historical_evidences = _build_context_and_evidences()
    # わざとCurrentのみ登録し、Historicalは登録しない(Fake/Unregistered Parent)。
    evidence_registry = EvidenceRegistry(tmp_path / "evidence.jsonl")
    evidence_registry.register(current_evidence)
    provenance_store = ProvenanceStore(tmp_path / "provenance.jsonl")

    with pytest.raises(ValueError, match="Fake Parent Evidence"):
        register_historical_context_provenance_bundle(
            context_record=context_record,
            context_evidence=context_evidence,
            current_record=current,
            current_evidence=current_evidence,
            historical_records=historical,
            historical_evidences=historical_evidences,
            evidence_registry=evidence_registry,
            provenance_store=provenance_store,
        )


def test_duplicate_upstream_registration_is_rejected(tmp_path: Path) -> None:
    context_record, context_evidence, current, current_evidence, historical, historical_evidences = _build_context_and_evidences()
    evidence_registry = _registered_registry(tmp_path, current_evidence, historical_evidences)
    provenance_store = ProvenanceStore(tmp_path / "provenance.jsonl")

    register_historical_context_provenance_bundle(
        context_record=context_record,
        context_evidence=context_evidence,
        current_record=current,
        current_evidence=current_evidence,
        historical_records=historical,
        historical_evidences=historical_evidences,
        evidence_registry=evidence_registry,
        provenance_store=provenance_store,
    )

    from lib.errors import AppendOnlyViolationError

    with pytest.raises(AppendOnlyViolationError):
        register_latest_reported_fy_per_upstream_provenance(
            record=current, evidence=current_evidence, provenance_store=provenance_store
        )


def test_single_helper_rejects_v1_evidence(tmp_path: Path) -> None:
    from lib.valuation.evidence import latest_reported_fy_per_to_evidence

    current = _current_record()
    v1_evidence = latest_reported_fy_per_to_evidence(
        current, source_authority_class=_AUTH, originating_source=_ORIG, delivery_provider=_DELIV
    )
    provenance_store = ProvenanceStore(tmp_path / "provenance.jsonl")
    with pytest.raises(ValueError, match="v1"):
        register_latest_reported_fy_per_upstream_provenance(
            record=current, evidence=v1_evidence, provenance_store=provenance_store
        )
