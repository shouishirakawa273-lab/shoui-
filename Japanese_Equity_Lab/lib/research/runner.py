"""Phase5 v1: Deterministic Experiment Runner。

新しいBacktest Engineは作らない。既存の`lib.backtest.engine.BacktestEngine`
(D0034/D0035/D0037/D0038で確立済みのPIT-safe実行機構)をそのまま呼び出す、
薄いWrapperに徹する(Phase5 v1要件§39: 既存Backtest Engineの再利用)。

このModuleが新たに追加する制約は3つ:

1. **Preregistrationの状態Gate**(VAL-001): `PreregistrationStatus.DRAFT`の
   Preregistrationに従うRunは実行できない。Preregistration自体が
   `preregister()`で明示的に固定された後でなければRunできない、という
   Phase5 v1要件§7の「Preregistrationは全ての実行より先に完了する」を
   構造的に強制する。
2. **Locked Test Gate**: `DataSplit.TEST`(Locked Test)を実行するには、
   `LockedTestGate.assert_unlocked(experiment_id)`を明示的に通過させる。
   RESEARCH_RULES.md「Hidden Test隔離」のAccess段階を実際のRunコマンドへ
   接続する箇所はここだけ。
3. **Split境界Gate**(Pre-run PIT Audit BLOCKER、2026-08-19で発見された実際の
   Bugへの恒久対策): 呼び出し側が渡す`trading_calendar`/`benchmark_bars`が
   そのsplit自身のend_sessionより先の日付を含んでいる場合、`run_split()`は
   `SplitBoundaryLeakageError`で即座に失敗する。呼び出し側は必ずsplitごとに
   `[train_period_start等の開始, そのsplitのend_session]`だけのデータを渡す
   こと(全期間共通のCalendar/Price Historyを使い回すと、Right Censoring
   (D0037)の境界がsplit自身のend_sessionより先へ伸び、Trade ExitがSplit境界
   を越えた後続期間のPriceで決済されうる)。

Train/Validation/Locked Testの期間そのものは`Preregistration`の
`train_period_*`/`validation_period_*`/`locked_test_period_*`から取得し、
Runner自身が期間を選ぶことはしない(Runner側でのパラメータ探索・期間変更を
防ぐ、Phase5 v1要件§11禁止事項)。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass

from lib.backtest.engine import (
    BacktestEngine,
    BacktestMetrics,
    BacktestRunConfig,
    DataSplit,
    PositionPolicy,
    TransactionCostConfig,
)
from lib.backtest.price_history import PriceHistorySource
from lib.errors import PreregistrationImmutabilityError, SplitBoundaryLeakageError
from lib.market_calendar import TradingCalendar
from lib.reproducibility import hash_json_safe
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
    """1 split分のRun結果(Metrics + どの期間・Preregistrationで実行したか)。

    `effective_config_hash` / `effective_transaction_cost_bps`(Post-Phase5
    Hardening B、Codex Transaction Cost Audit Finding3、D0070): 呼び出し側
    (Phase5 Script等)が実際に効いた`BacktestRunConfig`(transaction_cost含む)
    と無関係に独自のconfig_hashを組み立て、実行時に効いたTransaction Cost
    設定がExperiment Recordへ十分伝播しない問題への対応。この2 Fieldは
    `run_split()`が実際に`BacktestEngine.run()`へ渡した`BacktestRunConfig`
    (このsplitで本当に有効だった設定)から直接計算する、Single Source of
    Truth。呼び出し側は独自にconfig_hashを再計算せず、この値をそのまま
    `ReproducibilityFingerprint.config_hash`等へ再利用すること。
    """

    split: DataSplit
    metrics: BacktestMetrics
    preregistration_id: str
    dataset_contract_hash: str
    effective_config_hash: str
    effective_transaction_cost_bps: float


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

    # Split境界の構造的Gate(Pre-run PIT Audit BLOCKER、2026-08-19で確認された
    # 実際のBugに対する恒久対策)。呼び出し側がsplit自身のend_sessionより先の
    # 日付を含むTrading Calendar/Benchmark Barsを誤って渡した場合、
    # `BacktestEngine`のRight Censoring(D0037)がend_session側で正しく機能せず
    # (calendarのrange_endが実際の境界になるため)、Trade ExitがSplit境界を越えた
    # 後続期間(最悪Locked Test期間)のPriceで決済されうる。Runner自身がここで
    # 検証し、Silentに漏れることを防ぐ。
    #
    # 注(price_historyを直接rangeチェックしない理由、Fix確認Pre-run PIT Audit
    # MEDIUM observation): `price_history`(`PriceHistorySource`)はProtocol上
    # `bars_up_to(code, as_of)`のみを提供し、保持しているBarの全期間を列挙する
    # 手段を持たない。ただし`BacktestEngine.run()`はExit Dateを`trading_calendar`
    # で解決した*後*にのみ`price_history`を参照する(range外ならこの時点で
    # `TradingCalendarResolutionError`→`CENSORED_END_OF_SAMPLE`となり、Price
    # 参照自体に到達しない)。したがってこの`trading_calendar`チェックが
    # `price_history`の未来Bar混入も間接的に防ぐ、という不変条件にこのGateは
    # 依存している。この不変条件が崩れる変更(Exit解決順序の変更等)を
    # `lib/backtest/engine.py`へ加える場合は、`price_history`自体への直接的な
    # range検証の追加を再検討すること。
    if trading_calendar.range_end > end_session:
        raise SplitBoundaryLeakageError(
            f"trading_calendar.range_end({trading_calendar.range_end})がsplit={split.value}の"
            f"end_session({end_session})より先です。呼び出し側はこのsplit自身のend_sessionまでの"
            "データのみを渡してください(Split境界を越えたPrice参照防止)。"
        )
    leaking_benchmark_dates = [b.session_date for b in benchmark_bars if b.session_date > end_session]
    if leaking_benchmark_dates:
        raise SplitBoundaryLeakageError(
            f"benchmark_barsにsplit={split.value}のend_session({end_session})より先の日付"
            f"({sorted(leaking_benchmark_dates)[:3]}...)が含まれています。"
        )

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
        effective_config_hash=hash_json_safe(asdict(config)),
        effective_transaction_cost_bps=config.transaction_cost.round_trip_bps(),
    )


__all__ = ["SplitRunResult", "run_split"]
