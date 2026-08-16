"""Phase3C(D0038/D0039): Survivorship Bias / Point-in-Time Universeのテスト。

少数の「上場・上場廃止・非普通株混入」を含む合成Fixtureで、以下を確認する。
- 上場前・上場廃止後の銘柄がdecision_at時点のUniverseへ正しく出入りすること
- Survivorship Biasを解消できていない場合、resolutionがRESOLVEDにならないこと(PARTIAL)
- ETF等(普通株以外)がinstrument_type基準のbuild_common_stock_universe()で
  除外されること(marketだけでは普通株判定に使わないこと、D0039)
- BacktestEngine.run()にuniverse_providerを渡すと、上場廃止後の銘柄が
  Signal自体の対象から外れること(既存の`universe_codes`のみの経路は無変更)
- decision_atごとにMasterを再取得する`PitMasterUniverseProvider`が、確認済み範囲内では
  RESOLVEDを返し、範囲外ではMasterへ問い合わせずPARTIALへ安全側に倒すこと(D0039)

実際のMarketCode/instrument_typeの値・意味はこのセッションでは未検証のため、ここで使う
"0111"等の値は説明用の合成データであり、実データの値そのものではない
(DECISIONS.md D0038/D0039参照)。6502(東芝)の実データ確認(2023-12-19/2023-12-21)自体は
`PitMasterUniverseProvider`のas_of()の動作原理を裏付けるものであり、このテストファイルの
合成データそのものではない。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

import pytest
from lib.backtest.engine import BacktestEngine, BacktestRunConfig
from lib.backtest.price_history import StaticPriceHistory
from lib.market_calendar import TradingCalendar, session_close_at
from lib.schemas.price_data import AdjustedOHLCVBar
from lib.universe import (
    ListingBasedUniverseProvider,
    ListingRecord,
    PitCoverage,
    PitMasterUniverseProvider,
    UniverseResolution,
    build_common_stock_universe,
)

_COMMON_STOCK_INSTRUMENT_TYPES = frozenset({"COMMON_STOCK"})  # 普通株相当(合成、未検証)
_ETF_INSTRUMENT_TYPE = "ETF"  # ETF相当(合成、未検証)


def _mixed_listings() -> list[ListingRecord]:
    return [
        ListingRecord(
            code="1000", market="0111", instrument_type="COMMON_STOCK", company_name="長期上場企業", listing_date=date(2000, 1, 1)
        ),
        ListingRecord(
            code="2000",
            market="0111",
            instrument_type="COMMON_STOCK",
            company_name="年央廃止企業",
            listing_date=date(2010, 1, 1),
            delisting_date=date(2024, 6, 3),
        ),
        ListingRecord(
            code="3000", market="0112", instrument_type="COMMON_STOCK", company_name="年央上場企業", listing_date=date(2024, 7, 1)
        ),
        # marketは普通株(0111)と同じ値にしておく。marketだけでは普通株判定に使えないことの確認(D0039)。
        ListingRecord(
            code="4000",
            market="0111",
            instrument_type=_ETF_INSTRUMENT_TYPE,
            company_name="疑似ETF",
            listing_date=date(2015, 1, 1),
        ),
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


def test_build_common_stock_universe_excludes_non_common_stock_instrument_types() -> None:
    result = build_common_stock_universe(_mixed_listings(), common_stock_instrument_types=_COMMON_STOCK_INSTRUMENT_TYPES)
    included_codes = {listing.code for listing in result.included}
    excluded_codes = {listing.code for listing in result.excluded}
    assert included_codes == {"1000", "2000", "3000"}
    assert excluded_codes == {"4000"}
    assert result.excluded_instrument_types == {_ETF_INSTRUMENT_TYPE: 1}


def test_build_common_stock_universe_excludes_everything_when_allowlist_empty() -> None:
    """許可リストが空/不明な場合は安全側(除外側)に倒す。"""
    result = build_common_stock_universe(_mixed_listings(), common_stock_instrument_types=frozenset())
    assert result.included == ()
    assert len(result.excluded) == 4


def test_build_common_stock_universe_uses_instrument_type_not_market() -> None:
    """marketが普通株群と同じ値でも、instrument_typeがETFなら除外される(D0039)。"""
    result = build_common_stock_universe(_mixed_listings(), common_stock_instrument_types=_COMMON_STOCK_INSTRUMENT_TYPES)
    etf = next(listing for listing in result.excluded if listing.code == "4000")
    common_stock = next(listing for listing in result.included if listing.code == "1000")
    assert etf.market == common_stock.market == "0111"
    assert etf.instrument_type != common_stock.instrument_type


def test_build_common_stock_universe_labels_missing_instrument_type_as_not_available() -> None:
    listings = [ListingRecord(code="5000", market="0111", instrument_type=None)]
    result = build_common_stock_universe(listings, common_stock_instrument_types=_COMMON_STOCK_INSTRUMENT_TYPES)
    assert result.included == ()
    assert result.excluded_instrument_types == {"取得不可": 1}


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


def _pit_fetcher_with_call_log(call_log: list[date]) -> Callable[[date], list[ListingRecord]]:
    """decision_atごとにMasterを再問い合わせしたと仮定した合成fetcher。
    2000は2024-06-03(delisting_date相当)以降のas_ofでは含まれなくなる
    (=真のPIT問い合わせなら、当日のMasterには既に含まれていないはず、D0039)。"""

    def fetcher(as_of_date: date) -> list[ListingRecord]:
        call_log.append(as_of_date)
        listings = [ListingRecord(code="1000", market="0111", instrument_type="COMMON_STOCK", listing_date=date(2000, 1, 1))]
        if as_of_date < date(2024, 6, 3):
            listings.append(
                ListingRecord(code="2000", market="0111", instrument_type="COMMON_STOCK", listing_date=date(2010, 1, 1))
            )
        return listings

    return fetcher


def test_pit_master_provider_resolves_within_confirmed_coverage() -> None:
    """confirmed_coverage内のas_ofでは、その日付でMasterを再取得しRESOLVEDを返す
    (6502実データ確認、DECISIONS.md D0039)。"""
    call_log: list[date] = []
    coverage = PitCoverage(confirmed_from=date(2024, 1, 1), confirmed_until=date(2024, 12, 31))
    provider = PitMasterUniverseProvider(_pit_fetcher_with_call_log(call_log), confirmed_coverage=coverage)

    before = provider.as_of(datetime(2024, 6, 1, tzinfo=UTC))
    after = provider.as_of(datetime(2024, 6, 3, tzinfo=UTC))

    assert before.resolution == UniverseResolution.RESOLVED
    assert after.resolution == UniverseResolution.RESOLVED
    assert "2000" in before.codes
    assert "2000" not in after.codes
    assert before.survivorship_bias_unresolved is False
    assert call_log == [date(2024, 6, 1), date(2024, 6, 3)]


def test_pit_master_provider_falls_back_to_partial_outside_confirmed_coverage_without_fetching() -> None:
    """確認済み範囲外のas_ofでは、Masterへ問い合わせず(不要なAPI呼び出しを避け)安全側のPARTIALに倒す。"""
    call_log: list[date] = []
    coverage = PitCoverage(confirmed_from=date(2024, 1, 1), confirmed_until=date(2024, 12, 31))
    provider = PitMasterUniverseProvider(_pit_fetcher_with_call_log(call_log), confirmed_coverage=coverage)

    snapshot = provider.as_of(datetime(2020, 1, 1, tzinfo=UTC))

    assert snapshot.resolution == UniverseResolution.PARTIAL
    assert snapshot.survivorship_bias_unresolved is True
    assert call_log == []


def test_pit_master_provider_returns_data_unavailable_when_fetcher_returns_empty() -> None:
    coverage = PitCoverage(confirmed_from=date(2024, 1, 1), confirmed_until=date(2024, 12, 31))
    provider = PitMasterUniverseProvider(lambda _d: [], confirmed_coverage=coverage)
    snapshot = provider.as_of(datetime(2024, 6, 1, tzinfo=UTC))
    assert snapshot.resolution == UniverseResolution.DATA_UNAVAILABLE


def test_pit_master_provider_caches_per_date() -> None:
    """同じ日付内であれば、Masterへは1回しか問い合わせない。"""
    call_log: list[date] = []
    coverage = PitCoverage(confirmed_from=date(2024, 1, 1), confirmed_until=date(2024, 12, 31))
    provider = PitMasterUniverseProvider(_pit_fetcher_with_call_log(call_log), confirmed_coverage=coverage)

    provider.as_of(datetime(2024, 6, 1, 9, tzinfo=UTC))
    provider.as_of(datetime(2024, 6, 1, 15, tzinfo=UTC))

    assert call_log == [date(2024, 6, 1)]


def test_pit_master_provider_as_of_requires_tz_aware_datetime() -> None:
    coverage = PitCoverage(confirmed_from=date(2024, 1, 1), confirmed_until=date(2024, 12, 31))
    provider = PitMasterUniverseProvider(lambda _d: [], confirmed_coverage=coverage)
    with pytest.raises(ValueError, match="tz-aware"):
        provider.as_of(datetime(2024, 6, 1))
