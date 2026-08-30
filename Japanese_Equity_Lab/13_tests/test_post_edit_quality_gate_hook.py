"""Post-Edit Fast Gate Hook(D0098 Layer A)の環境解決・低負荷性Regression Test。

`.claude/hooks/post_edit_quality_gate.sh`はShell Scriptであり、Pythonの
Import/直接呼び出しはできない。したがってこのFileは実際にSubprocessと
して起動し、標準出力/標準エラー出力/Exit Codeを確認する
(`test_protected_path_hook.py`と同じBlack Box方針)。

D0098 Root Cause(DECISIONS.md D0098参照):

1. Hookが`.venv/bin/python`(POSIX Venv Layout)固定でWindows実体
   (`.venv/Scripts/python.exe`)を検出できず、存在しない`python3`へ
   Fallbackしていた結果、Windows App Execution Aliasが解決するToolingを
   一切持たないGlobal Pythonが選ばれていた(Python Resolution)。
2. Post-Edit Hookが毎Edit/Write/MultiEditのたびにRepo全体のruff/format/
   mypyに加えてfull pytest(tests/・Japanese_Equity_Lab/13_tests/の
   全件)まで起動し、さらにpytest内のHook Integration Testsがこの
   Script自身をsubprocessで再起動、その中で再度full pytestが走る構造に
   なっていた——PC Crash / 極端なCPU-RAM-I/O消費の最有力原因
   (Resource Exhaustion)。

D0098でPost-Edit Hookを「Layer A: Fast Fail-Fast Gate」(ruffのみ・
変更Fileのみ・mypy/pytest無し)へ縮小し、Root Cause 1・2いずれも
再発しないことをこのFileで固定する。重量級Integration Test
(Nested Venv作成等)は`@pytest.mark.integration`として残すが、
Post-Edit Hook自体からはpytestが完全に削除されたため、通常Edit経路
からは自然に除外される(marking自体には依存しない、DECISIONS.md
D0098 §3参照)。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HOOK_SCRIPT = _REPO_ROOT / ".claude" / "hooks" / "post_edit_quality_gate.sh"
_SETTINGS = _REPO_ROOT / ".claude" / "settings.json"


def _run_hook(
    payload: dict[str, object] | None,
    *,
    cwd: Path = _REPO_ROOT,
    timeout: int = 30,
) -> subprocess.CompletedProcess[str]:
    input_data = json.dumps(payload) if payload is not None else ""
    return subprocess.run(
        ["bash", str(_HOOK_SCRIPT)],
        input=input_data,
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=cwd,
        timeout=timeout,
        check=False,
    )


def test_hook_script_exists_and_is_registered_in_settings() -> None:
    assert _HOOK_SCRIPT.exists(), "post_edit_quality_gate.sh が見つかりません"
    settings = json.loads(_SETTINGS.read_text(encoding="utf-8"))
    commands = [h["command"] for entry in settings["hooks"]["PostToolUse"] for h in entry["hooks"]]
    assert any("post_edit_quality_gate.sh" in c for c in commands), (
        "post_edit_quality_gate.sh が.claude/settings.jsonのPostToolUse Hookとして登録されていません"
    )


def test_settings_hook_commands_are_invocation_cwd_independent() -> None:
    """D0098 Root Cause(2、Python解決側): settings.jsonのcommandがRelative
    Pathのままだと、起動時cwdがRepository Rootでない場合"No such file or
    directory"になる(実測再現・修正済み)。両Hook Commandがself-locating
    (`git rev-parse --show-toplevel`)されていることを静的に確認する。"""
    settings = json.loads(_SETTINGS.read_text(encoding="utf-8"))
    commands = [h["command"] for entry in settings["hooks"]["PostToolUse"] for h in entry["hooks"]]
    assert len(commands) >= 2
    for command in commands:
        assert "git rev-parse --show-toplevel" in command, f"cwd非依存の解決になっていません: {command!r}"


def test_hook_invocation_command_locates_repo_root_from_subdirectory_cwd() -> None:
    """settings.json実際のCommand文字列を、Repository Root以外のcwdから
    実行しても"No such file or directory"にならないことを確認する
    (Fix後のInvocation Formをそのまま再現)。file_pathを渡さない(空Stdin)
    ため、Fast Gate自体はfile_path未取得でskipし、低負荷のまま完了する。"""
    settings = json.loads(_SETTINGS.read_text(encoding="utf-8"))
    commands = [h["command"] for entry in settings["hooks"]["PostToolUse"] for h in entry["hooks"]]
    quality_gate_command = next(c for c in commands if "post_edit_quality_gate.sh" in c)
    subdir = _REPO_ROOT / "Japanese_Equity_Lab" / "lib"
    result = subprocess.run(
        ["bash", "-c", quality_gate_command],
        input="",
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=subdir,
        timeout=30,
        check=False,
    )
    assert "No such file or directory" not in result.stderr, result.stderr


def test_hook_scripts_do_not_hardcode_username_specific_paths() -> None:
    """要件v1 §10-D: 生成するPath解決Logicへ、日本語/Unicode Username等の
    Machine固有Absolute Pathを埋め込んでいないことを静的に確認する
    (`AppData\\Local`等のUser Profile配下への直書きが無いこと)。

    `C:\\Users\\<日本語ユーザー名>\\...`のような一般化されたPlaceholder例は
    Windowsパス形式を説明するCommentとして許容する(要件が禁止しているのは
    実行時Logicへの**実際の**Machine固有Home Directoryの直書きであり、
    汎化されたExampleそのものではない)。そのため判定は実際の`Path.home()`
    文字列の埋め込み有無で行う。"""
    protected_path_hook = _REPO_ROOT / ".claude" / "hooks" / "protected_path_warning.sh"
    home = str(Path.home())
    for script in (_HOOK_SCRIPT, protected_path_hook):
        content = script.read_text(encoding="utf-8")
        assert "AppData" not in content, f"{script.name} にUser Profile配下のHardcoded Pathが含まれています"
        assert home not in content, f"{script.name} に実際のMachine固有Home Directory({home!r})がHardcodeされています"


def test_hook_fails_closed_when_no_venv_present(tmp_path: Path) -> None:
    """`.venv`自体が存在しないRepositoryでは、Global Pythonへ切り替えず、
    明示的なActionable ErrorでExit非ゼロにすることを確認する(D0098
    Root Cause 1、Global Python Fallback禁止の確認)。"""
    fake_repo = tmp_path / "fake_repo_no_venv"
    fake_repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=fake_repo, check=True, timeout=30)
    hooks_dir = fake_repo / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True)
    hook_copy = hooks_dir / "post_edit_quality_gate.sh"
    hook_copy.write_bytes(_HOOK_SCRIPT.read_bytes())

    result = subprocess.run(
        ["bash", str(hook_copy)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=fake_repo,
        timeout=30,
        check=False,
    )
    assert result.returncode != 0
    assert ".venv" in (result.stdout + result.stderr)


# --- D0098 §8 Layer A Fast Gate要件 A〜J ---------------------------------


def test_fast_gate_resolves_repository_venv_python(tmp_path: Path) -> None:
    """要件A: Repository-local .venv Pythonを選択して実際にruffを起動
    できること(=このRepositoryの実.venvからPythonを解決できている)。"""
    target = tmp_path / "d0098_valid_a.py"
    target.write_text("value = 1\n", encoding="utf-8")
    result = _run_hook({"tool_input": {"file_path": str(target)}})
    combined = result.stdout + result.stderr
    assert "No module named ruff" not in combined, combined
    assert "[hook] ruff check (changed file only)" in result.stdout, combined


def test_fast_gate_never_falls_back_to_global_python(tmp_path: Path) -> None:
    """要件B: .venvが無いRepositoryでは(Global Pythonが実在してもなお)
    fail closedし、Global Pythonのimport成功に起因するTracebackや
    無言成功が起きないこと。"""
    fake_repo = tmp_path / "fake_repo_no_venv_b"
    fake_repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=fake_repo, check=True, timeout=30)
    hooks_dir = fake_repo / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True)
    hook_copy = hooks_dir / "post_edit_quality_gate.sh"
    hook_copy.write_bytes(_HOOK_SCRIPT.read_bytes())

    result = subprocess.run(
        ["bash", str(hook_copy)],
        input=json.dumps({"tool_input": {"file_path": str(fake_repo / "x.py")}}),
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=fake_repo,
        timeout=30,
        check=False,
    )
    combined = result.stdout + result.stderr
    assert result.returncode != 0
    assert "Traceback (most recent call last)" not in combined
    assert ".venv" in combined


@pytest.mark.integration
def test_fast_gate_fails_closed_when_repo_venv_lacks_ruff(tmp_path: Path) -> None:
    """要件C: `.venv`は存在するがruffがInstallされていない場合、Global
    Pythonへ黙ってFallbackせず、Actionable ErrorでExit非ゼロ
    (fail closed)にすること。

    Nested Venv作成を伴うため`@pytest.mark.integration`とし、Post-Edit
    Hook自体はもうpytestを一切呼ばないため、通常Edit経路では実行され
    ない(Layer C: Full Acceptanceでのみ明示実行する、DECISIONS.md
    D0098 §9)。
    """
    fake_repo = tmp_path / "fake_repo_c"
    fake_repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=fake_repo, check=True, timeout=30)

    hooks_dir = fake_repo / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True)
    hook_copy = hooks_dir / "post_edit_quality_gate.sh"
    hook_copy.write_bytes(_HOOK_SCRIPT.read_bytes())

    venv_result = subprocess.run(
        [sys.executable, "-m", "venv", str(fake_repo / ".venv"), "--without-pip"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert venv_result.returncode == 0, f"Nested Venv作成に失敗しました: {venv_result.stderr}"
    fake_python = fake_repo / ".venv" / "Scripts" / "python.exe"
    if not fake_python.exists():
        fake_python = fake_repo / ".venv" / "bin" / "python"
    assert fake_python.exists(), "Nested VenvのPython Interpreterが見つかりません"

    result = subprocess.run(
        ["bash", str(hook_copy)],
        input=json.dumps({"tool_input": {"file_path": str(fake_repo / "x.py")}}),
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=fake_repo,
        timeout=60,
        check=False,
    )
    assert result.returncode != 0, "ruffが欠落したVenvでもHookが成功終了してしまいました(fail closed違反)"
    combined = result.stdout + result.stderr
    assert "ruff" in combined, f"欠落ModuleのActionable Error Messageにruffが含まれていません: {combined!r}"
    assert "Traceback (most recent call last)" not in combined


def test_fast_gate_succeeds_on_valid_changed_python_file(tmp_path: Path) -> None:
    """要件D: 変更FileがValidなPythonであれば、Fast Gateは成功
    (exit 0)すること。"""
    target = tmp_path / "d0098_valid_d.py"
    target.write_text("value = 1\n", encoding="utf-8")
    result = _run_hook({"tool_input": {"file_path": str(target)}})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Fast Gate OK" in result.stdout


def test_fast_gate_propagates_ruff_failure(tmp_path: Path) -> None:
    """要件E: 変更FileがRuffのCheckに違反する場合、非ゼロで伝播すること。"""
    target = tmp_path / "d0098_bad_e.py"
    target.write_text("value=1\n", encoding="utf-8")  # E225: missing whitespace
    result = _run_hook({"tool_input": {"file_path": str(target)}})
    assert result.returncode != 0
    assert "Fast Gateに失敗しました" in result.stderr


def test_fast_gate_skips_non_python_files(tmp_path: Path) -> None:
    """要件F: non-Python Fileの編集では、Python Quality Tool(ruff)を
    起動せずにexit 0で即終了すること。"""
    target = tmp_path / "d0098_notes_f.md"
    target.write_text("# note\n", encoding="utf-8")
    result = _run_hook({"tool_input": {"file_path": str(target)}})
    assert result.returncode == 0
    assert "ruff check" not in result.stdout


def test_fast_gate_script_never_invokes_pytest_or_mypy() -> None:
    """要件G・H: Hook Script自体がpytest/mypyをspawnする経路を持たない
    ことを静的に確認する(Recursion/高負荷の構造的排除)。"""
    content = _HOOK_SCRIPT.read_text(encoding="utf-8")
    assert "-m pytest" not in content, "post_edit_quality_gate.shがpytestを起動しています(D0098違反)"
    assert "-m mypy" not in content, "post_edit_quality_gate.shがmypyを起動しています(D0098違反)"


def test_fast_gate_output_never_reports_pytest_or_mypy_stage(tmp_path: Path) -> None:
    """要件G・H(動的確認): 実際にHookを実行した出力にも
    pytest/mypy Stageのメッセージが一切現れないこと。"""
    target = tmp_path / "d0098_valid_gh.py"
    target.write_text("value = 1\n", encoding="utf-8")
    result = _run_hook({"tool_input": {"file_path": str(target)}})
    combined = result.stdout + result.stderr
    assert "[hook] pytest" not in combined
    assert "[hook] mypy" not in combined


def test_fast_gate_script_never_creates_nested_venv() -> None:
    """要件I: Hook Script自体がNested Venvを作成する経路を持たないことを
    静的に確認する。"""
    content = _HOOK_SCRIPT.read_text(encoding="utf-8")
    assert "-m venv" not in content, "post_edit_quality_gate.shがVenvを作成しています(D0098違反)"


def test_fast_gate_handles_unicode_japanese_repository_path(tmp_path: Path) -> None:
    """要件J: 日本語/Unicodeを含むFile Pathでも、Stdin経由のJSON解析・
    File存在確認・ruff起動のいずれも壊れないこと(このRepository自体が
    `C:\\Users\\<日本語ユーザー名>\\...`配下にあるため必須の確認、
    DECISIONS.md D0098参照)。"""
    unicode_dir = tmp_path / "日本語ディレクトリ"
    unicode_dir.mkdir()
    target = unicode_dir / "日本語ファイル名_d0098.py"
    target.write_text("value = 1\n", encoding="utf-8")
    result = _run_hook({"tool_input": {"file_path": str(target)}})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Fast Gate OK" in result.stdout
