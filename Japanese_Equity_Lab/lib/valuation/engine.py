"""Forward Valuation: Shared Model Formula + D0109 Forecast Integration
(D0110)。

本Moduleの3つの純粋関数(`compute_enterprise_value()`/`compute_equity_
value()`/`compute_value_per_share()`)が**唯一のValuation Model実装**
である。`lib.valuation.reverse`のBisection Solverも同じ3関数をそのまま
呼ぶ(D0110 §2「There must be ONE model contract per valuation
method」)——別々の数式を重複実装しない。

## D0109 Forecast統合(複製しない、D0110 §6/§25)

`evaluate_forward_valuation()`は既存`lib.forecasting.model.
FundamentalForecastResult`をそのまま消費する——新しいForecast
Ledgerは作らない。Evidence Cutoffは常にForecast自身の`evidence_
cutoff`を単一のValuation Cutoffとして使う(別途`decision_at`
Parameterを増やして2つのCutoff概念が分岐することを防ぐ)。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from lib.evaluation.integrity import compute_record_hash
from lib.evidence.thesis_impact import ThesisScenario
from lib.forecasting.model import METRIC_OPERATING_INCOME, ForecastStatus, FundamentalForecastResult
from lib.valuation.forward_reverse_model import (
    VALUATION_MODEL_ID,
    BalanceSheetInputs,
    ScenarioValuationResult,
    ValuationMultiple,
    ValuationResult,
    ValuationStatus,
)

VALUATION_MODEL_VERSION = "V1"
_REQUIRED_SCENARIOS = frozenset({ThesisScenario.BULL, ThesisScenario.BASE, ThesisScenario.BEAR})


def compute_enterprise_value(*, operating_income: Decimal, multiple_value: Decimal) -> Decimal:
    """`EnterpriseValue = OperatingIncome × Multiple`(D0110 §4の唯一の
    Formula)。Forward/Reverse両方がこの関数を直接呼ぶ。"""
    return operating_income * multiple_value


def compute_equity_value(*, enterprise_value: Decimal, net_debt: Decimal) -> Decimal:
    """`EquityValue = EnterpriseValue - NetDebt`。"""
    return enterprise_value - net_debt


def compute_value_per_share(*, equity_value: Decimal, share_count: Decimal) -> Decimal:
    """`ValuePerShare = EquityValue / ShareCount`。`share_count`は呼び
    出し側(`BalanceSheetInputs.__post_init__`)が既に`> 0`を保証して
    いる前提(ここでは再検証しない、Single Source of Truthを保つ)。"""
    return equity_value / share_count


def _evaluate_scenario(
    *,
    scenario: ThesisScenario,
    operating_income: Decimal,
    currency: str,
    multiple: ValuationMultiple,
    balance_sheet: BalanceSheetInputs,
) -> ScenarioValuationResult:
    enterprise_value = compute_enterprise_value(operating_income=operating_income, multiple_value=multiple.value)
    equity_value = compute_equity_value(enterprise_value=enterprise_value, net_debt=balance_sheet.net_debt)
    value_per_share = (
        compute_value_per_share(equity_value=equity_value, share_count=balance_sheet.share_count)
        if balance_sheet.share_count is not None
        else None
    )
    return ScenarioValuationResult(
        scenario=scenario,
        input_operating_income=operating_income,
        estimated_enterprise_value=enterprise_value,
        estimated_equity_value=equity_value,
        estimated_value_per_share=value_per_share,
        currency=currency,
    )


def _typed_failure(
    *,
    result_id: str,
    entity_id: str,
    target_period: str,
    currency: str | None,
    input_forecast_reference: str,
    multiple: ValuationMultiple | None,
    balance_sheet: BalanceSheetInputs | None,
    evidence_cutoff: datetime,
    calculated_at: datetime,
    valuation_model_version: str,
    status: ValuationStatus,
    reason: str,
) -> ValuationResult:
    payload = {
        "result_id": result_id,
        "entity_id": entity_id,
        "valuation_model_id": VALUATION_MODEL_ID,
        "valuation_model_version": valuation_model_version,
        "target_period": target_period,
        "currency": currency,
        "input_forecast_reference": input_forecast_reference,
        "multiple_used": multiple,
        "balance_sheet_used": balance_sheet,
        "scenarios": (),
        "evidence_cutoff": evidence_cutoff,
        "calculated_at": calculated_at,
        "status": status,
        "reason": reason,
    }
    return ValuationResult(
        result_id=result_id,
        entity_id=entity_id,
        valuation_model_id=VALUATION_MODEL_ID,
        valuation_model_version=valuation_model_version,
        target_period=target_period,
        currency=currency,
        input_forecast_reference=input_forecast_reference,
        multiple_used=multiple,
        balance_sheet_used=balance_sheet,
        scenarios=(),
        evidence_cutoff=evidence_cutoff,
        calculated_at=calculated_at,
        status=status,
        reason=reason,
        record_hash=compute_record_hash(payload),
    )


def evaluate_forward_valuation(
    forecast_result: FundamentalForecastResult,
    *,
    result_id: str,
    multiple: ValuationMultiple | None,
    balance_sheet: BalanceSheetInputs | None,
    calculated_at: datetime,
    valuation_model_version: str = VALUATION_MODEL_VERSION,
) -> ValuationResult:
    """D0109の`FundamentalForecastResult`(`status=SUCCESS`、`METRIC_
    OPERATING_INCOME`を含むこと)からBull/Base/Bear独立のForward
    Valuationを計算する唯一のEntrypoint(D0110 §6/§8/§9)。

    `multiple`/`balance_sheet`はOptional——欠落している場合は値を
    推測で埋めず`INSUFFICIENT_INPUT`を返す(D0110 §20「Missing
    required bridge input: INSUFFICIENT_INPUT」)。Evidence Cutoff
    (PIT)は`forecast_result.evidence_cutoff`を単一の基準として使う
    ——`multiple.available_at`/`balance_sheet.net_debt_available_at`/
    `balance_sheet.share_count_available_at`のいずれかがこれより後の
    場合、`PIT_INVALID`でFail Closedする(D0110 §16)。Bull/Base/Bear
    へ確率を付与しない(D0110 §9)。
    """

    currency: str | None = None
    # ↑ Forecastのunitが判明するまでNoneのまま(ValuationResult.currency
    # はstatus=SUCCESS以外ではNoneを許すため、Sentinel文字列は不要、
    # /code-review high Finding)。判明した時点で以下で上書きする。

    def _fail(status: ValuationStatus, reason: str) -> ValuationResult:
        return _typed_failure(
            result_id=result_id,
            entity_id=forecast_result.entity_id,
            target_period=forecast_result.target_period,
            currency=currency,
            input_forecast_reference=forecast_result.result_id,
            multiple=multiple,
            balance_sheet=balance_sheet,
            evidence_cutoff=forecast_result.evidence_cutoff,
            calculated_at=calculated_at,
            valuation_model_version=valuation_model_version,
            status=status,
            reason=reason,
        )

    if multiple is None:
        return _fail(ValuationStatus.INSUFFICIENT_INPUT, "multiple(ValuationMultiple)が指定されていません")
    if balance_sheet is None:
        return _fail(
            ValuationStatus.INSUFFICIENT_INPUT, "balance_sheet(BalanceSheetInputs)が指定されていません(EV→Equity Bridge不能)"
        )

    if forecast_result.status is not ForecastStatus.SUCCESS:
        return _fail(
            ValuationStatus.INSUFFICIENT_INPUT,
            f"FundamentalForecastResult(result_id={forecast_result.result_id!r}) は"
            f"status={forecast_result.status!r}(非SUCCESS)のためValuationできません",
        )

    scenario_keys = [s.scenario for s in forecast_result.scenarios]
    if len(set(scenario_keys)) != len(scenario_keys):
        return _fail(
            ValuationStatus.INVALID_ASSUMPTION,
            f"forecast_result.scenarios 内に重複したScenarioがあります: {[s.value for s in scenario_keys]}"
            "(同一Scenarioの一方が無言で上書きされることを防ぐ)",
        )
    missing_scenarios = _REQUIRED_SCENARIOS - set(scenario_keys)
    if missing_scenarios:
        return _fail(
            ValuationStatus.INSUFFICIENT_INPUT,
            f"BULL/BASE/BEAR全てが必要ですが不足しています: {sorted(s.value for s in missing_scenarios)}",
        )

    operating_income_by_scenario: dict[ThesisScenario, tuple[Decimal, str]] = {}
    for scenario_forecast in forecast_result.scenarios:
        matches = [v for v in scenario_forecast.metric_values if v.metric == METRIC_OPERATING_INCOME]
        if len(matches) != 1:
            return _fail(
                ValuationStatus.INSUFFICIENT_INPUT,
                f"scenario={scenario_forecast.scenario!r} に {METRIC_OPERATING_INCOME!r} の値がありません"
                "(forecast_result構築時にrequested_metricsへ含めたか確認してください)",
            )
        operating_income_by_scenario[scenario_forecast.scenario] = (matches[0].value, matches[0].unit)

    currencies = {unit for _, unit in operating_income_by_scenario.values()}
    if len(currencies) != 1:
        return _fail(ValuationStatus.INVALID_ASSUMPTION, f"Bull/Base/Bearでforecastのunitが一致しません: {currencies}")
    (currency,) = currencies

    if balance_sheet.net_debt_currency != currency:
        return _fail(
            ValuationStatus.INVALID_ASSUMPTION,
            f"BalanceSheetInputs.net_debt_currency({balance_sheet.net_debt_currency!r})がForecastの"
            f"unit({currency!r})と一致しません(Currency混在禁止、D0110 §17)",
        )

    evidence_cutoff = forecast_result.evidence_cutoff
    if multiple.available_at > evidence_cutoff:
        return _fail(
            ValuationStatus.PIT_INVALID,
            f"ValuationMultiple.available_at({multiple.available_at.isoformat()})がevidence_cutoff"
            f"({evidence_cutoff.isoformat()})より後です",
        )
    if balance_sheet.net_debt_available_at > evidence_cutoff:
        return _fail(
            ValuationStatus.PIT_INVALID,
            f"BalanceSheetInputs.net_debt_available_at({balance_sheet.net_debt_available_at.isoformat()})が"
            f"evidence_cutoff({evidence_cutoff.isoformat()})より後です",
        )
    if balance_sheet.share_count_available_at is not None and balance_sheet.share_count_available_at > evidence_cutoff:
        return _fail(
            ValuationStatus.PIT_INVALID,
            f"BalanceSheetInputs.share_count_available_at"
            f"({balance_sheet.share_count_available_at.isoformat()})がevidence_cutoff"
            f"({evidence_cutoff.isoformat()})より後です",
        )

    computed_scenarios = tuple(
        sorted(
            (
                _evaluate_scenario(
                    scenario=scenario,
                    operating_income=operating_income,
                    currency=currency,
                    multiple=multiple,
                    balance_sheet=balance_sheet,
                )
                for scenario, (operating_income, _) in operating_income_by_scenario.items()
            ),
            key=lambda r: r.scenario.value,
        )
    )
    payload = {
        "result_id": result_id,
        "entity_id": forecast_result.entity_id,
        "valuation_model_id": VALUATION_MODEL_ID,
        "valuation_model_version": valuation_model_version,
        "target_period": forecast_result.target_period,
        "currency": currency,
        "input_forecast_reference": forecast_result.result_id,
        "multiple_used": multiple,
        "balance_sheet_used": balance_sheet,
        "scenarios": computed_scenarios,
        "evidence_cutoff": evidence_cutoff,
        "calculated_at": calculated_at,
        "status": ValuationStatus.SUCCESS,
        "reason": None,
    }
    return ValuationResult(
        result_id=result_id,
        entity_id=forecast_result.entity_id,
        valuation_model_id=VALUATION_MODEL_ID,
        valuation_model_version=valuation_model_version,
        target_period=forecast_result.target_period,
        currency=currency,
        input_forecast_reference=forecast_result.result_id,
        multiple_used=multiple,
        balance_sheet_used=balance_sheet,
        scenarios=computed_scenarios,
        evidence_cutoff=evidence_cutoff,
        calculated_at=calculated_at,
        status=ValuationStatus.SUCCESS,
        reason=None,
        record_hash=compute_record_hash(payload),
    )


__all__ = [
    "VALUATION_MODEL_VERSION",
    "compute_enterprise_value",
    "compute_equity_value",
    "compute_value_per_share",
    "evaluate_forward_valuation",
]
