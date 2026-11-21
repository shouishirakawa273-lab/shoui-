"""`as_of` 時点で実際に利用可能だった日次Barの窓を切り出す(Step 1共通)。

`PriceHistorySource.bars_up_to` は `session_date <= as_of.date()` という**日付粒度**の
フィルタしか行わない(`lib/backtest/price_history.py`)。そのため寄り前の `as_of`
(例: 09:00 JST)を渡すと、まだ終わっていない当日セッションのBarが返る。日次Barが
利用可能になるのはそのセッションの大引け以降なので、ここで `session_close_at` による
時刻粒度のゲートを追加する。

併せて本モジュールが担保すること:

- `as_of` はtz-awareでなければならない(naiveは曖昧なので拒否する)。
- 同一 `session_date` の重複行を取り除く。重複はカバレッジ判定の分母を水増しし、
  リターン側では `(D, D)` という長さ0の区間を作ってしまう。
- Barは `session_date` 昇順に整列する(Protocolの昇順は仕様上の約束にすぎず、
  実装が守る保証はない)。
- 最新セッションが `as_of` からどれだけ古いかを返し、呼び出し側が「履歴は長いが
  内容が古い」銘柄を検出できるようにする。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

from lib.backtest.price_history import PriceHistorySource
from lib.market_calendar import session_close_at
from lib.schemas.price_data import AdjustedOHLCVBar


@dataclass(frozen=True, kw_only=True)
class BarWindow:
    """`as_of` 時点で利用可能だったBarの窓と、その素性。"""

    bars: tuple[AdjustedOHLCVBar, ...]
    duplicate_sessions_dropped: int
    first_session: date | None
    last_session: date | None
    staleness_days: int | None
    """`as_of.date()` と最新セッションの暦日差。Barが無ければNone。

    営業日数ではなく暦日である。本モジュールは `TradingCalendar` を持たないため
    営業日単位の経過は表現できない。データの存在から営業日構造を推定することは
    `lib/market_calendar.py` が明示的に禁じているので、推定もしない。
    """


def require_aware(as_of: datetime, *, label: str = "as_of") -> None:
    """tz-naiveな `as_of` を拒否する。

    naiveのまま `session_close_at`(JST)と比較すると例外になるか、黙って誤った
    境界で比較される。Lab全体の慣例に合わせ、入口で明示的に弾く。
    """
    if as_of.tzinfo is None or as_of.tzinfo.utcoffset(as_of) is None:
        raise ValueError(f"{label} must be timezone-aware: {as_of!r}")


def available_bars(
    *,
    source: PriceHistorySource,
    code: str,
    as_of: datetime,
    window_sessions: int,
) -> BarWindow:
    """`as_of` 時点で利用可能だった直近 `window_sessions` 本のBarを返す。

    大引けを過ぎていないセッションのBarは除外する。重複 `session_date` は後勝ちで
    1本に畳み、畳んだ本数を返す。

    Raises:
        ValueError: `as_of` がtz-naive、または `window_sessions` が非正の場合。
    """
    require_aware(as_of)
    if window_sessions <= 0:
        raise ValueError(f"window_sessions must be positive: {window_sessions}")

    raw: Sequence[AdjustedOHLCVBar] = source.bars_up_to(code, as_of)

    # 大引けを過ぎたセッションのみ。これが日付粒度ではない本来のPIT境界。
    settled = [bar for bar in raw if session_close_at(bar.session_date) <= as_of]

    by_session: dict[date, AdjustedOHLCVBar] = {}
    for bar in sorted(settled, key=lambda b: b.session_date):
        by_session[bar.session_date] = bar
    duplicates = len(settled) - len(by_session)

    ordered = [by_session[session] for session in sorted(by_session)]
    window = tuple(ordered[-window_sessions:])

    last_session = window[-1].session_date if window else None
    staleness = (as_of.date() - last_session).days if last_session is not None else None

    return BarWindow(
        bars=window,
        duplicate_sessions_dropped=duplicates,
        first_session=window[0].session_date if window else None,
        last_session=last_session,
        staleness_days=staleness,
    )
