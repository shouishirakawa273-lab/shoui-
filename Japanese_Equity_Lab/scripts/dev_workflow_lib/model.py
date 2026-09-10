"""DEV-AUTO-01: Capability-Based Role Model + Finding/TaskManifest Schema。

Product/Plan名(CLAUDE/CODEX/GPT_PLAN/STANDARD/PRO等)を一切使わず、
実際に許可される操作(Capability)そのものでRoleを表現する
(DEV-AUTO-01 §1/§2)。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

# DEV-AUTO-02.1.1: `TaskManifest.expected_head`にこのSentinel文字列を
# 指定すると、実際のSHAをManifestへHard-codeする代わりに、実行開始時点
# (`run_task()`の最初)でその瞬間のGit HEADを一度だけ解決し、そのRun
# 全体(Writer/Reviewer/全Closure Round)でImmutableな`starting_head`
# として再利用する(Bootstrap Problem: Manifestへ現在のHEADを書く→
# Commit→そのCommit自体がHEADを進める→Manifestが即座にStaleになる、
# という循環を断つ)。明示的な40桁SHAを指定した場合はこのSentinelとは
# 無関係に既存の厳密一致Checkがそのまま適用される(Backward
# Compatibility、§3)。
RUNTIME_HEAD_SENTINEL = "CURRENT"


class Capability(StrEnum):
    """実際に許可される操作そのもの(Product/Plan名ではない)。"""

    CAN_EDIT_REPO = "CAN_EDIT_REPO"
    CAN_RUN_TESTS = "CAN_RUN_TESTS"
    CAN_REVIEW_READ_ONLY = "CAN_REVIEW_READ_ONLY"
    CAN_COMMIT = "CAN_COMMIT"
    CAN_PUSH = "CAN_PUSH"


class Role(StrEnum):
    """DEV-AUTO-01 §2で定義する3つの論理Roleのみ(新しいRoleを増やす
    場合も`ROLE_CAPABILITIES`へ明示的にCapabilityを追加すること)。"""

    WRITER = "WRITER"
    REVIEWER = "REVIEWER"
    ACCEPTANCE_GATE = "ACCEPTANCE_GATE"


# DEV-AUTO-01 §2: RoleごとのCapability集合(Closed Mapping)。REVIEWERは
# CAN_EDIT_REPO/CAN_COMMIT/CAN_PUSHのいずれも持たない
# (Read-Only強制、§10 Review Independence)。ACCEPTANCE_GATEは
# CAN_EDIT_REPO/CAN_REVIEW_READ_ONLYを持たない(自ら実装もReviewも
# 行わず、Writer結果+Reviewer評決+Closure StatusのみをConsumeする、
# §2 ACCEPTANCE_GATE定義)。
ROLE_CAPABILITIES: dict[Role, frozenset[Capability]] = {
    Role.WRITER: frozenset({Capability.CAN_EDIT_REPO, Capability.CAN_RUN_TESTS}),
    Role.REVIEWER: frozenset({Capability.CAN_REVIEW_READ_ONLY, Capability.CAN_RUN_TESTS}),
    Role.ACCEPTANCE_GATE: frozenset({Capability.CAN_COMMIT, Capability.CAN_PUSH}),
}


def role_has_capability(role: Role, capability: Capability) -> bool:
    """例: `role_has_capability(Role.REVIEWER, Capability.CAN_COMMIT)`は
    常に`False`(Reviewerは書き込み系操作を一切Authorizeできない、
    DEV-AUTO-01 §10)。"""
    return capability in ROLE_CAPABILITIES.get(role, frozenset())


class WorkflowState(StrEnum):
    """DEV-AUTO-01 §3。永続化する場合のみJSONへSerializeする(DBは
    導入しない)。"""

    PLANNED = "PLANNED"
    IMPLEMENTING = "IMPLEMENTING"
    VALIDATING = "VALIDATING"
    REVIEWING = "REVIEWING"
    FIX_REQUIRED = "FIX_REQUIRED"
    CLOSURE_REVIEW = "CLOSURE_REVIEW"
    READY_FOR_ACCEPTANCE = "READY_FOR_ACCEPTANCE"
    ACCEPTED = "ACCEPTED"
    STOPPED = "STOPPED"


class Severity(StrEnum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NOTE = "NOTE"


class FindingStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class ReviewerVerdict(StrEnum):
    """既存Skeptic/PIT Reviewer Skillと同型の3値Outcome(数値Score・
    確率はいずれも使わない、DEV-AUTO-01 §14)。"""

    ACCEPTED = "ACCEPTED"
    NEEDS_FIX = "NEEDS_FIX"
    STOP = "STOP"


class AcceptanceVerdict(StrEnum):
    """DEV-AUTO-01 §2/§14。Acceptance Gateの戻り値はこの4値のみ。"""

    ACCEPT = "ACCEPT"
    FIX_REQUIRED = "FIX_REQUIRED"
    STOP = "STOP"
    HUMAN_APPROVAL_REQUIRED = "HUMAN_APPROVAL_REQUIRED"


@dataclass(kw_only=True, frozen=True)
class Finding:
    """DEV-AUTO-01 §4の最小Finding構造。"""

    finding_id: str
    severity: Severity
    status: FindingStatus
    summary: str
    location: str = ""
    reproducer: str = ""
    expected: str = ""
    actual: str = ""
    blocking: bool = False

    def __post_init__(self) -> None:
        if not self.finding_id:
            raise ValueError("finding_id は空にできません")
        if not isinstance(self.severity, Severity):
            raise ValueError(f"severity は Severity である必要があります: {self.severity!r}")
        if not isinstance(self.status, FindingStatus):
            raise ValueError(f"status は FindingStatus である必要があります: {self.status!r}")
        if not self.summary:
            raise ValueError("summary は空にできません")

    @staticmethod
    def from_dict(data: dict[str, Any]) -> Finding:
        return Finding(
            finding_id=str(data["finding_id"]),
            severity=Severity(data["severity"]),
            status=FindingStatus(data["status"]),
            summary=str(data["summary"]),
            location=str(data.get("location", "")),
            reproducer=str(data.get("reproducer", "")),
            expected=str(data.get("expected", "")),
            actual=str(data.get("actual", "")),
            blocking=bool(data.get("blocking", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "severity": self.severity.value,
            "status": self.status.value,
            "summary": self.summary,
            "location": self.location,
            "reproducer": self.reproducer,
            "expected": self.expected,
            "actual": self.actual,
            "blocking": self.blocking,
        }


@dataclass(kw_only=True, frozen=True)
class TaskManifest:
    """DEV-AUTO-01 §5。特定のTool Provider/Subscription Plan名は
    一切含めない(Capability要件のみを記述する)。"""

    task_id: str
    purpose: str
    expected_head: str = RUNTIME_HEAD_SENTINEL
    allowed_files: tuple[str, ...]
    frozen_files: tuple[str, ...] = field(default_factory=tuple)
    targeted_tests: tuple[str, ...] = field(default_factory=tuple)
    static_checks: tuple[str, ...] = field(default_factory=tuple)
    forbidden_actions: tuple[str, ...] = field(default_factory=tuple)
    requested_actions: tuple[str, ...] = field(default_factory=tuple)
    requires_independent_review: bool = True
    requires_human_approval: bool = False

    def __post_init__(self) -> None:
        if not self.task_id:
            raise ValueError("task_id は空にできません")
        if not self.purpose:
            raise ValueError("purpose は空にできません")
        if not self.expected_head:
            raise ValueError(
                f"expected_head は空にできません({RUNTIME_HEAD_SENTINEL!r}"
                "[Runtime HEAD Pinning]または明示的な40桁SHAのいずれかを指定してください)"
            )
        if not self.allowed_files:
            raise ValueError("allowed_files は空にできません(最低1件のScopeを明示する)")
        overlap = sorted(set(self.allowed_files) & set(self.frozen_files))
        if overlap:
            raise ValueError(f"allowed_files と frozen_files が重複しています: {overlap}")

    @staticmethod
    def from_dict(data: dict[str, Any]) -> TaskManifest:
        return TaskManifest(
            task_id=str(data["task_id"]),
            purpose=str(data["purpose"]),
            expected_head=str(data.get("expected_head", RUNTIME_HEAD_SENTINEL) or RUNTIME_HEAD_SENTINEL),
            allowed_files=tuple(str(p) for p in data.get("allowed_files", [])),
            frozen_files=tuple(str(p) for p in data.get("frozen_files", [])),
            targeted_tests=tuple(str(p) for p in data.get("targeted_tests", [])),
            static_checks=tuple(str(p) for p in data.get("static_checks", [])),
            forbidden_actions=tuple(str(p) for p in data.get("forbidden_actions", [])),
            requested_actions=tuple(str(p) for p in data.get("requested_actions", [])),
            requires_independent_review=bool(data.get("requires_independent_review", True)),
            requires_human_approval=bool(data.get("requires_human_approval", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "purpose": self.purpose,
            "expected_head": self.expected_head,
            "allowed_files": list(self.allowed_files),
            "frozen_files": list(self.frozen_files),
            "targeted_tests": list(self.targeted_tests),
            "static_checks": list(self.static_checks),
            "forbidden_actions": list(self.forbidden_actions),
            "requested_actions": list(self.requested_actions),
            "requires_independent_review": self.requires_independent_review,
            "requires_human_approval": self.requires_human_approval,
        }


__all__ = [
    "ROLE_CAPABILITIES",
    "RUNTIME_HEAD_SENTINEL",
    "AcceptanceVerdict",
    "Capability",
    "Finding",
    "FindingStatus",
    "ReviewerVerdict",
    "Role",
    "Severity",
    "TaskManifest",
    "WorkflowState",
    "role_has_capability",
]
