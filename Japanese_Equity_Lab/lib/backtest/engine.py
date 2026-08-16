"""Backtest Engineの骨格。

Phase1では実データでの売買シミュレーションは実装しない(Phase2で実施、DECISIONS.md D0003参照)。
ここで実装するのは以下の2点。どちらも外部APIなしでsynthetic dataだけでテストできる。

1. Look-ahead biasを混入させないための入力検証
   (decision_at時点でまだ利用不可能な情報が渡されたら拒否する)
2. 指標計算(sample_size, win_rate, benchmark比較, 年度別/セクター別/銘柄別分布等)

税金はスコープ外とし、ここで扱うリターンは手数料・スリッページ控除後、税引前
(Net Pre-tax Return)である。税引後シミュレーションは将来別モジュールで扱う。
"""

from __future__ import annotations

import statistics
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from lib.point_in_time import PointInTimeRecord, assert_no_lookahead


class DataSplit(StrEnum):
    TRAIN = "TRAIN"
    VALIDATION = "VALIDATION"
    TEST = "TEST"
    WALK_FORWARD = "WALK_FORWARD"


@dataclass(frozen=True)
class DecisionWindow:
    """1回の売買判断における decision_at(判断時刻) と execution_at(執行時刻)。"""

    decision_at: datetime
    execution_at: datetime

    def __post_init__(self) -> None:
        if self.decision_at.tzinfo is None or self.execution_at.tzinfo is None:
            raise ValueError("decision_at / execution_at はtz-awareである必要があります")
        if self.execution_at < self.decision_at:
            raise ValueError("execution_at は decision_at より前にはなりません")


@dataclass(frozen=True)
class SignalInput:
    """1回の意思決定でストラテジーに渡してよい情報の束。

    decision_at時点でavailable_atを過ぎていないレコードが1件でも含まれていたら、
    構築時点で LookAheadBiasError を送出する(黙って除外しない)。
    """

    window: DecisionWindow
    records: tuple[PointInTimeRecord, ...]

    def __post_init__(self) -> None:
        assert_no_lookahead(self.records, self.window.decision_at)


@dataclass(frozen=True)
class TradeResult:
    """1トレードの結果(手数料・スリッページ控除後、税引前)。"""

    code: str
    sector: str | None
    year: int
    net_pretax_return: float


@dataclass(frozen=True)
class BacktestMetrics:
    """RESEARCH_RULES.mdで要求される最低限の表示項目。"""

    data_split: DataSplit
    sample_size: int
    trade_count: int
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
) -> BacktestMetrics:
    """税引前・取引コスト調整後のリターン分布からBacktestMetricsを計算する。"""
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

    return BacktestMetrics(
        data_split=data_split,
        sample_size=len({t.code for t in trades}),
        trade_count=len(trades),
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


class BacktestEngine:
    """Phase2で実データ連携する売買シミュレーションのインターフェース。

    Phase1時点では、decision_at時点で利用可能な情報だけを使ってSignalInputを
    構築するところまでを実装する(build_signal_input)。シグナル生成〜約定の
    シミュレーションループはPhase2で実装する(run)。
    """

    def build_signal_input(self, window: DecisionWindow, records: Iterable[PointInTimeRecord]) -> SignalInput:
        return SignalInput(window=window, records=tuple(records))

    def run(self) -> BacktestMetrics:
        raise NotImplementedError(
            "実データでの売買シミュレーションはPhase2で実装する(DECISIONS.md D0003参照)。"
            "Phase1ではbuild_signal_input()とcompute_metrics()のみ提供する。"
        )
