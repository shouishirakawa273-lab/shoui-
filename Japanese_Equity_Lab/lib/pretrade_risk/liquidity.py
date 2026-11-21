"""売買代金に対するポジション規模の警告(Step 1、流動性)。

D0112 (`lib/portfolio_risk/engine.py`) は `UNSUPPORTED` に `"LIQUIDITY"` を
明示的に含め、厳密なcapital/constraint算術のみを行う。本モジュールはそれとは
独立しており、D0112の契約を変更しない。

本モジュールが出すのは**警告のための推定値**であり、D0112のような厳密な資本算術
ではない。したがってDecimalの厳密contextではなくfloatを用いる。

PIT境界は `lib/pretrade_risk/window.py` に集約する。`PriceHistorySource` への依存
だけでは日付粒度の保証しか得られない(`bars_up_to` は `session_date <= as_of.date()`)
ため、大引け未到来のセッションを除外するゲートをそこで追加している。

本モジュールが行わないこと: VaR、CVaR、ストレス較正、共分散ベースの最適化。
これらはD0112の `UNSUPPORTED` のまま据え置く。
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum

from lib.backtest.price_history import PriceHistorySource
from lib.pretrade_risk.window import available_bars
from lib.schemas.price_data import AdjustedOHLCVBar

logger = logging.getLogger(__name__)

DEFAULT_WINDOW_SESSIONS = 20
DEFAULT_THRESHOLD_DAYS = 3.0
DEFAULT_MIN_KNOWN_RATIO = 0.75
DEFAULT_MAX_STALENESS_DAYS = 10


class LiquidityOutcome(Enum):
    """流動性判定の結果。

    UNKNOWNはOKでもWARNでもない。データ不足または古さにより判定できなかったことを
    表す(`Unknownは0ではない。Unknownはfalseでもない。`)。
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
    duplicate_sessions_dropped: int
    first_session: date | None
    last_session: date | None
    staleness_days: int | None
    max_staleness_days: int
    average_daily_turnover: float | None
    days_to_liquidate: float | None
    threshold_days: float
    outcome: LiquidityOutcome
    unknown_reason: str | None = None


def _known_turnover(bar: AdjustedOHLCVBar) -> float | None:
    """1Barの売買代金(close×volume)。close/volumeのいずれかが未知ならNone。

    売買代金は分割調整に対して不変。`build_provider_derived_adjusted_bars`
    (CLIが使う `AsOfAdjustedPriceHistory` の経路)はcloseに累積factorを乗じ
    volumeを同じfactorで除すため積は変わらず、`apply_split_adjustments` は
    逆向きに同じfactorを使うため同様に積は変わらない。いずれの経路でも
    close×volumeは未調整の生の売買代金と一致する。
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
    max_staleness_days: int = DEFAULT_MAX_STALENESS_DAYS,
) -> LiquidityAssessment:
    """想定ポジション額が直近の平均売買代金の何日分かを評価する。

    欠損日は平均から除外した上で `sessions_unknown` に計上する。前方補完や
    補間による穴埋めは行わない(`根拠不明な数値を生成・推測で補完しない`)。

    UNKNOWNになる条件は3つある。いずれもOKにはしない。

    1. 既知セッションが `window_sessions * min_known_ratio` に満たない(履歴が短い)
    2. 最新セッションが `as_of` から `max_staleness_days` より古い(履歴が古い)
    3. 平均売買代金が正でない

    2は上場廃止・長期売買停止・Provider側のカバレッジ切れを捕まえる。履歴の
    **長さ**だけを見ていると、何年も前の売買代金で自信を持ってOKを返してしまう。
    なお `max_staleness_days` は暦日であり営業日ではない(`window.py` 参照)。

    Args:
        source: Price History。`as_of` 時点の利用可能性は `window.available_bars` が担保する。
        code: 銘柄コード。
        position_value: 想定ポジション額(円)。
        as_of: 判定時点。tz-awareでなければならない。
        window_sessions: 平均売買代金を取る直近セッション数。
        threshold_days: この日数を超えるとWARN。
        min_known_ratio: 判定に必要な既知セッションの最低比率。
        max_staleness_days: 最新セッションがこれより古ければUNKNOWN(暦日)。

    Raises:
        ValueError: 引数が判定不能な値の場合、または `as_of` がtz-naiveの場合。
    """
    if window_sessions <= 0:
        raise ValueError(f"window_sessions must be positive: {window_sessions}")
    if threshold_days <= 0:
        raise ValueError(f"threshold_days must be positive: {threshold_days}")
    if not 0.0 < min_known_ratio <= 1.0:
        raise ValueError(f"min_known_ratio must be in (0, 1]: {min_known_ratio}")
    if max_staleness_days < 0:
        raise ValueError(f"max_staleness_days must be non-negative: {max_staleness_days}")
    if not math.isfinite(position_value) or position_value < 0:
        raise ValueError(f"position_value must be a non-negative finite number: {position_value}")

    window = available_bars(source=source, code=code, as_of=as_of, window_sessions=window_sessions)
    sessions_observed = len(window.bars)

    turnovers = [t for t in (_known_turnover(bar) for bar in window.bars) if t is not None]
    sessions_known = len(turnovers)
    sessions_unknown = sessions_observed - sessions_known

    def _result(
        *,
        outcome: LiquidityOutcome,
        average: float | None,
        days: float | None,
        reason: str | None,
    ) -> LiquidityAssessment:
        if reason is not None:
            logger.info("liquidity UNKNOWN for %s at %s: %s", code, as_of.isoformat(), reason)
        return LiquidityAssessment(
            code=code,
            as_of=as_of,
            position_value=position_value,
            window_sessions=window_sessions,
            sessions_observed=sessions_observed,
            sessions_known=sessions_known,
            sessions_unknown=sessions_unknown,
            duplicate_sessions_dropped=window.duplicate_sessions_dropped,
            first_session=window.first_session,
            last_session=window.last_session,
            staleness_days=window.staleness_days,
            max_staleness_days=max_staleness_days,
            average_daily_turnover=average,
            days_to_liquidate=days,
            threshold_days=threshold_days,
            outcome=outcome,
            unknown_reason=reason,
        )

    def _unknown(reason: str) -> LiquidityAssessment:
        return _result(outcome=LiquidityOutcome.UNKNOWN, average=None, days=None, reason=reason)

    required_known = math.ceil(window_sessions * min_known_ratio)
    if sessions_known < required_known:
        return _unknown(f"known sessions {sessions_known} < required {required_known} (observed {sessions_observed})")

    if window.staleness_days is None:
        return _unknown("no settled session available at as_of")
    if window.staleness_days > max_staleness_days:
        return _unknown(
            f"latest session {window.last_session} is {window.staleness_days} calendar days "
            f"before as_of, exceeding max_staleness_days {max_staleness_days}"
        )

    average_turnover = sum(turnovers) / sessions_known
    if average_turnover <= 0:
        return _unknown(f"average daily turnover is not positive: {average_turnover}")

    days_to_liquidate = position_value / average_turnover
    outcome = LiquidityOutcome.WARN if days_to_liquidate > threshold_days else LiquidityOutcome.OK
    return _result(outcome=outcome, average=average_turnover, days=days_to_liquidate, reason=None)
