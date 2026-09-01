"""Phase5 v1 First Hypothesis(H0001)のStrategy Module単体Test。

Pre-run skeptic-review MEDIUM Finding(2026-08-19)への回帰Test: SignalのThreshold
(`lookback_days`)が`Preregistration.parameters`から確実に導出され、Module定数
(`DEFAULT_CONFIG`)への静かな依存に戻らないことを確認する。
"""

from __future__ import annotations

from datetime import date

import pytest
from lib.schemas.price_data import AdjustedOHLCVBar
from lib.strategies.short_term_reversal import (
    ShortTermReversalConfig,
    config_from_preregistration_parameters,
    five_day_reversal_signal,
)


def _bar(code: str, d: date, close: float) -> AdjustedOHLCVBar:
    return AdjustedOHLCVBar(
        code=code,
        session_date=d,
        open=close,
        high=close + 1,
        low=close - 1,
        close=close,
        volume=1000.0,
        split_adjustment_factor=1.0,
        source="synthetic",
    )


def test_config_from_preregistration_parameters_reads_both_fields() -> None:
    config = config_from_preregistration_parameters((("lookback_days", "3"), ("holding_period_days", "7")))
    assert config == ShortTermReversalConfig(lookback_days=3, holding_period_days=7)


def test_config_from_preregistration_parameters_requires_lookback_days() -> None:
    with pytest.raises(ValueError, match="lookback_days"):
        config_from_preregistration_parameters((("holding_period_days", "7"),))


def test_config_from_preregistration_parameters_requires_holding_period_days() -> None:
    with pytest.raises(ValueError, match="lookback_days"):
        config_from_preregistration_parameters((("lookback_days", "3"),))


def test_signal_uses_configured_lookback_days_not_module_default() -> None:
    """異なる`lookback_days`を渡すと、実際に異なるSignal判定になることを確認する
    (Preregistrationのlookback_daysが実際にSignal計算へ反映されることの直接証拠)。"""
    days = [date(2026, 1, d) for d in range(5, 13)]  # 8 sessions
    # 序盤に急落し、直近3営業日は緩やかに回復(上昇)しているが、直近6営業日で見れば
    # まだ下落したまま、という価格列(短期Lookbackと長期Lookbackで判定が割れる)。
    closes = [150, 100, 90, 80, 70, 75, 80, 85]
    bars = [_bar("TEST", d, c) for d, c in zip(days, closes, strict=True)]

    short_lookback = config_from_preregistration_parameters((("lookback_days", "3"), ("holding_period_days", "10")))
    long_lookback = config_from_preregistration_parameters((("lookback_days", "6"), ("holding_period_days", "10")))

    # lookback=3: 直近3営業日(70->85)は上昇 -> NO_SIGNAL
    assert five_day_reversal_signal(bars, short_lookback).value == "NO_SIGNAL"
    # lookback=6: 6営業日前(100)->直近(85)はまだ下落 -> BUY
    assert five_day_reversal_signal(bars, long_lookback).value == "BUY"


def test_five_day_reversal_signal_no_signal_on_insufficient_history() -> None:
    bars = [_bar("TEST", date(2026, 1, 5), 100.0)]
    config = ShortTermReversalConfig(lookback_days=5, holding_period_days=10)
    assert five_day_reversal_signal(bars, config).value == "NO_SIGNAL"
