"""Phase5 v1: Deterministic Experiment Runner。

新しいBacktest Engineは作らない。既存の`lib.backtest.engine.BacktestEngine`
(D0034/D0035/D0037/D0038で確立済みのPIT-safe実行機構)をそのまま呼び出す、
薄いWrapperに徹する(Phase5 v1要件§39: 既存Backtest Engineの再利用)。

このModuleが新たに追加する制約は2つだけ:

1. **Preregistrationの状態Gate**(VAL-001): `PreregistrationStatus.DRAFT`の
   Preregistrationに従うRunは実行できない。Preregistration自体が
   `preregister()`で明示的に固定された後でなければRunできない、という
   Phase5 v1要件§7の「Preregistrationは全ての実行より先に完了する」を
   構造的に強制する。
2. **Locked Test Gate**: `DataSplit.TEST`(Locked Test)を実行するには、
   `LockedTestGate.assert_unlocked(experiment_id)`を明示的に通過させる。
   RESEARCH_RULES.md「Hidden Test隔離」のAccess段階を実際のRunコマンドへ
   接続する箇所はここだけ。

Train/Validation/Locked Testの期間そのものは`Preregistration`の
`train_period_*`/`validation_period_*`/`locked_test_period_*`から取得し、
Runner自身が期間を選ぶことはしない(Runner側でのパラメータ探索・期間変更を
防ぐ、Phase5 v1要件§11禁止事項)。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from lib.backtest.engine import (
    BacktestEngine,
    BacktestMetrics,
    BacktestRunConfig,
    DataSplit,
    PositionPolicy,
    TransactionCostConfig,
)
from lib.backtest.price_history import PriceHistorySource
from lib.errors import PreregistrationImmutabilityError
from lib.market_calendar import TradingCalendar
from lib.research.locked_test import LockedTestGateProtocol
from lib.research.preregistration import Preregistration, PreregistrationStatus
from lib.schemas.price_data import AdjustedOHLCVBar
from lib.universe import UniverseProvider

# Preregistrationの`parameters`から探すHolding Period Key。値そのものは
# 事前登録済みの文字列であり、Runner側で最適化・変更しない(§11)。
_HOLDING_PERIOD_PARAM_KEY = "holding_period_days"

_SPLIT_TO_PERIOD_FIELDS: dict[DataSplit, tuple[str, str]] = {
    DataSplit.TRAIN: ("train_period_start", "train_period_end"),
    DataSplit.VALIDATION: ("validation_period_start", "validation_period_end"),
    DataSplit.TEST: ("locked_test_period_start", "locked_test_period_end"),
}


@dataclass(frozen=True)
class SplitRunResult:
    """1 split分のRun結果(Metrics + どの期間・Preregistrationで実行したか)。"""

    split: DataSplit
    metrics: BacktestMetrics
    preregistration_id: str
    dataset_contract_hash: str


def _holding_period_days(preregistration: Preregistration) -> int:
    params = dict(preregistration.parameters)
    raw = params.get(_HOLDING_PERIOD_PARAM_KEY)
    if raw is None:
        raise ValueError(
            f"Preregistration.parameters に {_HOLDING_PERIOD_PARAM_KEY!r} がありません"
            "(Runnerは事前登録済みパラメータ以外を使いません、Phase5 v1要件§11)"
        )
    return int(raw)


def run_split(
    *,
    preregistration: Preregistration,
    dataset_contract_hash: str,
    split: DataSplit,
    universe_codes: tuple[str, ...],
    price_history: PriceHistorySource,
    benchmark_bars: Sequence[AdjustedOHLCVBar],
    trading_calendar: TradingCalendar,
    signal_fn: Callable[[Sequence[AdjustedOHLCVBar]], bool],
    sector_by_code: dict[str, str] | None = None,
    universe_provider: UniverseProvider | None = None,
    transaction_cost: TransactionCostConfig | None = None,
    position_policy: PositionPolicy = PositionPolicy.NO_REENTRY_WHILE_POSITION_OPEN,
    locked_test_gate: LockedTestGateProtocol | None = None,
    experiment_id: str | None = None,
) -> SplitRunResult:
    """PreregistrationのCore Termsに従い、1 splitぶんの`BacktestEngine.run()`を実行する。

    `split`が`DataSplit.TEST`(Locked Test)の場合、`locked_test_gate`と
    `experiment_id`が必須で、`locked_test_gate.assert_unlocked(experiment_id)`
    を通らなければ`LockedTestAccessError`で失敗する(先にUnlockが必要)。
    `DataSplit.WALK_FORWARD`はPhase5 v1のScope外(§7、Train/Validation/
    Locked Testの3分割のみ)のため未対応。
    """
    if preregistration.status != PreregistrationStatus.PREREGISTERED:
        raise PreregistrationImmutabilityError(
            f"Preregistration(status={preregistration.status})はまだpreregister()されていません。"
            "PREREGISTERED以前のRunは禁止です(VAL-001、Phase5 v1要件§7)。"
        )
    preregistration.assert_not_mutated()

    if split not in _SPLIT_TO_PERIOD_FIELDS:
        raise ValueError(f"Phase5 v1はTRAIN/VALIDATION/TESTのみ対応しています(split={split})")
    start_field, end_field = _SPLIT_TO_PERIOD_FIELDS[split]
    start_session = getattr(preregistration, start_field)
    end_session = getattr(preregistration, end_field)

    if split == DataSplit.TEST:
        if locked_test_gate is None or experiment_id is None:
            raise PreregistrationImmutabilityError(
                "Locked Test(DataSplit.TEST)の実行には locked_test_gate と experiment_id が必須です"
                "(Hidden Test隔離、RESEARCH_RULES.md参照)"
            )
        locked_test_gate.assert_unlocked(experiment_id)

    config = BacktestRunConfig(
        universe_codes=universe_codes,
        start_session=start_session,
        end_session=end_session,
        holding_period_days=_holding_period_days(preregistration),
        transaction_cost=transaction_cost or TransactionCostConfig(),
        data_split=split,
        position_policy=position_policy,
    )
    metrics = BacktestEngine().run(
        config=config,
        price_history=price_history,
        benchmark_bars=benchmark_bars,
        trading_calendar=trading_calendar,
        signal_fn=signal_fn,
        sector_by_code=sector_by_code,
        universe_provider=universe_provider,
    )
    return SplitRunResult(
        split=split,
        metrics=metrics,
        preregistration_id=preregistration.preregistration_id,
        dataset_contract_hash=dataset_contract_hash,
    )


__all__ = ["SplitRunResult", "run_split"]
