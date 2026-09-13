"""DEV-AUTO-01 §13: Task ManifestからRole別Prompt Templateを機械的に
生成する(手作業でRoundごとに書き直さない)。生成される文字列は
いずれも以下を必ず含む: 期待HEAD・許可Fileリスト・Frozen Fileリスト・
禁止Action・対象Test・Acceptance基準。Reviewer向けTemplateは必ず
"READ ONLY"を明示する(DEV-AUTO-01 §13)。

DEV-AUTO-02.4 §1/§5/§6: Host-Side Validation Boundary。実D0103 Writer
Runで、Writer自身(Agent)がManifestのTargeted Tests/Static Checksを
自分のNoninteractive Claude CLI Subprocess内で実行しようとし、
Global Python PATH(Repository-Local`.venv`ではない)しか見えずruff/
mypyを実行できなかった。Writer/Reviewerに`manifest.targeted_tests`/
`static_checks`を自ら実行させる責任を課すのをやめ、Host(Orchestrator
Process自身、`host_validation.py`)が実行した結果のみをReviewer
Promptへ注入する設計へ変更した。Writerは「実装・変更内容の報告」
のみを、Reviewerは「Host Validation結果を踏まえた意味論的Review」
のみを担う(Agent Shell権限を再び広げるのではなく、Validation
Execution自体をAgentの責務から外すArchitecturalな解決、DEV-AUTO-02.4
§1)。
"""

from __future__ import annotations

from .host_validation import CommandResult, ValidationResult
from .model import Finding, TaskManifest

# DEV-AUTO-02.4 §5: WriterがHost Validation実行前に`tests`/
# `static_checks`Fieldへ書く、Fabricated PASS/FAILを防ぐための唯一の
# Sanctioned値。Writerがこれ以外の断定的な結果文言(例:
# "All tests passed")を書いた場合でも、Orchestrator自身は
# `WriterResult.tests`/`static_checks`の中身をAcceptance判定に一切
# 使わない(判定は常にHost自身が実行した`ValidationResult`のみに
# 基づく、DEV-AUTO-02.4 §1)ため、Writerの自己申告Fabricationが
# Acceptanceへ影響する経路は構造的に存在しない。
HOST_VALIDATION_PENDING = "host validation pending (host orchestrator runs it, not the Agent)"


def _bulleted(label: str, items: tuple[str, ...]) -> list[str]:
    if not items:
        return []
    return [f"{label}:", *[f"  - {item}" for item in items]]


# DEV-AUTO-02.4 §7: `claude --help`に実際のStructured-Output機能
# (`--json-schema`)が存在することを確認し、Executor Config側で
# `--json-schema`を設定して主たるContract Enforcementとする
# (`executor_config.example.json`参照)。それでもPrompt側の指示文言は
# 削除せず、`--json-schema`未設定の将来Executor・Fallback Path双方への
# 備えとして強化する(Fenced JSON誤発生の実例[実D0103 Writer Run]を
# 踏まえ、明示的に禁止する)。Parser Contract自体(LAST行JSON・厳密
# Parse・Fail Closed)は変更しない。
_STRICT_OUTPUT_INSTRUCTIONS = (
    "FINAL OUTPUT MUST BE ONE RAW JSON OBJECT ON THE FINAL LINE.\n"
    "DO NOT USE MARKDOWN.\n"
    "DO NOT USE ```json FENCES.\n"
    "DO NOT WRITE ANY TEXT AFTER THE JSON OBJECT.\n"
)

_WRITER_RESULT_FORMAT = (
    "- Report your result as the LAST line of your output, as a single JSON object with exactly "
    'these fields: status ("SUCCESS" or "FAILED"), files_changed (array of repo-relative paths), '
    "tests (short text summary), static_checks (short text summary), blocking_issue "
    "(string, or null if none), summary (short text). Do not add any other top-level field.\n" + _STRICT_OUTPUT_INSTRUCTIONS
)

_REVIEWER_RESULT_FORMAT = (
    "- Report your result as the LAST line of your output, as a single JSON object with exactly "
    'these fields: status ("COMPLETED"), verdict ("ACCEPTED", "NEEDS_FIX", or "STOP"), findings '
    "(array of objects, each with finding_id, severity [HIGH/MEDIUM/LOW/NOTE], status [OPEN/CLOSED], "
    "summary, location, reproducer, expected, actual, blocking [true/false]). Do not add any other "
    "top-level field.\n" + _STRICT_OUTPUT_INSTRUCTIONS
)


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
        *_bulleted("Targeted tests (run by the HOST orchestrator, not by you)", manifest.targeted_tests),
        *_bulleted("Static checks (run by the HOST orchestrator, not by you)", manifest.static_checks),
    ]
    return "\n".join(line for line in lines if line is not None)


def _tail(text: str, *, max_chars: int = 500) -> str:
    stripped = text.strip()
    if not stripped:
        return "(empty)"
    if len(stripped) <= max_chars:
        return stripped
    return "...(truncated)...\n" + stripped[-max_chars:]


def _format_command_result(label: str, result: CommandResult) -> list[str]:
    outcome = "TIMEOUT" if result.timed_out else ("PASS" if result.passed else "FAIL")
    lines = [f"  - [{label}] `{result.command}` -> {outcome} (exit {result.returncode})"]
    if not result.passed:
        lines.append(f"      stdout: {_tail(result.stdout)}")
        if result.stderr.strip():
            lines.append(f"      stderr: {_tail(result.stderr)}")
    return lines


def _format_validation_result(validation_result: ValidationResult) -> str:
    """DEV-AUTO-02.4 §6: Host(`host_validation.run_manifest_validation`)
    が既に実行した`targeted_tests`/`static_checks`のCommand・Pass/Fail・
    簡潔なstdout/stderr要約をReviewer Promptへそのまま埋め込む。Reviewer
    はこれらを自ら再実行する必要が無い(かつ、その権限も持たない)。"""
    if validation_result.blocked_reason is not None:
        return f"## Host-Executed Validation Results\nBLOCKED before execution: {validation_result.blocked_reason}\n"

    if not validation_result.targeted_tests and not validation_result.static_checks:
        return "## Host-Executed Validation Results\n(no targeted_tests/static_checks were configured for this task)\n"

    lines = ["## Host-Executed Validation Results (already run by the host orchestrator; do NOT re-run these yourself)"]
    for result in validation_result.targeted_tests:
        lines.extend(_format_command_result("targeted test", result))
    for result in validation_result.static_checks:
        lines.extend(_format_command_result("static check", result))
    lines.append(f"Overall: {'PASS' if validation_result.passed else 'FAIL'}")
    return "\n".join(lines) + "\n"


def build_writer_prompt(manifest: TaskManifest) -> str:
    """DEV-AUTO-01 §2 WRITER: `CAN_EDIT_REPO`/`CAN_RUN_TESTS`のみ、
    High-Risk Stageを独自にFreezeする権限は持たない。

    DEV-AUTO-02.4 §5: WriterはTargeted Tests/Static Checksを自ら実行
    しない(実行はHost Orchestratorの責務、`host_validation.py`)。
    Writerの責務は「調査 (inspect) → 許可されたCode変更の実装 →
    変更内容の報告」のみであり、実行していないValidationのPASS/FAILを
    断定してはならない(Fabrication禁止)。"""
    return (
        f"{_common_header(manifest)}\n\n"
        "## Role: WRITER\n"
        "Capabilities: CAN_EDIT_REPO, CAN_RUN_TESTS\n\n"
        "- Verify the repository HEAD matches Expected HEAD before editing. STOP if it differs.\n"
        "- Edit only the files listed under Allowed files. Never touch files listed under Frozen files.\n"
        "- Never perform any action listed under Forbidden actions.\n"
        "- Do NOT run the Targeted tests or Static checks yourself. The HOST orchestrator runs them "
        "after you finish and reports the results to the Reviewer -- you do not need shell "
        "permission for pytest/ruff/mypy, and must not claim a PASS/FAIL you did not actually "
        f'observe. Set both the "tests" and "static_checks" fields in your result to exactly '
        f'"{HOST_VALIDATION_PENDING}".\n'
        "- You may not commit, push, or independently declare acceptance.\n" + _WRITER_RESULT_FORMAT
    )


def build_reviewer_prompt(manifest: TaskManifest, validation_result: ValidationResult = ValidationResult()) -> str:
    """DEV-AUTO-01 §2/§10 REVIEWER: `CAN_REVIEW_READ_ONLY`のみ、Edit/
    Stage/Commit/Push権限は一切持たない(必ずREAD ONLYと明示する)。

    DEV-AUTO-02.4 §6: ReviewerはTargeted Tests/Static Checksを自ら
    実行しない(実行はHost Orchestratorの責務)。`validation_result`
    (Hostが既に実行した結果)をPromptへ直接注入し、Reviewerは
    その結果と選択されたTestの十分性を意味論的に判断する。
    `validation_result`省略時(Dry-Run Preview等、実行前)は空の
    `ValidationResult()`を渡す。"""
    return (
        f"{_common_header(manifest)}\n\n"
        "## Role: REVIEWER - READ ONLY\n"
        "Capabilities: CAN_REVIEW_READ_ONLY, CAN_RUN_TESTS\n\n"
        "READ ONLY: you must NOT edit, stage, commit, or push any file, and must NOT run any "
        "action listed under Forbidden actions.\n"
        "- Independently inspect the diff and the current repository state; do not merely trust "
        "the writer's summary of what changed.\n"
        f"{_format_validation_result(validation_result)}"
        "- Do NOT re-run the targeted tests or static checks yourself; use the Host-Executed "
        "Validation Results above. You MAY independently judge whether the selected tests/checks "
        "are actually sufficient evidence for the task's specific correctness claim -- if not, "
        "say so as a finding.\n"
        "- Classify each finding using severity HIGH/MEDIUM/LOW/NOTE and mark it blocking or "
        "not blocking. A FAIL in the Host-Executed Validation Results above must be reported as "
        "at least one blocking finding.\n"
        "- Return one verdict: ACCEPTED, NEEDS_FIX, or STOP.\n" + _REVIEWER_RESULT_FORMAT
    )


def build_closure_writer_prompt(manifest: TaskManifest, open_blocking_findings: tuple[Finding, ...]) -> str:
    """DEV-AUTO-02 §1/§8: Fix Round専用のNarrow Writer Prompt。渡された
    `open_blocking_findings`(通常`open_blocking_findings()`の戻り値)
    のみをFix対象として明示し、既にCLOSEDのFinding・非Blocking
    Findingへは触れないよう指示する(Closure Efficiency、DEV-AUTO-01
    §11をFix側にも適用する)。

    DEV-AUTO-02.4 §5: 初回Writerと同様、Targeted Tests/Static Checksは
    自ら実行しない(Fix後、Host Orchestratorが再実行する、§4)。"""
    if open_blocking_findings:
        finding_lines = [
            f"  - {f.finding_id} [{f.severity.value}]: {f.summary}\n"
            f"      location: {f.location}\n"
            f"      expected: {f.expected}\n"
            f"      actual: {f.actual}"
            for f in open_blocking_findings
        ]
    else:
        finding_lines = ["  (no specific blocking finding was provided; see Targeted tests/Static checks above)"]
    return (
        f"{_common_header(manifest)}\n\n"
        "## Role: WRITER (Closure Round)\n"
        "Capabilities: CAN_EDIT_REPO, CAN_RUN_TESTS\n\n"
        "- Verify the repository HEAD matches Expected HEAD before editing. STOP if it differs.\n"
        "- Edit only the files listed under Allowed files. Never touch files listed under Frozen files.\n"
        "- Fix ONLY the following remaining OPEN blocking findings. Do not make unrelated changes:\n"
        + "\n".join(finding_lines)
        + "\n"
        "- Do not re-open or re-litigate any finding not listed above.\n"
        "- Do NOT run the Targeted tests or Static checks yourself. The HOST orchestrator re-runs "
        "them after you finish and reports the results to the Closure Reviewer -- you do not need "
        f'shell permission for pytest/ruff/mypy. Set both the "tests" and "static_checks" fields '
        f'in your result to exactly "{HOST_VALIDATION_PENDING}".\n'
        "- You may not commit, push, or independently declare acceptance.\n" + _WRITER_RESULT_FORMAT
    )


def build_closure_reviewer_prompt(
    manifest: TaskManifest,
    open_findings: tuple[Finding, ...],
    validation_result: ValidationResult = ValidationResult(),
) -> str:
    """DEV-AUTO-01 §11 Closure Efficiency: 既にCLOSEDのFindingは一切
    含めない——渡された`open_findings`(通常`narrow_to_open_findings()`
    の戻り値)のみを再検証対象として明示する。

    DEV-AUTO-02.4 §6: Closure Writer Fix後にHostが再実行した
    `validation_result`をPromptへ注入する(§4「Closure Writer → HOST
    validation again → Closure Reviewer」)。"""
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
        f"{_format_validation_result(validation_result)}"
        "- Do NOT re-run the targeted tests or static checks yourself; use the Host-Executed "
        "Validation Results above. A FAIL there must be reflected as at least one OPEN blocking "
        "finding.\n"
        "- Return, for each listed finding above, an entry in findings with the SAME finding_id "
        "and its updated status (CLOSED or OPEN), plus one overall verdict: ACCEPTED, NEEDS_FIX, "
        "or STOP.\n" + _REVIEWER_RESULT_FORMAT
    )


__all__ = [
    "HOST_VALIDATION_PENDING",
    "build_closure_reviewer_prompt",
    "build_closure_writer_prompt",
    "build_reviewer_prompt",
    "build_writer_prompt",
]
