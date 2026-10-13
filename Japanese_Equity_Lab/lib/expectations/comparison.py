"""Expectation Comparison: Research Forecast vs Market Expectation Proxy
(D0108 §12/§13)。

既存D0107`PredictionRecord`(Research Forecast、複製しない)と、D0108の
`ConsensusSnapshot`/`ExpectationObservation`/`MarketImpliedAssumptionResult`
(いずれか1つ)との間の、単純な算術差分のみを計算する。

## No Investment Inference(D0108 §12/§23G)

差分の計算のみを行い、投資上の魅力度を一切推測しない——BUY/SELL/
Expected Returnをこのモジュールのいずれの関数も生成しない(本Module
自体にそのようなField/関数が存在しないことをSource Level ASTで確認
する、`13_tests/test_expectations_foundation.py`参照)。

## Fail Closed on Incompatible Comparison(D0108 §13)

比較対象のMetric/Target Period/Unitが一致しない場合は、無言で比較せず
`MarketExpectationsSchemaError`で拒否する。PIT違反(Proxy側の
`available_at`がComparisonの`pit_cutoff`より後)は既存`lib.errors.
LookAheadBiasError`で拒否する(D0108 §6)。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from lib.errors import LookAheadBiasError
from lib.evaluation.integrity import compute_record_hash
from lib.evaluation.model import ForecastShape, PredictionRecord
from lib.expectations.model import (
    ConsensusSnapshot,
    ExpectationObservation,
    ExpectationProxyCategory,
    MarketExpectationsSchemaError,
    StalenessStatus,
    require_nonempty_str,
    require_tz_aware,
)
from lib.expectations.reverse_spec import MarketImpliedAssumptionResult, MarketImpliedResultStatus

PROVENANCE_VERSION = "EXPECTATION_COMPARISON_V1"


class ComparisonSourceType(StrEnum):
    """`ExpectationComparison`の左辺/右辺のSource種別(D0108 §12/§13)。
    左辺は常に`RESEARCH_PREDICTION`(既存D0107 PredictionRecord)。右辺
    はAnalyst Consensus/Company Guidance/Price-Implied/Peer-Implied/
    Other-Explicit-Proxy/Market-Implied Assumptionのいずれか1つ。"""

    RESEARCH_PREDICTION = "RESEARCH_PREDICTION"
    ANALYST_CONSENSUS = "ANALYST_CONSENSUS"
    COMPANY_GUIDANCE = "COMPANY_GUIDANCE"
    PRICE_IMPLIED = "PRICE_IMPLIED"
    PEER_IMPLIED = "PEER_IMPLIED"
    OTHER_EXPLICIT_PROXY = "OTHER_EXPLICIT_PROXY"
    MARKET_IMPLIED_ASSUMPTION = "MARKET_IMPLIED_ASSUMPTION"


_PROXY_CATEGORY_TO_COMPARISON_SOURCE_TYPE: dict[ExpectationProxyCategory, ComparisonSourceType] = {
    ExpectationProxyCategory.ANALYST_CONSENSUS: ComparisonSourceType.ANALYST_CONSENSUS,
    ExpectationProxyCategory.COMPANY_GUIDANCE: ComparisonSourceType.COMPANY_GUIDANCE,
    ExpectationProxyCategory.PRICE_IMPLIED: ComparisonSourceType.PRICE_IMPLIED,
    ExpectationProxyCategory.PEER_IMPLIED: ComparisonSourceType.PEER_IMPLIED,
    ExpectationProxyCategory.OTHER_EXPLICIT_PROXY: ComparisonSourceType.OTHER_EXPLICIT_PROXY,
}


@dataclass(kw_only=True, frozen=True)
class ExpectationComparison:
    """Research Forecastと1件のMarket Expectation Proxy/Market-Implied
    Assumptionとの間の、単純な算術差分(D0108 §12)。BUY/SELL/Expected
    Return等の投資判断Fieldは一切持たない。
    """

    comparison_id: str
    entity_id: str
    metric: str
    target_period: str
    unit: str
    left_source_type: ComparisonSourceType
    left_source_ref: str
    left_value: Decimal
    right_source_type: ComparisonSourceType
    right_source_ref: str
    right_value: Decimal
    right_staleness_status: StalenessStatus
    difference: Decimal
    pit_cutoff: datetime
    compared_at: datetime
    provenance_version: str
    record_hash: str

    def __post_init__(self) -> None:
        for name, value in (
            ("comparison_id", self.comparison_id),
            ("entity_id", self.entity_id),
            ("metric", self.metric),
            ("target_period", self.target_period),
            ("unit", self.unit),
            ("left_source_ref", self.left_source_ref),
            ("right_source_ref", self.right_source_ref),
            ("provenance_version", self.provenance_version),
        ):
            require_nonempty_str(value, label=name)
        require_tz_aware(self.pit_cutoff, label="pit_cutoff")
        require_tz_aware(self.compared_at, label="compared_at")
        if self.left_source_type is not ComparisonSourceType.RESEARCH_PREDICTION:
            raise MarketExpectationsSchemaError("left_source_type は常に RESEARCH_PREDICTION である必要があります")
        if self.right_source_type is ComparisonSourceType.RESEARCH_PREDICTION:
            raise MarketExpectationsSchemaError("right_source_type を RESEARCH_PREDICTION にすることはできません")
        if self.difference != self.left_value - self.right_value:
            raise MarketExpectationsSchemaError("difference は left_value - right_value と一致する必要があります")


def build_expectation_comparison(
    *,
    comparison_id: str,
    entity_id: str,
    metric: str,
    target_period: str,
    unit: str,
    left_source_ref: str,
    left_value: Decimal,
    right_source_type: ComparisonSourceType,
    right_source_ref: str,
    right_value: Decimal,
    pit_cutoff: datetime,
    compared_at: datetime,
    right_staleness_status: StalenessStatus = StalenessStatus.UNKNOWN,
    provenance_version: str = PROVENANCE_VERSION,
) -> ExpectationComparison:
    """`ExpectationComparison`を構築する低位Entrypoint(D0108 §12)。

    左右のMetric/Target Period/Unitが既に同一であることをCallerが保証
    した上で呼ぶ(高位Helper`compare_prediction_to_*()`がこの一致を検証
    してから本関数を呼ぶ、不一致の場合はそちらでFail Closedする)。
    """
    difference = left_value - right_value
    payload = {
        "comparison_id": comparison_id,
        "entity_id": entity_id,
        "metric": metric,
        "target_period": target_period,
        "unit": unit,
        "left_source_type": ComparisonSourceType.RESEARCH_PREDICTION,
        "left_source_ref": left_source_ref,
        "left_value": left_value,
        "right_source_type": right_source_type,
        "right_source_ref": right_source_ref,
        "right_value": right_value,
        "right_staleness_status": right_staleness_status,
        "difference": difference,
        "pit_cutoff": pit_cutoff,
        "compared_at": compared_at,
        "provenance_version": provenance_version,
    }
    return ExpectationComparison(
        comparison_id=comparison_id,
        entity_id=entity_id,
        metric=metric,
        target_period=target_period,
        unit=unit,
        left_source_type=ComparisonSourceType.RESEARCH_PREDICTION,
        left_source_ref=left_source_ref,
        left_value=left_value,
        right_source_type=right_source_type,
        right_source_ref=right_source_ref,
        right_value=right_value,
        right_staleness_status=right_staleness_status,
        difference=difference,
        pit_cutoff=pit_cutoff,
        compared_at=compared_at,
        provenance_version=provenance_version,
        record_hash=compute_record_hash(payload),
    )


def _require_scalar_prediction(prediction: PredictionRecord) -> Decimal:
    if prediction.forecast_shape is not ForecastShape.SCALAR or prediction.scalar_forecast is None:
        raise MarketExpectationsSchemaError(
            f"PredictionRecord(prediction_id={prediction.prediction_id!r}) は forecast_shape=SCALAR"
            "である必要があります(D0108 v1はScalar Forecastのみ比較可能)"
        )
    return prediction.scalar_forecast.value


def compare_prediction_to_consensus_snapshot(
    prediction: PredictionRecord,
    consensus: ConsensusSnapshot,
    *,
    comparison_id: str,
    pit_cutoff: datetime,
    compared_at: datetime,
) -> ExpectationComparison:
    """`PredictionRecord`(Scalar Forecastのみ)と`ConsensusSnapshot`を
    比較する(D0108 §23)。Metric/Target Period不一致、Unit不一致は
    `MarketExpectationsSchemaError`でFail Closedする(§23 C/D/E)。
    `consensus.available_at > pit_cutoff`はLook-ahead(未来のConsensus)
    として`LookAheadBiasError`で拒否する(§23は暗黙のPIT要件、§6本体)。
    """
    left_value = _require_scalar_prediction(prediction)
    if prediction.target != consensus.metric:
        raise MarketExpectationsSchemaError(
            f"Metric不一致: PredictionRecord.target={prediction.target!r} != ConsensusSnapshot.metric={consensus.metric!r}"
        )
    if prediction.target_period != consensus.target_period:
        raise MarketExpectationsSchemaError(
            f"Target Period不一致: PredictionRecord.target_period={prediction.target_period!r} != "
            f"ConsensusSnapshot.target_period={consensus.target_period!r}"
        )
    if consensus.unit is None or prediction.scalar_forecast is None or prediction.scalar_forecast.unit != consensus.unit:
        raise MarketExpectationsSchemaError(
            f"Unit不一致: PredictionRecord.scalar_forecast.unit="
            f"{prediction.scalar_forecast.unit if prediction.scalar_forecast else None!r} != "
            f"ConsensusSnapshot.unit={consensus.unit!r}"
        )
    if consensus.available_at > pit_cutoff:
        raise LookAheadBiasError(
            f"ConsensusSnapshot(consensus_snapshot_id={consensus.consensus_snapshot_id!r}) の"
            f"available_at({consensus.available_at.isoformat()})がpit_cutoff({pit_cutoff.isoformat()})"
            "より後です(未来のConsensus情報)"
        )
    return build_expectation_comparison(
        comparison_id=comparison_id,
        entity_id=prediction.entity_id,
        metric=prediction.target,
        target_period=prediction.target_period,
        unit=consensus.unit,
        left_source_ref=prediction.prediction_id,
        left_value=left_value,
        right_source_type=ComparisonSourceType.ANALYST_CONSENSUS,
        right_source_ref=consensus.consensus_snapshot_id,
        right_value=consensus.value,
        pit_cutoff=pit_cutoff,
        compared_at=compared_at,
    )


def compare_prediction_to_observation(
    prediction: PredictionRecord,
    observation: ExpectationObservation,
    *,
    comparison_id: str,
    pit_cutoff: datetime,
    compared_at: datetime,
) -> ExpectationComparison:
    """`PredictionRecord`(Scalar Forecastのみ)と汎用`ExpectationObserva
    tion`(Company Guidance/Price-Implied/Peer-Implied/Other-Explicit-
    Proxy)を比較する(D0108 §23)。`observation.category`から
    `right_source_type`を自動導出する(Analyst ConsensusはCategoryを
    問わず誤って混同できない)。
    """
    left_value = _require_scalar_prediction(prediction)
    if prediction.target != observation.metric:
        raise MarketExpectationsSchemaError(
            f"Metric不一致: PredictionRecord.target={prediction.target!r} != ExpectationObservation.metric={observation.metric!r}"
        )
    if prediction.target_period != observation.target_period:
        raise MarketExpectationsSchemaError(
            f"Target Period不一致: PredictionRecord.target_period={prediction.target_period!r} != "
            f"ExpectationObservation.target_period={observation.target_period!r}"
        )
    if prediction.scalar_forecast is None or prediction.scalar_forecast.unit != observation.unit:
        raise MarketExpectationsSchemaError(
            f"Unit不一致: PredictionRecord.scalar_forecast.unit="
            f"{prediction.scalar_forecast.unit if prediction.scalar_forecast else None!r} != "
            f"ExpectationObservation.unit={observation.unit!r}"
        )
    if observation.available_at > pit_cutoff:
        raise LookAheadBiasError(
            f"ExpectationObservation(observation_id={observation.observation_id!r}) の"
            f"available_at({observation.available_at.isoformat()})がpit_cutoff({pit_cutoff.isoformat()})"
            "より後です(未来のExpectation情報)"
        )
    return build_expectation_comparison(
        comparison_id=comparison_id,
        entity_id=prediction.entity_id,
        metric=prediction.target,
        target_period=prediction.target_period,
        unit=observation.unit,
        left_source_ref=prediction.prediction_id,
        left_value=left_value,
        right_source_type=_PROXY_CATEGORY_TO_COMPARISON_SOURCE_TYPE[observation.category],
        right_source_ref=observation.observation_id,
        right_value=observation.value,
        right_staleness_status=observation.staleness_status,
        pit_cutoff=pit_cutoff,
        compared_at=compared_at,
    )


def compare_prediction_to_market_implied_result(
    prediction: PredictionRecord,
    result: MarketImpliedAssumptionResult,
    *,
    solve_for_variable_name: str,
    comparison_id: str,
    pit_cutoff: datetime,
    compared_at: datetime,
) -> ExpectationComparison:
    """`PredictionRecord`(Scalar Forecastのみ)と`MarketImpliedAssumption
    Result`(`status=SUCCESS`のみ)の`solve_for_variable_name`に対応する
    `SolvedVariable`を比較する(D0108 §23)。`status != SUCCESS`の場合は
    比較不能として明示的に拒否する(Caller側でStatusを確認してから呼ぶ
    こと、非SUCCESSから値を推測しない)。

    `prediction.target`と`solve_for_variable_name`が異なるMetricを指す
    場合はFail Closedする(他の`compare_prediction_to_*()`と同じ
    Metric一致要件、片方のMetricが実は別の変数という不整合なComparison
    を防ぐ、/code-review high Finding)。`result.computed_at`(この
    SolverによってこのResultが初めて知り得た時刻)が`pit_cutoff`より後の
    場合は`LookAheadBiasError`で拒否する(他の`compare_prediction_to_*()`
    が`available_at`でGateするのと同じPIT原則、/code-review high
    Finding)。
    """
    if result.status is not MarketImpliedResultStatus.SUCCESS:
        raise MarketExpectationsSchemaError(
            f"MarketImpliedAssumptionResult(result_id={result.result_id!r}) は"
            f"status={result.status!r}(非SUCCESS)のため比較できません"
        )
    if prediction.target != solve_for_variable_name:
        raise MarketExpectationsSchemaError(
            f"Metric不一致: PredictionRecord.target={prediction.target!r} != solve_for_variable_name={solve_for_variable_name!r}"
        )
    if result.computed_at > pit_cutoff:
        raise LookAheadBiasError(
            f"MarketImpliedAssumptionResult(result_id={result.result_id!r}) の"
            f"computed_at({result.computed_at.isoformat()})がpit_cutoff({pit_cutoff.isoformat()})"
            "より後です(未来のMarket-Implied Assumption情報)"
        )
    left_value = _require_scalar_prediction(prediction)
    solved = next((v for v in result.solved_values if v.name == solve_for_variable_name), None)
    if solved is None:
        raise MarketExpectationsSchemaError(
            f"MarketImpliedAssumptionResult(result_id={result.result_id!r}) に"
            f"solve_for_variable_name={solve_for_variable_name!r} のSolvedVariableがありません"
        )
    if prediction.scalar_forecast is None or prediction.scalar_forecast.unit != solved.unit:
        raise MarketExpectationsSchemaError(
            f"Unit不一致: PredictionRecord.scalar_forecast.unit="
            f"{prediction.scalar_forecast.unit if prediction.scalar_forecast else None!r} != "
            f"SolvedVariable.unit={solved.unit!r}"
        )
    return build_expectation_comparison(
        comparison_id=comparison_id,
        entity_id=prediction.entity_id,
        metric=prediction.target,
        target_period=prediction.target_period,
        unit=solved.unit,
        left_source_ref=prediction.prediction_id,
        left_value=left_value,
        right_source_type=ComparisonSourceType.MARKET_IMPLIED_ASSUMPTION,
        right_source_ref=result.result_id,
        right_value=solved.value,
        pit_cutoff=pit_cutoff,
        compared_at=compared_at,
    )


__all__ = [
    "PROVENANCE_VERSION",
    "ComparisonSourceType",
    "ExpectationComparison",
    "build_expectation_comparison",
    "compare_prediction_to_consensus_snapshot",
    "compare_prediction_to_market_implied_result",
    "compare_prediction_to_observation",
]
