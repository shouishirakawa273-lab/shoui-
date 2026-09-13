"""DEV-AUTO-02.4 §1/§2: Host-Side Validation Boundary。

実D0103 Writer Runで、Writer自身(Agent)が`build_writer_prompt`の指示に
より`manifest.targeted_tests`/`static_checks`を自分のNoninteractive
Claude CLI Subprocess内で実行しようとし、Global Python 3.14 PATH
(Repository-Local`.venv`ではない)しか見えずruff/mypyを実行できなかった
(pytestは偶然PATH上のGlobal Pythonにも入っていたため実行できたが、
ruff/mypyは入っていなかった)。DEV-AUTO-02.3で追加したBash Validation
Permissionは、この種のPermission/PATH不整合を解消する方向ではなく
Agent側のShell権限を広げる方向の対処であり、実際には解決していなかった。

本Moduleは、Manifestに明示されたCommand文字列(`targeted_tests`/
`static_checks`)を**Host自身**(Orchestrator Process、LLM非関与)が
`repo_root`をCwdとして直接実行する。Writer/ReviewerのAgent Subprocess
からは一切実行しない――両Role向けExecutor Configから`python`/`ruff`/
`mypy`のBash Allow-Listを削除しても、Manifest Validation自体は成立する
(DEV-AUTO-02.4 §1)。

Agentが独自に発明したCommandは一切実行しない――実行対象は常に
`TaskManifest.targeted_tests`/`static_checks`という既存のStructured
Fieldのみであり(DEV-AUTO-01からの既存Contract)、本Moduleはそれを
文字列のまま`subprocess`へ渡すだけの薄いLayerである(DEV-AUTO-02.4
§2「No shell command invented by Agent. Only commands already present
in TaskManifest may execute.」)。
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# DEV-AUTO-02.4 §11: Validation Command文字列自体がGit Mutation/
# Human-Gated操作に一致する場合、実行前にDetectしFail Closedする
# (Executeしてから後悔しない)。`human_gate.py`の`_HUMAN_GATED_PATTERNS`
# は"force push"/"reset --hard"等、限定的な言い回しのみを捕捉するため、
# 素の`git push`/`git commit`/`git reset`/`git clean`/Branch削除は
# 別途ここで明示的に禁止する(H0001/Locked Test自体は`human_gate.py`
# 側の`requires_human_approval()`が`targeted_tests`/`static_checks`
# 双方を既にScanしているため、ここでは重複させず、Git Mutation
# Verbのみを扱う)。
_FORBIDDEN_VALIDATION_COMMAND_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bgit\s+push\b", re.IGNORECASE),
    re.compile(r"\bgit\s+commit\b", re.IGNORECASE),
    re.compile(r"\bgit\s+add\b", re.IGNORECASE),
    re.compile(r"\bgit\s+reset\b", re.IGNORECASE),
    re.compile(r"\bgit\s+clean\b", re.IGNORECASE),
    re.compile(r"\bgit\s+checkout\b", re.IGNORECASE),
    re.compile(r"\bgit\s+branch\b", re.IGNORECASE),
)

# DEV-AUTO-02.4 §8: Diagnostics(DEV-AUTO-02.2.2)と同じ設計判断
# (Deterministic Size Bound、無言でのTruncateはしない)。Host Validation
# Commandのstdout/stderrはReviewer Promptへ丸ごと埋め込まれ得るため、
# Agent Execution Diagnosticsとは独立した、より小さいBoundを使う。
MAX_COMMAND_OUTPUT_CHARS = 20_000


def _bounded(text: str, *, max_chars: int = MAX_COMMAND_OUTPUT_CHARS) -> tuple[str, bool]:
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars], True


def find_forbidden_validation_command(commands: tuple[str, ...]) -> str | None:
    """DEV-AUTO-02.4 §11: `commands`(`targeted_tests`または
    `static_checks`)の中にGit Mutation Verbを含むCommandが1件でも
    あれば、その文字列をそのまま返す(なければ`None`)。呼び出し側
    (`orchestrator.py`)はこれを実行前Gateとして扱い、該当すれば
    Validation自体を一切実行せずSTOPする。"""
    for command in commands:
        for pattern in _FORBIDDEN_VALIDATION_COMMAND_PATTERNS:
            if pattern.search(command):
                return command
    return None


@dataclass(kw_only=True, frozen=True)
class CommandResult:
    command: str
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False
    stdout_truncated: bool = False
    stderr_truncated: bool = False

    @property
    def passed(self) -> bool:
        return self.returncode == 0 and not self.timed_out

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": self.command,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "timed_out": self.timed_out,
            "stdout_truncated": self.stdout_truncated,
            "stderr_truncated": self.stderr_truncated,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> CommandResult:
        return CommandResult(
            command=str(data["command"]),
            returncode=int(data["returncode"]),
            stdout=str(data.get("stdout", "")),
            stderr=str(data.get("stderr", "")),
            timed_out=bool(data.get("timed_out", False)),
            stdout_truncated=bool(data.get("stdout_truncated", False)),
            stderr_truncated=bool(data.get("stderr_truncated", False)),
        )


@dataclass(kw_only=True, frozen=True)
class ValidationResult:
    """DEV-AUTO-02.4 §2の`ValidationResult`。`targeted_tests`/
    `static_checks`それぞれについて、実際に実行された`CommandResult`を
    Command配列の順にそのまま保持する(DEV-AUTO-02.4 §2は最初の失敗で
    即Short-Circuitすることを妨げないため、両Category内では最初の
    失敗Commandまでのみが記録され得る――既存`run_targeted_validation`
    と同じFail Closed契約)。"""

    targeted_tests: tuple[CommandResult, ...] = field(default_factory=tuple)
    static_checks: tuple[CommandResult, ...] = field(default_factory=tuple)
    blocked_reason: str | None = None

    @property
    def targeted_tests_passed(self) -> bool:
        return all(r.passed for r in self.targeted_tests) and self.blocked_reason is None

    @property
    def static_checks_passed(self) -> bool:
        return all(r.passed for r in self.static_checks) and self.blocked_reason is None

    @property
    def passed(self) -> bool:
        return self.targeted_tests_passed and self.static_checks_passed

    @property
    def first_failure(self) -> CommandResult | None:
        for result in (*self.targeted_tests, *self.static_checks):
            if not result.passed:
                return result
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "targeted_tests": [r.to_dict() for r in self.targeted_tests],
            "static_checks": [r.to_dict() for r in self.static_checks],
            "blocked_reason": self.blocked_reason,
            "passed": self.passed,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> ValidationResult:
        return ValidationResult(
            targeted_tests=tuple(CommandResult.from_dict(item) for item in data.get("targeted_tests", [])),
            static_checks=tuple(CommandResult.from_dict(item) for item in data.get("static_checks", [])),
            blocked_reason=data.get("blocked_reason"),
        )


def _run_command(command: str, *, repo_root: Path, timeout_seconds: float) -> CommandResult:
    try:
        completed = subprocess.run(
            command,
            shell=True,  # noqa: S602 -- Manifestは人間が管理するTrusted Configuration(CI Config相当、DEV-AUTO-02からの既存前提)。実行前に`find_forbidden_validation_command()`でGit Mutation Verbを拒否する。
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raw_stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        raw_stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        stdout, stdout_truncated = _bounded(raw_stdout)
        stderr, stderr_truncated = _bounded(raw_stderr)
        return CommandResult(
            command=command,
            returncode=-1,
            stdout=stdout,
            stderr=stderr,
            timed_out=True,
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
        )
    stdout, stdout_truncated = _bounded(completed.stdout)
    stderr, stderr_truncated = _bounded(completed.stderr)
    return CommandResult(
        command=command,
        returncode=completed.returncode,
        stdout=stdout,
        stderr=stderr,
        stdout_truncated=stdout_truncated,
        stderr_truncated=stderr_truncated,
    )


def _run_command_list(commands: tuple[str, ...], *, repo_root: Path, timeout_seconds: float) -> tuple[CommandResult, ...]:
    results: list[CommandResult] = []
    for command in commands:
        result = _run_command(command, repo_root=repo_root, timeout_seconds=timeout_seconds)
        results.append(result)
        if not result.passed:
            # DEV-AUTO-02.4 §2「Fail closed on any nonzero exit」: 最初の
            # 失敗直後にそのCategory内の残りCommandを実行しない(既存
            # `run_targeted_validation`と同じShort-Circuit契約)。
            break
    return tuple(results)


def run_manifest_validation(
    targeted_tests: tuple[str, ...],
    static_checks: tuple[str, ...],
    *,
    repo_root: Path,
    timeout_seconds: float = 900.0,
) -> ValidationResult:
    """DEV-AUTO-02.4 §2/§4: `manifest.targeted_tests`→`manifest.
    static_checks`の順に、Host(このProcess自身)が直接実行する。LLMは
    一切関与しない。実行前に両Category全体を`find_forbidden_validation_
    command()`でCheckし、Git Mutation Verbを含むCommandが1件でも
    あれば**両Categoryとも一切実行せず**`blocked_reason`付きの
    `ValidationResult`を返す(DEV-AUTO-02.4 §11、呼び出し側はこれを
    STOPへMapする)。"""
    forbidden = find_forbidden_validation_command((*targeted_tests, *static_checks))
    if forbidden is not None:
        return ValidationResult(blocked_reason=f"validation command matches a forbidden git-mutation pattern: {forbidden!r}")

    targeted_results = _run_command_list(targeted_tests, repo_root=repo_root, timeout_seconds=timeout_seconds)
    static_results = _run_command_list(static_checks, repo_root=repo_root, timeout_seconds=timeout_seconds)
    return ValidationResult(targeted_tests=targeted_results, static_checks=static_results)


__all__ = [
    "MAX_COMMAND_OUTPUT_CHARS",
    "CommandResult",
    "ValidationResult",
    "find_forbidden_validation_command",
    "run_manifest_validation",
]
