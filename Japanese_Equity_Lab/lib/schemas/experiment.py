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
class ReproducibilityFingerprint:
    """同じRaw Snapshot・同じStrategy version・同じConfig・同じCode versionを
    使用した場合に同じBacktest結果になることを検証するための識別子群。

    `code_commit`はコミットIDのみで、working treeが変更されていたかどうかは分からない。
    `git_dirty=True`の場合、`code_commit`が指すコミットの内容と実行時のコード内容が
    完全には一致していない可能性があり、完全な再現性は保証されない。
    """

    run_id: str
    dataset_hash: str  # 使用したRaw Snapshotのcontent_hashから導出
    strategy_hash: str  # Strategyのバージョン識別子(パラメータ+ロジックのhash)
    config_hash: str  # BacktestRunConfig等の実行時設定のhash
    code_commit: str | None = None  # 実行時点のgit commit hash(取得できない場合はNone)
    git_dirty: bool | None = None  # working treeに未コミットの変更があったか(判定不能ならNone)


@dataclass(kw_only=True, frozen=True)
class Experiment(RecordMeta):
    experiment_id: str
    hypothesis_id: str
    strategy_id: str | None
    status: ExperimentStatus
    metrics: BacktestMetrics | None = None
    reproducibility: ReproducibilityFingerprint | None = None
    notes: str = ""
