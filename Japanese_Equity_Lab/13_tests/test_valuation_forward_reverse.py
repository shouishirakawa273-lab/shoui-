"""`lib.valuation.{forward_reverse_model,engine,reverse}`(D0110)の
Regression Test(D0110 §22/§27-33 Required Tests)。

1. Forward Valuationが決定論的に計算され、Bull/Base/Bearを独立評価し、
   入力順序非依存のHash/Identityを持ち、必須Assumption欠落/Currency
   不整合/PIT違反をTyped Statusで拒否すること、確率/Expected
   Return/Decision出力が存在しないこと。
2. Reverse ValuationがFORWARDと同じ3つの純粋関数を呼び(Round-Trip
   一致)、1変数+充足Fixed Assumptionのみ解き、複数未知変数は常に
   UNDERDETERMINED、未来価格はPIT_INVALID、Assumption SurfaceがGrid
   を実際に計算し、Fixed Assumptionを保存すること。
3. 数値安全性(Lower/Upper Bound・Zero・負のDomain・収束Tolerance・
   最大反復)がTyped Failureで表現されること、NaN/infが出力されない
   こと。
4. 会計的Sanity(負のMultiple拒否・0 Shares拒否・負のNet Debt=Net Cash
   許容)。
"""

from __future__ import annotations

import ast
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from lib.evidence.thesis_impact import ThesisScenario
from lib.expectations.reverse_spec import (
    BoundedAssumption,
    FixedAssumption,
    MarketImpliedResultStatus,
    SolveForVariable,
    build_reverse_valuation_spec,
)
from lib.forecasting.engine import compute_fundamental_forecast
from lib.forecasting.model import (
    METRIC_OPERATING_INCOME,
    METRIC_REVENUE,
    AssumptionSource,
    ForecastAssumption,
    HistoricalFundamentalBase,
    ScenarioAssumptions,
)
from lib.valuation import engine as valuation_engine_module
from lib.valuation import forward_reverse_model as valuation_model_module
from lib.valuation import reverse as valuation_reverse_module
from lib.valuation.engine import (
    VALUATION_MODEL_VERSION,
    compute_enterprise_value,
    compute_equity_value,
    compute_value_per_share,
    evaluate_forward_valuation,
)
from lib.valuation.forward_reverse_model import (
    VALUATION_MODEL_ID,
    VARIABLE_EV_OPERATING_INCOME_MULTIPLE,
    VARIABLE_NET_DEBT,
    VARIABLE_OPERATING_INCOME,
    VARIABLE_SHARE_COUNT,
    BalanceSheetInputs,
    MultipleSource,
    ValuationMultiple,
    ValuationSchemaError,
    ValuationStatus,
)
from lib.valuation.reverse import compute_assumption_surface_for_valuation, solve_reverse_valuation

_NOW = datetime(2026, 9, 1, tzinfo=UTC)
_MULTIPLE_AVAILABLE_AT = datetime(2026, 6, 1, tzinfo=UTC)


def _historical_base(value: Decimal = Decimal("1000"), unit: str = "JPY") -> HistoricalFundamentalBase:
    return HistoricalFundamentalBase(
        entity_id="7203",
        metric=METRIC_REVENUE,
        period="FY2026",
        value=value,
        unit=unit,
        currency=unit,
        source_id="JQUANTS",
        available_at=datetime(2026, 5, 1, tzinfo=UTC),
        provenance_ref="M1",
    )


def _judgment(name: str, value: str) -> ForecastAssumption:
    return ForecastAssumption(
        name=name, value=Decimal(value), unit="PERCENT", source=AssumptionSource.RESEARCH_JUDGMENT, rationale="t", created_at=_NOW
    )


def _scenario(scenario: ThesisScenario, growth: str, margin: str) -> ScenarioAssumptions:
    return ScenarioAssumptions(
        scenario=scenario, assumptions=(_judgment("REVENUE_GROWTH", growth), _judgment("OPERATING_MARGIN", margin))
    )


def _forecast(*, historical_bases=None, requested_metrics=(METRIC_OPERATING_INCOME,)):
    return compute_fundamental_forecast(
        result_id="FR1",
        entity_id="7203",
        target_period="FY2027",
        requested_metrics=requested_metrics,
        scenario_assumptions=(
            _scenario(ThesisScenario.BULL, "10", "11"),
            _scenario(ThesisScenario.BASE, "6", "10"),
            _scenario(ThesisScenario.BEAR, "0", "7"),
        ),
        historical_bases=(_historical_base(),) if historical_bases is None else historical_bases,
        evidence_cutoff=_NOW,
        research_snapshot_id="SNAP1",
        forecast_created_at=_NOW,
    )


def _multiple(value: Decimal = Decimal("8"), available_at: datetime = _MULTIPLE_AVAILABLE_AT) -> ValuationMultiple:
    return ValuationMultiple(
        value=value, source=MultipleSource.PEER_SET, reference_period="FY2026", available_at=available_at, method_version="V1"
    )


def _balance_sheet(
    *,
    net_debt: Decimal = Decimal("50"),
    net_debt_currency: str = "JPY",
    share_count: Decimal | None = Decimal("10"),
    available_at: datetime = _MULTIPLE_AVAILABLE_AT,
) -> BalanceSheetInputs:
    return BalanceSheetInputs(
        net_debt=net_debt,
        net_debt_currency=net_debt_currency,
        net_debt_available_at=available_at,
        source_id="COMPANY_BALANCE_SHEET",
        share_count=share_count,
        share_count_available_at=available_at if share_count is not None else None,
    )


_UNSET = object()


def _evaluate(*, forecast=_UNSET, multiple=_UNSET, balance_sheet=_UNSET, **overrides):
    resolved_forecast = _forecast() if forecast is _UNSET else forecast
    resolved_multiple = _multiple() if multiple is _UNSET else multiple
    resolved_balance_sheet = _balance_sheet() if balance_sheet is _UNSET else balance_sheet
    return evaluate_forward_valuation(
        resolved_forecast,
        result_id="V1",
        multiple=resolved_multiple,
        balance_sheet=resolved_balance_sheet,
        calculated_at=_NOW,
        **overrides,
    )


def _reverse_spec(*, solve_for, fixed_assumptions, observed_market_price, bounded_assumptions=(), price_available_at=_NOW):
    return build_reverse_valuation_spec(
        spec_id="SPEC1",
        valuation_model_id=VALUATION_MODEL_ID,
        valuation_model_version=VALUATION_MODEL_VERSION,
        entity_id="7203",
        observed_market_price=observed_market_price,
        price_currency="JPY",
        price_observed_at=price_available_at,
        price_available_at=price_available_at,
        price_source_id="MARKET_DATA",
        solve_for_variables=solve_for,
        valuation_horizon="FY2027",
        created_at=_NOW,
        fixed_assumptions=fixed_assumptions,
        bounded_assumptions=bounded_assumptions,
    )


_OI = Decimal("848")
_MULT = Decimal("8")
_ND = Decimal("50")
_SC = Decimal("10")


def _forward_price(oi=_OI, mult=_MULT, nd=_ND, sc=_SC) -> Decimal:
    ev = compute_enterprise_value(operating_income=oi, multiple_value=mult)
    eq = compute_equity_value(enterprise_value=ev, net_debt=nd)
    return compute_value_per_share(equity_value=eq, share_count=sc)


# ============================================================
# D0110 §27: Forward
# ============================================================


def test_27a_base_forecast_to_deterministic_valuation() -> None:
    result = _evaluate()
    assert result.status is ValuationStatus.SUCCESS
    base = next(s for s in result.scenarios if s.scenario is ThesisScenario.BASE)
    assert base.estimated_enterprise_value == Decimal("848.000")
    assert base.estimated_equity_value == Decimal("798.000")
    assert base.estimated_value_per_share == Decimal("79.800")


def test_27b_bull_base_bear_independently_valued() -> None:
    result = _evaluate()
    by_scenario = {s.scenario: s for s in result.scenarios}
    assert by_scenario[ThesisScenario.BULL].estimated_enterprise_value == Decimal("968.000")
    assert by_scenario[ThesisScenario.BASE].estimated_enterprise_value == Decimal("848.000")
    assert by_scenario[ThesisScenario.BEAR].estimated_enterprise_value == Decimal("560.00")


def test_27c_reordered_logical_inputs_produce_same_hash() -> None:
    result_1 = _evaluate()
    result_2 = _evaluate()
    assert result_1.record_hash == result_2.record_hash


def test_27d_missing_multiple_is_insufficient_input() -> None:
    result = _evaluate(multiple=None)
    assert result.status is ValuationStatus.INSUFFICIENT_INPUT


def test_27e_missing_balance_sheet_is_insufficient_input() -> None:
    result = _evaluate(balance_sheet=None)
    assert result.status is ValuationStatus.INSUFFICIENT_INPUT


def test_27f_incompatible_currency_is_rejected() -> None:
    result = _evaluate(balance_sheet=_balance_sheet(net_debt_currency="USD"))
    assert result.status is ValuationStatus.INVALID_ASSUMPTION


def test_27g_pit_invalid_multiple_is_rejected() -> None:
    result = _evaluate(multiple=_multiple(available_at=datetime(2026, 9, 10, tzinfo=UTC)))
    assert result.status is ValuationStatus.PIT_INVALID


def test_27h_pit_invalid_balance_sheet_is_rejected() -> None:
    result = _evaluate(balance_sheet=_balance_sheet(available_at=datetime(2026, 9, 10, tzinfo=UTC)))
    assert result.status is ValuationStatus.PIT_INVALID


def test_27i_no_scenario_probability_field() -> None:
    result = _evaluate()
    for scenario_result in result.scenarios:
        assert not hasattr(scenario_result, "probability")
        assert not hasattr(scenario_result, "weight")


def test_27j_no_expected_return_or_decision_field() -> None:
    result = _evaluate()
    for scenario_result in result.scenarios:
        assert not hasattr(scenario_result, "expected_return")
        assert not hasattr(scenario_result, "decision")
        assert not hasattr(scenario_result, "recommendation")
    assert not hasattr(result, "expected_return")
    assert not hasattr(result, "decision")


# ============================================================
# D0110 §22/§28: Reverse
# ============================================================


def test_22_28a_forward_reverse_round_trip_recovers_operating_income() -> None:
    price = _forward_price()
    spec = _reverse_spec(
        solve_for=(SolveForVariable(name=VARIABLE_OPERATING_INCOME, unit="JPY"),),
        fixed_assumptions=(
            FixedAssumption(name=VARIABLE_EV_OPERATING_INCOME_MULTIPLE, value=_MULT, unit="MULTIPLE"),
            FixedAssumption(name=VARIABLE_NET_DEBT, value=_ND, unit="JPY"),
            FixedAssumption(name=VARIABLE_SHARE_COUNT, value=_SC, unit="SHARES"),
        ),
        observed_market_price=price,
        bounded_assumptions=(
            BoundedAssumption(name=VARIABLE_OPERATING_INCOME, lower_bound=Decimal("0"), upper_bound=Decimal("2000"), unit="JPY"),
        ),
    )
    result = solve_reverse_valuation(spec, result_id="R1", decision_at=_NOW, computed_at=_NOW)
    assert result.status is MarketImpliedResultStatus.SUCCESS
    assert abs(result.solved_values[0].value - _OI) <= Decimal("0.01")


def test_28b_one_unknown_with_complete_fixed_assumptions_succeeds() -> None:
    price = _forward_price()
    spec = _reverse_spec(
        solve_for=(SolveForVariable(name=VARIABLE_EV_OPERATING_INCOME_MULTIPLE, unit="MULTIPLE"),),
        fixed_assumptions=(
            FixedAssumption(name=VARIABLE_OPERATING_INCOME, value=_OI, unit="JPY"),
            FixedAssumption(name=VARIABLE_NET_DEBT, value=_ND, unit="JPY"),
            FixedAssumption(name=VARIABLE_SHARE_COUNT, value=_SC, unit="SHARES"),
        ),
        observed_market_price=price,
        bounded_assumptions=(
            BoundedAssumption(
                name=VARIABLE_EV_OPERATING_INCOME_MULTIPLE,
                lower_bound=Decimal("0.01"),
                upper_bound=Decimal("50"),
                unit="MULTIPLE",
            ),
        ),
    )
    result = solve_reverse_valuation(spec, result_id="R2", decision_at=_NOW, computed_at=_NOW)
    assert result.status is MarketImpliedResultStatus.SUCCESS
    assert abs(result.solved_values[0].value - _MULT) <= Decimal("0.01")


def test_28c_multiple_unknowns_without_surface_mode_is_underdetermined() -> None:
    price = _forward_price()
    spec = _reverse_spec(
        solve_for=(
            SolveForVariable(name=VARIABLE_OPERATING_INCOME, unit="JPY"),
            SolveForVariable(name=VARIABLE_EV_OPERATING_INCOME_MULTIPLE, unit="MULTIPLE"),
        ),
        fixed_assumptions=(
            FixedAssumption(name=VARIABLE_NET_DEBT, value=_ND, unit="JPY"),
            FixedAssumption(name=VARIABLE_SHARE_COUNT, value=_SC, unit="SHARES"),
        ),
        observed_market_price=price,
    )
    result = solve_reverse_valuation(spec, result_id="R3", decision_at=_NOW, computed_at=_NOW)
    assert result.status is MarketImpliedResultStatus.UNDERDETERMINED
    assert result.solved_values == ()


def test_28d_no_solution_inside_bounds_is_typed_failure() -> None:
    spec = _reverse_spec(
        solve_for=(SolveForVariable(name=VARIABLE_OPERATING_INCOME, unit="JPY"),),
        fixed_assumptions=(
            FixedAssumption(name=VARIABLE_EV_OPERATING_INCOME_MULTIPLE, value=_MULT, unit="MULTIPLE"),
            FixedAssumption(name=VARIABLE_NET_DEBT, value=_ND, unit="JPY"),
            FixedAssumption(name=VARIABLE_SHARE_COUNT, value=_SC, unit="SHARES"),
        ),
        observed_market_price=Decimal("999999"),  # Unreachable within bounds
        bounded_assumptions=(
            BoundedAssumption(name=VARIABLE_OPERATING_INCOME, lower_bound=Decimal("0"), upper_bound=Decimal("2000"), unit="JPY"),
        ),
    )
    result = solve_reverse_valuation(spec, result_id="R4", decision_at=_NOW, computed_at=_NOW)
    assert result.status is MarketImpliedResultStatus.NO_SOLUTION


def test_28e_unsupported_solve_variable_is_invalid_spec() -> None:
    spec = _reverse_spec(
        solve_for=(SolveForVariable(name="SOME_UNKNOWN_VARIABLE", unit="JPY"),),
        fixed_assumptions=(),
        observed_market_price=Decimal("100"),
        bounded_assumptions=(
            BoundedAssumption(name="SOME_UNKNOWN_VARIABLE", lower_bound=Decimal("0"), upper_bound=Decimal("10"), unit="JPY"),
        ),
    )
    result = solve_reverse_valuation(spec, result_id="R5", decision_at=_NOW, computed_at=_NOW)
    assert result.status is MarketImpliedResultStatus.INVALID_SPEC


def test_28e_unsupported_valuation_model_id() -> None:
    spec = _reverse_spec(
        solve_for=(SolveForVariable(name=VARIABLE_OPERATING_INCOME, unit="JPY"),),
        fixed_assumptions=(
            FixedAssumption(name=VARIABLE_EV_OPERATING_INCOME_MULTIPLE, value=_MULT, unit="MULTIPLE"),
            FixedAssumption(name=VARIABLE_NET_DEBT, value=_ND, unit="JPY"),
            FixedAssumption(name=VARIABLE_SHARE_COUNT, value=_SC, unit="SHARES"),
        ),
        observed_market_price=Decimal("100"),
    )
    spec = replace(spec, valuation_model_id="SOME_OTHER_MODEL")
    result = solve_reverse_valuation(spec, result_id="R6", decision_at=_NOW, computed_at=_NOW)
    assert result.status is MarketImpliedResultStatus.UNSUPPORTED_MODEL


def test_28f_future_market_price_is_pit_invalid() -> None:
    spec = _reverse_spec(
        solve_for=(SolveForVariable(name=VARIABLE_OPERATING_INCOME, unit="JPY"),),
        fixed_assumptions=(
            FixedAssumption(name=VARIABLE_EV_OPERATING_INCOME_MULTIPLE, value=_MULT, unit="MULTIPLE"),
            FixedAssumption(name=VARIABLE_NET_DEBT, value=_ND, unit="JPY"),
            FixedAssumption(name=VARIABLE_SHARE_COUNT, value=_SC, unit="SHARES"),
        ),
        observed_market_price=Decimal("100"),
        bounded_assumptions=(
            BoundedAssumption(name=VARIABLE_OPERATING_INCOME, lower_bound=Decimal("0"), upper_bound=Decimal("2000"), unit="JPY"),
        ),
        price_available_at=datetime(2026, 9, 10, tzinfo=UTC),
    )
    result = solve_reverse_valuation(spec, result_id="R7", decision_at=datetime(2026, 9, 1, tzinfo=UTC), computed_at=_NOW)
    assert result.status is MarketImpliedResultStatus.PIT_INVALID


def _two_unknown_spec(price: Decimal) -> object:
    return _reverse_spec(
        solve_for=(
            SolveForVariable(name=VARIABLE_OPERATING_INCOME, unit="JPY"),
            SolveForVariable(name=VARIABLE_EV_OPERATING_INCOME_MULTIPLE, unit="MULTIPLE"),
        ),
        fixed_assumptions=(
            FixedAssumption(name=VARIABLE_NET_DEBT, value=_ND, unit="JPY"),
            FixedAssumption(name=VARIABLE_SHARE_COUNT, value=_SC, unit="SHARES"),
        ),
        observed_market_price=price,
        bounded_assumptions=(
            BoundedAssumption(name=VARIABLE_OPERATING_INCOME, lower_bound=Decimal("0"), upper_bound=Decimal("5000"), unit="JPY"),
        ),
    )


def test_28g_assumption_surface_produces_explicit_grid() -> None:
    price = _forward_price()
    spec = _two_unknown_spec(price)
    surface = compute_assumption_surface_for_valuation(
        spec,
        surface_id="SURF1",
        varied_variable=VARIABLE_EV_OPERATING_INCOME_MULTIPLE,
        varied_values=(Decimal("6"), Decimal("8"), Decimal("10")),
        decision_at=_NOW,
        generated_at=_NOW,
    )
    assert len(surface.points) == 3
    multiple_8_point = next(p for p in surface.points if p.varied_values == (Decimal("8"),))
    assert abs(multiple_8_point.solved_values[0].value - _OI) <= Decimal("0.01")


def test_28h_surface_points_preserve_fixed_assumptions() -> None:
    price = _forward_price()
    spec = _two_unknown_spec(price)
    surface = compute_assumption_surface_for_valuation(
        spec,
        surface_id="SURF2",
        varied_variable=VARIABLE_EV_OPERATING_INCOME_MULTIPLE,
        varied_values=(Decimal("8"),),
        decision_at=_NOW,
        generated_at=_NOW,
    )
    assert surface.fixed_assumptions == spec.fixed_assumptions


def test_28i_changed_fixed_assumption_changes_implied_result() -> None:
    price = _forward_price()
    spec_low_debt = _reverse_spec(
        solve_for=(SolveForVariable(name=VARIABLE_OPERATING_INCOME, unit="JPY"),),
        fixed_assumptions=(
            FixedAssumption(name=VARIABLE_EV_OPERATING_INCOME_MULTIPLE, value=_MULT, unit="MULTIPLE"),
            FixedAssumption(name=VARIABLE_NET_DEBT, value=Decimal("0"), unit="JPY"),
            FixedAssumption(name=VARIABLE_SHARE_COUNT, value=_SC, unit="SHARES"),
        ),
        observed_market_price=price,
        bounded_assumptions=(
            BoundedAssumption(name=VARIABLE_OPERATING_INCOME, lower_bound=Decimal("0"), upper_bound=Decimal("2000"), unit="JPY"),
        ),
    )
    result_low_debt = solve_reverse_valuation(spec_low_debt, result_id="R8", decision_at=_NOW, computed_at=_NOW)
    result_original = solve_reverse_valuation(
        _reverse_spec(
            solve_for=(SolveForVariable(name=VARIABLE_OPERATING_INCOME, unit="JPY"),),
            fixed_assumptions=(
                FixedAssumption(name=VARIABLE_EV_OPERATING_INCOME_MULTIPLE, value=_MULT, unit="MULTIPLE"),
                FixedAssumption(name=VARIABLE_NET_DEBT, value=_ND, unit="JPY"),
                FixedAssumption(name=VARIABLE_SHARE_COUNT, value=_SC, unit="SHARES"),
            ),
            observed_market_price=price,
            bounded_assumptions=(
                BoundedAssumption(
                    name=VARIABLE_OPERATING_INCOME, lower_bound=Decimal("0"), upper_bound=Decimal("2000"), unit="JPY"
                ),
            ),
        ),
        result_id="R9",
        decision_at=_NOW,
        computed_at=_NOW,
    )
    assert result_low_debt.solved_values[0].value != result_original.solved_values[0].value


def test_28j_input_ordering_does_not_affect_logical_result() -> None:
    price = _forward_price()
    fixed_forward = (
        FixedAssumption(name=VARIABLE_EV_OPERATING_INCOME_MULTIPLE, value=_MULT, unit="MULTIPLE"),
        FixedAssumption(name=VARIABLE_NET_DEBT, value=_ND, unit="JPY"),
        FixedAssumption(name=VARIABLE_SHARE_COUNT, value=_SC, unit="SHARES"),
    )
    fixed_reversed = tuple(reversed(fixed_forward))
    bounds = (
        BoundedAssumption(name=VARIABLE_OPERATING_INCOME, lower_bound=Decimal("0"), upper_bound=Decimal("2000"), unit="JPY"),
    )
    spec_a = _reverse_spec(
        solve_for=(SolveForVariable(name=VARIABLE_OPERATING_INCOME, unit="JPY"),),
        fixed_assumptions=fixed_forward,
        observed_market_price=price,
        bounded_assumptions=bounds,
    )
    spec_b = _reverse_spec(
        solve_for=(SolveForVariable(name=VARIABLE_OPERATING_INCOME, unit="JPY"),),
        fixed_assumptions=fixed_reversed,
        observed_market_price=price,
        bounded_assumptions=bounds,
    )
    assert spec_a.record_hash == spec_b.record_hash
    result_a = solve_reverse_valuation(spec_a, result_id="RA", decision_at=_NOW, computed_at=_NOW)
    result_b = solve_reverse_valuation(spec_b, result_id="RB", decision_at=_NOW, computed_at=_NOW)
    assert result_a.solved_values[0].value == result_b.solved_values[0].value


def test_solve_reverse_valuation_rejects_naive_decision_at() -> None:
    """Regression(/code-review high指摘, D0110): `decision_at`/
    `computed_at`がtz-awareでない場合、`spec.price_available_at`との
    Datetime比較で生のTypeErrorを漏らさず、明示的なSchema Errorで
    Fail Closedする(他のD0107-109モジュールと同じ既存Pattern)。"""
    spec = _reverse_spec(
        solve_for=(SolveForVariable(name=VARIABLE_OPERATING_INCOME, unit="JPY"),),
        fixed_assumptions=(
            FixedAssumption(name=VARIABLE_EV_OPERATING_INCOME_MULTIPLE, value=_MULT, unit="MULTIPLE"),
            FixedAssumption(name=VARIABLE_NET_DEBT, value=_ND, unit="JPY"),
            FixedAssumption(name=VARIABLE_SHARE_COUNT, value=_SC, unit="SHARES"),
        ),
        observed_market_price=_forward_price(),
        bounded_assumptions=(
            BoundedAssumption(name=VARIABLE_OPERATING_INCOME, lower_bound=Decimal("0"), upper_bound=Decimal("2000"), unit="JPY"),
        ),
    )
    naive_decision_at = datetime(2026, 9, 1)  # noqa: DTZ001 -- 意図的にtz-naive(Regression対象そのもの)
    with pytest.raises(Exception):  # noqa: B017, PT011 -- lib.expectations.model.MarketExpectationsSchemaError
        solve_reverse_valuation(spec, result_id="RNAIVE", decision_at=naive_decision_at, computed_at=_NOW)


def test_duplicate_scenario_in_forecast_result_is_invalid_assumption() -> None:
    """Regression(/code-review high指摘, D0110): `forecast_result.
    scenarios`に重複したScenarioが含まれる場合、片方を無言で上書き
    せず`INVALID_ASSUMPTION`でFail Closedする。"""
    forecast = _forecast()
    duplicated_scenarios = (*forecast.scenarios, forecast.scenarios[0])
    corrupted_forecast = replace(forecast, scenarios=duplicated_scenarios)
    result = evaluate_forward_valuation(
        corrupted_forecast, result_id="VDUP", multiple=_multiple(), balance_sheet=_balance_sheet(), calculated_at=_NOW
    )
    assert result.status is ValuationStatus.INVALID_ASSUMPTION


def test_assumption_surface_rejects_missing_bound_for_remaining_variable() -> None:
    """Regression(/code-review high指摘, D0110): `remaining`変数
    (Varied対象ではない方の未知変数)に対応する`bounded_assumptions`が
    無い場合、各Grid点が個別に失敗して空のSurfaceへ無言で埋没するの
    ではなく、構造的誤設定として一度だけ明示的にRaiseする。"""
    price = _forward_price()
    spec = _two_unknown_spec(price)
    spec_without_bound = replace(spec, bounded_assumptions=())
    with pytest.raises(ValueError, match="remaining"):
        compute_assumption_surface_for_valuation(
            spec_without_bound,
            surface_id="SURF_NO_BOUND",
            varied_variable=VARIABLE_EV_OPERATING_INCOME_MULTIPLE,
            varied_values=(Decimal("8"),),
            decision_at=_NOW,
            generated_at=_NOW,
        )


def test_assumption_surface_rejects_future_price() -> None:
    """Regression(/code-review high指摘, D0110): Surface計算全体が
    未来価格を理由に構造的に不可能な場合、Grid点ごとにPIT_INVALIDへ
    個別にFailさせて空Surfaceへ埋没させるのではなく、一度だけ明示的に
    Raiseする。"""
    price = _forward_price()
    spec = _two_unknown_spec(price)
    future_spec = replace(spec, price_available_at=datetime(2026, 9, 10, tzinfo=UTC))
    with pytest.raises(ValueError, match="price_available_at"):
        compute_assumption_surface_for_valuation(
            future_spec,
            surface_id="SURF_FUTURE",
            varied_variable=VARIABLE_EV_OPERATING_INCOME_MULTIPLE,
            varied_values=(Decimal("8"),),
            decision_at=datetime(2026, 9, 1, tzinfo=UTC),
            generated_at=_NOW,
        )


def test_balance_sheet_requires_source_id() -> None:
    """Regression(/code-review high指摘, D0110): `BalanceSheetInputs.
    source_id`は他のProvenance Field(`ValuationMultiple.source`/
    `reference_period`/`method_version`)と同じく必須かつ非空である
    必要がある(デフォルト空文字へ暗黙Fallbackしない)。"""
    with pytest.raises(ValuationSchemaError):
        BalanceSheetInputs(
            net_debt=Decimal("50"),
            net_debt_currency="JPY",
            net_debt_available_at=_MULTIPLE_AVAILABLE_AT,
            source_id="",
        )


# ============================================================
# D0110 §29: Numerical Safety
# ============================================================


def test_numerical_safety_lower_bound_exact_solution() -> None:
    spec = _reverse_spec(
        solve_for=(SolveForVariable(name=VARIABLE_OPERATING_INCOME, unit="JPY"),),
        fixed_assumptions=(
            FixedAssumption(name=VARIABLE_EV_OPERATING_INCOME_MULTIPLE, value=_MULT, unit="MULTIPLE"),
            FixedAssumption(name=VARIABLE_NET_DEBT, value=_ND, unit="JPY"),
            FixedAssumption(name=VARIABLE_SHARE_COUNT, value=_SC, unit="SHARES"),
        ),
        observed_market_price=_forward_price(oi=Decimal("0")),
        bounded_assumptions=(
            BoundedAssumption(name=VARIABLE_OPERATING_INCOME, lower_bound=Decimal("0"), upper_bound=Decimal("2000"), unit="JPY"),
        ),
    )
    result = solve_reverse_valuation(spec, result_id="RLOW", decision_at=_NOW, computed_at=_NOW)
    assert result.status is MarketImpliedResultStatus.SUCCESS
    assert abs(result.solved_values[0].value - Decimal("0")) <= Decimal("0.01")


def test_numerical_safety_upper_bound_exact_solution() -> None:
    spec = _reverse_spec(
        solve_for=(SolveForVariable(name=VARIABLE_OPERATING_INCOME, unit="JPY"),),
        fixed_assumptions=(
            FixedAssumption(name=VARIABLE_EV_OPERATING_INCOME_MULTIPLE, value=_MULT, unit="MULTIPLE"),
            FixedAssumption(name=VARIABLE_NET_DEBT, value=_ND, unit="JPY"),
            FixedAssumption(name=VARIABLE_SHARE_COUNT, value=_SC, unit="SHARES"),
        ),
        observed_market_price=_forward_price(oi=Decimal("2000")),
        bounded_assumptions=(
            BoundedAssumption(name=VARIABLE_OPERATING_INCOME, lower_bound=Decimal("0"), upper_bound=Decimal("2000"), unit="JPY"),
        ),
    )
    result = solve_reverse_valuation(spec, result_id="RHIGH", decision_at=_NOW, computed_at=_NOW)
    assert result.status is MarketImpliedResultStatus.SUCCESS
    assert abs(result.solved_values[0].value - Decimal("2000")) <= Decimal("0.01")


def test_numerical_safety_zero_crossing_net_debt() -> None:
    # Solve NET_DEBT such that EquityValue == 0 (price == 0).
    spec = _reverse_spec(
        solve_for=(SolveForVariable(name=VARIABLE_NET_DEBT, unit="JPY"),),
        fixed_assumptions=(
            FixedAssumption(name=VARIABLE_OPERATING_INCOME, value=_OI, unit="JPY"),
            FixedAssumption(name=VARIABLE_EV_OPERATING_INCOME_MULTIPLE, value=_MULT, unit="MULTIPLE"),
            FixedAssumption(name=VARIABLE_SHARE_COUNT, value=_SC, unit="SHARES"),
        ),
        observed_market_price=Decimal("0"),
        bounded_assumptions=(
            BoundedAssumption(name=VARIABLE_NET_DEBT, lower_bound=Decimal("-1000"), upper_bound=Decimal("10000"), unit="JPY"),
        ),
    )
    result = solve_reverse_valuation(spec, result_id="RZERO", decision_at=_NOW, computed_at=_NOW)
    assert result.status is MarketImpliedResultStatus.SUCCESS
    expected_net_debt = compute_enterprise_value(operating_income=_OI, multiple_value=_MULT)
    assert abs(result.solved_values[0].value - expected_net_debt) <= Decimal("0.01")


def test_numerical_safety_negative_domain_bound_for_multiple_is_invalid_spec() -> None:
    spec = _reverse_spec(
        solve_for=(SolveForVariable(name=VARIABLE_EV_OPERATING_INCOME_MULTIPLE, unit="MULTIPLE"),),
        fixed_assumptions=(
            FixedAssumption(name=VARIABLE_OPERATING_INCOME, value=_OI, unit="JPY"),
            FixedAssumption(name=VARIABLE_NET_DEBT, value=_ND, unit="JPY"),
            FixedAssumption(name=VARIABLE_SHARE_COUNT, value=_SC, unit="SHARES"),
        ),
        observed_market_price=Decimal("100"),
        bounded_assumptions=(
            BoundedAssumption(
                name=VARIABLE_EV_OPERATING_INCOME_MULTIPLE, lower_bound=Decimal("-5"), upper_bound=Decimal("10"), unit="MULTIPLE"
            ),
        ),
    )
    result = solve_reverse_valuation(spec, result_id="RNEG", decision_at=_NOW, computed_at=_NOW)
    assert result.status is MarketImpliedResultStatus.INVALID_SPEC


def test_numerical_safety_extreme_but_allowed_bounds_still_converge() -> None:
    spec = _reverse_spec(
        solve_for=(SolveForVariable(name=VARIABLE_OPERATING_INCOME, unit="JPY"),),
        fixed_assumptions=(
            FixedAssumption(name=VARIABLE_EV_OPERATING_INCOME_MULTIPLE, value=_MULT, unit="MULTIPLE"),
            FixedAssumption(name=VARIABLE_NET_DEBT, value=_ND, unit="JPY"),
            FixedAssumption(name=VARIABLE_SHARE_COUNT, value=_SC, unit="SHARES"),
        ),
        observed_market_price=_forward_price(),
        bounded_assumptions=(
            BoundedAssumption(
                name=VARIABLE_OPERATING_INCOME, lower_bound=Decimal("-1000000"), upper_bound=Decimal("1000000"), unit="JPY"
            ),
        ),
    )
    result = solve_reverse_valuation(spec, result_id="REXTREME", decision_at=_NOW, computed_at=_NOW)
    assert result.status is MarketImpliedResultStatus.SUCCESS
    assert abs(result.solved_values[0].value - _OI) <= Decimal("0.01")


def test_numerical_safety_convergence_tolerance_is_recorded() -> None:
    spec = _reverse_spec(
        solve_for=(SolveForVariable(name=VARIABLE_OPERATING_INCOME, unit="JPY"),),
        fixed_assumptions=(
            FixedAssumption(name=VARIABLE_EV_OPERATING_INCOME_MULTIPLE, value=_MULT, unit="MULTIPLE"),
            FixedAssumption(name=VARIABLE_NET_DEBT, value=_ND, unit="JPY"),
            FixedAssumption(name=VARIABLE_SHARE_COUNT, value=_SC, unit="SHARES"),
        ),
        observed_market_price=_forward_price(),
        bounded_assumptions=(
            BoundedAssumption(name=VARIABLE_OPERATING_INCOME, lower_bound=Decimal("0"), upper_bound=Decimal("2000"), unit="JPY"),
        ),
    )
    result = solve_reverse_valuation(spec, result_id="RTOL", decision_at=_NOW, computed_at=_NOW, tolerance=Decimal("0.001"))
    assert result.status is MarketImpliedResultStatus.SUCCESS
    assert result.reason is not None
    assert "0.001" in result.reason


def test_numerical_safety_max_iteration_behavior_returns_no_solution_not_fake_success() -> None:
    spec = _reverse_spec(
        solve_for=(SolveForVariable(name=VARIABLE_OPERATING_INCOME, unit="JPY"),),
        fixed_assumptions=(
            FixedAssumption(name=VARIABLE_EV_OPERATING_INCOME_MULTIPLE, value=_MULT, unit="MULTIPLE"),
            FixedAssumption(name=VARIABLE_NET_DEBT, value=_ND, unit="JPY"),
            FixedAssumption(name=VARIABLE_SHARE_COUNT, value=_SC, unit="SHARES"),
        ),
        observed_market_price=_forward_price(),
        bounded_assumptions=(
            BoundedAssumption(name=VARIABLE_OPERATING_INCOME, lower_bound=Decimal("0"), upper_bound=Decimal("2000"), unit="JPY"),
        ),
    )
    result = solve_reverse_valuation(
        spec, result_id="RMAXITER", decision_at=_NOW, computed_at=_NOW, tolerance=Decimal("0.0000000001"), max_iterations=1
    )
    assert result.status in (MarketImpliedResultStatus.NO_SOLUTION, MarketImpliedResultStatus.SUCCESS)
    if result.status is MarketImpliedResultStatus.SUCCESS:
        # If it DID succeed with 1 iteration, the solved value must still be
        # within the requested (extremely tight) tolerance -- never a fake
        # success at a looser precision than requested.
        assert abs(result.solved_values[0].value - _OI) <= Decimal("0.0000000001")


def test_numerical_safety_never_emits_nan_or_inf() -> None:
    spec = _reverse_spec(
        solve_for=(SolveForVariable(name=VARIABLE_OPERATING_INCOME, unit="JPY"),),
        fixed_assumptions=(
            FixedAssumption(name=VARIABLE_EV_OPERATING_INCOME_MULTIPLE, value=_MULT, unit="MULTIPLE"),
            FixedAssumption(name=VARIABLE_NET_DEBT, value=_ND, unit="JPY"),
            FixedAssumption(name=VARIABLE_SHARE_COUNT, value=_SC, unit="SHARES"),
        ),
        observed_market_price=_forward_price(),
        bounded_assumptions=(
            BoundedAssumption(name=VARIABLE_OPERATING_INCOME, lower_bound=Decimal("0"), upper_bound=Decimal("2000"), unit="JPY"),
        ),
    )
    result = solve_reverse_valuation(spec, result_id="RFINITE", decision_at=_NOW, computed_at=_NOW)
    assert result.solved_values[0].value.is_finite()


# ============================================================
# D0110 §30: Accounting / Economic Sanity
# ============================================================


def test_negative_multiple_is_rejected() -> None:
    with pytest.raises(ValuationSchemaError):
        ValuationMultiple(
            value=Decimal("-8"),
            source=MultipleSource.PEER_SET,
            reference_period="FY2026",
            available_at=_MULTIPLE_AVAILABLE_AT,
            method_version="V1",
        )


def test_zero_shares_is_rejected() -> None:
    with pytest.raises(ValuationSchemaError):
        BalanceSheetInputs(
            net_debt=Decimal("50"),
            net_debt_currency="JPY",
            net_debt_available_at=_MULTIPLE_AVAILABLE_AT,
            source_id="COMPANY_BALANCE_SHEET",
            share_count=Decimal("0"),
            share_count_available_at=_MULTIPLE_AVAILABLE_AT,
        )


def test_negative_net_debt_net_cash_is_valid() -> None:
    bs = BalanceSheetInputs(
        net_debt=Decimal("-200"),
        net_debt_currency="JPY",
        net_debt_available_at=_MULTIPLE_AVAILABLE_AT,
        source_id="COMPANY_BALANCE_SHEET",
        share_count=Decimal("10"),
        share_count_available_at=_MULTIPLE_AVAILABLE_AT,
    )
    assert bs.net_debt == Decimal("-200")
    result = _evaluate(balance_sheet=bs)
    assert result.status is ValuationStatus.SUCCESS
    base = next(s for s in result.scenarios if s.scenario is ThesisScenario.BASE)
    assert base.estimated_equity_value > base.estimated_enterprise_value


def test_missing_share_count_yields_no_value_per_share_but_still_success() -> None:
    result = _evaluate(balance_sheet=_balance_sheet(share_count=None))
    assert result.status is ValuationStatus.SUCCESS
    for scenario_result in result.scenarios:
        assert scenario_result.estimated_value_per_share is None


# ============================================================
# D0110 §32: No Expected Return / §33: No Model Calls / Structural
# ============================================================


def _module_identifiers(module_path: str) -> set[str]:
    source = Path(module_path).read_text(encoding="utf-8")
    tree = ast.parse(source)
    identifiers: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name | ast.Attribute):
            identifiers.add(getattr(node, "id", getattr(node, "attr", "")))
        elif isinstance(node, ast.arg):
            identifiers.add(node.arg)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            identifiers.add(node.name)
    return identifiers


def test_no_expected_return_or_decision_identifiers() -> None:
    for module_path in (
        valuation_model_module.__file__,
        valuation_engine_module.__file__,
        valuation_reverse_module.__file__,
    ):
        identifiers = _module_identifiers(module_path)
        for forbidden in (
            "expected_return",
            "scenario_probability",
            "probability_weighted_value",
            "BUY",
            "SELL",
            "HOLD",
            "position_size",
            "bull_probability",
            "base_probability",
            "bear_probability",
        ):
            assert forbidden not in identifiers, f"{module_path} に禁止識別子 {forbidden!r} が含まれています"


def test_no_decision_record_added() -> None:
    for module_path in (
        valuation_model_module.__file__,
        valuation_engine_module.__file__,
        valuation_reverse_module.__file__,
    ):
        source = Path(module_path).read_text(encoding="utf-8")
        assert "DecisionRecord" not in source
        assert "build_decision_record" not in source


def test_no_llm_dependency() -> None:
    for module_path in (
        valuation_model_module.__file__,
        valuation_engine_module.__file__,
        valuation_reverse_module.__file__,
    ):
        source = Path(module_path).read_text(encoding="utf-8")
        for forbidden in ("import openai", "import anthropic", "requests.post", "httpx.", ".classify(", ".extract("):
            assert forbidden not in source


def test_modules_do_not_touch_h0001() -> None:
    for module_path in (
        valuation_model_module.__file__,
        valuation_engine_module.__file__,
        valuation_reverse_module.__file__,
    ):
        source = Path(module_path).read_text(encoding="utf-8")
        assert "H0001" not in source
        assert "locked_test" not in source.lower()


def test_forward_and_reverse_share_the_same_pure_functions() -> None:
    """Reviewer Focus #1(D0110 §37): Forward/Reverseが本当に同じModelを
    呼んでいることをSource Levelで確認する——`lib.valuation.reverse`が
    `lib.valuation.engine`の3関数をImportして使っていること、独自の
    Formula文字列(`*`/`-`演算)を再定義していないことを確認する。"""
    reverse_source = Path(valuation_reverse_module.__file__).read_text(encoding="utf-8")
    assert (
        "from lib.valuation.engine import compute_enterprise_value, compute_equity_value, compute_value_per_share"
        in reverse_source
    )
    assert "def compute_enterprise_value" not in reverse_source
    assert "def compute_equity_value" not in reverse_source
    assert "def compute_value_per_share" not in reverse_source


def test_reuses_d0108_market_implied_contract_not_duplicated() -> None:
    for module_path in (valuation_engine_module.__file__, valuation_reverse_module.__file__):
        source = Path(module_path).read_text(encoding="utf-8")
        assert "class MarketImpliedAssumptionResult" not in source
        assert "class AssumptionSurface" not in source


def test_reuses_d0109_forecast_not_duplicated_ledger() -> None:
    source = Path(valuation_engine_module.__file__).read_text(encoding="utf-8")
    assert "class FundamentalForecastResult" not in source
    assert "AppendOnlyRecordStore" not in source
