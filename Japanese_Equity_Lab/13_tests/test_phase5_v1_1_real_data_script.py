"""Phase5 v1.1 H0001-R1 Real-Data Scriptの原則ベースTest(REALVAL-001〜010)。

`scripts/phase5_v1_1_h0001_real_data.py`はこのセッションが実行できない
(EGRESS_BLOCKED、DECISIONS.md参照)ため、実際のJ-Quants通信は一切行わず、
`JQuantsAdapter`のDependency Injection Point(`session`/`adapter`引数、
既存`test_data_sources.py`と同じPattern)を使ってテストする。

以下は既存の共通Mechanism(`lib.research.runner.run_split`の
`SplitBoundaryLeakageError`、`lib.research.locked_test.
FileBackedLockedTestGate`、`lib.backtest.engine`のMissing Bar処理)を
そのまま再利用しており、Phase5 v1側(`test_research_validation_
pipeline.py`のVAL-014〜018/027)で既に検証済みのため、このFileでは
重複させない:
- REALVAL-004(Split Loader Cannot Read Future Split Prices)
  相当は`run_split()`のVAL-027が既にCoverする。
- REALVAL-005(Missing Bars Not Zero-filled)相当は既存
  `lib.backtest.engine`のTestが既にCoverする。
- REALVAL-008(Locked Test One-Time Rule Preserved)相当は
  `FileBackedLockedTestGate`のVAL-016が既にCoverする(このScriptは
  同じClassを`locked_test_audit_real.jsonl`という別Fileで使うのみ)。
"""

from __future__ import annotations

import importlib.util
import inspect
from datetime import UTC, date, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from lib.data_sources.base import RawFetchResult
from lib.research.preregistration import Preregistration, PreregistrationStatus
from lib.research.registry import PreregistrationRegistry

_SCRIPT_PATH = Path(__file__).resolve().parent.parent.parent / "scripts" / "phase5_v1_1_h0001_real_data.py"


def _load_script_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("phase5_v1_1_h0001_real_data", _SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def script() -> ModuleType:
    return _load_script_module()


class _FakeAdapter:
    """`JQuantsAdapter`と同じMethod名を持つ、実通信をしないTest用のFake。"""

    def __init__(self) -> None:
        self.equity_bars_payload: list[dict[str, Any]] = [
            {
                "Code": "7203",
                "Date": "2024-01-04",
                "O": 2000.0,
                "H": 2010.0,
                "L": 1990.0,
                "C": 2005.0,
                "Vo": 1000,
                "AdjFactor": 1.0,
            },
            {
                "Code": "7203",
                "Date": "2024-01-05",
                "O": None,
                "H": None,
                "L": None,
                "C": 2015.0,
                "Vo": 900,
                "AdjFactor": 1.0,
            },
            {
                "Code": "6758",
                "Date": "2024-01-04",
                "O": 3000.0,
                "H": 3010.0,
                "L": 2990.0,
                "C": 3005.0,
                "Vo": 500,
                "AdjFactor": 1.0,
            },
        ]
        self.calendar_payload = [{"Date": "2024-01-04", "HolDiv": "1"}, {"Date": "2024-01-05", "HolDiv": "1"}]
        self.topix_payload = [
            {"Code": "TOPIX", "Date": "2024-01-04", "O": 2500.0, "H": 2510.0, "L": 2490.0, "C": 2505.0, "Vo": 500000},
            {"Code": "TOPIX", "Date": "2024-01-05", "O": 2505.0, "H": 2515.0, "L": 2495.0, "C": 2510.0, "Vo": 510000},
        ]
        self.master_payload = [
            {"Code": "7203", "CompanyName": "Toyota", "Mkt": "0111", "ListingDate": "1949-05-16", "DelistingDate": ""},
            {"Code": "6758", "CompanyName": "Sony", "Mkt": "0111", "ListingDate": "1958-12-01", "DelistingDate": ""},
        ]

    def _result(self, endpoint: str, payload: list[dict[str, Any]]) -> RawFetchResult:
        return RawFetchResult(
            source="jquants",
            endpoint=endpoint,
            request_parameters={},
            retrieved_at=datetime.now(UTC),
            data_period="2024-01-04/2024-01-05",
            response_schema_version="test-fake",
            payload=payload,
        )

    def fetch_equity_bars(self, *, codes: list[str], start_date: date, end_date: date) -> RawFetchResult:
        return self._result("/v2/equities/bars/daily", self.equity_bars_payload)

    def fetch_trading_calendar(self, *, start_date: date, end_date: date) -> RawFetchResult:
        return self._result("/v2/markets/calendar", self.calendar_payload)

    def fetch_topix_bars(self, *, start_date: date, end_date: date) -> RawFetchResult:
        return self._result("/v2/indices/bars/daily/topix", self.topix_payload)

    def fetch_equities_master(self) -> RawFetchResult:
        return self._result("/v2/equities/master", self.master_payload)


# --- REALVAL-002: Synthetic Benchmark Forbidden In Real Run (structural) -----------------


def test_realval002_script_never_imports_fixture_adapter_or_synthetic_benchmark() -> None:
    source = _SCRIPT_PATH.read_text(encoding="utf-8")
    assert "FixtureDataSourceAdapter" not in source
    assert "TOPIX_SYNTH" not in source


# --- REALVAL-003: Result Inspection Cannot Precede Preregistration ------------------------


def test_realval003_coverage_check_never_calls_strategy_or_backtest_engine_source(script: ModuleType) -> None:
    body = inspect.getsource(script.step_coverage_check)
    assert "run_split(" not in body
    assert "BacktestEngine" not in body
    assert "as_buy_signal_fn(" not in body
    assert "five_day_reversal_signal(" not in body


def test_realval003_coverage_check_runs_without_invoking_backtest_engine(
    script: ModuleType, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`BacktestEngine.run`が呼ばれたら即失敗する形にしてから、Coverage Checkが
    それでも正常終了することを確認する(構造検証だけでなく実行時にも保証する)。"""
    from lib.backtest.engine import BacktestEngine

    def _fail_if_called(*args: object, **kwargs: object) -> None:
        raise AssertionError("step_coverage_check() が BacktestEngine.run() を呼び出した(Result Inspection違反)")

    monkeypatch.setattr(BacktestEngine, "run", _fail_if_called)

    script.step_coverage_check(codes=("7203", "6758"), start=date(2024, 1, 4), end=date(2024, 1, 5), adapter=_FakeAdapter())
    out = capsys.readouterr().out
    assert "Coverage Check" in out
    assert "bar_count=2" in out  # 7203
    assert "missing_open=1" in out  # 2024-01-05 の欠損Bar
    assert "PIT universe as_of=" in out


# --- REALVAL-006: Current Universe Rejected(PIT Universeが実際にrun_splitへ渡される) ------


def test_realval006_run_and_record_passes_universe_provider_to_run_split(script: ModuleType) -> None:
    body = inspect.getsource(script._run_and_record)
    assert "universe_provider=universe_provider" in body
    assert "ListingBasedUniverseProvider" in inspect.getsource(script._load_real_price_data)


# --- REALVAL-007: Forbidden Capability Rejected (structural) ------------------------------


def test_realval007_script_never_imports_forbidden_capabilities() -> None:
    source = _SCRIPT_PATH.read_text(encoding="utf-8")
    for capability in (
        "lib.fundamentals",
        "lib.disclosures",
        "lib.positioning",
        "lib.macro",
        "lib.global_market",
        "lib.news",
        "lib.consensus",
        "lib.evidence",
    ):
        for line in source.splitlines():
            stripped = line.strip()
            assert not stripped.startswith((f"import {capability}", f"from {capability}")), (
                f"{capability} をImportしています(Phase5 v1.1要件§2)"
            )


def test_main_loads_dotenv_before_building_adapter() -> None:
    """`jquants_lab_pipeline.py`/`fetch_jquants_local_snapshot.py`と同じPattern
    (`main()`冒頭で`load_dotenv()`)を踏襲していることを確認する回帰Test。

    これが無いと`.env`のJQUANTS_API_KEYがOS環境変数として未Exportの場合に
    ローカル実行時、原因不明の「JQUANTS_API_KEY が設定されていません」で
    失敗する(このRoundで発見・修正した実際のGap)。
    """
    source = _SCRIPT_PATH.read_text(encoding="utf-8")
    assert "from dotenv import load_dotenv" in source
    main_body = source.split("def main() -> None:")[1]
    assert "load_dotenv()" in main_body.splitlines()[1]


# --- REALVAL-009: Real Run Secrets Not Persisted ------------------------------------------


def test_realval009_script_never_references_api_key_env_var_directly() -> None:
    """`JQuantsAdapter`自身が`JQUANTS_API_KEY`をログ・例外・Snapshotに出さない設計
    (D0031)であり、このScriptもキーを直接読む・出力する経路を持たない。"""
    source = _SCRIPT_PATH.read_text(encoding="utf-8")
    assert "JQUANTS_API_KEY" not in source
    assert "os.environ" not in source


# --- REALVAL-010: Real Experiment Does Not Overwrite Synthetic Experiment -----------------


def test_realval010_ids_distinct_from_synthetic_smoke_run(script: ModuleType) -> None:
    assert script.PREREGISTRATION_ID != script.PARENT_PREREGISTRATION_ID
    assert script.PARENT_PREREGISTRATION_ID == "PREREG0001"
    assert not script.EXPERIMENT_ID.startswith("BT_PHASE5_V1_H0001_SMOKE")


def test_realval010_build_real_preregistration_uses_revise_lineage(script: ModuleType, tmp_path: Path) -> None:
    registry_path = tmp_path / "preregistrations.jsonl"
    parent = Preregistration(
        preregistration_id="PREREG0001",
        hypothesis_id="H0001",
        research_question="短期(5営業日)Trailing Returnが負の銘柄は、その後TOPIX対比で超過リターンを生むか",
        alternative_explanations=(
            "単なる取引コスト以下のノイズである可能性",
            "特定の対象期間・対象銘柄への依存であり、市場全体には一般化できない可能性",
        ),
        falsification_condition="Locked Test期間でexcess_returnが0以下であれば、この仮説は支持されない",
        dataset_contract_id="DC0001_SMOKE_FIXTURE_V1",
        universe_definition="Price + PIT Universeのみ(Smoke Run)",
        train_period_start=date(2026, 1, 5),
        train_period_end=date(2026, 3, 4),
        validation_period_start=date(2026, 3, 5),
        validation_period_end=date(2026, 5, 1),
        locked_test_period_start=date(2026, 5, 5),
        locked_test_period_end=date(2026, 7, 3),
        primary_metric="excess_return",
        benchmark="TOPIX_SYNTH(Smoke Run合成Benchmark)",
        parameters=(("lookback_days", "5"), ("holding_period_days", "10")),
    ).preregister()
    PreregistrationRegistry(registry_path).record(parent)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(script, "_PREREGISTRATION_REGISTRY_PATH", registry_path)
    try:
        revised = script.build_real_preregistration(
            codes=("7203", "6758", "8056", "3626"),
            train_start=date(2015, 1, 5),
            train_end=date(2019, 12, 30),
            validation_start=date(2020, 1, 6),
            validation_end=date(2021, 12, 30),
            locked_test_start=date(2025, 1, 6),
            locked_test_end=date(2025, 12, 30),
        )
    finally:
        monkeypatch.undo()

    assert revised.preregistration_id == "PREREG0001_R1"
    assert revised.parent_preregistration_id == "PREREG0001"
    assert revised.status == PreregistrationStatus.DRAFT  # revise()直後はDRAFT、freezeは呼び出し側の責任
    assert revised.dataset_contract_id == "DC0002_JQUANTS_REAL_V1"
    assert revised.benchmark != parent.benchmark
    assert "TOPIX_SYNTH" not in revised.benchmark
    # Core Ruleは変更されない(Phase5 v1.1要件§6/§22)。
    assert revised.primary_metric == parent.primary_metric
    assert revised.parameters == parent.parameters
    assert revised.falsification_condition == parent.falsification_condition
    assert revised.forbidden_capabilities == parent.forbidden_capabilities
    assert revised.alternative_explanations == parent.alternative_explanations
    assert revised.secondary_metrics == parent.secondary_metrics
    assert revised.allowed_adjustments == parent.allowed_adjustments


def test_pit_audit_medium_fix_run_and_record_persists_universe_resolution_into_notes(
    script: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """pit-auditor MEDIUM Finding対応の回帰Test。

    `UniverseSnapshot.resolution`/`survivorship_bias_unresolved`は
    `BacktestMetrics`へ伝播しない(`lib/backtest/engine.py`確認済み)ため、
    `_run_and_record()`はSplit境界(開始・終了)で`universe_provider.as_of()`
    を呼び、その結果Summaryを`Experiment.notes`へ書き込む。実際に記録された
    `Experiment.notes`にその内容が現れることをEnd-to-Endで確認する
    (`JQuantsAdapter`を`_FakeAdapter`へ差し替え、Registry群をtmp_pathへ退避)。
    """
    registry_path = tmp_path / "preregistrations.jsonl"
    parent = Preregistration(
        preregistration_id="PREREG0001",
        hypothesis_id="H0001",
        research_question="短期(5営業日)Trailing Returnが負の銘柄は、その後TOPIX対比で超過リターンを生むか",
        alternative_explanations=("説明1で最低限の長さを満たす文字列", "説明2で最低限の長さを満たす文字列"),
        falsification_condition="Locked Test期間でexcess_returnが0以下であれば、この仮説は支持されない",
        dataset_contract_id="DC0001_SMOKE_FIXTURE_V1",
        universe_definition="Price + PIT Universeのみ(Smoke Run)",
        train_period_start=date(2026, 1, 5),
        train_period_end=date(2026, 3, 4),
        validation_period_start=date(2026, 3, 5),
        validation_period_end=date(2026, 5, 1),
        locked_test_period_start=date(2026, 5, 5),
        locked_test_period_end=date(2026, 7, 3),
        primary_metric="excess_return",
        parameters=(("lookback_days", "5"), ("holding_period_days", "10")),
    ).preregister()
    PreregistrationRegistry(registry_path).record(parent)

    monkeypatch.setattr(script, "_PREREGISTRATION_REGISTRY_PATH", registry_path)
    monkeypatch.setattr(script, "_EXPERIMENT_REGISTRY_PATH", tmp_path / "experiment_registry.jsonl")
    monkeypatch.setattr(script, "_PROVENANCE_PATH", tmp_path / "provenance.jsonl")
    monkeypatch.setattr(script, "_LAB_DIR", tmp_path)
    monkeypatch.setattr(script, "JQuantsAdapter", _FakeAdapter)

    script.step_preregister(
        codes=("7203", "6758"),
        train_start=date(2024, 1, 4),
        train_end=date(2024, 1, 5),
        validation_start=date(2024, 1, 8),
        validation_end=date(2024, 1, 9),
        locked_test_start=date(2024, 1, 10),
        locked_test_end=date(2024, 1, 11),
    )

    script._run_and_record(script.DataSplit.TRAIN, codes=("7203", "6758"))

    exp_registry = script.ExperimentRegistry(script._EXPERIMENT_REGISTRY_PATH)
    all_experiments = {e.experiment_id: e for e in exp_registry.all()}
    recorded = all_experiments.get(f"{script.EXPERIMENT_ID}_{script.DataSplit.TRAIN.value}")
    assert recorded is not None
    assert "universe_resolution=[" in recorded.notes
    assert "2024-01-04:" in recorded.notes
    assert "2024-01-05:" in recorded.notes


def test_d0065_real_data_period_design_satisfies_chronological_non_overlap(script: ModuleType, tmp_path: Path) -> None:
    """pit-auditor MEDIUM Finding対応の回帰Test。

    `PHASE5_V1_LOCAL_VALIDATION_GUIDE.md`/`DECISIONS.md` D0065で確定し、
    D0066の経緯により`PREREG0001_R1`として実際にFreezeされた実データ
    期間案(Train 2022-01-04〜2023-12-29/Validation 2024-01-04〜
    2024-12-30/Locked Test 2025-01-06〜2025-12-30)そのものを使って
    `build_real_preregistration()`を呼び、`Preregistration.__post_init__`の
    Chronological非重複Checkを実際に通過することを確認する。それまでの
    Lineage Test(`test_realval010_build_real_preregistration_uses_revise_
    lineage`)は`revise()`機構自体の検証が目的で任意の日付を使っており、
    D0065で確定した実際の6つの日付を組で検証するTestが無かった
    (ドキュメント上の日付をこっそり変えてもTestが検知できないGapだった)。
    """
    registry_path = tmp_path / "preregistrations.jsonl"
    parent = Preregistration(
        preregistration_id="PREREG0001",
        hypothesis_id="H0001",
        research_question="短期(5営業日)Trailing Returnが負の銘柄は、その後TOPIX対比で超過リターンを生むか",
        alternative_explanations=("説明1で最低限の長さを満たす文字列", "説明2で最低限の長さを満たす文字列"),
        falsification_condition="Locked Test期間でexcess_returnが0以下であれば、この仮説は支持されない",
        dataset_contract_id="DC0001_SMOKE_FIXTURE_V1",
        universe_definition="Price + PIT Universeのみ(Smoke Run)",
        train_period_start=date(2026, 1, 5),
        train_period_end=date(2026, 3, 4),
        validation_period_start=date(2026, 3, 5),
        validation_period_end=date(2026, 5, 1),
        locked_test_period_start=date(2026, 5, 5),
        locked_test_period_end=date(2026, 7, 3),
        primary_metric="excess_return",
        parameters=(("lookback_days", "5"), ("holding_period_days", "10")),
    ).preregister()
    PreregistrationRegistry(registry_path).record(parent)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(script, "_PREREGISTRATION_REGISTRY_PATH", registry_path)
    try:
        revised = script.build_real_preregistration(
            codes=("7203", "6758", "8056", "3626"),
            train_start=date(2022, 1, 4),
            train_end=date(2023, 12, 29),
            validation_start=date(2024, 1, 4),
            validation_end=date(2024, 12, 30),
            locked_test_start=date(2025, 1, 6),
            locked_test_end=date(2025, 12, 30),
        )
        frozen = revised.preregister()
    finally:
        monkeypatch.undo()

    assert frozen.status == PreregistrationStatus.PREREGISTERED
    assert frozen.train_period_end < frozen.validation_period_start
    assert frozen.validation_period_end < frozen.locked_test_period_start


def test_realval010_step_preregister_freezes_and_records_without_overwriting_parent(script: ModuleType, tmp_path: Path) -> None:
    registry_path = tmp_path / "preregistrations.jsonl"
    parent = Preregistration(
        preregistration_id="PREREG0001",
        hypothesis_id="H0001",
        research_question="短期(5営業日)Trailing Returnが負の銘柄は、その後TOPIX対比で超過リターンを生むか",
        alternative_explanations=("説明1で最低限の長さを満たす文字列", "説明2で最低限の長さを満たす文字列"),
        falsification_condition="Locked Test期間でexcess_returnが0以下であれば、この仮説は支持されない",
        dataset_contract_id="DC0001_SMOKE_FIXTURE_V1",
        universe_definition="Price + PIT Universeのみ(Smoke Run)",
        train_period_start=date(2026, 1, 5),
        train_period_end=date(2026, 3, 4),
        validation_period_start=date(2026, 3, 5),
        validation_period_end=date(2026, 5, 1),
        locked_test_period_start=date(2026, 5, 5),
        locked_test_period_end=date(2026, 7, 3),
        primary_metric="excess_return",
        parameters=(("lookback_days", "5"), ("holding_period_days", "10")),
    ).preregister()
    PreregistrationRegistry(registry_path).record(parent)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(script, "_PREREGISTRATION_REGISTRY_PATH", registry_path)
    try:
        script.step_preregister(
            codes=("7203",),
            train_start=date(2015, 1, 5),
            train_end=date(2019, 12, 30),
            validation_start=date(2020, 1, 6),
            validation_end=date(2021, 12, 30),
            locked_test_start=date(2025, 1, 6),
            locked_test_end=date(2025, 12, 30),
        )
    finally:
        monkeypatch.undo()

    registry = PreregistrationRegistry(registry_path)
    all_records = registry.all()
    assert len(all_records) == 2  # 親は上書きされず、子が追記される
    unchanged_parent = registry.get("PREREG0001")
    assert unchanged_parent is not None
    assert unchanged_parent.train_period_start == date(2026, 1, 5)  # 親は変化しない
    child = registry.get("PREREG0001_R1")
    assert child is not None
    assert child.status == PreregistrationStatus.PREREGISTERED  # step_preregisterでfreezeされている
