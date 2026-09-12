"""DEV-AUTO-02 §2/§3: Capability-Based Agent Execution。

Product/Plan名(CLAUDE/CODEX/GPT_PLAN等)をこのModule自体は一切知らない。
実際に許可される操作(`ExecutionCapability`)ごとにExecutorをMapする
Registryのみを扱う。`LocalCommandExecutor`のCommand Templateは常に
呼び出し側(人間、または`load_executor_registry_from_json()`が読む
Configuration File)から明示的に供給される——このModule自身が
特定のVendor CLI Flagをhard-codeすることは無い(DEV-AUTO-02 §3
「Do NOT invent unsupported CLI flags.」)。
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Literal, Protocol

from .model import Role


class ExecutionCapability(StrEnum):
    """DEV-AUTO-02 §2: 実際に許可される実行操作そのもの(Product/Plan名
    ではない)。"""

    CAN_EXECUTE_WRITER = "CAN_EXECUTE_WRITER"
    CAN_EXECUTE_READ_ONLY_REVIEWER = "CAN_EXECUTE_READ_ONLY_REVIEWER"


@dataclass(kw_only=True, frozen=True)
class AgentExecutionResult:
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False


class AgentExecutor(Protocol):
    def execute(self, *, role: Role, prompt: str, working_directory: Path) -> AgentExecutionResult: ...


def _decode_utf8_strict(data: bytes) -> str:
    """DEV-AUTO-02.2 §2: SubprocessのRaw Byte OutputをUTF-8として厳密に
    Decodeする。`locale.getpreferredencoding()`・Windows ANSI Code Page
    (cp932)・`PYTHONUTF8`環境変数には一切依存しない(Deterministic
    Windows Behavior)。不正なUTF-8であれば`UnicodeDecodeError`をそのまま
    Raiseし、呼び出し側がFail Closedで扱う(DEV-AUTO-02.2 §3、
    `errors="ignore"`は使わない)。"""
    return data.decode("utf-8", errors="strict")


@dataclass(kw_only=True, frozen=True)
class LocalCommandExecutor:
    """DEV-AUTO-02 §3: Command TemplateはConfigurationとして明示的に
    供給される汎用Subprocess Adapter(特定のVendor CLIをHard-codeしない、
    どのCommandでも動作する)。`prompt_via="arg"`はPromptをCommand末尾の
    Positional Argumentとして渡し、`"stdin"`はStandard Input経由で渡す。

    DEV-AUTO-02.2 §2: `subprocess.run`は`text=True`を使わずRaw Bytesで
    Captureし(Windows既定Codec cp932への暗黙依存を避ける)、`stdout`/
    `stderr`はこのAdapterが明示的にUTF-8としてDecodeする。Decode失敗は
    §3の通りFail Closed(`AgentExecutionResult.stdout`が`None`になる
    経路も、非`str`がParserへ渡る経路も存在しない)。
    """

    command: tuple[str, ...]
    timeout_seconds: float = 600.0
    prompt_via: Literal["arg", "stdin"] = "arg"

    def __post_init__(self) -> None:
        if not self.command:
            raise ValueError("command は空にできません")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds は正の値である必要があります")

    def execute(self, *, role: Role, prompt: str, working_directory: Path) -> AgentExecutionResult:
        del role  # このAdapter自体はRoleごとの差異を持たない(Prompt文字列側で表現済み)。
        if self.prompt_via == "arg":
            argv = [*self.command, prompt]
            stdin_input: bytes | None = None
        else:
            argv = list(self.command)
            stdin_input = prompt.encode("utf-8")

        try:
            completed = subprocess.run(
                argv,
                cwd=working_directory,
                input=stdin_input,
                capture_output=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            stdout_bytes = exc.stdout if isinstance(exc.stdout, bytes) else b""
            stderr_bytes = exc.stderr if isinstance(exc.stderr, bytes) else b""
            try:
                stdout = _decode_utf8_strict(stdout_bytes)
                stderr = _decode_utf8_strict(stderr_bytes)
            except UnicodeDecodeError as decode_exc:
                return AgentExecutionResult(
                    returncode=-1,
                    stdout="",
                    stderr=f"executor timed out and output was not valid UTF-8: {decode_exc}",
                    timed_out=True,
                )
            return AgentExecutionResult(returncode=-1, stdout=stdout, stderr=stderr, timed_out=True)
        except OSError as exc:
            return AgentExecutionResult(returncode=-1, stdout="", stderr=f"failed to launch command: {exc}")

        try:
            stdout = _decode_utf8_strict(completed.stdout)
            stderr = _decode_utf8_strict(completed.stderr)
        except UnicodeDecodeError as exc:
            # DEV-AUTO-02.2 §3: Decode失敗はCrashさせず、構造化された
            # 失敗Resultとして返す(呼び出し側`orchestrator.py`は
            # `returncode != 0`のPathでSTOPし、`WriterResult`/
            # `ReviewerResult`のParserには到達しない)。
            return AgentExecutionResult(returncode=-1, stdout="", stderr=f"executor output was not valid UTF-8: {exc}")

        return AgentExecutionResult(returncode=completed.returncode, stdout=stdout, stderr=stderr)


@dataclass(kw_only=True, frozen=True)
class ExecutorRegistry:
    """DEV-AUTO-02 §2: Capability -> Executorの明示的Mapping。未設定の
    Capabilityは`get()`が`None`を返す(呼び出し側がFail Closedで扱う、
    Silent Fallbackは行わない)。"""

    executors: dict[ExecutionCapability, AgentExecutor] = field(default_factory=dict)

    def get(self, capability: ExecutionCapability) -> AgentExecutor | None:
        return self.executors.get(capability)

    @staticmethod
    def empty() -> ExecutorRegistry:
        return ExecutorRegistry(executors={})


def load_executor_registry_from_json(path: Path) -> ExecutorRegistry:
    """DEV-AUTO-02 §4: Repo-Local/環境固有のExecutor Configurationを
    JSONから読み込む。APIキー・Token・Password等のSecretは一切扱わない
    (Command Templateの配列のみ、DEV-AUTO-02 §4)。

    期待するJSON形状:
    {
      "CAN_EXECUTE_WRITER": {"command": ["<cmd>", "<flag>", ...], "prompt_via": "arg", "timeout_seconds": 600},
      "CAN_EXECUTE_READ_ONLY_REVIEWER": {"command": [...], ...}
    }
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("executor config JSON must be an object")

    executors: dict[ExecutionCapability, AgentExecutor] = {}
    for key, value in raw.items():
        try:
            capability = ExecutionCapability(key)
        except ValueError as exc:
            raise ValueError(f"unknown execution capability in config: {key!r}") from exc
        if not isinstance(value, dict) or "command" not in value:
            raise ValueError(f"executor config for {key!r} must be an object with a 'command' array")
        command = value["command"]
        if not isinstance(command, list) or not all(isinstance(part, str) for part in command):
            raise ValueError(f"executor config for {key!r} 'command' must be a list of strings")
        prompt_via = value.get("prompt_via", "arg")
        if prompt_via not in ("arg", "stdin"):
            raise ValueError(f"executor config for {key!r} 'prompt_via' must be 'arg' or 'stdin'")
        timeout_seconds = float(value.get("timeout_seconds", 600.0))
        executors[capability] = LocalCommandExecutor(
            command=tuple(command), prompt_via=prompt_via, timeout_seconds=timeout_seconds
        )

    return ExecutorRegistry(executors=executors)


__all__ = [
    "AgentExecutionResult",
    "AgentExecutor",
    "ExecutionCapability",
    "ExecutorRegistry",
    "LocalCommandExecutor",
    "load_executor_registry_from_json",
]
