"""Raw API Payload(J-Quants/fixture共通のフィールド形状)からschemaへの変換。

RawとAdjustedを混同しないため、この変換は`RawOHLCVBar`しか生成しない
(=未調整のOHLCVのみ)。株式分割等の調整は別途`lib/schemas/price_data.py`の
`apply_split_adjustments_as_of`を通す。

既知の制約: J-Quantsの`daily_quotes`は独自の`AdjustmentFactor`を返すが、
これは公表時刻(announced_at)を伴わないためPoint-in-Time安全性を検証できない。
`detect_split_hints_from_daily_quotes()`はこれを`announced_at=None`の
`CorporateAction`として抽出するが、`apply_split_adjustments_as_of()`は
`announced_at`が無いActionを`LookAheadBiasError`で拒否する設計のため、
このhintはPIT-safeなBacktestには使えない(DECISIONS.md D0014/D0025参照)。
"""

from __future__ import annotations

from datetime import date

from lib.market_calendar import TradingCalendar
from lib.schemas.price_data import CorporateAction, CorporateActionType, RawOHLCVBar
from lib.universe import ListingRecord

# J-Quants trading_calendar の HolidayDivision: "1"が営業日、それ以外(0/2/3等)は非営業日、
# という理解に基づく(公式ドキュメントの想定。実レスポンスでの検証は未実施 - README参照)。
_TRADING_HOLIDAY_DIVISION = "1"

_SPLIT_HINT_NOTE = (
    "J-QuantsのAdjustmentFactorから検出した株式分割・併合の候補。"
    "announced_at(公表時刻)を伴わないためPoint-in-Time安全性を検証できない。"
    "apply_split_adjustments_as_of()に渡すとLookAheadBiasErrorで拒否される"
    "(意図した挙動)。実際に使えるのは、PIT保証を必要としない用途(例: 最新の"
    "調整済み系列を事後的に表示するためだけの参考情報)に限られる。"
    "split_ratioの向き・符号は実レスポンスで未検証。"
)


def daily_quotes_payload_to_raw_bars(payload: list[dict[str, object]], *, source: str = "jquants") -> list[RawOHLCVBar]:
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
                source=source,
            )
        )
    return bars


def index_prices_payload_to_raw_bars(
    payload: list[dict[str, object]], *, code: str, source: str = "jquants"
) -> list[RawOHLCVBar]:
    """J-Quants ``/indices`` ペイロードを``RawOHLCVBar``へ変換する(TOPIX等のBenchmark用)。

    ``/indices``が``/prices/daily_quotes``と同じOpen/High/Low/Close/Volumeの形状で
    値を返すという未検証の前提に立つ(ローカル環境での疎通確認が必要)。ペイロード側に
    ``Code``フィールドが無い場合に備え、呼び出し側が明示的に``code``を指定する。
    """
    bars = []
    for row in payload:
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
                source=source,
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


def detect_split_hints_from_daily_quotes(payload: list[dict[str, object]]) -> list[CorporateAction]:
    """``daily_quotes``の``AdjustmentFactor``が前日から変化した日を株式分割・併合の
    候補として抽出する(`announced_at=None`、PIT-safeなBacktestには使用不可)。

    「1.0以外の日を全て抽出する」のではなく「前日との変化」を見るのは、
    AdjustmentFactorが変化後も同じ値を保持し続ける実装(1回の分割に対して複数日
    ヒットしうる)・変化した日だけ1.0以外になる実装のどちらであっても、
    「効力発生日候補」を重複なく抽出できるようにするため
    (J-Quantsの実際の付与方式はこのセッションでは未検証)。

    どの用途で安全に使えるか・使えないかは`_SPLIT_HINT_NOTE`とRESEARCH_RULES.mdの
    「Corporate Action」節を参照。
    """
    by_code: dict[str, list[dict[str, object]]] = {}
    for row in payload:
        by_code.setdefault(str(row["Code"]), []).append(row)

    hints: list[CorporateAction] = []
    for code, rows in by_code.items():
        ordered = sorted(rows, key=lambda r: str(r["Date"]))
        previous_factor = 1.0
        for row in ordered:
            factor = _to_float_or_none(row.get("AdjustmentFactor"))
            if factor is None:
                continue
            if factor != previous_factor and factor != 1.0:
                effective_date = date.fromisoformat(str(row["Date"]))
                action_type = CorporateActionType.SPLIT if factor > 1.0 else CorporateActionType.REVERSE_SPLIT
                hints.append(
                    CorporateAction(
                        code=code,
                        action_type=action_type,
                        effective_date=effective_date,
                        announced_at=None,
                        split_ratio=factor,
                        note=_SPLIT_HINT_NOTE,
                        source="jquants_adjustment_factor_hint",
                    )
                )
            previous_factor = factor
    return hints


def listed_info_payload_to_listing_records(payload: list[dict[str, object]]) -> list[ListingRecord]:
    """J-Quants ``/listed/info`` ペイロードを``ListingRecord``へ変換する。

    既知の制約: ``/listed/info``は(未検証の限りでは)ある時点での上場状況の
    スナップショットであり、``listing_date`` / ``delisting_date``に相当する
    フィールドを含むかは未検証。含まれない場合、生成される``ListingRecord``は
    ``listing_date=None`` / ``delisting_date=None``のままになり、
    Survivorship biasを解消できない(`lib/universe.py`のUniverseSnapshot、
    `survivorship_bias_unresolved`参照)。
    """
    records: list[ListingRecord] = []
    for row in payload:
        records.append(
            ListingRecord(
                code=str(row["Code"]),
                market=str(row.get("MarketCode") or row.get("MarketCodeName") or "取得不可"),
                sector=_optional_str(row.get("Sector33Code") or row.get("Sector33CodeName")),
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
