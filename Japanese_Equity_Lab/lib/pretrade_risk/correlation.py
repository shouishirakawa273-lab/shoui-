"""保有候補間の日次リターン相関の警告(Step 1、相関)。

D0112 (`lib/portfolio_risk/engine.py`) は `UNSUPPORTED` に `"CORRELATION"` を
明示的に含める。本モジュールはそれとは独立しており、D0112の契約を変更しない。

業種分類による集中度チェックは相関の粗い代理変数にすぎない。業種が異なっても
同一要因(金利等)で同時に動く銘柄群は、業種制約を通過してしまう。本モジュールは
実際の日次リターンから相関を推定し、その見落としを埋める。

出すのは**警告のための推定値**であり、共分散ベースの最適化入力ではない。
平均分散最適化、VaR、CVaR、ストレス較正は行わない。

PIT安全性は `PriceHistorySource` への依存によって構造的に担保される。
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
from lib.schemas.price_data import AdjustedOHLCVBar

logger = logging.getLogger(__name__)

DEFAULT_WINDOW_SESSIONS = 250
DEFAULT_THRESHOLD = 0.7
DEFAULT_MIN_OVERLAP = 60

ReturnKey = tuple[date, date]
"""リターンの区間キー `(前セッション日, 当該セッション日)`。

欠損で間隔が空いたリターンを、別銘柄の異なる間隔のリターンと誤って対応付けない
ために、単一日付ではなく区間で持つ。
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
    threshold: float
    outcome: CorrelationOutcome
    unknown_reason: str | None = None


@dataclass(frozen=True, kw_only=True)
class CorrelationAssessment:
    """保有候補全体の相関判定結果。"""

    as_of: datetime
    codes: tuple[str, ...]
    window_sessions: int
    min_overlap: int
    threshold: float
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
    そのリターンを作らない(0で埋めない)。
    """
    ordered = sorted(bars, key=lambda b: b.session_date)
    returns: dict[ReturnKey, float] = {}
    for previous, current in zip(ordered, ordered[1:], strict=False):
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


def assess_correlation(
    *,
    source: PriceHistorySource,
    codes: Sequence[str],
    as_of: datetime,
    window_sessions: int = DEFAULT_WINDOW_SESSIONS,
    threshold: float = DEFAULT_THRESHOLD,
    min_overlap: int = DEFAULT_MIN_OVERLAP,
) -> CorrelationAssessment:
    """保有候補の全ペアについて日次リターン相関を評価する。

    リターンは区間キー `(前セッション日, 当該セッション日)` で対応付ける。
    両銘柄で区間が完全に一致するリターンのみを相関計算に使う。片方に欠損が
    あって間隔が異なる場合、そのリターンは対応付けずに捨てる(無理に揃えない)。

    重複本数が `min_overlap` に満たないペアはUNKNOWNとし、OKとはしない。

    警告は正の相関 `> threshold` に対して出す。負の相関は集中ではなく打ち消し
    合いなので警告対象にしないが、`pairs` には全ペアの推定値を含めるため
    呼び出し側から参照できる。

    Raises:
        ValueError: 引数が判定不能な値の場合、またはcodesに重複がある場合。
    """
    if window_sessions <= 1:
        raise ValueError(f"window_sessions must be greater than 1: {window_sessions}")
    if not -1.0 < threshold < 1.0:
        raise ValueError(f"threshold must be in (-1, 1): {threshold}")
    if min_overlap < 2:
        raise ValueError(f"min_overlap must be at least 2: {min_overlap}")

    ordered_codes = tuple(codes)
    if len(set(ordered_codes)) != len(ordered_codes):
        raise ValueError(f"codes must not contain duplicates: {ordered_codes}")

    # window_sessions本のBarから作れるリターンはwindow_sessions-1本。
    returns_by_code: dict[str, dict[ReturnKey, float]] = {
        code: _returns_by_interval(list(source.bars_up_to(code, as_of))[-window_sessions:]) for code in ordered_codes
    }

    pairs: list[PairCorrelation] = []
    reason: str | None
    for code_a, code_b in combinations(ordered_codes, 2):
        returns_a = returns_by_code[code_a]
        returns_b = returns_by_code[code_b]
        shared_keys = sorted(returns_a.keys() & returns_b.keys())
        overlap = len(shared_keys)

        if overlap < min_overlap:
            reason = f"overlapping returns {overlap} < required {min_overlap}"
            logger.info("correlation UNKNOWN for %s/%s at %s: %s", code_a, code_b, as_of.isoformat(), reason)
            pairs.append(
                PairCorrelation(
                    code_a=code_a,
                    code_b=code_b,
                    overlapping_returns=overlap,
                    correlation=None,
                    threshold=threshold,
                    outcome=CorrelationOutcome.UNKNOWN,
                    unknown_reason=reason,
                )
            )
            continue

        correlation = _pearson([returns_a[k] for k in shared_keys], [returns_b[k] for k in shared_keys])
        if correlation is None:
            reason = "zero variance in at least one return series"
            logger.info("correlation UNKNOWN for %s/%s at %s: %s", code_a, code_b, as_of.isoformat(), reason)
            outcome = CorrelationOutcome.UNKNOWN
        else:
            reason = None
            outcome = CorrelationOutcome.WARN if correlation > threshold else CorrelationOutcome.OK

        pairs.append(
            PairCorrelation(
                code_a=code_a,
                code_b=code_b,
                overlapping_returns=overlap,
                correlation=correlation,
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
        pairs=tuple(pairs),
    )
