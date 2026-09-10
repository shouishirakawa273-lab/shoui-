"""DEV-AUTO-02 §12: Resume / Crash Safety。

DBは導入しない(標準Library`json`のみ)。永続化するのは`run_id`/
`task_id`/`starting_head`/`state`/`writer_result`/`review_result`/
`open_findings`のみを含む極小のJSON File 1件のみ。**自動Resumeは
実装しない**——Crashした実行を黙って(Destructiveな段階から)再開する
経路は構造的に存在せず、`status <run-id>`はRecordをRead-Onlyで表示
するのみで、実際にやり直す場合は人間が新しい`run_id`で明示的に
`run`を再実行する(DEV-AUTO-02 §12「A crashed run must not silently
restart at a destructive stage. It should require explicit resume.」
の最も保守的な充足: 自動継続経路自体を作らない)。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from .agent_results import ReviewerResult, WriterResult, WriterStatus
from .model import Finding, ReviewerVerdict


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


__all__ = ["RunRecord", "RunState", "load_run_record", "run_record_path", "save_run_record"]
