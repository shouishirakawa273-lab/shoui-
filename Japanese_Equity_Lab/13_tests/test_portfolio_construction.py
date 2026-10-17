"""Exact independent allocation cases and fail-closed desired-input handling."""

from dataclasses import fields, replace
from datetime import timedelta
from decimal import ROUND_UP, Decimal, Inexact, localcontext
from fractions import Fraction

import pytest
from lib.evaluation.integrity import compute_record_hash, to_hashable, verify_record_integrity
from lib.portfolio_construction import construct_portfolio
from lib.portfolio_risk import make_request
from scripts.d0113_demo import run_demo, synthetic_construction_request

D = Decimal


def seal(record, **changes):
    changed = replace(record, **changes)
    return replace(changed, record_hash=compute_record_hash({f.name: getattr(changed, f.name) for f in fields(changed)}))


def desired_with(request, **changes):
    kwargs = {f.name: getattr(request.desired, f.name) for f in fields(request.desired) if f.name != "record_hash"}
    kwargs.update(changes)
    return seal(request, desired=make_request(**kwargs))


def test_caps_exact_conservation_subset_and_no_input_mutation():
    request = synthetic_construction_request()
    before = to_hashable(request)
    result = construct_portfolio(request)
    assert [a.allocated_weight for a in result.audit] == [D("0.3"), D("0.3")]
    assert [a.reduction for a in result.audit] == [D("0.1"), D("0.1")]
    assert all("COMPANY_LIMIT" in a.reasons and "SECTOR_LIMIT" in a.reasons for a in result.audit)
    assert result.output_request.cash_weight == D("0.4") and result.released_cash == D("0.2")
    assert (
        sum((Fraction(p.capital_weight) for p in result.output_request.positions), Fraction(result.output_request.cash_weight))
        == 1
    )
    assert result.output_risk.declared_constraints_pass
    assert result.output_request.joint_scenario_available_at == request.desired.joint_scenario_available_at
    assert request.desired.record_hash in result.output_request.joint_scenario_ref
    assert request.desired.joint_scenario_ref in result.output_request.joint_scenario_ref
    assert result.output_request.cash_zero_return_ref == request.desired.cash_zero_return_ref
    for selected in result.output_request.positions:
        original = next(p for p in request.desired.positions if p.position_id == selected.position_id)
        assert replace(selected, capital_weight=original.capital_weight) == original
        assert selected.capital_weight <= original.capital_weight
    assert verify_record_integrity(result) and verify_record_integrity(result.output_request)
    assert to_hashable(request) == before


def test_priority_sector_competition_and_budget_limit():
    request = synthetic_construction_request()
    positions = tuple(replace(p, sector="JOINT") for p in request.desired.positions)
    request = desired_with(
        request, positions=positions, policy=replace(request.desired.policy, max_company=D(1), max_sector=D("0.5"))
    )
    result = construct_portfolio(request)
    assert [a.allocated_weight for a in result.audit] == [D("0.4"), D("0.1")]
    reverse = construct_portfolio(seal(request, priority=tuple(reversed(request.priority))))
    assert reverse.output_request.positions[0].capital_weight == D("0.1")
    assert reverse.record_hash != result.record_hash
    budget = desired_with(request, policy=replace(request.desired.policy, max_sector=D(1), minimum_cash=D("0.6")))
    assert [a.allocated_weight for a in construct_portfolio(budget).audit] == [D("0.4"), D(0)]


def test_same_company_grid_and_non_grid_cash():
    request = synthetic_construction_request()
    p = request.desired.positions[0]
    positions = (replace(p, position_id="A", capital_weight=D("0.4001")), replace(p, position_id="B", capital_weight=D("0.3998")))
    request = desired_with(
        request,
        positions=positions,
        cash_weight=D("0.2001"),
        joint_comparison_hashes=tuple(p.comparison.record_hash for p in positions),
        policy=replace(request.desired.policy, max_company=D("0.5"), max_sector=D(1)),
    )
    request = seal(request, priority=("A", "B"), allocation_quantum=D("0.01"))
    result = construct_portfolio(request)
    assert [a.allocated_weight for a in result.audit] == [D("0.4"), D("0.1")]
    assert "GRID_FLOOR" in result.audit[0].reasons and "COMPANY_LIMIT" in result.audit[1].reasons
    assert result.output_request.cash_weight == D("0.5") >= request.desired.cash_weight
    with localcontext() as context:
        context.prec = 100
        tiny = D("0.3") - D("1e-70")
    request = desired_with(request, policy=replace(request.desired.policy, max_company=tiny))
    assert construct_portfolio(request).audit[0].allocated_weight == D("0.29")


def test_zero_allocation_and_all_cash():
    request = synthetic_construction_request()
    request = desired_with(request, policy=replace(request.desired.policy, max_company=D(0)))
    result = construct_portfolio(request)
    assert result.output_request.positions == () and result.output_request.cash_weight == 1
    assert result.output_request.joint_comparison_hashes == ()
    cash = desired_with(request, positions=(), cash_weight=D(1), joint_comparison_hashes=())
    cash = seal(cash, priority=())
    assert construct_portfolio(cash).audit == ()


@pytest.mark.parametrize(
    "case",
    [
        "hash",
        "desired_hash",
        "priority_missing",
        "priority_duplicate",
        "priority_unknown",
        "priority_list",
        "quantum_nan",
        "quantum_float",
        "quantum_wrong",
        "quantum_small",
        "quantum_zero",
        "policy_future",
        "calculated_before",
        "naive",
        "ref_missing",
        "id_type",
        "invalid_zero_allocation_constituent",
    ],
)
def test_reject_cases(case):
    request = synthetic_construction_request()
    future = request.desired.decision_cutoff + timedelta(seconds=1)
    desired = request.desired
    bad = seal(
        desired,
        policy=replace(desired.policy, max_company=D(0)),
        positions=(
            replace(desired.positions[0], comparison=replace(desired.positions[0].comparison, record_hash="bad")),
            desired.positions[1],
        ),
    )
    changes = {
        "hash": {"record_hash": "bad"},
        "desired_hash": {"desired": replace(desired, record_hash="bad")},
        "priority_missing": {"priority": request.priority[:1]},
        "priority_duplicate": {"priority": request.priority[:1] * 2},
        "priority_unknown": {"priority": ("OTHER", request.priority[1])},
        "priority_list": {"priority": list(request.priority)},
        "quantum_nan": {"allocation_quantum": D("NaN")},
        "quantum_float": {"allocation_quantum": 0.1},
        "quantum_wrong": {"allocation_quantum": D("0.03")},
        "quantum_small": {"allocation_quantum": D("1e-13")},
        "quantum_zero": {"allocation_quantum": D(0)},
        "policy_future": {"policy_available_at": future},
        "calculated_before": {"calculated_at": desired.calculated_at - timedelta(seconds=1)},
        "naive": {"calculated_at": request.calculated_at.replace(tzinfo=None)},
        "ref_missing": {"policy_ref": ""},
        "id_type": {"request_id": None},
        "invalid_zero_allocation_constituent": {"desired": bad},
    }
    changed = replace(request, **changes[case]) if case == "hash" else seal(request, **changes[case])
    with pytest.raises(ValueError):
        construct_portfolio(changed)


def test_context_order_hash_and_cli(tmp_path):
    import json
    import subprocess
    import sys
    from pathlib import Path

    request = synthetic_construction_request()
    expected = construct_portfolio(request)
    reordered = desired_with(request, positions=tuple(reversed(request.desired.positions)))
    assert reordered == request and construct_portfolio(reordered) == expected
    for precision in (3, 80):
        with localcontext() as context:
            context.prec, context.rounding, context.Emin, context.Emax = precision, ROUND_UP, -5, 5
            context.traps[Inexact] = context.flags[Inexact] = True
            before = context.copy()
            assert construct_portfolio(request) == expected
            assert run_demo()["result"] == to_hashable(expected)
            assert context.prec == before.prec and context.rounding == before.rounding
            assert context.flags == before.flags and context.traps == before.traps
    script = Path(__file__).resolve().parents[1] / "scripts" / "d0113_demo.py"
    process = subprocess.run([sys.executable, str(script)], cwd=tmp_path, capture_output=True, text=True, check=True)
    assert process.stderr == "" and json.loads(process.stdout) == run_demo()
