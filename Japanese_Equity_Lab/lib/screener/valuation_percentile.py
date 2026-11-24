"""バリュエーション指標の過去分位(Step 3 Stage 4b)。

方針書 Step 3 の出力「過去10年のPER・PBRの現在値と分位」。**方針は実データの分布を
見る前に `DECISIONS.md` 2026-11-24 (10) に記録済み**で、本モジュールはそれを実装
するだけである。分布を見てから閾値を動かさないために先に決めた。

## 算出済みの値を使い、自分で計算しない

`/equities/valuation` が `PER`/`FwdPER`/`PBR` を**日次系列**で返し、算出方法も公式に
文書化されている。したがって本Labは比率を定義せず、分位だけを取る
(ルート `CLAUDE.md`「取得できない項目を他の値から計算・推測して埋めることは禁止」)。

## 負の値は分布から外す

負のPERは「安い」ではなく「赤字」である。分布に残すと**下端が「最も安い」ではなく
「最も赤字」を意味してしまい、出力の読み方が反転する。** 負のPBRも同様に債務超過を
意味する。除外した件数は必ず報告し、分母を黙らせない。

**現在値そのものが非正のときは、その分位をUNKNOWNとする。** 0でも100でもない。
分布から除いた値を、その分布に位置づけることはできない。「負の利益は無限に割高」と
いう流儀もあるが、それは本Labが発明する変換なので採らない。

## 分割の処理を入れない理由は構造

PER・PBRは権利落ち日で株価と一株当たり価値が同時にずれて打ち消し合うため連続である
(7203の2021-09-29でPER 9.73→9.71、PBR 1.2→1.2を観測)。根拠は1件の観測ではなく
この構造。一株当たりの**水準**は段差が立つが、それは
`lib/screener/per_share.py` が独立に報告する。
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from lib.market_calendar import session_close_at
from lib.pretrade_risk.liquidity import DEFAULT_MAX_STALENESS_DAYS

logger = logging.getLogger(__name__)

PERCENTILE_INDICATORS: tuple[str, ...] = ("PER", "FwdPER", "PBR")
"""分位を取る指標。`FwdPER` は欠損が多い(7203で60/2440)が、判断で1つ除外するより
一律に扱って被覆率を正直に報告する方が読みやすい。"""

DEFAULT_WINDOW_YEARS = 10
DEFAULT_MIN_SESSIONS = 250
"""これ未満では「10年分位」という名前が積極的に誤解を招く。250は1営業年。"""

MAX_STALENESS_DAYS = DEFAULT_MAX_STALENESS_DAYS
"""`liquidity.py` が既に論証した閾値をそのまま使う(2つ目の数字を発明しない)。"""


@dataclass(frozen=True, kw_only=True)
class IndicatorPercentile:
    indicator: str
    current_value: Decimal | None
    percentile: Decimal | None
    """経験分布関数 `count(x <= 現在値) / n`。**小数**(0.23 = 下から23%)。"""
    sample_size: int
    excluded_non_positive: int
    """非正のため分布から外した件数。分母を黙らせないために必ず出す。"""
    excluded_missing: int
    first_session: date | None
    last_session: date | None
    unknown_reason: str | None


@dataclass(frozen=True, kw_only=True)
class ValuationPercentiles:
    code: str
    decision_at: datetime
    window_years: int
    window_start: date
    current_session: date | None
    staleness_days: int | None
    indicators: tuple[IndicatorPercentile, ...]
    unknown_reason: str | None

    def indicator(self, name: str) -> IndicatorPercentile | None:
        return next((i for i in self.indicators if i.indicator == name), None)


def _to_decimal(raw: object) -> Decimal | None:
    """`str()` を経由する。`Decimal(float)` は2進浮動小数の展開を持ち込む。"""
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, Decimal):
        return raw
    if isinstance(raw, int | float):
        return Decimal(str(raw))
    if isinstance(raw, str):
        text = raw.strip()
        if text == "":
            return None
        try:
            return Decimal(text)
        except ArithmeticError:
            return None
    return None


def _parse_session(raw: object) -> date | None:
    if not isinstance(raw, str) or raw.strip() == "":
        return None
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        return None


def assess_valuation_percentiles(
    *,
    code: str,
    rows: Sequence[Mapping[str, object]],
    decision_at: datetime,
    window_years: int = DEFAULT_WINDOW_YEARS,
    indicators: Sequence[str] = PERCENTILE_INDICATORS,
    min_sessions: int = DEFAULT_MIN_SESSIONS,
    max_staleness_days: int = MAX_STALENESS_DAYS,
) -> ValuationPercentiles:
    """`/equities/valuation` のRawから各指標の現在値と分位を出す。

    `rows` は銘柄混在でもよい(`Code` で絞る)。可視性は
    `session_close_at(Date) <= decision_at` で判定する——値はその場の終値から
    算出されるので、引けるまで知り得ない。
    """
    if decision_at.tzinfo is None:
        raise ValueError("decision_at must be timezone-aware")
    if window_years <= 0:
        raise ValueError(f"window_years must be positive: {window_years!r}")
    if min_sessions <= 0:
        raise ValueError(f"min_sessions must be positive: {min_sessions!r}")

    as_of = decision_at.date()
    try:
        window_start = as_of.replace(year=as_of.year - window_years)
    except ValueError:  # 2月29日
        window_start = as_of.replace(year=as_of.year - window_years, day=28)

    prefix = code[:4]
    visible: list[tuple[date, Mapping[str, object]]] = []
    for row in rows:
        raw_code = row.get("Code")
        if isinstance(raw_code, str) and raw_code[:4] != prefix:
            continue
        session = _parse_session(row.get("Date"))
        if session is None or session < window_start:
            continue
        if session_close_at(session) > decision_at:
            continue
        visible.append((session, row))

    def _empty(reason: str) -> ValuationPercentiles:
        return ValuationPercentiles(
            code=code,
            decision_at=decision_at,
            window_years=window_years,
            window_start=window_start,
            current_session=None,
            staleness_days=None,
            indicators=(),
            unknown_reason=reason,
        )

    if not visible:
        return _empty(f"{window_start.isoformat()}以降の可視な行が無い")

    visible.sort(key=lambda pair: pair[0])
    current_session, current_row = visible[-1]
    staleness_days = (as_of - current_session).days

    if staleness_days > max_staleness_days:
        return ValuationPercentiles(
            code=code,
            decision_at=decision_at,
            window_years=window_years,
            window_start=window_start,
            current_session=current_session,
            staleness_days=staleness_days,
            indicators=(),
            unknown_reason=(
                f"最新行が{staleness_days}日前で、{max_staleness_days}日の許容を超える"
                "(上場廃止・売買停止の可能性)。現在値を現在として扱わない"
            ),
        )

    results: list[IndicatorPercentile] = []
    for name in indicators:
        sample: list[Decimal] = []
        excluded_non_positive = 0
        excluded_missing = 0
        for _, row in visible:
            value = _to_decimal(row.get(name))
            if value is None:
                excluded_missing += 1
                continue
            if value <= 0:
                excluded_non_positive += 1
                continue
            sample.append(value)

        first = visible[0][0]
        last = visible[-1][0]
        current = _to_decimal(current_row.get(name))

        reason: str | None = None
        percentile: Decimal | None = None
        if current is None:
            reason = f"{name} の現在値が{current_session.isoformat()}の行に無い"
        elif current <= 0:
            # 分布から除いた値を、その分布に位置づけることはできない。
            reason = f"{name} の現在値が非正({current})のため分位は定義できない"
        elif len(sample) < min_sessions:
            reason = f"標本が{len(sample)}件で、{min_sessions}件(1営業年)に満たない"
        else:
            at_or_below = sum(1 for x in sample if x <= current)
            percentile = Decimal(at_or_below) / Decimal(len(sample))

        results.append(
            IndicatorPercentile(
                indicator=name,
                current_value=current,
                percentile=percentile,
                sample_size=len(sample),
                excluded_non_positive=excluded_non_positive,
                excluded_missing=excluded_missing,
                first_session=first,
                last_session=last,
                unknown_reason=reason,
            )
        )

    unresolved = [r.indicator for r in results if r.percentile is None]
    if unresolved:
        logger.info("screener: %s valuation percentile unresolved for %s", code, ", ".join(unresolved))

    return ValuationPercentiles(
        code=code,
        decision_at=decision_at,
        window_years=window_years,
        window_start=window_start,
        current_session=current_session,
        staleness_days=staleness_days,
        indicators=tuple(results),
        unknown_reason=None,
    )
