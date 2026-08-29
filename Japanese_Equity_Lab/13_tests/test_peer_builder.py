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
        peer_entity_code="7267",
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
        peer_entity_code="7267",
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
        peer_entity_code=peer_code,
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
        peer_entity_code="2004",
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
