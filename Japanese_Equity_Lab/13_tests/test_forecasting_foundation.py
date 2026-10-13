"""`lib.forecasting`(D0109)のRegression Test(D0109 §26-30 Required
Tests)。

`lib.forecasting.model`/`lib.forecasting.engine`が以下を機械的に強制
することを検証する:

1. 明示的Assumptionからの決定論的Base/Bull/Bear Forecast計算、入力
   順序非依存のIdentity/Hash、Historical Base欠落/Unit不整合/PIT
   違反/Operating Margin-Income不整合の各FailはTyped Statusで表現
   されること。
2. D0107 PredictionRecordとの統合(Bull/Base/Bear、Revision、Forecast
   Family、Version/Evidence Cutoff/ResearchSnapshot保持)。
3. Research Judgment Assumptionの明示的Label付け・Rationale必須・
   Evidence Masquerade禁止。
4. Valuation/Expected Return/BUY-SELL/Scenario Probability/
   DecisionRecordがいずれも存在しないこと、H0001が未実行であること。
"""

from __future__ import annotations

import ast
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from lib.evaluation import model as evaluation_model_module
from lib.evaluation.integrity import verify_record_integrity
from lib.evidence.model import DataLayer, EvidenceRecord, EvidenceType
from lib.evidence.thesis_impact import ThesisScenario
from lib.forecasting import engine as engine_module
from lib.forecasting import model as model_module
from lib.forecasting.engine import build_prediction_record_from_forecast, compute_fundamental_forecast
from lib.forecasting.model import (
    METRIC_OPERATING_INCOME,
    METRIC_OPERATING_MARGIN,
    METRIC_REVENUE,
    AssumptionSource,
    ForecastAssumption,
    ForecastSchemaError,
    ForecastStatus,
    HistoricalFundamentalBase,
    ScenarioAssumptions,
)
from lib.sources.catalog import DataCapability, PrimaryOrSecondary, SourceAuthorityClass, SourceMetadata

_NOW = datetime(2026, 9, 1, tzinfo=UTC)
_BASE_AVAILABLE_AT = datetime(2026, 5, 1, tzinfo=UTC)


def _historical_revenue_base(
    *, value: Decimal = Decimal("1000"), unit: str = "JPY", available_at: datetime = _BASE_AVAILABLE_AT
) -> HistoricalFundamentalBase:
    return HistoricalFundamentalBase(
        entity_id="7203",
        metric=METRIC_REVENUE,
        period="FY2026",
        value=value,
        unit=unit,
        currency=unit,
        source_id="JQUANTS_FINS_SUMMARY",
        available_at=available_at,
        provenance_ref="M1",
    )


def _judgment_assumption(*, name: str, value: str, unit: str = "PERCENT", rationale: str = "Research判断") -> ForecastAssumption:
    return ForecastAssumption(
        name=name,
        value=Decimal(value),
        unit=unit,
        source=AssumptionSource.RESEARCH_JUDGMENT,
        rationale=rationale,
        created_at=_NOW,
    )


def _scenario(scenario: ThesisScenario, *, growth: str, margin: str) -> ScenarioAssumptions:
    return ScenarioAssumptions(
        scenario=scenario,
        assumptions=(
            _judgment_assumption(name="REVENUE_GROWTH", value=growth),
            _judgment_assumption(name="OPERATING_MARGIN", value=margin),
        ),
    )


def _three_scenarios(*, bull=("10", "11"), base=("6", "10"), bear=("0", "7")) -> tuple[ScenarioAssumptions, ...]:
    return (
        _scenario(ThesisScenario.BULL, growth=bull[0], margin=bull[1]),
        _scenario(ThesisScenario.BASE, growth=base[0], margin=base[1]),
        _scenario(ThesisScenario.BEAR, growth=bear[0], margin=bear[1]),
    )


def _evidence_record(*, evidence_id: str = "E1", available_at: datetime = _BASE_AVAILABLE_AT) -> EvidenceRecord:
    source = SourceMetadata(
        source_id="S1",
        source_type="EDINET",
        provider_name="EDINET",
        source_authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        primary_or_secondary=PrimaryOrSecondary.PRIMARY,
        retrieved_at=available_at,
        published_at=available_at,
        available_at=available_at,
    )
    return EvidenceRecord(
        evidence_id=evidence_id,
        evidence_type=EvidenceType.FACT,
        layer=DataLayer.RAW,
        capability=DataCapability.FUNDAMENTAL,
        content="EvidenceDerived content",
        source=source,
    )


def _compute(
    *,
    scenario_assumptions: tuple[ScenarioAssumptions, ...] | None = None,
    historical_bases: tuple[HistoricalFundamentalBase, ...] | None = None,
    requested_metrics: tuple[str, ...] = (METRIC_REVENUE, METRIC_OPERATING_INCOME, METRIC_OPERATING_MARGIN),
    evidence_cutoff: datetime = _NOW,
    evidence_records: tuple[EvidenceRecord, ...] = (),
):
    return compute_fundamental_forecast(
        result_id="R1",
        entity_id="7203",
        target_period="FY2027",
        requested_metrics=requested_metrics,
        scenario_assumptions=_three_scenarios() if scenario_assumptions is None else scenario_assumptions,
        historical_bases=(_historical_revenue_base(),) if historical_bases is None else historical_bases,
        evidence_cutoff=evidence_cutoff,
        research_snapshot_id="SNAP1",
        forecast_created_at=_NOW,
        evidence_records=evidence_records,
    )


# ============================================================
# D0109 §26: Forecast
# ============================================================


def test_26a_deterministic_base_forecast_from_explicit_assumptions() -> None:
    result = _compute()
    assert result.status is ForecastStatus.SUCCESS
    base = next(s for s in result.scenarios if s.scenario is ThesisScenario.BASE)
    values = {v.metric: v.value for v in base.metric_values}
    assert values[METRIC_REVENUE] == Decimal("1060.00")
    assert values[METRIC_OPERATING_INCOME] == Decimal("106.000")
    assert verify_record_integrity(result)


def test_26b_bull_base_bear_independently_calculated() -> None:
    result = _compute()
    values_by_scenario = {s.scenario: {v.metric: v.value for v in s.metric_values} for s in result.scenarios}
    assert values_by_scenario[ThesisScenario.BULL][METRIC_REVENUE] == Decimal("1100.0")
    assert values_by_scenario[ThesisScenario.BULL][METRIC_OPERATING_INCOME] == Decimal("121.000")
    assert values_by_scenario[ThesisScenario.BASE][METRIC_REVENUE] == Decimal("1060.00")
    assert values_by_scenario[ThesisScenario.BASE][METRIC_OPERATING_INCOME] == Decimal("106.000")
    assert values_by_scenario[ThesisScenario.BEAR][METRIC_REVENUE] == Decimal("1000")
    assert values_by_scenario[ThesisScenario.BEAR][METRIC_OPERATING_INCOME] == Decimal("70.00")


def test_26c_repeated_identical_input_produces_identical_output() -> None:
    result_1 = _compute()
    result_2 = _compute()
    assert result_1.record_hash == result_2.record_hash


def test_26d_assumption_ordering_does_not_change_identity() -> None:
    forward = _three_scenarios()
    reversed_scenarios = tuple(reversed(forward))
    reversed_assumptions = tuple(replace(sa, assumptions=tuple(reversed(sa.assumptions))) for sa in reversed_scenarios)
    result_forward = _compute(scenario_assumptions=forward)
    result_reordered = _compute(scenario_assumptions=reversed_assumptions)
    assert result_forward.record_hash == result_reordered.record_hash


def test_26e_missing_historical_base_is_insufficient_input() -> None:
    result = _compute(historical_bases=())
    assert result.status is ForecastStatus.INSUFFICIENT_INPUT


def test_26f_incompatible_units_are_rejected() -> None:
    override = ForecastAssumption(
        name="OPERATING_INCOME",
        value=Decimal("106"),
        unit="USD",
        source=AssumptionSource.COMPANY_GUIDANCE,
        company_guidance_observation_ref="OBS1",
        created_at=_NOW,
    )
    base_scenario = _scenario(ThesisScenario.BASE, growth="6", margin="10")
    conflicting_base = replace(base_scenario, assumptions=(*base_scenario.assumptions, override))
    scenarios = (
        _scenario(ThesisScenario.BULL, growth="10", margin="11"),
        conflicting_base,
        _scenario(ThesisScenario.BEAR, growth="0", margin="7"),
    )
    result = _compute(scenario_assumptions=scenarios)
    assert result.status is ForecastStatus.INVALID_ASSUMPTION


def test_26g_pit_invalid_historical_base_is_rejected() -> None:
    future_base = _historical_revenue_base(available_at=datetime(2026, 9, 10, tzinfo=UTC))
    result = _compute(historical_bases=(future_base,))
    assert result.status is ForecastStatus.PIT_INVALID


def test_26g_pit_invalid_evidence_derived_assumption_is_rejected() -> None:
    future_evidence = _evidence_record(evidence_id="E_FUTURE", available_at=datetime(2026, 9, 10, tzinfo=UTC))
    evidence_assumption = ForecastAssumption(
        name="REVENUE_GROWTH",
        value=Decimal("6"),
        unit="PERCENT",
        source=AssumptionSource.EVIDENCE_DERIVED,
        evidence_ids=("E_FUTURE",),
        created_at=_NOW,
    )
    base_scenario = ScenarioAssumptions(
        scenario=ThesisScenario.BASE, assumptions=(evidence_assumption, _judgment_assumption(name="OPERATING_MARGIN", value="10"))
    )
    scenarios = (
        _scenario(ThesisScenario.BULL, growth="10", margin="11"),
        base_scenario,
        _scenario(ThesisScenario.BEAR, growth="0", margin="7"),
    )
    result = _compute(scenario_assumptions=scenarios, evidence_records=(future_evidence,))
    assert result.status is ForecastStatus.PIT_INVALID


def test_26h_operating_margin_income_inconsistency_is_rejected() -> None:
    override = ForecastAssumption(
        name="OPERATING_INCOME",
        value=Decimal("999"),
        unit="JPY",
        source=AssumptionSource.COMPANY_GUIDANCE,
        company_guidance_observation_ref="OBS1",
        created_at=_NOW,
    )
    base_scenario = _scenario(ThesisScenario.BASE, growth="6", margin="10")
    conflicting_base = replace(base_scenario, assumptions=(*base_scenario.assumptions, override))
    scenarios = (
        _scenario(ThesisScenario.BULL, growth="10", margin="11"),
        conflicting_base,
        _scenario(ThesisScenario.BEAR, growth="0", margin="7"),
    )
    result = _compute(scenario_assumptions=scenarios)
    assert result.status is ForecastStatus.INCONSISTENT_FORECAST


def test_26i_company_guidance_remains_distinct_from_research_forecast() -> None:
    guidance_assumption = ForecastAssumption(
        name="REVENUE_GROWTH",
        value=Decimal("6"),
        unit="PERCENT",
        source=AssumptionSource.COMPANY_GUIDANCE,
        company_guidance_observation_ref="GUIDANCE_OBS1",
        created_at=_NOW,
    )
    base_scenario = ScenarioAssumptions(
        scenario=ThesisScenario.BASE, assumptions=(guidance_assumption, _judgment_assumption(name="OPERATING_MARGIN", value="10"))
    )
    scenarios = (
        _scenario(ThesisScenario.BULL, growth="10", margin="11"),
        base_scenario,
        _scenario(ThesisScenario.BEAR, growth="0", margin="7"),
    )
    result = _compute(scenario_assumptions=scenarios)
    assert result.status is ForecastStatus.SUCCESS
    base = next(s for s in result.scenarios if s.scenario is ThesisScenario.BASE)
    used = next(a for a in base.assumptions if a.name == "REVENUE_GROWTH")
    assert used.source is AssumptionSource.COMPANY_GUIDANCE
    assert used.company_guidance_observation_ref == "GUIDANCE_OBS1"
    # The Research Forecast Result itself never claims to BE guidance -- the
    # distinction (source=COMPANY_GUIDANCE) remains visible on the assumption.
    assert not hasattr(base, "company_guidance_value")


def test_26j_consensus_remains_distinct_from_research_forecast() -> None:
    market_proxy_assumption = ForecastAssumption(
        name="REVENUE_GROWTH",
        value=Decimal("8"),
        unit="PERCENT",
        source=AssumptionSource.MARKET_PROXY,
        market_proxy_observation_ref="CONSENSUS_SNAPSHOT_1",
        created_at=_NOW,
    )
    base_scenario = ScenarioAssumptions(
        scenario=ThesisScenario.BASE,
        assumptions=(market_proxy_assumption, _judgment_assumption(name="OPERATING_MARGIN", value="10")),
    )
    scenarios = (
        _scenario(ThesisScenario.BULL, growth="10", margin="11"),
        base_scenario,
        _scenario(ThesisScenario.BEAR, growth="0", margin="7"),
    )
    result = _compute(scenario_assumptions=scenarios)
    assert result.status is ForecastStatus.SUCCESS
    base = next(s for s in result.scenarios if s.scenario is ThesisScenario.BASE)
    used = next(a for a in base.assumptions if a.name == "REVENUE_GROWTH")
    assert used.source is AssumptionSource.MARKET_PROXY
    assert used.market_proxy_observation_ref == "CONSENSUS_SNAPSHOT_1"


# ============================================================
# D0109 §27: Prediction Integration
# ============================================================


def test_27a_forecast_creates_d0107_compatible_prediction_record() -> None:
    result = _compute()
    pred = build_prediction_record_from_forecast(
        result,
        metric=METRIC_REVENUE,
        prediction_id="P1",
        model_version="FORECAST_ENGINE_V1",
        research_pipeline_version="PIPELINE_V1",
    )
    assert verify_record_integrity(pred)
    assert pred.bull_base_bear_forecast is not None
    assert pred.bull_base_bear_forecast.base == Decimal("1060.00")


def test_27bc_revised_forecast_creates_new_record_and_old_is_unchanged() -> None:
    result_1 = _compute()
    p001 = build_prediction_record_from_forecast(
        result_1,
        metric=METRIC_REVENUE,
        prediction_id="P001",
        model_version="FORECAST_ENGINE_V1",
        research_pipeline_version="PIPELINE_V1",
    )
    original_hash = p001.record_hash

    result_2 = _compute(
        scenario_assumptions=(
            _scenario(ThesisScenario.BULL, growth="9", margin="12"),
            _scenario(ThesisScenario.BASE, growth="5", margin="9"),
            _scenario(ThesisScenario.BEAR, growth="1", margin="7"),
        )
    )
    p002 = build_prediction_record_from_forecast(
        result_2,
        metric=METRIC_REVENUE,
        prediction_id="P002",
        model_version="FORECAST_ENGINE_V1",
        research_pipeline_version="PIPELINE_V1",
        parent_prediction_id="P001",
        existing_predictions=(p001,),
    )
    assert p001.record_hash == original_hash
    assert p002.parent_prediction_id == "P001"
    assert p002.record_hash != p001.record_hash


def test_27d_parent_prediction_id_correctly_linked() -> None:
    result_1 = _compute()
    p001 = build_prediction_record_from_forecast(
        result_1,
        metric=METRIC_REVENUE,
        prediction_id="P001",
        model_version="FORECAST_ENGINE_V1",
        research_pipeline_version="PIPELINE_V1",
    )
    result_2 = _compute()
    p002 = build_prediction_record_from_forecast(
        result_2,
        metric=METRIC_REVENUE,
        prediction_id="P002",
        model_version="FORECAST_ENGINE_V1",
        research_pipeline_version="PIPELINE_V1",
        parent_prediction_id="P001",
        existing_predictions=(p001,),
    )
    assert p002.parent_prediction_id == "P001"

    with pytest.raises(Exception):  # noqa: B017, PT011 -- D0107's own EvaluationFoundationSchemaError, missing parent
        build_prediction_record_from_forecast(
            result_2,
            metric=METRIC_REVENUE,
            prediction_id="P003",
            model_version="FORECAST_ENGINE_V1",
            research_pipeline_version="PIPELINE_V1",
            parent_prediction_id="P_DOES_NOT_EXIST",
            existing_predictions=(p001,),
        )


def test_27e_same_forecast_family_preserved() -> None:
    from lib.evaluation.model import forecast_family_key

    result_1 = _compute()
    p001 = build_prediction_record_from_forecast(
        result_1,
        metric=METRIC_REVENUE,
        prediction_id="P001",
        model_version="FORECAST_ENGINE_V1",
        research_pipeline_version="PIPELINE_V1",
    )
    result_2 = _compute()
    p002 = build_prediction_record_from_forecast(
        result_2,
        metric=METRIC_REVENUE,
        prediction_id="P002",
        model_version="FORECAST_ENGINE_V1",
        research_pipeline_version="PIPELINE_V1",
        parent_prediction_id="P001",
        existing_predictions=(p001,),
    )
    assert forecast_family_key(p001) == forecast_family_key(p002) == ("7203", METRIC_REVENUE, "FY2027")


def test_27f_model_prompt_pipeline_version_preserved() -> None:
    result = _compute()
    pred = build_prediction_record_from_forecast(
        result,
        metric=METRIC_REVENUE,
        prediction_id="P1",
        model_version="FORECAST_ENGINE_V1",
        research_pipeline_version="PIPELINE_V1",
        prompt_version="PROMPT_V1",
    )
    assert pred.model_version == "FORECAST_ENGINE_V1"
    assert pred.research_pipeline_version == "PIPELINE_V1"
    assert pred.prompt_version == "PROMPT_V1"


def test_27g_evidence_cutoff_preserved() -> None:
    result = _compute(evidence_cutoff=_NOW)
    pred = build_prediction_record_from_forecast(
        result,
        metric=METRIC_REVENUE,
        prediction_id="P1",
        model_version="FORECAST_ENGINE_V1",
        research_pipeline_version="PIPELINE_V1",
    )
    assert pred.evidence_cutoff == _NOW == result.evidence_cutoff


def test_27h_research_snapshot_preserved() -> None:
    result = _compute()
    pred = build_prediction_record_from_forecast(
        result,
        metric=METRIC_REVENUE,
        prediction_id="P1",
        model_version="FORECAST_ENGINE_V1",
        research_pipeline_version="PIPELINE_V1",
    )
    assert pred.research_snapshot_id == "SNAP1" == result.research_snapshot_id


# ============================================================
# D0109 §28: Judgment
# ============================================================


def test_28a_research_judgment_assumption_explicitly_labeled() -> None:
    assumption = _judgment_assumption(name="REVENUE_GROWTH", value="6", rationale="市場シェア拡大の継続を仮定")
    assert assumption.source is AssumptionSource.RESEARCH_JUDGMENT
    assert assumption.rationale == "市場シェア拡大の継続を仮定"


def test_28b_missing_rationale_where_required_is_rejected() -> None:
    with pytest.raises(ForecastSchemaError):
        ForecastAssumption(
            name="REVENUE_GROWTH",
            value=Decimal("6"),
            unit="PERCENT",
            source=AssumptionSource.RESEARCH_JUDGMENT,
            rationale=None,
            created_at=_NOW,
        )
    with pytest.raises(ForecastSchemaError):
        ForecastAssumption(
            name="REVENUE_GROWTH",
            value=Decimal("6"),
            unit="PERCENT",
            source=AssumptionSource.RESEARCH_JUDGMENT,
            rationale="",
            created_at=_NOW,
        )


def test_28c_model_assisted_judgment_provenance_retained() -> None:
    assumption = ForecastAssumption(
        name="REVENUE_GROWTH",
        value=Decimal("6"),
        unit="PERCENT",
        source=AssumptionSource.RESEARCH_JUDGMENT,
        rationale="Model提案を採用",
        model_version="PROPOSAL_MODEL_V1",
        prompt_version="PROMPT_V1",
        created_at=_NOW,
    )
    assert assumption.model_version == "PROPOSAL_MODEL_V1"
    assert assumption.prompt_version == "PROMPT_V1"


def test_28d_judgment_cannot_masquerade_as_evidence_record() -> None:
    with pytest.raises(ForecastSchemaError):
        ForecastAssumption(
            name="REVENUE_GROWTH",
            value=Decimal("6"),
            unit="PERCENT",
            source=AssumptionSource.RESEARCH_JUDGMENT,
            rationale="Judgment",
            evidence_ids=("E1",),
            created_at=_NOW,
        )


def test_28d_evidence_derived_requires_actual_evidence_ids() -> None:
    with pytest.raises(ForecastSchemaError):
        ForecastAssumption(
            name="REVENUE_GROWTH",
            value=Decimal("6"),
            unit="PERCENT",
            source=AssumptionSource.EVIDENCE_DERIVED,
            evidence_ids=(),
            created_at=_NOW,
        )


def test_28e_deterministic_formula_cannot_silently_alter_judgment_input() -> None:
    growth_value = Decimal("6")
    result = _compute(
        scenario_assumptions=(
            _scenario(ThesisScenario.BULL, growth="10", margin="11"),
            ScenarioAssumptions(
                scenario=ThesisScenario.BASE,
                assumptions=(
                    _judgment_assumption(name="REVENUE_GROWTH", value=str(growth_value)),
                    _judgment_assumption(name="OPERATING_MARGIN", value="10"),
                ),
            ),
            _scenario(ThesisScenario.BEAR, growth="0", margin="7"),
        ),
        requested_metrics=(METRIC_REVENUE,),
    )
    base = next(s for s in result.scenarios if s.scenario is ThesisScenario.BASE)
    used_growth = next(a for a in base.assumptions if a.name == "REVENUE_GROWTH")
    assert used_growth.value == growth_value
    revenue = next(v for v in base.metric_values if v.metric == METRIC_REVENUE)
    assert revenue.value == Decimal("1000") * (Decimal(1) + growth_value / Decimal(100))


# ============================================================
# Additional structural tests
# ============================================================


def test_unsupported_metric_is_rejected() -> None:
    result = _compute(requested_metrics=("EPS",))
    assert result.status is ForecastStatus.UNSUPPORTED_METRIC


def test_missing_scenario_is_insufficient_input() -> None:
    result = _compute(
        scenario_assumptions=(
            _scenario(ThesisScenario.BULL, growth="10", margin="11"),
            _scenario(ThesisScenario.BASE, growth="6", margin="10"),
        )
    )
    assert result.status is ForecastStatus.INSUFFICIENT_INPUT


def test_duplicate_scenario_raises_schema_error() -> None:
    with pytest.raises(ForecastSchemaError):
        _compute(
            scenario_assumptions=(
                _scenario(ThesisScenario.BASE, growth="6", margin="10"),
                _scenario(ThesisScenario.BASE, growth="5", margin="9"),
                _scenario(ThesisScenario.BEAR, growth="0", margin="7"),
            )
        )


def test_entity_mismatch_in_historical_base_is_identity_mismatch() -> None:
    mismatched_base = HistoricalFundamentalBase(
        entity_id="9999",
        metric=METRIC_REVENUE,
        period="FY2026",
        value=Decimal("1000"),
        unit="JPY",
        currency="JPY",
        source_id="JQUANTS_FINS_SUMMARY",
        available_at=_BASE_AVAILABLE_AT,
        provenance_ref="M1",
    )
    result = _compute(historical_bases=(mismatched_base,))
    assert result.status is ForecastStatus.IDENTITY_MISMATCH


def test_operating_income_alone_computes_revenue_as_internal_dependency() -> None:
    """Regression(/code-review high指摘, D0109): `OPERATING_INCOME`のみを
    `requested_metrics`へ指定した場合(`REVENUE`自体は要求しない)でも、
    `REVENUE`は内部依存として計算され、Historical Base/REVENUE_GROWTH
    Assumptionが揃っていれば`SUCCESS`になる——`REVENUE`がrequested_
    metricsに無いことを理由に無条件で`INSUFFICIENT_INPUT`にならない。
    `REVENUE`自体は`metric_values`へ公開されない。"""
    result = _compute(requested_metrics=(METRIC_OPERATING_INCOME,))
    assert result.status is ForecastStatus.SUCCESS
    base = next(s for s in result.scenarios if s.scenario is ThesisScenario.BASE)
    metrics_present = {v.metric for v in base.metric_values}
    assert metrics_present == {METRIC_OPERATING_INCOME}
    oi = next(v for v in base.metric_values if v.metric == METRIC_OPERATING_INCOME)
    assert oi.value == Decimal("106.000")


def test_naive_datetime_evidence_cutoff_raises_schema_error_not_type_error() -> None:
    """Regression(/code-review high指摘, D0109): `evidence_cutoff`が
    tz-awareでない場合、Historical Base/EvidenceとのDatetime比較で生の
    `TypeError`を漏らさず、`ForecastSchemaError`で明示的にFail Closed
    する。"""
    naive_cutoff = datetime(2026, 9, 1)  # noqa: DTZ001 -- 意図的にtz-naive(Regression対象そのもの)
    with pytest.raises(ForecastSchemaError):
        compute_fundamental_forecast(
            result_id="R_NAIVE",
            entity_id="7203",
            target_period="FY2027",
            requested_metrics=(METRIC_REVENUE,),
            scenario_assumptions=_three_scenarios(),
            historical_bases=(_historical_revenue_base(),),
            evidence_cutoff=naive_cutoff,
            research_snapshot_id="SNAP1",
            forecast_created_at=_NOW,
        )


def test_forecast_assumption_value_must_be_decimal() -> None:
    """Regression(/code-review high指摘, D0109): `ForecastAssumption.
    value`に`Decimal`以外(float/int等)を渡した場合、Engine内部の
    計算で生の`TypeError`を漏らさず、構築時点で`ForecastSchemaError`に
    する。"""
    with pytest.raises(ForecastSchemaError):
        ForecastAssumption(
            name="REVENUE_GROWTH",
            value=10.0,  # type: ignore[arg-type]
            unit="PERCENT",
            source=AssumptionSource.RESEARCH_JUDGMENT,
            rationale="test",
            created_at=_NOW,
        )


def test_unused_stale_evidence_derived_assumption_does_not_block_unrelated_metric() -> None:
    """Regression(/code-review high指摘, D0109): `requested_metrics`に
    実際には使われないEVIDENCE_DERIVED Assumption(別のMetric用)が、
    PIT違反のEvidenceを参照していても、要求されたMetric自体の計算を
    `PIT_INVALID`で巻き込まない。"""
    future_evidence = _evidence_record(evidence_id="E_UNUSED_FUTURE", available_at=datetime(2026, 9, 10, tzinfo=UTC))
    unused_evidence_assumption = ForecastAssumption(
        name="REVENUE_GROWTH",
        value=Decimal("6"),
        unit="PERCENT",
        source=AssumptionSource.EVIDENCE_DERIVED,
        evidence_ids=("E_UNUSED_FUTURE",),
        created_at=_NOW,
    )
    base_scenario = ScenarioAssumptions(
        scenario=ThesisScenario.BASE,
        assumptions=(unused_evidence_assumption, _judgment_assumption(name="OPERATING_MARGIN", value="10")),
    )
    scenarios = (
        _scenario(ThesisScenario.BULL, growth="10", margin="11"),
        base_scenario,
        _scenario(ThesisScenario.BEAR, growth="0", margin="7"),
    )
    # REVENUE_GROWTHを要求しない(OPERATING_MARGINのみ要求)ため、
    # unused_evidence_assumptionはこのRequestには無関係。
    result = _compute(
        scenario_assumptions=scenarios,
        requested_metrics=(METRIC_OPERATING_MARGIN,),
        evidence_records=(future_evidence,),
    )
    assert result.status is ForecastStatus.SUCCESS


# ============================================================
# D0109 §29: No Valuation / §30: No Probability
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


def test_no_valuation_logic_added() -> None:
    for module_path in (model_module.__file__, engine_module.__file__):
        identifiers = _module_identifiers(module_path)
        for forbidden in (
            "FairValue",
            "fair_value",
            "TargetPrice",
            "target_price",
            "DiscountedCashFlow",
            "ImpliedGrowth",
            "expected_return",
            "ExpectedReturn",
            "BUY",
            "SELL",
            "PortfolioOptimizer",
            "PositionSizing",
        ):
            assert forbidden not in identifiers, f"{module_path} に禁止識別子 {forbidden!r} が含まれています"


def test_no_scenario_probability_added() -> None:
    for module_path in (model_module.__file__, engine_module.__file__):
        identifiers = _module_identifiers(module_path)
        for forbidden in ("probability", "Probability", "bull_probability", "base_probability", "bear_probability"):
            assert forbidden not in identifiers, f"{module_path} に禁止識別子 {forbidden!r} が含まれています"


def test_no_decision_logic_added() -> None:
    for module_path in (model_module.__file__, engine_module.__file__):
        source = Path(module_path).read_text(encoding="utf-8")
        assert "DecisionRecord" not in source
        assert "build_decision_record" not in source


def test_forecasting_modules_have_no_llm_dependency() -> None:
    for module_path in (model_module.__file__, engine_module.__file__):
        source = Path(module_path).read_text(encoding="utf-8")
        for forbidden in ("import openai", "import anthropic", "requests.post", "httpx.", ".classify(", ".extract("):
            assert forbidden not in source


def test_forecasting_modules_do_not_touch_h0001() -> None:
    for module_path in (model_module.__file__, engine_module.__file__):
        source = Path(module_path).read_text(encoding="utf-8")
        assert "H0001" not in source
        assert "locked_test" not in source.lower()


def test_forecasting_reuses_d0107_prediction_record_does_not_duplicate_storage() -> None:
    source = Path(evaluation_model_module.__file__).read_text(encoding="utf-8")
    assert "FundamentalForecastResult" not in source
    assert "ForecastAssumption" not in source
    for module_path in (model_module.__file__, engine_module.__file__):
        source = Path(module_path).read_text(encoding="utf-8")
        assert "class PredictionRecord" not in source
        assert "AppendOnlyRecordStore" not in source
