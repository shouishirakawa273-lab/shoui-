"""保有候補間の日次リターン相関の警告(Step 1、相関)。

D0112 (`lib/portfolio_risk/engine.py`) は `UNSUPPORTED` に `"CORRELATION"` を
明示的に含める。本モジュールはそれとは独立しており、D0112の契約を変更しない。

業種分類による集中度チェックは相関の粗い代理変数にすぎない。業種が異なっても
同一要因(金利等)で同時に動く銘柄群は、業種制約を通過してしまう。本モジュールは
実際の日次リターンから相関を推定し、その見落としを埋める。

出すのは**警告のための推定値**であり、共分散ベースの最適化入力ではない。
平均分散最適化、VaR、CVaR、ストレス較正は行わない。

PIT境界は `lib/pretrade_risk/window.py` に集約する(大引け未到来セッションの除外、
重複セッションの排除、古さの計測)。
"""

from __future__ import annotations

import logging
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from itertools import combinations

from lib.backtest.price_history import PriceHistorySource
from lib.pretrade_risk.window import BarWindow, available_bars, require_aware
from lib.schemas.price_data import AdjustedOHLCVBar

logger = logging.getLogger(__name__)

DEFAULT_WINDOW_SESSIONS = 250
DEFAULT_THRESHOLD = 0.7
DEFAULT_MIN_OVERLAP = 60
DEFAULT_MAX_STALENESS_DAYS = 10

ReturnKey = tuple[date, date]
"""リターンの区間キー `(前セッション日, 当該セッション日)`。

欠損で間隔が空いたリターンを、別銘柄の異なる間隔のリターンと誤って対応付けない
ために、単一日付ではなく区間で持つ。

ただしこのキーが保証するのは「長さの違う区間を取り違えない」ことだけで、
「対応付いた区間同士が比較可能である」ことまでは保証しない。両銘柄が同じ日を
欠いている場合、片方は売買停止・片方はProviderの欠損ということがありうる。
その区別には取引カレンダーが要るが、本モジュールは持たない。データの存在から
営業日構造を推定することは `lib/market_calendar.py` が禁じているので推定もせず、
`max_interval_days` として呼び出し側に可視化するに留める。
"""


class CorrelationOutcome(Enum):
    """相関判定の結果。UNKNOWNはOKでもWARNでもない。"""

    OK = "OK"
    WARN = "WARN"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, kw_only=True)
class PairCorrelation:
    """2銘柄間の相関判定結果。判定できなければ `correlation` は0ではなくNone。"""

    code_a: str
    code_b: str
    overlapping_returns: int
    correlation: float | None
    max_interval_days: int | None
    """対応付いた区間のうち最大の暦日幅。通常の週末跨ぎは3。

    これを大きく超える値は、売買停止やデータ欠損を挟んだ区間が標本に混ざって
    いることを示す。営業日数ではない(上の `ReturnKey` 参照)。
    """
    threshold: float
    outcome: CorrelationOutcome
    unknown_reason: str | None = None


@dataclass(frozen=True, kw_only=True)
class CodeCoverage:
    """1銘柄ぶんの観測カバレッジ。要求した期間ではなく実際に得られた範囲。"""

    code: str
    sessions_observed: int
    duplicate_sessions_dropped: int
    first_session: date | None
    last_session: date | None
    staleness_days: int | None
    stale: bool


@dataclass(frozen=True, kw_only=True)
class CorrelationAssessment:
    """保有候補全体の相関判定結果。"""

    as_of: datetime
    codes: tuple[str, ...]
    window_sessions: int
    min_overlap: int
    threshold: float
    max_staleness_days: int
    coverage: tuple[CodeCoverage, ...]
    pairs: tuple[PairCorrelation, ...]

    @property
    def warned_pairs(self) -> tuple[PairCorrelation, ...]:
        return tuple(p for p in self.pairs if p.outcome is CorrelationOutcome.WARN)

    @property
    def unknown_pairs(self) -> tuple[PairCorrelation, ...]:
        return tuple(p for p in self.pairs if p.outcome is CorrelationOutcome.UNKNOWN)


def _returns_by_interval(bars: Sequence[AdjustedOHLCVBar]) -> dict[ReturnKey, float]:
    """隣接Barから日次リターンを作り、区間キーで返す。

    前終値・当終値のいずれかが未知、前終値が正でない、結果が非有限の場合は
    そのリターンを作らない(0で埋めない)。Barは `available_bars` が昇順かつ
    `session_date` 一意にして渡す。
    """
    returns: dict[ReturnKey, float] = {}
    for previous, current in zip(bars, bars[1:], strict=False):
        prev_close = previous.close
        curr_close = current.close
        if prev_close is None or curr_close is None:
            continue
        if not (math.isfinite(prev_close) and math.isfinite(curr_close)):
            continue
        if prev_close <= 0:
            continue
        value = curr_close / prev_close - 1.0
        if not math.isfinite(value):
            continue
        returns[(previous.session_date, current.session_date)] = value
    return returns


def _pearson(xs: Sequence[float], ys: Sequence[float]) -> float | None:
    """Pearson相関。いずれかの系列の分散が0なら相関は定義されずNoneを返す。"""
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    dx = [x - mean_x for x in xs]
    dy = [y - mean_y for y in ys]
    var_x = sum(d * d for d in dx)
    var_y = sum(d * d for d in dy)
    if var_x <= 0 or var_y <= 0:
        return None
    value = sum(a * b for a, b in zip(dx, dy, strict=True)) / math.sqrt(var_x * var_y)
    if not math.isfinite(value):
        return None
    return max(-1.0, min(1.0, value))


def _coverage(code: str, window: BarWindow, *, max_staleness_days: int) -> CodeCoverage:
    stale = window.staleness_days is None or window.staleness_days > max_staleness_days
    return CodeCoverage(
        code=code,
        sessions_observed=len(window.bars),
        duplicate_sessions_dropped=window.duplicate_sessions_dropped,
        first_session=window.first_session,
        last_session=window.last_session,
        staleness_days=window.staleness_days,
        stale=stale,
    )


def assess_correlation(
    *,
    source: PriceHistorySource,
    codes: Sequence[str],
    as_of: datetime,
    window_sessions: int = DEFAULT_WINDOW_SESSIONS,
    threshold: float = DEFAULT_THRESHOLD,
    min_overlap: int = DEFAULT_MIN_OVERLAP,
    max_staleness_days: int = DEFAULT_MAX_STALENESS_DAYS,
) -> CorrelationAssessment:
    """保有候補の全ペアについて日次リターン相関を評価する。

    リターンは区間キー `(前セッション日, 当該セッション日)` で対応付ける。
    両銘柄で区間が完全に一致するリターンのみを相関計算に使う。片方に欠損が
    あって間隔が異なる場合、そのリターンは対応付けずに捨てる(無理に揃えない)。

    UNKNOWNになる条件は3つある。いずれもOKにはしない。

    1. 重複本数が `min_overlap` に満たない
    2. どちらかの銘柄の最新セッションが `max_staleness_days` より古い
    3. どちらかの系列の分散が0で相関が定義されない

    警告は正の相関 `> threshold` に対して出す。負の相関は集中ではなく打ち消し
    合いなので警告対象にしないが、`pairs` には全ペアの推定値を含めるため
    呼び出し側から参照できる。

    Raises:
        ValueError: 引数が判定不能な値の場合、codesに重複がある場合、
            または `as_of` がtz-naiveの場合。
    """
    require_aware(as_of)
    if window_sessions <= 1:
        raise ValueError(f"window_sessions must be greater than 1: {window_sessions}")
    if not -1.0 < threshold < 1.0:
        raise ValueError(f"threshold must be in (-1, 1): {threshold}")
    if min_overlap < 2:
        raise ValueError(f"min_overlap must be at least 2: {min_overlap}")
    if max_staleness_days < 0:
        raise ValueError(f"max_staleness_days must be non-negative: {max_staleness_days}")

    ordered_codes = tuple(codes)
    if len(set(ordered_codes)) != len(ordered_codes):
        raise ValueError(f"codes must not contain duplicates: {ordered_codes}")

    windows = {
        code: available_bars(source=source, code=code, as_of=as_of, window_sessions=window_sessions) for code in ordered_codes
    }
    coverage = {code: _coverage(code, window, max_staleness_days=max_staleness_days) for code, window in windows.items()}
    returns_by_code = {code: _returns_by_interval(window.bars) for code, window in windows.items()}

    pairs: list[PairCorrelation] = []
    reason: str | None
    for code_a, code_b in combinations(ordered_codes, 2):
        shared_keys = sorted(returns_by_code[code_a].keys() & returns_by_code[code_b].keys())
        overlap = len(shared_keys)
        max_interval = max(((end - start).days for start, end in shared_keys), default=None)

        def _unknown(reason_text: str, *, a: str = code_a, b: str = code_b, n: int = overlap) -> PairCorrelation:
            logger.info("correlation UNKNOWN for %s/%s at %s: %s", a, b, as_of.isoformat(), reason_text)
            return PairCorrelation(
                code_a=a,
                code_b=b,
                overlapping_returns=n,
                correlation=None,
                max_interval_days=max_interval,
                threshold=threshold,
                outcome=CorrelationOutcome.UNKNOWN,
                unknown_reason=reason_text,
            )

        stale_codes = [c for c in (code_a, code_b) if coverage[c].stale]
        if stale_codes:
            detail = ", ".join(f"{c} last session {coverage[c].last_session}" for c in stale_codes)
            pairs.append(_unknown(f"stale coverage beyond max_staleness_days {max_staleness_days}: {detail}"))
            continue

        if overlap < min_overlap:
            pairs.append(_unknown(f"overlapping returns {overlap} < required {min_overlap}"))
            continue

        correlation = _pearson(
            [returns_by_code[code_a][k] for k in shared_keys],
            [returns_by_code[code_b][k] for k in shared_keys],
        )
        if correlation is None:
            pairs.append(_unknown("zero variance in at least one return series"))
            continue

        reason = None
        outcome = CorrelationOutcome.WARN if correlation > threshold else CorrelationOutcome.OK
        pairs.append(
            PairCorrelation(
                code_a=code_a,
                code_b=code_b,
                overlapping_returns=overlap,
                correlation=correlation,
                max_interval_days=max_interval,
                threshold=threshold,
                outcome=outcome,
                unknown_reason=reason,
            )
        )

    return CorrelationAssessment(
        as_of=as_of,
        codes=ordered_codes,
        window_sessions=window_sessions,
        min_overlap=min_overlap,
        threshold=threshold,
        max_staleness_days=max_staleness_days,
        coverage=tuple(coverage[code] for code in ordered_codes),
        pairs=tuple(pairs),
    )
