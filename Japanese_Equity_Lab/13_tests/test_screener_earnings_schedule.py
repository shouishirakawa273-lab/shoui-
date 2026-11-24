"""決算発表予定日のテスト。実APIには接続しない。

行の形は2026-11-24の7203実観測(`PubDate`/`SchDate`/`FQName`/`FYE`/`Code`/
`CoName`/`CoNameEn`、40件、年4回、予定日の約1ヶ月前に公表)。

要点は**改定履歴を畳まないこと**と、**公表日より前にその予定日を知っていたことに
しないこと**。
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

import pytest
from lib.screener.earnings_schedule import build_earnings_schedule

DECISION_AT = datetime(2026, 11, 24, 15, 30, tzinfo=UTC)
CODE = "7203"


def _row(published: str, scheduled: str | None, *, fq: str = "3Q", fye: str = "0331") -> dict[str, Any]:
    return {
        "PubDate": published,
        "SchDate": scheduled if scheduled is not None else "",
        "FQName": fq,
        "FYE": fye,
        "Code": "72030",
        "CoName": "トヨタ自動車",
        "CoNameEn": "TOYOTA MOTOR CORPORATION",
    }


# --- 次回の予定日 ---


def test_next_scheduled_is_the_nearest_future_date() -> None:
    rows = [
        _row("2026-09-28", "2026-11-05", fq="2Q"),
        _row("2026-12-20", "2027-02-05", fq="3Q"),
    ]
    schedule = build_earnings_schedule(code=CODE, rows=rows, decision_at=DECISION_AT)
    # 2026-12-20公表の行は判定時点より後なので見えない。
    assert schedule.next_scheduled is None
    assert schedule.unknown_reason is not None


def test_upcoming_scheduled_date_is_found() -> None:
    rows = [_row("2026-11-01", "2026-12-10", fq="3Q")]
    schedule = build_earnings_schedule(code=CODE, rows=rows, decision_at=DECISION_AT)
    assert schedule.next_scheduled is not None
    assert schedule.next_scheduled.scheduled_on == date(2026, 12, 10)
    assert schedule.next_scheduled.fiscal_quarter == "3Q"
    assert schedule.next_scheduled.fiscal_year_end == "0331"


def test_past_scheduled_dates_are_not_offered_as_next() -> None:
    rows = [_row("2026-09-28", "2026-11-05", fq="2Q")]
    schedule = build_earnings_schedule(code=CODE, rows=rows, decision_at=DECISION_AT)
    assert schedule.next_scheduled is None
    assert len(schedule.entries) == 1  # 履歴としては残す


def test_scheduled_on_the_decision_date_counts_as_upcoming() -> None:
    rows = [_row("2026-11-01", "2026-11-24", fq="3Q")]
    schedule = build_earnings_schedule(code=CODE, rows=rows, decision_at=DECISION_AT)
    assert schedule.next_scheduled is not None
    assert schedule.next_scheduled.scheduled_on == date(2026, 11, 24)


# --- 改定履歴 ---


def test_revisions_are_kept_not_collapsed() -> None:
    """[PIT] 予定日は改定される。最後の1件に畳むと履歴が消える。"""
    rows = [
        _row("2026-11-01", "2026-12-10", fq="3Q"),
        _row("2026-11-15", "2026-12-17", fq="3Q"),
    ]
    schedule = build_earnings_schedule(code=CODE, rows=rows, decision_at=DECISION_AT)
    assert len(schedule.entries) == 2
    assert {e.scheduled_on for e in schedule.entries} == {date(2026, 12, 10), date(2026, 12, 17)}
    assert schedule.revision_count == 1


def test_latest_publication_wins_for_the_same_scheduled_date() -> None:
    rows = [
        _row("2026-11-01", "2026-12-10", fq="3Q"),
        _row("2026-11-15", "2026-12-10", fq="3Q"),
    ]
    schedule = build_earnings_schedule(code=CODE, rows=rows, decision_at=DECISION_AT)
    assert schedule.next_scheduled is not None
    assert schedule.next_scheduled.published_on == date(2026, 11, 15)


def test_revision_count_is_zero_for_distinct_quarters() -> None:
    rows = [
        _row("2026-06-29", "2026-08-04", fq="1Q"),
        _row("2026-09-28", "2026-11-05", fq="2Q"),
        _row("2026-11-01", "2026-12-10", fq="3Q"),
    ]
    schedule = build_earnings_schedule(code=CODE, rows=rows, decision_at=DECISION_AT)
    assert schedule.revision_count == 0
    assert len(schedule.entries) == 3


def test_same_quarter_of_a_different_fiscal_year_is_not_a_revision() -> None:
    rows = [
        _row("2025-11-01", "2025-12-10", fq="3Q", fye="0331"),
        _row("2026-11-01", "2026-12-10", fq="3Q", fye="0630"),
    ]
    schedule = build_earnings_schedule(code=CODE, rows=rows, decision_at=DECISION_AT)
    assert schedule.revision_count == 0


# --- PIT ---


def test_rows_published_after_decision_date_are_invisible() -> None:
    rows = [_row("2026-12-01", "2027-02-05", fq="3Q")]
    schedule = build_earnings_schedule(code=CODE, rows=rows, decision_at=DECISION_AT)
    assert schedule.entries == ()
    assert schedule.unknown_reason is not None


def test_rows_without_a_publication_date_are_dropped() -> None:
    """可視性を判定できない行は推測で通さない。"""
    rows = [{"PubDate": "", "SchDate": "2026-12-10", "Code": "72030"}, _row("2026-11-01", "2026-12-10")]
    schedule = build_earnings_schedule(code=CODE, rows=rows, decision_at=DECISION_AT)
    assert len(schedule.entries) == 1


def test_naive_decision_at_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        build_earnings_schedule(code=CODE, rows=[], decision_at=datetime(2026, 11, 24))


def test_other_codes_are_ignored() -> None:
    rows = [{**_row("2026-11-01", "2026-12-10"), "Code": "67580"}]
    schedule = build_earnings_schedule(code=CODE, rows=rows, decision_at=DECISION_AT)
    assert schedule.entries == ()


# --- 未定・異常値 ---


def test_undecided_scheduled_date_is_none_not_dropped() -> None:
    """`SchDate` が空になることがある。行自体は履歴として残す。"""
    rows = [_row("2026-11-01", None, fq="3Q")]
    schedule = build_earnings_schedule(code=CODE, rows=rows, decision_at=DECISION_AT)
    assert len(schedule.entries) == 1
    assert schedule.entries[0].scheduled_on is None
    assert schedule.next_scheduled is None


def test_malformed_dates_do_not_crash() -> None:
    rows = [_row("not-a-date", "2026-12-10"), _row("2026-11-01", "also-not-a-date")]
    schedule = build_earnings_schedule(code=CODE, rows=rows, decision_at=DECISION_AT)
    assert len(schedule.entries) == 1
    assert schedule.entries[0].scheduled_on is None


def test_empty_rows_is_a_stated_reason() -> None:
    schedule = build_earnings_schedule(code=CODE, rows=[], decision_at=DECISION_AT)
    assert schedule.entries == ()
    assert schedule.next_scheduled is None
    assert schedule.unknown_reason is not None


def test_fiscal_year_end_is_kept_as_text_not_converted() -> None:
    """`FYE` は MMDD で年が入っていない。日付に変換しない。"""
    rows = [_row("2026-11-01", "2026-12-10", fye="0331")]
    schedule = build_earnings_schedule(code=CODE, rows=rows, decision_at=DECISION_AT)
    assert schedule.entries[0].fiscal_year_end == "0331"
