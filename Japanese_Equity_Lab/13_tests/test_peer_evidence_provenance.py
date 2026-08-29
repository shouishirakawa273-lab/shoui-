"""`lib.peer.evidence` / `lib.peer.provenance`(Stage 3.17、D0095): Peer
Context EvidenceのIdentity・Content・Provenance DAGをFresh-Process
Reload込みで検証する。

D0094の教訓(「77 Evidence ≠ 77 independent confirmations」)を踏まえ、
Peer Comparisonは常に1件の集約Evidenceとして表現し、Provenanceで個々の
Peer Metric Observationとのlineageを検証可能にする(要件v1 §3/§4)。
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from lib.evidence.model import DataLayer, EvidenceType
from lib.market_calendar import session_close_at
from lib.peer.builder import (
    build_peer_aggregate_context,
    build_peer_comparison_record,
    latest_reported_fy_per_record_to_peer_observation,
)
from lib.peer.evidence import (
    peer_valuation_context_evidence_id,
    peer_valuation_context_to_evidence,
    verify_peer_context_provenance,
)
from lib.peer.model import AcceptedPeer, PeerMetricType
from lib.peer.provenance import register_peer_context_provenance_bundle
from lib.registry.evidence_registry import EvidenceRegistry
from lib.registry.provenance import ProvenanceStore
from lib.sources.catalog import DataCapability, SourceAuthorityClass
from lib.valuation.evidence import latest_reported_fy_per_to_evidence_v2
from lib.valuation.model import CorporateActionBasisStatus, LatestReportedFyPerRecord

_JST = ZoneInfo("Asia/Tokyo")
_AS_OF = datetime(2024, 11, 15, 15, 0, tzinfo=_JST)
_AUTH = SourceAuthorityClass.PRIMARY_OFFICIAL
_ORIG = "JQUANTS_SOURCE_DATA"
_DELIV = "JQUANTS"


def _accepted_peer(entity_code: str, *, as_of: datetime = _AS_OF) -> AcceptedPeer:
    return AcceptedPeer(entity_code=entity_code, classification_system="TSE_SECTOR_33", classification_code="3700", as_of=as_of)


def _per_record(entity_code: str, *, multiple: Decimal, source_version_id: str) -> LatestReportedFyPerRecord:
    price_date = date(2024, 11, 14)
    eps_value = Decimal("100")
    price_value = multiple * eps_value
    return LatestReportedFyPerRecord(
        entity_code=entity_code,
        as_of=_AS_OF,
        price_date=price_date,
        price_value=price_value,
        price_available_at=session_close_at(price_date),
        denominator_type="FY_ACTUAL_EPS_CONSOLIDATED",
        eps_value=eps_value,
        fiscal_period_end=date(2024, 3, 31),
        published_at=datetime(2024, 5, 8, 13, 55, tzinfo=_JST),
        source_version_id=source_version_id,
        consolidation_scope="CONSOLIDATED",
        accounting_standard="IFRS",
        calculation_expression=f"price_close={price_value} / fy_actual_eps={eps_value}",
        multiple=multiple,
        corporate_action_basis_status=CorporateActionBasisStatus.CONFIRMED_NO_ACTION,
    )


def _register_entity(entity_code: str, multiple: Decimal, registry: EvidenceRegistry):
    record = _per_record(entity_code, multiple=multiple, source_version_id=f"SV_{entity_code}")
    evidence = latest_reported_fy_per_to_evidence_v2(
        record, source_authority_class=_AUTH, originating_source=_ORIG, delivery_provider=_DELIV
    )
    registry.register(evidence)
    observation = latest_reported_fy_per_record_to_peer_observation(record, evidence=evidence, as_of=_AS_OF)
    return record, evidence, observation


def _build_full_context(registry: EvidenceRegistry):
    _t_rec, _t_ev, target_obs = _register_entity("7203", Decimal("10"), registry)
    peer_recs = {}
    comparison_records = []
    for code, multiple in (("2001", Decimal("7")), ("2002", Decimal("8")), ("2003", Decimal("9"))):
        rec, _ev, obs = _register_entity(code, multiple, registry)
        peer_recs[code] = rec
        comparison_records.append(
            build_peer_comparison_record(
                target_entity_code="7203",
                accepted_peer=_accepted_peer(code),
                metric_type=PeerMetricType.LATEST_REPORTED_FY_PER,
                comparison_as_of=_AS_OF,
                target_observation=target_obs,
                peer_observation=obs,
            )
        )
    context = build_peer_aggregate_context(
        target_entity_code="7203",
        metric_type=PeerMetricType.LATEST_REPORTED_FY_PER,
        as_of=_AS_OF,
        target_observation=target_obs,
        comparison_records=comparison_records,
    )
    assert context is not None
    return context, peer_recs


# --- Evidence Identity / Content -----------------------------------------------


def test_evidence_id_is_deterministic_for_same_inputs(tmp_path: Path) -> None:
    registry_a = EvidenceRegistry(tmp_path / "a.jsonl")
    ctx_a, _ = _build_full_context(registry_a)
    registry_b = EvidenceRegistry(tmp_path / "b.jsonl")
    ctx_b, _ = _build_full_context(registry_b)
    assert peer_valuation_context_evidence_id(ctx_a) == peer_valuation_context_evidence_id(ctx_b)


def test_evidence_id_changes_when_peer_set_changes(tmp_path: Path) -> None:
    registry = EvidenceRegistry(tmp_path / "reg.jsonl")
    ctx_full, _ = _build_full_context(registry)

    reg2 = EvidenceRegistry(tmp_path / "reg2.jsonl")
    _t_rec2, _t_ev2, target_obs2 = _register_entity("7203", Decimal("10"), reg2)
    comparisons = []
    for code, multiple in (("2001", Decimal("7")), ("2002", Decimal("8")), ("3999", Decimal("9"))):  # different 3rd peer
        rec, _ev, obs = _register_entity(code, multiple, reg2)
        comparisons.append(
            build_peer_comparison_record(
                target_entity_code="7203",
                accepted_peer=_accepted_peer(code),
                metric_type=PeerMetricType.LATEST_REPORTED_FY_PER,
                comparison_as_of=_AS_OF,
                target_observation=target_obs2,
                peer_observation=obs,
            )
        )
    ctx_diff = build_peer_aggregate_context(
        target_entity_code="7203",
        metric_type=PeerMetricType.LATEST_REPORTED_FY_PER,
        as_of=_AS_OF,
        target_observation=target_obs2,
        comparison_records=comparisons,
    )
    assert ctx_diff is not None
    assert peer_valuation_context_evidence_id(ctx_full) != peer_valuation_context_evidence_id(ctx_diff)


def test_evidence_content_has_no_interpretive_words(tmp_path: Path) -> None:
    registry = EvidenceRegistry(tmp_path / "reg.jsonl")
    ctx, _ = _build_full_context(registry)
    evidence = peer_valuation_context_to_evidence(
        ctx, source_authority_class=_AUTH, originating_source=_ORIG, delivery_provider=_DELIV
    )
    forbidden = ["cheap", "expensive", "undervalued", "overvalued", "attractive", "BUY", "SELL", "rerating"]
    lowered = evidence.content.lower()
    for word in forbidden:
        assert word.lower() not in lowered, f"Forbidden interpretive word found: {word}"


def test_evidence_uses_peer_comparison_capability(tmp_path: Path) -> None:
    registry = EvidenceRegistry(tmp_path / "reg.jsonl")
    ctx, _ = _build_full_context(registry)
    evidence = peer_valuation_context_to_evidence(
        ctx, source_authority_class=_AUTH, originating_source=_ORIG, delivery_provider=_DELIV
    )
    assert evidence.capability == DataCapability.PEER_COMPARISON
    assert evidence.layer == DataLayer.DERIVED
    assert evidence.evidence_type == EvidenceType.FACT
    assert set(evidence.related_codes) == {"7203", "2001", "2002", "2003"}


# --- Provenance / Fresh-Process Reload ------------------------------------------


def test_provenance_bundle_and_fresh_process_reload(tmp_path: Path) -> None:
    evidence_path = tmp_path / "evidence_registry.jsonl"
    provenance_path = tmp_path / "provenance.jsonl"

    registry = EvidenceRegistry(evidence_path)
    ctx, peer_recs = _build_full_context(registry)
    context_evidence = peer_valuation_context_to_evidence(
        ctx, source_authority_class=_AUTH, originating_source=_ORIG, delivery_provider=_DELIV
    )
    registry.register(context_evidence)

    provenance_store = ProvenanceStore(provenance_path)
    target_record = _per_record("7203", multiple=Decimal("10"), source_version_id="SV_7203")
    records_by_entity = {"7203": target_record, **peer_recs}
    register_peer_context_provenance_bundle(
        context_record=ctx,
        context_evidence=context_evidence,
        evidence_registry=registry,
        provenance_store=provenance_store,
        latest_reported_fy_per_records_by_entity=records_by_entity,
    )

    # Fresh-process equivalent: brand-new Registry/Store instances pointed at the same files.
    fresh_registry = EvidenceRegistry(evidence_path)
    fresh_store = ProvenanceStore(provenance_path)

    reloaded_context_evidence = fresh_registry.require(context_evidence.evidence_id)
    assert reloaded_context_evidence.evidence_id == context_evidence.evidence_id

    reloaded_target = fresh_registry.require(ctx.target_observation_evidence_id)
    assert reloaded_target.related_codes == ("7203",)
    for peer_evidence_id in ctx.included_peer_observation_evidence_ids:
        assert fresh_registry.get(peer_evidence_id) is not None

    # Context -> Observation provenance resolves after reload.
    verify_peer_context_provenance(
        ctx, context_evidence_id=context_evidence.evidence_id, provenance_store=fresh_store, evidence_registry=fresh_registry
    )

    # Observation -> upstream Price/EPS provenance resolves after reload (LATEST_REPORTED_FY_PER only).
    parents = fresh_store.parents_of("valuation_evidence", ctx.target_observation_evidence_id)
    parent_types = {p.from_type for p in parents}
    assert "price_bar" in parent_types
    assert "fundamental_source_version" in parent_types


def test_target_observation_included_as_provenance_parent(tmp_path: Path) -> None:
    evidence_path = tmp_path / "evidence_registry.jsonl"
    provenance_path = tmp_path / "provenance.jsonl"
    registry = EvidenceRegistry(evidence_path)
    ctx, peer_recs = _build_full_context(registry)
    context_evidence = peer_valuation_context_to_evidence(
        ctx, source_authority_class=_AUTH, originating_source=_ORIG, delivery_provider=_DELIV
    )
    registry.register(context_evidence)
    provenance_store = ProvenanceStore(provenance_path)
    register_peer_context_provenance_bundle(
        context_record=ctx, context_evidence=context_evidence, evidence_registry=registry, provenance_store=provenance_store
    )
    parents = provenance_store.parents_of("valuation_evidence", context_evidence.evidence_id)
    parent_ids = {p.from_id for p in parents}
    assert ctx.target_observation_evidence_id in parent_ids
    for peer_evidence_id in ctx.included_peer_observation_evidence_ids:
        assert peer_evidence_id in parent_ids


def test_excluded_peer_not_a_provenance_parent(tmp_path: Path) -> None:
    from lib.peer.builder import missing_peer_metric_observation

    evidence_path = tmp_path / "evidence_registry.jsonl"
    provenance_path = tmp_path / "provenance.jsonl"
    registry = EvidenceRegistry(evidence_path)

    _t_rec, _t_ev, target_obs = _register_entity("7203", Decimal("10"), registry)
    comparisons = []
    for code, multiple in (("2001", Decimal("7")), ("2002", Decimal("8")), ("2003", Decimal("9"))):
        rec, _ev, obs = _register_entity(code, multiple, registry)
        comparisons.append(
            build_peer_comparison_record(
                target_entity_code="7203",
                accepted_peer=_accepted_peer(code),
                metric_type=PeerMetricType.LATEST_REPORTED_FY_PER,
                comparison_as_of=_AS_OF,
                target_observation=target_obs,
                peer_observation=obs,
            )
        )
    # A 4th peer WITH resolvable Evidence, but excluded because its metric is missing.
    excluded_rec, excluded_evidence, _unused_obs = _register_entity("4999", Decimal("11"), registry)
    excluded_missing_obs = missing_peer_metric_observation(
        entity_code="4999", metric_type=PeerMetricType.LATEST_REPORTED_FY_PER, as_of=_AS_OF
    )
    excluded_comparison = build_peer_comparison_record(
        target_entity_code="7203",
        accepted_peer=_accepted_peer("4999"),
        metric_type=PeerMetricType.LATEST_REPORTED_FY_PER,
        comparison_as_of=_AS_OF,
        target_observation=target_obs,
        peer_observation=excluded_missing_obs,
    )
    comparisons.append(excluded_comparison)

    ctx = build_peer_aggregate_context(
        target_entity_code="7203",
        metric_type=PeerMetricType.LATEST_REPORTED_FY_PER,
        as_of=_AS_OF,
        target_observation=target_obs,
        comparison_records=comparisons,
    )
    assert ctx is not None
    assert ctx.excluded_peer_entity_codes == ("4999",)
    assert excluded_evidence.evidence_id not in ctx.included_peer_observation_evidence_ids

    context_evidence = peer_valuation_context_to_evidence(
        ctx, source_authority_class=_AUTH, originating_source=_ORIG, delivery_provider=_DELIV
    )
    registry.register(context_evidence)
    provenance_store = ProvenanceStore(provenance_path)
    register_peer_context_provenance_bundle(
        context_record=ctx, context_evidence=context_evidence, evidence_registry=registry, provenance_store=provenance_store
    )
    parents = provenance_store.parents_of("valuation_evidence", context_evidence.evidence_id)
    parent_ids = {p.from_id for p in parents}
    assert excluded_evidence.evidence_id not in parent_ids


# --- D0096 Finding 4: Full Timestamp Evidence Identity (regressions I, J) ------


def _register_entity_at(entity_code: str, multiple: Decimal, registry: EvidenceRegistry, *, as_of: datetime):
    record = _per_record(entity_code, multiple=multiple, source_version_id=f"SV_{entity_code}")
    evidence = latest_reported_fy_per_to_evidence_v2(
        record, source_authority_class=_AUTH, originating_source=_ORIG, delivery_provider=_DELIV
    )
    registry.register(evidence)
    observation = latest_reported_fy_per_record_to_peer_observation(record, evidence=evidence, as_of=as_of)
    return record, evidence, observation


def _build_full_context_at(registry: EvidenceRegistry, *, as_of: datetime):
    _t_rec, _t_ev, target_obs = _register_entity_at("7203", Decimal("10"), registry, as_of=as_of)
    comparison_records = []
    for code, multiple in (("2001", Decimal("7")), ("2002", Decimal("8")), ("2003", Decimal("9"))):
        _rec, _ev, obs = _register_entity_at(code, multiple, registry, as_of=as_of)
        comparison_records.append(
            build_peer_comparison_record(
                target_entity_code="7203",
                accepted_peer=_accepted_peer(code, as_of=as_of),
                metric_type=PeerMetricType.LATEST_REPORTED_FY_PER,
                comparison_as_of=as_of,
                target_observation=target_obs,
                peer_observation=obs,
            )
        )
    context = build_peer_aggregate_context(
        target_entity_code="7203",
        metric_type=PeerMetricType.LATEST_REPORTED_FY_PER,
        as_of=as_of,
        target_observation=target_obs,
        comparison_records=comparison_records,
    )
    assert context is not None
    return context


def test_regression_i_same_day_different_timestamp_ids_differ(tmp_path: Path) -> None:
    """要件v1 §16-I: 同日でも時刻が異なればPeer Context Evidence IDが
    異なる(以前は`as_of.date()`のみで日付が同じなら衝突していた)。"""
    morning = datetime(2024, 11, 15, 10, 0, tzinfo=_JST)
    afternoon = datetime(2024, 11, 15, 15, 0, tzinfo=_JST)
    ctx_morning = _build_full_context_at(EvidenceRegistry(tmp_path / "morning.jsonl"), as_of=morning)
    ctx_afternoon = _build_full_context_at(EvidenceRegistry(tmp_path / "afternoon.jsonl"), as_of=afternoon)
    assert peer_valuation_context_evidence_id(ctx_morning) != peer_valuation_context_evidence_id(ctx_afternoon)


def test_regression_j_same_instant_different_tz_offset_same_id(tmp_path: Path) -> None:
    """要件v1 §16-J: 同一Instantを指す異なるTimezone Offset表記の
    as_ofは、Canonical UTC Normalizeにより同一Evidence IDになる。"""
    jst_repr = datetime(2024, 11, 15, 15, 0, tzinfo=_JST)
    utc_repr = jst_repr.astimezone(UTC)
    assert jst_repr == utc_repr  # same instant, different tzinfo object
    ctx_jst = _build_full_context_at(EvidenceRegistry(tmp_path / "jst.jsonl"), as_of=jst_repr)
    ctx_utc = _build_full_context_at(EvidenceRegistry(tmp_path / "utc.jsonl"), as_of=utc_repr)
    assert peer_valuation_context_evidence_id(ctx_jst) == peer_valuation_context_evidence_id(ctx_utc)


# --- D0096 Finding 6: Validate Optional Upstream Mapping Before Write (L, M) ---


def test_regression_l_extra_entity_in_upstream_mapping_raises_before_write(tmp_path: Path) -> None:
    """要件v1 §16-L: `latest_reported_fy_per_records_by_entity`に
    Context外の余分なEntityが含まれる場合、Context->Observation第1階層
    Linkすら1件も書き込まれる前にfail closedする。"""
    evidence_path = tmp_path / "evidence_registry.jsonl"
    provenance_path = tmp_path / "provenance.jsonl"
    registry = EvidenceRegistry(evidence_path)
    ctx, peer_recs = _build_full_context(registry)
    context_evidence = peer_valuation_context_to_evidence(
        ctx, source_authority_class=_AUTH, originating_source=_ORIG, delivery_provider=_DELIV
    )
    registry.register(context_evidence)
    provenance_store = ProvenanceStore(provenance_path)

    target_record = _per_record("7203", multiple=Decimal("10"), source_version_id="SV_7203")
    extra_record = _per_record("9999", multiple=Decimal("5"), source_version_id="SV_9999")  # not a target/included peer
    records_by_entity = {"7203": target_record, **peer_recs, "9999": extra_record}

    with pytest.raises(ValueError, match="余分なEntity"):
        register_peer_context_provenance_bundle(
            context_record=ctx,
            context_evidence=context_evidence,
            evidence_registry=registry,
            provenance_store=provenance_store,
            latest_reported_fy_per_records_by_entity=records_by_entity,
        )
    # No first-tier Context -> Observation link was written despite the failure.
    assert provenance_store.parents_of("valuation_evidence", context_evidence.evidence_id) == []


def test_regression_m_mismatched_record_entity_in_upstream_mapping_raises_before_write(tmp_path: Path) -> None:
    """要件v1 §16-M: `latest_reported_fy_per_records_by_entity`のMapping
    KeyとRecord.entity_codeが食い違う場合も、第1階層Write前にfail closed
    する。"""
    evidence_path = tmp_path / "evidence_registry.jsonl"
    provenance_path = tmp_path / "provenance.jsonl"
    registry = EvidenceRegistry(evidence_path)
    ctx, peer_recs = _build_full_context(registry)
    context_evidence = peer_valuation_context_to_evidence(
        ctx, source_authority_class=_AUTH, originating_source=_ORIG, delivery_provider=_DELIV
    )
    registry.register(context_evidence)
    provenance_store = ProvenanceStore(provenance_path)

    target_record = _per_record("7203", multiple=Decimal("10"), source_version_id="SV_7203")
    # Mapping key "2001" but the record itself claims entity_code "2002" (mismatch).
    mismatched_record = _per_record("2002", multiple=Decimal("7"), source_version_id="SV_MISMATCH")
    records_by_entity = {"7203": target_record, "2001": mismatched_record, "2002": peer_recs["2002"], "2003": peer_recs["2003"]}

    with pytest.raises(ValueError, match="Mapping Key"):
        register_peer_context_provenance_bundle(
            context_record=ctx,
            context_evidence=context_evidence,
            evidence_registry=registry,
            provenance_store=provenance_store,
            latest_reported_fy_per_records_by_entity=records_by_entity,
        )
    assert provenance_store.parents_of("valuation_evidence", context_evidence.evidence_id) == []


def test_regression_n_all_included_peer_upstream_lineage_reloadable(tmp_path: Path) -> None:
    """要件v1 §16-N: Targetだけでなく、Includeされた全PeerについてもFresh
    Reload後にPrice/EPS Upstream Lineageが解決できる。"""
    evidence_path = tmp_path / "evidence_registry.jsonl"
    provenance_path = tmp_path / "provenance.jsonl"
    registry = EvidenceRegistry(evidence_path)
    ctx, peer_recs = _build_full_context(registry)
    context_evidence = peer_valuation_context_to_evidence(
        ctx, source_authority_class=_AUTH, originating_source=_ORIG, delivery_provider=_DELIV
    )
    registry.register(context_evidence)
    provenance_store = ProvenanceStore(provenance_path)
    target_record = _per_record("7203", multiple=Decimal("10"), source_version_id="SV_7203")
    records_by_entity = {"7203": target_record, **peer_recs}
    register_peer_context_provenance_bundle(
        context_record=ctx,
        context_evidence=context_evidence,
        evidence_registry=registry,
        provenance_store=provenance_store,
        latest_reported_fy_per_records_by_entity=records_by_entity,
    )

    fresh_store = ProvenanceStore(provenance_path)
    for peer_evidence_id in ctx.included_peer_observation_evidence_ids:
        parents = fresh_store.parents_of("valuation_evidence", peer_evidence_id)
        parent_types = {p.from_type for p in parents}
        assert "price_bar" in parent_types
        assert "fundamental_source_version" in parent_types
