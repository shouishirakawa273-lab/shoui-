"""バリュエーション分位のテスト。実APIには接続しない。

方針は `DECISIONS.md` 2026-11-24 (10) に**実データの分布を見る前**に記録してある。
ここで固定するのはその方針であり、観測に合わせた調整ではない。

行の形は2026-11-24の7203実観測に合わせている(11 Field、`Date`は営業日)。
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from lib.screener.valuation_percentile import (
    DEFAULT_MIN_SESSIONS,
    MAX_STALENESS_DAYS,
    PERCENTILE_INDICATORS,
    assess_valuation_percentiles,
)

DECISION_AT = datetime(2026, 11, 24, 15, 30, tzinfo=UTC)
CODE = "7203"


def _row(session: date, *, per: float | None = 10.0, pbr: float | None = 1.0, fwd: float | None = 11.0) -> dict[str, Any]:
    return {
        "Date": session.isoformat(),
        "Code": "72030",
        "EPS": 344.11,
        "FwdEPS": 303.1,
        "BPS": 3179.34,
        "ROE": 0.1151,
        "FwdROE": 0.0953,
        "PER": per,
        "FwdPER": fwd,
        "PBR": pbr,
        "MktCap": 39009555.0,
    }


def _series(values: list[float | None], *, end: date = date(2026, 11, 20)) -> list[dict[str, Any]]:
    """末尾を `end` として1日ずつ遡る行列。最後の要素が現在値になる。"""
    rows = []
    for offset, value in enumerate(reversed(values)):
        rows.append(_row(end - __import__("datetime").timedelta(days=offset), per=value, pbr=value, fwd=value))
    return list(reversed(rows))


def _flat(n: int, value: float) -> list[float | None]:
    return [value] * n


# --- 基本 ---


def test_percentile_is_the_empirical_cdf() -> None:
    """`count(x <= 現在値) / n`。現在値は自分の標本に含まれる。"""
    values: list[float | None] = [*_flat(DEFAULT_MIN_SESSIONS - 1, 5.0), 10.0]
    result = assess_valuation_percentiles(code=CODE, rows=_series(values), decision_at=DECISION_AT)
    per = result.indicator("PER")
    assert per is not None
    assert per.current_value == Decimal("10")
    assert per.sample_size == DEFAULT_MIN_SESSIONS
    assert per.percentile == Decimal(1)  # 全件が現在値以下


def test_lowest_value_gets_the_lowest_percentile() -> None:
    values: list[float | None] = [*_flat(DEFAULT_MIN_SESSIONS - 1, 20.0), 5.0]
    result = assess_valuation_percentiles(code=CODE, rows=_series(values), decision_at=DECISION_AT)
    per = result.indicator("PER")
    assert per is not None
    assert per.percentile == Decimal(1) / Decimal(DEFAULT_MIN_SESSIONS)


def test_all_three_indicators_are_reported() -> None:
    result = assess_valuation_percentiles(code=CODE, rows=_series(_flat(DEFAULT_MIN_SESSIONS, 10.0)), decision_at=DECISION_AT)
    assert tuple(i.indicator for i in result.indicators) == PERCENTILE_INDICATORS


# --- 非正の値 ---


def test_negative_values_leave_the_distribution_and_are_counted() -> None:
    """負のPERは「安い」ではなく「赤字」。分布に残すと下端の意味が反転する。"""
    values: list[float | None] = [*_flat(50, -3.0), *_flat(DEFAULT_MIN_SESSIONS, 10.0)]
    result = assess_valuation_percentiles(code=CODE, rows=_series(values), decision_at=DECISION_AT)
    per = result.indicator("PER")
    assert per is not None
    assert per.sample_size == DEFAULT_MIN_SESSIONS
    assert per.excluded_non_positive == 50
    assert per.percentile is not None


def test_current_non_positive_value_has_unknown_percentile() -> None:
    """[方針] 0でも100でもない。分布から除いた値を分布に位置づけられない。"""
    values: list[float | None] = [*_flat(DEFAULT_MIN_SESSIONS, 10.0), -2.0]
    result = assess_valuation_percentiles(code=CODE, rows=_series(values), decision_at=DECISION_AT)
    per = result.indicator("PER")
    assert per is not None
    assert per.current_value == Decimal("-2")
    assert per.percentile is None
    assert per.unknown_reason is not None
    assert "非正" in per.unknown_reason


def test_zero_is_treated_as_non_positive() -> None:
    values: list[float | None] = [*_flat(DEFAULT_MIN_SESSIONS, 10.0), 0.0]
    result = assess_valuation_percentiles(code=CODE, rows=_series(values), decision_at=DECISION_AT)
    per = result.indicator("PER")
    assert per is not None
    assert per.percentile is None


def test_negative_earnings_are_not_mapped_to_infinitely_expensive() -> None:
    """その流儀もあるが、本Labが発明する変換なので採らない。"""
    values: list[float | None] = [*_flat(DEFAULT_MIN_SESSIONS, 10.0), -2.0]
    result = assess_valuation_percentiles(code=CODE, rows=_series(values), decision_at=DECISION_AT)
    per = result.indicator("PER")
    assert per is not None
    assert per.percentile != Decimal(1)


# --- 欠損 ---


def test_missing_values_are_counted_separately_from_non_positive() -> None:
    values: list[float | None] = [*[None] * 30, *_flat(DEFAULT_MIN_SESSIONS, 10.0)]
    result = assess_valuation_percentiles(code=CODE, rows=_series(values), decision_at=DECISION_AT)
    per = result.indicator("PER")
    assert per is not None
    assert per.excluded_missing == 30
    assert per.excluded_non_positive == 0


def test_missing_current_value_is_unknown_not_zero() -> None:
    values: list[float | None] = [*_flat(DEFAULT_MIN_SESSIONS, 10.0), None]
    result = assess_valuation_percentiles(code=CODE, rows=_series(values), decision_at=DECISION_AT)
    per = result.indicator("PER")
    assert per is not None
    assert per.current_value is None
    assert per.percentile is None


# --- 最小標本 ---


def test_sample_below_one_trading_year_is_unknown() -> None:
    """250件未満では「10年分位」という名前が誤解を招く。"""
    result = assess_valuation_percentiles(code=CODE, rows=_series(_flat(DEFAULT_MIN_SESSIONS - 1, 10.0)), decision_at=DECISION_AT)
    per = result.indicator("PER")
    assert per is not None
    assert per.percentile is None
    assert per.sample_size == DEFAULT_MIN_SESSIONS - 1
    assert "1営業年" in (per.unknown_reason or "")


def test_coverage_is_always_reported_so_a_short_sample_is_visible() -> None:
    rows = _series(_flat(300, 10.0))
    result = assess_valuation_percentiles(code=CODE, rows=rows, decision_at=DECISION_AT)
    per = result.indicator("PER")
    assert per is not None
    assert per.first_session is not None
    assert per.last_session == date(2026, 11, 20)
    assert per.sample_size == 300


# --- PIT ---


def test_rows_after_decision_at_are_not_visible() -> None:
    """値はその場の終値から算出されるので、引けるまで知り得ない。"""
    future = date(2026, 11, 25)
    rows = [*_series(_flat(DEFAULT_MIN_SESSIONS, 10.0)), _row(future, per=99.0)]
    result = assess_valuation_percentiles(code=CODE, rows=rows, decision_at=DECISION_AT)
    assert result.current_session == date(2026, 11, 20)
    per = result.indicator("PER")
    assert per is not None
    assert per.current_value == Decimal("10")


def test_rows_before_the_window_are_excluded() -> None:
    old = _row(date(2010, 1, 4), per=1.0)
    rows = [old, *_series(_flat(DEFAULT_MIN_SESSIONS, 10.0))]
    result = assess_valuation_percentiles(code=CODE, rows=rows, decision_at=DECISION_AT, window_years=10)
    per = result.indicator("PER")
    assert per is not None
    assert per.sample_size == DEFAULT_MIN_SESSIONS
    assert result.window_start == date(2016, 11, 24)


def test_naive_decision_at_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        assess_valuation_percentiles(code=CODE, rows=_series(_flat(10, 10.0)), decision_at=datetime(2026, 11, 24))


def test_other_codes_are_ignored() -> None:
    other = {**_row(date(2026, 11, 20), per=99.0), "Code": "67580"}
    rows = [*_series(_flat(DEFAULT_MIN_SESSIONS, 10.0)), other]
    result = assess_valuation_percentiles(code=CODE, rows=rows, decision_at=DECISION_AT)
    per = result.indicator("PER")
    assert per is not None
    assert per.current_value == Decimal("10")


# --- 陳腐化 ---


def test_stale_series_is_unknown_not_treated_as_current() -> None:
    """上場廃止・売買停止の可能性。現在値を現在として扱わない。"""
    stale_end = date(2026, 11, 24) - __import__("datetime").timedelta(days=MAX_STALENESS_DAYS + 5)
    rows = _series(_flat(DEFAULT_MIN_SESSIONS, 10.0), end=stale_end)
    result = assess_valuation_percentiles(code=CODE, rows=rows, decision_at=DECISION_AT)
    assert result.indicators == ()
    assert result.unknown_reason is not None
    assert result.staleness_days is not None
    assert result.staleness_days > MAX_STALENESS_DAYS


def test_staleness_reuses_the_liquidity_threshold() -> None:
    """2つ目の数字を発明しない。"""
    from lib.pretrade_risk.liquidity import DEFAULT_MAX_STALENESS_DAYS

    assert MAX_STALENESS_DAYS == DEFAULT_MAX_STALENESS_DAYS


# --- 入力検証 ---


def test_no_visible_rows_is_a_stated_reason() -> None:
    result = assess_valuation_percentiles(code=CODE, rows=[], decision_at=DECISION_AT)
    assert result.indicators == ()
    assert result.unknown_reason is not None


@pytest.mark.parametrize(("years", "minimum"), [(0, 250), (-1, 250)])
def test_invalid_window_is_rejected(years: int, minimum: int) -> None:
    with pytest.raises(ValueError, match="window_years"):
        assess_valuation_percentiles(code=CODE, rows=_series(_flat(10, 10.0)), decision_at=DECISION_AT, window_years=years)


def test_float_values_do_not_leak_binary_expansion() -> None:
    values: list[float | None] = [*_flat(DEFAULT_MIN_SESSIONS - 1, 0.1), 0.1]
    result = assess_valuation_percentiles(code=CODE, rows=_series(values), decision_at=DECISION_AT)
    per = result.indicator("PER")
    assert per is not None
    assert per.current_value == Decimal("0.1")
    assert str(per.current_value) == "0.1"
