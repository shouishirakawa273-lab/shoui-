"""Raw API Payload(J-Quants/fixture共通のフィールド形状)からschemaへの変換。

RawとAdjustedを混同しないため、この変換は`RawOHLCVBar`しか生成しない
(=未調整のOHLCVのみ)。株式分割等の調整は別途`lib/schemas/price_data.py`の
`apply_split_adjustments_as_of`を通す。

既知の制約: J-Quantsの`daily_quotes`は独自の`AdjustmentFactor`を返すが、
これは公表時刻(announced_at)を伴わないためPoint-in-Time安全性を検証できない。
本モジュールでは`AdjustmentFactor`は利用せず、常にRawOHLCVBarを未調整のまま返す
(corporate actionsを別途 announced_at 付きで取得できるまでの既知の制約。
DECISIONS.md 参照)。
"""

from __future__ import annotations

from datetime import date

from lib.market_calendar import TradingCalendar
from lib.schemas.price_data import RawOHLCVBar

# J-Quants trading_calendar の HolidayDivision: "1"が営業日、それ以外(0/2/3等)は非営業日、
# という理解に基づく(公式ドキュメントの想定。実レスポンスでの検証は未実施 - README参照)。
_TRADING_HOLIDAY_DIVISION = "1"


def daily_quotes_payload_to_raw_bars(payload: list[dict[str, object]]) -> list[RawOHLCVBar]:
    """J-Quants/fixtureの``daily_quotes``ペイロードを``RawOHLCVBar``へ変換する。

    AdjustmentFactor等の調整済みフィールドは使わず、Open/High/Low/Close/Volumeの
    未調整値のみをそのまま使う。
    """
    bars: list[RawOHLCVBar] = []
    for row in payload:
        code = str(row["Code"])
        session_date = date.fromisoformat(str(row["Date"]))
        bars.append(
            RawOHLCVBar(
                code=code,
                session_date=session_date,
                open=_to_float_or_none(row.get("Open")),
                high=_to_float_or_none(row.get("High")),
                low=_to_float_or_none(row.get("Low")),
                close=_to_float_or_none(row.get("Close")),
                volume=_to_float_or_none(row.get("Volume")),
                source="jquants",
            )
        )
    return bars


def trading_calendar_payload_to_calendar(
    payload: list[dict[str, object]],
    *,
    range_start: date,
    range_end: date,
) -> TradingCalendar:
    """J-Quants/fixtureの``trading_calendar``ペイロードから``TradingCalendar``を構築する。"""
    trading_dates = frozenset(
        date.fromisoformat(str(row["Date"])) for row in payload if str(row.get("HolidayDivision")) == _TRADING_HOLIDAY_DIVISION
    )
    return TradingCalendar(trading_dates=trading_dates, range_start=range_start, range_end=range_end)


def _to_float_or_none(value: object) -> float | None:
    """取得できない値(None/空文字/"-")は推測で埋めず None(取得不可)として扱う。"""
    if value is None or value == "" or value == "-":
        return None
    return float(value)  # type: ignore[arg-type]
