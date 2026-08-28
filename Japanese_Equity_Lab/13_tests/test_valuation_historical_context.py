"""LATEST_REPORTED_FY_PER_HISTORICAL_CONTEXT v1(Stage 3.15、D0089):
Historical PER Monthly Anchors分布をInterpretationなしのDerived Valuation
FACTとして構築できるかを検証する。

D0087(Multi-Year Price Snapshot)+ D0088(PIT Correction)で実測した
「Historical PER観測30件+Current PER観測1件」という実データ構造を、
Production Codeとして再現可能・PIT-safeに構築できることを、Synthetic
Fixtureで確認する(実データ受け入れは別途Real 7203 Acceptance Scratch
Scriptで実施、D0089参照)。
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from lib.errors import LookAheadBiasError
from lib.evidence.model import DataLayer, Frequency
from lib.market_calendar import session_close_at
from lib.registry.provenance import ProvenanceLink, ProvenanceStore
from lib.sources.catalog import DataCapability, SourceAuthorityClass
from lib.valuation.evidence import latest_reported_fy_per_evidence_id
from lib.valuation.historical_context_builder import build_latest_reported_fy_per_historical_context
from lib.valuation.historical_context_evidence import (
    latest_reported_fy_per_historical_context_to_evidence,
    verify_historical_context_provenance,
)
from lib.valuation.model import (
    MEDIAN_METHOD_ORDERED_MIDPOINT,
    MINIMUM_MONTHLY_OBSERVATIONS,
    PERCENTILE_METHOD_EMPIRICAL_CDF_LE,
    PERCENTILE_SCALE_PERCENT_0_100,
    CorporateActionBasisStatus,
    HistoricalContextStatus,
    LatestReportedFyPerRecord,
)

_JST = ZoneInfo("Asia/Tokyo")
_ENTITY = "7203"
_CURRENT_REFERENCE_AS_OF = datetime(2024, 11, 15, 15, 0, tzinfo=_JST)


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
    """3 Denominator Regime(12/12/6)、n=30の合成Historical Sample。
    実データ(D0087/D0088)の構造(FY2022/3・FY2023/3・FY2024/3)を模す。"""
    records: list[LatestReportedFyPerRecord] = []
    regime_specs = [
        (date(2022, 3, 31), Decimal("205.23"), "SV_FY2022", 12),
        (date(2023, 3, 31), Decimal("179.47"), "SV_FY2023", 12),
        (date(2024, 3, 31), Decimal("365.94"), "SV_FY2024", 6),
    ]
    month_index = 0
    for fiscal_period_end, eps_value, source_version_id, count in regime_specs:
        for i in range(count):
            year = 2022 + (month_index // 12)
            month = (month_index % 12) + 5  # 5月始まり(2022-05が最初のAnchor、D0088実測と一致)
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


def _build_context(historical_records=None, **overrides):
    current = overrides.pop("current_record", None) or _current_record()
    historical = historical_records if historical_records is not None else _thirty_historical_records()
    kwargs = {
        "entity_code": _ENTITY,
        "current_reference_as_of": _CURRENT_REFERENCE_AS_OF,
        "current_record": current,
        "historical_records": historical,
        "attempted_anchor_count": len(historical) + 9,
        "excluded_future_anchor_count": 2,
        "unavailable_denominator_count": 7,
        "corporate_action_excluded_count": 0,
        "minimum_sample_count": MINIMUM_MONTHLY_OBSERVATIONS,
    }
    kwargs.update(overrides)
    return build_latest_reported_fy_per_historical_context(**kwargs)


# --- PIT -------------------------------------------------------------------------------


def test_future_historical_observation_raises_look_ahead_bias_error() -> None:
    historical = _thirty_historical_records()
    future_anchor = _per_record(
        as_of=datetime(2024, 12, 30, 15, 30, tzinfo=_JST),  # current_referenceより後
        price_date=date(2024, 12, 30),
        price_value=Decimal("3146"),
        eps_value=Decimal("365.94"),
        fiscal_period_end=date(2024, 3, 31),
        published_at=datetime(2024, 5, 8, 13, 55, tzinfo=_JST),
        source_version_id="SV_FY2024",
    )
    with pytest.raises(LookAheadBiasError):
        _build_context(
            historical_records=[*historical, future_anchor],
            attempted_anchor_count=len(historical) + 1 + 9,
        )


def test_current_observation_id_contaminating_historical_ids_is_rejected() -> None:
    current = _current_record()
    historical = _thirty_historical_records()
    # Current PERとPrice Date/Multipleが完全一致するHistorical Anchorを混入させる
    # (evidence_idはentity_code + price_dateから決定的に導出されるため、Current自身と
    # 同じprice_dateのRecordを混ぜるとID衝突=Contaminationになる)。
    contaminated = [*historical[:-1], current]
    with pytest.raises(ValueError, match="Contamination"):
        _build_context(historical_records=contaminated, attempted_anchor_count=len(contaminated) + 9)


def test_duplicate_historical_observation_ids_are_rejected() -> None:
    historical = _thirty_historical_records()
    duplicated = [*historical, historical[0]]
    with pytest.raises(ValueError, match="重複"):
        _build_context(historical_records=duplicated, attempted_anchor_count=len(duplicated) + 9)


def test_current_record_as_of_mismatch_is_rejected() -> None:
    mismatched_current = _per_record(
        as_of=datetime(2024, 11, 15, 15, 0, tzinfo=_JST).replace(hour=14),
        price_date=date(2024, 11, 14),
        price_value=Decimal("2666"),
        eps_value=Decimal("365.94"),
        fiscal_period_end=date(2024, 3, 31),
        published_at=datetime(2024, 5, 8, 13, 55, tzinfo=_JST),
        source_version_id="SV_FY2024",
    )
    with pytest.raises(ValueError, match="Current Reference"):
        _build_context(current_record=mismatched_current)


def test_entity_code_mismatch_is_rejected() -> None:
    historical = _thirty_historical_records()
    mismatched = LatestReportedFyPerRecord(
        entity_code="9999",
        as_of=historical[0].as_of,
        price_date=historical[0].price_date,
        price_value=historical[0].price_value,
        price_available_at=historical[0].price_available_at,
        denominator_type=historical[0].denominator_type,
        eps_value=historical[0].eps_value,
        fiscal_period_end=historical[0].fiscal_period_end,
        published_at=historical[0].published_at,
        source_version_id=historical[0].source_version_id,
        consolidation_scope=historical[0].consolidation_scope,
        accounting_standard=historical[0].accounting_standard,
        calculation_expression=historical[0].calculation_expression,
        multiple=historical[0].multiple,
        corporate_action_basis_status=historical[0].corporate_action_basis_status,
    )
    with pytest.raises(ValueError, match="entity_code"):
        _build_context(historical_records=[*historical[1:], mismatched])


def test_bookkeeping_mismatch_in_attempted_anchor_count_is_rejected() -> None:
    with pytest.raises(ValueError, match="attempted_anchor_count"):
        _build_context(attempted_anchor_count=999)


# --- Statistics --------------------------------------------------------------------------


def test_sample_count_zero_returns_none() -> None:
    context = _build_context(
        historical_records=[], attempted_anchor_count=9, unavailable_denominator_count=9, excluded_future_anchor_count=0
    )
    assert context is None


def test_sample_count_below_minimum_returns_none() -> None:
    eleven = _thirty_historical_records()[:11]
    context = _build_context(historical_records=eleven, attempted_anchor_count=len(eleven) + 9)
    assert context is None


def test_sample_count_at_minimum_boundary_builds_record() -> None:
    twelve = _thirty_historical_records()[:12]
    context = _build_context(historical_records=twelve, attempted_anchor_count=len(twelve) + 9)
    assert context is not None
    assert context.sample_count == 12
    assert context.minimum_sample_count == MINIMUM_MONTHLY_OBSERVATIONS


def test_denominator_regimes_counted_correctly() -> None:
    context = _build_context()
    assert context is not None
    assert context.distinct_denominator_regime_count == 3
    counts = {r.fiscal_period_end: r.observation_count for r in context.denominator_regimes}
    assert counts[date(2022, 3, 31)] == 12
    assert counts[date(2023, 3, 31)] == 12
    assert counts[date(2024, 3, 31)] == 6


def test_regime_with_inconsistent_eps_is_rejected() -> None:
    historical = _thirty_historical_records()
    tampered = list(historical)
    tampered[0] = _per_record(
        as_of=tampered[0].as_of,
        price_date=tampered[0].price_date,
        price_value=tampered[0].price_value,
        eps_value=Decimal("999.99"),  # 同一fiscal_period_endだが値が矛盾
        fiscal_period_end=tampered[0].fiscal_period_end,
        published_at=tampered[0].published_at,
        source_version_id=tampered[0].source_version_id,
    )
    with pytest.raises(ValueError, match="Regime"):
        _build_context(historical_records=tampered)


def test_median_even_n_is_ordered_midpoint_decimal_average() -> None:
    context = _build_context()
    assert context is not None
    sorted_pers = sorted(r.multiple for r in _thirty_historical_records())
    expected_median = (sorted_pers[14] + sorted_pers[15]) / Decimal(2)
    assert context.historical_median == expected_median
    assert context.median_method == MEDIAN_METHOD_ORDERED_MIDPOINT


def test_historical_min_max_match_synthetic_sample() -> None:
    context = _build_context()
    assert context is not None
    sorted_pers = sorted(r.multiple for r in _thirty_historical_records())
    assert context.historical_min == sorted_pers[0]
    assert context.historical_max == sorted_pers[-1]


def test_percentile_definition_is_inclusive_le_and_decimal_only() -> None:
    """current_perをHistorical Sampleへ人為的にちょうど1件だけ<=になるよう仕込み、
    count(historical_per<=current_per)*100/nがそのまま返ることを確認する
    (D0088実測: sample_count=30、count=1、percentile=3.333...%)。"""
    historical = _thirty_historical_records()
    # 全Historical PERの最小値より低いCurrent PERにすると、count(<=)=0になるはず
    lowest = min(r.multiple for r in historical)
    current = _per_record(
        as_of=_CURRENT_REFERENCE_AS_OF,
        price_date=date(2024, 11, 14),
        price_value=(lowest - Decimal("1")) * Decimal("365.94"),
        eps_value=Decimal("365.94"),
        fiscal_period_end=date(2024, 3, 31),
        published_at=datetime(2024, 5, 8, 13, 55, tzinfo=_JST),
        source_version_id="SV_FY2024",
    )
    context = _build_context(current_record=current)
    assert context is not None
    assert context.current_percentile == Decimal(0)
    assert context.percentile_method == PERCENTILE_METHOD_EMPIRICAL_CDF_LE
    assert context.percentile_scale == PERCENTILE_SCALE_PERCENT_0_100
    assert isinstance(context.current_percentile, Decimal)


def test_percentile_tie_is_included_in_le_count() -> None:
    historical = _thirty_historical_records()
    tie_value = historical[0].multiple
    current = _per_record(
        as_of=_CURRENT_REFERENCE_AS_OF,
        price_date=date(2024, 11, 14),
        price_value=tie_value * Decimal("365.94"),  # ちょうど1件と同値
        eps_value=Decimal("365.94"),
        fiscal_period_end=date(2024, 3, 31),
        published_at=datetime(2024, 5, 8, 13, 55, tzinfo=_JST),
        source_version_id="SV_FY2024",
    )
    context = _build_context(current_record=current)
    assert context is not None
    count_le = sum(1 for r in historical if r.multiple <= tie_value)
    expected = Decimal(count_le) * Decimal(100) / Decimal(30)
    assert context.current_percentile == expected
    assert count_le >= 1


def test_current_minus_historical_median_is_signed_fact_only() -> None:
    context = _build_context()
    assert context is not None
    assert context.current_minus_historical_median == context.current_per - context.historical_median


def test_context_status_is_partial_for_v1() -> None:
    context = _build_context()
    assert context is not None
    assert context.context_status == HistoricalContextStatus.PARTIAL


def test_available_at_is_max_of_all_parents_and_not_after_reference() -> None:
    context = _build_context()
    assert context is not None
    assert context.available_at <= context.current_reference_as_of
    from lib.valuation.evidence import latest_reported_fy_per_available_at

    expected = max(latest_reported_fy_per_available_at(r) for r in [_current_record(), *_thirty_historical_records()])
    assert context.available_at == expected


# --- Evidence ------------------------------------------------------------------------------

_FORBIDDEN_WORDS = (
    "Cheap",
    "Expensive",
    "Undervalued",
    "Overvalued",
    "Attractive",
    "Bullish",
    "Bearish",
    "upside",
    "downside",
    "expected return",
    "BUY",
    "SELL",
    "target price",
    "割安",
    "割高",
    "買い",
    "売り",
)


def test_historical_context_evidence_type_layer_capability() -> None:
    context = _build_context()
    assert context is not None
    evidence = latest_reported_fy_per_historical_context_to_evidence(
        context,
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        originating_source="JQUANTS_SOURCE_DATA",
        delivery_provider="JQUANTS",
    )
    assert evidence.layer == DataLayer.DERIVED
    assert evidence.capability == DataCapability.VALUATION
    assert evidence.source.available_at == context.available_at
    assert evidence.source.published_at is None


def test_historical_context_evidence_has_no_interpretation_words() -> None:
    context = _build_context()
    assert context is not None
    evidence = latest_reported_fy_per_historical_context_to_evidence(
        context,
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        originating_source="JQUANTS_SOURCE_DATA",
        delivery_provider="JQUANTS",
    )
    lowered = evidence.content.lower()
    for word in _FORBIDDEN_WORDS:
        assert word.lower() not in lowered, f"禁止語 {word!r} がEvidence content に含まれています: {evidence.content!r}"


def test_historical_context_evidence_frequency_is_monthly() -> None:
    context = _build_context()
    assert context is not None
    assert context.anchor_frequency == Frequency.MONTHLY


# --- Provenance -----------------------------------------------------------------------------


def _wire_full_provenance(context, evidence_id: str, store: ProvenanceStore) -> None:
    for i, oid in enumerate(context.historical_observation_ids):
        store.add_link(
            ProvenanceLink(
                link_id=f"L_HIST_{i}",
                from_type="valuation_evidence",
                from_id=oid,
                to_type="valuation_evidence",
                to_id=evidence_id,
            )
        )
    store.add_link(
        ProvenanceLink(
            link_id="L_CURRENT",
            from_type="valuation_evidence",
            from_id=context.current_per_observation_id,
            to_type="valuation_evidence",
            to_id=evidence_id,
        )
    )


def test_provenance_has_exactly_31_direct_parents(tmp_path: Path) -> None:
    context = _build_context()
    assert context is not None
    evidence = latest_reported_fy_per_historical_context_to_evidence(
        context,
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        originating_source="JQUANTS_SOURCE_DATA",
        delivery_provider="JQUANTS",
    )
    store = ProvenanceStore(tmp_path / "provenance.jsonl")
    _wire_full_provenance(context, evidence.evidence_id, store)

    parents = store.parents_of("valuation_evidence", evidence.evidence_id)
    assert len(parents) == 31
    verify_historical_context_provenance(context, context_evidence_id=evidence.evidence_id, provenance_store=store)


def test_provenance_parents_of_returns_all_branches_unlike_trace_to_origin(tmp_path: Path) -> None:
    """`trace_to_origin()`は複数親Targetを1件へ潰す既知の制約があるため、
    `parents_of()`(Multi-Parent Retrieval Hardening)が全件返すことを直接確認する。"""
    context = _build_context()
    assert context is not None
    evidence_id = "EVID_CONTEXT_TEST"
    store = ProvenanceStore(tmp_path / "provenance.jsonl")
    _wire_full_provenance(context, evidence_id, store)

    all_parents = store.parents_of("valuation_evidence", evidence_id)
    assert len(all_parents) == 31

    traced = store.trace_to_origin("valuation_evidence", evidence_id)
    assert len(traced) <= 1  # 既存挙動: 複数親のうち最後の1件のみ(Breaking Changeなし)


def test_missing_parent_link_is_rejected(tmp_path: Path) -> None:
    context = _build_context()
    assert context is not None
    evidence_id = "EVID_CONTEXT_TEST_MISSING"
    store = ProvenanceStore(tmp_path / "provenance.jsonl")
    # 30件のHistoricalのうち1件だけ登録を忘れる + Currentのみ登録(31件揃わない)
    for i, oid in enumerate(context.historical_observation_ids[:-1]):
        store.add_link(
            ProvenanceLink(
                link_id=f"L_{i}",
                from_type="valuation_evidence",
                from_id=oid,
                to_type="valuation_evidence",
                to_id=evidence_id,
            )
        )
    store.add_link(
        ProvenanceLink(
            link_id="L_CURRENT",
            from_type="valuation_evidence",
            from_id=context.current_per_observation_id,
            to_type="valuation_evidence",
            to_id=evidence_id,
        )
    )
    with pytest.raises(ValueError, match="missing"):
        verify_historical_context_provenance(context, context_evidence_id=evidence_id, provenance_store=store)


def test_dangling_unexpected_parent_link_is_rejected(tmp_path: Path) -> None:
    context = _build_context()
    assert context is not None
    evidence_id = "EVID_CONTEXT_TEST_DANGLING"
    store = ProvenanceStore(tmp_path / "provenance.jsonl")
    _wire_full_provenance(context, evidence_id, store)
    # Fake Lineage: Recordが知らないIDを追加登録
    store.add_link(
        ProvenanceLink(
            link_id="L_FAKE",
            from_type="valuation_evidence",
            from_id="EVID_LATEST_REPORTED_FY_PER_7203_1999-01-01",
            to_type="valuation_evidence",
            to_id=evidence_id,
        )
    )
    with pytest.raises(ValueError, match="unexpected"):
        verify_historical_context_provenance(context, context_evidence_id=evidence_id, provenance_store=store)


def test_duplicate_registered_parent_link_is_rejected(tmp_path: Path) -> None:
    context = _build_context()
    assert context is not None
    evidence_id = "EVID_CONTEXT_TEST_DUP"
    store = ProvenanceStore(tmp_path / "provenance.jsonl")
    _wire_full_provenance(context, evidence_id, store)
    store.add_link(
        ProvenanceLink(
            link_id="L_DUP",
            from_type="valuation_evidence",
            from_id=context.historical_observation_ids[0],
            to_type="valuation_evidence",
            to_id=evidence_id,
        )
    )
    with pytest.raises(ValueError, match="重複"):
        verify_historical_context_provenance(context, context_evidence_id=evidence_id, provenance_store=store)


def test_each_historical_observation_id_matches_evidence_id_format() -> None:
    """Historical Observation IDが`latest_reported_fy_per_evidence_id()`と同一Formatで
    あることを確認する(D0077既存PER Evidenceとして独立にlineageを追跡可能な形式)。"""
    context = _build_context()
    assert context is not None
    historical = _thirty_historical_records()
    expected_ids = {latest_reported_fy_per_evidence_id(r) for r in historical}
    assert set(context.historical_observation_ids) == expected_ids
