"""DEV-AUTO-01 §9/§10: Read-Only Git Repository Gate。

このModuleは`git status`/`git rev-parse`のみを実行する
(Read-Onlyなsubcommand限定)。`add`/`commit`/`push`/`reset`/`clean`等
書き込み系Git操作は一切実行しない——Acceptance Gate通過後の
Commit/Push自体は、このModuleを呼び出す側(人間、またはEnumで
`CAN_COMMIT`/`CAN_PUSH`を持つ`Role.ACCEPTANCE_GATE`側の別の明示的な
呼び出し)の責務であり、このModule自体は常に安全側(副作用無し)に
留まる。
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(kw_only=True, frozen=True)
class GateResult:
    passed: bool
    reason: str


def _run_git(repo_root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def check_expected_head(repo_root: Path, expected_head: str) -> GateResult:
    """DEV-AUTO-01 §9「Before any write workflow: verify expected
    HEAD」。不一致は常にSTOP相当(呼び出し側でAcceptanceVerdict.STOPへ
    Mapする)。"""
    actual_head = _run_git(repo_root, "rev-parse", "HEAD").strip()
    if actual_head != expected_head:
        return GateResult(
            passed=False,
            reason=f"HEAD mismatch: expected={expected_head} actual={actual_head}",
        )
    return GateResult(passed=True, reason="HEAD matches expected_head")


def list_changed_paths(repo_root: Path) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """`git status --porcelain`から(tracked_changed_paths,
    untracked_paths)を抽出する。Rename(`R  old -> new`)は新Pathのみを
    Trackedとして扱う。"""
    porcelain = _run_git(repo_root, "status", "--porcelain")
    tracked: list[str] = []
    untracked: list[str] = []
    for line in porcelain.splitlines():
        if not line:
            continue
        status_code = line[:2]
        raw_path = line[3:].strip()
        path = raw_path.split(" -> ")[-1].strip() if " -> " in raw_path else raw_path
        path = path.strip('"')
        if status_code == "??":
            untracked.append(path)
        else:
            tracked.append(path)
    return tuple(tracked), tuple(untracked)


def check_scope(
    repo_root: Path,
    *,
    allowed_files: tuple[str, ...],
    frozen_files: tuple[str, ...],
) -> GateResult:
    """DEV-AUTO-01 §9「Before commit: verify only allowed files
    changed」。Trackedな変更のみを対象にする——UntrackedなFile
    (`.agents/`/`.codex/`/`AGENTS.md`等、既存の無関係なFile)は
    `git add`で明示的Pathのみを使う限りStageされないため、ここでは
    ScopeからのTracked逸脱と`frozen_files`への書き込みのみを検出する
    (Untracked Fileを誤ってStageしないこと自体は呼び出し側のGit Add
    Discipline、DEV-AUTO-01 §9「Never use git add . / git add -A」に
    委ねる)。"""
    tracked_changed, _untracked = list_changed_paths(repo_root)
    allowed = set(allowed_files)
    frozen = set(frozen_files)

    frozen_touched = sorted(set(tracked_changed) & frozen)
    if frozen_touched:
        return GateResult(passed=False, reason=f"frozen files were modified: {frozen_touched}")

    out_of_scope = sorted(p for p in tracked_changed if p not in allowed)
    if out_of_scope:
        return GateResult(passed=False, reason=f"changes outside allowed_files: {out_of_scope}")

    return GateResult(passed=True, reason="all tracked changes are within allowed_files")


__all__ = ["GateResult", "check_expected_head", "check_scope", "list_changed_paths"]
