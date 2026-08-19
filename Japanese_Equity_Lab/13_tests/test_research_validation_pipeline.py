"""Phase5 v1 Hypothesis Validation Pipelineの原則ベースTest(VAL-001〜VAL-026)。

実装の詳細(具体的な関数名の内部Logic)ではなく、Phase5 v1 kickoff要件が
明示的に述べた原則(Preregistrationは実行前に固定される・Random Split禁止・
Locked Testは一度しかUnlockできない・Evidence Pathへは接続しない、等)から
期待される振る舞いを検証する。
"""

from __future__ import annotations

from dataclasses import fields
from datetime import date, timedelta
from pathlib import Path

import pytest
from lib.backtest.engine import DataSplit
from lib.backtest.price_history import StaticPriceHistory
from lib.errors import AppendOnlyViolationError, LockedTestAccessError, PreregistrationImmutabilityError
from lib.market_calendar import TradingCalendar
from lib.research.dataset_contract import DatasetContract
from lib.research.locked_test import AccessStage, FileBackedLockedTestGate, LockedTestGate
from lib.research.preregistration import DEFAULT_FORBIDDEN_CAPABILITIES, Preregistration, PreregistrationStatus
from lib.research.registry import PreregistrationRegistry
from lib.research.runner import SplitRunResult, run_split
from lib.schemas.price_data import AdjustedOHLCVBar

_TRAIN_START, _TRAIN_END = date(2015, 1, 5), date(2015, 1, 30)
_VALIDATION_START, _VALIDATION_END = date(2015, 2, 2), date(2015, 2, 27)
_LOCKED_TEST_START, _LOCKED_TEST_END = date(2015, 3, 2), date(2015, 3, 27)


def _weekdays(start: date, end: date) -> list[date]:
    days = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


def _preregistration(**overrides: object) -> Preregistration:
    defaults: dict[str, object] = dict(
        preregistration_id="PREREG_TEST_0001",
        hypothesis_id="H_TEST_0001",
        research_question="短期Reversalは超過リターンを生むか",
        alternative_explanations=(
            "単なる取引コスト以下のノイズである可能性",
            "特定セクター・特定期間への依存(市場全体への一般化不可)である可能性",
        ),
        falsification_condition="Locked Testでexcess_returnが0以下であれば仮説は支持されない",
        dataset_contract_id="DC_TEST_0001",
        universe_definition="Price+PIT Universeのみ(Phase5 v1要件§5)",
        train_period_start=_TRAIN_START,
        train_period_end=_TRAIN_END,
        validation_period_start=_VALIDATION_START,
        validation_period_end=_VALIDATION_END,
        locked_test_period_start=_LOCKED_TEST_START,
        locked_test_period_end=_LOCKED_TEST_END,
        primary_metric="excess_return",
        parameters=(("holding_period_days", "3"),),
    )
    defaults.update(overrides)
    return Preregistration(**defaults)  # type: ignore[arg-type]


def _dataset_contract(**overrides: object) -> DatasetContract:
    defaults: dict[str, object] = dict(
        dataset_contract_id="DC_TEST_0001",
        source="J-Quants (fixture)",
        snapshot_reference="synthetic_jquants_v2_bars.json",
        date_range_start=_TRAIN_START,
        date_range_end=_LOCKED_TEST_END,
        universe_mechanism="lib.universe PIT Universe",
        pit_mechanism="lib.point_in_time.PointInTimeRecord",
        adjustment_method="PIT_AS_OF_ADJFACTOR_V1",
        missing_handling="欠損はUNEXECUTABLE_NO_OPENとして記録しfallbackしない",
        corporate_action_handling="Phase3A PIT-safe AdjFactor調整を再利用",
        delisting_handling="PIT Universeにより上場廃止銘柄も期間内は含める",
        liquidity_availability="Fixtureのため流動性フィルタなし",
        feature_computation="5営業日Trailing Close-to-Close Return",
        target_computation="10営業日Holding、Next Session Open執行",
    )
    defaults.update(overrides)
    return DatasetContract(**defaults)  # type: ignore[arg-type]


def _bars(code: str, days: list[date], *, base: float = 1000.0, step: float = 1.0) -> list[AdjustedOHLCVBar]:
    bars = []
    for i, d in enumerate(days):
        price = base + step * i
        bars.append(
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
        )
    return bars


def _always_buy(_bars: object) -> bool:
    return True


# --- VAL-001: Cannot Run Before Preregistration -----------------------------------------


def test_val001_cannot_run_before_preregistration() -> None:
    draft = _preregistration()
    assert draft.status == PreregistrationStatus.DRAFT
    all_days = _weekdays(_TRAIN_START, _LOCKED_TEST_END)
    calendar = TradingCalendar(trading_dates=frozenset(all_days), range_start=all_days[0], range_end=all_days[-1])
    with pytest.raises(PreregistrationImmutabilityError):
        run_split(
            preregistration=draft,
            dataset_contract_hash=_dataset_contract().contract_hash(),
            split=DataSplit.TRAIN,
            universe_codes=("TESTCODE",),
            price_history=StaticPriceHistory({"TESTCODE": _bars("TESTCODE", all_days)}),
            benchmark_bars=_bars("TOPIX_SYNTH", all_days, base=2000.0, step=0.5),
            trading_calendar=calendar,
            signal_fn=_always_buy,
        )


# --- VAL-002: Core Fields Immutable After PREREGISTERED (tamper detection) ---------------


def test_val002_mutated_core_fields_are_detected_after_preregister() -> None:
    from dataclasses import replace

    preregistered = _preregistration().preregister()
    tampered = replace(preregistered, primary_metric="sharpe_ratio")  # Core Fieldを直接書き換え
    with pytest.raises(PreregistrationImmutabilityError):
        tampered.assert_not_mutated()


def test_val002_unmutated_preregistration_passes_assert() -> None:
    preregistered = _preregistration().preregister()
    preregistered.assert_not_mutated()  # 例外を投げなければOK


# --- VAL-003: Revise Creates New ID With Lineage, Original Untouched ---------------------


def test_val003_revise_creates_new_id_and_preserves_original() -> None:
    preregistered = _preregistration().preregister()
    revised = preregistered.revise(new_preregistration_id="PREREG_TEST_0002", primary_metric="sharpe_ratio")

    assert revised.preregistration_id == "PREREG_TEST_0002"
    assert revised.parent_preregistration_id == preregistered.preregistration_id
    assert revised.status == PreregistrationStatus.DRAFT
    assert revised.primary_metric == "sharpe_ratio"
    # 元のオブジェクトはfrozenであり、reviseの呼び出しでは一切変化しない。
    assert preregistered.primary_metric == "excess_return"
    assert preregistered.status == PreregistrationStatus.PREREGISTERED


def test_val003_revise_rejects_non_core_field_names() -> None:
    preregistered = _preregistration().preregister()
    with pytest.raises(ValueError):
        preregistered.revise(new_preregistration_id="PREREG_TEST_0002", preregistration_id="SHOULD_NOT_BE_ALLOWED")


def test_val003_revise_before_preregister_is_rejected() -> None:
    draft = _preregistration()
    with pytest.raises(PreregistrationImmutabilityError):
        draft.revise(new_preregistration_id="PREREG_TEST_0002")


# --- VAL-004/VAL-005: Chronological Split Enforced (Random Split禁止) --------------------


def test_val004_train_must_end_before_validation_starts() -> None:
    with pytest.raises(ValueError, match="Random Split禁止"):
        _preregistration(validation_period_start=_TRAIN_START, validation_period_end=_TRAIN_END)


def test_val005_validation_must_end_before_locked_test_starts() -> None:
    with pytest.raises(ValueError, match="Random Split禁止"):
        _preregistration(locked_test_period_start=_VALIDATION_START, locked_test_period_end=_VALIDATION_END)


def test_val006_boundary_touching_periods_are_rejected() -> None:
    """Train終了日 == Validation開始日のような境界の重複も禁止する(厳密な時系列分離)。"""
    with pytest.raises(ValueError, match="Random Split禁止"):
        _preregistration(validation_period_start=_TRAIN_END, validation_period_end=_VALIDATION_END)


# --- VAL-007/VAL-008: Preregistration must record falsifiability + alternatives ----------


def test_val007_requires_at_least_two_alternative_explanations() -> None:
    with pytest.raises(ValueError, match="alternative_explanations"):
        _preregistration(alternative_explanations=("単一の説明のみ",))


def test_val008_requires_non_empty_falsification_condition() -> None:
    with pytest.raises(ValueError, match="falsification_condition"):
        _preregistration(falsification_condition="")


# --- VAL-009: Forbidden Capabilities cover the D0061 Phase5 v1 Forbidden Data list -------


def test_val009_default_forbidden_capabilities_exclude_non_price_universe_sources() -> None:
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
        assert capability in DEFAULT_FORBIDDEN_CAPABILITIES
    # Price/Universe自体はForbiddenに含めない(Phase5 v1で唯一使用が許可されたデータ)。
    assert "lib.universe" not in DEFAULT_FORBIDDEN_CAPABILITIES
    assert "lib.backtest" not in DEFAULT_FORBIDDEN_CAPABILITIES


# --- VAL-010/VAL-011: Preregistration Registry is append-only, never overwrites ----------


def test_val010_duplicate_preregistration_id_is_rejected(tmp_path: Path) -> None:
    registry = PreregistrationRegistry(tmp_path / "preregistrations.jsonl")
    preregistered = _preregistration().preregister()
    registry.record(preregistered)
    with pytest.raises(AppendOnlyViolationError):
        registry.record(preregistered)


def test_val011_revised_preregistration_is_recorded_separately_original_unchanged(tmp_path: Path) -> None:
    registry = PreregistrationRegistry(tmp_path / "preregistrations.jsonl")
    original = _preregistration().preregister()
    registry.record(original)
    revised = original.revise(new_preregistration_id="PREREG_TEST_0002", primary_metric="sharpe_ratio").preregister()
    registry.record(revised)

    all_records = registry.all()
    assert len(all_records) == 2
    stored_original = registry.get("PREREG_TEST_0001")
    assert stored_original is not None
    assert stored_original.primary_metric == "excess_return"  # 上書きされていない
    stored_revised = registry.get("PREREG_TEST_0002")
    assert stored_revised is not None
    assert stored_revised.parent_preregistration_id == "PREREG_TEST_0001"


# --- VAL-012/VAL-013: Dataset Contract must be fully explicit and deterministically hashable --


def test_val012_dataset_contract_rejects_empty_required_fields() -> None:
    with pytest.raises(ValueError):
        _dataset_contract(missing_handling="")


def test_val013_dataset_contract_hash_is_deterministic_and_sensitive_to_changes() -> None:
    a = _dataset_contract()
    b = _dataset_contract()
    assert a.contract_hash() == b.contract_hash()

    changed = _dataset_contract(adjustment_method="NONE")
    assert changed.contract_hash() != a.contract_hash()


# --- VAL-014/VAL-015/VAL-016: Locked Test隔離(RESEARCH_RULES.md Hidden Test隔離) ---------


def test_val014_locked_test_cannot_be_accessed_without_unlock() -> None:
    gate = LockedTestGate()
    assert gate.is_unlocked("EXP_TEST_0001") is False
    with pytest.raises(LockedTestAccessError):
        gate.assert_unlocked("EXP_TEST_0001")


def test_val015_unlock_requires_reason_and_actor_and_is_audited() -> None:
    gate = LockedTestGate()
    with pytest.raises(ValueError):
        gate.unlock(experiment_id="EXP_TEST_0001", reason="", actor="researcher")
    with pytest.raises(ValueError):
        gate.unlock(experiment_id="EXP_TEST_0001", reason="Train/Validation完了", actor="")

    record = gate.unlock(experiment_id="EXP_TEST_0001", reason="Train/Validation完了、Final Review準備", actor="researcher")
    assert record.experiment_id == "EXP_TEST_0001"
    assert gate.is_unlocked("EXP_TEST_0001") is True
    assert record in gate.audit_trail()


def test_val016_locked_test_cannot_be_unlocked_twice() -> None:
    gate = LockedTestGate()
    gate.unlock(experiment_id="EXP_TEST_0001", reason="初回Unlock", actor="researcher")
    with pytest.raises(LockedTestAccessError):
        gate.unlock(experiment_id="EXP_TEST_0001", reason="再Unlockしようとしている", actor="researcher")


def test_val016_file_backed_gate_persists_unlock_across_separate_instances(tmp_path: Path) -> None:
    """VerifyLocked Test隔離が単一プロセス内メモリだけの弱いGateではなく、別プロセス
    (別コマンド実行)をまたいでもUnlock済み状態・再Unlock拒否の両方を維持することを
    確認する(このLabのScriptはExperimentごとに別コマンド実行になるため必須)。"""
    storage = tmp_path / "locked_test_audit.jsonl"

    gate1 = FileBackedLockedTestGate(storage)
    assert gate1.is_unlocked("EXP_TEST_0001") is False
    gate1.unlock(experiment_id="EXP_TEST_0001", reason="Train/Validation完了", actor="researcher")

    # 別インスタンス(別プロセスを模す)がファイルからUnlock状態を復元できる。
    gate2 = FileBackedLockedTestGate(storage)
    assert gate2.is_unlocked("EXP_TEST_0001") is True
    gate2.assert_unlocked("EXP_TEST_0001")  # 例外を投げなければOK
    with pytest.raises(LockedTestAccessError):
        gate2.unlock(experiment_id="EXP_TEST_0001", reason="再Unlockしようとしている", actor="researcher")


def test_val016_access_stage_names_match_research_rules_roadmap() -> None:
    """RESEARCH_RULES.mdが既に明記していたAccess段階名と一致させる(用語の分岐を防ぐ)。"""
    assert {stage.value for stage in AccessStage} == {"RESEARCH", "VALIDATION", "LOCKED_TEST", "FUTURE_PAPER_TRADE"}


# --- VAL-017: Runner refuses Locked Test split without Gate/experiment_id ----------------


def test_val017_runner_refuses_locked_test_split_without_gate() -> None:
    preregistered = _preregistration().preregister()
    all_days = _weekdays(_TRAIN_START, _LOCKED_TEST_END)
    calendar = TradingCalendar(trading_dates=frozenset(all_days), range_start=all_days[0], range_end=all_days[-1])
    with pytest.raises(PreregistrationImmutabilityError):
        run_split(
            preregistration=preregistered,
            dataset_contract_hash=_dataset_contract().contract_hash(),
            split=DataSplit.TEST,
            universe_codes=("TESTCODE",),
            price_history=StaticPriceHistory({"TESTCODE": _bars("TESTCODE", all_days)}),
            benchmark_bars=_bars("TOPIX_SYNTH", all_days, base=2000.0, step=0.5),
            trading_calendar=calendar,
            signal_fn=_always_buy,
        )


def test_val017_runner_refuses_locked_test_split_when_not_unlocked() -> None:
    preregistered = _preregistration().preregister()
    all_days = _weekdays(_TRAIN_START, _LOCKED_TEST_END)
    calendar = TradingCalendar(trading_dates=frozenset(all_days), range_start=all_days[0], range_end=all_days[-1])
    gate = LockedTestGate()
    with pytest.raises(LockedTestAccessError):
        run_split(
            preregistration=preregistered,
            dataset_contract_hash=_dataset_contract().contract_hash(),
            split=DataSplit.TEST,
            universe_codes=("TESTCODE",),
            price_history=StaticPriceHistory({"TESTCODE": _bars("TESTCODE", all_days)}),
            benchmark_bars=_bars("TOPIX_SYNTH", all_days, base=2000.0, step=0.5),
            trading_calendar=calendar,
            signal_fn=_always_buy,
            locked_test_gate=gate,
            experiment_id="EXP_TEST_0001",
        )


def test_val017_runner_permits_locked_test_split_once_unlocked() -> None:
    preregistered = _preregistration().preregister()
    all_days = _weekdays(_TRAIN_START, _LOCKED_TEST_END)
    calendar = TradingCalendar(trading_dates=frozenset(all_days), range_start=all_days[0], range_end=all_days[-1])
    gate = LockedTestGate()
    gate.unlock(experiment_id="EXP_TEST_0001", reason="Train/Validation完了", actor="researcher")

    result = run_split(
        preregistration=preregistered,
        dataset_contract_hash=_dataset_contract().contract_hash(),
        split=DataSplit.TEST,
        universe_codes=("TESTCODE",),
        price_history=StaticPriceHistory({"TESTCODE": _bars("TESTCODE", all_days)}),
        benchmark_bars=_bars("TOPIX_SYNTH", all_days, base=2000.0, step=0.5),
        trading_calendar=calendar,
        signal_fn=_always_buy,
        locked_test_gate=gate,
        experiment_id="EXP_TEST_0001",
    )
    assert isinstance(result, SplitRunResult)
    assert result.split == DataSplit.TEST


# --- VAL-018: Runner uses Preregistration-defined periods per split, not arbitrary ranges --


def test_val018_train_split_uses_train_period_only() -> None:
    preregistered = _preregistration().preregister()
    train_days = _weekdays(_TRAIN_START, _TRAIN_END)
    calendar = TradingCalendar(trading_dates=frozenset(train_days), range_start=train_days[0], range_end=train_days[-1])
    # Benchmarkの提供範囲はTrain期間のみ(Validation/Locked Testはカバーしない)。
    result = run_split(
        preregistration=preregistered,
        dataset_contract_hash=_dataset_contract().contract_hash(),
        split=DataSplit.TRAIN,
        universe_codes=("TESTCODE",),
        price_history=StaticPriceHistory({"TESTCODE": _bars("TESTCODE", train_days)}),
        benchmark_bars=_bars("TOPIX_SYNTH", train_days, base=2000.0, step=0.5),
        trading_calendar=calendar,
        signal_fn=_always_buy,
    )
    assert result.metrics.data_split == DataSplit.TRAIN


def test_val018_validation_split_fails_with_train_only_benchmark_data() -> None:
    """VALIDATION splitはPreregistrationのvalidation期間を要求するため、Train期間しか
    カバーしないBenchmarkでは(BacktestEngineの既存Benchmark網羅性チェックにより)失敗する
    -> Runnerがsplitごとに正しい期間を選んでいることの間接証拠。"""
    from lib.backtest.engine import BenchmarkDataInsufficientError

    preregistered = _preregistration().preregister()
    train_days = _weekdays(_TRAIN_START, _TRAIN_END)
    validation_days = _weekdays(_VALIDATION_START, _VALIDATION_END)
    full_calendar_days = train_days + validation_days
    calendar = TradingCalendar(
        trading_dates=frozenset(full_calendar_days), range_start=full_calendar_days[0], range_end=full_calendar_days[-1]
    )
    with pytest.raises(BenchmarkDataInsufficientError):
        run_split(
            preregistration=preregistered,
            dataset_contract_hash=_dataset_contract().contract_hash(),
            split=DataSplit.VALIDATION,
            universe_codes=("TESTCODE",),
            price_history=StaticPriceHistory({"TESTCODE": _bars("TESTCODE", full_calendar_days)}),
            benchmark_bars=_bars("TOPIX_SYNTH", train_days, base=2000.0, step=0.5),  # Train期間のみ
            trading_calendar=calendar,
            signal_fn=_always_buy,
        )


def test_val018_walk_forward_split_is_out_of_scope_for_phase5_v1() -> None:
    preregistered = _preregistration().preregister()
    all_days = _weekdays(_TRAIN_START, _LOCKED_TEST_END)
    calendar = TradingCalendar(trading_dates=frozenset(all_days), range_start=all_days[0], range_end=all_days[-1])
    with pytest.raises(ValueError, match="TRAIN/VALIDATION/TEST"):
        run_split(
            preregistration=preregistered,
            dataset_contract_hash=_dataset_contract().contract_hash(),
            split=DataSplit.WALK_FORWARD,
            universe_codes=("TESTCODE",),
            price_history=StaticPriceHistory({"TESTCODE": _bars("TESTCODE", all_days)}),
            benchmark_bars=_bars("TOPIX_SYNTH", all_days, base=2000.0, step=0.5),
            trading_calendar=calendar,
            signal_fn=_always_buy,
        )


# --- VAL-019: Runner never auto-selects/optimizes parameters -----------------------------


def test_val019_runner_requires_preregistered_holding_period_parameter() -> None:
    preregistered = _preregistration(parameters=()).preregister()  # holding_period_daysを登録しない
    train_days = _weekdays(_TRAIN_START, _TRAIN_END)
    calendar = TradingCalendar(trading_dates=frozenset(train_days), range_start=train_days[0], range_end=train_days[-1])
    with pytest.raises(ValueError, match="holding_period_days"):
        run_split(
            preregistration=preregistered,
            dataset_contract_hash=_dataset_contract().contract_hash(),
            split=DataSplit.TRAIN,
            universe_codes=("TESTCODE",),
            price_history=StaticPriceHistory({"TESTCODE": _bars("TESTCODE", train_days)}),
            benchmark_bars=_bars("TOPIX_SYNTH", train_days, base=2000.0, step=0.5),
            trading_calendar=calendar,
            signal_fn=_always_buy,
        )


# --- VAL-020: No Evidence Path Wiring While D0057 Open (structural) ----------------------


def test_val020_research_modules_never_import_evidence_path() -> None:
    """D0061 Phase5 v1 Forbidden Dataの一つ、`lib.evidence`(filter_usable_at含む)への
    接続をこのRoundでは行わない(Phase5 v1要件§6)。lib/research/配下のソースを直接
    grepし、実際のImport文(from/import)にlib.evidenceが現れないことを構造的に確認
    する(`DEFAULT_FORBIDDEN_CAPABILITIES`のような文字列リテラルとしての言及は許容する
    -- Forbidden Data一覧そのものがこの文字列を保持することは意図的)。"""
    research_dir = Path(__file__).resolve().parent.parent / "lib" / "research"
    assert research_dir.is_dir()
    for path in sorted(research_dir.glob("*.py")):
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith(("import lib.evidence", "from lib.evidence")):
                pytest.fail(f"{path}:{lineno} が lib.evidence をImportしています(D0057未解決、Phase5 v1要件§6)")
        assert "filter_usable_at" not in path.read_text(encoding="utf-8"), (
            f"{path} が filter_usable_at を参照しています(Phase5 v1要件§6)"
        )


# --- VAL-021 (optional): Runner never fetches "current listed universe" implicitly -------


def test_val021_runner_requires_explicit_universe_no_implicit_current_listing_fetch() -> None:
    """RunnerはCallerが渡した`universe_codes`/`universe_provider`のみを使い、内部で
    「現在の上場銘柄一覧」を独自に取得する経路を持たない(Survivorship Bias防止、
    Phase5 v1要件§14)。runner.pyのソースを直接確認する構造Test。"""
    runner_path = Path(__file__).resolve().parent.parent / "lib" / "research" / "runner.py"
    content = runner_path.read_text(encoding="utf-8")
    assert "requests" not in content
    assert "JQuantsAdapter" not in content


# --- VAL-024 (optional): Post-Locked-Test parameter change requires a brand-new Experiment --


def test_val024_no_in_place_mutation_path_exists_only_revise_produces_new_experiment() -> None:
    """パラメータ変更(例: holding_period_daysの変更)は、PREREGISTERED後のPreregistration
    を直接書き換える経路が存在せず、`revise()`で新しいIDを発行する以外に方法がない
    -> Post-Locked-Test含め、パラメータ変更は常に「新しいExperiment」を意味する
    (Phase5 v1要件§51禁止事項)。"""
    import dataclasses

    preregistered = _preregistration().preregister()
    with pytest.raises(dataclasses.FrozenInstanceError):
        preregistered.parameters = (("holding_period_days", "999"),)  # type: ignore[misc]

    revised = preregistered.revise(new_preregistration_id="PREREG_TEST_0002", parameters=(("holding_period_days", "999"),))
    assert revised.parameters == (("holding_period_days", "999"),)
    assert preregistered.parameters == (("holding_period_days", "3"),)  # 元は不変
    assert revised.preregistration_id != preregistered.preregistration_id


# --- VAL-025 (optional): Registry never exposes a delete/overwrite API -------------------


def test_val025_preregistration_registry_exposes_no_delete_or_update_method() -> None:
    public_methods = {name for name in dir(PreregistrationRegistry) if not name.startswith("_")}
    assert "delete" not in public_methods
    assert "update" not in public_methods
    assert "overwrite" not in public_methods


# --- VAL-026 (optional): Result schema never carries a BUY/SELL field --------------------


def test_val026_split_run_result_carries_no_buy_sell_field() -> None:
    field_names = {f.name for f in fields(SplitRunResult)}
    forbidden = {"buy", "sell", "action", "recommendation", "signal_to_act_on"}
    assert field_names.isdisjoint(forbidden)
