"""DEV-AUTO-01 §7/§8/§9: Human Approval Boundary Guard。

いかなるTask ManifestもこのGateをBypassできない——`purpose`/
`task_id`/`forbidden_actions`/`targeted_tests`のいずれかにHuman-Gated
Operationを示すPatternが含まれていれば、Automationは
`HUMAN_APPROVAL_REQUIRED`理由を返して停止する。Silent Substitution
(別のTestへ黙って差し替える)・Silent Skipはいずれも行わない
(DEV-AUTO-01 §8「Do NOT execute it. Do NOT silently substitute
another test.」)。
"""

from __future__ import annotations

import re

from .model import TaskManifest

# DEV-AUTO-01 §7: Human Approvalが必須のBoundary(Closed List、推測で
# 緩めない)。H0001/2025 Locked Testは最優先(§8で専用Guardとしても
# 重複確認する)。
_HUMAN_GATED_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"h0001", re.IGNORECASE),
    re.compile(r"locked[\s_-]*test", re.IGNORECASE),
    re.compile(r"2025[\s_-]*locked", re.IGNORECASE),
    re.compile(r"held[\s_-]*out", re.IGNORECASE),
    re.compile(r"force[\s_-]*push", re.IGNORECASE),
    re.compile(r"branch[\s_-]*delet", re.IGNORECASE),
    re.compile(r"reset[\s_-]*--hard", re.IGNORECASE),
    re.compile(r"\brebase\b", re.IGNORECASE),
    re.compile(r"cherry-pick", re.IGNORECASE),
    re.compile(r"production[\s_-]*trad", re.IGNORECASE),
    re.compile(r"live[\s_-]*trad", re.IGNORECASE),
    re.compile(r"\bexecution\b", re.IGNORECASE),
    re.compile(r"acceptance[\s_-]*methodology", re.IGNORECASE),
    re.compile(r"preregist", re.IGNORECASE),
    re.compile(r"strategy[\s_-]*rule", re.IGNORECASE),
)

# DEV-AUTO-01 §9: Old Bad Commitへの参照(Rebase/Cherry-Pick/Reset対象
# としての指定)を禁止する。
_PROHIBITED_COMMIT_PREFIXES: tuple[str, ...] = ("e8eb683",)


def requires_human_approval(manifest: TaskManifest) -> str | None:
    """該当すれば理由文字列、しなければ`None`を返す。呼び出し側は
    `None`以外を`AcceptanceVerdict.HUMAN_APPROVAL_REQUIRED`へMapする。"""
    if manifest.requires_human_approval:
        return "task manifest explicitly sets requires_human_approval=True"

    haystacks = (
        manifest.task_id,
        manifest.purpose,
        *manifest.forbidden_actions,
        *manifest.targeted_tests,
    )
    for text in haystacks:
        for pattern in _HUMAN_GATED_PATTERNS:
            if pattern.search(text):
                return f"human-gated boundary detected: pattern={pattern.pattern!r} matched={text!r}"
    return None


def is_h0001_request(manifest: TaskManifest) -> bool:
    """DEV-AUTO-01 §8専用Guard: H0001/2025 Locked Testへの直接言及のみを
    狭く検出する(`requires_human_approval()`の一般Patternの部分集合、
    診断メッセージを明確にするための専用関数)。"""
    h0001_pattern = re.compile(r"h0001|2025[\s_-]*locked", re.IGNORECASE)
    haystacks = (manifest.task_id, manifest.purpose, *manifest.forbidden_actions, *manifest.targeted_tests)
    return any(h0001_pattern.search(text) for text in haystacks)


def is_prohibited_commit_reference(ref: str) -> bool:
    """Old Bad Commit(`e8eb683`)へのRebase/Cherry-Pick/Reset対象指定を
    防ぐ(DEV-AUTO-01 §9)。"""
    normalized = ref.strip().lower()
    return any(normalized.startswith(prefix) for prefix in _PROHIBITED_COMMIT_PREFIXES)


__all__ = ["is_h0001_request", "is_prohibited_commit_reference", "requires_human_approval"]
