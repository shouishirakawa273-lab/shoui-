"""Forward + Reverse Valuation Engine: Core Record Types(D0110)。

D0110は最初の本番Valuation計算Layerである。**Forward ValuationとReverse
ValuationはSAME Valuation Model実装(`lib.valuation.engine`の純粋な
`compute_enterprise_value()`/`compute_equity_value()`/`compute_value_
per_share()`)を呼ぶ**(D0110 §2「There must be ONE model contract per
valuation method」)——別々の数式を重複実装しない。

## 既存`lib/valuation/`との関係(複製しない、衝突しない)

既存`lib/valuation/model.py`(D0077+、`LatestReportedFyPerRecord`等)は
Historical Trailing PER Derived Factを扱うまったく別の既存Production
Moduleであり、本Moduleはこれを複製・変更しない(新しいFile名
`forward_reverse_model.py`で衝突を避ける、D0110 §34「Check collisions
before writing」)。本Module(Research Forecast + 明示的Valuation
AssumptionからのForward/Reverse計算)とは目的・入力・Capabilityが異なる。

## v1 Scope: EV/Operating Income Multiple Model

D0109 v1がEPSを予測しない(`lib/forecasting`参照)ため、EPS×PERモデル
ではなくOperating Income Multiple Modelを選択した(D0110 §4「Because
D0109 v1 does not yet forecast EPS, avoid requiring EPS」):

```
EnterpriseValue = ForecastOperatingIncome × EV_OPERATING_INCOME_MULTIPLE
EquityValue     = EnterpriseValue - NetDebt
ValuePerShare   = EquityValue / ShareCount        (ShareCount提供時のみ)
```

既存Peer Multiple Selection Engineは存在しないため新設しない
(D0110 §19)——`ValuationMultiple`はCallerが既に決定済みの値を
Provenance付きで渡す。

## 4つのModel変数(Forward/Reverse共有、D0110 §10)

`OPERATING_INCOME`/`EV_OPERATING_INCOME_MULTIPLE`/`NET_DEBT`/
`SHARE_COUNT`——Reverse Solverはこのいずれか1つを未知変数として解く
(他3つをFixed Assumptionとして)。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from lib.evidence.thesis_impact import ThesisScenario

VALUATION_MODEL_ID = "EV_OPERATING_INCOME_MULTIPLE_V1"
"""D0110 v1が実装する唯一の本番Valuation Model ID(D0110 §3「A single
well-tested model is enough for D0110 v1」)。Formula:
`EnterpriseValue = OperatingIncome × Multiple`、
`EquityValue = EnterpriseValue - NetDebt`、
`ValuePerShare = EquityValue / ShareCount`(ShareCount提供時のみ)。
Formula変更時は新Version文字列を発行し、本IDを書き換えない。
"""

VARIABLE_OPERATING_INCOME = "OPERATING_INCOME"
VARIABLE_EV_OPERATING_INCOME_MULTIPLE = "EV_OPERATING_INCOME_MULTIPLE"
VARIABLE_NET_DEBT = "NET_DEBT"
VARIABLE_SHARE_COUNT = "SHARE_COUNT"

SUPPORTED_SOLVE_VARIABLES: frozenset[str] = frozenset(
    {VARIABLE_OPERATING_INCOME, VARIABLE_EV_OPERATING_INCOME_MULTIPLE, VARIABLE_NET_DEBT, VARIABLE_SHARE_COUNT}
)

UNIT_MULTIPLE = "MULTIPLE"
UNIT_SHARES = "SHARES"


class ValuationSchemaError(ValueError):
    """本Module固有のSchema/Invariant違反(呼び出し側のProgramming
    Errorに相当するもの)で送出する(D0103-D0109と同じ方針)。PIT違反・
    Domain-level計算失敗は`lib.valuation.engine`/`lib.valuation.reverse`
    のTyped Outcome(`ValuationStatus`/D0108`MarketImpliedResultStatus`)
    で表現し、本Errorとは区別する。"""


class MultipleSource(StrEnum):
    """`ValuationMultiple.source`(D0110 §18)。選定されたMultipleを
    客観的Truthとして扱わない——出自を常に可視化する。"""

    HISTORICAL_SELF = "HISTORICAL_SELF"
    PEER_SET = "PEER_SET"
    MARKET_OBSERVED = "MARKET_OBSERVED"
    RESEARCH_JUDGMENT = "RESEARCH_JUDGMENT"


class ValuationStatus(StrEnum):
    """`ValuationResult.status`(D0110 §8、Typed Outcome)。"""

    SUCCESS = "SUCCESS"
    INSUFFICIENT_INPUT = "INSUFFICIENT_INPUT"
    PIT_INVALID = "PIT_INVALID"
    INVALID_ASSUMPTION = "INVALID_ASSUMPTION"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    UNSUPPORTED_MODEL = "UNSUPPORTED_MODEL"


def require_nonempty_str(value: str, *, label: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValuationSchemaError(f"{label} は空でないstrである必要があります")


def require_tz_aware(value: datetime, *, label: str) -> None:
    if value.tzinfo is None:
        raise ValuationSchemaError(f"{label} はtz-awareである必要があります")


def require_decimal(value: object, *, label: str) -> None:
    if not isinstance(value, Decimal):
        raise ValuationSchemaError(
            f"{label} は Decimal である必要があります(実際: {type(value).__name__}、float/int等をそのまま渡さない)"
        )


@dataclass(kw_only=True, frozen=True)
class ValuationMultiple:
    """`EV_OPERATING_INCOME_MULTIPLE`のProvenance付き入力値(D0110 §18)。
    客観的Truthとして扱わない——`source`/`reference_period`/
    `available_at`/`method_version`を常に保持する。

    v1 Model(正のMultiple前提、D0110 §30「negative multiple: likely
    invalid for chosen positive-multiple model → reject」)のため
    `value > 0`を要求する。これは普遍的なFinance Lawではなく、本Model
    固有の制約として明示する。
    """

    value: Decimal
    source: MultipleSource
    reference_period: str
    available_at: datetime
    method_version: str

    def __post_init__(self) -> None:
        require_decimal(self.value, label="ValuationMultiple.value")
        if not isinstance(self.source, MultipleSource):
            raise ValuationSchemaError(f"source は MultipleSource である必要があります: {self.source!r}")
        require_nonempty_str(self.reference_period, label="ValuationMultiple.reference_period")
        require_nonempty_str(self.method_version, label="ValuationMultiple.method_version")
        require_tz_aware(self.available_at, label="ValuationMultiple.available_at")
        if self.value <= 0:
            raise ValuationSchemaError(
                f"ValuationMultiple.value({self.value})は0以下です——{VALUATION_MODEL_ID}は正のMultipleのみ"
                "対応します(D0110 §30、本Model固有の制約)"
            )


@dataclass(kw_only=True, frozen=True)
class BalanceSheetInputs:
    """EV→Equity Bridgeに必要なBalance Sheet入力(D0110 §20/§21)。
    欠落時は0を推測しない——`share_count`は`None`のままにでき、その場合
    `estimated_value_per_share`は計算されない(D0110 §8「'estimated
    value per share' if supported」)。

    `net_debt`は任意の符号を許容する(Net Cashは負のNet Debtとして正当
    な状態、D0110 §30「negative net debt: may represent net cash and
    can be valid」)。`share_count`が設定される場合は`> 0`を要求する
    (D0110 §30「zero shares: reject」)。
    """

    net_debt: Decimal
    net_debt_currency: str
    net_debt_available_at: datetime
    source_id: str
    share_count: Decimal | None = None
    share_count_available_at: datetime | None = None

    def __post_init__(self) -> None:
        require_decimal(self.net_debt, label="BalanceSheetInputs.net_debt")
        require_nonempty_str(self.net_debt_currency, label="BalanceSheetInputs.net_debt_currency")
        require_nonempty_str(self.source_id, label="BalanceSheetInputs.source_id")
        require_tz_aware(self.net_debt_available_at, label="BalanceSheetInputs.net_debt_available_at")
        if self.share_count is not None:
            require_decimal(self.share_count, label="BalanceSheetInputs.share_count")
            if self.share_count <= 0:
                raise ValuationSchemaError(f"BalanceSheetInputs.share_count({self.share_count})は0以下です(D0110 §30)")
            if self.share_count_available_at is None:
                raise ValuationSchemaError(
                    "share_count が設定されている場合 share_count_available_at は必須です(D0110 §21、PIT必須)"
                )
            require_tz_aware(self.share_count_available_at, label="BalanceSheetInputs.share_count_available_at")


@dataclass(kw_only=True, frozen=True)
class ScenarioValuationResult:
    """1 Scenario(Bull/Base/Bear)のValuation計算結果(D0110 §8/§9)。
    Probability Weightingは一切保持しない(D0110 §9)。
    """

    scenario: ThesisScenario
    input_operating_income: Decimal
    estimated_enterprise_value: Decimal
    estimated_equity_value: Decimal
    estimated_value_per_share: Decimal | None
    currency: str


@dataclass(kw_only=True, frozen=True)
class ValuationResult:
    """D0110の唯一の公開Forward Result型(D0110 §8、Typed Outcome)。
    `status != SUCCESS`の場合は`scenarios`は空Tupleのまま。Expected
    Return/BUY-SELL/Price Target Recommendation言語は一切含まない
    (Source Level ASTで確認、`13_tests/test_valuation_forward_
    reverse.py`参照)。
    """

    result_id: str
    entity_id: str
    valuation_model_id: str
    valuation_model_version: str
    target_period: str
    currency: str | None
    input_forecast_reference: str
    multiple_used: ValuationMultiple | None
    balance_sheet_used: BalanceSheetInputs | None
    scenarios: tuple[ScenarioValuationResult, ...]
    evidence_cutoff: datetime
    calculated_at: datetime
    status: ValuationStatus
    reason: str | None
    record_hash: str

    def __post_init__(self) -> None:
        for name, value in (
            ("result_id", self.result_id),
            ("entity_id", self.entity_id),
            ("valuation_model_id", self.valuation_model_id),
            ("valuation_model_version", self.valuation_model_version),
            ("target_period", self.target_period),
            ("input_forecast_reference", self.input_forecast_reference),
        ):
            require_nonempty_str(value, label=name)
        require_tz_aware(self.evidence_cutoff, label="evidence_cutoff")
        require_tz_aware(self.calculated_at, label="calculated_at")
        if not isinstance(self.status, ValuationStatus):
            raise ValuationSchemaError(f"status は ValuationStatus である必要があります: {self.status!r}")
        if self.status is ValuationStatus.SUCCESS:
            if len(self.scenarios) == 0:
                raise ValuationSchemaError("status=SUCCESS の場合 scenarios は最低1件必要です")
            if self.multiple_used is None or self.balance_sheet_used is None:
                raise ValuationSchemaError("status=SUCCESS の場合 multiple_used/balance_sheet_used は必須です")
            if not self.currency:
                raise ValuationSchemaError("status=SUCCESS の場合 currency は必須です")
        elif len(self.scenarios) != 0:
            raise ValuationSchemaError(f"status={self.status!r}(非SUCCESS)にも関わらず scenarios が設定されています")


__all__ = [
    "SUPPORTED_SOLVE_VARIABLES",
    "UNIT_MULTIPLE",
    "UNIT_SHARES",
    "VALUATION_MODEL_ID",
    "VARIABLE_EV_OPERATING_INCOME_MULTIPLE",
    "VARIABLE_NET_DEBT",
    "VARIABLE_OPERATING_INCOME",
    "VARIABLE_SHARE_COUNT",
    "BalanceSheetInputs",
    "MultipleSource",
    "ScenarioValuationResult",
    "ValuationMultiple",
    "ValuationResult",
    "ValuationSchemaError",
    "ValuationStatus",
    "require_decimal",
    "require_nonempty_str",
    "require_tz_aware",
]
