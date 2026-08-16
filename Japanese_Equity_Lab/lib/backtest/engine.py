"""Backtest Engine。

Phase1〜1.1では骨格(指標計算・PIT検証・Close-to-Close防止)のみを実装した
(DECISIONS.md D0003)。Phase2で`BacktestEngine.run()`を実装し、以下を一本の
再現可能なPipelineとして通す。

Data -> Feature -> Signal -> Decision -> Execution -> Position -> Exit/Evaluation
-> Return -> Benchmark Comparison

`run()`は**Portfolio Simulation**(実際に資金を配分する前提のシミュレーション)である。
Event Study(個々のシグナルの前後リターンをoverlapさせたまま統計的に見る分析)とは
目的が異なり、デフォルトの`PositionPolicy.NO_REENTRY_WHILE_POSITION_OPEN`により、
同一銘柄で既にポジションを保有している間に出た追加シグナルは新規建てしない
(RESEARCH_RULES.md「Event StudyとPortfolio Simulationの違い」参照)。

税金はスコープ外とし、ここで扱うリターンは手数料・スリッページ控除後、税引前
(Net Pre-tax Return)である。税引後シミュレーションは将来別モジュールで扱う。
"""

from __future__ import annotations

import statistics
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum

from lib.errors import LookAheadBiasError
from lib.market_calendar import TradingCalendar, TradingCalendarResolutionError, session_close_at, session_open_at
from lib.point_in_time import PointInTimeRecord, assert_no_lookahead
from lib.schemas.price_data import AdjustedOHLCVBar


class DataSplit(StrEnum):
    TRAIN = "TRAIN"
    VALIDATION = "VALIDATION"
    TEST = "TEST"
    WALK_FORWARD = "WALK_FORWARD"


class ExecutionModel(StrEnum):
    """Ver.1のデフォルトは NEXT_SESSION_OPEN。CLOSING_AUCTIONは将来実装(Phase1未対応)。"""

    NEXT_SESSION_OPEN = "NEXT_SESSION_OPEN"
    CLOSING_AUCTION = "CLOSING_AUCTION"


class PositionPolicy(StrEnum):
    """同一銘柄で既にポジションを保有している間に出た追加Signalの扱い。

    NO_REENTRY_WHILE_POSITION_OPEN(デフォルト、かつ現時点で唯一の実装): 保有中は
    追加のシグナルを無視する(ExecutionOutcome.SKIPPED_POSITION_OPEN)。ピラミッディングや
    複数ポジションの重ね持ちはVer.1では行わない。
    """

    NO_REENTRY_WHILE_POSITION_OPEN = "NO_REENTRY_WHILE_POSITION_OPEN"


class ExecutionOutcome(StrEnum):
    """1回のシグナルがどうなったかを必ず記録する(silent skipしない)。"""

    EXECUTED = "EXECUTED"
    UNEXECUTABLE_NO_OPEN = "UNEXECUTABLE_NO_OPEN"  # 執行日のOpenが欠損(entryできない)
    MISSING_PRICE = "MISSING_PRICE"  # entryはできたがexit日の価格が欠損している
    OUTSIDE_DATA_RANGE = "OUTSIDE_DATA_RANGE"  # Trading Calendarの範囲外で執行日/exit日が解決できない
    SKIPPED_POSITION_OPEN = "SKIPPED_POSITION_OPEN"  # 同一銘柄で既にポジション保有中


@dataclass(frozen=True)
class DecisionWindow:
    """1回の売買判断における3つの時刻(すべてtz-aware)。

    information_used_at: シグナル生成に使ってよい情報の締め時刻。Point-in-Timeガードは
        この時刻を基準に行う(build_signal_input参照)。
    decision_at: シグナルを確定した時刻。通常はinformation_used_atと同時刻。
    execution_at: 実際に約定する時刻。

    Ver.1のデフォルトExecution Modelは「当日Closeまでの情報でSignal生成 -> 次営業日Openで約定」。
    decision_atがその日の大引け時刻と一致する場合、同日中の執行(Closing Auction等)は
    このモデルでは禁止する(Close-to-Close Look-ahead防止。将来別Execution Modelとして実装する)。
    """

    information_used_at: datetime
    decision_at: datetime
    execution_at: datetime

    def __post_init__(self) -> None:
        for name, value in (
            ("information_used_at", self.information_used_at),
            ("decision_at", self.decision_at),
            ("execution_at", self.execution_at),
        ):
            if value.tzinfo is None:
                raise ValueError(f"{name} はtz-awareである必要があります")
        if not (self.information_used_at <= self.decision_at < self.execution_at):
            raise ValueError(
                "information_used_at <= decision_at < execution_at である必要があります "
                f"(information_used_at={self.information_used_at.isoformat()}, "
                f"decision_at={self.decision_at.isoformat()}, execution_at={self.execution_at.isoformat()})"
            )
        if self.decision_at == session_close_at(self.decision_at.date()) and self.execution_at.date() <= self.decision_at.date():
            raise LookAheadBiasError(
                "Close-to-Close実行は禁止です。同日Closeの情報で意思決定した場合、"
                "同日中の価格では約定できません(次営業日Open以降のexecution_atを指定してください)。"
                "Closing Auction戦略はExecutionModel.CLOSING_AUCTIONとして将来別途実装します。"
            )


def build_close_to_next_open_window(
    *,
    decision_session_date: date,
    execution_session_date: date,
) -> DecisionWindow:
    """Ver.1のデフォルトExecution Model(NEXT_SESSION_OPEN)のDecisionWindowを構築する。

    当日Closeまでの情報でSignal生成 -> 次営業日Openで約定、というVer.1の既定動作を表す。
    execution_session_dateは呼び出し側が「実際に取引がある次の営業日」を渡すこと
    (Phase1.1時点では祝日・臨時休場カレンダーは未実装。安易にdecision_session_date+1日を
    使うと休場日を約定日にしてしまう恐れがあるため、この関数では自動計算しない)。
    """
    if execution_session_date <= decision_session_date:
        raise LookAheadBiasError(
            "execution_session_date は decision_session_date より後の営業日である必要があります "
            f"(decision_session_date={decision_session_date}, execution_session_date={execution_session_date})"
        )
    decision_at = session_close_at(decision_session_date)
    return DecisionWindow(
        information_used_at=decision_at,
        decision_at=decision_at,
        execution_at=session_open_at(execution_session_date),
    )


@dataclass(frozen=True)
class SignalInput:
    """1回の意思決定でストラテジーに渡してよい情報の束。

    information_used_at時点でavailable_atを過ぎていないレコードが1件でも含まれていたら、
    構築時点で LookAheadBiasError を送出する(黙って除外しない)。available_atは
    「市場で当時利用可能になった日時」であり、Research Labがデータを取得した日時
    (retrieved_at、`lib/data_sources/base.RawFetchResult`参照)とは別物である
    (両者を混同しないことは`lib/point_in_time.py`のdocstring、および
    `13_tests/test_available_at_vs_retrieved_at.py`で確認する)。
    """

    window: DecisionWindow
    records: tuple[PointInTimeRecord, ...]

    def __post_init__(self) -> None:
        assert_no_lookahead(self.records, self.window.information_used_at)


@dataclass(frozen=True)
class TradeResult:
    """1トレードの結果(取引コスト控除前・税引前のgross return)。

    手数料・スリッページは個々のTradeResultには織り込まず、compute_metrics()の
    transaction_cost_bpsで一括して調整する(二重控除を避けるため)。

    holding期間が重なるtrade(同一銘柄で保有期間が被るもの)を統計的に独立な
    サンプルとして扱わないこと(RESEARCH_RULES.md参照)。`BacktestEngine.run()`は
    デフォルトでPositionPolicy.NO_REENTRY_WHILE_POSITION_OPENにより重複を防ぐが、
    compute_metrics()を直接使う場合(Event Study等)は呼び出し側の責任で扱うこと。
    """

    code: str
    sector: str | None
    year: int
    entry_date: date
    net_pretax_return: float


@dataclass(frozen=True)
class BacktestMetrics:
    """RESEARCH_RULES.mdで要求される最低限の表示項目。

    サンプル数に関する用語:
    - signal_count: signal_fnがTrueを返した回数(執行できたかどうかを問わない)。
    - executed_count / trade_count: 実際にトレードとして成立した数(両者は同じ値になる。
      「執行の分母」という文脈ではexecuted_count、既存の「トレード数」という文脈では
      trade_countと呼ぶ)。
    - unexecuted_count: signal_count - executed_count。
    - execution_rate: executed_count / signal_count(signal_count=0の場合はNone)。
    - unique_tickers: 実際にトレードが成立した銘柄のユニーク数(旧sample_size)。
    - unique_entry_dates: 実際の執行(entry)日のユニーク数。trade_countとの差が大きいほど、
      同時期に多くの銘柄へエントリーしている=市場全体のレジームに従属した結果である可能性が
      高いことを示唆する(独立サンプルとみなせるかどうかの目安)。
    - execution_outcomes: ExecutionOutcome別の件数(silent skipしない)。
    """

    data_split: DataSplit
    unique_tickers: int
    trade_count: int
    unique_entry_dates: int
    signal_count: int
    executed_count: int
    unexecuted_count: int
    execution_rate: float | None
    execution_outcomes: dict[str, int]
    average_return: float | None
    median_return: float | None
    win_rate: float | None
    benchmark_return: float | None
    excess_return: float | None
    sector_benchmark_return: float | None
    sector_excess_return: float | None
    volatility: float | None
    max_drawdown: float | None
    transaction_cost_adjusted_return: float | None
    year_by_year_performance: dict[int, float] = field(default_factory=dict)
    sector_by_sector_performance: dict[str, float] = field(default_factory=dict)
    stock_by_stock_distribution: dict[str, float] = field(default_factory=dict)


def compute_metrics(
    trades: Sequence[TradeResult],
    *,
    data_split: DataSplit,
    benchmark_return: float | None = None,
    sector_benchmark_return: float | None = None,
    transaction_cost_bps: float = 0.0,
    signal_count: int = 0,
    execution_outcomes: Mapping[str, int] | None = None,
) -> BacktestMetrics:
    """税引前・取引コスト調整後のリターン分布からBacktestMetricsを計算する。

    signal_count / execution_outcomesを渡さない場合(0件・空のまま)、
    signal_countはtrade_countと無関係の既定値0になり、execution_rateはNoneになる
    (Event Studyのように「シグナルの分母」を追跡しない用途での直接呼び出しを想定)。
    """
    returns = [t.net_pretax_return for t in trades]
    cost = transaction_cost_bps / 10_000
    cost_adjusted = [r - cost for r in returns]

    average_return = statistics.fmean(returns) if returns else None
    median_return = statistics.median(returns) if returns else None
    win_rate = (sum(1 for r in returns if r > 0) / len(returns)) if returns else None
    volatility = statistics.pstdev(returns) if len(returns) >= 2 else None
    transaction_cost_adjusted_return = statistics.fmean(cost_adjusted) if cost_adjusted else None
    max_drawdown = _max_drawdown(cost_adjusted) if cost_adjusted else None

    year_perf: dict[int, list[float]] = {}
    sector_perf: dict[str, list[float]] = {}
    stock_perf: dict[str, list[float]] = {}
    for t in trades:
        year_perf.setdefault(t.year, []).append(t.net_pretax_return)
        if t.sector is not None:
            sector_perf.setdefault(t.sector, []).append(t.net_pretax_return)
        stock_perf.setdefault(t.code, []).append(t.net_pretax_return)

    excess_return = None if average_return is None or benchmark_return is None else average_return - benchmark_return
    sector_excess_return = (
        None if average_return is None or sector_benchmark_return is None else average_return - sector_benchmark_return
    )

    executed_count = len(trades)
    unexecuted_count = max(signal_count - executed_count, 0)
    execution_rate = (executed_count / signal_count) if signal_count > 0 else None

    return BacktestMetrics(
        data_split=data_split,
        unique_tickers=len({t.code for t in trades}),
        trade_count=executed_count,
        unique_entry_dates=len({t.entry_date for t in trades}),
        signal_count=signal_count,
        executed_count=executed_count,
        unexecuted_count=unexecuted_count,
        execution_rate=execution_rate,
        execution_outcomes=dict(execution_outcomes or {}),
        average_return=average_return,
        median_return=median_return,
        win_rate=win_rate,
        benchmark_return=benchmark_return,
        excess_return=excess_return,
        sector_benchmark_return=sector_benchmark_return,
        sector_excess_return=sector_excess_return,
        volatility=volatility,
        max_drawdown=max_drawdown,
        transaction_cost_adjusted_return=transaction_cost_adjusted_return,
        year_by_year_performance={y: statistics.fmean(rs) for y, rs in year_perf.items()},
        sector_by_sector_performance={s: statistics.fmean(rs) for s, rs in sector_perf.items()},
        stock_by_stock_distribution={c: statistics.fmean(rs) for c, rs in stock_perf.items()},
    )


def _max_drawdown(period_returns: Sequence[float]) -> float:
    """リターン系列を順番に複利計算した際の最大ドローダウン。"""
    cumulative = 1.0
    peak = 1.0
    max_dd = 0.0
    for r in period_returns:
        cumulative *= 1 + r
        peak = max(peak, cumulative)
        drawdown = (cumulative - peak) / peak
        max_dd = min(max_dd, drawdown)
    return max_dd


class BenchmarkDataInsufficientError(Exception):
    """Benchmarkデータが要求されたBacktest期間を全区間カバーしていない場合に送出する。"""


@dataclass(frozen=True)
class TransactionCostConfig:
    """Simple Cost Model。commission/slippageは往復(entry+exit)それぞれに掛かる想定。"""

    commission_bps: float = 0.0
    slippage_bps: float = 0.0

    def __post_init__(self) -> None:
        if self.commission_bps < 0 or self.slippage_bps < 0:
            raise ValueError("commission_bps / slippage_bps は0以上である必要があります")

    def round_trip_bps(self) -> float:
        """entry・exitそれぞれにcommission+slippageがかかるため2倍する。"""
        return 2 * (self.commission_bps + self.slippage_bps)


@dataclass(frozen=True)
class BacktestRunConfig:
    """`BacktestEngine.run()`の実行設定。パラメータ最適化を目的とした探索には使わない
    (Pipeline Validation Strategyのパラメータは固定し、変更しない)。"""

    universe_codes: tuple[str, ...]
    start_session: date
    end_session: date
    holding_period_days: int
    transaction_cost: TransactionCostConfig = field(default_factory=TransactionCostConfig)
    data_split: DataSplit = DataSplit.TEST
    position_policy: PositionPolicy = PositionPolicy.NO_REENTRY_WHILE_POSITION_OPEN

    def __post_init__(self) -> None:
        if self.start_session > self.end_session:
            raise ValueError("start_session は end_session 以前である必要があります")
        if self.holding_period_days < 1:
            raise ValueError("holding_period_days は1以上である必要があります")


class BacktestEngine:
    """Signal生成〜Return計算〜Benchmark比較までを通すBacktest Engine(Portfolio Simulation)。

    SignalそのものはEngineの外(`signal_fn`)から与える(SignalとPortfolio Construction/
    Execution Modelを分離する、というRESEARCH_RULES.mdの方針を反映)。

    Event Study(個々のシグナル前後のリターンをoverlap許容で集計する分析)を行いたい場合は、
    `run()`を使わず、`compute_metrics()`を独自に集めたTradeResult列へ直接適用すること。
    その場合overlapping observationsが混入しうる点を必ず明記する(RESEARCH_RULES.md参照)。
    """

    def build_signal_input(self, window: DecisionWindow, records: Iterable[PointInTimeRecord]) -> SignalInput:
        return SignalInput(window=window, records=tuple(records))

    def run(
        self,
        *,
        config: BacktestRunConfig,
        price_history: Mapping[str, Sequence[AdjustedOHLCVBar]],
        benchmark_bars: Sequence[AdjustedOHLCVBar],
        trading_calendar: TradingCalendar,
        signal_fn: Callable[[Sequence[AdjustedOHLCVBar]], bool],
        sector_by_code: dict[str, str] | None = None,
    ) -> BacktestMetrics:
        """Data -> Feature -> Signal -> Decision -> Execution -> Return -> Benchmark比較を実行する。

        1回のシグナルの結末は必ずExecutionOutcomeとして記録する(silent skipしない)。
        価格が欠損している(該当日のbarが無い、またはOpenがNone)場合は、そのトレードを
        MISSING_PRICE / UNEXECUTABLE_NO_OPENとして記録しスキップする(都合の良い価格への
        fallbackはしない)。休場日を執行日にしようとした場合はOUTSIDE_DATA_RANGEとして記録し
        スキップする(勝手に平日扱いしない)。`config.position_policy`が
        NO_REENTRY_WHILE_POSITION_OPEN(既定)の場合、同一銘柄で既にポジションを
        保有している間の追加シグナルはSKIPPED_POSITION_OPENとして記録しスキップする。
        """
        benchmark_dates = {b.session_date for b in benchmark_bars}
        if not benchmark_dates or min(benchmark_dates) > config.start_session or max(benchmark_dates) < config.end_session:
            raise BenchmarkDataInsufficientError(
                f"Benchmarkデータが要求期間({config.start_session}〜{config.end_session})を"
                "全区間カバーしていません。都合の良い期間へ勝手に切り詰めず失敗させます。"
            )
        benchmark_by_date = {b.session_date: b for b in benchmark_bars}

        decision_dates = sorted(d for d in trading_calendar.trading_dates if config.start_session <= d <= config.end_session)

        trades: list[TradeResult] = []
        matched_benchmark_returns: list[float] = []
        signal_count = 0
        outcome_counter: Counter[str] = Counter()

        for code in config.universe_codes:
            bars_for_code = sorted(price_history.get(code, ()), key=lambda b: b.session_date)
            bars_by_date = {b.session_date: b for b in bars_for_code}
            position_open_until: date | None = None  # NO_REENTRY_WHILE_POSITION_OPEN用

            for decision_date in decision_dates:
                bars_up_to_decision = [b for b in bars_for_code if b.session_date <= decision_date]
                if not signal_fn(bars_up_to_decision):
                    continue
                signal_count += 1

                if (
                    config.position_policy == PositionPolicy.NO_REENTRY_WHILE_POSITION_OPEN
                    and position_open_until is not None
                    and decision_date < position_open_until
                ):
                    outcome_counter[ExecutionOutcome.SKIPPED_POSITION_OPEN.value] += 1
                    continue

                try:
                    execution_date = trading_calendar.next_trading_session(decision_date)
                    exit_date = trading_calendar.nth_next_trading_session(execution_date, config.holding_period_days)
                except TradingCalendarResolutionError:
                    outcome_counter[ExecutionOutcome.OUTSIDE_DATA_RANGE.value] += 1
                    continue  # Calendarデータ範囲外 - 都合よく代替せずスキップ

                window = build_close_to_next_open_window(
                    decision_session_date=decision_date, execution_session_date=execution_date
                )
                records = tuple(
                    PointInTimeRecord(
                        value_date=b.session_date,
                        published_at=session_close_at(b.session_date),
                        available_at=session_close_at(b.session_date),
                        label=f"{code} close",
                    )
                    for b in bars_up_to_decision
                )
                self.build_signal_input(window, records)  # PIT違反があればLookAheadBiasErrorで即失敗させる

                entry_bar = bars_by_date.get(execution_date)
                if entry_bar is None or entry_bar.open is None:
                    outcome_counter[ExecutionOutcome.UNEXECUTABLE_NO_OPEN.value] += 1
                    continue  # 価格欠損 - 都合の良い価格へfallbackせずスキップ

                # entryが確定した時点でポジションは保有中とみなす(exit価格の有無に関わらず)。
                position_open_until = exit_date

                exit_bar = bars_by_date.get(exit_date)
                if exit_bar is None or exit_bar.open is None:
                    outcome_counter[ExecutionOutcome.MISSING_PRICE.value] += 1
                    continue  # entryはできたがexit価格が欠損 - fallbackせずスキップ

                outcome_counter[ExecutionOutcome.EXECUTED.value] += 1
                gross_return = exit_bar.open / entry_bar.open - 1
                trades.append(
                    TradeResult(
                        code=code,
                        sector=(sector_by_code or {}).get(code),
                        year=execution_date.year,
                        entry_date=execution_date,
                        net_pretax_return=gross_return,
                    )
                )

                benchmark_entry = benchmark_by_date.get(execution_date)
                benchmark_exit = benchmark_by_date.get(exit_date)
                if (
                    benchmark_entry is not None
                    and benchmark_entry.open is not None
                    and benchmark_exit is not None
                    and benchmark_exit.open is not None
                ):
                    matched_benchmark_returns.append(benchmark_exit.open / benchmark_entry.open - 1)
                # Benchmark側の価格が欠損している場合でも、トレード自体はEXECUTED済みとして扱う
                # (Executionの成否とBenchmark比較可否は別の関心事)。

        benchmark_return = statistics.fmean(matched_benchmark_returns) if matched_benchmark_returns else None
        return compute_metrics(
            trades,
            data_split=config.data_split,
            benchmark_return=benchmark_return,
            transaction_cost_bps=config.transaction_cost.round_trip_bps(),
            signal_count=signal_count,
            execution_outcomes=dict(outcome_counter),
        )
