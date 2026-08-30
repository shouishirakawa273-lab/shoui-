"""Protected Path Warning Hook(4A.5.1-6)の回帰Test。

`.claude/hooks/protected_path_warning.sh`はShell Scriptであり、Pythonの
Import/直接呼び出しはできない。したがってこのFileは実際にSubprocessとして
起動し、標準入力へHook Input(JSON)を渡した結果(stdout/stderr/Exit Code)を
確認する(Bash Script自体をBlack Boxとして扱う、Unit Testに近い粒度)。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HOOK_SCRIPT = _REPO_ROOT / ".claude" / "hooks" / "protected_path_warning.sh"


def _run_hook(file_path: str | None) -> subprocess.CompletedProcess[str]:
    payload = {"tool_input": {"file_path": file_path}} if file_path is not None else {}
    return subprocess.run(
        ["bash", str(_HOOK_SCRIPT)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        # D0098: このHookはWarning文へ日本語(UTF-8)を出力する。この環境の
        # `locale.getpreferredencoding()`はWindows日本語Codepage(cp932)で
        # あり、Git Bash側のStdout/StderrバイトストリームはUTF-8であるため、
        # `encoding`未指定だとsubprocessの出力Decode時に`UnicodeDecodeError`
        # になる(DECISIONS.md D0098で実測確認済み)。明示的にUTF-8を指定する。
        encoding="utf-8",
        cwd=_REPO_ROOT,
        timeout=10,
        check=False,
    )


def test_hook_script_exists_and_is_registered_in_settings() -> None:
    assert _HOOK_SCRIPT.exists(), "protected_path_warning.sh が見つかりません"
    settings = json.loads((_REPO_ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    commands = [h["command"] for entry in settings["hooks"]["PostToolUse"] for h in entry["hooks"]]
    assert any("protected_path_warning.sh" in c for c in commands), (
        "protected_path_warning.sh が.claude/settings.jsonのPostToolUse Hookとして登録されていません"
    )


def test_hook_never_blocks_regardless_of_input() -> None:
    """このHookは常にexit 0(Non-blocking Warning、4A.5.1-6の設計判断)。"""
    for file_path in (
        str(_REPO_ROOT / "core" / "models.py"),
        str(_REPO_ROOT / "app.py"),
        str(_REPO_ROOT / "tests" / "test_foo.py"),
        str(_REPO_ROOT / "Japanese_Equity_Lab" / "lib" / "disclosures" / "evidence.py"),
        None,  # 不正な(file_pathが無い)Input
    ):
        result = _run_hook(file_path)
        assert result.returncode == 0, f"file_path={file_path!r} でexit 0以外が返りました: {result.returncode}"


def test_hook_warns_on_protected_screening_tool_paths() -> None:
    for file_path in (
        str(_REPO_ROOT / "core" / "models.py"),
        str(_REPO_ROOT / "app.py"),
        str(_REPO_ROOT / "tests" / "test_foo.py"),
    ):
        result = _run_hook(file_path)
        assert "WARNING" in result.stderr, f"file_path={file_path!r} でWarningが出力されませんでした: {result.stderr!r}"


def test_hook_does_not_warn_on_lab_paths_including_13_tests() -> None:
    """`Japanese_Equity_Lab/13_tests/`は文字列として`tests`を含むが、Root直下の
    `tests/`とは別Pathであり、誤ってWarningを出してはならない(False Positive
    防止の直接確認)。"""
    for file_path in (
        str(_REPO_ROOT / "Japanese_Equity_Lab" / "lib" / "disclosures" / "evidence.py"),
        str(_REPO_ROOT / "Japanese_Equity_Lab" / "13_tests" / "test_pit_principles.py"),
        str(_REPO_ROOT / "Japanese_Equity_Lab" / "DECISIONS.md"),
    ):
        result = _run_hook(file_path)
        assert "WARNING" not in result.stderr, f"file_path={file_path!r} で誤ってWarningが出力されました"


def test_hook_does_not_warn_or_crash_on_missing_file_path() -> None:
    result = _run_hook(None)
    assert result.returncode == 0
    assert "WARNING" not in result.stderr
