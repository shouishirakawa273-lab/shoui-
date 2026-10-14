"""DEV-AUTO-02.4(Host-Side Validation Boundary)のRegression Test。

実D0103 Writer Runで、Writer自身のNoninteractive Claude CLI Subprocess
環境がGlobal Python PATHしか見えずruff/mypyを実行できなかった
(pytestは偶然実行できたが、ruff/mypyはできなかった)。本Moduleは
Manifest Validation(`targeted_tests`/`static_checks`)をHost自身
(このTest Moduleが検証する`host_validation.py`)が直接実行する設計を
検証する。実Subprocess(`sys.executable -c ...`/`exit 0`/`exit 1`)を
実際に起動するTestを含む(投資判断・Market Data・実Model呼び出しは
このTest Module・対象Codeのいずれにも存在しない、
`INVESTMENT_LOGIC_CHANGED = NO`)。
"""

from __future__ import annotations

import sys
from pathlib import Path

from scripts.dev_workflow_lib.host_validation import (
    MAX_COMMAND_OUTPUT_CHARS,
    CommandResult,
    ValidationResult,
    find_forbidden_validation_command,
    run_manifest_validation,
)

# ============================================================
# A/B: Host Validationが実際にtargeted_tests/static_checksを実行する
# ============================================================


def test_A_run_manifest_validation_executes_targeted_tests(tmp_path: Path) -> None:
    result = run_manifest_validation(("exit 0",), (), repo_root=tmp_path)

    assert result.blocked_reason is None
    assert len(result.targeted_tests) == 1
    assert result.targeted_tests[0].command == "exit 0"
    assert result.targeted_tests[0].returncode == 0
    assert result.targeted_tests_passed is True
    assert result.static_checks == ()


def test_B_run_manifest_validation_executes_static_checks(tmp_path: Path) -> None:
    result = run_manifest_validation((), ("exit 0",), repo_root=tmp_path)

    assert result.blocked_reason is None
    assert len(result.static_checks) == 1
    assert result.static_checks[0].command == "exit 0"
    assert result.static_checks_passed is True
    assert result.targeted_tests == ()


def test_run_manifest_validation_executes_both_categories_in_order(tmp_path: Path) -> None:
    result = run_manifest_validation(("exit 0",), ("exit 0",), repo_root=tmp_path)

    assert result.passed is True
    assert len(result.targeted_tests) == 1
    assert len(result.static_checks) == 1


def test_run_manifest_validation_uses_repo_root_as_cwd(tmp_path: Path) -> None:
    # DEV-AUTO-02.4 §3: Manifestの`targeted_tests`/`static_checks`が
    # Repository-Relative Path(`.venv\Scripts\...`)を使う前提そのものを
    # 固定する: `repo_root`がCwdとして実際に使われることを、Marker File
    # の存在Checkで確認する。
    (tmp_path / "marker.txt").write_text("x", encoding="utf-8")
    command = f"{sys.executable} -c \"import pathlib,sys; sys.exit(0 if pathlib.Path('marker.txt').exists() else 1)\""

    result = run_manifest_validation((command,), (), repo_root=tmp_path)

    assert result.targeted_tests[0].returncode == 0
    assert result.targeted_tests_passed is True


# ============================================================
# C: 最初の失敗Commandが記録され、後続はShort-Circuitされる
# ============================================================


def test_C_first_failing_command_is_recorded_and_later_commands_are_skipped(tmp_path: Path) -> None:
    result = run_manifest_validation(("exit 1", "exit 0"), (), repo_root=tmp_path)

    assert result.targeted_tests_passed is False
    assert len(result.targeted_tests) == 1  # 2件目("exit 0")はShort-Circuitで未実行。
    assert result.targeted_tests[0].command == "exit 1"
    assert result.targeted_tests[0].returncode == 1
    assert result.passed is False
    assert result.first_failure is not None
    assert result.first_failure.command == "exit 1"


def test_static_checks_short_circuit_independently_of_targeted_tests(tmp_path: Path) -> None:
    result = run_manifest_validation(("exit 0",), ("exit 1", "exit 0"), repo_root=tmp_path)

    assert result.targeted_tests_passed is True
    assert result.static_checks_passed is False
    assert len(result.static_checks) == 1
    assert result.passed is False


def test_empty_command_lists_pass_vacuously(tmp_path: Path) -> None:
    result = run_manifest_validation((), (), repo_root=tmp_path)

    assert result.passed is True
    assert result.targeted_tests_passed is True
    assert result.static_checks_passed is True
    assert result.first_failure is None


# ============================================================
# K: Agent-Providedの任意Commandは一切実行されない
# (Manifestに明示されたCommand文字列のみが実行対象)
# ============================================================


def test_K_only_manifest_supplied_commands_are_ever_executed(tmp_path: Path) -> None:
    # `run_manifest_validation`のSignature自体が`targeted_tests`/
    # `static_checks`という既存Structured Fieldの2引数のみを受け取り、
    # Agent Output・自由記述Prompt等、他のいかなるSourceからもCommandを
    # 受け取らないことを構造的に確認する(LLMは一切関与しない)。
    marker = tmp_path / "should_not_exist.txt"
    result = run_manifest_validation(("exit 0",), ("exit 0",), repo_root=tmp_path)

    assert result.passed is True
    assert not marker.exists()
    for category in (result.targeted_tests, result.static_checks):
        for command_result in category:
            assert command_result.command in ("exit 0",)


def test_find_forbidden_validation_command_detects_git_mutation_verbs() -> None:
    assert find_forbidden_validation_command(("git push origin main",)) == "git push origin main"
    assert find_forbidden_validation_command(("git commit -am x",)) == "git commit -am x"
    assert find_forbidden_validation_command(("git add -A",)) == "git add -A"
    assert find_forbidden_validation_command(("git reset --hard HEAD",)) == "git reset --hard HEAD"
    assert find_forbidden_validation_command(("git clean -fd",)) == "git clean -fd"
    assert find_forbidden_validation_command(("git checkout -- file.py",)) == "git checkout -- file.py"
    assert find_forbidden_validation_command(("git branch -D feature",)) == "git branch -D feature"


def test_find_forbidden_validation_command_allows_safe_read_only_commands() -> None:
    assert find_forbidden_validation_command(("git status --short", "git diff", "git rev-parse HEAD")) is None
    assert find_forbidden_validation_command(("pytest -q", "ruff check foo.py")) is None


def test_run_manifest_validation_blocks_and_executes_nothing_on_forbidden_command(tmp_path: Path) -> None:
    marker = tmp_path / "ran.txt"
    write_marker_command = f"{sys.executable} -c \"open('ran.txt', 'w').close()\""

    result = run_manifest_validation(("git push origin main", write_marker_command), (), repo_root=tmp_path)

    assert result.blocked_reason is not None
    assert "git push origin main" in result.blocked_reason
    assert result.targeted_tests == ()
    assert result.static_checks == ()
    assert result.passed is False
    assert not marker.exists()  # Forbidden Command検出後、後続Commandも一切実行されない。


def test_run_manifest_validation_blocks_when_forbidden_command_is_in_static_checks(tmp_path: Path) -> None:
    result = run_manifest_validation(("exit 0",), ("git reset --hard HEAD",), repo_root=tmp_path)

    assert result.blocked_reason is not None
    assert result.targeted_tests == ()  # targeted_tests側も一切実行されない(両Category共倒れ)。
    assert result.static_checks == ()


# ============================================================
# Timeout / Truncation
# ============================================================


def test_run_manifest_validation_records_timeout(tmp_path: Path) -> None:
    result = run_manifest_validation(
        (f'{sys.executable} -c "import time; time.sleep(5)"',), (), repo_root=tmp_path, timeout_seconds=0.2
    )

    assert result.targeted_tests[0].timed_out is True
    assert result.targeted_tests_passed is False


def test_large_command_output_is_truncated_deterministically_and_flagged(tmp_path: Path) -> None:
    huge_print = f"{sys.executable} -c \"print('x' * {MAX_COMMAND_OUTPUT_CHARS + 5000})\""

    result = run_manifest_validation((huge_print,), (), repo_root=tmp_path)

    command_result = result.targeted_tests[0]
    assert command_result.returncode == 0
    assert len(command_result.stdout) == MAX_COMMAND_OUTPUT_CHARS
    assert command_result.stdout_truncated is True


# ============================================================
# CommandResult / ValidationResult: to_dict/from_dict Round-Trip
# ============================================================


def test_command_result_round_trips_through_dict() -> None:
    original = CommandResult(command="pytest -q", returncode=1, stdout="out", stderr="err", timed_out=False)
    restored = CommandResult.from_dict(original.to_dict())
    assert restored == original


def test_validation_result_round_trips_through_dict() -> None:
    original = ValidationResult(
        targeted_tests=(CommandResult(command="pytest -q", returncode=0, stdout="ok", stderr=""),),
        static_checks=(CommandResult(command="ruff check .", returncode=1, stdout="", stderr="fail"),),
    )
    restored = ValidationResult.from_dict(original.to_dict())
    assert restored.targeted_tests == original.targeted_tests
    assert restored.static_checks == original.static_checks
    assert restored.passed == original.passed


def test_validation_result_no_secret_looking_fields() -> None:
    for field_names in (CommandResult.__dataclass_fields__.keys(), ValidationResult.__dataclass_fields__.keys()):
        for forbidden in ("api_key", "token", "password", "secret"):
            assert forbidden not in field_names
