"""Standalone synthetic public-API example. No external data or test imports."""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.evaluation.integrity import to_hashable  # noqa: E402
from lib.evidence.thesis_impact import ThesisScenario  # noqa: E402
from lib.forecasting.engine import compute_fundamental_forecast  # noqa: E402
from lib.forecasting.model import AssumptionSource, ForecastAssumption, HistoricalFundamentalBase, ScenarioAssumptions  # noqa: E402
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

T = datetime(2026, 1, 10, tzinfo=UTC)
D = Decimal


def synthetic_inputs():
    """All amounts and evidence are fictional; only BASE changes in replay."""

    def valuation(replay):
        forecast = compute_fundamental_forecast(
            result_id="SYNTHETIC_FORECAST_" + str(replay),
            entity_id="SYNTHETIC",
            target_period="FY_SYNTHETIC",
            requested_metrics=("OPERATING_INCOME",),
            scenario_assumptions=tuple(
                ScenarioAssumptions(
                    scenario=s,
                    assumptions=tuple(
                        ForecastAssumption(
                            name=n,
                            value=D(v),
                            unit="PERCENT",
                            source=AssumptionSource.RESEARCH_JUDGMENT,
                            rationale="synthetic",
                            created_at=T,
                        )
                        for n, v in (("REVENUE_GROWTH", "0"), ("OPERATING_MARGIN", margin))
                    ),
                )
                for s, margin in (
                    (ThesisScenario.BULL, "15"),
                    (ThesisScenario.BASE, "12" if replay else "10"),
                    (ThesisScenario.BEAR, "5"),
                )
            ),
            historical_bases=(
                HistoricalFundamentalBase(
                    entity_id="SYNTHETIC",
                    metric="REVENUE",
                    period="PRIOR",
                    value=D("1000"),
                    unit="JPY",
                    currency="JPY",
                    source_id="SYNTHETIC",
                    available_at=T,
                    provenance_ref="SYNTHETIC",
                ),
            ),
            evidence_cutoff=T,
            research_snapshot_id="SYNTHETIC",
            forecast_created_at=T,
        )
        return evaluate_forward_valuation(
            forecast,
            result_id="SYNTHETIC_VALUATION_" + str(replay),
            multiple=ValuationMultiple(
                value=D("8"),
                source=MultipleSource.RESEARCH_JUDGMENT,
                reference_period="PRIOR",
                available_at=T,
                method_version="SYNTHETIC",
            ),
            balance_sheet=BalanceSheetInputs(
                net_debt=D("50"),
                net_debt_currency="JPY",
                net_debt_available_at=T,
                source_id="SYNTHETIC",
                share_count=D("10"),
                share_count_available_at=T,
            ),
            calculated_at=T,
        )

    baseline, replay = valuation(False), valuation(True)
    exit_at = T + timedelta(days=365)
    terms = SharedTerms(
        price=PriceReference(
            price_id="SYNTHETIC_PRICE",
            entity_id="SYNTHETIC",
            currency="JPY",
            value=D("80"),
            observed_at=T,
            available_at=T,
            source_ref="SYNTHETIC_PRICE_SOURCE",
        ),
        cash=CashTerms(
            dividend=D("3"),
            entry_cost=D("1"),
            exit_cost=D("2"),
            currency="JPY",
            source_ref="SYNTHETIC_CASH",
            available_at=T,
            coverage_start=T,
            coverage_end=exit_at,
        ),
        exit_mapping=ExitMapping(target_period="FY_SYNTHETIC", exit_at=exit_at, evidence_ref="SYNTHETIC_MAPPING", available_at=T),
        basis=ShareBasisAttestation(
            baseline_hash=baseline.record_hash,
            replay_hash=replay.record_hash,
            price_id="SYNTHETIC_PRICE",
            share_count=D("10"),
            price_basis_ref="SYNTHETIC_PRICE_BASIS",
            baseline_basis_ref="SYNTHETIC_BASELINE_BASIS",
            replay_basis_ref="SYNTHETIC_REPLAY_BASIS",
            confirmed=True,
            available_at=T,
        ),
        decision_cutoff=T,
        macro_scenarios=(ThesisScenario.BASE,),
        macro_reference="SYNTHETIC_EXPLICIT_ASSUMPTION",
        synthetic=True,
    )
    return baseline, replay, terms


def run_demo():
    baseline, replay, terms = synthetic_inputs()
    result = compare_scenario_returns(baseline=baseline, replay=replay, terms=terms, calculated_at=T)
    return {"synthetic": True, "empirical_validation": False, "result": to_hashable(result)}


if __name__ == "__main__":
    print(json.dumps(run_demo(), sort_keys=True, ensure_ascii=False))
