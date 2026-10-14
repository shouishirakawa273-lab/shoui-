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
from lib.market_calendar import session_close_at, session_open_at
from lib.schemas.base import RecordMeta


class CorporateActionType(StrEnum):
    SPLIT = "SPLIT"
    REVERSE_SPLIT = "REVERSE_SPLIT"
    DIVIDEND = "DIVIDEND"
    MERGER = "MERGER"
    DELISTING = "DELISTING"
    TICKER_CHANGE = "TICKER_CHANGE"
    ADJUSTMENT_EVENT = "ADJUSTMENT_EVENT"
    """J-Quants V2の``AdjFactor``/``ExRT``から機械的に検出したイベントで、SPLIT/
    REVERSE_SPLITのどちらかを断定する根拠(値の方向の公式仕様)が未検証のもの。
    分割か併合かを決め打ちせず、この汎用型で表す(DECISIONS.md D0032参照)。"""


@dataclass(kw_only=True, frozen=True)
class RawOHLCVBar(RecordMeta):
    """調整前の生の日次OHLCV。取得元の値をそのまま保持し、後から書き換えない。

    `code`はResearch Lab内部Code(普通株4桁、例: "7203")。J-Quants API V2は
    Provider Code(5桁、例: "72030")を返すため、`convert.py`が変換時に正規化する
    (`lib.data_sources.ticker_codes`、DECISIONS.md D0036)。正規化前のProvider側の
    生の値は`provider_code`に別途保持し、両者を混同しない。
    """

    code: str
    session_date: date
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: float | None
    provider_code: str | None = None


@dataclass(kw_only=True, frozen=True)
class CorporateAction(RecordMeta):
    """株式分割・併合・配当・合併・上場廃止等の企業イベント。

    `code`はResearch Lab内部Code。`provider_code`はProvider側の生の値
    (DECISIONS.md D0036、RawOHLCVBar参照)。
    """

    code: str
    action_type: CorporateActionType
    effective_date: date
    announced_at: datetime | None = None
    split_ratio: float | None = None  # 分割後株数 / 分割前株数 (SPLIT/REVERSE_SPLITのみ)
    dividend_per_share: float | None = None  # DIVIDENDのみ。Ver.1では価格調整に反映しない。
    raw_adj_factor: float | None = None
    """J-Quants V2 ``AdjFactor``の値をそのまま保持する(ADJUSTMENT_EVENTのみ)。
    ``split_ratio``(「新株数/旧株数」という本スキーマ独自の向きの定義)とは
    別に、Provider側の生の値を検証可能な形で残す。この値をPrice調整へ適用する
    公式の計算方法(ex-dateより前の価格へ乗算)は確定している
    (``build_provider_derived_adjusted_bars``、DECISIONS.md D0034参照)。"""
    provider_code: str | None = None
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


# --- Phase3A.1: Case A (Announcementを Signalとして使う) と Case B (Price Seriesの
# 連続化) を分離する(DECISIONS.md D0032参照)。上のapply_split_adjustments_as_ofは
# Case A向け(``announced_at``必須、事前に「いつ発表されたか」を知る必要がある用途)。
# 以下はCase B向け(J-Quants V2の``AdjFactor``/``ExRT``のように、Provider自身が
# 効力発生日のBar行に付与するmechanicalなイベントを扱う)。


def provider_event_available_at(effective_date: date) -> datetime:
    """Provider由来(V2 AdjFactor/ExRT等)のCorporate Actionが「知り得た」時刻。

    このイベントは事前の公表(announced_at)を経由せず、効力発生日(effective_date、
    ex-date)のBar行そのものにmechanicalに付与される。したがって、このEventの存在が
    Research Labにとって知り得るのは、その日のBarデータ自体が取得可能になる時刻
    (=市場のその日の大引け、``session_close_at(effective_date)``)と同じである。
    RawOHLCVBarのavailable_atと同じ導出元を使うことで、個別に未来情報を混入させる
    余地を無くす(RawOHLCVBar自体のPIT gateと同じ基準に揃える)。
    """
    return session_close_at(effective_date)


def build_provider_derived_adjusted_bars(
    raw_bars: list[RawOHLCVBar],
    events: list[CorporateAction],
    *,
    as_of: datetime,
) -> list[AdjustedOHLCVBar]:
    """Provider由来のAdjFactorイベントからAs-of Adjusted Seriesを構築する
    (Case B: Price Seriesの連続化。announced_atは不要)。

    **公式仕様(確定、DECISIONS.md D0034)**: J-Quants V2のAdjFactorはCorporate Action
    のex-dateのrecordに記録される。ex-date **より前** の日の価格・出来高にのみ、
    そのex-dateのAdjFactorを累積して適用する(ex-date当日・以降の価格は無調整のまま)。

    ```
    Adjusted Price  = Raw Price  × Π(dより後でas_of以前にeffectiveなAdjFactor)
    Adjusted Volume = Raw Volume ÷ Π(dより後でas_of以前にeffectiveなAdjFactor)
    ```

    例(公式仕様の例そのもの): 2024-01-11がAdjFactor=0.5のex-date、2024-01-10 C=980、
    2024-01-11 C=480、2024-01-12 C=500の場合 -> Adjusted Close は 2024-01-10=490
    (=980×0.5)、2024-01-11=480(無調整、ex-date当日は対象外)、2024-01-12=500
    (無調整、ex-dateより後)。

    ``announced_at``が無いことを理由にPrice Adjustment全体をBLOCKする必要はないと
    判断した(DECISIONS.md D0032)。このEventは「将来起きることを事前に知る」Case A
    (Corporate Action Announcementを取引Signalとして使う用途)とは異なり、効力発生日
    当日のBarデータそのものから機械的に導出される。その日のBarを使ってよいなら
    (=available_atのPIT gateを通過しているなら)、同じ日に付随するこのEventも同時に
    「知り得る」情報であり、別途announced_atを要求する意味が無い。

    **PIT gate(Look-ahead防止)**: as_of時点でまだ効力発生日のBarデータ自体が
    取得可能でないはずのEvent(``provider_event_available_at(effective_date) > as_of``)
    は、Case Aの「未公表」ケースとは異なりエラーにはせず、**黙って調整対象から除外する**
    (=Backtest Pipelineは通常、ある時点までの全Raw/Event Dataを保持したまま複数の
    decision_atで繰り返しこの関数を呼ぶため、「まだ知り得ない」Eventが渡された集合に
    混ざっていること自体は異常ではない。異常なのはそれを「適用してしまう」ことであり、
    本関数はそれを構造的に防ぐ)。

    **ExRTとの役割分離**: AdjFactorが1.0のEvent(ExRTのみが設定されている行)は
    Price Adjustmentの計算に一切寄与しない(1.0を掛けても無変化なので数学的には無害だが、
    「ExRTが存在するという理由だけで独自の補正係数を推測して適用する」ことをしない
    という設計意図を明示するため、明示的にスキップする)。
    """
    if as_of.tzinfo is None:
        raise ValueError("as_of はtz-awareである必要があります")

    applicable_events: list[tuple[date, float]] = [
        (e.effective_date, e.raw_adj_factor)
        for e in events
        if e.raw_adj_factor is not None and e.raw_adj_factor != 1.0 and provider_event_available_at(e.effective_date) <= as_of
    ]

    adjusted: list[AdjustedOHLCVBar] = []
    for bar in sorted(raw_bars, key=lambda b: b.session_date):
        cumulative_factor = 1.0
        for effective_date, factor in applicable_events:
            if effective_date > bar.session_date:
                cumulative_factor *= factor
        adjusted.append(
            AdjustedOHLCVBar(
                code=bar.code,
                session_date=bar.session_date,
                open=None if bar.open is None else bar.open * cumulative_factor,
                high=None if bar.high is None else bar.high * cumulative_factor,
                low=None if bar.low is None else bar.low * cumulative_factor,
                close=None if bar.close is None else bar.close * cumulative_factor,
                volume=None if bar.volume is None else bar.volume / cumulative_factor,
                split_adjustment_factor=cumulative_factor,
                derived_from="raw+jquants_v2_adjfactor_events(as_of_pit_safe)",
                source=bar.source,
            )
        )
    return adjusted
