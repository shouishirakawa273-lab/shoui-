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
class PriceAdjustmentProvenance:
    """このExperimentのPrice Seriesがどのように調整されたかを追跡する(D0035)。

    `adjustment_method`はバージョン識別子として扱う(例: ``PIT_AS_OF_ADJFACTOR_V1``
    = decision_atごとにPIT-safeなAdjFactor調整を適用、``NONE`` = 無調整)。
    調整方法自体が変わった場合はこの識別子を新しいバージョンへ変更し、過去の
    Experimentの記録はそのまま(上書きせず)残す。
    """

    adjustment_method: str
    as_of_policy: str  # 例: "decision_at" (PIT-safe) / "static" (無調整・調整不要)
    corporate_action_source: str  # 例: "jquants_v2_adjfactor" / "none"
    raw_snapshot_ids: tuple[str, ...] = ()


@dataclass(kw_only=True, frozen=True)
class Experiment(RecordMeta):
    experiment_id: str
    hypothesis_id: str
    strategy_id: str | None
    status: ExperimentStatus
    metrics: BacktestMetrics | None = None
    reproducibility: ReproducibilityFingerprint | None = None
    price_adjustment: PriceAdjustmentProvenance | None = None
    notes: str = ""
    # 将来のAblation比較(例: Fundamental+Momentum+News vs News抜き)のため、この
    # ExperimentがどのDataCapabilityを使用したかを追跡する(D0040)。空タプルは
    # 「未記録」であり「何も使っていない」という意味ではない(既存Experimentとの
    # 後方互換のためdefault=()、Ablation Engine自体はPhase3Dでは実装しない)。
    used_data_capabilities: tuple[str, ...] = ()
    # 2種類のHistorical Research(Market Information Study / Reproducible System
    # Simulation)のどちらの基準でPIT判定したかを追跡する(D0042、
    # `lib.evidence.model.AvailabilitySemantics`の値を文字列で保持)。Noneは
    # 「未記録」(既存Experimentとの後方互換)。
    availability_semantics: str | None = None
