"""Deterministic synthetic D0110 walkthrough; run this file from any directory.

The observed FX response is NOT converted into a company driver. The copper
research-period assumption is independently supplied, with synthetic evidence.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.company_exposure.bridge import baseline_input_hash, compute_exposure_bridge  # noqa: E402
from lib.company_exposure.model import (  # noqa: E402
    BaselineCoverage,
    BridgeRequest,
    CompanyExposure,
    DriverAssumption,
    ExposureCondition,
    ExposureSource,
)
from lib.evaluation.integrity import to_hashable  # noqa: E402
from lib.evaluation.model import (  # noqa: E402
    EvaluationMetric,
    ForecastShape,
    ScalarForecast,
    build_evaluation_contract,
    build_prediction_record,
    build_research_snapshot,
)
from lib.event_responses.measurement import link_surprise_response, measure_event_window  # noqa: E402
from lib.event_responses.model import (  # noqa: E402
    EventWindowSpec,
    MarketObservation,
    MeasureKind,
    ObservationSeriesKey,
    WindowKind,
)
from lib.evidence.model import DataLayer, EvidenceRecord, EvidenceType  # noqa: E402
from lib.evidence.thesis_impact import ThesisScenario  # noqa: E402
from lib.forecasting.model import (  # noqa: E402
    AssumptionSource,
    ForecastAssumption,
    HistoricalFundamentalBase,
    ScenarioAssumptions,
)
from lib.macro_events.model import build_macro_consensus_snapshot, build_macro_event, build_macro_first_release  # noqa: E402
from lib.macro_events.surprise import CALC_RULE_ACTUAL_MINUS_EXPECTED_PP_V1, compute_macro_surprise  # noqa: E402
from lib.macro_experiments.comparison import MacroComparisonSample, compare_macro_forecasts, register_macro_plan  # noqa: E402
from lib.sources.catalog import DataCapability, PrimaryOrSecondary, SourceAuthorityClass, SourceMetadata  # noqa: E402
from lib.valuation.engine import evaluate_forward_valuation  # noqa: E402
from lib.valuation.forward_reverse_model import BalanceSheetInputs, MultipleSource, ValuationMultiple  # noqa: E402

T = datetime(2026, 1, 10, 12, tzinfo=UTC)
OLD = T - timedelta(days=1)
D = Decimal


def synthetic_bridge_request(*, future_driver: bool = False) -> BridgeRequest:
    """Explicit, standalone fixture; never imports test helpers or real disclosures."""
    entity = "SYNTHETIC_COMPANY"
    start, end = T + timedelta(days=1), T + timedelta(days=366)
    evidence = EvidenceRecord(
        evidence_id="SYNTHETIC_E",
        evidence_type=EvidenceType.CLAIM,
        layer=DataLayer.RAW,
        capability=DataCapability.FUNDAMENTAL,
        content="Synthetic sensitivity, not an actual company disclosure",
        related_codes=(entity,),
        source=SourceMetadata(
            source_id="SYNTHETIC",
            source_type="COMPANY_IR",
            provider_name="synthetic",
            source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
            primary_or_secondary=PrimaryOrSecondary.PRIMARY,
            retrieved_at=OLD,
            published_at=OLD,
            available_at=OLD,
            source_url="https://example.invalid/synthetic",
        ),
    )
    condition = ExposureCondition(driver="COPPER", level=D("100"), unit="USD/metric_tonne")
    exposure = CompanyExposure(
        exposure_id="SYNTHETIC_COPPER",
        version="1",
        entity_id=entity,
        driver="COPPER",
        driver_unit="USD/metric_tonne",
        driver_step=D("10"),
        sensitivity_amount=D("20"),
        profit_unit="JPY",
        currency="JPY",
        profit_metric="OPERATING_INCOME",
        scope="CONSOLIDATED",
        forecast_period="FY_SYNTHETIC",
        applicable_from=start,
        applicable_until=end,
        minimum_level=D("1"),
        maximum_level=D("1000"),
        base_conditions=(condition,),
        other_base_assumptions=(("hedging", "synthetic fixed"),),
        source_type=ExposureSource.COMPANY_DISCLOSED,
        source_id="SYNTHETIC",
        source_url="https://example.invalid/synthetic",
        source_locator="synthetic table",
        evidence_ids=(evidence.evidence_id,),
        disclosed_at=OLD,
        available_at=OLD,
        interaction_group="synthetic",
        coverage_keys=("copper-profit",),
        limitations="Synthetic linear example only",
    )
    driver = DriverAssumption(
        assumption_id="SYNTHETIC_DRIVER",
        entity_id=entity,
        forecast_period="FY_SYNTHETIC",
        scenario=ThesisScenario.BASE,
        driver="COPPER",
        unit="USD/metric_tonne",
        baseline_level=D("100"),
        scenario_level=D("110"),
        available_at=T + timedelta(seconds=1) if future_driver else OLD,
        created_at=OLD,
        evidence_ids=(evidence.evidence_id,),
        rationale="Independent research-period assumption, not event response",
    )
    scenarios = tuple(
        ScenarioAssumptions(
            scenario=s,
            assumptions=tuple(
                ForecastAssumption(
                    name=name,
                    value=D(value),
                    unit="PERCENT",
                    source=AssumptionSource.RESEARCH_JUDGMENT,
                    evidence_ids=(),
                    rationale="synthetic baseline",
                    created_at=OLD,
                )
                for name, value in (("REVENUE_GROWTH", "0"), ("OPERATING_MARGIN", "10"))
            ),
        )
        for s in (ThesisScenario.BULL, ThesisScenario.BASE, ThesisScenario.BEAR)
    )
    bases = (
        HistoricalFundamentalBase(
            entity_id=entity,
            metric="REVENUE",
            period="PRIOR_SYNTHETIC",
            value=D("1000"),
            unit="JPY",
            currency="JPY",
            source_id="SYNTHETIC",
            available_at=OLD,
            provenance_ref=evidence.evidence_id,
        ),
    )
    coverage = BaselineCoverage(
        entity_id=entity,
        forecast_period="FY_SYNTHETIC",
        scenario=ThesisScenario.BASE,
        levels=(condition,),
        other_base_assumptions=(("hedging", "synthetic fixed"),),
        applied_increment_keys=(),
        complete=True,
        evidence_ids=(evidence.evidence_id,),
        rationale="Synthetic complete coverage",
        available_at=OLD,
        created_at=OLD,
        baseline_input_hash=baseline_input_hash(scenarios, bases),
    )
    return BridgeRequest(
        request_id="SYNTHETIC_BRIDGE",
        entity_id=entity,
        forecast_period="FY_SYNTHETIC",
        scenario=ThesisScenario.BASE,
        period_start=start,
        period_end=end,
        evidence_cutoff=T,
        created_at=T,
        research_snapshot_id="SYNTHETIC_SNAPSHOT",
        exposures=(exposure,),
        drivers=(driver,),
        coverage=coverage,
        baseline_scenarios=scenarios,
        historical_bases=bases,
        evidence_records=(evidence,),
    )


def run_demo(*, future_consensus: bool = False, future_post: bool = False, future_driver: bool = False) -> dict[str, Any]:
    """Return one reproducible artifact, including refusals instead of fabricated output."""
    event = build_macro_event(
        event_id="SYNTHETIC_CPI",
        event_type="CPI",
        jurisdiction="US",
        scheduled_at=T,
        event_period="2026-01",
        source_id="SYNTHETIC",
        schedule_available_at=OLD,
        created_at=OLD,
    )
    consensus = build_macro_consensus_snapshot(
        consensus_snapshot_id="SYNTHETIC_CONSENSUS",
        event_id=event.event_id,
        dimension="HEADLINE_YOY",
        value=D("3.1"),
        unit="PERCENT",
        consensus_snapshot_at=T - timedelta(minutes=5),
        available_at=T + timedelta(seconds=1) if future_consensus else T - timedelta(minutes=5),
        created_at=T - timedelta(minutes=5),
        provider="SYNTHETIC",
        source_id="SYNTHETIC",
    )
    release = build_macro_first_release(
        release_id="SYNTHETIC_RELEASE",
        event_id=event.event_id,
        dimension="HEADLINE_YOY",
        actual_first_release=D("3.3"),
        unit="PERCENT",
        actual_public_at=T,
        available_at=T,
        created_at=T,
        source_id="SYNTHETIC",
    )
    surprise = compute_macro_surprise(
        surprise_id="SYNTHETIC_SURPRISE",
        event=event,
        consensus=consensus,
        first_release=release,
        calculation_rule_id=CALC_RULE_ACTUAL_MINUS_EXPECTED_PP_V1,
        calculated_at=T,
        decision_at=T,
    )
    key = ObservationSeriesKey(
        instrument_id="USDJPY",
        instrument_definition=(("base", "USD"), ("quote", "JPY")),
        measure_kind=MeasureKind.PRICE,
        unit="JPY/USD",
        quote_convention="MID",
        source_id="SYNTHETIC",
    )
    cutoff = T + timedelta(minutes=6)
    points = (
        MarketObservation(
            observation_id="PRE",
            series=key,
            value=D("150"),
            observed_at=T - timedelta(seconds=1),
            available_at=T - timedelta(seconds=1),
        ),
        MarketObservation(
            observation_id="POST",
            series=key,
            value=D("151.5"),
            observed_at=T + timedelta(minutes=5),
            available_at=cutoff + timedelta(seconds=1) if future_post else T + timedelta(minutes=5),
        ),
    )
    response = measure_event_window(
        response_id="SYNTHETIC_RESPONSE",
        event=event,
        first_release=release,
        series=key,
        window=EventWindowSpec(
            window_id="5M",
            kind=WindowKind.FIVE_MINUTES,
            policy_version="V1",
            pre_max_age=timedelta(seconds=10),
            post_max_lag=timedelta(seconds=5),
        ),
        observations=points,
        evaluation_cutoff=cutoff,
        calculated_at=cutoff,
    )
    link = None
    if surprise.surprise is not None:
        link = link_surprise_response(
            link_id="SYNTHETIC_LINK",
            response=response,
            event=event,
            anchor_release=release,
            surprise=surprise.surprise,
            consensus=consensus,
            first_release=release,
            link_cutoff=cutoff,
            linked_at=cutoff,
        )
    bridge = compute_exposure_bridge(synthetic_bridge_request(future_driver=future_driver))
    valuations = []
    for i, forecast in enumerate((bridge.baseline_forecast, bridge.replay_forecast)):
        if forecast is not None:
            valuations.append(
                evaluate_forward_valuation(
                    forecast,
                    result_id=f"SYNTHETIC_VALUATION_{i}",
                    calculated_at=T,
                    multiple=ValuationMultiple(
                        value=D("8"),
                        source=MultipleSource.PEER_SET,
                        reference_period="SYNTHETIC",
                        available_at=OLD,
                        method_version="SYNTHETIC_V1",
                    ),
                    balance_sheet=BalanceSheetInputs(
                        net_debt=D("50"),
                        net_debt_currency="JPY",
                        net_debt_available_at=OLD,
                        source_id="SYNTHETIC",
                        share_count=D("10"),
                        share_count_available_at=OLD,
                    ),
                )
            )
    registered = OLD + timedelta(hours=1)
    contract = build_evaluation_contract(
        evaluation_contract_id="SYNTHETIC_CONTRACT",
        evaluation_contract_version=1,
        target="HEADLINE_YOY",
        target_period=event.event_period,
        actual_truth_description="Caller-declared synthetic first release",
        metric=EvaluationMetric.ABSOLUTE_ERROR,
        evaluable_at_policy="record maturity",
        created_at=registered,
    )
    plan = register_macro_plan(
        experiment_id="SYNTHETIC_EXPERIMENT",
        event_type="CPI",
        dimension="HEADLINE_YOY",
        unit="PERCENT",
        entity_id="US",
        model_version="SYNTHETIC_V1",
        event_ids=(event.event_id,),
        contracts=(contract,),
        minimum_samples=2,
        synthetic=True,
        registered_at=registered,
        window_start=registered + timedelta(hours=1),
        window_end=T + timedelta(days=1),
    )
    snapshot = build_research_snapshot(
        snapshot_id="SYNTHETIC_MACRO_SNAPSHOT",
        entity_id="US",
        evidence_cutoff=T - timedelta(minutes=10),
        research_artifact_id="SYNTHETIC_RESEARCH",
        research_artifact_version=1,
        created_at=T - timedelta(minutes=10),
    )
    prediction = build_prediction_record(
        prediction_id="SYNTHETIC_PREDICTION",
        entity_id="US",
        target="HEADLINE_YOY",
        target_period=event.event_period,
        forecast_shape=ForecastShape.SCALAR,
        scalar_forecast=ScalarForecast(value=D("3.2"), unit="PERCENT"),
        created_at=T - timedelta(minutes=9),
        evidence_cutoff=snapshot.evidence_cutoff,
        research_snapshot_id=snapshot.snapshot_id,
        model_version="SYNTHETIC_V1",
        research_pipeline_version="SYNTHETIC_V1",
        evaluation_contract_id=contract.evaluation_contract_id,
    )
    comparison = compare_macro_forecasts(
        plan=plan,
        samples=(
            MacroComparisonSample(
                event=event, consensus=consensus, release=release, prediction=prediction, snapshot=snapshot, synthetic=True
            ),
        ),
        evaluated_at=cutoff,
    )
    return {
        "synthetic": True,
        "empirical_certified": False,
        "d0110_1": to_hashable(surprise),
        "d0110_2": {"response": to_hashable(response), "link": to_hashable(link)},
        "d0110_3": {"bridge": to_hashable(bridge), "valuations": to_hashable(valuations)},
        "d0110_4": to_hashable(comparison),
        "limitations": [
            "Synthetic functionality only; not historical PIT certification or empirical performance",
            "FX event response is observational; copper assumption is independently injected",
            "No implicit pretax-to-operating-income conversion",
            "No automatic promotion",
        ],
    }


if __name__ == "__main__":
    print(json.dumps(run_demo(), ensure_ascii=False, sort_keys=True, indent=2))
