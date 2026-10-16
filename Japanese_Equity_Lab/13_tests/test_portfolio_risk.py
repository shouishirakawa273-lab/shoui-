"""Exact weights, independent portfolio arithmetic, conditional limits and rejection checks."""

from dataclasses import fields, replace
from datetime import timedelta
from decimal import ROUND_UP, Decimal, Inexact, localcontext
from fractions import Fraction

import pytest
from lib.evaluation.integrity import compute_record_hash, to_hashable, verify_record_integrity
from lib.evidence.thesis_impact import ThesisScenario
from lib.portfolio_risk import evaluate_portfolio_risk, make_request
from scripts.d0112_demo import run_demo, synthetic_request

D = Decimal


def seal(record, **changes):
    updated = replace(record, **changes)
    return replace(updated, record_hash=compute_record_hash({f.name: getattr(updated, f.name) for f in fields(updated)}))


def test_independent_fraction_arithmetic_and_offset_downside():
    request = synthetic_request()
    before = to_hashable(request)
    result = evaluate_portfolio_risk(request)
    with localcontext() as context:
        context.prec = 50
        for output in result.scenarios:
            for side, field in (("baseline", "baseline_net_return"), ("replay", "replay_net_return")):
                contributions = [
                    Fraction(p.capital_weight)
                    * Fraction(
                        getattr(
                            next(s for s in p.comparison.scenarios if s.scenario is output.scenario), side
                        ).net_before_tax_return
                    )
                    for p in request.positions
                ]
                exact = sum(contributions, Fraction(0))
                expected = D(exact.numerator) / D(exact.denominator)
                # Individual product rounding has at most one last-place difference from rational sum.
                assert abs(getattr(output, field) - expected) <= D("1e-49")
            assert output.replay_minus_baseline == output.replay_net_return - output.baseline_net_return
    bear = next(s for s in result.scenarios if s.scenario is ThesisScenario.BEAR)
    assert bear.baseline_net_return > 0
    assert result.baseline_downside == 0
    assert sum(p.capital_weight * p.comparison.baseline_downside for p in request.positions) > 0
    assert result.declared_constraints_pass and not result.breaches
    assert result.cash_weight == D("0.2")
    assert set(result.unsupported_checks) >= {"THEME", "EVENT", "LIQUIDITY", "CORRELATION", "VAR"}
    assert before == to_hashable(request) and verify_record_integrity(result)


def test_exact_limits_and_company_aggregation():
    request = synthetic_request()
    p = request.positions[0]
    positions = (p, replace(p, position_id="ZZ_SECOND", capital_weight=D("0.4")))
    changed = seal(
        request, positions=positions, joint_comparison_hashes=tuple(sorted(x.comparison.record_hash for x in positions))
    )
    result = evaluate_portfolio_risk(changed)
    assert result.company_weights == ((p.comparison.terms.price.entity_id, D("0.8")),)
    assert result.breaches == (f"COMPANY:{p.comparison.terms.price.entity_id}", f"SECTOR:{p.sector}")
    epsilon = D("1e-70")
    with localcontext() as context:
        context.prec = 100
        positions = (
            replace(request.positions[0], capital_weight=D("0.4") + epsilon),
            replace(request.positions[1], capital_weight=D("0.4") - epsilon),
        )
    result = evaluate_portfolio_risk(seal(request, positions=positions))
    assert f"COMPANY:{positions[0].comparison.terms.price.entity_id}" in result.breaches
    assert f"SECTOR:{positions[0].sector}" in result.breaches
    with localcontext() as context:
        context.prec = 100
        overweight = replace(request.positions[0], capital_weight=D("0.4") + epsilon)
    with pytest.raises(ValueError):
        evaluate_portfolio_risk(seal(request, positions=(overweight, request.positions[1])))


def test_all_cash_explicit_empty_binding():
    request = seal(synthetic_request(), positions=(), cash_weight=D(1), joint_comparison_hashes=())
    result = evaluate_portfolio_risk(request)
    assert all(s.baseline_net_return == s.replay_net_return == 0 for s in result.scenarios)
    assert result.company_weights == result.sector_weights == ()
    assert result.declared_constraints_pass and result.baseline_downside == 0


@pytest.mark.parametrize(
    "case",
    [
        "hash",
        "cash_nan",
        "cash_negative",
        "weight_zero",
        "weight_nan",
        "sum",
        "duplicate",
        "unknown_sector",
        "blank_sector_ref",
        "sector_future",
        "same_entity_sector",
        "binding",
        "binding_multiplicity",
        "policy_future",
        "policy_limit",
        "cash_future",
        "joint_future",
        "joint_missing",
        "cutoff_order",
        "naive",
        "mode",
        "comparison_hash",
        "terms_hash",
        "comparison_future",
        "currency",
        "scenario_missing",
        "scenario_duplicate",
        "scenario_nan",
    ],
)
def test_invalid_inputs_fail_closed(case):
    request = synthetic_request()
    p, other = request.positions
    future = request.decision_cutoff + timedelta(seconds=1)
    changed_comparison = p.comparison
    comparison_changes = {
        "comparison_hash": replace(changed_comparison, record_hash="wrong"),
        "terms_hash": seal(changed_comparison, terms_hash="wrong"),
        "comparison_future": seal(changed_comparison, calculated_at=future),
        "currency": seal(
            changed_comparison,
            terms=replace(changed_comparison.terms, price=replace(changed_comparison.terms.price, currency="USD")),
        ),
        "scenario_missing": seal(changed_comparison, scenarios=changed_comparison.scenarios[:2]),
        "scenario_duplicate": seal(changed_comparison, scenarios=(changed_comparison.scenarios[0],) * 3),
        "scenario_nan": seal(
            changed_comparison,
            scenarios=(
                replace(
                    changed_comparison.scenarios[0],
                    baseline=replace(changed_comparison.scenarios[0].baseline, net_before_tax_return=D("NaN")),
                ),
                *changed_comparison.scenarios[1:],
            ),
        ),
    }
    changes = {
        "hash": {"record_hash": "wrong"},
        "cash_nan": {"cash_weight": D("NaN")},
        "cash_negative": {"cash_weight": D(-1)},
        "weight_zero": {"positions": (replace(p, capital_weight=D(0)), other)},
        "weight_nan": {"positions": (replace(p, capital_weight=D("NaN")), other)},
        "sum": {"cash_weight": D("0.1")},
        "duplicate": {"positions": (p, p)},
        "unknown_sector": {"positions": (replace(p, sector="UNKNOWN"), other)},
        "blank_sector_ref": {"positions": (replace(p, sector_ref=""), other)},
        "sector_future": {"positions": (replace(p, sector_available_at=future), other)},
        "same_entity_sector": {"positions": (p, replace(p, position_id=other.position_id, sector="OTHER"))},
        "binding": {"joint_comparison_hashes": ()},
        "binding_multiplicity": {"joint_comparison_hashes": (p.comparison.record_hash,)},
        "policy_future": {"policy": replace(request.policy, available_at=future)},
        "policy_limit": {"policy": replace(request.policy, max_company=D("1.1"))},
        "cash_future": {"cash_available_at": future},
        "joint_future": {"joint_scenario_available_at": future},
        "joint_missing": {"joint_scenario_ref": ""},
        "cutoff_order": {"exit_at": request.decision_cutoff},
        "naive": {"calculated_at": request.calculated_at.replace(tzinfo=None)},
        "mode": {"synthetic": False},
    }
    if case in comparison_changes:
        comp = comparison_changes[case]
        changes[case] = {
            "positions": (replace(p, comparison=comp), other),
            "joint_comparison_hashes": tuple(sorted((comp.record_hash, other.comparison.record_hash))),
        }
    changed = replace(request, **changes[case]) if case == "hash" else seal(request, **changes[case])
    with pytest.raises(ValueError):
        evaluate_portfolio_risk(changed)


def test_context_and_canonical_order_reproducibility():
    request = synthetic_request()
    kwargs = {f.name: getattr(request, f.name) for f in fields(request) if f.name != "record_hash"}
    kwargs["positions"] = tuple(reversed(request.positions))
    kwargs["joint_comparison_hashes"] = tuple(reversed(request.joint_comparison_hashes))
    reordered = make_request(**kwargs)
    assert reordered == request
    expected = evaluate_portfolio_risk(request)
    for precision in (3, 80):
        with localcontext() as context:
            context.prec, context.rounding, context.Emin, context.Emax = precision, ROUND_UP, -5, 5
            context.traps[Inexact] = context.flags[Inexact] = True
            before = context.copy()
            assert evaluate_portfolio_risk(request) == expected
            assert run_demo()["result"] == to_hashable(expected)
            assert context.prec == before.prec and context.rounding == before.rounding
            assert context.traps == before.traps and context.flags == before.flags
    assert run_demo()["empirical_validation"] is False


def test_cash_breach_and_typed_sort_metadata():
    request = synthetic_request()
    result = evaluate_portfolio_risk(seal(request, policy=replace(request.policy, minimum_cash=D("0.3"))))
    assert result.breaches == ("CASH_MINIMUM",)
    kwargs = {f.name: getattr(request, f.name) for f in fields(request) if f.name != "record_hash"}
    kwargs["positions"] = (replace(request.positions[0], position_id=None), request.positions[1])
    with pytest.raises(ValueError):
        make_request(**kwargs)


def test_demo_cli_other_directory(tmp_path):
    import json
    import subprocess
    import sys
    from pathlib import Path

    script = Path(__file__).resolve().parents[1] / "scripts" / "d0112_demo.py"
    process = subprocess.run([sys.executable, str(script)], cwd=tmp_path, capture_output=True, text=True, check=True)
    assert process.stderr == "" and json.loads(process.stdout) == run_demo()
