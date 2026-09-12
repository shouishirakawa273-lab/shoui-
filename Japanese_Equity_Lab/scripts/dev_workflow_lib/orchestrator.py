"""DEV-AUTO-02 §1: Capability-Based Agent Execution Orchestrator。

`run_task()`が唯一のSanctioned Orchestration Flow。Open-endedな自律
Loopは実装しない——Closure Roundは`max_closure_rounds`(既定2)で
必ず打ち切り、超過すれば`HUMAN_ATTENTION_REQUIRED`を返す(DEV-AUTO-02
§7)。Human Approval Boundary(H0001含む)は最初にChecked、該当すれば
**いかなるAgentも一切実行しない**(DEV-AUTO-02 §9)。Reviewer実行は
実行前後のGit状態Snapshotを比較し、差分があれば無条件に`STOP`する
(DEV-AUTO-02 §6、Reviewerの評決自体を信用しない)。
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from uuid import uuid4

from .acceptance import evaluate_acceptance, narrow_to_open_findings, open_blocking_findings
from .agent_results import ReviewerResult, WriterResult, WriterStatus
from .executor import AgentExecutionResult, AgentExecutor, ExecutionCapability, ExecutorRegistry
from .gates import GateResult, check_expected_head, check_scope, list_changed_paths, resolve_head
from .human_gate import requires_human_approval
from .model import RUNTIME_HEAD_SENTINEL, AcceptanceVerdict, Finding, Role, TaskManifest
from .prompts import build_closure_reviewer_prompt, build_closure_writer_prompt, build_reviewer_prompt, build_writer_prompt
from .run_record import ExecutionDiagnostics, RunRecord, RunState, save_run_record

MAX_CLOSURE_ROUNDS = 2


class OrchestratorOutcome(StrEnum):
    ACCEPT_CANDIDATE = "ACCEPT_CANDIDATE"
    STOP = "STOP"
    HUMAN_APPROVAL_REQUIRED = "HUMAN_APPROVAL_REQUIRED"
    HUMAN_ATTENTION_REQUIRED = "HUMAN_ATTENTION_REQUIRED"
    DRY_RUN = "DRY_RUN"


@dataclass(kw_only=True, frozen=True)
class DryRunReport:
    """DEV-AUTO-02 §11。Agentを一切呼び出さずに生成する完全なPreview。

    `resolved_starting_head`(DEV-AUTO-02.1.1 §10): Runtime HEAD Pinning
    (`expected_head == RUNTIME_HEAD_SENTINEL`)が選択されている場合でも
    実際にPinされたSHAをそのまま確認できるよう、解決済みの値を明示的に
    保持する(明示的SHA指定の場合はそのSHA自身が入る)。"""

    manifest_task_id: str
    human_gate_reason: str | None
    resolved_starting_head: str
    head_check: GateResult
    scope_check: GateResult
    writer_prompt: str
    reviewer_prompt: str
    writer_command_preview: tuple[str, ...] | None
    reviewer_command_preview: tuple[str, ...] | None


@dataclass(kw_only=True, frozen=True)
class OrchestratorResult:
    outcome: OrchestratorOutcome
    reason: str
    run_record: RunRecord
    acceptance_verdict: AcceptanceVerdict | None = None
    dry_run_report: DryRunReport | None = None
    executor_invocations: int = 0


def _safe_execute(executor: AgentExecutor, *, role: Role, prompt: str, working_directory: Path) -> AgentExecutionResult:
    """Executorが直接Exceptionを送出した場合でもOrchestrator自体を
    Crashさせず、構造化された失敗Resultへ変換する(DEV-AUTO-02 §1、
    Writer/Reviewer実行の失敗はいずれもTyped Resultとして扱い、生
    Exceptionを外へ漏らさない)。`LocalCommandExecutor`自体は既に
    Subprocess例外を内部でCatch済みだが、Protocol契約に反してException
    を送出するCustom Executor実装にも備える。"""
    try:
        return executor.execute(role=role, prompt=prompt, working_directory=working_directory)
    except Exception as exc:  # noqa: BLE001 -- 意図的なBroad Catch(Executor実装の異常系をTyped Resultへ変換する)。
        return AgentExecutionResult(returncode=-1, stdout="", stderr=f"executor raised {type(exc).__name__}: {exc}")


def _resolve_manifest_head(manifest: TaskManifest, *, repo_root: Path) -> TaskManifest:
    """DEV-AUTO-02.1.1 §2: `expected_head`がRuntime HEAD Pinning
    Sentinel(`RUNTIME_HEAD_SENTINEL`)であれば、この瞬間のGit HEADを
    一度だけ`resolve_head()`で読み取り、それを`expected_head`とする
    新しい`TaskManifest`を返す(元のManifestは変更しない、Frozen
    Dataclass)。以降そのRunでは呼び出し側が返り値のManifestだけを
    使い続けることで、starting_headがWriter/Reviewer/全Closure Round
    を通じてImmutableであることを保証する(§9「Do NOT repin HEAD
    between rounds」)。明示的な40桁SHAが指定されている場合は無変更で
    そのまま返す(Sentinelの再解釈をしない、§3 Backward
    Compatibility)。"""
    if manifest.expected_head != RUNTIME_HEAD_SENTINEL:
        return manifest
    resolved_head = resolve_head(repo_root)
    return replace(manifest, expected_head=resolved_head)


def _preview_command(executor: AgentExecutor | None) -> tuple[str, ...] | None:
    command = getattr(executor, "command", None)
    if isinstance(command, tuple) and all(isinstance(part, str) for part in command):
        return command
    return None


def run_targeted_validation(commands: tuple[str, ...], *, repo_root: Path, timeout_seconds: float = 900.0) -> GateResult:
    """`manifest.targeted_tests`/`manifest.static_checks`の各Entryを
    Shell Commandとして実行する。Manifestは人間が作成・管理する信頼済み
    Configurationであり(任意の外部/未検証入力ではない)、CI Config
    (`run:` Step)と同種の前提を置く。空Listは無条件でPASS扱い
    (DEV-AUTO-01からの既存契約、`tests_passed`/`static_checks_passed`
    は呼び出し側があらかじめ確定させる値という設計を、ここでは
    Command文字列を実行することで具体化する)。"""
    if not commands:
        return GateResult(passed=True, reason="no commands configured")
    for command in commands:
        try:
            completed = subprocess.run(
                command,
                shell=True,  # noqa: S602 -- Manifestは人間が管理するTrusted Configuration(CI Config相当)。
                cwd=repo_root,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return GateResult(passed=False, reason=f"command timed out: {command}")
        if completed.returncode != 0:
            return GateResult(
                passed=False,
                reason=f"command failed (exit {completed.returncode}): {command}\n{completed.stdout}\n{completed.stderr}",
            )
    return GateResult(passed=True, reason="all commands passed")


def _merge_closure_findings(current: tuple[Finding, ...], closure_updates: tuple[Finding, ...]) -> tuple[Finding, ...]:
    updates_by_id = {f.finding_id: f for f in closure_updates}
    current_ids = {f.finding_id for f in current}
    merged = tuple(updates_by_id.get(f.finding_id, f) for f in current)
    new_findings = tuple(f for f in closure_updates if f.finding_id not in current_ids)
    return merged + new_findings


def _build_dry_run_report(
    manifest: TaskManifest,
    *,
    repo_root: Path,
    executors: ExecutorRegistry,
) -> DryRunReport:
    return DryRunReport(
        manifest_task_id=manifest.task_id,
        human_gate_reason=requires_human_approval(manifest),
        resolved_starting_head=manifest.expected_head,
        head_check=check_expected_head(repo_root, manifest.expected_head),
        scope_check=check_scope(repo_root, allowed_files=manifest.allowed_files, frozen_files=manifest.frozen_files),
        writer_prompt=build_writer_prompt(manifest),
        reviewer_prompt=build_reviewer_prompt(manifest),
        writer_command_preview=_preview_command(executors.get(ExecutionCapability.CAN_EXECUTE_WRITER)),
        reviewer_command_preview=_preview_command(executors.get(ExecutionCapability.CAN_EXECUTE_READ_ONLY_REVIEWER)),
    )


def run_task(
    *,
    manifest: TaskManifest,
    repo_root: Path,
    executors: ExecutorRegistry,
    runs_dir: Path,
    run_id: str | None = None,
    dry_run: bool = False,
    max_closure_rounds: int = MAX_CLOSURE_ROUNDS,
) -> OrchestratorResult:
    """DEV-AUTO-02 §1の唯一のSanctioned Orchestration Flow。"""
    run_id = run_id or f"run-{uuid4().hex[:12]}"
    invocations = 0

    # DEV-AUTO-02.1.1 §2: Runtime HEAD Pinningの解決はここ1箇所のみで
    # 行う(Dry-Run/本実行いずれもこの直後の`manifest`を使う)。以降この
    # 関数内では常にこの解決済み`manifest`のみを参照し、再解決は行わない
    # (§9「Do NOT repin HEAD between rounds」)。明示的なSHA指定の場合は
    # 無変更のまま返る(§3 Backward Compatibility)。
    manifest = _resolve_manifest_head(manifest, repo_root=repo_root)

    def _record(
        state: RunState,
        *,
        reason: str = "",
        writer_result: WriterResult | None = None,
        review_result: ReviewerResult | None = None,
        open_findings: tuple[Finding, ...] = (),
        closure_round: int = 0,
        writer_execution: ExecutionDiagnostics | None = None,
        reviewer_execution: ExecutionDiagnostics | None = None,
        closure_writer_executions: tuple[ExecutionDiagnostics, ...] = (),
        closure_reviewer_executions: tuple[ExecutionDiagnostics, ...] = (),
    ) -> RunRecord:
        record = RunRecord(
            run_id=run_id,
            task_id=manifest.task_id,
            starting_head=manifest.expected_head,
            state=state,
            writer_result=writer_result,
            review_result=review_result,
            open_findings=open_findings,
            closure_round=closure_round,
            reason=reason,
            writer_execution=writer_execution,
            reviewer_execution=reviewer_execution,
            closure_writer_executions=closure_writer_executions,
            closure_reviewer_executions=closure_reviewer_executions,
        )
        save_run_record(record, runs_dir=runs_dir)
        return record

    # DEV-AUTO-02 §11: Dry-Runは常にAgentを一切呼び出さず、Manifest/両
    # Prompt/Command Preview/Human Gate/Acceptance Logicの完全なPreview
    # を返す(Executor未設定でも常に完走する)。
    if dry_run:
        report = _build_dry_run_report(manifest, repo_root=repo_root, executors=executors)
        record = _record(RunState.DRY_RUN, reason="dry-run: no agent invoked")
        return OrchestratorResult(
            outcome=OrchestratorOutcome.DRY_RUN,
            reason="dry-run completed; zero agent invocations",
            run_record=record,
            dry_run_report=report,
            executor_invocations=0,
        )

    # DEV-AUTO-02 §9: いかなるAgent実行より先にHuman Approval Boundaryを
    # 確認する。該当すれば無条件にここで停止し、Writer/Reviewerいずれも
    # 一切呼び出さない(No agent may bypass this)。
    human_gate_reason = requires_human_approval(manifest)
    if human_gate_reason is not None:
        record = _record(RunState.HUMAN_APPROVAL_REQUIRED, reason=human_gate_reason)
        return OrchestratorResult(
            outcome=OrchestratorOutcome.HUMAN_APPROVAL_REQUIRED,
            reason=human_gate_reason,
            run_record=record,
            executor_invocations=0,
        )

    # DEV-AUTO-02 §1 Step1: Repository Validation(既存Head/Scope Gate)。
    head_result = check_expected_head(repo_root, manifest.expected_head)
    if not head_result.passed:
        record = _record(RunState.REPOSITORY_GATE_FAILED, reason=head_result.reason)
        return OrchestratorResult(outcome=OrchestratorOutcome.STOP, reason=head_result.reason, run_record=record)

    writer_executor = executors.get(ExecutionCapability.CAN_EXECUTE_WRITER)
    reviewer_executor = executors.get(ExecutionCapability.CAN_EXECUTE_READ_ONLY_REVIEWER)
    if writer_executor is None:
        reason = "no executor configured for CAN_EXECUTE_WRITER"
        record = _record(RunState.STOPPED, reason=reason)
        return OrchestratorResult(outcome=OrchestratorOutcome.STOP, reason=reason, run_record=record)
    if reviewer_executor is None:
        reason = "no executor configured for CAN_EXECUTE_READ_ONLY_REVIEWER"
        record = _record(RunState.STOPPED, reason=reason)
        return OrchestratorResult(outcome=OrchestratorOutcome.STOP, reason=reason, run_record=record)

    # DEV-AUTO-02.1.1 §7 Writer Gate: Writer実行の直前にもう一度、
    # Repository HEADがPin済みの`starting_head`(`manifest.expected_head`
    # 、Step1と同じImmutable値)からDriftしていないことを確認する。
    # Step1の確認からここまでの間にHEADが変化していればWriterを一切
    # 実行せずSTOPする(Zero Writer Invocation)。
    pre_writer_head_check = check_expected_head(repo_root, manifest.expected_head)
    if not pre_writer_head_check.passed:
        record = _record(RunState.REPOSITORY_GATE_FAILED, reason=pre_writer_head_check.reason)
        return OrchestratorResult(outcome=OrchestratorOutcome.STOP, reason=pre_writer_head_check.reason, run_record=record)

    # ---- Writer ----
    _record(RunState.WRITER_RUNNING)
    writer_prompt = build_writer_prompt(manifest)
    writer_exec_result = _safe_execute(writer_executor, role=Role.WRITER, prompt=writer_prompt, working_directory=repo_root)
    invocations += 1
    # DEV-AUTO-02.2.2 §1/§3: WriterResult.from_raw_output()のParse成否に
    # 関わらず(成功・失敗どちらの経路でもSTOPする経路でも)、実行直後の
    # 生Diagnosticsを必ずRunRecordへ渡す(Parse失敗Caseで唯一Raw stdoutを
    # 診断できる情報源になる)。
    writer_diag = ExecutionDiagnostics.from_execution_result(writer_exec_result)
    if writer_exec_result.returncode != 0 or writer_exec_result.timed_out:
        reason = f"writer execution failed (returncode={writer_exec_result.returncode}, timed_out={writer_exec_result.timed_out})"
        record = _record(RunState.WRITER_FAILED, reason=reason, writer_execution=writer_diag)
        return OrchestratorResult(
            outcome=OrchestratorOutcome.STOP, reason=reason, run_record=record, executor_invocations=invocations
        )

    try:
        writer_result = WriterResult.from_raw_output(writer_exec_result.stdout)
    except ValueError as exc:
        reason = f"malformed writer result: {exc}"
        record = _record(RunState.WRITER_FAILED, reason=reason, writer_execution=writer_diag)
        return OrchestratorResult(
            outcome=OrchestratorOutcome.STOP, reason=reason, run_record=record, executor_invocations=invocations
        )
    if writer_result.status != WriterStatus.SUCCESS:
        reason = f"writer reported FAILED: {writer_result.blocking_issue or writer_result.summary}"
        record = _record(RunState.WRITER_FAILED, reason=reason, writer_result=writer_result, writer_execution=writer_diag)
        return OrchestratorResult(
            outcome=OrchestratorOutcome.STOP, reason=reason, run_record=record, executor_invocations=invocations
        )
    _record(RunState.WRITER_DONE, writer_result=writer_result, writer_execution=writer_diag)

    # DEV-AUTO-02 §10: Acceptance前のScope Gate(Frozen File未変更・
    # Allowed File範囲内)を必ず確認する——Writer出力を無条件に信頼しない。
    scope_result = check_scope(repo_root, allowed_files=manifest.allowed_files, frozen_files=manifest.frozen_files)
    if not scope_result.passed:
        record = _record(RunState.STOPPED, reason=scope_result.reason, writer_result=writer_result, writer_execution=writer_diag)
        return OrchestratorResult(
            outcome=OrchestratorOutcome.STOP, reason=scope_result.reason, run_record=record, executor_invocations=invocations
        )

    tests_result = run_targeted_validation(manifest.targeted_tests, repo_root=repo_root)
    static_result = run_targeted_validation(manifest.static_checks, repo_root=repo_root)

    # ---- Reviewer(Read-Only、実行前後のGit状態を比較する) ----
    # DEV-AUTO-02.1.1 §8 Reviewer Gate: Reviewer実行前にもPin済み
    # `starting_head`との一致を確認する(HEADが既にDriftしていれば
    # Reviewerを一切実行せずSTOPする)。
    pre_review_head_check = check_expected_head(repo_root, manifest.expected_head)
    if not pre_review_head_check.passed:
        record = _record(
            RunState.REPOSITORY_GATE_FAILED,
            reason=pre_review_head_check.reason,
            writer_result=writer_result,
            writer_execution=writer_diag,
        )
        return OrchestratorResult(
            outcome=OrchestratorOutcome.STOP,
            reason=pre_review_head_check.reason,
            run_record=record,
            executor_invocations=invocations,
        )
    pre_review_tracked, pre_review_untracked = list_changed_paths(repo_root)
    pre_review_head = pre_review_head_check.reason

    _record(RunState.REVIEWING, writer_result=writer_result, writer_execution=writer_diag)
    reviewer_prompt = build_reviewer_prompt(manifest)
    reviewer_exec_result = _safe_execute(
        reviewer_executor, role=Role.REVIEWER, prompt=reviewer_prompt, working_directory=repo_root
    )
    invocations += 1
    reviewer_diag = ExecutionDiagnostics.from_execution_result(reviewer_exec_result)

    post_review_tracked, post_review_untracked = list_changed_paths(repo_root)
    post_review_head = check_expected_head(repo_root, manifest.expected_head).reason
    if (pre_review_tracked, pre_review_untracked, pre_review_head) != (
        post_review_tracked,
        post_review_untracked,
        post_review_head,
    ):
        reason = "reviewer modified the repository (git state changed); reviewer verdict rejected"
        record = _record(
            RunState.REVIEW_FAILED,
            reason=reason,
            writer_result=writer_result,
            writer_execution=writer_diag,
            reviewer_execution=reviewer_diag,
        )
        return OrchestratorResult(
            outcome=OrchestratorOutcome.STOP, reason=reason, run_record=record, executor_invocations=invocations
        )

    if reviewer_exec_result.returncode != 0 or reviewer_exec_result.timed_out:
        reason = (
            f"reviewer execution failed (returncode={reviewer_exec_result.returncode}, "
            f"timed_out={reviewer_exec_result.timed_out})"
        )
        record = _record(
            RunState.REVIEW_FAILED,
            reason=reason,
            writer_result=writer_result,
            writer_execution=writer_diag,
            reviewer_execution=reviewer_diag,
        )
        return OrchestratorResult(
            outcome=OrchestratorOutcome.STOP, reason=reason, run_record=record, executor_invocations=invocations
        )

    try:
        review_result = ReviewerResult.from_raw_output(reviewer_exec_result.stdout)
    except ValueError as exc:
        reason = f"malformed reviewer result: {exc}"
        record = _record(
            RunState.REVIEW_FAILED,
            reason=reason,
            writer_result=writer_result,
            writer_execution=writer_diag,
            reviewer_execution=reviewer_diag,
        )
        return OrchestratorResult(
            outcome=OrchestratorOutcome.STOP, reason=reason, run_record=record, executor_invocations=invocations
        )
    _record(
        RunState.REVIEW_DONE,
        writer_result=writer_result,
        review_result=review_result,
        writer_execution=writer_diag,
        reviewer_execution=reviewer_diag,
    )

    current_findings = review_result.findings
    verdict = evaluate_acceptance(
        manifest=manifest,
        reviewer_verdict=review_result.verdict,
        findings=current_findings,
        tests_passed=tests_result.passed,
        static_checks_passed=static_result.passed,
        scope_clean=scope_result.passed,
    )

    if verdict == AcceptanceVerdict.ACCEPT:
        record = _record(
            RunState.ACCEPT_CANDIDATE,
            writer_result=writer_result,
            review_result=review_result,
            writer_execution=writer_diag,
            reviewer_execution=reviewer_diag,
        )
        return OrchestratorResult(
            outcome=OrchestratorOutcome.ACCEPT_CANDIDATE,
            reason="all gates passed; reviewer accepted",
            run_record=record,
            acceptance_verdict=verdict,
            executor_invocations=invocations,
        )
    if verdict == AcceptanceVerdict.HUMAN_APPROVAL_REQUIRED:
        record = _record(
            RunState.HUMAN_APPROVAL_REQUIRED,
            writer_result=writer_result,
            review_result=review_result,
            writer_execution=writer_diag,
            reviewer_execution=reviewer_diag,
        )
        return OrchestratorResult(
            outcome=OrchestratorOutcome.HUMAN_APPROVAL_REQUIRED,
            reason="human approval boundary detected during acceptance evaluation",
            run_record=record,
            acceptance_verdict=verdict,
            executor_invocations=invocations,
        )
    if verdict == AcceptanceVerdict.STOP:
        record = _record(
            RunState.STOPPED,
            writer_result=writer_result,
            review_result=review_result,
            writer_execution=writer_diag,
            reviewer_execution=reviewer_diag,
        )
        return OrchestratorResult(
            outcome=OrchestratorOutcome.STOP,
            reason="reviewer verdict was STOP",
            run_record=record,
            acceptance_verdict=verdict,
            executor_invocations=invocations,
        )

    # ---- Bounded Closure Loop(DEV-AUTO-02 §7/§8) ----
    closure_round = 0
    # DEV-AUTO-02.2.2 §2: Closure Roundの実行Diagnosticsは、その時点までの
    # 全Roundを順にAppendする最小Tuple構造で保持する(Round番号は
    # `closure_round`のIndex[1-based]と一致するため、独自のRound Key
    # Dictを新設しない)。
    closure_writer_diagnostics: list[ExecutionDiagnostics] = []
    closure_reviewer_diagnostics: list[ExecutionDiagnostics] = []
    while closure_round < max_closure_rounds:
        closure_round += 1
        blockers = open_blocking_findings(current_findings)
        _record(
            RunState.CLOSURE_ROUND,
            closure_round=closure_round,
            open_findings=narrow_to_open_findings(current_findings),
            writer_execution=writer_diag,
            reviewer_execution=reviewer_diag,
            closure_writer_executions=tuple(closure_writer_diagnostics),
            closure_reviewer_executions=tuple(closure_reviewer_diagnostics),
        )

        # DEV-AUTO-02.1.1 §7/§9: Closure Roundごとのwriter実行直前にも
        # 同じPin済み`starting_head`との一致を確認する(§9「Do NOT repin
        # HEAD between rounds」——ここでは`manifest`を再解決せず、Run開始
        # 時点で一度だけPinされた同じ値との一致を毎Round確認するのみ)。
        closure_pre_writer_head_check = check_expected_head(repo_root, manifest.expected_head)
        if not closure_pre_writer_head_check.passed:
            record = _record(
                RunState.REPOSITORY_GATE_FAILED,
                reason=closure_pre_writer_head_check.reason,
                closure_round=closure_round,
                closure_writer_executions=tuple(closure_writer_diagnostics),
                closure_reviewer_executions=tuple(closure_reviewer_diagnostics),
            )
            return OrchestratorResult(
                outcome=OrchestratorOutcome.STOP,
                reason=closure_pre_writer_head_check.reason,
                run_record=record,
                executor_invocations=invocations,
            )

        closure_writer_prompt = build_closure_writer_prompt(manifest, blockers)
        closure_writer_exec = _safe_execute(
            writer_executor, role=Role.WRITER, prompt=closure_writer_prompt, working_directory=repo_root
        )
        invocations += 1
        # DEV-AUTO-02.2.2 §1/§3: このRoundのWriter Diagnosticsを、Parse
        # 成否に関わらずAccumulatorへ即座にAppendする(malformed Caseでも
        # このRoundのRaw stdout/stderrが必ずRecordへ残る)。
        closure_writer_diagnostics.append(ExecutionDiagnostics.from_execution_result(closure_writer_exec))
        if closure_writer_exec.returncode != 0 or closure_writer_exec.timed_out:
            reason = f"closure writer execution failed at round {closure_round}"
            record = _record(
                RunState.WRITER_FAILED,
                reason=reason,
                closure_round=closure_round,
                closure_writer_executions=tuple(closure_writer_diagnostics),
                closure_reviewer_executions=tuple(closure_reviewer_diagnostics),
            )
            return OrchestratorResult(
                outcome=OrchestratorOutcome.STOP, reason=reason, run_record=record, executor_invocations=invocations
            )
        try:
            closure_writer_result = WriterResult.from_raw_output(closure_writer_exec.stdout)
        except ValueError as exc:
            reason = f"malformed closure writer result at round {closure_round}: {exc}"
            record = _record(
                RunState.WRITER_FAILED,
                reason=reason,
                closure_round=closure_round,
                closure_writer_executions=tuple(closure_writer_diagnostics),
                closure_reviewer_executions=tuple(closure_reviewer_diagnostics),
            )
            return OrchestratorResult(
                outcome=OrchestratorOutcome.STOP, reason=reason, run_record=record, executor_invocations=invocations
            )
        if closure_writer_result.status != WriterStatus.SUCCESS:
            reason = f"closure writer reported FAILED at round {closure_round}"
            record = _record(
                RunState.WRITER_FAILED,
                reason=reason,
                writer_result=closure_writer_result,
                closure_round=closure_round,
                closure_writer_executions=tuple(closure_writer_diagnostics),
                closure_reviewer_executions=tuple(closure_reviewer_diagnostics),
            )
            return OrchestratorResult(
                outcome=OrchestratorOutcome.STOP, reason=reason, run_record=record, executor_invocations=invocations
            )

        scope_result = check_scope(repo_root, allowed_files=manifest.allowed_files, frozen_files=manifest.frozen_files)
        if not scope_result.passed:
            record = _record(
                RunState.STOPPED,
                reason=scope_result.reason,
                closure_round=closure_round,
                closure_writer_executions=tuple(closure_writer_diagnostics),
                closure_reviewer_executions=tuple(closure_reviewer_diagnostics),
            )
            return OrchestratorResult(
                outcome=OrchestratorOutcome.STOP, reason=scope_result.reason, run_record=record, executor_invocations=invocations
            )

        tests_result = run_targeted_validation(manifest.targeted_tests, repo_root=repo_root)
        static_result = run_targeted_validation(manifest.static_checks, repo_root=repo_root)

        # DEV-AUTO-02.1.1 §8/§9: Closure Reviewerの実行前にもPin済み
        # `starting_head`との一致を確認する。
        closure_pre_review_head_check = check_expected_head(repo_root, manifest.expected_head)
        if not closure_pre_review_head_check.passed:
            record = _record(
                RunState.REPOSITORY_GATE_FAILED,
                reason=closure_pre_review_head_check.reason,
                closure_round=closure_round,
                closure_writer_executions=tuple(closure_writer_diagnostics),
                closure_reviewer_executions=tuple(closure_reviewer_diagnostics),
            )
            return OrchestratorResult(
                outcome=OrchestratorOutcome.STOP,
                reason=closure_pre_review_head_check.reason,
                run_record=record,
                executor_invocations=invocations,
            )

        open_for_closure_review = narrow_to_open_findings(current_findings)
        pre_tracked, pre_untracked = list_changed_paths(repo_root)
        closure_reviewer_prompt = build_closure_reviewer_prompt(manifest, open_for_closure_review)
        closure_review_exec = _safe_execute(
            reviewer_executor, role=Role.REVIEWER, prompt=closure_reviewer_prompt, working_directory=repo_root
        )
        invocations += 1
        closure_reviewer_diagnostics.append(ExecutionDiagnostics.from_execution_result(closure_review_exec))
        post_tracked, post_untracked = list_changed_paths(repo_root)
        if (pre_tracked, pre_untracked) != (post_tracked, post_untracked):
            reason = f"closure reviewer modified the repository at round {closure_round}"
            record = _record(
                RunState.REVIEW_FAILED,
                reason=reason,
                closure_round=closure_round,
                closure_writer_executions=tuple(closure_writer_diagnostics),
                closure_reviewer_executions=tuple(closure_reviewer_diagnostics),
            )
            return OrchestratorResult(
                outcome=OrchestratorOutcome.STOP, reason=reason, run_record=record, executor_invocations=invocations
            )
        if closure_review_exec.returncode != 0 or closure_review_exec.timed_out:
            reason = f"closure reviewer execution failed at round {closure_round}"
            record = _record(
                RunState.REVIEW_FAILED,
                reason=reason,
                closure_round=closure_round,
                closure_writer_executions=tuple(closure_writer_diagnostics),
                closure_reviewer_executions=tuple(closure_reviewer_diagnostics),
            )
            return OrchestratorResult(
                outcome=OrchestratorOutcome.STOP, reason=reason, run_record=record, executor_invocations=invocations
            )
        try:
            closure_review_result = ReviewerResult.from_raw_output(closure_review_exec.stdout)
        except ValueError as exc:
            reason = f"malformed closure reviewer result at round {closure_round}: {exc}"
            record = _record(
                RunState.REVIEW_FAILED,
                reason=reason,
                closure_round=closure_round,
                closure_writer_executions=tuple(closure_writer_diagnostics),
                closure_reviewer_executions=tuple(closure_reviewer_diagnostics),
            )
            return OrchestratorResult(
                outcome=OrchestratorOutcome.STOP, reason=reason, run_record=record, executor_invocations=invocations
            )

        current_findings = _merge_closure_findings(current_findings, closure_review_result.findings)
        verdict = evaluate_acceptance(
            manifest=manifest,
            reviewer_verdict=closure_review_result.verdict,
            findings=current_findings,
            tests_passed=tests_result.passed,
            static_checks_passed=static_result.passed,
            scope_clean=scope_result.passed,
        )

        if verdict == AcceptanceVerdict.ACCEPT:
            record = _record(
                RunState.ACCEPT_CANDIDATE,
                writer_result=closure_writer_result,
                review_result=closure_review_result,
                closure_round=closure_round,
                closure_writer_executions=tuple(closure_writer_diagnostics),
                closure_reviewer_executions=tuple(closure_reviewer_diagnostics),
            )
            return OrchestratorResult(
                outcome=OrchestratorOutcome.ACCEPT_CANDIDATE,
                reason=f"accepted after closure round {closure_round}",
                run_record=record,
                acceptance_verdict=verdict,
                executor_invocations=invocations,
            )
        if verdict in (AcceptanceVerdict.STOP, AcceptanceVerdict.HUMAN_APPROVAL_REQUIRED):
            state = RunState.STOPPED if verdict == AcceptanceVerdict.STOP else RunState.HUMAN_APPROVAL_REQUIRED
            outcome = (
                OrchestratorOutcome.STOP if verdict == AcceptanceVerdict.STOP else OrchestratorOutcome.HUMAN_APPROVAL_REQUIRED
            )
            record = _record(
                state,
                writer_result=closure_writer_result,
                review_result=closure_review_result,
                closure_round=closure_round,
                closure_writer_executions=tuple(closure_writer_diagnostics),
                closure_reviewer_executions=tuple(closure_reviewer_diagnostics),
            )
            return OrchestratorResult(
                outcome=outcome,
                reason=f"closure round {closure_round} verdict was {verdict.value}",
                run_record=record,
                acceptance_verdict=verdict,
                executor_invocations=invocations,
            )
        # verdict == FIX_REQUIRED -> loop again if rounds remain.

    reason = f"blocking findings remain OPEN after {max_closure_rounds} closure round(s)"
    record = _record(
        RunState.HUMAN_ATTENTION_REQUIRED,
        reason=reason,
        open_findings=narrow_to_open_findings(current_findings),
        closure_round=closure_round,
        closure_writer_executions=tuple(closure_writer_diagnostics),
        closure_reviewer_executions=tuple(closure_reviewer_diagnostics),
    )
    return OrchestratorResult(
        outcome=OrchestratorOutcome.HUMAN_ATTENTION_REQUIRED,
        reason=reason,
        run_record=record,
        executor_invocations=invocations,
    )


__all__ = [
    "MAX_CLOSURE_ROUNDS",
    "DryRunReport",
    "OrchestratorOutcome",
    "OrchestratorResult",
    "run_targeted_validation",
    "run_task",
]
