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
