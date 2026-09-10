"""DEV-AUTO-01(Development Workflow Automation)のRegression Test。

`scripts/dev_workflow_lib/`(Pure Function中心のLibrary)と
`scripts/dev_workflow.py`(Thin CLI)の両方を検証する。実Git Repository
との相互作用が必要なTest(HEAD一致確認・Scope Diff確認)は`tmp_path`
配下に隔離したTemporary Git Repositoryを使い、実際のRepository状態には
一切触れない。投資判断・Market Data・Model呼び出しはこのTest Module・
対象Codeのいずれにも存在しない(`INVESTMENT_LOGIC_CHANGED = NO`)。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from scripts.dev_workflow_lib import gates as gates_module
from scripts.dev_workflow_lib.acceptance import evaluate_acceptance, narrow_to_open_findings, open_blocking_findings
from scripts.dev_workflow_lib.gates import check_expected_head, check_scope, list_changed_paths
from scripts.dev_workflow_lib.human_gate import (
    is_h0001_request,
    is_prohibited_commit_reference,
    requires_human_approval,
)
from scripts.dev_workflow_lib.model import (
    ROLE_CAPABILITIES,
    AcceptanceVerdict,
    Capability,
    Finding,
    FindingStatus,
    ReviewerVerdict,
    Role,
    Severity,
    TaskManifest,
    role_has_capability,
)
from scripts.dev_workflow_lib.prompts import build_closure_reviewer_prompt, build_reviewer_prompt, build_writer_prompt

_CLI_PATH = Path(__file__).resolve().parent.parent / "scripts" / "dev_workflow.py"


# ============================================================
# Fixtures / Helpers
# ============================================================


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


def _manifest(**overrides: object) -> TaskManifest:
    base: dict[str, object] = {
        "task_id": "T1",
        "purpose": "test task",
        "expected_head": "a" * 40,
        "allowed_files": ("a.py",),
        "frozen_files": ("b.py",),
    }
    base.update(overrides)
    return TaskManifest(**base)  # type: ignore[arg-type]


def _write_manifest_json(path: Path, **overrides: object) -> None:
    data: dict[str, object] = {
        "task_id": "T1",
        "purpose": "cli smoke test",
        "expected_head": "a" * 40,
        "allowed_files": ["allowed.txt"],
        "frozen_files": ["frozen.txt"],
        "targeted_tests": [],
        "static_checks": [],
        "forbidden_actions": [],
        "requires_independent_review": True,
        "requires_human_approval": False,
    }
    data.update(overrides)
    path.write_text(json.dumps(data), encoding="utf-8")


# ============================================================
# Repository Gate: expected HEAD
# ============================================================


def test_expected_head_match_passes(tmp_path: Path) -> None:
    repo, head = _init_temp_repo(tmp_path)
    result = check_expected_head(repo, head)
    assert result.passed


def test_expected_head_mismatch_is_stop_signal(tmp_path: Path) -> None:
    repo, _head = _init_temp_repo(tmp_path)
    result = check_expected_head(repo, "0" * 40)
    assert not result.passed
    assert "mismatch" in result.reason.lower()


# ============================================================
# Repository Gate: scope diff
# ============================================================


def test_scope_allowed_file_change_passes(tmp_path: Path) -> None:
    repo, _head = _init_temp_repo(tmp_path)
    (repo / "allowed.txt").write_text("changed\n", encoding="utf-8")
    result = check_scope(repo, allowed_files=("allowed.txt",), frozen_files=("frozen.txt",))
    assert result.passed


def test_frozen_file_change_stops(tmp_path: Path) -> None:
    repo, _head = _init_temp_repo(tmp_path)
    (repo / "frozen.txt").write_text("changed\n", encoding="utf-8")
    result = check_scope(repo, allowed_files=("allowed.txt",), frozen_files=("frozen.txt",))
    assert not result.passed
    assert "frozen.txt" in result.reason


def test_out_of_scope_tracked_change_stops(tmp_path: Path) -> None:
    repo, _head = _init_temp_repo(tmp_path)
    (repo / "not_in_manifest.txt").write_text("x\n", encoding="utf-8")
    subprocess.run(["git", "add", "not_in_manifest.txt"], cwd=repo, check=True)
    result = check_scope(repo, allowed_files=("allowed.txt",), frozen_files=("frozen.txt",))
    assert not result.passed


def test_unrelated_untracked_files_are_ignored_by_scope_check(tmp_path: Path) -> None:
    repo, _head = _init_temp_repo(tmp_path)
    (repo / "allowed.txt").write_text("changed\n", encoding="utf-8")
    (repo / "unrelated_untracked.txt").write_text("noise\n", encoding="utf-8")

    result = check_scope(repo, allowed_files=("allowed.txt",), frozen_files=("frozen.txt",))

    assert result.passed
    tracked, untracked = list_changed_paths(repo)
    assert "unrelated_untracked.txt" in untracked
    assert "unrelated_untracked.txt" not in tracked


def test_gates_module_never_calls_write_git_commands() -> None:
    # DEV-AUTO-01 §9: gates.pyはRead-Only(`status`/`rev-parse`)のみを
    # 実行する。書き込み系Subcommandへの参照が一切無いことをSource
    # Level(Substring)で確認する(将来の変更が誤ってWrite操作を
    # 混入させることをFail Closedで検知する)。
    source = Path(gates_module.__file__).read_text(encoding="utf-8")
    forbidden_tokens = ('"add"', '"commit"', '"push"', '"reset"', '"clean"', '"rebase"', '"cherry-pick"')
    for token in forbidden_tokens:
        assert token not in source, f"gates.py must not reference write git subcommand {token}"


# ============================================================
# Human Approval Boundary / H0001 Guard
# ============================================================


def test_high_risk_operation_requires_human_approval() -> None:
    manifest = _manifest(requires_human_approval=True)
    assert requires_human_approval(manifest) is not None

    verdict = evaluate_acceptance(
        manifest=manifest,
        reviewer_verdict=ReviewerVerdict.ACCEPTED,
        findings=(),
        tests_passed=True,
        static_checks_passed=True,
        scope_clean=True,
    )
    assert verdict == AcceptanceVerdict.HUMAN_APPROVAL_REQUIRED


def test_h0001_request_requires_human_approval_and_is_not_silently_substituted() -> None:
    manifest = _manifest(forbidden_actions=("do not run H0001",))
    assert is_h0001_request(manifest)
    assert requires_human_approval(manifest) is not None

    verdict = evaluate_acceptance(
        manifest=manifest,
        reviewer_verdict=ReviewerVerdict.ACCEPTED,
        findings=(),
        tests_passed=True,
        static_checks_passed=True,
        scope_clean=True,
    )
    assert verdict == AcceptanceVerdict.HUMAN_APPROVAL_REQUIRED


def test_2025_locked_test_reference_requires_human_approval() -> None:
    manifest = _manifest(purpose="rerun the 2025 locked test")
    assert requires_human_approval(manifest) is not None


def test_force_push_reference_requires_human_approval() -> None:
    manifest = _manifest(forbidden_actions=("force push to main",))
    assert requires_human_approval(manifest) is not None


def test_ordinary_manifest_does_not_require_human_approval() -> None:
    manifest = _manifest()
    assert requires_human_approval(manifest) is None
    assert not is_h0001_request(manifest)


def test_prohibited_old_bad_commit_reference_detected() -> None:
    assert is_prohibited_commit_reference("e8eb683")
    assert is_prohibited_commit_reference("E8EB683abcdef")
    assert not is_prohibited_commit_reference("cb5baaafb8d5de6052b70a00abc2e52eea37d293")


# ============================================================
# Finding Classification / Acceptance Gate
# ============================================================


def test_blocking_finding_open_forces_fix_required() -> None:
    manifest = _manifest()
    findings = (Finding(finding_id="F1", severity=Severity.HIGH, status=FindingStatus.OPEN, summary="x", blocking=True),)

    verdict = evaluate_acceptance(
        manifest=manifest,
        reviewer_verdict=ReviewerVerdict.ACCEPTED,
        findings=findings,
        tests_passed=True,
        static_checks_passed=True,
        scope_clean=True,
    )

    assert verdict == AcceptanceVerdict.FIX_REQUIRED
    assert open_blocking_findings(findings) == findings


def test_all_blockers_closed_is_accept_candidate() -> None:
    manifest = _manifest()
    findings = (
        Finding(finding_id="F1", severity=Severity.HIGH, status=FindingStatus.CLOSED, summary="x", blocking=True),
        Finding(finding_id="F2", severity=Severity.LOW, status=FindingStatus.CLOSED, summary="y", blocking=False),
    )

    verdict = evaluate_acceptance(
        manifest=manifest,
        reviewer_verdict=ReviewerVerdict.ACCEPTED,
        findings=findings,
        tests_passed=True,
        static_checks_passed=True,
        scope_clean=True,
    )

    assert verdict == AcceptanceVerdict.ACCEPT
    assert open_blocking_findings(findings) == ()


def test_reviewer_needs_fix_forces_fix_required_even_with_no_blocking_findings() -> None:
    manifest = _manifest()
    verdict = evaluate_acceptance(
        manifest=manifest,
        reviewer_verdict=ReviewerVerdict.NEEDS_FIX,
        findings=(),
        tests_passed=True,
        static_checks_passed=True,
        scope_clean=True,
    )
    assert verdict == AcceptanceVerdict.FIX_REQUIRED


def test_reviewer_stop_forces_stop() -> None:
    manifest = _manifest()
    verdict = evaluate_acceptance(
        manifest=manifest,
        reviewer_verdict=ReviewerVerdict.STOP,
        findings=(),
        tests_passed=True,
        static_checks_passed=True,
        scope_clean=True,
    )
    assert verdict == AcceptanceVerdict.STOP


def test_failing_tests_or_static_checks_force_fix_required() -> None:
    manifest = _manifest()
    verdict = evaluate_acceptance(
        manifest=manifest,
        reviewer_verdict=ReviewerVerdict.ACCEPTED,
        findings=(),
        tests_passed=False,
        static_checks_passed=True,
        scope_clean=True,
    )
    assert verdict == AcceptanceVerdict.FIX_REQUIRED


def test_dirty_scope_forces_fix_required() -> None:
    manifest = _manifest()
    verdict = evaluate_acceptance(
        manifest=manifest,
        reviewer_verdict=ReviewerVerdict.ACCEPTED,
        findings=(),
        tests_passed=True,
        static_checks_passed=True,
        scope_clean=False,
    )
    assert verdict == AcceptanceVerdict.FIX_REQUIRED


def test_independent_review_required_but_missing_forces_fix_required() -> None:
    manifest = _manifest(requires_independent_review=True)
    verdict = evaluate_acceptance(
        manifest=manifest,
        reviewer_verdict=None,
        findings=(),
        tests_passed=True,
        static_checks_passed=True,
        scope_clean=True,
    )
    assert verdict == AcceptanceVerdict.FIX_REQUIRED


def test_independent_review_optional_and_absent_still_accepts() -> None:
    manifest = _manifest(requires_independent_review=False)
    verdict = evaluate_acceptance(
        manifest=manifest,
        reviewer_verdict=None,
        findings=(),
        tests_passed=True,
        static_checks_passed=True,
        scope_clean=True,
    )
    assert verdict == AcceptanceVerdict.ACCEPT


# ============================================================
# Role / Capability Separation
# ============================================================


def test_reviewer_role_cannot_authorize_write_actions() -> None:
    assert not role_has_capability(Role.REVIEWER, Capability.CAN_EDIT_REPO)
    assert not role_has_capability(Role.REVIEWER, Capability.CAN_COMMIT)
    assert not role_has_capability(Role.REVIEWER, Capability.CAN_PUSH)
    assert role_has_capability(Role.REVIEWER, Capability.CAN_REVIEW_READ_ONLY)


def test_writer_role_cannot_commit_or_push() -> None:
    assert role_has_capability(Role.WRITER, Capability.CAN_EDIT_REPO)
    assert not role_has_capability(Role.WRITER, Capability.CAN_COMMIT)
    assert not role_has_capability(Role.WRITER, Capability.CAN_PUSH)
    assert not role_has_capability(Role.WRITER, Capability.CAN_REVIEW_READ_ONLY)


def test_acceptance_gate_role_has_no_edit_or_review_capability() -> None:
    assert not role_has_capability(Role.ACCEPTANCE_GATE, Capability.CAN_EDIT_REPO)
    assert not role_has_capability(Role.ACCEPTANCE_GATE, Capability.CAN_REVIEW_READ_ONLY)
    assert role_has_capability(Role.ACCEPTANCE_GATE, Capability.CAN_COMMIT)
    assert role_has_capability(Role.ACCEPTANCE_GATE, Capability.CAN_PUSH)


def test_every_role_has_a_capability_mapping() -> None:
    for role in Role:
        assert role in ROLE_CAPABILITIES


def test_capability_names_are_capability_based_not_plan_names() -> None:
    forbidden_literal_names = {"CLAUDE", "CODEX", "GPT_PLAN", "STANDARD", "PRO"}
    capability_values = {c.value for c in Capability}
    assert capability_values.isdisjoint(forbidden_literal_names)
    for value in capability_values:
        assert value.startswith("CAN_")


# ============================================================
# Closure Audit Narrowing
# ============================================================


def test_closure_review_contains_only_remaining_open_findings() -> None:
    findings = (
        Finding(finding_id="F01", severity=Severity.HIGH, status=FindingStatus.CLOSED, summary="closed one"),
        Finding(finding_id="F02", severity=Severity.MEDIUM, status=FindingStatus.OPEN, summary="still open", blocking=True),
        Finding(finding_id="F03", severity=Severity.LOW, status=FindingStatus.CLOSED, summary="closed two"),
    )

    open_findings = narrow_to_open_findings(findings)

    assert [f.finding_id for f in open_findings] == ["F02"]

    manifest = _manifest()
    prompt = build_closure_reviewer_prompt(manifest, open_findings)
    assert "F02" in prompt
    assert "F01" not in prompt
    assert "F03" not in prompt


def test_closure_review_with_no_open_findings_says_none_remain() -> None:
    manifest = _manifest()
    prompt = build_closure_reviewer_prompt(manifest, ())
    assert "none" in prompt.lower()


# ============================================================
# Prompt Templates
# ============================================================


def test_reviewer_prompts_explicitly_say_read_only() -> None:
    manifest = _manifest()
    assert "READ ONLY" in build_reviewer_prompt(manifest)
    assert "READ ONLY" in build_closure_reviewer_prompt(manifest, ())


def test_writer_prompt_includes_head_scope_and_forbidden_actions() -> None:
    manifest = _manifest(forbidden_actions=("do not force push",), targeted_tests=("test_x.py",))
    prompt = build_writer_prompt(manifest)
    assert manifest.expected_head in prompt
    assert "a.py" in prompt
    assert "b.py" in prompt
    assert "do not force push" in prompt
    assert "test_x.py" in prompt


def test_prompts_do_not_reference_product_plan_names() -> None:
    manifest = _manifest()
    forbidden_literal_names = ("CLAUDE", "CODEX", "GPT_PLAN", "STANDARD", "PRO")
    for prompt in (build_writer_prompt(manifest), build_reviewer_prompt(manifest), build_closure_reviewer_prompt(manifest, ())):
        for name in forbidden_literal_names:
            assert name not in prompt


# ============================================================
# Task Manifest / Finding Schema Validation
# ============================================================


def test_manifest_rejects_empty_allowed_files() -> None:
    with pytest.raises(ValueError):
        TaskManifest(task_id="T", purpose="p", expected_head="h" * 40, allowed_files=())


def test_manifest_rejects_overlap_between_allowed_and_frozen() -> None:
    with pytest.raises(ValueError):
        TaskManifest(task_id="T", purpose="p", expected_head="h" * 40, allowed_files=("x.py",), frozen_files=("x.py",))


def test_manifest_round_trips_through_json() -> None:
    manifest = _manifest(targeted_tests=("t1.py",), static_checks=("ruff check",))
    restored = TaskManifest.from_dict(manifest.to_dict())
    assert restored == manifest


def test_finding_round_trips_through_json() -> None:
    finding = Finding(
        finding_id="F1",
        severity=Severity.HIGH,
        status=FindingStatus.OPEN,
        summary="s",
        location="loc",
        reproducer="repro",
        expected="e",
        actual="a",
        blocking=True,
    )
    restored = Finding.from_dict(finding.to_dict())
    assert restored == finding


def test_finding_rejects_empty_summary() -> None:
    with pytest.raises(ValueError):
        Finding(finding_id="F1", severity=Severity.LOW, status=FindingStatus.OPEN, summary="")


# ============================================================
# CLI (subprocess-level, no impact on the real repository)
# ============================================================


def test_cli_validate_head_mismatch_stops(tmp_path: Path) -> None:
    repo, _head = _init_temp_repo(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    _write_manifest_json(manifest_path, expected_head="0" * 40)

    result = subprocess.run(
        [sys.executable, str(_CLI_PATH), "validate", str(manifest_path), "--repo-root", str(repo)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["verdict"] == "STOP"


def test_cli_validate_passes_when_scope_clean(tmp_path: Path) -> None:
    repo, head = _init_temp_repo(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    _write_manifest_json(manifest_path, expected_head=head)

    result = subprocess.run(
        [sys.executable, str(_CLI_PATH), "validate", str(manifest_path), "--repo-root", str(repo)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["verdict"] == "OK"


def test_cli_validate_human_approval_required_for_h0001(tmp_path: Path) -> None:
    repo, head = _init_temp_repo(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    _write_manifest_json(manifest_path, expected_head=head, forbidden_actions=["run H0001"])

    result = subprocess.run(
        [sys.executable, str(_CLI_PATH), "validate", str(manifest_path), "--repo-root", str(repo)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["verdict"] == "HUMAN_APPROVAL_REQUIRED"


def test_cli_gate_accepts_when_everything_clean(tmp_path: Path) -> None:
    repo, head = _init_temp_repo(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    _write_manifest_json(manifest_path, expected_head=head)

    result = subprocess.run(
        [
            sys.executable,
            str(_CLI_PATH),
            "gate",
            str(manifest_path),
            "--repo-root",
            str(repo),
            "--reviewer-verdict",
            "ACCEPTED",
            "--tests-passed",
            "--static-passed",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["verdict"] == "ACCEPT"


def test_cli_gate_reports_open_findings(tmp_path: Path) -> None:
    repo, head = _init_temp_repo(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    _write_manifest_json(manifest_path, expected_head=head)
    findings_path = tmp_path / "findings.json"
    findings_path.write_text(
        json.dumps(
            [
                {"finding_id": "F1", "severity": "HIGH", "status": "OPEN", "summary": "still broken", "blocking": True},
            ]
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(_CLI_PATH),
            "gate",
            str(manifest_path),
            "--repo-root",
            str(repo),
            "--findings",
            str(findings_path),
            "--reviewer-verdict",
            "ACCEPTED",
            "--tests-passed",
            "--static-passed",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["verdict"] == "FIX_REQUIRED"
    assert payload["open_findings"][0]["finding_id"] == "F1"


def test_cli_render_prompt_reviewer_role(tmp_path: Path) -> None:
    manifest_path = tmp_path / "manifest.json"
    _write_manifest_json(manifest_path)

    result = subprocess.run(
        [sys.executable, str(_CLI_PATH), "render-prompt", str(manifest_path), "--role", "reviewer"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "READ ONLY" in result.stdout
