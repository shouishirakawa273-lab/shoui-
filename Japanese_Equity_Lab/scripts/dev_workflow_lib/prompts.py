"""DEV-AUTO-01 §13: Task ManifestからRole別Prompt Templateを機械的に
生成する(手作業でRoundごとに書き直さない)。生成される文字列は
いずれも以下を必ず含む: 期待HEAD・許可Fileリスト・Frozen Fileリスト・
禁止Action・対象Test・Acceptance基準。Reviewer向けTemplateは必ず
"READ ONLY"を明示する(DEV-AUTO-01 §13)。
"""

from __future__ import annotations

from .model import Finding, TaskManifest


def _bulleted(label: str, items: tuple[str, ...]) -> list[str]:
    if not items:
        return []
    return [f"{label}:", *[f"  - {item}" for item in items]]


def _common_header(manifest: TaskManifest) -> str:
    lines = [
        f"# Task: {manifest.task_id}",
        f"# Purpose: {manifest.purpose}",
        "",
        f"Expected HEAD: {manifest.expected_head}",
        "",
        *_bulleted("Allowed files", manifest.allowed_files),
        *_bulleted("Frozen files (must NOT change)", manifest.frozen_files),
        *_bulleted("Forbidden actions", manifest.forbidden_actions),
        *_bulleted("Targeted tests", manifest.targeted_tests),
        *_bulleted("Static checks", manifest.static_checks),
    ]
    return "\n".join(line for line in lines if line is not None)


def build_writer_prompt(manifest: TaskManifest) -> str:
    """DEV-AUTO-01 §2 WRITER: `CAN_EDIT_REPO`/`CAN_RUN_TESTS`のみ、
    High-Risk Stageを独自にFreezeする権限は持たない。"""
    return (
        f"{_common_header(manifest)}\n\n"
        "## Role: WRITER\n"
        "Capabilities: CAN_EDIT_REPO, CAN_RUN_TESTS\n\n"
        "- Verify the repository HEAD matches Expected HEAD before editing. STOP if it differs.\n"
        "- Edit only the files listed under Allowed files. Never touch files listed under Frozen files.\n"
        "- Never perform any action listed under Forbidden actions.\n"
        "- Run every test listed under Targeted tests and every check listed under Static checks "
        "before reporting the change as done.\n"
        "- You may not commit, push, or independently declare acceptance. Report your diff and "
        "test/static results for review.\n"
    )


def build_reviewer_prompt(manifest: TaskManifest) -> str:
    """DEV-AUTO-01 §2/§10 REVIEWER: `CAN_REVIEW_READ_ONLY`のみ、Edit/
    Stage/Commit/Push権限は一切持たない(必ずREAD ONLYと明示する)。"""
    return (
        f"{_common_header(manifest)}\n\n"
        "## Role: REVIEWER - READ ONLY\n"
        "Capabilities: CAN_REVIEW_READ_ONLY, CAN_RUN_TESTS\n\n"
        "READ ONLY: you must NOT edit, stage, commit, or push any file, and must NOT run any "
        "action listed under Forbidden actions.\n"
        "- Independently inspect the diff and the current repository state; do not merely trust "
        "the writer's summary of what changed.\n"
        "- Probe the stated acceptance boundary directly (targeted tests, static checks, and the "
        "task's specific correctness claim).\n"
        "- Classify each finding using severity HIGH/MEDIUM/LOW/NOTE and mark it blocking or "
        "not blocking.\n"
        "- Return one verdict: ACCEPTED, NEEDS_FIX, or STOP.\n"
    )


def build_closure_reviewer_prompt(manifest: TaskManifest, open_findings: tuple[Finding, ...]) -> str:
    """DEV-AUTO-01 §11 Closure Efficiency: 既にCLOSEDのFindingは一切
    含めない——渡された`open_findings`(通常`narrow_to_open_findings()`
    の戻り値)のみを再検証対象として明示する。"""
    if open_findings:
        finding_lines = [f"  - {f.finding_id} [{f.severity.value}]: {f.summary}" for f in open_findings]
    else:
        finding_lines = ["  (none - nothing remains open)"]
    return (
        f"{_common_header(manifest)}\n\n"
        "## Role: CLOSURE REVIEWER - READ ONLY\n"
        "Capabilities: CAN_REVIEW_READ_ONLY, CAN_RUN_TESTS\n\n"
        "READ ONLY: you must NOT edit, stage, commit, or push any file.\n"
        "- Do NOT re-audit findings that are already CLOSED.\n"
        "- Re-test ONLY the following remaining OPEN findings:\n" + "\n".join(finding_lines) + "\n"
        "- Do not restart a full/broad audit unless this fix changed shared architecture that "
        "the original findings did not cover.\n"
        "- Return, for each listed finding, CLOSED or OPEN, plus one overall verdict: "
        "ACCEPTED, NEEDS_FIX, or STOP.\n"
    )


__all__ = ["build_closure_reviewer_prompt", "build_reviewer_prompt", "build_writer_prompt"]
