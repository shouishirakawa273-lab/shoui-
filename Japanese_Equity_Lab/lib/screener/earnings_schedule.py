"""決算発表予定日(Step 3 Stage 4b)。

方針書 Step 3 の出力「直近の決算発表予定日」。`/v2/fins/earnings-date` の
Raw(`PubDate`/`SchDate`/`FQName`/`FYE`)を読む。

## 予定日は改定される。(公表日, 予定日) の対で持つ

公式リリースノートは、**予定日で検索すると訂正された予定日は現在有効なものだけが
取得できる**と明記している。だから `lib/data_sources/jquants.py` の
`fetch_earnings_dates` は予定日検索を提供せず、銘柄コードで引く。

本モジュールはその前提を引き継ぎ、**同じ決算期について複数の (公表日, 予定日) が
あればすべて保持する。** 最後の1件に畳むと改定の履歴が消える。

## PIT

`PubDate` 以降でなければその予定日は知り得ない。`decision_at` の日付より後に公表
された行は見せない。日付粒度しか無いので、**同日公表のものは可視とみなす**
——公表時刻が提供されないため、`session_close_at` のような時刻での切り分けが
できない。これは楽観側に倒す選択なので明記する(保守的にするなら前日までに限る
べきだが、1日のずれで予定日を知っていたことにするのは、予定日という性質上
実害が小さいと判断した)。

## 「直近」の意味

判定時点以降で最も近い予定日を「次回」とする。過去の予定日は、改定履歴を読む
ためにそのまま残す。

**次回が `None` になるのは正常な状態でもある。** 7203の実観測では3Q予定日は毎年
1月上旬に公表される(2017-01-04公表→2017-02-06予定)。したがって11月下旬の時点で
3Qの予定日はまだ公表されていない。**過去の予定日を代わりに見せない**——それは
「直近の決算発表予定日」ではない。理由を述べて `None` を返す。

## 決算期を識別するFieldが無い

`FYE` はMMDDで年を含まず、`FQName` は四半期だけを表す。したがって
「どの決算年度の3Qか」はこのEndpointのFieldからは決まらない。
`restatements_of_the_same_date` の節を参照。
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime

logger = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class ScheduledEarnings:
    """1件の (公表日, 予定日) 。"""

    published_on: date
    scheduled_on: date | None
    """予定日。未定のとき `SchDate` が空文字になるため `None` を取り得る。"""
    fiscal_quarter: str | None
    """`FQName`(FY/1Q/2Q/3Q)。"""
    fiscal_year_end: str | None
    """`FYE`(MMDD形式、例 "0331")。日付に変換しない——年が入っていない。"""


@dataclass(frozen=True, kw_only=True)
class EarningsSchedule:
    code: str
    decision_at: datetime
    entries: tuple[ScheduledEarnings, ...]
    """可視な全件。公表日の昇順。改定履歴を読めるよう畳まない。"""
    next_scheduled: ScheduledEarnings | None
    """判定時点以降で最も近い予定日。無ければ `None`。"""
    unknown_reason: str | None

    @property
    def restatements_of_the_same_date(self) -> int:
        """**同じ予定日**が、異なる公表日で複数回報告された回数。

        これは「決算期ごとの改定回数」**ではない**。決算期を識別するFieldが無い
        ためである: `FYE` は `"0331"` のようなMMDDで**年を含まない**。

        2026-11-24、最初の実行で `(FYE, FQName)` をキーに「改定回数」を数えたら、
        7203で40件中36回になった。`(0331, 3Q)` が10年ぶん衝突し、4キーに対して
        36件が「2件目以降」と判定されていた。docstringに「年が入っていない」と
        書いた2つ下で、それを決算期の識別子として使っていた。

        予定日から決算年度を逆算すれば「決算期ごとの改定」は数えられるが、それは
        「開示は期末から数ヶ月以内に行われる」という推測を要する。Sourceが持って
        いない区分を発明しないため、**数えられるものだけを数える**: 同一の
        `SchDate` が複数の `PubDate` で報告された件数。予定日が変わった改定は
        ここには出ないので、`entries` を人が読む。
        """
        seen: set[date] = set()
        restatements = 0
        for entry in self.entries:
            if entry.scheduled_on is None:
                continue
            if entry.scheduled_on in seen:
                restatements += 1
            else:
                seen.add(entry.scheduled_on)
        return restatements


def _parse_date(raw: object) -> date | None:
    if not isinstance(raw, str) or raw.strip() == "":
        return None
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        return None


def _text(raw: object) -> str | None:
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    return text or None


def build_earnings_schedule(
    *,
    code: str,
    rows: Sequence[Mapping[str, object]],
    decision_at: datetime,
) -> EarningsSchedule:
    """`/fins/earnings-date` のRawから、可視な予定日と次回を組み立てる。

    `rows` は銘柄混在でもよい(`Code` で絞る)。`PubDate` が無い行は、可視性を
    判定できないので落とす(推測で通さない)。
    """
    if decision_at.tzinfo is None:
        raise ValueError("decision_at must be timezone-aware")

    as_of = decision_at.date()
    prefix = code[:4]
    entries: list[ScheduledEarnings] = []
    dropped_without_pubdate = 0

    for row in rows:
        raw_code = row.get("Code")
        if isinstance(raw_code, str) and raw_code[:4] != prefix:
            continue
        published_on = _parse_date(row.get("PubDate"))
        if published_on is None:
            dropped_without_pubdate += 1
            continue
        if published_on > as_of:
            continue
        entries.append(
            ScheduledEarnings(
                published_on=published_on,
                scheduled_on=_parse_date(row.get("SchDate")),
                fiscal_quarter=_text(row.get("FQName")),
                fiscal_year_end=_text(row.get("FYE")),
            )
        )

    if dropped_without_pubdate:
        logger.warning(
            "screener: %s の決算発表予定日 %d 件はPubDateが無く可視性を判定できないため除外しました",
            code,
            dropped_without_pubdate,
        )

    if not entries:
        return EarningsSchedule(
            code=code,
            decision_at=decision_at,
            entries=(),
            next_scheduled=None,
            unknown_reason="判定時点までに公表された決算発表予定日が無い",
        )

    entries.sort(key=lambda e: (e.published_on, e.scheduled_on or date.max))

    # 判定時点以降で最も近い予定日。同じ予定日が複数回公表されていれば、
    # **最後に公表されたもの**を採る(それが現在有効な報告)。
    upcoming = [e for e in entries if e.scheduled_on is not None and e.scheduled_on >= as_of]
    next_scheduled = min(upcoming, key=lambda e: (e.scheduled_on or date.max, -e.published_on.toordinal())) if upcoming else None

    return EarningsSchedule(
        code=code,
        decision_at=decision_at,
        entries=tuple(entries),
        next_scheduled=next_scheduled,
        unknown_reason=None if next_scheduled is not None else "判定時点以降の予定日が公表されていない",
    )
