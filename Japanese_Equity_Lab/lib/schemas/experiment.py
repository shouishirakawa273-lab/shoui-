"""Experiment (Backtest実行1回分の記録) schema。Multiple Testing対策の分母を構成する。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from lib.backtest.engine import BacktestMetrics
from lib.schemas.base import RecordMeta


class ExperimentStatus(StrEnum):
    """generated/tested/rejected/pending/paper/validatedの分母として集計する状態。"""

    GENERATED = "GENERATED"
    PENDING = "PENDING"
    TESTED = "TESTED"
    REJECTED = "REJECTED"
    PAPER = "PAPER"
    VALIDATED = "VALIDATED"


@dataclass(kw_only=True, frozen=True)
class Experiment(RecordMeta):
    experiment_id: str
    hypothesis_id: str
    strategy_id: str | None
    status: ExperimentStatus
    metrics: BacktestMetrics | None = None
    notes: str = ""
