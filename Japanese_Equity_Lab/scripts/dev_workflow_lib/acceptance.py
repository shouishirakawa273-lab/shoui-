"""DEV-AUTO-01 §11/§14: Deterministic Acceptance Gate + Closure Audit
Narrowing。LLM Score・確率はいずれも使用しない(Closed Rule Setのみ、
DEV-AUTO-01 §14「No LLM score. No probability.」)。
"""

from __future__ import annotations

from .human_gate import requires_human_approval
from .model import AcceptanceVerdict, Finding, FindingStatus, ReviewerVerdict, TaskManifest


def open_blocking_findings(findings: tuple[Finding, ...]) -> tuple[Finding, ...]:
    return tuple(f for f in findings if f.status == FindingStatus.OPEN and f.blocking)


def narrow_to_open_findings(findings: tuple[Finding, ...]) -> tuple[Finding, ...]:
    """DEV-AUTO-01 §11「Closure Efficiency」: 次のFix/Closure Auditが
    対象とすべき唯一の集合。既にCLOSEDのFindingは含めない(再監査
    しない)。Blocking/Non-Blockingを問わずOPENなFinding全てを返す
    (Non-Blockingでも次RoundでのTracking対象としては残す)。"""
    return tuple(f for f in findings if f.status == FindingStatus.OPEN)


def evaluate_acceptance(
    *,
    manifest: TaskManifest,
    reviewer_verdict: ReviewerVerdict | None,
    findings: tuple[Finding, ...],
    tests_passed: bool,
    static_checks_passed: bool,
    scope_clean: bool,
) -> AcceptanceVerdict:
    """DEV-AUTO-01 §14の決定論的Rule。優先順位(先に該当した方を採用、
    Hidden Weighting無し):

    1. Human Approval Boundary該当 → HUMAN_APPROVAL_REQUIRED
    2. Reviewer Verdict = STOP → STOP
    3. Blocking FindingがOPEN → FIX_REQUIRED
    4. Reviewer Verdict = NEEDS_FIX → FIX_REQUIRED
    5. Test/Static Gate/Scopeのいずれか失敗 → FIX_REQUIRED
    6. Independent Review必須なのにReviewer Verdict != ACCEPTED
       → FIX_REQUIRED
    7. 上記いずれにも該当しない → ACCEPT
    """
    if requires_human_approval(manifest) is not None:
        return AcceptanceVerdict.HUMAN_APPROVAL_REQUIRED

    if reviewer_verdict == ReviewerVerdict.STOP:
        return AcceptanceVerdict.STOP

    if open_blocking_findings(findings):
        return AcceptanceVerdict.FIX_REQUIRED

    if reviewer_verdict == ReviewerVerdict.NEEDS_FIX:
        return AcceptanceVerdict.FIX_REQUIRED

    if not tests_passed or not static_checks_passed or not scope_clean:
        return AcceptanceVerdict.FIX_REQUIRED

    if manifest.requires_independent_review and reviewer_verdict != ReviewerVerdict.ACCEPTED:
        return AcceptanceVerdict.FIX_REQUIRED

    return AcceptanceVerdict.ACCEPT


__all__ = ["evaluate_acceptance", "narrow_to_open_findings", "open_blocking_findings"]
