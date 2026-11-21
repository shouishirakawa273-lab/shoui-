"""売買代金に対するポジション規模の警告(Step 1、流動性)。

D0112 (`lib/portfolio_risk/engine.py`) は `UNSUPPORTED` に `"LIQUIDITY"` を
明示的に含め、厳密なcapital/constraint算術のみを行う。本モジュールはそれとは
独立しており、D0112の契約を変更しない。

本モジュールが出すのは**警告のための推定値**であり、D0112のような厳密な資本算術
ではない。したがってDecimalの厳密contextではなくfloatを用いる。

PIT安全性は `PriceHistorySource` への依存によって構造的に担保される
(`bars_up_to(code, as_of)` は `session_date <= as_of.date()` のBarのみを返す)。

本モジュールが行わないこと: VaR、CVaR、ストレス較正、共分散ベースの最適化。
これらはD0112の `UNSUPPORTED` のまま据え置く。
"""

from __future__ import annotations

import logging
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from lib.backtest.price_history import PriceHistorySource
from lib.schemas.price_data import AdjustedOHLCVBar

logger = logging.getLogger(__name__)

DEFAULT_WINDOW_SESSIONS = 20
DEFAULT_THRESHOLD_DAYS = 3.0
DEFAULT_MIN_KNOWN_RATIO = 0.75


class LiquidityOutcome(Enum):
    """流動性判定の結果。

    UNKNOWNはOKでもWARNでもない。データ不足で判定できなかったことを表す
    (`Unknownは0ではない。Unknownはfalseでもない。`)。
    """

    OK = "OK"
    WARN = "WARN"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, kw_only=True)
class LiquidityAssessment:
    """1銘柄の流動性判定結果。

    `average_daily_turnover` と `days_to_liquidate` は、判定できなかった場合に
    0ではなくNoneになる。
    """

    code: str
    as_of: datetime
    position_value: float
    window_sessions: int
    sessions_observed: int
    sessions_known: int
    sessions_unknown: int
    average_daily_turnover: float | None
    days_to_liquidate: float | None
    threshold_days: float
    outcome: LiquidityOutcome
    unknown_reason: str | None = None


def _known_turnover(bar: AdjustedOHLCVBar) -> float | None:
    """1Barの売買代金(close×volume)。close/volumeのいずれかが未知ならNone。

    分割調整はcloseを `/factor`、volumeを `*factor` するため、その積である
    売買代金は分割調整に対して不変
    (`lib/schemas/price_data.py:apply_split_adjustments`)。
    """
    close = bar.close
    volume = bar.volume
    if close is None or volume is None:
        return None
    if not (math.isfinite(close) and math.isfinite(volume)):
        return None
    if close < 0 or volume < 0:
        return None
    return close * volume


def assess_liquidity(
    *,
    source: PriceHistorySource,
    code: str,
    position_value: float,
    as_of: datetime,
    window_sessions: int = DEFAULT_WINDOW_SESSIONS,
    threshold_days: float = DEFAULT_THRESHOLD_DAYS,
    min_known_ratio: float = DEFAULT_MIN_KNOWN_RATIO,
) -> LiquidityAssessment:
    """想定ポジション額が直近の平均売買代金の何日分かを評価する。

    欠損日は平均から除外した上で `sessions_unknown` に計上する。前方補完や
    補間による穴埋めは行わない(`根拠不明な数値を生成・推測で補完しない`)。

    既知セッションが `window_sessions * min_known_ratio` に満たない場合、平均は
    信頼できないため OK とはせず UNKNOWN を返す。

    Args:
        source: PIT安全なPrice History。`as_of` 以降のBarは構造的に入らない。
        code: 銘柄コード。
        position_value: 想定ポジション額(円)。
        as_of: 判定時点。
        window_sessions: 平均売買代金を取る直近セッション数。
        threshold_days: この日数を超えるとWARN。
        min_known_ratio: 判定に必要な既知セッションの最低比率。

    Raises:
        ValueError: 引数が判定不能な値(非正のwindow、負のposition_value等)の場合。
    """
    if window_sessions <= 0:
        raise ValueError(f"window_sessions must be positive: {window_sessions}")
    if threshold_days <= 0:
        raise ValueError(f"threshold_days must be positive: {threshold_days}")
    if not 0.0 < min_known_ratio <= 1.0:
        raise ValueError(f"min_known_ratio must be in (0, 1]: {min_known_ratio}")
    if not math.isfinite(position_value) or position_value < 0:
        raise ValueError(f"position_value must be a non-negative finite number: {position_value}")

    bars: Sequence[AdjustedOHLCVBar] = source.bars_up_to(code, as_of)
    window = list(bars)[-window_sessions:]
    sessions_observed = len(window)

    turnovers = [t for t in (_known_turnover(bar) for bar in window) if t is not None]
    sessions_known = len(turnovers)
    sessions_unknown = sessions_observed - sessions_known

    def _unknown(reason: str) -> LiquidityAssessment:
        logger.info("liquidity UNKNOWN for %s at %s: %s", code, as_of.isoformat(), reason)
        return LiquidityAssessment(
            code=code,
            as_of=as_of,
            position_value=position_value,
            window_sessions=window_sessions,
            sessions_observed=sessions_observed,
            sessions_known=sessions_known,
            sessions_unknown=sessions_unknown,
            average_daily_turnover=None,
            days_to_liquidate=None,
            threshold_days=threshold_days,
            outcome=LiquidityOutcome.UNKNOWN,
            unknown_reason=reason,
        )

    required_known = math.ceil(window_sessions * min_known_ratio)
    if sessions_known < required_known:
        return _unknown(f"known sessions {sessions_known} < required {required_known} (observed {sessions_observed})")

    average_turnover = sum(turnovers) / sessions_known
    if average_turnover <= 0:
        return _unknown(f"average daily turnover is not positive: {average_turnover}")

    days_to_liquidate = position_value / average_turnover
    outcome = LiquidityOutcome.WARN if days_to_liquidate > threshold_days else LiquidityOutcome.OK

    return LiquidityAssessment(
        code=code,
        as_of=as_of,
        position_value=position_value,
        window_sessions=window_sessions,
        sessions_observed=sessions_observed,
        sessions_known=sessions_known,
        sessions_unknown=sessions_unknown,
        average_daily_turnover=average_turnover,
        days_to_liquidate=days_to_liquidate,
        threshold_days=threshold_days,
        outcome=outcome,
    )
