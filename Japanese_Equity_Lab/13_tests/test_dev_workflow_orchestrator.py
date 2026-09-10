"""DEV-AUTO-02(Capability-Based Agent Execution Orchestrator)の
Regression Test。

`FakeExecutor`(In-Process Test Double、実Subprocessを起動しない)で
`run_task()`を駆動する。Git Repositoryとの相互作用が必要なTestは
`tmp_path`配下に隔離したTemporary Git Repositoryのみを使い、実際の
Repository状態には一切触れない。投資判断・Market Data・実Model呼び出し
はこのTest Module・対象Codeのいずれにも存在しない
(`INVESTMENT_LOGIC_CHANGED = NO`)。
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from scripts.dev_workflow_lib.executor import AgentExecutionResult, ExecutionCapability, ExecutorRegistry
from scripts.dev_workflow_lib.model import Role, TaskManifest
from scripts.dev_workflow_lib.orchestrator import OrchestratorOutcome, run_task
from scripts.dev_workflow_lib.run_record import RunState, load_run_record

_MANIFEST_PATH = (
    Path(__file__).resolve().parent.parent / "scripts" / "manifests" / "d0103_semantic_claim_evidence_integration_pilot.json"
)


# ============================================================
# Fixtures / Helpers
# ============================================================


@dataclass
class FakeExecutor:
    """`AgentExecutor` Protocolを満たすIn-Process Test Double。
    `response_fn`は呼び出しCountを受け取り、返すRaw stdout文字列(JSON)
    を決める(Closure Roundごとに異なる応答を返すTestで使う)。"""

    response_fn: Callable[[int], str] | None = None
    fixed_response: str | None = None
    returncode: int = 0
    timed_out: bool = False
    raise_exc: Exception | None = None
    mutate_fn: Callable[[Path], None] | None = None
    calls: list[str] = field(default_factory=list)

    def execute(self, *, role: Role, prompt: str, working_directory: Path) -> AgentExecutionResult:
        self.calls.append(prompt)
        if self.mutate_fn is not None:
            self.mutate_fn(working_directory)
        if self.raise_exc is not None:
            raise self.raise_exc
        if self.response_fn is not None:
            stdout = self.response_fn(len(self.calls))
        else:
            stdout = self.fixed_response or ""
        return AgentExecutionResult(returncode=self.returncode, stdout=stdout, stderr="", timed_out=self.timed_out)

    @property
    def call_count(self) -> int:
        return len(self.calls)


def _writer_success(files_changed: tuple[str, ...] = ()) -> str:
    return json.dumps(
        {
            "status": "SUCCESS",
            "files_changed": list(files_changed),
            "tests": "ok",
            "static_checks": "ok",
            "blocking_issue": None,
            "summary": "done",
        }
    )


def _writer_failed(blocking_issue: str = "could not complete") -> str:
    return json.dumps(
        {
            "status": "FAILED",
            "files_changed": [],
            "tests": "",
            "static_checks": "",
            "blocking_issue": blocking_issue,
            "summary": "failed",
        }
    )


def _reviewer_result(verdict: str, findings: list[dict[str, object]] | None = None) -> str:
    return json.dumps({"status": "COMPLETED", "verdict": verdict, "findings": findings or []})


def _finding(finding_id: str, *, status: str = "OPEN", blocking: bool = True, severity: str = "HIGH") -> dict[str, object]:
    return {
        "finding_id": finding_id,
        "severity": severity,
        "status": status,
        "summary": f"issue {finding_id}",
        "location": "somewhere",
        "reproducer": "repro",
        "expected": "expected",
        "actual": "actual",
        "blocking": blocking,
    }


def _init_temp_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / "allowed.txt").write_text("original\n", encoding="utf-8")
    (repo / "frozen.txt").write_text("original\n", encoding="utf-8")
    subprocess.run(["git", "add", "allowed.txt", "frozen.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True).stdout.strip()
    return repo, head


def _manifest(*, expected_head: str, **overrides: object) -> TaskManifest:
    base: dict[str, object] = {
        "task_id": "ORCH-T1",
        "purpose": "orchestrator test task",
        "expected_head": expected_head,
        "allowed_files": ("allowed.txt",),
        "frozen_files": ("frozen.txt",),
        "targeted_tests": (),
        "static_checks": (),
        "requires_independent_review": True,
    }
    base.update(overrides)
    return TaskManifest(**base)  # type: ignore[arg-type]


def _registry(writer: FakeExecutor, reviewer: FakeExecutor) -> ExecutorRegistry:
    return ExecutorRegistry(
        executors={
            ExecutionCapability.CAN_EXECUTE_WRITER: writer,
            ExecutionCapability.CAN_EXECUTE_READ_ONLY_REVIEWER: reviewer,
        }
    )


# ============================================================
# Dry Run
# ============================================================


def test_dry_run_invokes_zero_agents(tmp_path: Path) -> None:
    repo, head = _init_temp_repo(tmp_path)
    manifest = _manifest(expected_head=head)
    writer = FakeExecutor(fixed_response=_writer_success())
    reviewer = FakeExecutor(fixed_response=_reviewer_result("ACCEPTED"))

    result = run_task(
        manifest=manifest,
        repo_root=repo,
        executors=_registry(writer, reviewer),
        runs_dir=tmp_path / "runs",
        dry_run=True,
    )

    assert result.outcome == OrchestratorOutcome.DRY_RUN
    assert result.executor_invocations == 0
    assert writer.call_count == 0
    assert reviewer.call_count == 0
    assert result.dry_run_report is not None
    assert result.dry_run_report.writer_prompt
    assert result.dry_run_report.reviewer_prompt


def test_dry_run_works_with_empty_executor_registry(tmp_path: Path) -> None:
    repo, head = _init_temp_repo(tmp_path)
    manifest = _manifest(expected_head=head)

    result = run_task(
        manifest=manifest,
        repo_root=repo,
        executors=ExecutorRegistry.empty(),
        runs_dir=tmp_path / "runs",
        dry_run=True,
    )

    assert result.outcome == OrchestratorOutcome.DRY_RUN
    assert result.executor_invocations == 0


def test_d0103_pilot_dry_run_succeeds_with_zero_executions(tmp_path: Path) -> None:
    # DEV-AUTO-02 §14: D0103はこのRoundで実行しない。Dry-Runのみ成功する
    # ことを確認する(Dry-Runは常に完走しAgentを一切呼ばないことのみを
    # 検証する)。DEV-AUTO-02.1.1: `expected_head`はRuntime HEAD Pinning
    # Sentinelへ修復済みのため、Dry-Run時点でこのTemp RepositoryのHEADが
    # そのまま`resolved_starting_head`として解決され、`head_check.passed`
    # は常にTrueになることも確認する(Stale Manifest HEAD Bootstrap
    # Problemの直接的な解消)。
    manifest_data = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest = TaskManifest.from_dict(manifest_data)
    repo, head = _init_temp_repo(tmp_path)
    writer = FakeExecutor(fixed_response=_writer_success())
    reviewer = FakeExecutor(fixed_response=_reviewer_result("ACCEPTED"))

    result = run_task(
        manifest=manifest,
        repo_root=repo,
        executors=_registry(writer, reviewer),
        runs_dir=tmp_path / "runs",
        dry_run=True,
    )

    assert result.outcome == OrchestratorOutcome.DRY_RUN
    assert result.executor_invocations == 0
    assert writer.call_count == 0
    assert reviewer.call_count == 0
    # DEV-AUTO-02.1: D0103 Pilot ManifestはH0001/Locked Test等を
    # `forbidden_actions`(Prohibition)としてのみ記載し、`requested_actions`
    # には通常のScoped実装/Test/Review作業のみを列挙するよう修復した
    # (Human-Gate False-Positive Fix)。したがってこのManifestは
    # Human Gateを一切Triggerしない(HUMAN_APPROVAL_REQUIRED = NO)ことを
    # 確認する——D0103がこのRoundで実際に実行される経路はDry-Run自体が
    # AgentをZero回しか呼ばないことで別途保証されている。
    assert result.dry_run_report is not None
    assert result.dry_run_report.human_gate_reason is None
    assert result.dry_run_report.resolved_starting_head == head
    assert result.dry_run_report.head_check.passed
    assert head in result.dry_run_report.writer_prompt
    assert head in result.dry_run_report.reviewer_prompt
    assert "CURRENT" not in result.dry_run_report.writer_prompt
    assert "CURRENT" not in result.dry_run_report.reviewer_prompt


def test_d0103_pilot_non_dry_run_halts_before_any_execution(tmp_path: Path) -> None:
    # DEV-AUTO-02.1.1: `expected_head`はRuntime HEAD Pinning Sentinel
    # (`"CURRENT"`)へ修復済みのため、どのRepositoryに対してもHEAD Gate
    # 自体は常にPASSする(これがこのFixの狙い、D0103_DRY_RUN_READYの
    # 前提)。それでもD0103は「明示的にExecutor Configurationを渡さない
    # 限り」実行されない——Default Executor RegistryはEmptyであり
    # (DEV-AUTO-02.1既存の安全側判断)、Executor未設定を理由にAgentを
    # 一切呼ばずSTOPする(D0103_EXECUTED = NOはこの経路で維持される)。
    manifest_data = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest = TaskManifest.from_dict(manifest_data)
    repo, _head = _init_temp_repo(tmp_path)

    result = run_task(
        manifest=manifest,
        repo_root=repo,
        executors=ExecutorRegistry.empty(),
        runs_dir=tmp_path / "runs",
        dry_run=False,
    )

    assert result.outcome == OrchestratorOutcome.STOP
    assert "no executor configured" in result.reason
    assert result.executor_invocations == 0


# ============================================================
# Human Approval / H0001 / Repository Gates(zero agent executions)
# ============================================================


def test_human_gated_manifest_executes_zero_agents(tmp_path: Path) -> None:
    repo, head = _init_temp_repo(tmp_path)
    manifest = _manifest(expected_head=head, requires_human_approval=True)
    writer = FakeExecutor(fixed_response=_writer_success())
    reviewer = FakeExecutor(fixed_response=_reviewer_result("ACCEPTED"))

    result = run_task(manifest=manifest, repo_root=repo, executors=_registry(writer, reviewer), runs_dir=tmp_path / "runs")

    assert result.outcome == OrchestratorOutcome.HUMAN_APPROVAL_REQUIRED
    assert writer.call_count == 0
    assert reviewer.call_count == 0


def test_h0001_reference_executes_zero_agents(tmp_path: Path) -> None:
    repo, head = _init_temp_repo(tmp_path)
    manifest = _manifest(expected_head=head, requested_actions=("run H0001",))
    writer = FakeExecutor(fixed_response=_writer_success())
    reviewer = FakeExecutor(fixed_response=_reviewer_result("ACCEPTED"))

    result = run_task(manifest=manifest, repo_root=repo, executors=_registry(writer, reviewer), runs_dir=tmp_path / "runs")

    assert result.outcome == OrchestratorOutcome.HUMAN_APPROVAL_REQUIRED
    assert writer.call_count == 0
    assert reviewer.call_count == 0
    record = load_run_record(result.run_record.run_id, runs_dir=tmp_path / "runs")
    assert record.state == RunState.HUMAN_APPROVAL_REQUIRED


def test_expected_head_mismatch_executes_zero_agents(tmp_path: Path) -> None:
    repo, _head = _init_temp_repo(tmp_path)
    manifest = _manifest(expected_head="0" * 40)
    writer = FakeExecutor(fixed_response=_writer_success())
    reviewer = FakeExecutor(fixed_response=_reviewer_result("ACCEPTED"))

    result = run_task(manifest=manifest, repo_root=repo, executors=_registry(writer, reviewer), runs_dir=tmp_path / "runs")

    assert result.outcome == OrchestratorOutcome.STOP
    assert writer.call_count == 0
    assert reviewer.call_count == 0


def test_no_executor_configured_stops_before_execution(tmp_path: Path) -> None:
    repo, head = _init_temp_repo(tmp_path)
    manifest = _manifest(expected_head=head)

    result = run_task(manifest=manifest, repo_root=repo, executors=ExecutorRegistry.empty(), runs_dir=tmp_path / "runs")

    assert result.outcome == OrchestratorOutcome.STOP
    assert result.executor_invocations == 0


# ============================================================
# Writer / Reviewer Execution Failures
# ============================================================


def test_malformed_writer_result_stops(tmp_path: Path) -> None:
    repo, head = _init_temp_repo(tmp_path)
    manifest = _manifest(expected_head=head)
    writer = FakeExecutor(fixed_response="not json at all")
    reviewer = FakeExecutor(fixed_response=_reviewer_result("ACCEPTED"))

    result = run_task(manifest=manifest, repo_root=repo, executors=_registry(writer, reviewer), runs_dir=tmp_path / "runs")

    assert result.outcome == OrchestratorOutcome.STOP
    assert "malformed" in result.reason.lower()
    assert reviewer.call_count == 0


def test_malformed_reviewer_result_stops(tmp_path: Path) -> None:
    repo, head = _init_temp_repo(tmp_path)
    manifest = _manifest(expected_head=head)
    writer = FakeExecutor(fixed_response=_writer_success())
    reviewer = FakeExecutor(fixed_response="{not valid json")

    result = run_task(manifest=manifest, repo_root=repo, executors=_registry(writer, reviewer), runs_dir=tmp_path / "runs")

    assert result.outcome == OrchestratorOutcome.STOP
    assert "malformed" in result.reason.lower()


def test_writer_execution_failure_stops(tmp_path: Path) -> None:
    repo, head = _init_temp_repo(tmp_path)
    manifest = _manifest(expected_head=head)
    writer = FakeExecutor(returncode=1, fixed_response="")
    reviewer = FakeExecutor(fixed_response=_reviewer_result("ACCEPTED"))

    result = run_task(manifest=manifest, repo_root=repo, executors=_registry(writer, reviewer), runs_dir=tmp_path / "runs")

    assert result.outcome == OrchestratorOutcome.STOP
    assert reviewer.call_count == 0


def test_writer_raises_exception_is_caught_and_stops(tmp_path: Path) -> None:
    repo, head = _init_temp_repo(tmp_path)
    manifest = _manifest(expected_head=head)
    writer = FakeExecutor(raise_exc=RuntimeError("boom"))
    reviewer = FakeExecutor(fixed_response=_reviewer_result("ACCEPTED"))

    result = run_task(manifest=manifest, repo_root=repo, executors=_registry(writer, reviewer), runs_dir=tmp_path / "runs")

    assert result.outcome == OrchestratorOutcome.STOP


def test_writer_reports_failed_status_stops(tmp_path: Path) -> None:
    repo, head = _init_temp_repo(tmp_path)
    manifest = _manifest(expected_head=head)
    writer = FakeExecutor(fixed_response=_writer_failed("cannot resolve conflicting instructions"))
    reviewer = FakeExecutor(fixed_response=_reviewer_result("ACCEPTED"))

    result = run_task(manifest=manifest, repo_root=repo, executors=_registry(writer, reviewer), runs_dir=tmp_path / "runs")

    assert result.outcome == OrchestratorOutcome.STOP
    assert reviewer.call_count == 0


def test_reviewer_execution_failure_stops(tmp_path: Path) -> None:
    repo, head = _init_temp_repo(tmp_path)
    manifest = _manifest(expected_head=head)
    writer = FakeExecutor(fixed_response=_writer_success())
    reviewer = FakeExecutor(returncode=1, fixed_response="")

    result = run_task(manifest=manifest, repo_root=repo, executors=_registry(writer, reviewer), runs_dir=tmp_path / "runs")

    assert result.outcome == OrchestratorOutcome.STOP


def test_reviewer_raises_exception_is_caught_and_stops(tmp_path: Path) -> None:
    repo, head = _init_temp_repo(tmp_path)
    manifest = _manifest(expected_head=head)
    writer = FakeExecutor(fixed_response=_writer_success())
    reviewer = FakeExecutor(raise_exc=RuntimeError("boom"))

    result = run_task(manifest=manifest, repo_root=repo, executors=_registry(writer, reviewer), runs_dir=tmp_path / "runs")

    assert result.outcome == OrchestratorOutcome.STOP


# ============================================================
# Reviewer Independence(Read-Only Enforcement)
# ============================================================


def test_reviewer_modifying_repo_stops_and_rejects_verdict(tmp_path: Path) -> None:
    repo, head = _init_temp_repo(tmp_path)
    manifest = _manifest(expected_head=head)
    writer = FakeExecutor(fixed_response=_writer_success())

    def _mutate(working_directory: Path) -> None:
        (working_directory / "sneaky_write.txt").write_text("reviewer should not do this\n", encoding="utf-8")

    reviewer = FakeExecutor(fixed_response=_reviewer_result("ACCEPTED"), mutate_fn=_mutate)

    result = run_task(manifest=manifest, repo_root=repo, executors=_registry(writer, reviewer), runs_dir=tmp_path / "runs")

    assert result.outcome == OrchestratorOutcome.STOP
    assert "reviewer modified" in result.reason.lower()


def test_frozen_file_mutation_by_writer_stops(tmp_path: Path) -> None:
    repo, head = _init_temp_repo(tmp_path)
    manifest = _manifest(expected_head=head)

    def _mutate_frozen(working_directory: Path) -> None:
        (working_directory / "frozen.txt").write_text("writer touched a frozen file\n", encoding="utf-8")

    writer = FakeExecutor(fixed_response=_writer_success(), mutate_fn=_mutate_frozen)
    reviewer = FakeExecutor(fixed_response=_reviewer_result("ACCEPTED"))

    result = run_task(manifest=manifest, repo_root=repo, executors=_registry(writer, reviewer), runs_dir=tmp_path / "runs")

    assert result.outcome == OrchestratorOutcome.STOP
    assert "frozen.txt" in result.reason
    assert reviewer.call_count == 0


# ============================================================
# Closure Loop
# ============================================================


def test_reviewer_needs_fix_only_open_blockers_enter_closure(tmp_path: Path) -> None:
    repo, head = _init_temp_repo(tmp_path)
    manifest = _manifest(expected_head=head)
    writer = FakeExecutor(fixed_response=_writer_success())

    initial_findings = [
        _finding("F1", status="OPEN", blocking=True),
        _finding("F2", status="OPEN", blocking=False),
    ]

    def _reviewer_response(call_number: int) -> str:
        if call_number == 1:
            return _reviewer_result("NEEDS_FIX", initial_findings)
        return _reviewer_result(
            "ACCEPTED", [_finding("F1", status="CLOSED", blocking=True), _finding("F2", status="CLOSED", blocking=False)]
        )

    reviewer = FakeExecutor(response_fn=_reviewer_response)

    result = run_task(manifest=manifest, repo_root=repo, executors=_registry(writer, reviewer), runs_dir=tmp_path / "runs")

    assert result.outcome == OrchestratorOutcome.ACCEPT_CANDIDATE
    # Closure Writer Promptには唯一のBlocking FindingであるF1のみが含まれ、
    # Non-BlockingのF2は含まれないことを確認する。
    closure_writer_prompt = writer.calls[1]
    assert "F1" in closure_writer_prompt
    assert "F2" not in closure_writer_prompt


def test_closure_success_is_accept_candidate(tmp_path: Path) -> None:
    repo, head = _init_temp_repo(tmp_path)
    manifest = _manifest(expected_head=head)
    writer = FakeExecutor(fixed_response=_writer_success())

    def _reviewer_response(call_number: int) -> str:
        if call_number == 1:
            return _reviewer_result("NEEDS_FIX", [_finding("F1")])
        return _reviewer_result("ACCEPTED", [_finding("F1", status="CLOSED")])

    reviewer = FakeExecutor(response_fn=_reviewer_response)

    result = run_task(manifest=manifest, repo_root=repo, executors=_registry(writer, reviewer), runs_dir=tmp_path / "runs")

    assert result.outcome == OrchestratorOutcome.ACCEPT_CANDIDATE
    assert writer.call_count == 2  # initial + 1 closure round
    assert reviewer.call_count == 2


def test_closure_rounds_exceed_maximum_stops_with_human_attention(tmp_path: Path) -> None:
    repo, head = _init_temp_repo(tmp_path)
    manifest = _manifest(expected_head=head)
    writer = FakeExecutor(fixed_response=_writer_success())
    # Reviewerは常にNEEDS_FIXを返し続ける(Findingが一切CLOSEDにならない)。
    reviewer = FakeExecutor(fixed_response=_reviewer_result("NEEDS_FIX", [_finding("F1")]))

    result = run_task(
        manifest=manifest,
        repo_root=repo,
        executors=_registry(writer, reviewer),
        runs_dir=tmp_path / "runs",
        max_closure_rounds=2,
    )

    assert result.outcome == OrchestratorOutcome.HUMAN_ATTENTION_REQUIRED
    # 初回Writer+Reviewer(2回)+Closure Round 2回分のWriter+Reviewer(4回) = 6回。
    assert writer.call_count == 3
    assert reviewer.call_count == 3


# ============================================================
# Capability-Based Execution
# ============================================================


def test_capability_based_executor_substitution_works(tmp_path: Path) -> None:
    repo, head = _init_temp_repo(tmp_path)
    manifest = _manifest(expected_head=head)
    writer_a = FakeExecutor(fixed_response=_writer_success())
    reviewer_a = FakeExecutor(fixed_response=_reviewer_result("ACCEPTED"))
    writer_b = FakeExecutor(fixed_response=_writer_success())
    reviewer_b = FakeExecutor(fixed_response=_reviewer_result("ACCEPTED"))

    run_task(manifest=manifest, repo_root=repo, executors=_registry(writer_a, reviewer_a), runs_dir=tmp_path / "runs_a")
    run_task(manifest=manifest, repo_root=repo, executors=_registry(writer_b, reviewer_b), runs_dir=tmp_path / "runs_b")

    assert writer_a.call_count == 1
    assert reviewer_a.call_count == 1
    assert writer_b.call_count == 1
    assert reviewer_b.call_count == 1


def test_no_provider_product_plan_names_required() -> None:
    forbidden_literal_names = ("CLAUDE", "CODEX", "GPT_PLAN", "STANDARD", "PRO")
    for capability in ExecutionCapability:
        assert capability.value.startswith("CAN_")
        for name in forbidden_literal_names:
            assert name not in capability.value


def test_orchestrator_source_has_no_provider_literal() -> None:
    import scripts.dev_workflow_lib.orchestrator as orchestrator_module

    source = Path(orchestrator_module.__file__).read_text(encoding="utf-8")
    for name in ("Claude", "Codex", "codex", "claude", '"claude"', "'claude'"):
        assert name not in source, f"orchestrator.py must not hard-code provider literal {name!r}"


# ============================================================
# Run Record
# ============================================================


def test_run_record_persisted_and_readable(tmp_path: Path) -> None:
    repo, head = _init_temp_repo(tmp_path)
    manifest = _manifest(expected_head=head)
    writer = FakeExecutor(fixed_response=_writer_success())
    reviewer = FakeExecutor(fixed_response=_reviewer_result("ACCEPTED"))
    runs_dir = tmp_path / "runs"

    result = run_task(
        manifest=manifest, repo_root=repo, executors=_registry(writer, reviewer), runs_dir=runs_dir, run_id="fixed-id"
    )

    record = load_run_record("fixed-id", runs_dir=runs_dir)
    assert record.run_id == "fixed-id"
    assert record.task_id == manifest.task_id
    assert record.state == RunState.ACCEPT_CANDIDATE
    assert result.run_record.state == RunState.ACCEPT_CANDIDATE


def test_run_record_has_no_secret_looking_fields() -> None:
    from scripts.dev_workflow_lib.run_record import RunRecord

    field_names = set(RunRecord.__dataclass_fields__.keys())
    for forbidden in ("api_key", "token", "password", "secret"):
        assert forbidden not in field_names


def test_status_command_is_read_only_and_does_not_execute(tmp_path: Path) -> None:
    # `status`はRun Record自体のみをReadする——このTestはRegistry無し
    # (Executor未使用)でも`load_run_record`が正しく動くことを確認する。
    with pytest.raises(FileNotFoundError):
        load_run_record("does-not-exist", runs_dir=tmp_path / "runs")


# ============================================================
# DEV-AUTO-02.1: Local Executor Configuration (§14 I, J)
# ============================================================

_EXECUTOR_CONFIG_PATH = Path(__file__).resolve().parent.parent / "scripts" / "executor_config.example.json"


def test_I_reviewer_executor_config_retains_read_only_enforcement() -> None:
    # Config-Level: ReviewerのCommandは`--restricted`(Bash/PowerShell/
    # REPL/Code-Execution/WebFetchを除去)とFile変更系Toolの明示的
    # `--disallowedTools`を含み、Writerとは別のInvocation/Processである
    # ことを確認する(DEV-AUTO-02.1)。
    from scripts.dev_workflow_lib.executor import load_executor_registry_from_json

    registry = load_executor_registry_from_json(_EXECUTOR_CONFIG_PATH)
    writer = registry.get(ExecutionCapability.CAN_EXECUTE_WRITER)
    reviewer = registry.get(ExecutionCapability.CAN_EXECUTE_READ_ONLY_REVIEWER)
    assert writer is not None
    assert reviewer is not None
    assert writer is not reviewer

    reviewer_command = reviewer.command  # type: ignore[union-attr]
    assert "--restricted" in reviewer_command
    assert "--disallowedTools" in reviewer_command
    disallowed_index = reviewer_command.index("--disallowedTools")
    disallowed_value = reviewer_command[disallowed_index + 1]
    for mutating_tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        assert mutating_tool in disallowed_value

    # Orchestrator-Level(独立した第2層): Reviewerが実際にRepositoryを
    # 変更した場合はVerdictを無条件に拒否しSTOPする(既存のGit状態Diff
    # 比較、test_reviewer_modifying_repo_stops_and_rejects_verdictで
    # 別途検証済み)。ここでは両方のLayerが揃っていることのみを確認する。
    writer_command = writer.command  # type: ignore[union-attr]
    assert writer_command != reviewer_command


def test_J_executor_config_contains_no_secret_fields() -> None:
    # `scripts/executor_config.example.json`はAPIキー・Token・Password・
    # Secret・Credential等を一切含まない(コミット可能なExample、
    # DEV-AUTO-02.1)。Key名・Value双方をCase-Insensitiveに走査する。
    raw_text = _EXECUTOR_CONFIG_PATH.read_text(encoding="utf-8").lower()
    forbidden_tokens = ("api_key", "apikey", "token", "password", "secret", "credential")
    for forbidden in forbidden_tokens:
        assert forbidden not in raw_text, f"executor config example must not reference {forbidden!r}"

    # Bare, PATH-resolvable command name only (no user-specific absolute
    # path such as `C:\Users\...` or `/home/...`).
    assert "c:\\users" not in raw_text
    assert "/home/" not in raw_text


# ============================================================
# DEV-AUTO-02.1.1: Runtime HEAD Pinning (§11 A-H)
# ============================================================


def test_A_runtime_sentinel_resolves_to_current_head_and_passes(tmp_path: Path) -> None:
    repo, head = _init_temp_repo(tmp_path)
    manifest = _manifest(expected_head="CURRENT")

    result = run_task(
        manifest=manifest, repo_root=repo, executors=ExecutorRegistry.empty(), runs_dir=tmp_path / "runs", dry_run=True
    )

    assert result.dry_run_report is not None
    assert result.dry_run_report.resolved_starting_head == head
    assert result.dry_run_report.head_check.passed


def test_B_head_drift_between_pin_and_writer_stops_with_zero_writer_invocations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Runtime HEAD Pinningが解決した瞬間の値(Simulateする都合上、実際の
    # HEADとは異なる固定値)と、その後の各Gate(Step1/Writer Gate)が
    # 実際に読むHEADが食い違う状況を`resolve_head()`のMonkeypatchで
    # 再現する。Pin解決自体は`orchestrator._resolve_manifest_head()`が
    # 呼ぶ`resolve_head`のみを差し替え、各Gateが呼ぶ`check_expected_head`
    # (`gates.py`内部で実Git HEADを読む、無変更)は本物のままにする——
    # つまり「Pinされた値」と「実際のHEAD」が一致しない状態を作る。
    import scripts.dev_workflow_lib.orchestrator as orchestrator_module

    repo, _real_head = _init_temp_repo(tmp_path)
    monkeypatch.setattr(orchestrator_module, "resolve_head", lambda repo_root: "0" * 40)

    manifest = _manifest(expected_head="CURRENT")
    writer = FakeExecutor(fixed_response=_writer_success())
    reviewer = FakeExecutor(fixed_response=_reviewer_result("ACCEPTED"))

    result = run_task(manifest=manifest, repo_root=repo, executors=_registry(writer, reviewer), runs_dir=tmp_path / "runs")

    assert result.outcome == OrchestratorOutcome.STOP
    assert result.executor_invocations == 0
    assert writer.call_count == 0
    assert reviewer.call_count == 0


def test_C_explicit_sha_matching_current_head_passes(tmp_path: Path) -> None:
    repo, head = _init_temp_repo(tmp_path)
    manifest = _manifest(expected_head=head)

    result = run_task(
        manifest=manifest, repo_root=repo, executors=ExecutorRegistry.empty(), runs_dir=tmp_path / "runs", dry_run=True
    )

    assert result.dry_run_report is not None
    assert result.dry_run_report.resolved_starting_head == head
    assert result.dry_run_report.head_check.passed


def test_D_explicit_sha_mismatch_stops(tmp_path: Path) -> None:
    repo, _head = _init_temp_repo(tmp_path)
    manifest = _manifest(expected_head="0" * 40)
    writer = FakeExecutor(fixed_response=_writer_success())
    reviewer = FakeExecutor(fixed_response=_reviewer_result("ACCEPTED"))

    result = run_task(manifest=manifest, repo_root=repo, executors=_registry(writer, reviewer), runs_dir=tmp_path / "runs")

    assert result.outcome == OrchestratorOutcome.STOP
    assert writer.call_count == 0
    assert reviewer.call_count == 0


def test_E_prompt_rendering_uses_resolved_sha_never_sentinel(tmp_path: Path) -> None:
    repo, head = _init_temp_repo(tmp_path)
    manifest = _manifest(expected_head="CURRENT")
    writer = FakeExecutor(fixed_response=_writer_success())
    reviewer = FakeExecutor(fixed_response=_reviewer_result("ACCEPTED"))

    result = run_task(manifest=manifest, repo_root=repo, executors=_registry(writer, reviewer), runs_dir=tmp_path / "runs")

    assert result.outcome == OrchestratorOutcome.ACCEPT_CANDIDATE
    assert writer.call_count == 1
    assert reviewer.call_count == 1
    for prompt in (*writer.calls, *reviewer.calls):
        assert f"Expected HEAD: {head}" in prompt
        assert "CURRENT" not in prompt


def test_F_run_record_stores_resolved_starting_sha(tmp_path: Path) -> None:
    repo, head = _init_temp_repo(tmp_path)
    manifest = _manifest(expected_head="CURRENT")

    result = run_task(
        manifest=manifest, repo_root=repo, executors=ExecutorRegistry.empty(), runs_dir=tmp_path / "runs", dry_run=True
    )

    assert result.run_record.starting_head == head
    assert result.run_record.starting_head != "CURRENT"
    record = load_run_record(result.run_record.run_id, runs_dir=tmp_path / "runs")
    assert record.starting_head == head


def test_G_closure_rounds_preserve_original_starting_head(tmp_path: Path) -> None:
    repo, head = _init_temp_repo(tmp_path)
    manifest = _manifest(expected_head="CURRENT")
    writer = FakeExecutor(fixed_response=_writer_success())

    def _reviewer_response(call_number: int) -> str:
        if call_number == 1:
            return _reviewer_result("NEEDS_FIX", [_finding("F1")])
        return _reviewer_result("ACCEPTED", [_finding("F1", status="CLOSED")])

    reviewer = FakeExecutor(response_fn=_reviewer_response)

    result = run_task(manifest=manifest, repo_root=repo, executors=_registry(writer, reviewer), runs_dir=tmp_path / "runs")

    assert result.outcome == OrchestratorOutcome.ACCEPT_CANDIDATE
    assert writer.call_count == 2  # initial + 1 closure round
    assert reviewer.call_count == 2
    assert result.run_record.starting_head == head
    # 初回Round・Closure Roundいずれで送られたPromptも、常に同じ
    # Resolved SHAを保持していること(Repinしていないこと)を確認する。
    for prompt in (*writer.calls, *reviewer.calls):
        assert f"Expected HEAD: {head}" in prompt


def test_H_d0103_dry_run_head_check_pass_human_gate_clear_zero_executions(tmp_path: Path) -> None:
    manifest_data = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest = TaskManifest.from_dict(manifest_data)
    repo, head = _init_temp_repo(tmp_path)

    result = run_task(
        manifest=manifest, repo_root=repo, executors=ExecutorRegistry.empty(), runs_dir=tmp_path / "runs", dry_run=True
    )

    assert result.outcome == OrchestratorOutcome.DRY_RUN
    assert result.executor_invocations == 0
    assert result.dry_run_report is not None
    assert result.dry_run_report.human_gate_reason is None
    assert result.dry_run_report.head_check.passed
    assert result.dry_run_report.resolved_starting_head == head
