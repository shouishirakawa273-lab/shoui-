"""Fundamental Forecast Engine: Core Record Types(D0109)。

D0109は会社Fundamental(Revenue/Operating Income/Operating Margin)の
**Research-derived Forecast**を構築する——Valuation・Expected Return・
BUY/SELL判断は一切含まない(D0110+の責務、本Module自身にそのような
Field/関数が存在しないことをSource Level ASTで確認する、
`13_tests/test_forecasting_foundation.py`参照)。

## 4つの別概念(D0109 §2、絶対に混同しない)

- **OBSERVED HISTORICAL FUNDAMENTAL**(`HistoricalFundamentalBase`):
  過去の実績値。既存`lib.fundamentals`のPIT派生Logicを複製せず、
  Caller(`lib.fundamentals.view.fundamentals_as_of()`等へ既にアクセス
  できる側)が解決済みの値をそのまま受け取る。
- **MANAGEMENT GUIDANCE**: `AssumptionSource.COMPANY_GUIDANCE`
  (既存D0108`lib.expectations.model.ExpectationObservation`
  (`category=COMPANY_GUIDANCE`)への参照を保持するのみ、複製しない)。
- **RESEARCH FORECAST**(`FundamentalForecastResult`): 本Module自身が
  構築する、Research判断に基づくForecast。
- **MARKET EXPECTATION**: `AssumptionSource.MARKET_PROXY`(既存D0108
  `ConsensusSnapshot`/`ExpectationObservation`への参照を保持するのみ)。

## 既存Abstractionの再利用(複製しない)

`ThesisScenario`(Bull/Base/Bear、既存`lib.evidence.thesis_impact`)・
`ThesisImpactReference`(既存`lib.evaluation.model`)・
`compute_record_hash`/`verify_record_integrity`(既存`lib.evaluation.
integrity`)をそのまま再利用する。新しいScenario Enum・新しいHash
Algorithmは作らない。

## Metric Vocabulary(自由文字列、既存規約への追従)

Repository全体(`FundamentalMetric.metric_type`・`ConsensusRecord.
metric_type`・`PredictionRecord.target`)が指標名を固定Enumではなく
自由文字列で表現している(将来の未知指標を型変更無しで扱えるようにする
ための既存設計判断)。D0109もこの既存規約にそのまま従い、新しい型付き
Metric Systemを作らない——v1でSupportする5指標名は`SUPPORTED_FORECAST_
METRICS`という文字列定数のFrozensetとしてのみ宣言する(D0109 §4)。

## v1 Scope: REVENUE/OPERATING_INCOME/OPERATING_MARGINのみ実計算

EPS/FCFは`SUPPORTED_FORECAST_METRICS`に含めない——両指標には
Tax Rate/Share Count/D&A/Working Capital等、追加のAssumption Category
が必要であり、「Full Corporate Financial Modelを作らない」(D0109 §7)
という制約と「§25 Required Acceptance Scenario」の実例(Revenue/
Operating Income/Operating Marginのみ)の両方に従い、v1のScopeから
明示的に除外した判断である(未サポートのMetricを要求した場合は
`ForecastStatus.UNSUPPORTED_METRIC`で明示的にFail Closedする、
推測で埋めない)。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from lib.evaluation.model import ThesisImpactReference
from lib.evidence.thesis_impact import ThesisScenario

FORMULA_VERSION = "FUNDAMENTAL_FORECAST_ENGINE_V1"
"""唯一の決定論的Formula Version識別子(D0109 §12)。本Versionが表す
計算式(`lib.forecasting.engine`で実装、将来のD0107 Evaluation
Reconstructionに十分な精度で再現可能):

    REVENUE = historical_base(REVENUE).value × (1 + REVENUE_GROWTH/100)
    OPERATING_MARGIN = Assumption値そのまま(Pass-through、Deriveしない)
    OPERATING_INCOME = REVENUE × OPERATING_MARGIN/100

Formulaを変更する場合は新しいVersion文字列を発行し、本Versionを書き換
えない(既存Record群の再現性を損なわないため)。
"""

METRIC_REVENUE = "REVENUE"
METRIC_OPERATING_INCOME = "OPERATING_INCOME"
METRIC_OPERATING_MARGIN = "OPERATING_MARGIN"

SUPPORTED_FORECAST_METRICS: frozenset[str] = frozenset({METRIC_REVENUE, METRIC_OPERATING_INCOME, METRIC_OPERATING_MARGIN})

ASSUMPTION_REVENUE_GROWTH = "REVENUE_GROWTH"
ASSUMPTION_OPERATING_MARGIN = "OPERATING_MARGIN"
ASSUMPTION_OPERATING_INCOME_OVERRIDE = "OPERATING_INCOME"
"""Companyガイダンス等から得られる、Margin経由のDerivationとは独立した
明示的Operating Income Assumption(Optional)。両方が与えられた場合、
Engineは両者の整合性を検証する(D0109 §15、Test H)。"""

PERCENT_UNIT = "PERCENT"


class ForecastSchemaError(ValueError):
    """本Module固有のSchema/Invariant違反(呼び出し側のProgramming
    Errorに相当するもの)で送出する(D0103-D0108と同じ方針)。PIT違反・
    Domain-level計算失敗は`lib.forecasting.engine`のTyped Outcome
    (`ForecastStatus`)で表現し、本Errorとは区別する。"""


class AssumptionSource(StrEnum):
    """各Assumptionの出自(D0109 §8)。`RESEARCH_JUDGMENT`を暗黙に
    Evidenceであるかのように主張しない——出自が不明/判断ベースである
    ことを常に可視化する。"""

    HISTORICAL_TREND = "HISTORICAL_TREND"
    COMPANY_GUIDANCE = "COMPANY_GUIDANCE"
    EVIDENCE_DERIVED = "EVIDENCE_DERIVED"
    RESEARCH_JUDGMENT = "RESEARCH_JUDGMENT"
    MARKET_PROXY = "MARKET_PROXY"


class ForecastStatus(StrEnum):
    """`FundamentalForecastResult.status`(D0109 §14)。"""

    SUCCESS = "SUCCESS"
    INSUFFICIENT_INPUT = "INSUFFICIENT_INPUT"
    PIT_INVALID = "PIT_INVALID"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    INVALID_ASSUMPTION = "INVALID_ASSUMPTION"
    UNSUPPORTED_METRIC = "UNSUPPORTED_METRIC"
    INCONSISTENT_FORECAST = "INCONSISTENT_FORECAST"


def require_nonempty_str(value: str, *, label: str) -> None:
    if not isinstance(value, str) or not value:
        raise ForecastSchemaError(f"{label} は空でないstrである必要があります")


def require_tz_aware(value: datetime, *, label: str) -> None:
    if value.tzinfo is None:
        raise ForecastSchemaError(f"{label} はtz-awareである必要があります")


@dataclass(kw_only=True, frozen=True)
class ForecastAssumption:
    """1件の構造化Assumption(D0109 §7)。`source`ごとに要求される
    Provenance Fieldを`__post_init__`で強制する(D0109 §8/§9/§28)。

    `RESEARCH_JUDGMENT`と`EVIDENCE_DERIVED`は相互排他——Judgment
    Assumptionが`evidence_ids`を持つことを許さない(Judgmentが
    EvidenceRecordであるかのようにMasqueradeすることを防ぐ、D0109
    §28D)。
    """

    name: str
    value: Decimal
    unit: str
    source: AssumptionSource
    rationale: str | None = None
    evidence_ids: tuple[str, ...] = ()
    company_guidance_observation_ref: str | None = None
    market_proxy_observation_ref: str | None = None
    thesis_impact_reference: ThesisImpactReference | None = None
    model_version: str | None = None
    prompt_version: str | None = None
    created_at: datetime

    def __post_init__(self) -> None:
        require_nonempty_str(self.name, label="ForecastAssumption.name")
        require_nonempty_str(self.unit, label="ForecastAssumption.unit")
        if not isinstance(self.value, Decimal):
            raise ForecastSchemaError(
                f"ForecastAssumption.value は Decimal である必要があります(実際: {type(self.value).__name__}、"
                "float/int等をそのまま渡さない、計算精度・一貫性のため)"
            )
        if not isinstance(self.source, AssumptionSource):
            raise ForecastSchemaError(f"source は AssumptionSource である必要があります: {self.source!r}")
        require_tz_aware(self.created_at, label="ForecastAssumption.created_at")
        if self.source is AssumptionSource.RESEARCH_JUDGMENT:
            if not self.rationale:
                raise ForecastSchemaError(
                    "source=RESEARCH_JUDGMENT の場合 rationale は必須です"
                    "(Judgmentを無言のDeterministic Factとして偽装しない、D0109 §9)"
                )
            if self.evidence_ids:
                raise ForecastSchemaError(
                    "source=RESEARCH_JUDGMENT のAssumptionはevidence_idsを持てません"
                    "(JudgmentがEvidenceRecordであるかのようにMasqueradeすることを防ぐ、D0109 §28D)"
                )
        elif self.source is AssumptionSource.EVIDENCE_DERIVED:
            if not self.evidence_ids:
                raise ForecastSchemaError(
                    "source=EVIDENCE_DERIVED の場合 evidence_ids は最低1件必要です"
                    "(Evidence裏付けを主張しつつ実際のEvidence参照を持たないことを防ぐ)"
                )
        elif self.source is AssumptionSource.COMPANY_GUIDANCE:
            if not self.company_guidance_observation_ref:
                raise ForecastSchemaError("source=COMPANY_GUIDANCE の場合 company_guidance_observation_ref は必須です")
        elif self.source is AssumptionSource.MARKET_PROXY and not self.market_proxy_observation_ref:
            raise ForecastSchemaError("source=MARKET_PROXY の場合 market_proxy_observation_ref は必須です")


@dataclass(kw_only=True, frozen=True)
class ScenarioAssumptions:
    """1つのScenario(Bull/Base/Bear)に対するAssumption集合(D0109 §6)。
    Scenario間のProbability Weightingは一切保持しない(D0109 §30)。
    """

    scenario: ThesisScenario
    assumptions: tuple[ForecastAssumption, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.scenario, ThesisScenario):
            raise ForecastSchemaError(f"scenario は ThesisScenario である必要があります: {self.scenario!r}")
        names = [a.name for a in self.assumptions]
        if len(set(names)) != len(names):
            raise ForecastSchemaError(f"assumptions 内に重複した名前があります: {names}")


@dataclass(kw_only=True, frozen=True)
class HistoricalFundamentalBase:
    """Forecast計算の基点となる、過去のObserved Historical Fundamental
    (D0109 §22)。既存`lib.fundamentals`のPIT派生Logic(`RevisionHistory`/
    `fundamentals_as_of()`)を複製しない——Caller側が既に解決済みの値
    (`available_at`含む)をそのまま受け取る。
    """

    entity_id: str
    metric: str
    period: str
    value: Decimal
    unit: str
    currency: str | None
    source_id: str
    available_at: datetime
    provenance_ref: str

    def __post_init__(self) -> None:
        for name, value in (
            ("entity_id", self.entity_id),
            ("metric", self.metric),
            ("period", self.period),
            ("unit", self.unit),
            ("source_id", self.source_id),
            ("provenance_ref", self.provenance_ref),
        ):
            require_nonempty_str(value, label=name)
        require_tz_aware(self.available_at, label="available_at")


@dataclass(kw_only=True, frozen=True)
class ForecastMetricValue:
    """1 Scenario内の1指標の計算結果(D0109 §13)。"""

    metric: str
    value: Decimal
    unit: str


@dataclass(kw_only=True, frozen=True)
class ScenarioFundamentalForecast:
    """1つのScenarioについての、計算済みMetric群+使用したAssumption/
    Historical Baseの完全な再構成可能Record(D0109 §13/§34)。
    """

    scenario: ThesisScenario
    metric_values: tuple[ForecastMetricValue, ...]
    assumptions: tuple[ForecastAssumption, ...]
    historical_bases: tuple[HistoricalFundamentalBase, ...]


@dataclass(kw_only=True, frozen=True)
class FundamentalForecastResult:
    """D0109の唯一の公開Result型(D0109 §13、Typed Outcome)。
    `status != SUCCESS`の場合は`scenarios`は空Tupleのまま。
    """

    result_id: str
    entity_id: str
    target_period: str
    forecast_created_at: datetime
    evidence_cutoff: datetime
    research_snapshot_id: str
    formula_version: str
    status: ForecastStatus
    scenarios: tuple[ScenarioFundamentalForecast, ...]
    reason: str | None
    model_version: str | None
    prompt_version: str | None
    record_hash: str

    def __post_init__(self) -> None:
        for name, value in (
            ("result_id", self.result_id),
            ("entity_id", self.entity_id),
            ("target_period", self.target_period),
            ("research_snapshot_id", self.research_snapshot_id),
            ("formula_version", self.formula_version),
        ):
            require_nonempty_str(value, label=name)
        require_tz_aware(self.forecast_created_at, label="forecast_created_at")
        require_tz_aware(self.evidence_cutoff, label="evidence_cutoff")
        if not isinstance(self.status, ForecastStatus):
            raise ForecastSchemaError(f"status は ForecastStatus である必要があります: {self.status!r}")
        if self.status is ForecastStatus.SUCCESS:
            if len(self.scenarios) == 0:
                raise ForecastSchemaError("status=SUCCESS の場合 scenarios は最低1件必要です")
        elif len(self.scenarios) != 0:
            raise ForecastSchemaError(f"status={self.status!r}(非SUCCESS)にも関わらず scenarios が設定されています")


__all__ = [
    "ASSUMPTION_OPERATING_INCOME_OVERRIDE",
    "ASSUMPTION_OPERATING_MARGIN",
    "ASSUMPTION_REVENUE_GROWTH",
    "FORMULA_VERSION",
    "METRIC_OPERATING_INCOME",
    "METRIC_OPERATING_MARGIN",
    "METRIC_REVENUE",
    "PERCENT_UNIT",
    "SUPPORTED_FORECAST_METRICS",
    "AssumptionSource",
    "ForecastAssumption",
    "ForecastMetricValue",
    "ForecastSchemaError",
    "ForecastStatus",
    "FundamentalForecastResult",
    "HistoricalFundamentalBase",
    "ScenarioAssumptions",
    "ScenarioFundamentalForecast",
    "require_nonempty_str",
    "require_tz_aware",
]
