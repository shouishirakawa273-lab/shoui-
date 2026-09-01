"""Pipeline Validation専用の固定Strategy(パラメータ最適化はしない)。

20営業日Price Return > 0 ならBUYシグナル、次営業日Openで約定、60営業日保有。
このStrategyのPerformanceの良し悪しは評価対象ではない。目的はPipeline全体
(Data -> Feature -> Signal -> Decision -> Execution -> Return -> Benchmark比較 ->
Experiment Registry)が最後まで正常に動くことを確認することであり、
「儲かるStrategyを探すこと」ではない(RESEARCH_RULES.md参照)。

パラメータはこのまま固定して使う。変更したくなった場合はこの定数を書き換えるのではなく、
新しいSTRATEGY_VERSION(ひいては新しいHypothesis/Strategy ID)を発行すること。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from lib.schemas.price_data import AdjustedOHLCVBar

STRATEGY_ID = "S_FIXED_20D_MOMENTUM_V1"
STRATEGY_VERSION = "1.0.0"


class SignalDecision(StrEnum):
    BUY = "BUY"
    NO_SIGNAL = "NO_SIGNAL"


@dataclass(frozen=True)
class FixedMomentumConfig:
    """固定パラメータ。パラメータ探索・最適化の対象にしない。"""

    lookback_days: int = 20
    holding_period_days: int = 60


DEFAULT_CONFIG = FixedMomentumConfig()


def twenty_day_momentum_signal(
    bars_up_to_decision: Sequence[AdjustedOHLCVBar],
    config: FixedMomentumConfig = DEFAULT_CONFIG,
) -> SignalDecision:
    """直近`lookback_days`営業日のPrice Returnが正ならBUYを返す。

    サンプルが不足している、または価格が欠損している場合は、他の値から推測して
    埋めることはせずNO_SIGNALとする。
    """
    ordered = sorted(bars_up_to_decision, key=lambda b: b.session_date)
    if len(ordered) < config.lookback_days + 1:
        return SignalDecision.NO_SIGNAL
    recent = ordered[-1]
    lookback = ordered[-(config.lookback_days + 1)]
    if recent.close is None or lookback.close is None or lookback.close == 0:
        return SignalDecision.NO_SIGNAL
    price_return = recent.close / lookback.close - 1
    return SignalDecision.BUY if price_return > 0 else SignalDecision.NO_SIGNAL


def as_buy_signal_fn(config: FixedMomentumConfig = DEFAULT_CONFIG) -> Callable[[Sequence[AdjustedOHLCVBar]], bool]:
    """BacktestEngine.run()のsignal_fn(bool返却)として使うためのラッパー。"""

    def _signal_fn(bars_up_to_decision: Sequence[AdjustedOHLCVBar]) -> bool:
        return twenty_day_momentum_signal(bars_up_to_decision, config) == SignalDecision.BUY

    return _signal_fn
