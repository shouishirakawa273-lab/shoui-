"""Phase5 v1 First Hypothesis: Short-term Reversal(単純・低パラメータ数の固定Strategy)。

直近`lookback_days`営業日のPrice Returnが負ならBUYシグナル、次営業日Openで約定、
`holding_period_days`営業日保有。`lib.strategies.fixed_pipeline_validation`
(Momentum、符号が逆)と機構的に対称な単純Ruleであり、「燃え尽きた期間」
(RESEARCH_RULES.md、2022-01-04〜2024-12-30・7203/6758/8056/3626・
20営業日Momentum→60営業日保有)とはMechanism/パラメータ双方で意図的に区別する。

パラメータはPreregistration(`lib.research.preregistration.Preregistration.
parameters`)で事前登録した値のみを使う。このModule自体はパラメータの探索・
最適化を行わない(Phase5 v1要件§11)。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from lib.schemas.price_data import AdjustedOHLCVBar

STRATEGY_ID = "S_SHORT_TERM_REVERSAL_V1"
STRATEGY_VERSION = "1.0.0"


class SignalDecision(StrEnum):
    BUY = "BUY"
    NO_SIGNAL = "NO_SIGNAL"


@dataclass(frozen=True)
class ShortTermReversalConfig:
    """Preregistrationの`parameters`と一致させる値。ここを直接書き換えて再利用しない
    (変更したい場合は新しいPreregistration/Experimentを発行する、Phase5 v1要件§51)。"""

    lookback_days: int = 5
    holding_period_days: int = 10


DEFAULT_CONFIG = ShortTermReversalConfig()


def five_day_reversal_signal(
    bars_up_to_decision: Sequence[AdjustedOHLCVBar],
    config: ShortTermReversalConfig = DEFAULT_CONFIG,
) -> SignalDecision:
    """直近`lookback_days`営業日のPrice Returnが負ならBUYを返す。

    サンプル不足・価格欠損の場合は他の値から推測して埋めず、NO_SIGNALとする
    (`lib.strategies.fixed_pipeline_validation.twenty_day_momentum_signal`と
    同じ欠損時方針)。
    """
    ordered = sorted(bars_up_to_decision, key=lambda b: b.session_date)
    if len(ordered) < config.lookback_days + 1:
        return SignalDecision.NO_SIGNAL
    recent = ordered[-1]
    lookback = ordered[-(config.lookback_days + 1)]
    if recent.close is None or lookback.close is None or lookback.close == 0:
        return SignalDecision.NO_SIGNAL
    price_return = recent.close / lookback.close - 1
    return SignalDecision.BUY if price_return < 0 else SignalDecision.NO_SIGNAL


def as_buy_signal_fn(config: ShortTermReversalConfig = DEFAULT_CONFIG) -> Callable[[Sequence[AdjustedOHLCVBar]], bool]:
    """BacktestEngine.run()のsignal_fn(bool返却)として使うためのラッパー。"""

    def _signal_fn(bars_up_to_decision: Sequence[AdjustedOHLCVBar]) -> bool:
        return five_day_reversal_signal(bars_up_to_decision, config) == SignalDecision.BUY

    return _signal_fn


def config_from_preregistration_parameters(parameters: tuple[tuple[str, str], ...]) -> ShortTermReversalConfig:
    """`Preregistration.parameters`から`ShortTermReversalConfig`を導出する。

    Pre-run skeptic-review MEDIUM Finding(2026-08-19)への対応: 従来は
    `holding_period_days`のみRunner側(`lib.research.runner.run_split`)が
    Preregistrationと照合しており、`lookback_days`はこのModuleの`DEFAULT_
    CONFIG`を呼び出し側が直接使うだけで、Preregistrationとの一致がCode上
    保証されていなかった(Module定数が静かに書き換わってもPreregistration
    Immutability機構では検知できない)。実行するSplitのSignal Thresholdは
    必ずこの関数経由でPreregistrationから導出すること。
    """
    params = dict(parameters)
    if "lookback_days" not in params or "holding_period_days" not in params:
        raise ValueError("parameters に lookback_days / holding_period_days の両方が必要です")
    return ShortTermReversalConfig(
        lookback_days=int(params["lookback_days"]),
        holding_period_days=int(params["holding_period_days"]),
    )
