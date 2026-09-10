#!/usr/bin/env python
"""DEV-AUTO-01/DEV-AUTO-02: Development Workflow Automation CLI。

小さなRepo-Local Interface(外部Agent Framework不使用、新規依存Package
無し、標準Library[argparse/json/pathlib]のみ)。実装本体は
`dev_workflow_lib/`(このFileと同じ`scripts/`直下)にあり、このFile
自体はThinなCLI Wiringのみを行う。

Usage:
    python scripts/dev_workflow.py validate <manifest.json> [--repo-root PATH]
    python scripts/dev_workflow.py gate <manifest.json> [--findings <findings.json>]
        [--reviewer-verdict ACCEPTED|NEEDS_FIX|STOP]
        [--tests-passed / --tests-failed]
        [--static-passed / --static-failed]
        [--repo-root PATH]
    python scripts/dev_workflow.py render-prompt <manifest.json>
        --role writer|reviewer|closure-reviewer [--findings <findings.json>]
    python scripts/dev_workflow.py run <manifest.json> [--dry-run]
        [--executor-config <executors.json>] [--repo-root PATH] [--runs-dir PATH] [--run-id ID]
    python scripts/dev_workflow.py status <run-id> [--runs-dir PATH]

`validate`/`gate`/`render-prompt`/`status`はいずれも読み取り専用
(`git status`/`git rev-parse`のみ、または既存Run RecordのRead)。
`run`は`--dry-run`であればAgentを一切呼び出さない(DEV-AUTO-02 §11)。
`--dry-run`を付けない`run`は、`--executor-config`で明示的に設定した
Capability(`CAN_EXECUTE_WRITER`/`CAN_EXECUTE_READ_ONLY_REVIEWER`)の
みAgentを実行する——設定が無ければ実行前にFail Closedで停止する。
Commit/Pushはこのscript自体では一切実行しない(DEV-AUTO-01 §9、
Acceptance Gate通過後の実際のCommit/Pushは人間またはAcceptance_Gate
Role側の別の明示的操作)。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Windows Consoleの既定Codepage(cp932等)ではJapanese Text/一部の記号を
# 含むJSON出力・Prompt出力がUnicodeEncodeErrorになるため、可能であれば
# 明示的にUTF-8へReconfigureする(pytest実行時等、`reconfigure()`が
# 存在しないIOへ差し替えられている場合はSilentに諦める、副作用無し)。
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except (AttributeError, ValueError):
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dev_workflow_lib.acceptance import evaluate_acceptance, narrow_to_open_findings  # noqa: E402
from dev_workflow_lib.executor import ExecutorRegistry, load_executor_registry_from_json  # noqa: E402
from dev_workflow_lib.gates import check_expected_head, check_scope  # noqa: E402
from dev_workflow_lib.human_gate import requires_human_approval  # noqa: E402
from dev_workflow_lib.model import Finding, ReviewerVerdict, TaskManifest  # noqa: E402
from dev_workflow_lib.orchestrator import run_task  # noqa: E402
from dev_workflow_lib.prompts import (  # noqa: E402
    build_closure_reviewer_prompt,
    build_reviewer_prompt,
    build_writer_prompt,
)
from dev_workflow_lib.run_record import load_run_record  # noqa: E402


def _load_manifest(path: Path) -> TaskManifest:
    return TaskManifest.from_dict(json.loads(path.read_text(encoding="utf-8")))


def _load_findings(path: Path | None) -> tuple[Finding, ...]:
    if path is None:
        return ()
    raw = json.loads(path.read_text(encoding="utf-8"))
    return tuple(Finding.from_dict(item) for item in raw)


def _emit(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def cmd_validate(args: argparse.Namespace) -> int:
    manifest = _load_manifest(Path(args.manifest))
    repo_root = Path(args.repo_root) if args.repo_root else Path.cwd()

    human_reason = requires_human_approval(manifest)
    if human_reason is not None:
        _emit({"verdict": "HUMAN_APPROVAL_REQUIRED", "reason": human_reason})
        return 1

    head_result = check_expected_head(repo_root, manifest.expected_head)
    if not head_result.passed:
        _emit({"verdict": "STOP", "reason": head_result.reason})
        return 1

    scope_result = check_scope(repo_root, allowed_files=manifest.allowed_files, frozen_files=manifest.frozen_files)
    passed = head_result.passed and scope_result.passed
    _emit(
        {
            "verdict": "OK" if passed else "STOP",
            "head_check": {"passed": head_result.passed, "reason": head_result.reason},
            "scope_check": {"passed": scope_result.passed, "reason": scope_result.reason},
        }
    )
    return 0 if passed else 1


def cmd_gate(args: argparse.Namespace) -> int:
    manifest = _load_manifest(Path(args.manifest))
    repo_root = Path(args.repo_root) if args.repo_root else Path.cwd()
    findings = _load_findings(Path(args.findings) if args.findings else None)
    reviewer_verdict = ReviewerVerdict(args.reviewer_verdict) if args.reviewer_verdict else None

    head_result = check_expected_head(repo_root, manifest.expected_head)
    scope_result = check_scope(repo_root, allowed_files=manifest.allowed_files, frozen_files=manifest.frozen_files)

    verdict = evaluate_acceptance(
        manifest=manifest,
        reviewer_verdict=reviewer_verdict,
        findings=findings,
        tests_passed=args.tests_passed,
        static_checks_passed=args.static_passed,
        scope_clean=head_result.passed and scope_result.passed,
    )

    open_findings = narrow_to_open_findings(findings)
    _emit(
        {
            "verdict": verdict.value,
            "head_check": {"passed": head_result.passed, "reason": head_result.reason},
            "scope_check": {"passed": scope_result.passed, "reason": scope_result.reason},
            "open_findings": [f.to_dict() for f in open_findings],
        }
    )
    return 0 if verdict.value == "ACCEPT" else 1


def cmd_render_prompt(args: argparse.Namespace) -> int:
    manifest = _load_manifest(Path(args.manifest))
    findings = _load_findings(Path(args.findings) if args.findings else None)
    open_findings = narrow_to_open_findings(findings)

    if args.role == "writer":
        print(build_writer_prompt(manifest))
    elif args.role == "reviewer":
        print(build_reviewer_prompt(manifest))
    else:
        print(build_closure_reviewer_prompt(manifest, open_findings))
    return 0


def _default_runs_dir(repo_root: Path) -> Path:
    return repo_root / ".dev_workflow_runs"


def cmd_run(args: argparse.Namespace) -> int:
    manifest = _load_manifest(Path(args.manifest))
    repo_root = Path(args.repo_root) if args.repo_root else Path.cwd()
    runs_dir = Path(args.runs_dir) if args.runs_dir else _default_runs_dir(repo_root)
    executors = load_executor_registry_from_json(Path(args.executor_config)) if args.executor_config else ExecutorRegistry.empty()

    result = run_task(
        manifest=manifest,
        repo_root=repo_root,
        executors=executors,
        runs_dir=runs_dir,
        run_id=args.run_id,
        dry_run=args.dry_run,
    )

    payload: dict[str, object] = {
        "outcome": result.outcome.value,
        "reason": result.reason,
        "run_id": result.run_record.run_id,
        "executor_invocations": result.executor_invocations,
    }
    if result.acceptance_verdict is not None:
        payload["acceptance_verdict"] = result.acceptance_verdict.value
    if result.dry_run_report is not None:
        report = result.dry_run_report
        payload["dry_run_report"] = {
            "task_id": report.manifest_task_id,
            "human_gate_reason": report.human_gate_reason,
            "resolved_starting_head": report.resolved_starting_head,
            "head_check": {"passed": report.head_check.passed, "reason": report.head_check.reason},
            "scope_check": {"passed": report.scope_check.passed, "reason": report.scope_check.reason},
            "writer_command_preview": (list(report.writer_command_preview) if report.writer_command_preview else None),
            "reviewer_command_preview": (list(report.reviewer_command_preview) if report.reviewer_command_preview else None),
            "writer_prompt": report.writer_prompt,
            "reviewer_prompt": report.reviewer_prompt,
        }
    _emit(payload)
    return 0 if result.outcome.value == "ACCEPT_CANDIDATE" or result.outcome.value == "DRY_RUN" else 1


def cmd_status(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root) if args.repo_root else Path.cwd()
    runs_dir = Path(args.runs_dir) if args.runs_dir else _default_runs_dir(repo_root)
    record = load_run_record(args.run_id, runs_dir=runs_dir)
    _emit(record.to_dict())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dev_workflow.py", description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="Check expected HEAD + scope against a task manifest")
    validate_parser.add_argument("manifest")
    validate_parser.add_argument("--repo-root", default=None)
    validate_parser.set_defaults(func=cmd_validate)

    gate_parser = subparsers.add_parser("gate", help="Evaluate the deterministic acceptance gate")
    gate_parser.add_argument("manifest")
    gate_parser.add_argument("--findings", default=None)
    gate_parser.add_argument("--reviewer-verdict", choices=["ACCEPTED", "NEEDS_FIX", "STOP"], default=None)
    gate_parser.add_argument("--tests-passed", dest="tests_passed", action="store_true")
    gate_parser.add_argument("--tests-failed", dest="tests_passed", action="store_false")
    gate_parser.set_defaults(tests_passed=False)
    gate_parser.add_argument("--static-passed", dest="static_passed", action="store_true")
    gate_parser.add_argument("--static-failed", dest="static_passed", action="store_false")
    gate_parser.set_defaults(static_passed=False)
    gate_parser.add_argument("--repo-root", default=None)
    gate_parser.set_defaults(func=cmd_gate)

    render_parser = subparsers.add_parser("render-prompt", help="Render a role-specific prompt from a task manifest")
    render_parser.add_argument("manifest")
    render_parser.add_argument("--role", choices=["writer", "reviewer", "closure-reviewer"], required=True)
    render_parser.add_argument("--findings", default=None)
    render_parser.set_defaults(func=cmd_render_prompt)

    run_parser = subparsers.add_parser("run", help="Run the bounded Writer/Reviewer/Closure orchestration flow")
    run_parser.add_argument("manifest")
    run_parser.add_argument("--dry-run", action="store_true")
    run_parser.add_argument("--executor-config", default=None)
    run_parser.add_argument("--repo-root", default=None)
    run_parser.add_argument("--runs-dir", default=None)
    run_parser.add_argument("--run-id", default=None)
    run_parser.set_defaults(func=cmd_run)

    status_parser = subparsers.add_parser("status", help="Display a persisted run record (read-only)")
    status_parser.add_argument("run_id")
    status_parser.add_argument("--repo-root", default=None)
    status_parser.add_argument("--runs-dir", default=None)
    status_parser.set_defaults(func=cmd_status)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    result: int = args.func(args)
    return result


if __name__ == "__main__":
    raise SystemExit(main())
