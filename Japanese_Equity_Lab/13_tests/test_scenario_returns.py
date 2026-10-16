"""Public-API integration and independently stated D0111 ratio checks."""

from dataclasses import asdict, replace
from datetime import timedelta
from decimal import ROUND_UP, Decimal, Inexact, getcontext, localcontext

import pytest
from lib.evaluation.integrity import compute_record_hash, verify_record_integrity
from lib.evidence.thesis_impact import ThesisScenario
from lib.scenario_returns import compare_scenario_returns
from scripts.d0111_demo import T, run_demo, synthetic_inputs

D = Decimal


def rehash(record, **changes):
    updated = replace(record, **changes)
    return replace(
        updated, record_hash=compute_record_hash({k: getattr(updated, k) for k in asdict(updated) if k != "record_hash"})
    )


def evaluate(baseline, replay, terms):
    return compare_scenario_returns(baseline=baseline, replay=replay, terms=terms, calculated_at=T)


def test_independent_formula_and_input_integrity():
    b, r, t = synthetic_inputs()
    before = (b.record_hash, r.record_hash, compute_record_hash({"terms": t}))
    result = evaluate(b, r, t)
    with localcontext() as ctx:
        ctx.prec = 50
        base = next(s for s in result.scenarios if s.scenario is ThesisScenario.BASE)
        assert base.baseline.valuation_gap == D("-5") / 80
        assert base.baseline.gross_return == D("-2") / 80
        assert base.baseline.net_before_tax_return == D("-5") / 81
        assert base.replay.net_before_tax_return == D("11") / 81
        assert base.replay_minus_baseline.net_before_tax_return == D("11") / 81 - D("-5") / 81
        assert result.baseline_downside == D("45") / 81
        assert result.replay_downside == result.baseline_downside
        assert result.downside_delta == 0
    assert verify_record_integrity(result)
    assert before == (b.record_hash, r.record_hash, compute_record_hash({"terms": t}))


@pytest.mark.parametrize(
    "case",
    [
        "price_zero",
        "price_negative",
        "price_nan",
        "cash_missing",
        "cash_negative",
        "cash_infinity",
        "cash_currency",
        "cash_future",
        "cash_coverage",
        "price_future",
        "price_order",
        "price_naive",
        "mapping_future",
        "mapping_period",
        "exit_order",
        "basis_unknown",
        "basis_hash",
        "basis_price",
        "basis_shares",
        "basis_reference",
        "basis_future",
        "mode",
        "roster_empty",
        "roster_duplicate",
        "roster_string",
    ],
)
def test_terms_reject_each_invalid_input(case):
    b, r, t = synthetic_inputs()
    future = T + timedelta(seconds=1)
    changes = {
        "price_zero": {"price": replace(t.price, value=D(0))},
        "price_negative": {"price": replace(t.price, value=D(-1))},
        "price_nan": {"price": replace(t.price, value=D("NaN"))},
        "cash_missing": {"cash": replace(t.cash, dividend=None)},
        "cash_negative": {"cash": replace(t.cash, entry_cost=D(-1))},
        "cash_infinity": {"cash": replace(t.cash, exit_cost=D("Infinity"))},
        "cash_currency": {"cash": replace(t.cash, currency="USD")},
        "cash_future": {"cash": replace(t.cash, available_at=future)},
        "cash_coverage": {"cash": replace(t.cash, coverage_start=future)},
        "price_future": {"price": replace(t.price, available_at=future)},
        "price_order": {"price": replace(t.price, observed_at=future)},
        "price_naive": {"price": replace(t.price, observed_at=T.replace(tzinfo=None))},
        "mapping_future": {"exit_mapping": replace(t.exit_mapping, available_at=future)},
        "mapping_period": {"exit_mapping": replace(t.exit_mapping, target_period="OTHER")},
        "exit_order": {"exit_mapping": replace(t.exit_mapping, exit_at=T)},
        "basis_unknown": {"basis": replace(t.basis, confirmed=False)},
        "basis_hash": {"basis": replace(t.basis, baseline_hash="wrong")},
        "basis_price": {"basis": replace(t.basis, price_id="wrong")},
        "basis_shares": {"basis": replace(t.basis, share_count=D(11))},
        "basis_reference": {"basis": replace(t.basis, price_basis_ref="")},
        "basis_future": {"basis": replace(t.basis, available_at=future)},
        "mode": {"synthetic": None},
        "roster_empty": {"macro_scenarios": ()},
        "roster_duplicate": {"macro_scenarios": (ThesisScenario.BASE, ThesisScenario.BASE)},
        "roster_string": {"macro_scenarios": ("BASE",)},
    }
    with pytest.raises(ValueError):
        evaluate(b, r, replace(t, **changes[case]))


@pytest.mark.parametrize(
    "case",
    [
        "hash",
        "entity",
        "currency",
        "model",
        "version",
        "period",
        "cutoff",
        "future_calculation",
        "multiple",
        "debt",
        "shares",
        "scenario_duplicate",
        "scenario_currency",
        "oi_nan",
        "ev_infinity",
        "equity_nan",
        "per_share_missing",
        "per_share_negative",
        "non_target",
    ],
)
def test_valuation_reject_each_invalid_input(case):
    b, r, t = synthetic_inputs()
    s = r.scenarios[0]
    changes = {
        "hash": {"record_hash": "tamper"},
        "entity": {"entity_id": "OTHER"},
        "currency": {"currency": "USD"},
        "model": {"valuation_model_id": "OTHER"},
        "version": {"valuation_model_version": "OTHER"},
        "period": {"target_period": "OTHER"},
        "cutoff": {"evidence_cutoff": T - timedelta(seconds=1)},
        "future_calculation": {"calculated_at": T + timedelta(seconds=1)},
        "multiple": {"multiple_used": replace(r.multiple_used, value=D(9))},
        "debt": {"balance_sheet_used": replace(r.balance_sheet_used, net_debt=D(51))},
        "shares": {"balance_sheet_used": replace(r.balance_sheet_used, share_count=D(11))},
        "scenario_duplicate": {"scenarios": (s, s, s)},
        "scenario_currency": {"scenarios": (replace(s, currency="USD"), *r.scenarios[1:])},
        "oi_nan": {"scenarios": (replace(s, input_operating_income=D("NaN")), *r.scenarios[1:])},
        "ev_infinity": {"scenarios": (replace(s, estimated_enterprise_value=D("Infinity")), *r.scenarios[1:])},
        "equity_nan": {"scenarios": (replace(s, estimated_equity_value=D("NaN")), *r.scenarios[1:])},
        "per_share_missing": {"scenarios": (replace(s, estimated_value_per_share=None), *r.scenarios[1:])},
        "per_share_negative": {"scenarios": (replace(s, estimated_value_per_share=D(-1)), *r.scenarios[1:])},
        "non_target": {
            "scenarios": tuple(
                replace(x, estimated_value_per_share=D(99)) if x.scenario is ThesisScenario.BULL else x for x in r.scenarios
            )
        },
    }
    changed = replace(r, **changes[case]) if case == "hash" else rehash(r, **changes[case])
    terms = replace(t, basis=replace(t.basis, replay_hash=changed.record_hash))
    with pytest.raises(ValueError):
        evaluate(b, changed, terms)


def test_decimal_context_independence_and_demo():
    b, r, t = synthetic_inputs()
    expected = evaluate(b, r, t)
    for precision in (3, 80):
        with localcontext() as ctx:
            ctx.prec = precision
            ctx.rounding = ROUND_UP
            ctx.Emin = -5
            ctx.Emax = 5
            ctx.clamp = 1
            ctx.capitals = 0
            ctx.traps[Inexact] = True
            ctx.flags[Inexact] = True
            before = ctx.copy()
            assert evaluate(b, r, t) == expected
            assert ctx.prec == before.prec and ctx.rounding == before.rounding
            assert ctx.traps == before.traps and ctx.flags == before.flags
            assert (ctx.Emin, ctx.Emax, ctx.clamp, ctx.capitals) == (before.Emin, before.Emax, before.clamp, before.capitals)
    assert getcontext().prec > 0
    artifact = run_demo()
    assert artifact["synthetic"] is True and artifact["empirical_validation"] is False


@pytest.mark.parametrize(
    "case", ["multiple_future", "debt_future", "shares_missing", "shares_future", "bs_currency", "missing_scenario"]
)
def test_valuation_input_availability_and_completeness(case):
    b, r, t = synthetic_inputs()
    bs = r.balance_sheet_used
    future = T + timedelta(seconds=1)
    changes = {
        "multiple_future": {"multiple_used": replace(r.multiple_used, available_at=future)},
        "debt_future": {"balance_sheet_used": replace(bs, net_debt_available_at=future)},
        "shares_missing": {"balance_sheet_used": replace(bs, share_count=None, share_count_available_at=None)},
        "shares_future": {"balance_sheet_used": replace(bs, share_count_available_at=future)},
        "bs_currency": {"balance_sheet_used": replace(bs, net_debt_currency="USD")},
        "missing_scenario": {"scenarios": r.scenarios[:2]},
    }
    changed = rehash(r, **changes[case])
    with pytest.raises(ValueError):
        evaluate(b, changed, replace(t, basis=replace(t.basis, replay_hash=changed.record_hash)))


def test_zero_valuation_allowed_and_non_success_refused():
    from lib.forecasting.engine import compute_fundamental_forecast
    from lib.valuation.engine import evaluate_forward_valuation

    b, r, t = synthetic_inputs()
    changed = rehash(
        r,
        scenarios=tuple(
            replace(s, estimated_value_per_share=D(0)) if s.scenario is ThesisScenario.BASE else s for s in r.scenarios
        ),
    )
    result = evaluate(b, changed, replace(t, basis=replace(t.basis, replay_hash=changed.record_hash)))
    assert next(s for s in result.scenarios if s.scenario is ThesisScenario.BASE).replay.valuation_gap == -1
    forecast = compute_fundamental_forecast(
        result_id="MISSING_INPUT",
        entity_id="SYNTHETIC",
        target_period="FY_SYNTHETIC",
        requested_metrics=("OPERATING_INCOME",),
        scenario_assumptions=(),
        historical_bases=(),
        evidence_cutoff=T,
        research_snapshot_id="SYNTHETIC",
        forecast_created_at=T,
    )
    failed = evaluate_forward_valuation(
        forecast, result_id="MISSING_FORECAST", multiple=r.multiple_used, balance_sheet=r.balance_sheet_used, calculated_at=T
    )
    with pytest.raises(ValueError):
        evaluate(b, failed, replace(t, basis=replace(t.basis, replay_hash=failed.record_hash)))
