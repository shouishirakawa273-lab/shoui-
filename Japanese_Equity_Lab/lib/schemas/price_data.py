"""価格データ: raw OHLCV / corporate actions / adjusted OHLCV を明確に分離する。

調整済みデータだけを保存すると、後から調整方法の誤りに気付けない。
必ずrawとcorporate actionsを別々に保持し、adjustedは両者から再現可能な形にする。
Ver.1はキャピタルゲイン研究が主目的のため、株式分割・併合による価格連続性のみを補正し、
配当再投資によるTotal Return化は行わない(RESEARCH_RULES.md参照)。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum

from lib.errors import LookAheadBiasError
from lib.schemas.base import RecordMeta


class CorporateActionType(StrEnum):
    SPLIT = "SPLIT"
    REVERSE_SPLIT = "REVERSE_SPLIT"
    DIVIDEND = "DIVIDEND"
    MERGER = "MERGER"
    DELISTING = "DELISTING"
    TICKER_CHANGE = "TICKER_CHANGE"


@dataclass(kw_only=True, frozen=True)
class RawOHLCVBar(RecordMeta):
    """調整前の生の日次OHLCV。取得元の値をそのまま保持し、後から書き換えない。"""

    code: str
    session_date: date
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: float | None


@dataclass(kw_only=True, frozen=True)
class CorporateAction(RecordMeta):
    """株式分割・併合・配当・合併・上場廃止等の企業イベント。"""

    code: str
    action_type: CorporateActionType
    effective_date: date
    announced_at: datetime | None = None
    split_ratio: float | None = None  # 分割後株数 / 分割前株数 (SPLIT/REVERSE_SPLITのみ)
    dividend_per_share: float | None = None  # DIVIDENDのみ。Ver.1では価格調整に反映しない。
    note: str | None = None


@dataclass(kw_only=True, frozen=True)
class AdjustedOHLCVBar(RecordMeta):
    """株式分割による価格連続性のみを補正したOHLCV。"""

    code: str
    session_date: date
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: float | None
    split_adjustment_factor: float
    derived_from: str = "raw+corporate_actions"


def apply_split_adjustments(raw_bars: list[RawOHLCVBar], actions: list[CorporateAction]) -> list[AdjustedOHLCVBar]:
    """株式分割・併合のみを反映した調整済みOHLCVを生成する(配当によるTotal Return化はしない)。"""
    splits = sorted(
        (a for a in actions if a.action_type in (CorporateActionType.SPLIT, CorporateActionType.REVERSE_SPLIT)),
        key=lambda a: a.effective_date,
    )
    adjusted: list[AdjustedOHLCVBar] = []
    for bar in sorted(raw_bars, key=lambda b: b.session_date):
        factor = 1.0
        for action in splits:
            if action.split_ratio is not None and bar.session_date < action.effective_date:
                factor *= action.split_ratio
        adjusted.append(
            AdjustedOHLCVBar(
                code=bar.code,
                session_date=bar.session_date,
                open=None if bar.open is None else bar.open / factor,
                high=None if bar.high is None else bar.high / factor,
                low=None if bar.low is None else bar.low / factor,
                close=None if bar.close is None else bar.close / factor,
                volume=None if bar.volume is None else bar.volume * factor,
                split_adjustment_factor=factor,
                source=bar.source,
            )
        )
    return adjusted


def apply_split_adjustments_as_of(
    raw_bars: list[RawOHLCVBar],
    actions: list[CorporateAction],
    *,
    as_of: datetime,
) -> list[AdjustedOHLCVBar]:
    """as_of(decision_at)時点でannounced_at済みのCorporate Actionのみを反映する。

    Adjusted OHLCVをFeature生成に使う場合、as_ofより後にannounceされる
    (=その時点ではまだ知り得ない)株式分割・併合を過去のSignal生成に混入させてはならない。
    announced_atが不明(None)のCorporate Actionは、Point-in-Time安全性を検証できないため
    LookAheadBiasErrorで拒否する(黙って除外せず、呼び出し側にデータ不備を明示する)。
    Raw priceは本関数でも書き換えず、常にRawOHLCVBarのまま不変で保持する。
    """
    if as_of.tzinfo is None:
        raise ValueError("as_of はtz-awareである必要があります")
    unresolved = [a for a in actions if a.announced_at is None]
    if unresolved:
        raise LookAheadBiasError(
            f"announced_atが不明なCorporate Actionが{len(unresolved)}件あり、"
            "Point-in-Time安全性を検証できません(apply_split_adjustments_as_ofには渡せません)。"
        )
    known_actions = [a for a in actions if a.announced_at is not None and a.announced_at <= as_of]
    return apply_split_adjustments(raw_bars, known_actions)
