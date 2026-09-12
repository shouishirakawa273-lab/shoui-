"""DEV-AUTO-02 §12: Resume / Crash Safety。

DBは導入しない(標準Library`json`のみ)。永続化するのは`run_id`/
`task_id`/`starting_head`/`state`/`writer_result`/`review_result`/
`open_findings`と(DEV-AUTO-02.2.2 §2で追加した)Writer/Reviewer/
Closure各実行の生Diagnostics(`writer_execution`/`reviewer_execution`/
`closure_writer_executions`/`closure_reviewer_executions`)のみを含む
小さなJSON File 1件のみ。**自動Resumeは実装しない**——Crashした実行を
黙って(Destructiveな段階から)再開する経路は構造的に存在せず、
`status <run-id>`はRecordをRead-Onlyで表示するのみで、実際にやり直す
場合は人間が新しい`run_id`で明示的に`run`を再実行する(DEV-AUTO-02
§12「A crashed run must not silently restart at a destructive stage.
It should require explicit resume.」の最も保守的な充足: 自動継続経路
自体を作らない)。

DEV-AUTO-02.2.2: 実D0103 RunでWriter実行自体は成功したがWriterResultの
Parseが失敗し(`malformed writer result: ...`)、Raw stdout/stderrが
どこにも保持されておらず実際のProtocol Failureを診断できなかった
(RunRecordが`writer_result = null`しか残さなかった)。これを受け、
`WriterResult`/`ReviewerResult`のParse成否に関わらず`ExecutionDiagnostics`
(returncode/timed_out/stdout/stderr、`MAX_DIAGNOSTIC_CHARS`でBound、
超過分は`stdout_truncated`/`stderr_truncated`で明示)を必ず保持する。
これはObservability専用の追加であり、`WriterResult`/`ReviewerResult`の
Schemaや「LAST行が単一JSON Object」というParser Contractには一切
変更を加えていない。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from .agent_results import ReviewerResult, WriterResult, WriterStatus
from .executor import AgentExecutionResult
from .model import Finding, ReviewerVerdict

# DEV-AUTO-02.2.2 §5: Executor stdout/stderrをRunRecordへ無制限に
# 永続化しない(Repository外部からのAgent出力を無検証のまま無限に
# Diskへ書き込むことを避ける、Deterministic Size Bound)。件数超過分は
# 切り捨て、`stdout_truncated`/`stderr_truncated`で必ず明示する
# (無言でのTruncateはしない)。
MAX_DIAGNOSTIC_CHARS = 20_000


def _bounded(value: object, *, max_chars: int = MAX_DIAGNOSTIC_CHARS) -> tuple[str, bool]:
    # DEV-AUTO-02.2.2 §1: `AgentExecutionResult.stdout`/`stderr`は型Hint
    # のみでRuntime強制されない(DEV-AUTO-02.2で対処した実D0103 Crashと
    # 同型: 契約に反したCustom Executor実装が`stdout=None`を返す経路が
    # 理論上残る)。Diagnostics保存はObservability専用のBest-Effort層
    # であり、ここでCrashしてOrchestrator自体をFail Openにしてはならない
    # ため、非`str`は`AttributeError`/`TypeError`を送出せず可読な
    # Placeholderへ変換する(既存の`agent_results._extract_json_object`
    # 側のFail Closed Contract自体は変更しない、あくまで別層)。
    text = value if isinstance(value, str) else f"<non-str executor output: {type(value).__name__}>"
    if len(text) <= max_chars:
        return text, False
    return text[:max_chars], True


@dataclass(kw_only=True, frozen=True)
class ExecutionDiagnostics:
    """DEV-AUTO-02.2.2 §1/§2: `AgentExecutionResult`の生Diagnostics
    (stdout/stderr/returncode/timed_out)をRunRecordへ永続化するための
    最小Envelope。WriterResult/ReviewerResultのParse成否に関わらず
    (成功時も失敗時も)保持する——Protocol Failure(Parse失敗)の実際の
    原因を後から診断できることが唯一の目的であり、これ自体は一切
    ParseもContract Validationも行わない生データ保持層(§8「No parser
    contract change」)。"""

    returncode: int
    timed_out: bool
    stdout: str
    stderr: str
    stdout_truncated: bool = False
    stderr_truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "returncode": self.returncode,
            "timed_out": self.timed_out,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "stdout_truncated": self.stdout_truncated,
            "stderr_truncated": self.stderr_truncated,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> ExecutionDiagnostics:
        return ExecutionDiagnostics(
            returncode=int(data["returncode"]),
            timed_out=bool(data.get("timed_out", False)),
            stdout=str(data.get("stdout", "")),
            stderr=str(data.get("stderr", "")),
            stdout_truncated=bool(data.get("stdout_truncated", False)),
            stderr_truncated=bool(data.get("stderr_truncated", False)),
        )

    @staticmethod
    def from_execution_result(result: AgentExecutionResult, *, max_chars: int = MAX_DIAGNOSTIC_CHARS) -> ExecutionDiagnostics:
        stdout, stdout_truncated = _bounded(result.stdout, max_chars=max_chars)
        stderr, stderr_truncated = _bounded(result.stderr, max_chars=max_chars)
        return ExecutionDiagnostics(
            returncode=result.returncode,
            timed_out=result.timed_out,
            stdout=stdout,
            stderr=stderr,
            stdout_truncated=stdout_truncated,
            stderr_truncated=stderr_truncated,
        )


class RunState(StrEnum):
    STARTED = "STARTED"
    HUMAN_APPROVAL_REQUIRED = "HUMAN_APPROVAL_REQUIRED"
    REPOSITORY_GATE_FAILED = "REPOSITORY_GATE_FAILED"
    WRITER_RUNNING = "WRITER_RUNNING"
    WRITER_FAILED = "WRITER_FAILED"
    WRITER_DONE = "WRITER_DONE"
    REVIEWING = "REVIEWING"
    REVIEW_FAILED = "REVIEW_FAILED"
    REVIEW_DONE = "REVIEW_DONE"
    CLOSURE_ROUND = "CLOSURE_ROUND"
    ACCEPT_CANDIDATE = "ACCEPT_CANDIDATE"
    HUMAN_ATTENTION_REQUIRED = "HUMAN_ATTENTION_REQUIRED"
    STOPPED = "STOPPED"
    DRY_RUN = "DRY_RUN"


@dataclass(kw_only=True, frozen=True)
class RunRecord:
    run_id: str
    task_id: str
    starting_head: str
    state: RunState
    writer_result: WriterResult | None = None
    review_result: ReviewerResult | None = None
    open_findings: tuple[Finding, ...] = field(default_factory=tuple)
    closure_round: int = 0
    reason: str = ""
    # DEV-AUTO-02.2.2 §2: WriterResult/ReviewerResultのParseに成功したか
    # 否かに関わらず、実行ごとの生Diagnosticsを別途保持する
    # (`writer_result`/`review_result`はParse成功時のみ`None`以外になる
    # 既存Contractを変更しない、あくまで並行する追加Field)。Closure
    # Roundは`closure_round`(何Round目まで進んだか)と同じIndex順で
    # Tupleへ1件ずつ追記する最小構造とし、独自のRound番号Keyingは
    # 導入しない。
    writer_execution: ExecutionDiagnostics | None = None
    reviewer_execution: ExecutionDiagnostics | None = None
    closure_writer_executions: tuple[ExecutionDiagnostics, ...] = field(default_factory=tuple)
    closure_reviewer_executions: tuple[ExecutionDiagnostics, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "task_id": self.task_id,
            "starting_head": self.starting_head,
            "state": self.state.value,
            "writer_result": (
                None
                if self.writer_result is None
                else {
                    "status": self.writer_result.status.value,
                    "files_changed": list(self.writer_result.files_changed),
                    "tests": self.writer_result.tests,
                    "static_checks": self.writer_result.static_checks,
                    "blocking_issue": self.writer_result.blocking_issue,
                    "summary": self.writer_result.summary,
                }
            ),
            "review_result": (
                None
                if self.review_result is None
                else {
                    "status": self.review_result.status,
                    "verdict": self.review_result.verdict.value,
                    "findings": [f.to_dict() for f in self.review_result.findings],
                }
            ),
            "open_findings": [f.to_dict() for f in self.open_findings],
            "closure_round": self.closure_round,
            "reason": self.reason,
            "writer_execution": (None if self.writer_execution is None else self.writer_execution.to_dict()),
            "reviewer_execution": (None if self.reviewer_execution is None else self.reviewer_execution.to_dict()),
            "closure_writer_executions": [d.to_dict() for d in self.closure_writer_executions],
            "closure_reviewer_executions": [d.to_dict() for d in self.closure_reviewer_executions],
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> RunRecord:
        writer_result = None
        if data.get("writer_result") is not None:
            wr = data["writer_result"]
            writer_result = WriterResult(
                status=WriterStatus(wr["status"]),
                files_changed=tuple(wr.get("files_changed", [])),
                tests=str(wr.get("tests", "")),
                static_checks=str(wr.get("static_checks", "")),
                blocking_issue=wr.get("blocking_issue"),
                summary=str(wr.get("summary", "")),
            )

        review_result = None
        if data.get("review_result") is not None:
            rr = data["review_result"]
            review_result = ReviewerResult(
                status=str(rr.get("status", "COMPLETED")),
                verdict=ReviewerVerdict(rr["verdict"]),
                findings=tuple(Finding.from_dict(item) for item in rr.get("findings", [])),
            )

        writer_execution = (
            None if data.get("writer_execution") is None else ExecutionDiagnostics.from_dict(data["writer_execution"])
        )
        reviewer_execution = (
            None if data.get("reviewer_execution") is None else ExecutionDiagnostics.from_dict(data["reviewer_execution"])
        )

        return RunRecord(
            run_id=str(data["run_id"]),
            task_id=str(data["task_id"]),
            starting_head=str(data["starting_head"]),
            state=RunState(data["state"]),
            writer_result=writer_result,
            review_result=review_result,
            open_findings=tuple(Finding.from_dict(item) for item in data.get("open_findings", [])),
            closure_round=int(data.get("closure_round", 0)),
            reason=str(data.get("reason", "")),
            writer_execution=writer_execution,
            reviewer_execution=reviewer_execution,
            closure_writer_executions=tuple(
                ExecutionDiagnostics.from_dict(item) for item in data.get("closure_writer_executions", [])
            ),
            closure_reviewer_executions=tuple(
                ExecutionDiagnostics.from_dict(item) for item in data.get("closure_reviewer_executions", [])
            ),
        )


def run_record_path(run_id: str, *, runs_dir: Path) -> Path:
    return runs_dir / f"{run_id}.json"


def save_run_record(record: RunRecord, *, runs_dir: Path) -> Path:
    runs_dir.mkdir(parents=True, exist_ok=True)
    path = run_record_path(record.run_id, runs_dir=runs_dir)
    path.write_text(json.dumps(record.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_run_record(run_id: str, *, runs_dir: Path) -> RunRecord:
    path = run_record_path(run_id, runs_dir=runs_dir)
    return RunRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))


__all__ = [
    "MAX_DIAGNOSTIC_CHARS",
    "ExecutionDiagnostics",
    "RunRecord",
    "RunState",
    "load_run_record",
    "run_record_path",
    "save_run_record",
]
