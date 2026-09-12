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

D0098.1 Root Cause(DECISIONS.md D0098.1参照): D0098時点のFast Gateは
tool_input.file_pathが実際にこのRepository配下かどうかを検証しておらず、
Claude Scratchpad等Repository外の`.py`FileへのEditでもこのRepositoryの
`pyproject.toml`を使ってruffを実行し、Repository外Fileの整形差分だけで
Fast Gateが失敗していた(SCRATCHPAD_FALSE_POSITIVE)。Repository Boundary
Guard(`Path.relative_to()`によるPath Parts単位のMembership Check)を
追加し、Repository外の`.py`Fileは判定不能時と同じFail Open経路(skip)へ
倒すようにした。既存の要件A/D/E/G・H(動的)/JのTestは、この変更後も
実際にFast Gateがruffを起動する経路を検証し続けられるよう、pytestの
`tmp_path`(常にRepository外)ではなく`_repo_local_python_file()`(下記
Helper、Repository配下に実File作成)を使うよう更新した。
"""

from __future__ import annotations

import contextlib
import json
import subprocess
import sys
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HOOK_SCRIPT = _REPO_ROOT / ".claude" / "hooks" / "post_edit_quality_gate.sh"
_SETTINGS = _REPO_ROOT / ".claude" / "settings.json"
_THIS_TEST_DIR = Path(__file__).resolve().parent


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


@contextlib.contextmanager
def _repo_local_python_file(content: str, *, name: str | None = None, suffix: str = ".py") -> Iterator[Path]:
    """D0098.1: Repository Boundary Guardの対象として実際にFast Gateが
    ruffを起動する経路を検証するには、Test対象File自体がこのRepository
    配下に実在している必要がある(pytestの`tmp_path`は常にRepository外
    ——通常OS Temp配下——であり、Boundary Guard導入後は必ずskipされて
    しまうため)。このRepositoryの`13_tests/`配下に一意な名前でFileを
    作成し、Test終了後は成功・失敗いずれでも必ず削除する。"""
    filename = name if name is not None else f"_d0098_1_scratch_{uuid.uuid4().hex}{suffix}"
    target = _THIS_TEST_DIR / filename
    target.write_text(content, encoding="utf-8")
    try:
        yield target
    finally:
        target.unlink(missing_ok=True)


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


def test_fast_gate_resolves_repository_venv_python() -> None:
    """要件A: Repository-local .venv Pythonを選択して実際にruffを起動
    できること(=このRepositoryの実.venvからPythonを解決できている)。
    D0098.1: Boundary Guardを実際に通過させるため、対象FileはRepository
    配下に作成する(`_repo_local_python_file`)。"""
    with _repo_local_python_file("value = 1\n") as target:
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


def test_fast_gate_succeeds_on_valid_changed_python_file() -> None:
    """要件D: 変更FileがValidなPythonであれば、Fast Gateは成功
    (exit 0)すること。D0098.1: Repository配下に実File作成。"""
    with _repo_local_python_file("value = 1\n") as target:
        result = _run_hook({"tool_input": {"file_path": str(target)}})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Fast Gate OK" in result.stdout


def test_fast_gate_propagates_ruff_failure() -> None:
    """要件E: 変更FileがRuffのCheckに違反する場合、非ゼロで伝播すること。
    D0098.1: Repository配下に実File作成(Boundary Guardをすり抜けさせない)。"""
    with _repo_local_python_file("value=1\n") as target:  # E225: missing whitespace
        result = _run_hook({"tool_input": {"file_path": str(target)}})
    assert result.returncode != 0
    assert "Fast Gateに失敗しました" in result.stderr


def test_fast_gate_skips_non_python_files() -> None:
    """要件F: non-Python Fileの編集では、Python Quality Tool(ruff)を
    起動せずにexit 0で即終了すること。D0098.1: Repository配下に実File
    作成し、skip理由が拡張子判定であることを明確にする(Boundary Guard
    による別経路のskipと混同しない)。"""
    with _repo_local_python_file("# note\n", suffix=".md") as target:
        result = _run_hook({"tool_input": {"file_path": str(target)}})
    assert result.returncode == 0
    assert "ruff check" not in result.stdout


def test_fast_gate_script_never_invokes_pytest_or_mypy() -> None:
    """要件G・H: Hook Script自体がpytest/mypyをspawnする経路を持たない
    ことを静的に確認する(Recursion/高負荷の構造的排除)。"""
    content = _HOOK_SCRIPT.read_text(encoding="utf-8")
    assert "-m pytest" not in content, "post_edit_quality_gate.shがpytestを起動しています(D0098違反)"
    assert "-m mypy" not in content, "post_edit_quality_gate.shがmypyを起動しています(D0098違反)"


def test_fast_gate_output_never_reports_pytest_or_mypy_stage() -> None:
    """要件G・H(動的確認): 実際にHookを実行した出力にも
    pytest/mypy Stageのメッセージが一切現れないこと。D0098.1: Boundary
    Guardを通過させ、実際にruff経路を動かした上で確認する。"""
    with _repo_local_python_file("value = 1\n") as target:
        result = _run_hook({"tool_input": {"file_path": str(target)}})
    combined = result.stdout + result.stderr
    assert "[hook] pytest" not in combined
    assert "[hook] mypy" not in combined


def test_fast_gate_script_never_creates_nested_venv() -> None:
    """要件I: Hook Script自体がNested Venvを作成する経路を持たないことを
    静的に確認する。"""
    content = _HOOK_SCRIPT.read_text(encoding="utf-8")
    assert "-m venv" not in content, "post_edit_quality_gate.shがVenvを作成しています(D0098違反)"


def test_fast_gate_handles_unicode_japanese_repository_path() -> None:
    """要件J: 日本語/Unicodeを含むFile Pathでも、Stdin経由のJSON解析・
    File存在確認・ruff起動のいずれも壊れないこと(このRepository自体が
    `C:\\Users\\<日本語ユーザー名>\\...`配下にあるため必須の確認、
    DECISIONS.md D0098参照)。D0098.1: Boundary Guardを通過させるため
    Repository配下(`13_tests/`)に日本語Filenameで実File作成する。"""
    with _repo_local_python_file("value = 1\n", name="日本語ファイル名_d0098.py") as target:
        result = _run_hook({"tool_input": {"file_path": str(target)}})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Fast Gate OK" in result.stdout


# --- D0098.1 Repository Boundary Guard要件 ---------------------------------


def test_boundary_guard_skips_external_scratchpad_style_python_file(tmp_path: Path) -> None:
    """D0098.1要件A: Claude Scratchpad相当(Repository外`scratchpad/`配下)
    の`.py`Fileは、exit 0でskipし、ruff Stageを一切出力しないこと
    (SCRATCHPAD_FALSE_POSITIVEの再発防止)。`tmp_path`は常にRepository外
    ——通常OS Temp配下——であるため、追加の細工なしにRepository外Pathを
    表現できる。"""
    scratchpad_dir = tmp_path / "scratchpad"
    scratchpad_dir.mkdir()
    target = scratchpad_dir / "d0098_1_scratchpad_style.py"
    target.write_text("value = 1\n", encoding="utf-8")
    result = _run_hook({"tool_input": {"file_path": str(target)}})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ruff check" not in result.stdout
    assert "ruff format" not in result.stdout


def test_boundary_guard_skips_external_arbitrary_python_file(tmp_path: Path) -> None:
    """D0098.1要件B: Scratchpad固有の命名でなくとも、Repository外の
    任意の`.py`Fileは同様にexit 0でskipし、ruff Stageを一切出力しない
    こと。"""
    external_dir = tmp_path / "some_external_project"
    external_dir.mkdir()
    target = external_dir / "unrelated_module.py"
    target.write_text("value = 1\n", encoding="utf-8")
    result = _run_hook({"tool_input": {"file_path": str(target)}})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ruff check" not in result.stdout
    assert "ruff format" not in result.stdout


def test_boundary_guard_still_runs_for_repository_local_python_file() -> None:
    """D0098.1要件C: Repository配下の`.py`Fileは、Boundary Guard導入後も
    引き続きFast Gateが実行される(過剰Blockになっていないことの確認、
    要件Dと相補的)。"""
    with _repo_local_python_file("value = 1\n") as target:
        result = _run_hook({"tool_input": {"file_path": str(target)}})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "[hook] ruff check (changed file only)" in result.stdout
    assert "Fast Gate OK" in result.stdout


def test_boundary_guard_rejects_near_prefix_sibling_directory(tmp_path: Path) -> None:
    """D0098.1要件D: `repo_root`に対する素朴な文字列Prefix比較では、
    例えばRepository Root(`.../shoui-`)に対する`.../shoui-other/x.py`の
    ようなNear-Prefix Pathを誤って"内側"と判定しうる。実際のRepository
    RootとFilesystem上で兄弟関係にある(同じ親Directory直下の別名)
    Directoryを動的に作成し、Machine固有Pathを一切Hardcodeせずに
    このCaseを再現する(`Path.relative_to()`はPath Parts単位で比較する
    ため、本来は誤判定しないはずであることを確認する)。"""
    sibling_name = f"{_REPO_ROOT.name}-other-external-{uuid.uuid4().hex[:8]}"
    near_prefix_dir = _REPO_ROOT.parent / sibling_name
    near_prefix_dir.mkdir()
    try:
        target = near_prefix_dir / "x.py"
        target.write_text("value = 1\n", encoding="utf-8")
        result = _run_hook({"tool_input": {"file_path": str(target)}})
        assert result.returncode == 0, result.stdout + result.stderr
        assert "ruff check" not in result.stdout
        assert "ruff format" not in result.stdout
    finally:
        for child in near_prefix_dir.glob("*"):
            child.unlink()
        near_prefix_dir.rmdir()


def test_boundary_guard_skips_external_unicode_path(tmp_path: Path) -> None:
    """D0098.1要件E: Repository外の日本語/Unicodeを含むFile Pathも、
    CrashやHangを起こさず安全にskipされること(Fail Openのまま)。"""
    unicode_external_dir = tmp_path / "日本語スクラッチパッド"
    unicode_external_dir.mkdir()
    target = unicode_external_dir / "日本語外部ファイル.py"
    target.write_text("value = 1\n", encoding="utf-8")
    result = _run_hook({"tool_input": {"file_path": str(target)}})
    assert result.returncode == 0, result.stdout + result.stderr
    assert "ruff check" not in result.stdout
    assert "ruff format" not in result.stdout
