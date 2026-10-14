"""Fundamental Forecast Engine: Deterministic Calculator + D0107
Prediction Integration(D0109)。

本Moduleは`compute_fundamental_forecast()`(D0109 §3の
`ForecastInput -> ForecastAssumptionSet -> FundamentalForecast`部分)と
`build_prediction_record_from_forecast()`(`FundamentalForecast ->
PredictionRecord`部分)を提供する唯一のEntrypointである。

## 決定論のみ(D0109 §10/§31)

Model呼び出しは一切行わない(zero model call、D0108と同じ判断:
「D0109 v1に Model Assistanceが不要ならZero Model Callを優先する」
(D0109 §10)という指示に従い、v1では決定論的計算のみを実装した。
`ForecastAssumption.model_version`/`prompt_version`はAssumption自体が
将来Model-Assisted Proposalから来た場合のための前方互換Provenance
Slotとして残すが、本Engine自身はいずれのFieldも設定しない)。

## No Hidden Plug Number(D0109 §11)

必要なHistorical Base/Assumptionが欠落している場合は値を推測で埋めず
`ForecastStatus.INSUFFICIENT_INPUT`を返す。
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

from lib.evaluation.integrity import compute_record_hash
from lib.evaluation.model import (
    BullBaseBearForecast,
    ForecastShape,
    PredictionRecord,
    build_prediction_record,
)
from lib.evidence.model import EvidenceRecord
from lib.evidence.thesis_impact import ThesisScenario
from lib.forecasting.model import (
    ASSUMPTION_OPERATING_INCOME_OVERRIDE,
    ASSUMPTION_OPERATING_MARGIN,
    ASSUMPTION_REVENUE_GROWTH,
    FORMULA_VERSION,
    METRIC_OPERATING_INCOME,
    METRIC_OPERATING_MARGIN,
    METRIC_REVENUE,
    PERCENT_UNIT,
    SUPPORTED_FORECAST_METRICS,
    AssumptionSource,
    ForecastAssumption,
    ForecastMetricValue,
    ForecastSchemaError,
    ForecastStatus,
    FundamentalForecastResult,
    HistoricalFundamentalBase,
    ScenarioAssumptions,
    ScenarioFundamentalForecast,
    require_tz_aware,
)

_REQUIRED_SCENARIOS = frozenset({ThesisScenario.BULL, ThesisScenario.BASE, ThesisScenario.BEAR})


def _typed_failure(
    *,
    result_id: str,
    entity_id: str,
    target_period: str,
    forecast_created_at: datetime,
    evidence_cutoff: datetime,
    research_snapshot_id: str,
    formula_version: str,
    status: ForecastStatus,
    reason: str,
    model_version: str | None,
    prompt_version: str | None,
) -> FundamentalForecastResult:
    payload = {
        "result_id": result_id,
        "entity_id": entity_id,
        "target_period": target_period,
        "forecast_created_at": forecast_created_at,
        "evidence_cutoff": evidence_cutoff,
        "research_snapshot_id": research_snapshot_id,
        "formula_version": formula_version,
        "status": status,
        "scenarios": (),
        "reason": reason,
        "model_version": model_version,
        "prompt_version": prompt_version,
    }
    return FundamentalForecastResult(
        result_id=result_id,
        entity_id=entity_id,
        target_period=target_period,
        forecast_created_at=forecast_created_at,
        evidence_cutoff=evidence_cutoff,
        research_snapshot_id=research_snapshot_id,
        formula_version=formula_version,
        status=status,
        scenarios=(),
        reason=reason,
        model_version=model_version,
        prompt_version=prompt_version,
        record_hash=compute_record_hash(payload),
    )


def _find_assumption(assumptions: Sequence[ForecastAssumption], name: str) -> ForecastAssumption | None:
    matches = [a for a in assumptions if a.name == name]
    if len(matches) > 1:
        raise ForecastSchemaError(f"assumption名 {name!r} が複数件あります(Caller側のScenarioAssumptions構築が不正)")
    return matches[0] if matches else None


def _find_historical_base(
    bases: Sequence[HistoricalFundamentalBase], *, entity_id: str, metric: str
) -> tuple[HistoricalFundamentalBase | None, str | None]:
    matches = [b for b in bases if b.metric == metric]
    if len(matches) > 1:
        return None, f"historical_bases 内に metric={metric!r} が複数件あり、どれを使うべきか一意に決まりません"
    if not matches:
        return None, None
    base = matches[0]
    if base.entity_id != entity_id:
        return None, f"historical_bases の entity_id({base.entity_id!r})が対象entity_id({entity_id!r})と一致しません"
    return base, None


def _compute_scenario(
    *,
    scenario_assumptions: ScenarioAssumptions,
    entity_id: str,
    requested_metrics: frozenset[str],
    historical_bases: Sequence[HistoricalFundamentalBase],
    evidence_cutoff: datetime,
    evidence_records: Sequence[EvidenceRecord],
) -> tuple[ScenarioFundamentalForecast | None, ForecastStatus | None, str | None]:
    assumptions = scenario_assumptions.assumptions
    used_assumptions: list[ForecastAssumption] = []
    used_bases: list[HistoricalFundamentalBase] = []
    metric_values: dict[str, ForecastMetricValue] = {}

    # --- どのAssumption名がこのrequested_metricsに実際に必要かを先に
    # 決定する(未使用のEVIDENCE_DERIVED Assumptionが参照する古い/未来の
    # Evidenceだけを理由にForecast全体をPIT_INVALIDにしない、/code-review
    # high Finding)。
    relevant_names: set[str] = set()
    if METRIC_REVENUE in requested_metrics or METRIC_OPERATING_INCOME in requested_metrics:
        relevant_names.add(ASSUMPTION_REVENUE_GROWTH)
    if METRIC_OPERATING_MARGIN in requested_metrics or METRIC_OPERATING_INCOME in requested_metrics:
        relevant_names.add(ASSUMPTION_OPERATING_MARGIN)
    if METRIC_OPERATING_INCOME in requested_metrics:
        relevant_names.add(ASSUMPTION_OPERATING_INCOME_OVERRIDE)

    # --- PIT: EVIDENCE_DERIVED assumptions(relevant_namesのみ検証)-----
    evidence_by_id = {e.evidence_id: e for e in evidence_records}
    for assumption in assumptions:
        if assumption.source is not AssumptionSource.EVIDENCE_DERIVED:
            continue
        if assumption.name not in relevant_names:
            continue
        for evidence_id in assumption.evidence_ids:
            record = evidence_by_id.get(evidence_id)
            if record is None:
                return (
                    None,
                    ForecastStatus.INSUFFICIENT_INPUT,
                    f"assumption={assumption.name!r} が参照する evidence_id={evidence_id!r} が"
                    "evidence_records内に見つかりません(裏付けを検証できません)",
                )
            if not record.is_usable_at(evidence_cutoff):
                return (
                    None,
                    ForecastStatus.PIT_INVALID,
                    f"assumption={assumption.name!r} が参照する evidence_id={evidence_id!r} は"
                    f"evidence_cutoff({evidence_cutoff.isoformat()})時点でPIT利用不可です",
                )

    revenue_value: Decimal | None = None
    revenue_base: HistoricalFundamentalBase | None = None

    if METRIC_REVENUE in requested_metrics or METRIC_OPERATING_INCOME in requested_metrics:
        # OPERATING_INCOME = REVENUE x OPERATING_MARGIN(D0109 §12)のため、
        # REVENUEがrequested_metricsに無くてもOPERATING_INCOMEが要求されて
        # いればREVENUEを内部依存として計算する(REVENUE自体はrequested_
        # metricsに含まれない限りmetric_valuesへ公開しない、/code-review
        # high Finding)。
        growth = _find_assumption(assumptions, ASSUMPTION_REVENUE_GROWTH)
        if growth is None:
            return None, ForecastStatus.INSUFFICIENT_INPUT, "REVENUE_GROWTH assumptionが見つかりません"
        if growth.unit != PERCENT_UNIT:
            return None, ForecastStatus.INVALID_ASSUMPTION, f"REVENUE_GROWTH の unit は{PERCENT_UNIT!r}である必要があります"
        base, base_error = _find_historical_base(historical_bases, entity_id=entity_id, metric=METRIC_REVENUE)
        if base_error is not None:
            return None, ForecastStatus.IDENTITY_MISMATCH, base_error
        if base is None:
            return None, ForecastStatus.INSUFFICIENT_INPUT, f"metric={METRIC_REVENUE!r} の historical_base が見つかりません"
        if base.available_at > evidence_cutoff:
            return (
                None,
                ForecastStatus.PIT_INVALID,
                f"historical_base(metric=REVENUE)のavailable_at({base.available_at.isoformat()})が"
                f"evidence_cutoff({evidence_cutoff.isoformat()})より後です",
            )
        revenue_value = base.value * (Decimal(1) + growth.value / Decimal(100))
        if revenue_value < 0:
            return None, ForecastStatus.INCONSISTENT_FORECAST, f"計算されたREVENUE({revenue_value})が負数です"
        revenue_base = base
        used_assumptions.append(growth)
        used_bases.append(base)
        if METRIC_REVENUE in requested_metrics:
            metric_values[METRIC_REVENUE] = ForecastMetricValue(metric=METRIC_REVENUE, value=revenue_value, unit=base.unit)

    if METRIC_OPERATING_MARGIN in requested_metrics or METRIC_OPERATING_INCOME in requested_metrics:
        margin = _find_assumption(assumptions, ASSUMPTION_OPERATING_MARGIN)
        if margin is None:
            return None, ForecastStatus.INSUFFICIENT_INPUT, "OPERATING_MARGIN assumptionが見つかりません"
        if margin.unit != PERCENT_UNIT:
            return None, ForecastStatus.INVALID_ASSUMPTION, f"OPERATING_MARGIN の unit は{PERCENT_UNIT!r}である必要があります"
        if margin.value < 0 or margin.value > 100:
            return None, ForecastStatus.INVALID_ASSUMPTION, f"OPERATING_MARGIN({margin.value})は0-100の範囲外です"
        if margin not in used_assumptions:
            used_assumptions.append(margin)
        if METRIC_OPERATING_MARGIN in requested_metrics:
            metric_values[METRIC_OPERATING_MARGIN] = ForecastMetricValue(
                metric=METRIC_OPERATING_MARGIN, value=margin.value, unit=PERCENT_UNIT
            )

        if METRIC_OPERATING_INCOME in requested_metrics:
            if revenue_value is None or revenue_base is None:
                return None, ForecastStatus.INSUFFICIENT_INPUT, "OPERATING_INCOME を計算するには REVENUE が必要です"
            operating_income = revenue_value * (margin.value / Decimal(100))
            override = _find_assumption(assumptions, ASSUMPTION_OPERATING_INCOME_OVERRIDE)
            if override is not None:
                if override.unit != revenue_base.unit:
                    return (
                        None,
                        ForecastStatus.INVALID_ASSUMPTION,
                        f"OPERATING_INCOME Overrideのunit({override.unit!r})がREVENUEのunit({revenue_base.unit!r})と一致しません",
                    )
                if override.value != operating_income:
                    return (
                        None,
                        ForecastStatus.INCONSISTENT_FORECAST,
                        f"OPERATING_MARGIN から導出した OPERATING_INCOME({operating_income})が、"
                        f"明示的な OPERATING_INCOME Assumption({override.value})と一致しません",
                    )
                used_assumptions.append(override)
            metric_values[METRIC_OPERATING_INCOME] = ForecastMetricValue(
                metric=METRIC_OPERATING_INCOME, value=operating_income, unit=revenue_base.unit
            )

    canonical_assumptions = tuple(sorted(used_assumptions, key=lambda a: a.name))
    canonical_bases = tuple(sorted(used_bases, key=lambda b: b.metric))
    canonical_metric_values = tuple(metric_values[m] for m in sorted(metric_values))
    return (
        ScenarioFundamentalForecast(
            scenario=scenario_assumptions.scenario,
            metric_values=canonical_metric_values,
            assumptions=canonical_assumptions,
            historical_bases=canonical_bases,
        ),
        None,
        None,
    )


def compute_fundamental_forecast(
    *,
    result_id: str,
    entity_id: str,
    target_period: str,
    requested_metrics: Sequence[str],
    scenario_assumptions: Sequence[ScenarioAssumptions],
    historical_bases: Sequence[HistoricalFundamentalBase],
    evidence_cutoff: datetime,
    research_snapshot_id: str,
    forecast_created_at: datetime,
    evidence_records: Sequence[EvidenceRecord] = (),
    formula_version: str = FORMULA_VERSION,
    model_version: str | None = None,
    prompt_version: str | None = None,
) -> FundamentalForecastResult:
    """D0109の唯一のForecast計算Entrypoint(D0109 §3)。

    決定論的のみ(Model呼び出し無し、D0109 §10)。Statusの判定順序:
    1. `requested_metrics`がSUPPORTED_FORECAST_METRICSの部分集合である
       こと(`UNSUPPORTED_METRIC`)。
    2. `scenario_assumptions`がBULL/BASE/BEARを重複無く・不足無く含む
       こと(`INSUFFICIENT_INPUT`)。
    3. 各ScenarioについてHistorical Base/Assumptionの充足・Unit整合・
       PIT・内部整合性を検証する(`_compute_scenario()`)。
    いずれかのScenarioが失敗した場合、Result全体をそのStatusでFail
    Closedする(部分的SUCCESSは返さない——Bull/Base/Bearが独立に再現
    可能であることと、Result全体のAtomicityは別概念、D0109 §6/§13)。

    `evidence_cutoff`/`forecast_created_at`がtz-awareでない場合、以降の
    Datetime比較(Historical Base/Evidence PIT判定)が生のTypeErrorに
    なる前に、ここで明示的に`ForecastSchemaError`としてFail Closedする
    (/code-review high Finding)。
    """
    require_tz_aware(evidence_cutoff, label="evidence_cutoff")
    require_tz_aware(forecast_created_at, label="forecast_created_at")

    def _fail(status: ForecastStatus, reason: str) -> FundamentalForecastResult:
        return _typed_failure(
            result_id=result_id,
            entity_id=entity_id,
            target_period=target_period,
            forecast_created_at=forecast_created_at,
            evidence_cutoff=evidence_cutoff,
            research_snapshot_id=research_snapshot_id,
            formula_version=formula_version,
            status=status,
            reason=reason,
            model_version=model_version,
            prompt_version=prompt_version,
        )

    requested = frozenset(requested_metrics)
    unsupported = requested - SUPPORTED_FORECAST_METRICS
    if unsupported:
        return _fail(ForecastStatus.UNSUPPORTED_METRIC, f"未対応のMetricが要求されました: {sorted(unsupported)}")
    if not requested:
        return _fail(ForecastStatus.INSUFFICIENT_INPUT, "requested_metrics が空です")

    scenario_keys = [sa.scenario for sa in scenario_assumptions]
    if len(set(scenario_keys)) != len(scenario_keys):
        raise ForecastSchemaError(f"scenario_assumptions 内に重複したScenarioがあります: {scenario_keys}")
    missing_scenarios = _REQUIRED_SCENARIOS - set(scenario_keys)
    if missing_scenarios:
        return _fail(
            ForecastStatus.INSUFFICIENT_INPUT,
            f"BULL/BASE/BEAR全てが必要ですが不足しています: {sorted(s.value for s in missing_scenarios)}",
        )

    computed_scenarios: list[ScenarioFundamentalForecast] = []
    for sa in scenario_assumptions:
        scenario_forecast, failure_status, failure_reason = _compute_scenario(
            scenario_assumptions=sa,
            entity_id=entity_id,
            requested_metrics=requested,
            historical_bases=historical_bases,
            evidence_cutoff=evidence_cutoff,
            evidence_records=evidence_records,
        )
        if failure_status is not None:
            assert failure_reason is not None
            return _fail(failure_status, f"[{sa.scenario.value}] {failure_reason}")
        assert scenario_forecast is not None
        computed_scenarios.append(scenario_forecast)

    canonical_scenarios = tuple(sorted(computed_scenarios, key=lambda s: s.scenario.value))
    payload = {
        "result_id": result_id,
        "entity_id": entity_id,
        "target_period": target_period,
        "forecast_created_at": forecast_created_at,
        "evidence_cutoff": evidence_cutoff,
        "research_snapshot_id": research_snapshot_id,
        "formula_version": formula_version,
        "status": ForecastStatus.SUCCESS,
        "scenarios": canonical_scenarios,
        "reason": None,
        "model_version": model_version,
        "prompt_version": prompt_version,
    }
    return FundamentalForecastResult(
        result_id=result_id,
        entity_id=entity_id,
        target_period=target_period,
        forecast_created_at=forecast_created_at,
        evidence_cutoff=evidence_cutoff,
        research_snapshot_id=research_snapshot_id,
        formula_version=formula_version,
        status=ForecastStatus.SUCCESS,
        scenarios=canonical_scenarios,
        reason=None,
        model_version=model_version,
        prompt_version=prompt_version,
        record_hash=compute_record_hash(payload),
    )


def build_prediction_record_from_forecast(
    forecast_result: FundamentalForecastResult,
    *,
    metric: str,
    prediction_id: str,
    model_version: str,
    research_pipeline_version: str,
    prompt_version: str | None = None,
    parent_prediction_id: str | None = None,
    target_resolution_at: datetime | None = None,
    existing_predictions: Sequence[PredictionRecord] = (),
) -> PredictionRecord:
    """SUCCESSの`FundamentalForecastResult`から1指標分のBull/Base/Bear
    `PredictionRecord`を構築する(D0109 §17/§18)。

    D0107の既存`BullBaseBearForecast`(新しいForecast Shapeを追加しない)
    へ、各Scenarioの`metric`値をそのまま転記する。D0107 Schema自体は
    一切変更しない(`build_prediction_record()`をそのまま再利用、D0109
    §18)。
    """
    if forecast_result.status is not ForecastStatus.SUCCESS:
        raise ForecastSchemaError(
            f"FundamentalForecastResult(result_id={forecast_result.result_id!r}) は"
            f"status={forecast_result.status!r}(非SUCCESS)のためPredictionRecordを構築できません"
        )
    values_by_scenario: dict[ThesisScenario, ForecastMetricValue] = {}
    for scenario_forecast in forecast_result.scenarios:
        matches = [v for v in scenario_forecast.metric_values if v.metric == metric]
        if len(matches) != 1:
            raise ForecastSchemaError(
                f"FundamentalForecastResult(result_id={forecast_result.result_id!r}) の"
                f"scenario={scenario_forecast.scenario!r} に metric={metric!r} の値がありません"
                "(forecast_result構築時にrequested_metricsへ含めたか確認してください)"
            )
        values_by_scenario[scenario_forecast.scenario] = matches[0]

    missing = _REQUIRED_SCENARIOS - set(values_by_scenario)
    if missing:
        raise ForecastSchemaError(f"BULL/BASE/BEAR全てが必要ですが不足しています: {sorted(s.value for s in missing)}")

    units = {v.unit for v in values_by_scenario.values()}
    if len(units) != 1:
        raise ForecastSchemaError(f"Bull/Base/Bearでunitが一致しません: {units}")
    (unit,) = units

    bull_base_bear = BullBaseBearForecast(
        bull=values_by_scenario[ThesisScenario.BULL].value,
        base=values_by_scenario[ThesisScenario.BASE].value,
        bear=values_by_scenario[ThesisScenario.BEAR].value,
        unit=unit,
    )
    return build_prediction_record(
        prediction_id=prediction_id,
        entity_id=forecast_result.entity_id,
        target=metric,
        target_period=forecast_result.target_period,
        forecast_shape=ForecastShape.BULL_BASE_BEAR,
        bull_base_bear_forecast=bull_base_bear,
        created_at=forecast_result.forecast_created_at,
        evidence_cutoff=forecast_result.evidence_cutoff,
        research_snapshot_id=forecast_result.research_snapshot_id,
        model_version=model_version,
        research_pipeline_version=research_pipeline_version,
        prompt_version=prompt_version,
        parent_prediction_id=parent_prediction_id,
        target_resolution_at=target_resolution_at,
        existing_predictions=existing_predictions,
    )


__all__ = ["build_prediction_record_from_forecast", "compute_fundamental_forecast"]
