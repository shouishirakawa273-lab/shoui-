"""Phase3A.2(D0035): decision_atごとのPIT-safe Price Adjustmentのテスト。

D0034で判明した問題(全期間共通の事前計算済みAdjusted Seriesを使い回すと、
Walk-Forwardの一部decision_atが未来のCorporate Actionで調整された価格を見てしまう)を
`AsOfAdjustedPriceHistory`(`lib/backtest/price_history.py`)がどう解消するかを確認する。

ユーザー提示の公式例(2024-01-10 C=980 / 2024-01-11 C=480,AdjFactor=0.5(ex-date) /
2024-01-12 C=500)をTest A/B/Cとしてそのまま使う。
"""

from __future__ import annotations

from datetime import date

import pytest
from lib.backtest.engine import BacktestEngine, BacktestRunConfig
from lib.backtest.price_history import AsOfAdjustedPriceHistory, StaticPriceHistory
from lib.data_sources.convert import equity_bars_payload_to_raw_bars, trading_calendar_payload_to_calendar
from lib.market_calendar import session_close_at
from lib.schemas.price_data import CorporateAction, CorporateActionType, RawOHLCVBar, apply_split_adjustments
from lib.strategies.fixed_pipeline_validation import as_buy_signal_fn

_OFFICIAL_RAW_BARS = {
    "7203": [
        RawOHLCVBar(code="7203", session_date=date(2024, 1, 10), open=980.0, high=980.0, low=980.0, close=980.0, volume=1000.0),
        RawOHLCVBar(code="7203", session_date=date(2024, 1, 11), open=480.0, high=480.0, low=480.0, close=480.0, volume=2000.0),
        RawOHLCVBar(code="7203", session_date=date(2024, 1, 12), open=500.0, high=500.0, low=500.0, close=500.0, volume=1500.0),
    ]
}
_OFFICIAL_EVENTS = {
    "7203": [
        CorporateAction(
            code="7203",
            action_type=CorporateActionType.ADJUSTMENT_EVENT,
            effective_date=date(2024, 1, 11),
            raw_adj_factor=0.5,
        )
    ]
}


def _closes(history: AsOfAdjustedPriceHistory, code: str, as_of_date: date) -> dict[date, float | None]:
    bars = history.bars_up_to(code, as_of=session_close_at(as_of_date))
    return {b.session_date: b.close for b in bars}


def test_A_future_split_must_not_affect_earlier_decision() -> None:
    """decision_at=1/10 close時点では、1/11のex-dateはまだ未来なので未使用のまま。"""
    history = AsOfAdjustedPriceHistory(_OFFICIAL_RAW_BARS, _OFFICIAL_EVENTS)
    closes = _closes(history, "7203", date(2024, 1, 10))
    assert closes == {date(2024, 1, 10): pytest.approx(980.0)}


def test_B_split_becomes_usable_after_effective_date() -> None:
    """decision_at=1/11 close以降、1/11のCorporate Actionはeffective済み。"""
    history = AsOfAdjustedPriceHistory(_OFFICIAL_RAW_BARS, _OFFICIAL_EVENTS)
    closes = _closes(history, "7203", date(2024, 1, 11))
    assert closes[date(2024, 1, 10)] == pytest.approx(490.0)
    assert closes[date(2024, 1, 11)] == pytest.approx(480.0)


def test_C_later_date() -> None:
    """decision_at=1/12: 1/10=490, 1/11=480, 1/12=500。"""
    history = AsOfAdjustedPriceHistory(_OFFICIAL_RAW_BARS, _OFFICIAL_EVENTS)
    closes = _closes(history, "7203", date(2024, 1, 12))
    assert closes == {
        date(2024, 1, 10): pytest.approx(490.0),
        date(2024, 1, 11): pytest.approx(480.0),
        date(2024, 1, 12): pytest.approx(500.0),
    }


def test_D_two_sequential_corporate_actions_apply_cumulative_factor_stepwise() -> None:
    """異なる日付にAdjFactorを2件置き、decision_atの進行に応じてcumulative factorが
    段階的に変化すること(1件目のみeffective -> 両方effective)。"""
    raw_bars = {
        "7203": [
            RawOHLCVBar(code="7203", session_date=date(2024, 1, 5), open=1000.0, high=1000.0, low=1000.0, close=1000.0, volume=1),
            RawOHLCVBar(
                code="7203", session_date=date(2024, 1, 11), open=500.0, high=500.0, low=500.0, close=500.0, volume=1
            ),  # ex-date 1(factor=0.5)
            RawOHLCVBar(
                code="7203", session_date=date(2024, 1, 20), open=400.0, high=400.0, low=400.0, close=400.0, volume=1
            ),  # ex-date 2(factor=0.8)
            RawOHLCVBar(code="7203", session_date=date(2024, 1, 25), open=410.0, high=410.0, low=410.0, close=410.0, volume=1),
        ]
    }
    events = {
        "7203": [
            CorporateAction(
                code="7203",
                action_type=CorporateActionType.ADJUSTMENT_EVENT,
                effective_date=date(2024, 1, 11),
                raw_adj_factor=0.5,
            ),
            CorporateAction(
                code="7203",
                action_type=CorporateActionType.ADJUSTMENT_EVENT,
                effective_date=date(2024, 1, 20),
                raw_adj_factor=0.8,
            ),
        ]
    }
    history = AsOfAdjustedPriceHistory(raw_bars, events)

    # 両方のex-dateより前: 無調整。
    before_both = _closes(history, "7203", date(2024, 1, 10))
    assert before_both[date(2024, 1, 5)] == pytest.approx(1000.0)

    # 1件目のみeffective(1/11 close以降、1/20より前): 0.5のみ累積。
    between = _closes(history, "7203", date(2024, 1, 19))
    assert between[date(2024, 1, 5)] == pytest.approx(1000.0 * 0.5)
    assert between[date(2024, 1, 11)] == pytest.approx(500.0)  # ex-date当日は無調整

    # 両方effective(1/20 close以降): 0.5 * 0.8が1/5に、0.8が1/11に累積。
    after_both = _closes(history, "7203", date(2024, 1, 20))
    assert after_both[date(2024, 1, 5)] == pytest.approx(1000.0 * 0.5 * 0.8)
    assert after_both[date(2024, 1, 11)] == pytest.approx(500.0 * 0.8)
    assert after_both[date(2024, 1, 20)] == pytest.approx(400.0)  # 2件目のex-date当日は無調整


def test_E_ticker_isolation() -> None:
    """A社のCorporate ActionがB社のPrice Seriesへ影響しないこと。"""
    raw_bars = {
        "AAAA": _OFFICIAL_RAW_BARS["7203"],
        "BBBB": [
            RawOHLCVBar(code="BBBB", session_date=date(2024, 1, 10), open=100.0, high=100.0, low=100.0, close=100.0, volume=1),
            RawOHLCVBar(code="BBBB", session_date=date(2024, 1, 11), open=101.0, high=101.0, low=101.0, close=101.0, volume=1),
            RawOHLCVBar(code="BBBB", session_date=date(2024, 1, 12), open=102.0, high=102.0, low=102.0, close=102.0, volume=1),
        ],
    }
    events = {"AAAA": _OFFICIAL_EVENTS["7203"], "BBBB": []}
    history = AsOfAdjustedPriceHistory(raw_bars, events)

    as_of = session_close_at(date(2024, 1, 12))
    a_closes = {b.session_date: b.close for b in history.bars_up_to("AAAA", as_of=as_of)}
    b_closes = {b.session_date: b.close for b in history.bars_up_to("BBBB", as_of=as_of)}

    assert a_closes[date(2024, 1, 10)] == pytest.approx(490.0)  # AAAAは分割調整される
    assert b_closes == {date(2024, 1, 10): 100.0, date(2024, 1, 11): 101.0, date(2024, 1, 12): 102.0}  # BBBBは無調整のまま


def _weekdays(start: date, count: int) -> list[date]:
    from datetime import timedelta

    days: list[date] = []
    current = start
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def test_F_full_backtest_momentum_feature_is_continuous_across_mid_period_split() -> None:
    """Corporate ActionがBacktest期間の途中に存在するSynthetic Fixtureを使い、
    split前後でMomentum Featureが経済的に連続した値になること。未来Splitを
    混入させた場合(誤った実装)とは結果が異なることも確認する。"""
    days = _weekdays(date(2024, 1, 4), 150)
    split_day = days[74]  # ちょうど期間の中間あたり

    raw_bars: list[RawOHLCVBar] = []
    for i, d in enumerate(days):
        if d < split_day:
            close = 1000.0 + 2.0 * i  # 分割前: 1日+2の右肩上がり
        elif d == split_day:
            pre_split_trend = 1000.0 + 2.0 * (i - 1)
            close = pre_split_trend * 0.5  # ex-date当日、分割後の水準へ半減
        else:
            days_since_split = i - (days.index(split_day))
            close = (1000.0 + 2.0 * (days.index(split_day) - 1)) * 0.5 + 1.0 * days_since_split  # 分割後も右肩上がり継続
        raw_bars.append(RawOHLCVBar(code="7203", session_date=d, open=close, high=close, low=close, close=close, volume=1000.0))

    events = [
        CorporateAction(
            code="7203", action_type=CorporateActionType.ADJUSTMENT_EVENT, effective_date=split_day, raw_adj_factor=0.5
        )
    ]
    correct_history = AsOfAdjustedPriceHistory({"7203": raw_bars}, {"7203": events})

    # decision_atをsplit_dayの5営業日後に設定し、20営業日Momentum(直近close/20営業日前close-1)を
    # 正しいAs-of Adjusted Seriesで計算する。
    decision_idx = days.index(split_day) + 5
    decision_date = days[decision_idx]
    bars_correct = correct_history.bars_up_to("7203", as_of=session_close_at(decision_date))
    momentum_correct = bars_correct[-1].close / bars_correct[-21].close - 1

    # 右肩上がりが分割前後で連続しているため、Momentumは小さい正の値のはず
    # (Raw価格のまま計算した場合に発生するはずの、分割による見せかけの-50%近い暴落にはならない)。
    assert momentum_correct is not None
    assert -0.1 < momentum_correct < 0.5

    # 反面教師: 「未来のCorporate Actionを含む全期間を単一のas_ofで事前調整してしまう」
    # 旧アーキテクチャに相当する誤った経路(常にrun全体の終端close時点で調整)と比較する。
    # split_dayより前のdecision_atについて、正しい実装(まだ未適用)と、誤った実装
    # (最初から適用済み)とでMomentum/価格が異なることを確認する。
    early_decision_date = days[days.index(split_day) - 10]
    correct_bars_before = correct_history.bars_up_to("7203", as_of=session_close_at(early_decision_date))
    wrong_as_of_end = session_close_at(days[-1])  # 誤り: 常に期間終端のas_ofで事前調整
    wrong_bars_before = correct_history.bars_up_to("7203", as_of=wrong_as_of_end)
    wrong_bars_before_sliced = [b for b in wrong_bars_before if b.session_date <= early_decision_date]

    correct_last_close = correct_bars_before[-1].close
    wrong_last_close = wrong_bars_before_sliced[-1].close
    assert correct_last_close != pytest.approx(wrong_last_close)  # 未来Split混入により値が変わってしまう(誤りの再現)
    assert wrong_last_close == pytest.approx(correct_last_close * 0.5)  # 誤りは「未来のfactorが混入する」形で現れる


def test_G_no_corporate_action_dataset_matches_pre_phase3a2_metrics_exactly() -> None:
    """Corporate Actionが存在しないDatasetでは、StaticPriceHistory経由(Phase3A.1以前
    相当)とAsOfAdjustedPriceHistory(空Events)経由とでBacktestMetricsが完全一致し、
    かつ両者ともPhase3A.1時点で確認済みの既知の値と一致すること(回帰確認)。"""
    from pathlib import Path

    from lib.data_sources.fixture import FixtureDataSourceAdapter

    fixture_path = Path(__file__).resolve().parent / "fixtures" / "synthetic_jquants_v2_bars.json"
    codes = ["7203", "6758", "9984"]
    start, end = date(2026, 1, 5), date(2026, 6, 30)

    adapter = FixtureDataSourceAdapter(fixture_path)
    quotes_result = adapter.fetch_equity_bars(codes=codes, start_date=start, end_date=end)
    calendar_result = adapter.fetch_trading_calendar(start_date=start, end_date=end)
    benchmark_result = adapter.fetch_equity_bars(codes=["TOPIX_SYNTH"], start_date=start, end_date=end)

    raw_bars = equity_bars_payload_to_raw_bars(quotes_result.payload)
    raw_by_code: dict[str, list[RawOHLCVBar]] = {}
    for bar in raw_bars:
        raw_by_code.setdefault(bar.code, []).append(bar)
    benchmark_bars = apply_split_adjustments(equity_bars_payload_to_raw_bars(benchmark_result.payload), [])
    trading_calendar = trading_calendar_payload_to_calendar(calendar_result.payload, range_start=start, range_end=end)

    run_config = BacktestRunConfig(universe_codes=tuple(codes), start_session=start, end_session=end, holding_period_days=60)

    static_history = StaticPriceHistory({code: apply_split_adjustments(bars, []) for code, bars in raw_by_code.items()})
    as_of_history = AsOfAdjustedPriceHistory(raw_by_code, {code: [] for code in codes})  # Corporate Actionなし

    engine = BacktestEngine()
    metrics_static = engine.run(
        config=run_config,
        price_history=static_history,
        benchmark_bars=benchmark_bars,
        trading_calendar=trading_calendar,
        signal_fn=as_buy_signal_fn(),
    )
    metrics_as_of = engine.run(
        config=run_config,
        price_history=as_of_history,
        benchmark_bars=benchmark_bars,
        trading_calendar=trading_calendar,
        signal_fn=as_buy_signal_fn(),
    )

    assert metrics_static == metrics_as_of

    # Phase3A.1で確認済みの既知の値(--source fixtureデモ実行結果)のうち、trade_count・
    # 各tradeのreturnに関わる値は完全一致することを確認する(D0037はExecutionOutcomeの
    # 分類方法のみを変更し、Signal/Executionの判定ロジック自体は変更していないため)。
    assert metrics_static.unique_tickers == 2
    assert metrics_static.trade_count == 2
    assert metrics_static.unique_entry_dates == 1
    assert metrics_static.signal_count == 210
    assert metrics_static.policy_skipped_count == 120
    assert metrics_static.order_attempt_count == 90
    assert metrics_static.executed_count == 2
    assert metrics_static.average_return == pytest.approx(0.03208160645601388)

    # D0037で修正した分類: この合成データ(fixtureの短い期間)ではOUTSIDE_DATA_RANGEの
    # 88件はすべてBacktest期間終了によるRight Censoringであり、真のExecution Failureは
    # 0件だったことが判明した(Phase3A.1時点ではこれを誤ってexecution_failed_countへ
    # 含めていた)。
    assert metrics_static.censored_count == 88
    assert metrics_static.execution_failed_count == 0
    assert metrics_static.eligible_order_attempt_count == 2  # order_attempt_count(90) - censored_count(88)
    assert metrics_static.order_execution_rate == pytest.approx(1.0)  # 評価可能だった2件は両方EXECUTED
