"""Step 1 相関警告の合成データテスト。実APIには一切接続しない。"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta

import pytest
from lib.backtest.price_history import StaticPriceHistory
from lib.pretrade_risk import CorrelationOutcome, assess_correlation
from lib.schemas.price_data import AdjustedOHLCVBar

AS_OF = datetime(2026, 11, 21, 15, 0, tzinfo=UTC)
START = date(2025, 1, 6)


def _bar(code: str, session_date: date, close: float | None) -> AdjustedOHLCVBar:
    return AdjustedOHLCVBar(
        code=code,
        session_date=session_date,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=10_000.0,
        split_adjustment_factor=1.0,
    )


def _from_returns(code: str, returns: list[float], *, start: date = START) -> list[AdjustedOHLCVBar]:
    """与えたリターン列を再現する終値Bar列を作る(先頭は基準日)。"""
    bars = [_bar(code, start, 1000.0)]
    close = 1000.0
    for index, value in enumerate(returns, start=1):
        close *= 1.0 + value
        bars.append(_bar(code, start + timedelta(days=index), close))
    return bars


def _wave(n: int, *, phase: float = 0.0, scale: float = 0.01) -> list[float]:
    """決定的で分散が正になるリターン列。"""
    return [scale * math.sin(phase + i * 0.7) for i in range(n)]


def _source(*series: list[AdjustedOHLCVBar]) -> StaticPriceHistory:
    return StaticPriceHistory({bars[0].code: bars for bars in series})


def test_identical_movement_warns() -> None:
    returns = _wave(120)
    source = _source(_from_returns("1111", returns), _from_returns("2222", returns))

    result = assess_correlation(source=source, codes=["1111", "2222"], as_of=AS_OF)

    (pair,) = result.pairs
    assert pair.correlation == pytest.approx(1.0)
    assert pair.outcome is CorrelationOutcome.WARN
    assert result.warned_pairs == (pair,)


def test_opposite_movement_is_not_warned() -> None:
    """負の相関は集中ではなく打ち消し合いなので警告しない。推定値は残す。"""
    returns = _wave(120)
    source = _source(_from_returns("1111", returns), _from_returns("2222", [-r for r in returns]))

    result = assess_correlation(source=source, codes=["1111", "2222"], as_of=AS_OF)

    (pair,) = result.pairs
    assert pair.correlation is not None
    assert pair.correlation < -0.9
    assert pair.outcome is CorrelationOutcome.OK
    assert result.warned_pairs == ()


def test_weakly_related_series_is_ok() -> None:
    source = _source(
        _from_returns("1111", _wave(200)),
        _from_returns("2222", _wave(200, phase=math.pi / 2)),
    )

    result = assess_correlation(source=source, codes=["1111", "2222"], as_of=AS_OF)

    (pair,) = result.pairs
    assert pair.correlation is not None
    assert abs(pair.correlation) < 0.7
    assert pair.outcome is CorrelationOutcome.OK


def test_insufficient_overlap_is_unknown_not_ok() -> None:
    source = _source(_from_returns("1111", _wave(10)), _from_returns("2222", _wave(10)))

    result = assess_correlation(source=source, codes=["1111", "2222"], as_of=AS_OF)

    (pair,) = result.pairs
    assert pair.outcome is CorrelationOutcome.UNKNOWN
    assert pair.correlation is None
    assert pair.overlapping_returns == 10
    assert pair.unknown_reason is not None


def test_flat_series_has_undefined_correlation_and_is_unknown() -> None:
    """分散0の系列との相関は定義されない。0にしない。"""
    flat = [_bar("2222", START + timedelta(days=i), 1000.0) for i in range(120)]
    source = _source(_from_returns("1111", _wave(120)), flat)

    result = assess_correlation(source=source, codes=["1111", "2222"], as_of=AS_OF)

    (pair,) = result.pairs
    assert pair.outcome is CorrelationOutcome.UNKNOWN
    assert pair.correlation is None
    assert pair.overlapping_returns >= 60


def test_returns_are_paired_only_on_identical_intervals() -> None:
    """片方に欠損日があると区間が変わるため、そのリターンは対応付けない。"""
    returns = _wave(120)
    series_a = _from_returns("1111", returns)
    series_b = _from_returns("2222", returns)
    # 2222 から中間の1セッションを落とす。前後2本の区間キーが変わる。
    dropped = series_b.pop(50)

    result = assess_correlation(source=_source(series_a, series_b), codes=["1111", "2222"], as_of=AS_OF)

    (pair,) = result.pairs
    full = assess_correlation(
        source=_source(series_a, _from_returns("2222", returns)), codes=["1111", "2222"], as_of=AS_OF
    ).pairs[0]

    # 落としたのは中間日なので、欠損の前後2本ぶんが対応付けから外れる。
    assert series_b[0].session_date < dropped.session_date < series_b[-1].session_date
    assert pair.overlapping_returns == full.overlapping_returns - 2


def test_missing_close_breaks_only_its_own_returns() -> None:
    returns = _wave(120)
    series_b = _from_returns("2222", returns)
    series_b[50] = _bar("2222", series_b[50].session_date, None)

    result = assess_correlation(source=_source(_from_returns("1111", returns), series_b), codes=["1111", "2222"], as_of=AS_OF)

    (pair,) = result.pairs
    # 終値未知のBarに接する2本のリターンだけが作られない。残りは生きる。
    assert pair.overlapping_returns == len(returns) - 2
    assert pair.correlation is not None


def test_bars_after_as_of_are_not_used() -> None:
    """PIT: as_of より後のセッションは構造的に入らない。"""
    returns = _wave(120)
    series_a = _from_returns("1111", returns, start=date(2026, 7, 1))
    series_b = _from_returns("2222", returns, start=date(2026, 7, 1))
    # as_of より後に、相関を壊す向きの動きを足す。
    future_a = _bar("1111", date(2026, 12, 1), 2000.0)
    future_b = _bar("2222", date(2026, 12, 1), 100.0)

    result = assess_correlation(source=_source([*series_a, future_a], [*series_b, future_b]), codes=["1111", "2222"], as_of=AS_OF)

    (pair,) = result.pairs
    assert pair.overlapping_returns == len(returns)
    assert pair.correlation == pytest.approx(1.0)


def test_all_pairs_are_evaluated() -> None:
    source = _source(
        _from_returns("1111", _wave(150)),
        _from_returns("2222", _wave(150, phase=0.3)),
        _from_returns("3333", _wave(150, phase=2.0)),
    )

    result = assess_correlation(source=source, codes=["1111", "2222", "3333"], as_of=AS_OF)

    assert len(result.pairs) == 3
    assert {(p.code_a, p.code_b) for p in result.pairs} == {("1111", "2222"), ("1111", "3333"), ("2222", "3333")}


def test_window_limits_how_far_back_returns_are_taken() -> None:
    returns = _wave(300)
    source = _source(_from_returns("1111", returns), _from_returns("2222", returns))

    result = assess_correlation(source=source, codes=["1111", "2222"], as_of=AS_OF, window_sessions=100)

    # 直近100本のBarから作れるリターンは99本。
    (pair,) = result.pairs
    assert pair.overlapping_returns == 99


def test_duplicate_codes_raise() -> None:
    source = _source(_from_returns("1111", _wave(120)))

    with pytest.raises(ValueError, match="duplicates"):
        assess_correlation(source=source, codes=["1111", "1111"], as_of=AS_OF)


@pytest.mark.parametrize(
    "kwargs",
    [{"window_sessions": 1}, {"threshold": 1.0}, {"threshold": -1.0}, {"min_overlap": 1}],
)
def test_invalid_arguments_raise(kwargs: dict[str, float | int]) -> None:
    call: dict[str, object] = {
        "source": _source(_from_returns("1111", _wave(120)), _from_returns("2222", _wave(120))),
        "codes": ["1111", "2222"],
        "as_of": AS_OF,
    }
    call.update(kwargs)

    with pytest.raises(ValueError):
        assess_correlation(**call)  # type: ignore[arg-type]
