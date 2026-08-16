"""Phase3C(D0038): Survivorship Bias / Point-in-Time Universeのテスト。

少数の「上場・上場廃止・非普通株混入」を含む合成Fixtureで、以下を確認する。
- 上場前・上場廃止後の銘柄がdecision_at時点のUniverseへ正しく出入りすること
- Survivorship Biasを解消できていない場合、resolutionがRESOLVEDにならないこと(PARTIAL)
- ETF等(普通株以外)がbuild_common_stock_universe()で除外されること
- BacktestEngine.run()にuniverse_providerを渡すと、上場廃止後の銘柄が
  Signal自体の対象から外れること(既存の`universe_codes`のみの経路は無変更)

実際のMarketCodeの値・意味はこのセッションでは未検証のため、ここで使う"0111"等の
値は説明用の合成データであり、実データの値そのものではない(DECISIONS.md D0038参照)。
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from lib.backtest.engine import BacktestEngine, BacktestRunConfig
from lib.backtest.price_history import StaticPriceHistory
from lib.market_calendar import TradingCalendar, session_close_at
from lib.schemas.price_data import AdjustedOHLCVBar
from lib.universe import (
    ListingBasedUniverseProvider,
    ListingRecord,
    UniverseResolution,
    build_common_stock_universe,
)

_COMMON_STOCK_MARKET_CODES = frozenset({"0111", "0112", "0113"})  # Prime/Standard/Growth相当(合成、未検証)
_ETF_MARKET_CODE = "0117"  # ETF相当(合成、未検証)


def _mixed_listings() -> list[ListingRecord]:
    return [
        ListingRecord(code="1000", market="0111", company_name="長期上場企業", listing_date=date(2000, 1, 1)),
        ListingRecord(
            code="2000",
            market="0111",
            company_name="年央廃止企業",
            listing_date=date(2010, 1, 1),
            delisting_date=date(2024, 6, 3),
        ),
        ListingRecord(code="3000", market="0112", company_name="年央上場企業", listing_date=date(2024, 7, 1)),
        ListingRecord(code="4000", market=_ETF_MARKET_CODE, company_name="疑似ETF", listing_date=date(2015, 1, 1)),
    ]


def test_delisted_stock_leaves_universe_after_delisting_date() -> None:
    provider = ListingBasedUniverseProvider(_mixed_listings())
    before = provider.as_of(datetime(2024, 6, 1, tzinfo=UTC))
    after = provider.as_of(datetime(2024, 6, 3, tzinfo=UTC))
    assert "2000" in before.codes
    assert "2000" not in after.codes  # delisting_date当日から対象外


def test_newly_listed_stock_enters_universe_only_after_listing_date() -> None:
    provider = ListingBasedUniverseProvider(_mixed_listings())
    before = provider.as_of(datetime(2024, 6, 30, tzinfo=UTC))
    after = provider.as_of(datetime(2024, 7, 1, tzinfo=UTC))
    assert "3000" not in before.codes
    assert "3000" in after.codes


def test_resolution_is_resolved_when_delisting_dates_are_present() -> None:
    """1件でもdelisting_dateがあれば、Survivorship Biasを一部解消できているとみなしRESOLVED。"""
    provider = ListingBasedUniverseProvider(_mixed_listings())
    snapshot = provider.as_of(datetime(2024, 6, 1, tzinfo=UTC))
    assert snapshot.resolution == UniverseResolution.RESOLVED
    assert snapshot.survivorship_bias_unresolved is False


def test_resolution_is_partial_not_resolved_when_only_current_listings_known() -> None:
    """全listingにdelisting_dateが無い(=現在の上場銘柄しか分からない)場合、
    resolutionはRESOLVEDにせずPARTIALとして明示する(D0038)。"""
    survivors_only = [
        ListingRecord(code="1000", market="0111", listing_date=date(2000, 1, 1)),
        ListingRecord(code="3000", market="0112", listing_date=date(2024, 7, 1)),
    ]
    provider = ListingBasedUniverseProvider(survivors_only)
    snapshot = provider.as_of(datetime(2024, 8, 1, tzinfo=UTC))
    assert snapshot.resolution == UniverseResolution.PARTIAL
    assert snapshot.resolution != UniverseResolution.RESOLVED
    assert snapshot.survivorship_bias_unresolved is True


def test_build_common_stock_universe_excludes_non_common_stock_market_codes() -> None:
    result = build_common_stock_universe(_mixed_listings(), common_stock_market_codes=_COMMON_STOCK_MARKET_CODES)
    included_codes = {listing.code for listing in result.included}
    excluded_codes = {listing.code for listing in result.excluded}
    assert included_codes == {"1000", "2000", "3000"}
    assert excluded_codes == {"4000"}
    assert result.excluded_market_codes == {_ETF_MARKET_CODE: 1}


def test_build_common_stock_universe_excludes_everything_when_allowlist_empty() -> None:
    """許可リストが空/不明な場合は安全側(除外側)に倒す。"""
    result = build_common_stock_universe(_mixed_listings(), common_stock_market_codes=frozenset())
    assert result.included == ()
    assert len(result.excluded) == 4


def _weekdays(start: date, count: int) -> list[date]:
    days: list[date] = []
    current = start
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def _flat_bars(code: str, days: list[date], price: float) -> list[AdjustedOHLCVBar]:
    return [
        AdjustedOHLCVBar(
            code=code,
            session_date=d,
            open=price,
            high=price + 1,
            low=price - 1,
            close=price,
            volume=1000.0,
            split_adjustment_factor=1.0,
            source="synthetic",
        )
        for d in days
    ]


def test_backtest_engine_stops_generating_signals_after_delisting_via_universe_provider() -> None:
    """universe_providerを渡すと、上場廃止後は銘柄がUniverseから外れ、Price Historyに
    Barが存在していてもSignal自体が評価されなくなることを確認する
    (既存のuniverse_codesのみの経路(universe_provider省略)とは異なる挙動になることも
    合わせて確認する)。"""
    days = _weekdays(date(2024, 1, 4), 200)
    delisting_date = days[100]
    listings = [
        ListingRecord(code="2000", market="0111", listing_date=date(2010, 1, 1), delisting_date=delisting_date),
    ]
    universe_provider = ListingBasedUniverseProvider(listings)

    calendar = TradingCalendar(trading_dates=frozenset(days), range_start=days[0], range_end=days[-1])
    # 常にSignal=Trueを返す(Universeによる除外だけを見たいため)。
    bars = _flat_bars("2000", days, price=1000.0)
    price_history = StaticPriceHistory({"2000": bars})
    benchmark_bars = _flat_bars("TOPIX", days, price=2000.0)
    config = BacktestRunConfig(universe_codes=("2000",), start_session=days[0], end_session=days[-1], holding_period_days=5)

    engine = BacktestEngine()
    metrics_with_universe = engine.run(
        config=config,
        price_history=price_history,
        benchmark_bars=benchmark_bars,
        trading_calendar=calendar,
        signal_fn=lambda bars_: len(bars_) > 0,
        universe_provider=universe_provider,
    )
    metrics_without_universe = engine.run(
        config=config,
        price_history=price_history,
        benchmark_bars=benchmark_bars,
        trading_calendar=calendar,
        signal_fn=lambda bars_: len(bars_) > 0,
    )

    # Universe適用時は上場廃止日以降Signalが発生しないため、廃止日までの営業日数程度で
    # signal_countが頭打ちになる(全期間分のsignal_countより明確に少ない)。
    assert metrics_with_universe.signal_count < metrics_without_universe.signal_count
    assert metrics_with_universe.signal_count <= 101  # delisting_date(days[100])当日まで(0-indexedで101営業日分)
    # 既存の経路(universe_provider省略)は挙動が変わらない(後方互換)。
    assert metrics_without_universe.signal_count == len(days)


def test_universe_provider_as_of_requires_tz_aware_datetime() -> None:
    provider = ListingBasedUniverseProvider(_mixed_listings())
    with pytest.raises(ValueError, match="tz-aware"):
        provider.as_of(datetime(2024, 6, 1))  # tz無し


def test_universe_provider_as_of_uses_session_close_at_for_engine_integration() -> None:
    """BacktestEngineはdecision_atとしてsession_close_at(decision_date)を渡す。
    delisting_date当日のsession_close_atではもう対象外になることを確認する。"""
    listings = [ListingRecord(code="2000", market="0111", listing_date=date(2010, 1, 1), delisting_date=date(2024, 6, 3))]
    provider = ListingBasedUniverseProvider(listings)
    snapshot = provider.as_of(session_close_at(date(2024, 6, 3)))
    assert "2000" not in snapshot.codes
