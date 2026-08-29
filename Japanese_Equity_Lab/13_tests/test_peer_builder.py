"""`lib.peer.builder`(Stage 3.17、D0095): Observation変換Adapter・
Comparison Record・Aggregate Contextの数値契約を検証する。

`MINIMUM_PEER_SAMPLE_COUNT = 3`のSample Sufficiency Policyと、Historical
Valuation Contextと同じ統計定義(Empirical CDF Percentile・Ordered
Midpoint Median)を実際の数値で確認する。既存Production Builder
(`lib.valuation.builder.build_latest_reported_fy_per()`等)は直接呼ばず、
`13_tests/test_valuation_historical_context.py`と同じ「Recordを直接
構築する」パターンを踏襲する(Peer固有のLogicの検証に集中するため)。
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from lib.market_calendar import session_close_at
from lib.peer.builder import (
    build_peer_aggregate_context,
    build_peer_comparison_record,
    current_fy_company_forecast_per_record_to_peer_observation,
    latest_reported_fy_per_record_to_peer_observation,
    missing_peer_metric_observation,
)
from lib.peer.model import (
    MINIMUM_PEER_SAMPLE_COUNT,
    AcceptedPeer,
    PeerComparisonRecord,
    PeerExclusionReason,
    PeerMetricAvailability,
    PeerMetricObservation,
    PeerMetricType,
)
from lib.sources.catalog import SourceAuthorityClass
from lib.valuation.evidence import current_fy_company_forecast_per_to_evidence, latest_reported_fy_per_to_evidence_v2
from lib.valuation.model import CorporateActionBasisStatus, CurrentFyCompanyForecastPerRecord, LatestReportedFyPerRecord

_JST = ZoneInfo("Asia/Tokyo")
_AS_OF = datetime(2024, 11, 15, 15, 0, tzinfo=_JST)


def _accepted_peer(entity_code: str, *, as_of: datetime = _AS_OF, classification_code: str = "3700") -> AcceptedPeer:
    return AcceptedPeer(
        entity_code=entity_code, classification_system="TSE_SECTOR_33", classification_code=classification_code, as_of=as_of
    )


def _per_record(
    entity_code: str, *, price_value: Decimal, eps_value: Decimal, source_version_id: str
) -> LatestReportedFyPerRecord:
    price_date = date(2024, 11, 14)
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
        multiple=price_value / eps_value,
        corporate_action_basis_status=CorporateActionBasisStatus.CONFIRMED_NO_ACTION,
    )


def _per_observation(entity_code: str, *, multiple: Decimal, source_version_id: str) -> PeerMetricObservation:
    eps_value = Decimal("100")
    price_value = multiple * eps_value
    record = _per_record(entity_code, price_value=price_value, eps_value=eps_value, source_version_id=source_version_id)
    evidence = latest_reported_fy_per_to_evidence_v2(
        record,
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        originating_source="JQUANTS_SOURCE_DATA",
        delivery_provider="JQUANTS",
    )
    return latest_reported_fy_per_record_to_peer_observation(record, evidence=evidence, as_of=_AS_OF)


# --- Adapters -----------------------------------------------------------------


def test_latest_reported_fy_per_adapter_produces_available_observation() -> None:
    obs = _per_observation("7203", multiple=Decimal("10"), source_version_id="SV_TARGET")
    assert obs.availability == PeerMetricAvailability.AVAILABLE
    assert obs.value == Decimal("10")
    assert obs.metric_type == PeerMetricType.LATEST_REPORTED_FY_PER
    assert obs.source_evidence_id is not None


def test_latest_reported_fy_per_adapter_rejects_mismatched_evidence() -> None:
    record = _per_record("7203", price_value=Decimal("1000"), eps_value=Decimal("100"), source_version_id="SV_A")
    wrong_evidence = latest_reported_fy_per_to_evidence_v2(
        _per_record("9999", price_value=Decimal("1000"), eps_value=Decimal("100"), source_version_id="SV_A"),
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        originating_source="JQUANTS_SOURCE_DATA",
        delivery_provider="JQUANTS",
    )
    with pytest.raises(ValueError, match="対応していません"):
        latest_reported_fy_per_record_to_peer_observation(record, evidence=wrong_evidence, as_of=_AS_OF)


def test_current_fy_company_forecast_per_adapter_produces_available_observation() -> None:
    record = CurrentFyCompanyForecastPerRecord(
        entity_code="7203",
        as_of=_AS_OF,
        price_date=date(2024, 11, 14),
        price_value=Decimal("2500"),
        price_available_at=session_close_at(date(2024, 11, 14)),
        denominator_type="CURRENT_FY_COMPANY_FORECAST_EPS_CONSOLIDATED",
        eps_value=Decimal("250"),
        forecast_period_start=date(2024, 4, 1),
        forecast_period_end=date(2025, 3, 31),
        guidance_published_at=datetime(2024, 11, 6, 15, 30, tzinfo=_JST),
        source_version_id="SV_FORECAST",
        source_field="FEPS",
        fiscal_year_target="NEXT",
        disclosure_period_type="2Q",
        consolidation_scope="CONSOLIDATED",
        accounting_standard="IFRS",
        calculation_expression="price_close=2500 / forecast_eps=250",
        multiple=Decimal("10"),
        corporate_action_basis_status=CorporateActionBasisStatus.CONFIRMED_NO_ACTION,
    )
    evidence = current_fy_company_forecast_per_to_evidence(
        record,
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        originating_source="JQUANTS_SOURCE_DATA",
        delivery_provider="JQUANTS",
    )
    obs = current_fy_company_forecast_per_record_to_peer_observation(record, evidence=evidence, as_of=_AS_OF)
    assert obs.metric_type == PeerMetricType.CURRENT_FY_COMPANY_FORECAST_PER
    assert obs.fiscal_period_end == date(2025, 3, 31)


def test_missing_observation_rejects_available() -> None:
    with pytest.raises(ValueError, match="AVAILABLE以外"):
        missing_peer_metric_observation(
            entity_code="7267",
            metric_type=PeerMetricType.LATEST_REPORTED_FY_PER,
            as_of=_AS_OF,
            availability=PeerMetricAvailability.AVAILABLE,
        )


def test_missing_observation_is_not_zero() -> None:
    obs = missing_peer_metric_observation(entity_code="7267", metric_type=PeerMetricType.LATEST_REPORTED_FY_PER, as_of=_AS_OF)
    assert obs.value is None
    assert obs.availability == PeerMetricAvailability.MISSING


# --- Comparison Record ---------------------------------------------------------


def test_comparison_record_metric_unavailable_when_peer_missing() -> None:
    target_obs = _per_observation("7203", multiple=Decimal("10"), source_version_id="SV_T")
    peer_missing = missing_peer_metric_observation(
        entity_code="7267", metric_type=PeerMetricType.LATEST_REPORTED_FY_PER, as_of=_AS_OF
    )
    record = build_peer_comparison_record(
        target_entity_code="7203",
        accepted_peer=_accepted_peer("7267"),
        metric_type=PeerMetricType.LATEST_REPORTED_FY_PER,
        comparison_as_of=_AS_OF,
        target_observation=target_obs,
        peer_observation=peer_missing,
    )
    assert record.exclusion_reasons == (PeerExclusionReason.METRIC_UNAVAILABLE,)
    assert record.difference is None


def test_comparison_record_computes_difference_when_comparable() -> None:
    target_obs = _per_observation("7203", multiple=Decimal("10"), source_version_id="SV_T")
    peer_obs = _per_observation("7267", multiple=Decimal("8"), source_version_id="SV_P")
    record = build_peer_comparison_record(
        target_entity_code="7203",
        accepted_peer=_accepted_peer("7267"),
        metric_type=PeerMetricType.LATEST_REPORTED_FY_PER,
        comparison_as_of=_AS_OF,
        target_observation=target_obs,
        peer_observation=peer_obs,
    )
    assert record.exclusion_reasons == ()
    assert record.difference == Decimal("2")


# --- Aggregate Context ----------------------------------------------------------


def _comparison(peer_code: str, multiple: Decimal, target_obs: PeerMetricObservation) -> PeerComparisonRecord:
    peer_obs = _per_observation(peer_code, multiple=multiple, source_version_id=f"SV_{peer_code}")
    return build_peer_comparison_record(
        target_entity_code="7203",
        accepted_peer=_accepted_peer(peer_code),
        metric_type=PeerMetricType.LATEST_REPORTED_FY_PER,
        comparison_as_of=_AS_OF,
        target_observation=target_obs,
        peer_observation=peer_obs,
    )


def test_minimum_sample_count_is_3() -> None:
    assert MINIMUM_PEER_SAMPLE_COUNT == 3


def test_two_valid_peers_yields_no_aggregate() -> None:
    target_obs = _per_observation("7203", multiple=Decimal("10"), source_version_id="SV_T")
    records = [
        _comparison("2001", Decimal("7"), target_obs),
        _comparison("2002", Decimal("9"), target_obs),
    ]
    ctx = build_peer_aggregate_context(
        target_entity_code="7203",
        metric_type=PeerMetricType.LATEST_REPORTED_FY_PER,
        as_of=_AS_OF,
        target_observation=target_obs,
        comparison_records=records,
    )
    assert ctx is None


def test_three_valid_peers_yields_aggregate_with_exact_statistics() -> None:
    target_obs = _per_observation("7203", multiple=Decimal("10"), source_version_id="SV_T")
    records = [
        _comparison("2003", Decimal("9"), target_obs),
        _comparison("2001", Decimal("7"), target_obs),
        _comparison("2002", Decimal("8"), target_obs),
    ]
    ctx = build_peer_aggregate_context(
        target_entity_code="7203",
        metric_type=PeerMetricType.LATEST_REPORTED_FY_PER,
        as_of=_AS_OF,
        target_observation=target_obs,
        comparison_records=records,
    )
    assert ctx is not None
    assert ctx.peer_count == 3
    assert ctx.peer_min == Decimal("7")
    assert ctx.peer_median == Decimal("8")
    assert ctx.peer_max == Decimal("9")
    # Target(10) > all 3 peers -> percentile = 3/3*100 = 100.
    assert ctx.target_percentile == Decimal("100")
    assert ctx.included_peer_entity_codes == ("2001", "2002", "2003")  # deterministic entity-code order


def test_excluded_peer_not_counted_toward_sample() -> None:
    target_obs = _per_observation("7203", multiple=Decimal("10"), source_version_id="SV_T")
    peer_missing = missing_peer_metric_observation(
        entity_code="2004", metric_type=PeerMetricType.LATEST_REPORTED_FY_PER, as_of=_AS_OF
    )
    excluded_record = build_peer_comparison_record(
        target_entity_code="7203",
        accepted_peer=_accepted_peer("2004"),
        metric_type=PeerMetricType.LATEST_REPORTED_FY_PER,
        comparison_as_of=_AS_OF,
        target_observation=target_obs,
        peer_observation=peer_missing,
    )
    records = [
        _comparison("2001", Decimal("7"), target_obs),
        _comparison("2002", Decimal("8"), target_obs),
        _comparison("2003", Decimal("9"), target_obs),
        excluded_record,
    ]
    ctx = build_peer_aggregate_context(
        target_entity_code="7203",
        metric_type=PeerMetricType.LATEST_REPORTED_FY_PER,
        as_of=_AS_OF,
        target_observation=target_obs,
        comparison_records=records,
    )
    assert ctx is not None
    assert ctx.peer_count == 3
    assert "2004" not in ctx.included_peer_entity_codes
    assert ctx.excluded_peer_entity_codes == ("2004",)


def test_median_of_even_sample_uses_ordered_midpoint() -> None:
    target_obs = _per_observation("7203", multiple=Decimal("10"), source_version_id="SV_T")
    records = [
        _comparison("2001", Decimal("6"), target_obs),
        _comparison("2002", Decimal("7"), target_obs),
        _comparison("2003", Decimal("9"), target_obs),
        _comparison("2004", Decimal("10"), target_obs),
    ]
    ctx = build_peer_aggregate_context(
        target_entity_code="7203",
        metric_type=PeerMetricType.LATEST_REPORTED_FY_PER,
        as_of=_AS_OF,
        target_observation=target_obs,
        comparison_records=records,
    )
    assert ctx is not None
    # sorted = [6, 7, 9, 10] -> midpoint average of 7 and 9 = 8.
    assert ctx.peer_median == Decimal("8")


def test_target_unavailable_yields_no_aggregate() -> None:
    target_missing = missing_peer_metric_observation(
        entity_code="7203", metric_type=PeerMetricType.LATEST_REPORTED_FY_PER, as_of=_AS_OF
    )
    ctx = build_peer_aggregate_context(
        target_entity_code="7203",
        metric_type=PeerMetricType.LATEST_REPORTED_FY_PER,
        as_of=_AS_OF,
        target_observation=target_missing,
        comparison_records=[],
    )
    assert ctx is None


# --- D0096 Finding 1: AcceptedPeer Contract Enforcement (regressions A-D) ------


def test_regression_a_comparison_builder_requires_accepted_peer_keyword() -> None:
    """要件v1 §16-A: `build_peer_comparison_record()`はもはや生の
    `peer_entity_code`を受け付けない(TypeError、Bypass Path撤去)。"""
    target_obs = _per_observation("7203", multiple=Decimal("10"), source_version_id="SV_T")
    peer_obs = _per_observation("7267", multiple=Decimal("8"), source_version_id="SV_P")
    with pytest.raises(TypeError):
        build_peer_comparison_record(
            target_entity_code="7203",
            peer_entity_code="7267",
            metric_type=PeerMetricType.LATEST_REPORTED_FY_PER,
            comparison_as_of=_AS_OF,
            target_observation=target_obs,
            peer_observation=peer_obs,
        )


def test_regression_b_accepted_peer_entity_code_mismatch_fails_closed() -> None:
    """要件v1 §16-B: `accepted_peer.entity_code != peer_observation.entity_code`
    はfail closed。"""
    target_obs = _per_observation("7203", multiple=Decimal("10"), source_version_id="SV_T")
    peer_obs = _per_observation("7267", multiple=Decimal("8"), source_version_id="SV_P")
    with pytest.raises(ValueError, match="peer_observation.entity_code"):
        build_peer_comparison_record(
            target_entity_code="7203",
            accepted_peer=_accepted_peer("9999"),  # mismatched entity_code
            metric_type=PeerMetricType.LATEST_REPORTED_FY_PER,
            comparison_as_of=_AS_OF,
            target_observation=target_obs,
            peer_observation=peer_obs,
        )


def test_regression_c_accepted_peer_as_of_mismatch_fails_closed() -> None:
    """要件v1 §16-C: `accepted_peer.as_of != comparison_as_of`はfail closed。"""
    target_obs = _per_observation("7203", multiple=Decimal("10"), source_version_id="SV_T")
    peer_obs = _per_observation("7267", multiple=Decimal("8"), source_version_id="SV_P")
    other_as_of = _AS_OF.replace(hour=10)
    with pytest.raises(ValueError, match="comparison_as_of"):
        build_peer_comparison_record(
            target_entity_code="7203",
            accepted_peer=_accepted_peer("7267", as_of=other_as_of),
            metric_type=PeerMetricType.LATEST_REPORTED_FY_PER,
            comparison_as_of=_AS_OF,
            target_observation=target_obs,
            peer_observation=peer_obs,
        )


def test_regression_d_target_observation_entity_mismatch_fails_closed() -> None:
    """要件v1 §16-D: `target_observation.entity_code != target_entity_code`
    はfail closed。"""
    target_obs = _per_observation("9999", multiple=Decimal("10"), source_version_id="SV_T")  # wrong entity
    peer_obs = _per_observation("7267", multiple=Decimal("8"), source_version_id="SV_P")
    with pytest.raises(ValueError, match="target_entity_code"):
        build_peer_comparison_record(
            target_entity_code="7203",
            accepted_peer=_accepted_peer("7267"),
            metric_type=PeerMetricType.LATEST_REPORTED_FY_PER,
            comparison_as_of=_AS_OF,
            target_observation=target_obs,
            peer_observation=peer_obs,
        )


# --- D0096 Finding 5: Wrong Metric Family Parent (regression K) ----------------


def test_regression_k_wrong_metric_family_evidence_rejected() -> None:
    """要件v1 §16-K: 同一Entity・PIT-Compatibleでも、Metric Familyが
    異なるEvidence(CURRENT_FY_COMPANY_FORECAST_PER)を`latest_reported_
    fy_per_record_to_peer_observation()`(LATEST_REPORTED_FY_PER専用)へ
    渡すとfail closedで拒否される。"""
    per_record = _per_record("7203", price_value=Decimal("1000"), eps_value=Decimal("100"), source_version_id="SV_A")
    forecast_record = CurrentFyCompanyForecastPerRecord(
        entity_code="7203",
        as_of=_AS_OF,
        price_date=date(2024, 11, 14),
        price_value=Decimal("1000"),
        price_available_at=session_close_at(date(2024, 11, 14)),
        denominator_type="CURRENT_FY_COMPANY_FORECAST_EPS_CONSOLIDATED",
        eps_value=Decimal("100"),
        forecast_period_start=date(2024, 4, 1),
        forecast_period_end=date(2025, 3, 31),
        guidance_published_at=datetime(2024, 11, 6, 15, 30, tzinfo=_JST),
        source_version_id="SV_A",
        source_field="FEPS",
        fiscal_year_target="NEXT",
        disclosure_period_type="2Q",
        consolidation_scope="CONSOLIDATED",
        accounting_standard="IFRS",
        calculation_expression="price_close=1000 / forecast_eps=100",
        multiple=Decimal("10"),
        corporate_action_basis_status=CorporateActionBasisStatus.CONFIRMED_NO_ACTION,
    )
    wrong_family_evidence = current_fy_company_forecast_per_to_evidence(
        forecast_record,
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        originating_source="JQUANTS_SOURCE_DATA",
        delivery_provider="JQUANTS",
    )
    # related_codes/value_dateだけを揃えても、Metric Family検証で拒否される。
    with pytest.raises(ValueError, match="不適格|一致しません"):
        latest_reported_fy_per_record_to_peer_observation(per_record, evidence=wrong_family_evidence, as_of=_AS_OF)
