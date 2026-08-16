from __future__ import annotations

from pathlib import Path

import pytest
from lib.backtest.engine import BacktestMetrics, DataSplit
from lib.errors import AppendOnlyViolationError
from lib.registry.experiment_registry import ExperimentRegistry
from lib.schemas.experiment import Experiment, ExperimentStatus, ReproducibilityFingerprint


def _metrics() -> BacktestMetrics:
    return BacktestMetrics(
        data_split=DataSplit.TEST,
        unique_tickers=10,
        trade_count=15,
        unique_entry_dates=12,
        signal_count=20,
        executed_count=15,
        unexecuted_count=5,
        execution_rate=0.75,
        execution_outcomes={"EXECUTED": 15, "UNEXECUTABLE_NO_OPEN": 5},
        average_return=0.04,
        median_return=0.03,
        win_rate=0.6,
        benchmark_return=0.02,
        excess_return=0.02,
        sector_benchmark_return=0.01,
        sector_excess_return=0.03,
        volatility=0.1,
        max_drawdown=-0.08,
        transaction_cost_adjusted_return=0.035,
        year_by_year_performance={2025: 0.03, 2026: 0.05},
        sector_by_sector_performance={"Auto": 0.04},
        stock_by_stock_distribution={"7203": 0.05},
    )


def test_record_and_read_back_roundtrip(tmp_path: Path) -> None:
    registry = ExperimentRegistry(tmp_path / "experiments.jsonl")
    experiment = Experiment(
        experiment_id="BT0001",
        hypothesis_id="H0001",
        strategy_id="S0001",
        status=ExperimentStatus.TESTED,
        metrics=_metrics(),
    )
    registry.record(experiment)

    loaded = registry.all()
    assert len(loaded) == 1
    assert loaded[0].experiment_id == "BT0001"
    assert loaded[0].metrics is not None
    assert loaded[0].metrics.year_by_year_performance == {2025: 0.03, 2026: 0.05}


def test_record_and_read_back_roundtrip_preserves_reproducibility(tmp_path: Path) -> None:
    registry = ExperimentRegistry(tmp_path / "experiments.jsonl")
    fingerprint = ReproducibilityFingerprint(
        run_id="RUN0001",
        dataset_hash="abc123",
        strategy_hash="def456",
        config_hash="ghi789",
        code_commit="f30d1a9",
        git_dirty=True,
    )
    experiment = Experiment(
        experiment_id="BT0002",
        hypothesis_id="H0001",
        strategy_id="S0001",
        status=ExperimentStatus.TESTED,
        metrics=_metrics(),
        reproducibility=fingerprint,
    )
    registry.record(experiment)

    loaded = registry.all()[0]
    assert loaded.reproducibility == fingerprint


def test_duplicate_experiment_id_is_rejected(tmp_path: Path) -> None:
    registry = ExperimentRegistry(tmp_path / "experiments.jsonl")
    experiment = Experiment(experiment_id="BT0001", hypothesis_id="H0001", strategy_id=None, status=ExperimentStatus.GENERATED)
    registry.record(experiment)
    with pytest.raises(AppendOnlyViolationError):
        registry.record(experiment)


def test_summary_reports_denominators_including_zero_counts(tmp_path: Path) -> None:
    registry = ExperimentRegistry(tmp_path / "experiments.jsonl")
    registry.record(
        Experiment(experiment_id="BT0001", hypothesis_id="H0001", strategy_id=None, status=ExperimentStatus.GENERATED)
    )
    registry.record(Experiment(experiment_id="BT0002", hypothesis_id="H0002", strategy_id=None, status=ExperimentStatus.REJECTED))
    registry.record(Experiment(experiment_id="BT0003", hypothesis_id="H0003", strategy_id=None, status=ExperimentStatus.REJECTED))

    summary = registry.summary()
    assert summary["GENERATED"] == 1
    assert summary["REJECTED"] == 2
    assert summary["VALIDATED"] == 0  # 存在しない状態も0として分母に含まれる
