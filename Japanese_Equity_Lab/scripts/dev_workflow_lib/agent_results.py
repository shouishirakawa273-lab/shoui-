"""DEV-AUTO-02 §5: 機械可読なAgent実行結果Envelope。

`WriterResult`/`ReviewerResult`はいずれも厳密なJSON Parsingのみを行い、
自由形式のProse(自然文Output)を推測でParseしない
(DEV-AUTO-02 §5「Do not parse arbitrary prose if a structured result
can be required. Fail closed on malformed result.」)。Parse失敗は必ず
`ValueError`をRaiseし、呼び出し側(`orchestrator.py`)がこれを
Deterministicに`STOP`へMapする。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from .model import Finding, ReviewerVerdict


class WriterStatus(StrEnum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


def _extract_json_object(raw_output: str) -> dict[str, Any]:
    """`raw_output`全体をまずJSONとしてParseし、失敗した場合のみ最後の
    非空行をJSONとしてParseし直す(Agent実行Toolが前後にLog/Banner等の
    余分な出力を混ぜる場合への最小限の許容、それでも失敗すれば必ず
    `ValueError`)。Fenced Code Block等の複雑なExtractionは行わない
    (推測によるParseを増やさない)。

    DEV-AUTO-02.2 §4: `raw_output`が`str`でない場合(例: Executor
    実装の不備で`None`が渡った場合)も、`AttributeError`をExternalへ
    漏らさず、ここでFail Closedの`ValueError`に変換する。"""
    if not isinstance(raw_output, str):
        raise ValueError(f"agent output must be a string, got {type(raw_output).__name__}")
    stripped = raw_output.strip()
    if not stripped:
        raise ValueError("agent output is empty")
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError:
        lines = [line for line in stripped.splitlines() if line.strip()]
        if not lines:
            raise ValueError("agent output is empty") from None
        try:
            data = json.loads(lines[-1])
        except json.JSONDecodeError as exc:
            raise ValueError(f"agent output is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("agent result JSON must be an object")
    return data


@dataclass(kw_only=True, frozen=True)
class WriterResult:
    """DEV-AUTO-02 §5 Writer Result Envelope。"""

    status: WriterStatus
    files_changed: tuple[str, ...] = field(default_factory=tuple)
    tests: str = ""
    static_checks: str = ""
    blocking_issue: str | None = None
    summary: str = ""

    @staticmethod
    def from_raw_output(raw_output: str) -> WriterResult:
        data = _extract_json_object(raw_output)
        if "status" not in data:
            raise ValueError("writer result missing required field 'status'")
        try:
            status = WriterStatus(data["status"])
        except ValueError as exc:
            raise ValueError(f"writer result has invalid 'status': {data['status']!r}") from exc

        files_changed_raw = data.get("files_changed", [])
        if not isinstance(files_changed_raw, list) or not all(isinstance(p, str) for p in files_changed_raw):
            raise ValueError("writer result 'files_changed' must be a list of strings")

        blocking_issue = data.get("blocking_issue")
        if blocking_issue is not None and not isinstance(blocking_issue, str):
            raise ValueError("writer result 'blocking_issue' must be a string or null")

        return WriterResult(
            status=status,
            files_changed=tuple(files_changed_raw),
            tests=str(data.get("tests", "")),
            static_checks=str(data.get("static_checks", "")),
            blocking_issue=blocking_issue,
            summary=str(data.get("summary", "")),
        )


@dataclass(kw_only=True, frozen=True)
class ReviewerResult:
    """DEV-AUTO-02 §5 Reviewer Result Envelope。`findings`は既存
    `Finding`(DEV-AUTO-01)をそのまま再利用する(独自のFinding Schemaを
    新設しない)。"""

    status: str
    verdict: ReviewerVerdict
    findings: tuple[Finding, ...] = field(default_factory=tuple)

    @staticmethod
    def from_raw_output(raw_output: str) -> ReviewerResult:
        data = _extract_json_object(raw_output)
        if "verdict" not in data:
            raise ValueError("reviewer result missing required field 'verdict'")
        try:
            verdict = ReviewerVerdict(data["verdict"])
        except ValueError as exc:
            raise ValueError(f"reviewer result has invalid 'verdict': {data['verdict']!r}") from exc

        raw_findings = data.get("findings", [])
        if not isinstance(raw_findings, list):
            raise ValueError("reviewer result 'findings' must be a list")
        try:
            findings = tuple(Finding.from_dict(item) for item in raw_findings)
        except (KeyError, ValueError) as exc:
            raise ValueError(f"reviewer result contains an invalid finding: {exc}") from exc

        return ReviewerResult(status=str(data.get("status", "COMPLETED")), verdict=verdict, findings=findings)


__all__ = ["ReviewerResult", "WriterResult", "WriterStatus"]
