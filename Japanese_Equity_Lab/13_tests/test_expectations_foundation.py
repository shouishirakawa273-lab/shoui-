"""`lib.expectations`(D0108)のRegression Test(D0108 §21-24 Required
Tests)。

`lib.expectations.model`/`lib.expectations.reverse_spec`/`lib.
expectations.comparison`が以下を機械的に強制することを検証する:

1. ConsensusSnapshot/ExpectationObservationがImmutable/Tamper-Evident
   であること、同一Metric/Periodの異なるProviderが別Observationとして
   残ること、Company Guidance != Analyst Consensusであること、PIT
   Cutoff以降のObservationがComparisonで拒否されること、Staleness/
   Single-Estimate-Promotion Guardがあること。
2. ReverseValuationSpecが未知変数の個数からSolverModeを構造的に導出し
   (呼び出し側が嘘をつけない)、固定Assumptionが結果のProvenanceへ
   保存され、同一論理Assumptionの順序違いが同一Hashへ正規化され、未来
   価格・未対応Modelが適切なTyped Statusで拒否されること。
3. ExpectationComparisonがIncompatibleなMetric/Period/Unitを拒否し、
   Stale Proxyを比較結果にも引き継ぎ、BUY/SELL/Expected Returnを一切
   生成しないこと。
4. H0001が未実行であること、D0107 PredictionRecordを複製しないこと、
   D0108がDecisionRecordを自動生成しないこと、LLM依存がないこと。
"""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from lib.consensus.model import ConsensusRecord, StatisticType
from lib.errors import LookAheadBiasError
from lib.evaluation import model as evaluation_model_module
from lib.evaluation.integrity import verify_record_integrity
from lib.evaluation.model import ForecastShape, ScalarForecast, build_prediction_record
from lib.evidence.model import ValueAvailability
from lib.evidence.research_artifact import DataGapStatus
from lib.expectations import comparison as comparison_module
from lib.expectations import model as expectations_model_module
from lib.expectations import reverse_spec as reverse_spec_module
from lib.expectations.comparison import (
    ComparisonSourceType,
    compare_prediction_to_consensus_snapshot,
    compare_prediction_to_market_implied_result,
    compare_prediction_to_observation,
)
from lib.expectations.model import (
    ConsensusCoverageStatus,
    ExpectationProxyCategory,
    MarketExpectationsSchemaError,
    StalenessStatus,
    build_consensus_snapshot,
    classify_consensus_coverage,
    missing_expectation_data_gap,
    observation_from_company_forecast_metric,
    observation_from_consensus_snapshot,
)
from lib.expectations.reverse_spec import (
    TOY_LINEAR_V1,
    AssumptionSurfacePoint,
    BoundedAssumption,
    FixedAssumption,
    MarketImpliedResultStatus,
    SolveForVariable,
    SolverMode,
    build_assumption_surface,
    build_reverse_valuation_spec,
    solve_toy_linear_reverse_valuation,
)
from lib.fundamentals.model import (
    ActualOrForecast,
    ConsolidationScope,
    FiscalYearTarget,
    FundamentalMetric,
    PeriodBasis,
    PeriodType,
)

_NOW = datetime(2026, 9, 1, tzinfo=UTC)


def _consensus_record(
    *,
    record_id: str = "C1",
    series_id: str = "S1",
    source_id: str = "PROVIDER_A",
    entity_id: str | None = "7203",
    metric_type: str = "EPS",
    analyst_count: int | None = 5,
    provider_target_period_id: str | None = "FY2027",
    value: Decimal | None = Decimal("300"),
    unit: str | None = "JPY",
    retrieved_at: datetime = datetime(2026, 8, 1, tzinfo=UTC),
    provider_available_at: datetime | None = datetime(2026, 8, 1, tzinfo=UTC),
) -> ConsensusRecord:
    return ConsensusRecord(
        record_id=record_id,
        series_id=series_id,
        source_id=source_id,
        entity_id=entity_id,
        source_entity_identifier="7203.T",
        metric_type=metric_type,
        statistic_type=StatisticType.MEAN,
        analyst_count=analyst_count,
        provider_target_period_id=provider_target_period_id,
        raw_value=None if value is None else str(value),
        value=value,
        unit=unit,
        value_availability=ValueAvailability.PRESENT if value is not None else ValueAvailability.MISSING_OR_UNSPECIFIED,
        provider_available_at=provider_available_at,
        retrieved_at=retrieved_at,
    )


def _company_forecast_metric(
    *,
    metric_id: str = "M1",
    value: Decimal = Decimal("290"),
    unit: str | None = "JPY",
    actual_or_forecast: ActualOrForecast = ActualOrForecast.COMPANY_FORECAST,
) -> FundamentalMetric:
    return FundamentalMetric(
        metric_id=metric_id,
        envelope_id="E1",
        series_id="SER1",
        metric_type="EPS",
        raw_value=str(value),
        value=value,
        value_availability=ValueAvailability.PRESENT,
        actual_or_forecast=actual_or_forecast,
        fiscal_year_target=FiscalYearTarget.CURRENT_FISCAL_YEAR,
        period_type=PeriodType.FY,
        period_basis=PeriodBasis.CUMULATIVE,
        consolidation_scope=ConsolidationScope.CONSOLIDATED,
        accounting_standard=None,
        source_field="ForecastEPS",
        currency="JPY",
        unit=unit,
    )


def _prediction(
    *,
    prediction_id: str = "P001",
    value: str = "320",
    target: str = "EPS",
    target_period: str = "FY2027",
    unit: str = "JPY",
):
    return build_prediction_record(
        prediction_id=prediction_id,
        entity_id="7203",
        target=target,
        target_period=target_period,
        forecast_shape=ForecastShape.SCALAR,
        scalar_forecast=ScalarForecast(value=Decimal(value), unit=unit),
        created_at=_NOW,
        evidence_cutoff=datetime(2026, 8, 20, tzinfo=UTC),
        research_snapshot_id="SNAP1",
        model_version="MODEL_V1",
        research_pipeline_version="PIPELINE_V1",
    )


# ============================================================
# D0108 §21: ConsensusSnapshot / ExpectationObservation
# ============================================================


def test_21a_consensus_snapshot_is_immutable_and_tamper_evident() -> None:
    record = _consensus_record()
    snapshot = build_consensus_snapshot(consensus_snapshot_id="CS1", source_record=record, created_at=_NOW)
    assert verify_record_integrity(snapshot)
    with pytest.raises(FrozenInstanceError):
        snapshot.value = Decimal("999")  # type: ignore[misc]
    tampered = replace(snapshot, value=Decimal("999"))
    assert not verify_record_integrity(tampered)


def test_21b_same_metric_period_two_providers_remain_distinct() -> None:
    record_a = _consensus_record(record_id="C_A", source_id="PROVIDER_A", value=Decimal("300"))
    record_b = _consensus_record(record_id="C_B", source_id="PROVIDER_B", value=Decimal("305"))
    snapshot_a = build_consensus_snapshot(consensus_snapshot_id="CS_A", source_record=record_a, created_at=_NOW)
    snapshot_b = build_consensus_snapshot(consensus_snapshot_id="CS_B", source_record=record_b, created_at=_NOW)

    assert snapshot_a.metric == snapshot_b.metric
    assert snapshot_a.target_period == snapshot_b.target_period
    assert snapshot_a.source_id != snapshot_b.source_id
    assert snapshot_a.value != snapshot_b.value
    assert snapshot_a.record_hash != snapshot_b.record_hash


def test_21c_company_guidance_is_not_analyst_consensus() -> None:
    guidance_metric = _company_forecast_metric(actual_or_forecast=ActualOrForecast.COMPANY_FORECAST)
    observation = observation_from_company_forecast_metric(
        guidance_metric,
        observation_id="OBS1",
        entity_id="7203",
        target_period="FY2027",
        observed_at=_NOW,
        available_at=_NOW,
        created_at=_NOW,
    )
    assert observation.category is ExpectationProxyCategory.COMPANY_GUIDANCE
    assert observation.category is not ExpectationProxyCategory.ANALYST_CONSENSUS

    actual_metric = _company_forecast_metric(actual_or_forecast=ActualOrForecast.ACTUAL)
    with pytest.raises(MarketExpectationsSchemaError):
        observation_from_company_forecast_metric(
            actual_metric,
            observation_id="OBS2",
            entity_id="7203",
            target_period="FY2027",
            observed_at=_NOW,
            available_at=_NOW,
            created_at=_NOW,
        )


def test_observation_from_company_forecast_metric_rejects_missing_unit_explicitly() -> None:
    """Regression(/code-review high指摘, D0108): `metric.unit`が`None`
    の場合、`"" `へ暗黙Fallbackして後段の空文字Validationに間接的に
    引っ掛けるのではなく、ここで明示的に拒否する(CLAUDE.mdの「取得でき
    ない値を推測で埋めない」原則)。"""
    guidance_metric = _company_forecast_metric(actual_or_forecast=ActualOrForecast.COMPANY_FORECAST, unit=None)
    with pytest.raises(MarketExpectationsSchemaError):
        observation_from_company_forecast_metric(
            guidance_metric,
            observation_id="OBS_NO_UNIT",
            entity_id="7203",
            target_period="FY2027",
            observed_at=_NOW,
            available_at=_NOW,
            created_at=_NOW,
        )


def test_21d_observation_after_pit_cutoff_is_rejected_in_comparison() -> None:
    record = _consensus_record(provider_available_at=datetime(2026, 9, 10, tzinfo=UTC))
    snapshot = build_consensus_snapshot(consensus_snapshot_id="CS_FUTURE", source_record=record, created_at=_NOW)
    prediction = _prediction()

    with pytest.raises(LookAheadBiasError):
        compare_prediction_to_consensus_snapshot(
            prediction,
            snapshot,
            comparison_id="CMP_FUTURE",
            pit_cutoff=datetime(2026, 9, 1, tzinfo=UTC),
            compared_at=_NOW,
        )


def test_21e_stale_observation_is_identifiable() -> None:
    record = _consensus_record(
        retrieved_at=datetime(2026, 6, 1, tzinfo=UTC), provider_available_at=datetime(2026, 6, 1, tzinfo=UTC)
    )
    snapshot = build_consensus_snapshot(consensus_snapshot_id="CS_STALE", source_record=record, created_at=_NOW)
    observation = observation_from_consensus_snapshot(
        snapshot,
        observation_id="OBS_STALE",
        created_at=_NOW,
        decision_at=datetime(2026, 9, 1, tzinfo=UTC),
        staleness_max_age_days=30,
    )
    assert observation.staleness_status is StalenessStatus.STALE

    fresh_observation = observation_from_consensus_snapshot(
        snapshot,
        observation_id="OBS_FRESH",
        created_at=_NOW,
        decision_at=datetime(2026, 6, 5, tzinfo=UTC),
        staleness_max_age_days=30,
    )
    assert fresh_observation.staleness_status is StalenessStatus.FRESH


def test_21f_unavailable_consensus_is_explicit_data_gap() -> None:
    gap = missing_expectation_data_gap(
        category=ExpectationProxyCategory.ANALYST_CONSENSUS,
        metric="EPS",
        target_period="FY2027",
        status=DataGapStatus.UNAVAILABLE,
        note="Providerから未取得",
    )
    assert gap.status is DataGapStatus.UNAVAILABLE
    assert "ANALYST_CONSENSUS" in gap.topic
    assert "EPS" in gap.topic
    assert "FY2027" in gap.topic


def test_21g_single_estimate_is_not_silently_promoted_to_broad_consensus() -> None:
    assert classify_consensus_coverage(1) is ConsensusCoverageStatus.SINGLE_ESTIMATE
    assert classify_consensus_coverage(1) is not ConsensusCoverageStatus.BROAD_COVERAGE
    assert classify_consensus_coverage(None) is ConsensusCoverageStatus.UNKNOWN_COVERAGE
    assert classify_consensus_coverage(2, broad_coverage_minimum=3) is ConsensusCoverageStatus.LIMITED_COVERAGE
    assert classify_consensus_coverage(5, broad_coverage_minimum=3) is ConsensusCoverageStatus.BROAD_COVERAGE

    record = _consensus_record(analyst_count=1)
    snapshot = build_consensus_snapshot(consensus_snapshot_id="CS_SINGLE", source_record=record, created_at=_NOW)
    assert snapshot.coverage_status is ConsensusCoverageStatus.SINGLE_ESTIMATE


def test_consensus_snapshot_requires_resolved_entity_id() -> None:
    record = _consensus_record(entity_id=None)
    with pytest.raises(MarketExpectationsSchemaError):
        build_consensus_snapshot(consensus_snapshot_id="CS_AMBIGUOUS", source_record=record, created_at=_NOW)


def test_consensus_snapshot_requires_provider_available_at_no_fallback() -> None:
    record = _consensus_record(provider_available_at=None)
    with pytest.raises(MarketExpectationsSchemaError):
        build_consensus_snapshot(consensus_snapshot_id="CS_NO_AVAIL", source_record=record, created_at=_NOW)


# ============================================================
# D0108 §22: ReverseValuationSpec / MarketImpliedAssumptionResult
# ============================================================


def _toy_spec(
    *,
    spec_id: str = "SPEC1",
    solve_for: tuple[SolveForVariable, ...] = (SolveForVariable(name="REVENUE_GROWTH", unit="PERCENT"),),
    fixed_assumptions: tuple[FixedAssumption, ...] = (
        FixedAssumption(name="base_price", value=Decimal("2000"), unit="JPY"),
        FixedAssumption(name="sensitivity", value=Decimal("100"), unit="JPY_PER_PERCENT"),
    ),
    bounded_assumptions: tuple[BoundedAssumption, ...] = (),
    price_available_at: datetime = datetime(2026, 8, 20, tzinfo=UTC),
    valuation_model_id: str = TOY_LINEAR_V1,
):
    return build_reverse_valuation_spec(
        spec_id=spec_id,
        valuation_model_id=valuation_model_id,
        valuation_model_version="V1",
        entity_id="7203",
        observed_market_price=Decimal("3000"),
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


def test_22a_single_unknown_with_sufficient_fixed_assumptions_is_valid_spec() -> None:
    spec = _toy_spec()
    assert spec.solver_mode is SolverMode.SINGLE_VARIABLE
    result = solve_toy_linear_reverse_valuation(spec, result_id="R1", decision_at=_NOW, computed_at=_NOW)
    assert result.status is MarketImpliedResultStatus.SUCCESS
    assert len(result.solved_values) == 1
    assert result.solved_values[0].name == "REVENUE_GROWTH"
    assert result.solved_values[0].value == (Decimal("3000") - Decimal("2000")) / Decimal("100")


def test_22b_multiple_unknowns_require_solution_surface_not_scalar() -> None:
    spec = _toy_spec(
        solve_for=(
            SolveForVariable(name="REVENUE_GROWTH", unit="PERCENT"),
            SolveForVariable(name="OPERATING_MARGIN", unit="PERCENT"),
        ),
        fixed_assumptions=(),
    )
    assert spec.solver_mode is SolverMode.SOLUTION_SURFACE
    result = solve_toy_linear_reverse_valuation(spec, result_id="R2", decision_at=_NOW, computed_at=_NOW)
    assert result.status is MarketImpliedResultStatus.UNDERDETERMINED
    assert result.solved_values == ()


def test_22c_missing_fixed_assumptions_is_rejected() -> None:
    spec = _toy_spec(fixed_assumptions=())
    result = solve_toy_linear_reverse_valuation(spec, result_id="R3", decision_at=_NOW, computed_at=_NOW)
    assert result.status is MarketImpliedResultStatus.INVALID_SPEC


def test_22d_fixed_assumptions_are_preserved_in_result_provenance() -> None:
    spec = _toy_spec()
    success_result = solve_toy_linear_reverse_valuation(spec, result_id="R4", decision_at=_NOW, computed_at=_NOW)
    assert success_result.fixed_assumptions_echo == spec.fixed_assumptions

    failing_spec = _toy_spec(
        spec_id="SPEC_ZERO_SENSITIVITY",
        fixed_assumptions=(
            FixedAssumption(name="base_price", value=Decimal("2000"), unit="JPY"),
            FixedAssumption(name="sensitivity", value=Decimal("0"), unit="JPY_PER_PERCENT"),
        ),
    )
    no_solution_result = solve_toy_linear_reverse_valuation(failing_spec, result_id="R5", decision_at=_NOW, computed_at=_NOW)
    assert no_solution_result.status is MarketImpliedResultStatus.NO_SOLUTION
    assert no_solution_result.fixed_assumptions_echo == failing_spec.fixed_assumptions


def test_22e_different_fixed_assumptions_produce_distinct_identity() -> None:
    spec_a = _toy_spec(
        fixed_assumptions=(
            FixedAssumption(name="base_price", value=Decimal("2000"), unit="JPY"),
            FixedAssumption(name="sensitivity", value=Decimal("100"), unit="JPY_PER_PERCENT"),
        )
    )
    spec_b = _toy_spec(
        fixed_assumptions=(
            FixedAssumption(name="base_price", value=Decimal("2200"), unit="JPY"),
            FixedAssumption(name="sensitivity", value=Decimal("100"), unit="JPY_PER_PERCENT"),
        )
    )
    assert spec_a.record_hash != spec_b.record_hash


def test_22f_same_logical_assumptions_different_ordering_same_canonical_identity() -> None:
    fixed_1 = FixedAssumption(name="base_price", value=Decimal("2000"), unit="JPY")
    fixed_2 = FixedAssumption(name="sensitivity", value=Decimal("100"), unit="JPY_PER_PERCENT")
    spec_order_a = _toy_spec(fixed_assumptions=(fixed_1, fixed_2))
    spec_order_b = _toy_spec(fixed_assumptions=(fixed_2, fixed_1))
    assert spec_order_a.record_hash == spec_order_b.record_hash
    assert spec_order_a.fixed_assumptions == spec_order_b.fixed_assumptions


def test_22g_future_price_observation_is_pit_rejected() -> None:
    spec = _toy_spec(price_available_at=datetime(2026, 9, 10, tzinfo=UTC))
    result = solve_toy_linear_reverse_valuation(
        spec, result_id="R6", decision_at=datetime(2026, 9, 1, tzinfo=UTC), computed_at=_NOW
    )
    assert result.status is MarketImpliedResultStatus.PIT_INVALID


def test_22h_unsupported_valuation_model_is_typed_failure() -> None:
    spec = _toy_spec(valuation_model_id="SOME_OTHER_MODEL_V1")
    result = solve_toy_linear_reverse_valuation(spec, result_id="R7", decision_at=_NOW, computed_at=_NOW)
    assert result.status is MarketImpliedResultStatus.UNSUPPORTED_MODEL


def test_reverse_valuation_spec_rejects_solve_for_overlap_with_fixed() -> None:
    with pytest.raises(MarketExpectationsSchemaError):
        build_reverse_valuation_spec(
            spec_id="SPEC_OVERLAP",
            valuation_model_id=TOY_LINEAR_V1,
            valuation_model_version="V1",
            entity_id="7203",
            observed_market_price=Decimal("3000"),
            price_currency="JPY",
            price_observed_at=_NOW,
            price_available_at=_NOW,
            price_source_id="MARKET_DATA",
            solve_for_variables=(SolveForVariable(name="REVENUE_GROWTH", unit="PERCENT"),),
            valuation_horizon="FY2027",
            created_at=_NOW,
            fixed_assumptions=(FixedAssumption(name="REVENUE_GROWTH", value=Decimal("5"), unit="PERCENT"),),
        )


def test_reverse_valuation_spec_rejects_duplicate_bounded_assumption_names() -> None:
    """Regression(/code-review high指摘, D0108): 同一変数名を持つ2件の
    `BoundedAssumption`(矛盾するRange)を許すと、`solve_toy_linear_
    reverse_valuation()`の`bound_by_name`辞書構築時に後勝ちで片方が黙って
    無視される。構築時点でFail Closedする。"""
    with pytest.raises(MarketExpectationsSchemaError):
        build_reverse_valuation_spec(
            spec_id="SPEC_BOUNDED_DUP",
            valuation_model_id=TOY_LINEAR_V1,
            valuation_model_version="V1",
            entity_id="7203",
            observed_market_price=Decimal("3000"),
            price_currency="JPY",
            price_observed_at=_NOW,
            price_available_at=_NOW,
            price_source_id="MARKET_DATA",
            solve_for_variables=(SolveForVariable(name="REVENUE_GROWTH", unit="PERCENT"),),
            valuation_horizon="FY2027",
            created_at=_NOW,
            fixed_assumptions=(
                FixedAssumption(name="base_price", value=Decimal("2000"), unit="JPY"),
                FixedAssumption(name="sensitivity", value=Decimal("100"), unit="JPY_PER_PERCENT"),
            ),
            bounded_assumptions=(
                BoundedAssumption(name="REVENUE_GROWTH", lower_bound=Decimal("0"), upper_bound=Decimal("10"), unit="PERCENT"),
                BoundedAssumption(name="REVENUE_GROWTH", lower_bound=Decimal("5"), upper_bound=Decimal("20"), unit="PERCENT"),
            ),
        )


def test_assumption_surface_rejects_single_variable_spec() -> None:
    spec = _toy_spec()
    with pytest.raises(MarketExpectationsSchemaError):
        build_assumption_surface(
            surface_id="SURF1",
            spec=spec,
            varied_assumption_names=("OPERATING_MARGIN",),
            points=(),
            generated_at=_NOW,
        )


def test_assumption_surface_accepts_solution_surface_spec_with_points() -> None:
    spec = _toy_spec(
        solve_for=(SolveForVariable(name="REVENUE_GROWTH", unit="PERCENT"),),
        fixed_assumptions=(),
    )
    multi_spec = _toy_spec(
        spec_id="SPEC_SURFACE",
        solve_for=(
            SolveForVariable(name="REVENUE_GROWTH", unit="PERCENT"),
            SolveForVariable(name="OPERATING_MARGIN", unit="PERCENT"),
        ),
        fixed_assumptions=(),
    )
    assert spec.solver_mode is SolverMode.SINGLE_VARIABLE  # sanity: single stays single
    surface = build_assumption_surface(
        surface_id="SURF2",
        spec=multi_spec,
        varied_assumption_names=("OPERATING_MARGIN",),
        points=(
            AssumptionSurfacePoint(
                varied_values=(Decimal("8"),),
                solved_values=(reverse_spec_module.SolvedVariable(name="REVENUE_GROWTH", value=Decimal("14"), unit="PERCENT"),),
            ),
            AssumptionSurfacePoint(
                varied_values=(Decimal("10"),),
                solved_values=(reverse_spec_module.SolvedVariable(name="REVENUE_GROWTH", value=Decimal("10"), unit="PERCENT"),),
            ),
        ),
        generated_at=_NOW,
    )
    assert len(surface.points) == 2
    assert verify_record_integrity(surface)


# ============================================================
# D0108 §23: ExpectationComparison
# ============================================================


def test_23a_research_eps_vs_consensus_eps_same_period_unit_is_valid_delta() -> None:
    prediction = _prediction(value="320")
    record = _consensus_record(value=Decimal("300"))
    snapshot = build_consensus_snapshot(consensus_snapshot_id="CS_A", source_record=record, created_at=_NOW)
    comparison = compare_prediction_to_consensus_snapshot(
        prediction, snapshot, comparison_id="CMP_A", pit_cutoff=datetime(2026, 9, 1, tzinfo=UTC), compared_at=_NOW
    )
    assert comparison.difference == Decimal("20")
    assert comparison.left_source_type is ComparisonSourceType.RESEARCH_PREDICTION
    assert comparison.right_source_type is ComparisonSourceType.ANALYST_CONSENSUS
    assert verify_record_integrity(comparison)


def test_23b_research_growth_vs_market_implied_growth_is_valid_conditional_comparison() -> None:
    prediction = _prediction(value="6", target="REVENUE_GROWTH", unit="PERCENT")
    spec = _toy_spec()
    result = solve_toy_linear_reverse_valuation(spec, result_id="R_CMP", decision_at=_NOW, computed_at=_NOW)
    assert result.status is MarketImpliedResultStatus.SUCCESS

    comparison = compare_prediction_to_market_implied_result(
        prediction,
        result,
        solve_for_variable_name="REVENUE_GROWTH",
        comparison_id="CMP_B",
        pit_cutoff=_NOW,
        compared_at=_NOW,
    )
    assert comparison.right_source_type is ComparisonSourceType.MARKET_IMPLIED_ASSUMPTION
    assert comparison.difference == prediction.scalar_forecast.value - result.solved_values[0].value  # type: ignore[union-attr]


def test_compare_prediction_to_market_implied_result_rejects_metric_mismatch() -> None:
    """Regression(/code-review high指摘, D0108): `prediction.target`と
    `solve_for_variable_name`が異なるMetricを指す場合、無言でEPS vs
    成長率というNonsensicalなComparisonを構築してはならない(他の
    `compare_prediction_to_*()`と同じMetric一致要件)。"""
    prediction = _prediction(target="EPS", value="320", unit="JPY")
    spec = _toy_spec()
    result = solve_toy_linear_reverse_valuation(spec, result_id="R_MISMATCH", decision_at=_NOW, computed_at=_NOW)
    assert result.status is MarketImpliedResultStatus.SUCCESS

    with pytest.raises(MarketExpectationsSchemaError):
        compare_prediction_to_market_implied_result(
            prediction,
            result,
            solve_for_variable_name="REVENUE_GROWTH",
            comparison_id="CMP_MISMATCH",
            pit_cutoff=_NOW,
            compared_at=_NOW,
        )


def test_compare_prediction_to_market_implied_result_rejects_future_result() -> None:
    """Regression(/code-review high指摘, D0108): `result.computed_at`が
    `pit_cutoff`より後の場合、その他の`compare_prediction_to_*()`と同じ
    くLook-ahead(未来のMarket-Implied Assumption情報)としてFail Closed
    する。"""
    prediction = _prediction(value="6", target="REVENUE_GROWTH", unit="PERCENT")
    spec = _toy_spec()
    result = solve_toy_linear_reverse_valuation(
        spec, result_id="R_FUTURE", decision_at=datetime(2026, 9, 10, tzinfo=UTC), computed_at=datetime(2026, 9, 10, tzinfo=UTC)
    )
    assert result.status is MarketImpliedResultStatus.SUCCESS

    with pytest.raises(LookAheadBiasError):
        compare_prediction_to_market_implied_result(
            prediction,
            result,
            solve_for_variable_name="REVENUE_GROWTH",
            comparison_id="CMP_FUTURE_RESULT",
            pit_cutoff=datetime(2026, 9, 1, tzinfo=UTC),
            compared_at=_NOW,
        )


def test_23c_different_target_periods_are_rejected() -> None:
    prediction = _prediction(target_period="FY2027")
    record = _consensus_record(provider_target_period_id="FY2028")
    snapshot = build_consensus_snapshot(consensus_snapshot_id="CS_PERIOD", source_record=record, created_at=_NOW)
    with pytest.raises(MarketExpectationsSchemaError):
        compare_prediction_to_consensus_snapshot(
            prediction, snapshot, comparison_id="CMP_C", pit_cutoff=datetime(2026, 9, 1, tzinfo=UTC), compared_at=_NOW
        )


def test_23d_different_units_are_rejected() -> None:
    prediction = _prediction(unit="JPY")
    record = _consensus_record(unit="USD")
    snapshot = build_consensus_snapshot(consensus_snapshot_id="CS_UNIT", source_record=record, created_at=_NOW)
    with pytest.raises(MarketExpectationsSchemaError):
        compare_prediction_to_consensus_snapshot(
            prediction, snapshot, comparison_id="CMP_D", pit_cutoff=datetime(2026, 9, 1, tzinfo=UTC), compared_at=_NOW
        )


def test_23e_different_metrics_are_rejected() -> None:
    prediction = _prediction(target="EPS")
    record = _consensus_record(metric_type="REVENUE")
    snapshot = build_consensus_snapshot(consensus_snapshot_id="CS_METRIC", source_record=record, created_at=_NOW)
    with pytest.raises(MarketExpectationsSchemaError):
        compare_prediction_to_consensus_snapshot(
            prediction, snapshot, comparison_id="CMP_E", pit_cutoff=datetime(2026, 9, 1, tzinfo=UTC), compared_at=_NOW
        )


def test_23f_stale_proxy_remains_marked_stale_in_comparison_output() -> None:
    prediction = _prediction()
    record = _consensus_record(
        retrieved_at=datetime(2026, 6, 1, tzinfo=UTC), provider_available_at=datetime(2026, 6, 1, tzinfo=UTC)
    )
    snapshot = build_consensus_snapshot(consensus_snapshot_id="CS_STALE_CMP", source_record=record, created_at=_NOW)
    observation = observation_from_consensus_snapshot(
        snapshot,
        observation_id="OBS_STALE_CMP",
        created_at=_NOW,
        decision_at=datetime(2026, 9, 1, tzinfo=UTC),
        staleness_max_age_days=30,
    )
    assert observation.staleness_status is StalenessStatus.STALE

    comparison = compare_prediction_to_observation(
        prediction, observation, comparison_id="CMP_F", pit_cutoff=datetime(2026, 9, 1, tzinfo=UTC), compared_at=_NOW
    )
    assert comparison.right_staleness_status is StalenessStatus.STALE


def test_23g_comparison_never_emits_buy_sell_or_expected_return() -> None:
    source = Path(comparison_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    identifiers: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name | ast.Attribute):
            identifiers.add(getattr(node, "id", getattr(node, "attr", "")))
        elif isinstance(node, ast.arg):
            identifiers.add(node.arg)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            identifiers.add(node.name)
    for forbidden in ("BUY", "SELL", "expected_return", "DecisionRecord", "build_decision_record"):
        assert forbidden not in identifiers


# ============================================================
# D0108 §24: No Unique Market Expectation Claim
# ============================================================


def test_24_no_unique_market_expectation_claim_identifiers() -> None:
    for module_path in (
        expectations_model_module.__file__,
        reverse_spec_module.__file__,
        comparison_module.__file__,
    ):
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
        for forbidden in (
            "true_market_expectation",
            "market_expected_growth",
            "the_market_expects",
            "BUY",
            "SELL",
            "expected_return",
            "Backtest",
            "PortfolioOptimizer",
            "PositionSizing",
            "Correlation",
            "Sharpe",
        ):
            assert forbidden not in identifiers, f"{module_path} に禁止識別子 {forbidden!r} が含まれています"


# ============================================================
# D0107 Integration / D0109-D0110 Boundary / No Decision Logic / No LLM / H0001
# ============================================================


def test_expectations_reuses_d0107_prediction_record_does_not_duplicate_storage() -> None:
    source = Path(evaluation_model_module.__file__).read_text(encoding="utf-8")
    assert "ExpectationComparison" not in source
    assert "ConsensusSnapshot" not in source
    for module_path in (
        expectations_model_module.__file__,
        reverse_spec_module.__file__,
        comparison_module.__file__,
    ):
        source = Path(module_path).read_text(encoding="utf-8")
        assert "class PredictionRecord" not in source
        assert "AppendOnlyRecordStore" not in source


def test_expectations_modules_never_create_decision_record() -> None:
    for module_path in (
        expectations_model_module.__file__,
        reverse_spec_module.__file__,
        comparison_module.__file__,
    ):
        source = Path(module_path).read_text(encoding="utf-8")
        assert "DecisionRecord" not in source
        assert "build_decision_record" not in source


def test_expectations_modules_have_no_llm_dependency() -> None:
    for module_path in (
        expectations_model_module.__file__,
        reverse_spec_module.__file__,
        comparison_module.__file__,
    ):
        source = Path(module_path).read_text(encoding="utf-8")
        for forbidden in ("import openai", "import anthropic", "requests.post", "httpx.", ".classify(", ".extract("):
            assert forbidden not in source


def test_expectations_modules_do_not_touch_h0001() -> None:
    for module_path in (
        expectations_model_module.__file__,
        reverse_spec_module.__file__,
        comparison_module.__file__,
    ):
        source = Path(module_path).read_text(encoding="utf-8")
        assert "H0001" not in source
        assert "locked_test" not in source.lower()


def test_expectations_modules_build_no_production_valuation_engine() -> None:
    source = Path(reverse_spec_module.__file__).read_text(encoding="utf-8")
    for forbidden in ("scipy", "numpy.linalg", "DiscountedCashFlow", "MonteCarlo"):
        assert forbidden not in source
