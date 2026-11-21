"""Step 1 流動性警告の合成データテスト。実APIには一切接続しない。"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from lib.backtest.price_history import AsOfAdjustedPriceHistory, StaticPriceHistory
from lib.market_calendar import session_close_at
from lib.pretrade_risk import LiquidityOutcome, assess_liquidity
from lib.schemas.price_data import AdjustedOHLCVBar, CorporateAction, CorporateActionType, RawOHLCVBar

AS_OF = session_close_at(date(2026, 11, 21))


def _bar(
    code: str,
    session_date: date,
    *,
    close: float | None,
    volume: float | None,
) -> AdjustedOHLCVBar:
    return AdjustedOHLCVBar(
        code=code,
        session_date=session_date,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=volume,
        split_adjustment_factor=1.0,
    )


def _series(
    code: str = "1234",
    *,
    sessions: int = 20,
    close: float | None = 1000.0,
    volume: float | None = 10_000.0,
    end: date = date(2026, 11, 20),
) -> list[AdjustedOHLCVBar]:
    """end から遡って sessions 本の連続した(暦日ベースの)Bar列。"""
    return [_bar(code, end - timedelta(days=sessions - 1 - i), close=close, volume=volume) for i in range(sessions)]


def _source(bars: list[AdjustedOHLCVBar]) -> StaticPriceHistory:
    return StaticPriceHistory({bars[0].code: bars})


def test_position_well_within_daily_turnover_is_ok() -> None:
    # 平均売買代金 = 1000 * 10_000 = 10,000,000円/日。100万円は0.1日分。
    result = assess_liquidity(source=_source(_series()), code="1234", position_value=1_000_000.0, as_of=AS_OF)

    assert result.outcome is LiquidityOutcome.OK
    assert result.average_daily_turnover == pytest.approx(10_000_000.0)
    assert result.days_to_liquidate == pytest.approx(0.1)
    assert result.sessions_known == 20
    assert result.sessions_unknown == 0


def test_position_exceeding_threshold_warns() -> None:
    # 5000万円 / 1000万円 = 5日分 > 既定の3日。
    result = assess_liquidity(source=_source(_series()), code="1234", position_value=50_000_000.0, as_of=AS_OF)

    assert result.outcome is LiquidityOutcome.WARN
    assert result.days_to_liquidate == pytest.approx(5.0)


def test_exactly_at_threshold_is_ok_not_warn() -> None:
    # 判定は `> threshold` なので、ちょうど3日分はWARNにしない。
    result = assess_liquidity(source=_source(_series()), code="1234", position_value=30_000_000.0, as_of=AS_OF)

    assert result.days_to_liquidate == pytest.approx(3.0)
    assert result.outcome is LiquidityOutcome.OK


def test_missing_volume_is_excluded_from_mean_and_counted_not_zero_filled() -> None:
    bars = _series()
    # 20本中3本のvolumeを欠損させる。欠損日を0として平均に含めてはならない。
    for index in (0, 5, 10):
        bars[index] = _bar(bars[index].code, bars[index].session_date, close=1000.0, volume=None)

    result = assess_liquidity(source=_source(bars), code="1234", position_value=1_000_000.0, as_of=AS_OF)

    assert result.sessions_observed == 20
    assert result.sessions_known == 17
    assert result.sessions_unknown == 3
    # 既知17本はすべて同じ売買代金なので、0埋めされていなければ平均は変わらない。
    assert result.average_daily_turnover == pytest.approx(10_000_000.0)
    assert result.outcome is LiquidityOutcome.OK


def test_insufficient_known_sessions_is_unknown_not_ok() -> None:
    bars = _series()
    # 既知を6本だけ残す。既定の min_known_ratio=0.75 は15本を要求する。
    for index in range(14):
        bars[index] = _bar(bars[index].code, bars[index].session_date, close=1000.0, volume=None)

    result = assess_liquidity(source=_source(bars), code="1234", position_value=1_000_000.0, as_of=AS_OF)

    assert result.outcome is LiquidityOutcome.UNKNOWN
    assert result.average_daily_turnover is None
    assert result.days_to_liquidate is None
    assert result.sessions_known == 6
    assert result.unknown_reason is not None


def test_no_bars_at_all_is_unknown_not_ok() -> None:
    result = assess_liquidity(source=StaticPriceHistory({}), code="9999", position_value=1_000_000.0, as_of=AS_OF)

    assert result.outcome is LiquidityOutcome.UNKNOWN
    assert result.sessions_observed == 0
    assert result.sessions_known == 0
    assert result.average_daily_turnover is None


def test_zero_turnover_is_unknown_not_division_by_zero() -> None:
    result = assess_liquidity(source=_source(_series(volume=0.0)), code="1234", position_value=1_000_000.0, as_of=AS_OF)

    assert result.outcome is LiquidityOutcome.UNKNOWN
    assert result.days_to_liquidate is None


def test_bars_after_as_of_are_not_used() -> None:
    """PIT: as_of より後のセッションは構造的に入らない。"""
    bars = _series(sessions=20, volume=10_000.0, end=date(2026, 11, 20))
    # as_of の翌日に、平均を大きく動かすほどの出来高を置く。
    future = _bar("1234", date(2026, 11, 22), close=1000.0, volume=10_000_000.0)

    result = assess_liquidity(source=_source([*bars, future]), code="1234", position_value=1_000_000.0, as_of=AS_OF)

    assert result.sessions_observed == 20
    assert result.average_daily_turnover == pytest.approx(10_000_000.0)


def test_turnover_is_invariant_under_split_adjustment() -> None:
    """closeは /factor、volumeは *factor されるため売買代金は不変。"""
    unadjusted = assess_liquidity(
        source=_source(_series(close=1000.0, volume=10_000.0)),
        code="1234",
        position_value=1_000_000.0,
        as_of=AS_OF,
    )
    # 1:2分割後に相当する表現。
    adjusted = assess_liquidity(
        source=_source(_series(close=500.0, volume=20_000.0)),
        code="1234",
        position_value=1_000_000.0,
        as_of=AS_OF,
    )

    assert unadjusted.average_daily_turnover == pytest.approx(adjusted.average_daily_turnover)
    assert unadjusted.days_to_liquidate == pytest.approx(adjusted.days_to_liquidate)


def test_window_takes_the_most_recent_sessions() -> None:
    old = [_bar("1234", date(2026, 1, 5) + timedelta(days=i), close=1000.0, volume=1_000.0) for i in range(30)]
    recent = _series(sessions=20, volume=10_000.0)

    result = assess_liquidity(
        source=_source([*old, *recent]), code="1234", position_value=1_000_000.0, as_of=AS_OF, window_sessions=20
    )

    # 直近20本のみを見るので、古い低出来高は平均に影響しない。
    assert result.sessions_observed == 20
    assert result.average_daily_turnover == pytest.approx(10_000_000.0)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"window_sessions": 0},
        {"threshold_days": 0.0},
        {"threshold_days": -1.0},
        {"min_known_ratio": 0.0},
        {"min_known_ratio": 1.5},
        {"position_value": -1.0},
        {"position_value": float("nan")},
    ],
)
def test_invalid_arguments_raise(kwargs: dict[str, float | int]) -> None:
    call: dict[str, object] = {
        "source": _source(_series()),
        "code": "1234",
        "position_value": 1_000_000.0,
        "as_of": AS_OF,
    }
    call.update(kwargs)

    with pytest.raises(ValueError):
        assess_liquidity(**call)  # type: ignore[arg-type]


def test_long_but_stale_history_is_unknown_not_ok() -> None:
    """[HIGH] 履歴が「短い」ではなく「古い」場合もOKにしない。

    上場廃止・長期売買停止・Providerのカバレッジ切れでは、窓は満たされるのに
    中身が何年も前になる。min_known_ratio は長さしか見ないので素通りしていた。
    """
    stale_end = date(2025, 5, 20)  # AS_OF から約1年半前
    bars = _series(sessions=20, end=stale_end)

    result = assess_liquidity(source=_source(bars), code="1234", position_value=1_000_000.0, as_of=AS_OF)

    assert result.sessions_observed == 20
    assert result.sessions_known == 20
    assert result.sessions_unknown == 0
    assert result.outcome is LiquidityOutcome.UNKNOWN
    assert result.average_daily_turnover is None
    assert result.last_session == stale_end
    assert result.staleness_days is not None and result.staleness_days > 500
    assert "max_staleness_days" in (result.unknown_reason or "")


def test_recent_history_within_staleness_bound_is_assessed() -> None:
    result = assess_liquidity(
        source=_source(_series(sessions=20, end=date(2026, 11, 20))),
        code="1234",
        position_value=1_000_000.0,
        as_of=AS_OF,
    )

    assert result.outcome is LiquidityOutcome.OK
    assert result.staleness_days == 1


def test_duplicate_sessions_do_not_inflate_coverage() -> None:
    """[MEDIUM] 重複行でカバレッジ床を通過させない。"""
    bars = _series(sessions=10)
    result = assess_liquidity(source=_source([*bars, *bars]), code="1234", position_value=1_000_000.0, as_of=AS_OF)

    # 10本を重複させても20本には見えない。既定は15本要求なのでUNKNOWN。
    assert result.sessions_observed == 10
    assert result.duplicate_sessions_dropped == 10
    assert result.outcome is LiquidityOutcome.UNKNOWN


def test_observed_coverage_is_reported() -> None:
    """[MEDIUM] 要求期間ではなく実際の観測範囲が分かること。"""
    result = assess_liquidity(
        source=_source(_series(sessions=20, end=date(2026, 11, 20))),
        code="1234",
        position_value=1_000_000.0,
        as_of=AS_OF,
    )

    assert result.first_session == date(2026, 11, 1)
    assert result.last_session == date(2026, 11, 20)


def test_turnover_is_invariant_under_the_as_of_adjusted_path() -> None:
    """[LOW] 実際にCLIが通る調整関数を使って売買代金不変性を固定する。

    `build_provider_derived_adjusted_bars` はcloseに累積factorを乗じvolumeを
    同じfactorで除す。どちらかが価格だけを調整するよう変わればここで落ちる。
    """
    sessions = [date(2026, 11, 20) - timedelta(days=19 - i) for i in range(20)]
    raw = [
        RawOHLCVBar(code="1234", session_date=s, open=1000.0, high=1000.0, low=1000.0, close=1000.0, volume=10_000.0)
        for s in sessions
    ]
    split = CorporateAction(
        code="1234",
        action_type=CorporateActionType.SPLIT,
        effective_date=sessions[10],
        split_ratio=2.0,
        announced_at=session_close_at(sessions[0]),
    )

    without_event = assess_liquidity(
        source=AsOfAdjustedPriceHistory({"1234": raw}, {"1234": []}),
        code="1234",
        position_value=1_000_000.0,
        as_of=AS_OF,
    )
    with_event = assess_liquidity(
        source=AsOfAdjustedPriceHistory({"1234": raw}, {"1234": [split]}),
        code="1234",
        position_value=1_000_000.0,
        as_of=AS_OF,
    )

    assert without_event.average_daily_turnover == pytest.approx(10_000_000.0)
    assert with_event.average_daily_turnover == pytest.approx(without_event.average_daily_turnover)


def test_naive_as_of_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        assess_liquidity(
            source=_source(_series()),
            code="1234",
            position_value=1_000_000.0,
            as_of=datetime(2026, 11, 21, 15, 30),
        )
