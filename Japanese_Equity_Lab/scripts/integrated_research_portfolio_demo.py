"""One synthetic exposure-to-portfolio path through public production APIs.

Prints an audit artifact; never fetches data, saves files or certifies real inputs.
"""

from __future__ import annotations

import argparse
import json
import sys
from decimal import ROUND_HALF_EVEN, Context, Decimal, DivisionByZero, InvalidOperation, Overflow, localcontext
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.company_exposure.bridge import compute_exposure_bridge  # noqa: E402
from lib.company_exposure.model import BridgeStatus  # noqa: E402
from lib.evaluation.integrity import compute_record_hash, to_hashable  # noqa: E402
from lib.portfolio_construction import construct_portfolio, make_construction_request  # noqa: E402
from lib.portfolio_risk import PortfolioPolicy, PortfolioPosition, evaluate_portfolio_risk, make_request  # noqa: E402
from lib.scenario_returns import (  # noqa: E402
    CashTerms,
    ExitMapping,
    PriceReference,
    ShareBasisAttestation,
    SharedTerms,
    compare_scenario_returns,
)
from lib.valuation.engine import evaluate_forward_valuation  # noqa: E402
from lib.valuation.forward_reverse_model import BalanceSheetInputs, MultipleSource, ValuationMultiple  # noqa: E402
from scripts.d0110_demo import synthetic_bridge_request  # noqa: E402

FORMAT_VERSION = "SYNTHETIC_INTEGRATED_RESEARCH_PORTFOLIO_V1"
DECIMAL_CONTRACT = "DECIMAL_50_HALF_EVEN_E999999_V1"


def run_demo(*, future_driver: bool = False, bad_joint_binding: bool = False) -> dict[str, Any]:
    """Use actual bridge forecasts for both valuation arms; fail without downstream output."""
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
        request = synthetic_bridge_request(future_driver=future_driver)
        bridge = compute_exposure_bridge(request)
        report: dict[str, Any] = {
            "format_version": FORMAT_VERSION,
            "decimal_contract": DECIMAL_CONTRACT,
            "synthetic": True,
            "empirical_validation": False,
            "product_acceptance": False,
            "cutoff": request.evidence_cutoff,
            "request": request,
            "bridge": bridge,
            "multiple": None,
            "balance_sheet": None,
            "valuations": None,
            "shared_terms": None,
            "returns": None,
            "desired_request": None,
            "desired_risk": None,
            "construction_request": None,
            "construction_result": None,
            "rejection": None,
            "limitations": (
                "Fictional inputs and caller-attested share basis; no real-company acceptance",
                "Period copper assumption is explicitly supplied, not inferred from event response",
                "No causal effect, probability weighting, execution replay or empirical performance certification",
                "Hashes establish internal lineage, not source truth or independent source arithmetic certification",
                "Standalone synthetic report, not a general real-input parser or persisted replay service",
                "One fictional company plus cash is not diversification or a recommendation",
                "Construction weight changes are policy effects, not macro causal effects",
                "Event observation and macro forecast comparison paths are not certified here",
            ),
        }
        if bridge.status is not BridgeStatus.SUCCESS:
            report["rejection"] = {"phase": "EXPOSURE_BRIDGE", "status": bridge.status.value, "reason": bridge.reason}
        else:
            assert bridge.baseline_forecast is not None and bridge.replay_forecast is not None
            cutoff = request.evidence_cutoff
            multiple = ValuationMultiple(
                value=Decimal("8"),
                source=MultipleSource.PEER_SET,
                reference_period="SYNTHETIC",
                available_at=cutoff,
                method_version="SYNTHETIC_V1",
            )
            balance = BalanceSheetInputs(
                net_debt=Decimal("50"),
                net_debt_currency="JPY",
                net_debt_available_at=cutoff,
                source_id="SYNTHETIC",
                share_count=Decimal("10"),
                share_count_available_at=cutoff,
            )
            valuations = tuple(
                evaluate_forward_valuation(
                    forecast,
                    result_id=f"SYNTHETIC_PATH_VALUATION_{i}",
                    multiple=multiple,
                    balance_sheet=balance,
                    calculated_at=cutoff,
                )
                for i, forecast in enumerate((bridge.baseline_forecast, bridge.replay_forecast))
            )
            baseline, replay = valuations
            terms = SharedTerms(
                price=PriceReference(
                    price_id="SYNTHETIC_PATH_PRICE",
                    entity_id=request.entity_id,
                    currency="JPY",
                    value=Decimal("80"),
                    observed_at=cutoff,
                    available_at=cutoff,
                    source_ref="SYNTHETIC_PRICE_SOURCE",
                ),
                cash=CashTerms(
                    dividend=Decimal("3"),
                    entry_cost=Decimal("1"),
                    exit_cost=Decimal("2"),
                    currency="JPY",
                    source_ref="SYNTHETIC_CASH_ASSUMPTIONS",
                    available_at=cutoff,
                    coverage_start=cutoff,
                    coverage_end=request.period_end,
                ),
                exit_mapping=ExitMapping(
                    target_period=request.forecast_period,
                    exit_at=request.period_end,
                    evidence_ref="SYNTHETIC_FISCAL_EXIT_MAPPING",
                    available_at=cutoff,
                ),
                basis=ShareBasisAttestation(
                    baseline_hash=baseline.record_hash,
                    replay_hash=replay.record_hash,
                    price_id="SYNTHETIC_PATH_PRICE",
                    share_count=Decimal("10"),
                    price_basis_ref="SYNTHETIC_PRICE_BASIS",
                    baseline_basis_ref="SYNTHETIC_BASELINE_BASIS",
                    replay_basis_ref="SYNTHETIC_REPLAY_BASIS",
                    confirmed=True,
                    available_at=cutoff,
                ),
                decision_cutoff=cutoff,
                macro_scenarios=(request.scenario,),
                macro_reference=bridge.record_hash,
                synthetic=True,
            )
            returns = compare_scenario_returns(baseline=baseline, replay=replay, terms=terms, calculated_at=cutoff)
            report.update(multiple=multiple, balance_sheet=balance, valuations=valuations, shared_terms=terms, returns=returns)
            desired = make_request(
                request_id="INTEGRATED_DESIRED_PORTFOLIO",
                positions=(
                    PortfolioPosition(
                        position_id="SYNTHETIC_POSITION",
                        capital_weight=Decimal("0.8"),
                        comparison=returns,
                        sector="SYNTHETIC_METALS",
                        sector_ref="SYNTHETIC_SECTOR_EVIDENCE",
                        sector_available_at=cutoff,
                    ),
                ),
                cash_weight=Decimal("0.2"),
                policy=PortfolioPolicy(
                    policy_id="INTEGRATED_SYNTHETIC_LIMITS",
                    source_ref="EXPLICIT_POLICY",
                    available_at=cutoff,
                    max_company=Decimal("0.5"),
                    max_sector=Decimal("0.6"),
                    minimum_cash=Decimal("0.2"),
                ),
                currency="JPY",
                decision_cutoff=cutoff,
                exit_at=request.period_end,
                joint_scenario_ref="EXPLICIT_SINGLE_COMPANY_JOINT_SCENARIOS",
                joint_scenario_available_at=cutoff,
                joint_comparison_hashes=("WRONG_BINDING" if bad_joint_binding else returns.record_hash,),
                cash_zero_return_ref="EXPLICIT_ZERO_CASH_RETURN_ASSUMPTION_NO_INTEREST_GUARANTEE",
                cash_available_at=cutoff,
                calculated_at=cutoff,
                synthetic=True,
            )
            report["desired_request"] = desired
            try:
                desired_risk = evaluate_portfolio_risk(desired)
            except ValueError as error:
                report["rejection"] = {"phase": "PORTFOLIO_RISK", "status": "INVALID_INPUT", "reason": str(error)}
            else:
                # Declared limit breaches are diagnostic outputs, not malformed inputs.
                report["desired_risk"] = desired_risk
                construction = make_construction_request(
                    request_id="INTEGRATED_CONSTRUCTION",
                    desired=desired,
                    priority=("SYNTHETIC_POSITION",),
                    allocation_quantum=Decimal("0.01"),
                    policy_ref="EXPLICIT_CALLER_PRIORITY_AND_GRID",
                    policy_available_at=cutoff,
                    calculated_at=cutoff,
                )
                report["construction_request"] = construction
                report["construction_result"] = construct_portfolio(construction)
        # Hash precisely the emitted JSON-safe payload, excluding its own hash.
        safe = to_hashable(report)
        assert isinstance(safe, dict)
        safe["artifact_hash"] = compute_record_hash(safe)
        return safe


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--future-driver", action="store_true")
    parser.add_argument("--bad-joint-binding", action="store_true")
    options = parser.parse_args()
    print(
        json.dumps(
            run_demo(future_driver=options.future_driver, bad_joint_binding=options.bad_joint_binding),
            sort_keys=True,
            ensure_ascii=False,
        )
    )
