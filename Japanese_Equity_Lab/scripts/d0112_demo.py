"""Two fictional companies under explicitly joint conditional scenarios, never an allocation recommendation."""

from __future__ import annotations

import json
import sys
from dataclasses import fields, replace
from decimal import ROUND_HALF_EVEN, Context, Decimal, DivisionByZero, InvalidOperation, Overflow, localcontext
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.evaluation.integrity import compute_record_hash, to_hashable  # noqa: E402
from lib.portfolio_risk import PortfolioPolicy, PortfolioPosition, evaluate_portfolio_risk, make_request  # noqa: E402
from lib.scenario_returns import compare_scenario_returns  # noqa: E402
from scripts.d0111_demo import T, synthetic_inputs  # noqa: E402


def _rehash(record):
    return replace(record, record_hash=compute_record_hash({f.name: getattr(record, f.name) for f in fields(record)}))


def _synthetic_request():
    """Synthetic clones preserve economic inputs; entity and source lineage are explicitly renamed."""
    positions = []
    for company, price, sector in (("SYNTHETIC_A", "80", "METALS"), ("SYNTHETIC_B", "20", "INDUSTRIAL")):
        b, r, terms = synthetic_inputs()
        b = _rehash(
            replace(
                b, entity_id=company, result_id=f"{company}:BASELINE", input_forecast_reference=f"{company}:FORECAST_BASELINE"
            )
        )
        r = _rehash(
            replace(r, entity_id=company, result_id=f"{company}:REPLAY", input_forecast_reference=f"{company}:FORECAST_REPLAY")
        )
        price_id = f"{company}:PRICE"
        terms = replace(
            terms,
            price=replace(terms.price, entity_id=company, value=Decimal(price), price_id=price_id),
            basis=replace(terms.basis, baseline_hash=b.record_hash, replay_hash=r.record_hash, price_id=price_id),
        )
        comparison = compare_scenario_returns(baseline=b, replay=r, terms=terms, calculated_at=T)
        positions.append(
            PortfolioPosition(
                position_id=company,
                capital_weight=Decimal("0.4"),
                comparison=comparison,
                sector=sector,
                sector_ref=f"{company}:SYNTHETIC_CLASSIFICATION",
                sector_available_at=T,
            )
        )
    return make_request(
        request_id="SYNTHETIC_PORTFOLIO",
        positions=tuple(positions),
        cash_weight=Decimal("0.2"),
        policy=PortfolioPolicy(
            policy_id="SYNTHETIC_POLICY",
            source_ref="EXPLICIT_SYNTHETIC_LIMITS",
            available_at=T,
            max_company=Decimal("0.4"),
            max_sector=Decimal("0.4"),
            minimum_cash=Decimal("0.2"),
        ),
        currency="JPY",
        decision_cutoff=T,
        exit_at=positions[0].comparison.terms.exit_mapping.exit_at,
        joint_scenario_ref="SYNTHETIC_JOINT_ASSUMPTIONS_SAME_3_SCENARIOS_EXPLICITLY_APPLY_TO_BOTH",
        joint_scenario_available_at=T,
        joint_comparison_hashes=tuple(p.comparison.record_hash for p in positions),
        cash_zero_return_ref="EXPLICIT_SYNTHETIC_ZERO_CASH_RETURN_NO_INTEREST_GUARANTEE",
        cash_available_at=T,
        calculated_at=T,
        synthetic=True,
    )


def synthetic_request():
    context = Context(
        prec=50,
        rounding=ROUND_HALF_EVEN,
        Emin=-999999,
        Emax=999999,
        capitals=1,
        clamp=0,
        flags=[],
        traps=[InvalidOperation, DivisionByZero, Overflow],
    )
    with localcontext(context):
        return _synthetic_request()


def run_demo():
    request = synthetic_request()
    return {
        "synthetic": True,
        "empirical_validation": False,
        "limitations": "Synthetic renamed lineage; no independent source, correlation or risk calibration certification",
        "request": to_hashable(request),
        "result": to_hashable(evaluate_portfolio_risk(request)),
    }


if __name__ == "__main__":
    print(json.dumps(run_demo(), sort_keys=True, ensure_ascii=False))
