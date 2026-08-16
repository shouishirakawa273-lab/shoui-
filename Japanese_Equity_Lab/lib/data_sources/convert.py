"""Raw API Payload(J-Quants API V2)からschemaへの変換。

RawとAdjustedを混同しないため、この変換は`RawOHLCVBar`しか生成しない
(=未調整のOHLCVのみ)。株式分割等の調整は別途`lib/schemas/price_data.py`の
`apply_split_adjustments_as_of`(Case A: announced_at必須)または
`build_provider_derived_adjusted_bars`(Case B: V2のAdjFactor/ExRTイベント、
announced_at不要)を通す。

**Phase3A.1でJ-Quants API V2へ全面移行した**(DECISIONS.md D0031)。V1の
``/prices/daily_quotes``等のField名を前提としたコードは削除済み。以下のField名は
ユーザーがセッション内で明示したV2仕様をCanonical Specificationとして採用したもので、
このセッション自身は公式ドキュメントへ疎通できず独自検証はできていない
(README.md、DECISIONS.md D0031参照)。
"""

from __future__ import annotations

from datetime import date

from lib.market_calendar import TradingCalendar
from lib.schemas.price_data import CorporateAction, CorporateActionType, RawOHLCVBar
from lib.universe import ListingRecord

TOPIX_CODE = "TOPIX"

# V2 ``/v2/markets/calendar`` の ``HolDiv``(公式仕様、ユーザー確定情報、DECISIONS.md
# D0034参照)。
#   0 = Non-business day
#   1 = Business day
#   2 = Day of TSE Half-Day Trading Sessions
#   3 = Non-business day (with holiday trading)
HOL_DIV_NON_BUSINESS_DAY = "0"
HOL_DIV_BUSINESS_DAY = "1"
HOL_DIV_HALF_DAY_TRADING = "2"
HOL_DIV_NON_BUSINESS_WITH_HOLIDAY_TRADING = "3"

# 日本株現物Backtestのデフォルト: 半休場日(2)も取引日として扱い、holiday tradingのみの
# 非営業日(3)は現物Cash Equity Pipelineでは非取引日として扱う(ユーザー確定仕様)。
_TRADING_HOL_DIV_DEFAULT: frozenset[str] = frozenset({HOL_DIV_BUSINESS_DAY, HOL_DIV_HALF_DAY_TRADING})

_ADJUSTMENT_EVENT_NOTE = (
    "J-QuantsV2のAdjFactor/ExRTから検出したCorporate Action候補。AdjFactorはEx-date"
    "recordに記録され、Price Adjustment(Case B: Price Series連続化)には"
    "`build_provider_derived_adjusted_bars`を使う(公式仕様確定、DECISIONS.md D0034参照)。"
    "ExRTはCorporate Action / ex-right eventのmetadataとして保持するのみで、"
    "AdjFactor=1の日にExRTだけが存在してもPrice Adjustmentは行わない。"
    "Case A(Announcementを取引Signalとして使う用途)には使えない(announced_atを持たない)。"
)


def equity_bars_payload_to_raw_bars(payload: list[dict[str, object]], *, source: str = "jquants") -> list[RawOHLCVBar]:
    """``/v2/equities/bars/daily``ペイロードを``RawOHLCVBar``へ変換する。

    Adjusted系フィールド(AdjO/AdjH/AdjL/AdjC/AdjVo)・AdjFactor・ExRT等の調整済み/
    イベント情報は使わず、O/H/L/C/Vo(未調整値)のみをそのまま使う。
    """
    bars: list[RawOHLCVBar] = []
    for row in payload:
        code = str(row["Code"])
        session_date = date.fromisoformat(str(row["Date"]))
        bars.append(
            RawOHLCVBar(
                code=code,
                session_date=session_date,
                open=_to_float_or_none(row.get("O")),
                high=_to_float_or_none(row.get("H")),
                low=_to_float_or_none(row.get("L")),
                close=_to_float_or_none(row.get("C")),
                volume=_to_float_or_none(row.get("Vo")),
                source=source,
            )
        )
    return bars


def topix_bars_payload_to_raw_bars(payload: list[dict[str, object]], *, source: str = "jquants") -> list[RawOHLCVBar]:
    """``/v2/indices/bars/daily/topix``ペイロードを``RawOHLCVBar``へ変換する(Benchmark用)。

    TOPIX専用Endpointのため銘柄コードは含まれない想定で、内部的に固定コード
    ``TOPIX_CODE``を割り当てる。個別銘柄Barと同じO/H/L/Cフィールド形状という
    前提に立つ(未検証)。出来高(Vo)が含まれない場合はNone(取得不可)のまま扱う。
    """
    bars: list[RawOHLCVBar] = []
    for row in payload:
        session_date = date.fromisoformat(str(row["Date"]))
        bars.append(
            RawOHLCVBar(
                code=TOPIX_CODE,
                session_date=session_date,
                open=_to_float_or_none(row.get("O")),
                high=_to_float_or_none(row.get("H")),
                low=_to_float_or_none(row.get("L")),
                close=_to_float_or_none(row.get("C")),
                volume=_to_float_or_none(row.get("Vo")),
                source=source,
            )
        )
    return bars


def trading_calendar_payload_to_calendar(
    payload: list[dict[str, object]],
    *,
    range_start: date,
    range_end: date,
    trading_hol_div_values: frozenset[str] | None = None,
) -> TradingCalendar:
    """``/v2/markets/calendar``ペイロードから``TradingCalendar``を構築する。

    `trading_hol_div_values`省略時は`_TRADING_HOL_DIV_DEFAULT`(公式仕様に基づく既定値:
    Business day(1) / Half-Day Trading(2)を取引日とする)を使う。半休場日を取引日として
    扱わない、あるいはholiday trading日(3)も取引日として扱うなど、既定と異なる運用を
    したい場合はこの引数で明示的に上書きできる。
    """
    hol_div_values = trading_hol_div_values if trading_hol_div_values is not None else _TRADING_HOL_DIV_DEFAULT
    trading_dates = frozenset(date.fromisoformat(str(row["Date"])) for row in payload if str(row.get("HolDiv")) in hol_div_values)
    return TradingCalendar(trading_dates=trading_dates, range_start=range_start, range_end=range_end)


def detect_corporate_action_events_from_equity_bars(payload: list[dict[str, object]]) -> list[CorporateAction]:
    """``equity_bars``の``AdjFactor``/``ExRT``からCorporate Action候補を抽出する。

    J-Quants V2ではAdjFactorはCorporate Actionの権利落ち日(ex-date)のrecordそのものに
    記録される(公式仕様確定、DECISIONS.md D0034)。したがって``AdjFactor != 1``または
    ``ExRT``が設定されている行を、そのままEvent当日として認識する(前日比較による
    ヒューリスティックは使わない)。

    抽出したEventは`CorporateActionType.ADJUSTMENT_EVENT`(種別未断定)、
    `announced_at=None`(Case Aには使えない)、`raw_adj_factor`にAdjFactorの生値を保持する。
    Price Series連続化(Case B)には`build_provider_derived_adjusted_bars`を使う。
    **ExRTのみが設定されAdjFactor==1の行も検出はするが**(Corporate Actionの
    metadataとして記録する)、`build_provider_derived_adjusted_bars`はAdjFactor!=1の
    ものだけを実際のPrice Adjustmentに使い、ExRTの存在だけを理由に独自の補正係数を
    推測・適用することはない。
    """
    events: list[CorporateAction] = []
    for row in payload:
        factor = _to_float_or_none(row.get("AdjFactor"))
        ex_rights = row.get("ExRT")
        is_event_day = (factor is not None and factor != 1.0) or (ex_rights is not None and ex_rights != "")
        if not is_event_day:
            continue
        events.append(
            CorporateAction(
                code=str(row["Code"]),
                action_type=CorporateActionType.ADJUSTMENT_EVENT,
                effective_date=date.fromisoformat(str(row["Date"])),
                announced_at=None,
                raw_adj_factor=factor,
                note=_ADJUSTMENT_EVENT_NOTE,
                source="jquants_v2_adjfactor_exrt",
            )
        )
    return events


def equities_master_payload_to_listing_records(payload: list[dict[str, object]]) -> list[ListingRecord]:
    """``/v2/equities/master``ペイロードを``ListingRecord``へ変換する。

    既知の制約: ``/v2/equities/master``のレスポンスに``listing_date`` /
    ``delisting_date``に相当するフィールドが含まれるかは未検証。含まれない場合、
    生成される``ListingRecord``は``listing_date=None`` / ``delisting_date=None``の
    ままになり、Survivorship biasを解消できない(`lib/universe.py`の
    `UniverseSnapshot.survivorship_bias_unresolved`参照)。会社名(`company_name`)は
    Ticker/Company Name整合性チェック(`lib/universe.check_company_name_consistency`)
    に使うため、フィールド名は暫定的に"CompanyName"を想定している(未検証)。
    """
    records: list[ListingRecord] = []
    for row in payload:
        records.append(
            ListingRecord(
                code=str(row["Code"]),
                market=str(row.get("MarketCode") or row.get("MarketCodeName") or "取得不可"),
                sector=_optional_str(row.get("Sector33Code") or row.get("Sector33CodeName")),
                company_name=_optional_str(row.get("CompanyName")),
                listing_date=_optional_date(row.get("ListingDate")),
                delisting_date=_optional_date(row.get("DelistingDate")),
                source="jquants",
            )
        )
    return records


def _optional_str(value: object) -> str | None:
    if value is None or value == "":
        return None
    return str(value)


def _optional_date(value: object) -> date | None:
    if value is None or value == "":
        return None
    return date.fromisoformat(str(value))


def _to_float_or_none(value: object) -> float | None:
    """取得できない値(None/空文字/"-")は推測で埋めず None(取得不可)として扱う。"""
    if value is None or value == "" or value == "-":
        return None
    return float(value)  # type: ignore[arg-type]
