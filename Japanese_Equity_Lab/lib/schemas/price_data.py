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
from lib.market_calendar import session_open_at
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


def is_known_at(action: CorporateAction, as_of: datetime) -> bool:
    """そのCorporate Actionの「存在」がas_of時点で公知になっていたか(known_at = announced_at)。

    Event情報(例:「分割が発表されている」)としてはこの時刻以降利用してよい、という意味の
    Point-in-Time制約。Price Seriesを調整してよいかどうかとは別問題(is_adjustable_at参照)。
    """
    if action.announced_at is None:
        return False
    return action.announced_at <= as_of


def is_adjustable_at(action: CorporateAction, as_of: datetime) -> bool:
    """as_of時点でPrice Seriesの調整に反映してよいか(adjustable_at = effective_dateの寄付)。

    株式分割・併合は効力発生日(ex-date相当)の寄付から株数・価格基準が切り替わる。
    「発表済みだが未実施」の場合、まだ市場では旧基準のまま取引されているため、
    過去のPrice Featureを新基準へ遡って補正してはならない。
    """
    return session_open_at(action.effective_date) <= as_of


def apply_split_adjustments_as_of(
    raw_bars: list[RawOHLCVBar],
    actions: list[CorporateAction],
    *,
    as_of: datetime,
) -> list[AdjustedOHLCVBar]:
    """as_of(decision_at)時点で実際に効力が発生済みのCorporate Actionのみを反映する。

    Corporate Actionには2つの異なる時点がある。
    - known_at (= announced_at): そのCorporate Actionの「存在」が公知になった時刻。
    - adjustable_at (= effective_dateの寄付時刻): 実際に株数・価格基準が切り替わる時刻。

    例: 8/1に分割発表、8/15が意思決定時点(decision_at)、10/1が分割の効力発生日、の場合。
    8/15時点では「将来分割される」というEvent情報は利用できる(known_atを過ぎている)が、
    10/1の分割はまだ効力が発生していない(adjustable_atを過ぎていない)ため、
    8/15時点の過去Price Featureを10/1以降の基準へ補正してはならない
    (=このCorporate Actionはこの関数の返すAdjusted OHLCVには一切反映されない)。

    announced_atが不明(None)、またはas_ofより後にannounceされる(=まだ公知でない)
    Corporate Actionが混入している場合はLookAheadBiasErrorで拒否する
    (黙って除外せず、呼び出し側の入力に未来情報が混じっていることを明示する)。
    一方、known_atは過ぎているがadjustable_atをまだ過ぎていないCorporate Actionは、
    エラーにはせず単に調整対象から除外する(これは意図した挙動であり、データ不備ではない)。
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
    not_yet_known = [a for a in actions if not is_known_at(a, as_of)]
    if not_yet_known:
        raise LookAheadBiasError(
            f"as_of={as_of.isoformat()} 時点でまだ公表されていないCorporate Actionが"
            f"{len(not_yet_known)}件含まれています(未来情報の混入)。"
        )
    adjustable_actions = [a for a in actions if is_adjustable_at(a, as_of)]
    return apply_split_adjustments(raw_bars, adjustable_actions)
