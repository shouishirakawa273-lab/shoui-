"""Synthetic operating-income module integration; no actual company or return acceptance."""

from dataclasses import replace
from datetime import timedelta
from decimal import ROUND_HALF_EVEN, Decimal

import pytest
from lib.company_exposure.bridge import compute_exposure_bridge
from lib.company_exposure.model import BridgeStatus
from lib.evaluation.integrity import verify_record_integrity
from lib.evidence.thesis_impact import ThesisScenario
from lib.valuation.engine import evaluate_forward_valuation
from lib.valuation.forward_reverse_model import BalanceSheetInputs, MultipleSource, ValuationMultiple, ValuationStatus
from test_company_exposure_bridge import OLD, T, request


def test_synthetic_bridge_replay_flows_into_per_share_valuation() -> None:
    req = request()
    original_hash = req.record_hash
    bridge = compute_exposure_bridge(req)
    assert bridge.status is BridgeStatus.SUCCESS, bridge.reason
    assert bridge.baseline_forecast is not None and bridge.replay_forecast is not None
    assert bridge.target_operating_income_jpy is not None and bridge.replay_operating_income_jpy is not None
    assert bridge.rounding_difference_jpy == bridge.replay_operating_income_jpy - bridge.target_operating_income_jpy
    rounded_target = (bridge.target_operating_income_jpy / bridge.money_quantum).to_integral_value(rounding=ROUND_HALF_EVEN)
    rounded_replay = (bridge.replay_operating_income_jpy / bridge.money_quantum).to_integral_value(rounding=ROUND_HALF_EVEN)
    assert rounded_target == rounded_replay
    multiple = ValuationMultiple(
        value=Decimal("8"),
        source=MultipleSource.PEER_SET,
        reference_period="SYNTHETIC_PRIOR",
        available_at=OLD,
        method_version="SYNTHETIC_INTEGRATION_V1",
    )
    balance = BalanceSheetInputs(
        net_debt=Decimal("50"),
        net_debt_currency="JPY",
        net_debt_available_at=OLD,
        source_id="SYNTHETIC_BALANCE",
        share_count=Decimal("10"),
        share_count_available_at=OLD,
    )
    values = [
        evaluate_forward_valuation(
            forecast,
            result_id=f"SYNTHETIC_VALUE_{i}",
            multiple=multiple,
            balance_sheet=balance,
            calculated_at=T,
        )
        for i, forecast in enumerate((bridge.baseline_forecast, bridge.replay_forecast))
    ]
    assert all(v.status is ValuationStatus.SUCCESS for v in values)
    baseline = {s.scenario: s for s in values[0].scenarios}
    replay = {s.scenario: s for s in values[1].scenarios}
    baseline_forecast = {s.scenario: s.metric_values for s in bridge.baseline_forecast.scenarios}
    replay_forecast = {s.scenario: s.metric_values for s in bridge.replay_forecast.scenarios}
    for forecast in (bridge.baseline_forecast, bridge.replay_forecast):
        income = next(
            v for s in forecast.scenarios if s.scenario is req.scenario for v in s.metric_values if v.metric == "OPERATING_INCOME"
        )
        assert income.unit == "JPY"
    for selected in (baseline[req.scenario], replay[req.scenario]):
        assert selected.currency == "JPY"
        assert selected.estimated_enterprise_value == selected.input_operating_income * Decimal("8")
        assert selected.estimated_equity_value == selected.input_operating_income * Decimal("8") - Decimal("50")
        assert selected.estimated_value_per_share == (selected.input_operating_income * Decimal("8") - Decimal("50")) / Decimal(
            "10"
        )
    base = baseline[ThesisScenario.BASE]
    adjusted = replay[ThesisScenario.BASE]
    assert base.input_operating_income == bridge.baseline_operating_income_jpy == Decimal("100")
    assert adjusted.input_operating_income == bridge.replay_operating_income_jpy == Decimal("120")
    assert base.estimated_value_per_share == Decimal("75")
    assert adjusted.estimated_value_per_share == Decimal("91")
    assert (
        adjusted.estimated_value_per_share - base.estimated_value_per_share
        == ((adjusted.input_operating_income - base.input_operating_income) * Decimal("8") / Decimal("10"))
        == Decimal("16")
    )
    for scenario in (ThesisScenario.BULL, ThesisScenario.BEAR):
        assert baseline_forecast[scenario] == replay_forecast[scenario]
        assert baseline[scenario] == replay[scenario]
    assert req.record_hash == original_hash and verify_record_integrity(req)


@pytest.mark.parametrize("future_input", ["multiple", "balance_sheet"])
def test_synthetic_replay_valuation_rejects_one_future_input(future_input: str) -> None:
    req = request()
    bridge = compute_exposure_bridge(req)
    assert bridge.status is BridgeStatus.SUCCESS and bridge.replay_forecast is not None
    multiple = ValuationMultiple(
        value=Decimal("8"),
        source=MultipleSource.PEER_SET,
        reference_period="SYNTHETIC_PRIOR",
        available_at=OLD,
        method_version="SYNTHETIC_INTEGRATION_V1",
    )
    balance = BalanceSheetInputs(
        net_debt=Decimal("50"),
        net_debt_currency="JPY",
        net_debt_available_at=OLD,
        source_id="SYNTHETIC_BALANCE",
        share_count=Decimal("10"),
        share_count_available_at=OLD,
    )
    valid = evaluate_forward_valuation(
        bridge.replay_forecast,
        result_id="SYNTHETIC_VALID",
        multiple=multiple,
        balance_sheet=balance,
        calculated_at=T,
    )
    assert valid.status is ValuationStatus.SUCCESS
    if future_input == "multiple":
        multiple = replace(multiple, available_at=T + timedelta(seconds=1))
    else:
        balance = replace(balance, net_debt_available_at=T + timedelta(seconds=1))
    invalid = evaluate_forward_valuation(
        bridge.replay_forecast,
        result_id="SYNTHETIC_FUTURE",
        multiple=multiple,
        balance_sheet=balance,
        calculated_at=T,
    )
    assert invalid.status is ValuationStatus.PIT_INVALID
    assert invalid.scenarios == ()
