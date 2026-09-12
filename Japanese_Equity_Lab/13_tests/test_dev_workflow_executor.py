"""DEV-AUTO-02.2(Windows UTF-8 Subprocess Hardening)のRegression Test。

実際のD0103 Runで発生した`cp932`Decode Crash(`subprocess.py
_readerthread` → `UnicodeDecodeError` → `writer_exec_result.stdout`が
`None`化 → `WriterResult.from_raw_output(None)` → `AttributeError`)の
再発防止を検証する。実Subprocess(`sys.executable`)を実際に起動する
Testを含む(純粋なDecode Helperの単体Testだけに留めない、DEV-AUTO-02.2
§6)。投資判断・Market Data・実Model呼び出しはこのTest Module・対象Code
のいずれにも存在しない(`INVESTMENT_LOGIC_CHANGED = NO`)。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from scripts.dev_workflow_lib.agent_results import ReviewerResult, WriterResult, WriterStatus
from scripts.dev_workflow_lib.executor import AgentExecutionResult, LocalCommandExecutor
from scripts.dev_workflow_lib.model import ReviewerVerdict, Role

# cp932では表現できない(または表現が異なる)UTF-8文字を含む文字列。
# 「検証結果」はcp932でもEncode可能だが、"→"(U+2192)はcp932の
# 標準的なMappingに含まれず、Windows既定Codecへの暗黙依存があれば
# ここでDecode Errorが再現する。
_UNSAFE_UNDER_CP932 = "検証結果 → ✓"


def _python_command(*, script: str) -> LocalCommandExecutor:
    return LocalCommandExecutor(command=(sys.executable, "-c", script))


# ============================================================
# DEV-AUTO-02.2 §6: 実SubprocessでのUTF-8 Regression Test
# ============================================================


def test_local_command_executor_decodes_utf8_unsafe_under_cp932(tmp_path: Path) -> None:
    # Text ModeやAmbient Localeに一切依存せず、Raw Bytes経由でUTF-8を
    # 明示的にDecodeすることを、実際の`LocalCommandExecutor`Adapter越しに
    # 確認する(Pure Decode Helperの単体Testだけでは、`text=True`+
    # 暗黙Localeによる実際のSubprocess Crash Pathを再現できない)。
    script = f"import sys\nsys.stdout.buffer.write({_UNSAFE_UNDER_CP932!r}.encode('utf-8'))\n"
    executor = _python_command(script=script)

    result = executor.execute(role=Role.WRITER, prompt="unused", working_directory=tmp_path)

    assert result.returncode == 0
    assert result.timed_out is False
    assert result.stdout == _UNSAFE_UNDER_CP932


def test_local_command_executor_round_trips_utf8_via_stdin(tmp_path: Path) -> None:
    # `prompt_via="stdin"`もUTF-8 Byte経由で送信・受信されることを確認する
    # (`stdin_input`をStrのままPipeへ渡すとAmbient Localeへ暗黙依存する)。
    script = "import sys\nsys.stdout.buffer.write(sys.stdin.buffer.read())\n"
    executor = LocalCommandExecutor(command=(sys.executable, "-c", script), prompt_via="stdin")

    result = executor.execute(role=Role.WRITER, prompt=_UNSAFE_UNDER_CP932, working_directory=tmp_path)

    assert result.returncode == 0
    assert result.stdout == _UNSAFE_UNDER_CP932


# ============================================================
# DEV-AUTO-02.2 §7: 不正UTF-8のRegression Test
# ============================================================


def test_local_command_executor_fails_closed_on_invalid_utf8_stdout(tmp_path: Path) -> None:
    # 意図的に不正なUTF-8 Byte Sequenceを出力するChild Processを起動する。
    # `UnicodeDecodeError`がここでUncaughtのままExternalへ漏れないこと、
    # かつ`errors="ignore"`等でSilentに破損させず、構造化された失敗
    # (`returncode=-1`)として返ることを確認する。
    script = "import sys\nsys.stdout.buffer.write(bytes([0xFF, 0xFE, 0x00, 0x01]))\n"
    executor = _python_command(script=script)

    result = executor.execute(role=Role.WRITER, prompt="unused", working_directory=tmp_path)

    assert result.returncode == -1
    assert result.timed_out is False
    assert result.stdout == ""
    assert "UTF-8" in result.stderr


def test_local_command_executor_fails_closed_on_invalid_utf8_stderr(tmp_path: Path) -> None:
    script = "import sys\nsys.stderr.buffer.write(bytes([0xFF, 0xFE, 0x00, 0x01]))\nsys.exit(0)\n"
    executor = _python_command(script=script)

    result = executor.execute(role=Role.WRITER, prompt="unused", working_directory=tmp_path)

    assert result.returncode == -1
    assert result.stdout == ""


# ============================================================
# DEV-AUTO-02.2 §4/§8: None / 非strのParser境界Regression Test
# ============================================================


def test_writer_result_from_raw_output_rejects_none_without_attributeerror() -> None:
    # 実際に発生したCrash: `WriterResult.from_raw_output(None)` →
    # `raw_output.strip()` → `AttributeError`。ここでは代わりに
    # 制御された`ValueError`(呼び出し側`orchestrator.py`がSTOPへMapする
    # Contract)が上がることを確認する。
    with pytest.raises(ValueError, match="must be a string"):
        WriterResult.from_raw_output(None)  # type: ignore[arg-type]


def test_reviewer_result_from_raw_output_rejects_none_without_attributeerror() -> None:
    with pytest.raises(ValueError, match="must be a string"):
        ReviewerResult.from_raw_output(None)  # type: ignore[arg-type]


def test_writer_result_from_raw_output_rejects_non_str_types() -> None:
    with pytest.raises(ValueError, match="must be a string"):
        WriterResult.from_raw_output(b'{"status": "SUCCESS"}')  # type: ignore[arg-type]


def test_agent_execution_result_stdout_is_never_none_after_decode_failure(tmp_path: Path) -> None:
    # `AgentExecutionResult.stdout`が`None`になる経路が存在しないことを、
    # 不正UTF-8Case・正常Case双方でTypeとして確認する(型Hintではなく
    # 実際のRuntime Valueを確認する)。
    invalid_script = "import sys\nsys.stdout.buffer.write(bytes([0xFF, 0xFE]))\n"
    result = _python_command(script=invalid_script).execute(role=Role.WRITER, prompt="unused", working_directory=tmp_path)
    assert isinstance(result.stdout, str)
    assert isinstance(result.stderr, str)


# ============================================================
# DEV-AUTO-02.2 §9: Writer/Reviewer/Closure共有Adapterの一貫性
# ============================================================


def test_utf8_and_invalid_utf8_behavior_is_identical_for_writer_and_reviewer_roles(tmp_path: Path) -> None:
    # `LocalCommandExecutor.execute()`はRoleごとの分岐を持たない
    # (`del role`)ため、Writer/Reviewer/Closure Writer/Closure Reviewerの
    # いずれも同一のUTF-8 Safe Pathを通る。ここではWRITER/REVIEWER双方の
    # Roleで同じCommandを実行し、挙動が一致することを明示的に確認する。
    ok_script = f"import sys\nsys.stdout.buffer.write({_UNSAFE_UNDER_CP932!r}.encode('utf-8'))\n"
    bad_script = "import sys\nsys.stdout.buffer.write(bytes([0xFF, 0xFE]))\n"

    ok_executor = _python_command(script=ok_script)
    bad_executor = _python_command(script=bad_script)

    for role in (Role.WRITER, Role.REVIEWER):
        ok_result = ok_executor.execute(role=role, prompt="unused", working_directory=tmp_path)
        assert ok_result.returncode == 0
        assert ok_result.stdout == _UNSAFE_UNDER_CP932

        bad_result = bad_executor.execute(role=role, prompt="unused", working_directory=tmp_path)
        assert bad_result.returncode == -1
        assert bad_result.stdout == ""


# ============================================================
# DEV-AUTO-02.2 §3/§8: Public Boundaryから生Exceptionが漏れないこと
# ============================================================


def test_malformed_agent_execution_result_never_raises_attributeerror() -> None:
    # `AgentExecutionResult`は型HintのみでRuntime強制はされないため、
    # 不良なExecutor実装が`stdout=None`を返す経路が理論上残り得る
    # (実際のD0103 Crashが辿った経路と同型)。それでも`from_raw_output`
    # 境界で必ず`ValueError`にFail Closedし、`AttributeError`/`TypeError`
    # がPublic Boundaryへ漏れないことを確認する。
    malformed = AgentExecutionResult(returncode=0, stdout=None, stderr="")  # type: ignore[arg-type]

    with pytest.raises(ValueError):
        WriterResult.from_raw_output(malformed.stdout)


# ============================================================
# DEV-AUTO-02.2.1: Claude CLI Output Transport Closure
# ============================================================
#
# `claude -p --output-format json`はAgent自身の回答をClaude CLI固有の
# 外側Envelope Object(duration_api_ms/session_id/usage/.../result/...)
# へ包み、Workflow JSONはそのEnvelopeの`result`Fieldへ二重Encodeされた
# 文字列として入る。WriterResult/ReviewerResultはこの外側Envelopeを
# 一切知らない(Provider-Specific Unwrapを持たない、DEV-AUTO-02 §3
# Capability-Based/Provider-Agnostic Coreを維持)ため、
# `--output-format text`(=Prompt自身が指示するLAST行JSON、prompts.py)
# へ切り替えるのが正しい対処であり、Coreの変更は不要という設計判断を
# 固定するRegressionを以下に置く。

_EXECUTOR_CONFIG_PATH = Path(__file__).resolve().parent.parent / "scripts" / "executor_config.example.json"

# 実際のClaude CLI `--output-format json`実行(`claude -p --output-format
# json --permission-prompts none "..."`)で観測した外側Envelopeを模した
# Fixture(Usage統計等の大半のFieldは本質的でないため省略する)。
# Workflow JSON(`{"status": "SUCCESS", ...}`相当)はEscapeされた文字列と
# して`result`Fieldに入り、Envelope自体のTop-Levelには`status`も
# `verdict`も存在しない。
_CLAUDE_CLI_JSON_ENVELOPE = json.dumps(
    {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "session_id": "f53a2d64-c3dd-445e-ae85-0e63fc64eabc",
        "result": '{"status":"SUCCESS","note":"smoke-test"}',
    }
)


def test_example_executor_config_uses_parser_compatible_text_output_format() -> None:
    # `--output-format json`は上記のEnvelope問題を起こすため、Example
    # ConfigのWriter/Reviewer双方が`text`を使うことを固定する。
    raw = json.loads(_EXECUTOR_CONFIG_PATH.read_text(encoding="utf-8"))
    for capability_key in ("CAN_EXECUTE_WRITER", "CAN_EXECUTE_READ_ONLY_REVIEWER"):
        command = raw[capability_key]["command"]
        format_index = command.index("--output-format")
        assert command[format_index + 1] == "text"
        assert "json" not in command[format_index + 1 : format_index + 2]


def test_example_reviewer_config_terminates_disallowed_tools_before_prompt() -> None:
    # `--disallowedTools <tools...>`はVariadicであり、`prompt_via="arg"`
    # がCommand末尾へ追加するPromptがそのままDisallowedTools一覧へ
    # 飲み込まれてしまう(実際に`claude`を起動し、"Input must be provided
    # either through stdin or as a prompt argument"で失敗することを確認
    # 済み)。Reviewer ConfigのCommand配列が`--`(End-of-Options)で終わり、
    # Prompt追加後もOption Parsingへ巻き込まれないことを固定する。
    raw = json.loads(_EXECUTOR_CONFIG_PATH.read_text(encoding="utf-8"))
    command = raw["CAN_EXECUTE_READ_ONLY_REVIEWER"]["command"]
    assert "--disallowedTools" in command
    assert command[-1] == "--"


def test_writer_result_fails_closed_on_raw_claude_cli_json_envelope() -> None:
    # CoreがProvider固有のUnwrap(例: Envelopeの`result`Fieldを自動的に
    # 展開する等)を一切実装していないことを確認する。Envelopeそのものを
    # 渡した場合は、Top-Levelに`status`が存在しないため必ずFail Closedで
    # `ValueError`になる。
    with pytest.raises(ValueError, match="status"):
        WriterResult.from_raw_output(_CLAUDE_CLI_JSON_ENVELOPE)


def test_reviewer_result_fails_closed_on_raw_claude_cli_json_envelope() -> None:
    with pytest.raises(ValueError, match="verdict"):
        ReviewerResult.from_raw_output(_CLAUDE_CLI_JSON_ENVELOPE)


def test_writer_result_parses_last_line_of_text_output_with_japanese_utf8() -> None:
    # `--output-format text`実行を模したRaw Output: Agentの自然文Prose
    # (日本語含む)の後、LAST行のみが単一JSON Object(prompts.py
    # `_WRITER_RESULT_FORMAT`が要求する形)。UTF-8日本語がJSON文字列
    # Value内で正しく保持されることを確認する。
    raw_output = (
        "変更点を確認しました。テストも実行しました。\n"
        '{"status": "SUCCESS", "files_changed": ["core/foo.py"], '
        '"tests": "pytest 12 passed", "static_checks": "ruff/mypy OK", '
        '"blocking_issue": null, "summary": "検証結果 → 修正完了"}\n'
    )

    result = WriterResult.from_raw_output(raw_output)

    assert result.status == WriterStatus.SUCCESS
    assert result.files_changed == ("core/foo.py",)
    assert result.summary == "検証結果 → 修正完了"


def test_reviewer_result_parses_last_line_of_text_output_with_japanese_utf8() -> None:
    raw_output = (
        "READ ONLYでDiffを確認しました。問題は見つかりませんでした。\n"
        '{"status": "COMPLETED", "verdict": "ACCEPTED", "findings": []}\n'
    )

    result = ReviewerResult.from_raw_output(raw_output)

    assert result.status == "COMPLETED"
    assert result.verdict == ReviewerVerdict.ACCEPTED
    assert result.findings == ()
