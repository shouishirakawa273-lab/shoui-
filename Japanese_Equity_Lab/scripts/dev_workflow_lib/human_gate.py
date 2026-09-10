"""DEV-AUTO-01 §7/§8/§9 + DEV-AUTO-02.1: Human Approval Boundary Guard。

いかなるTask ManifestもこのGateをBypassできない——Human-Gated
Operationが実際に「要求」されていれば、Automationは
`HUMAN_APPROVAL_REQUIRED`理由を返して停止する。Silent Substitution
(別のTestへ黙って差し替える)・Silent Skipはいずれも行わない
(DEV-AUTO-01 §8「Do NOT execute it. Do NOT silently substitute
another test.」)。

DEV-AUTO-02.1 False-Positive Fix
---------------------------------
DEV-AUTO-02までの実装は`forbidden_actions`(禁止事項のリスト)を
「要求」と同じ土俵でKeyword Scanしていたため、`forbidden_actions:
["H0001"]`のように安全側でH0001を明示的に禁止しているManifestすら
`HUMAN_APPROVAL_REQUIRED`へ誤判定していた(Prohibitionを
Requestと取り違えるFalse Positive)。

修正方針(生成的なNLP Intent Classifierは追加しない、狭い決定論的
Ruleのみ):

1. `forbidden_actions`はもはやKeyword Scan対象から完全に除外する
   (Prohibitionは定義上「要求」ではない——Semanticsとして、
   Executorは`forbidden_actions`に記載された操作を実行してはならない
   という制約は`orchestrator.py`側のScope/Diff Gateで別途構造的に
   強制されるべきものであり、このModuleの責務はTextからの検出のみ)。
2. 新しい構造化Field`requested_actions`(明示的に「これを実行する」
   と宣言するField)は常にScanする——Negation判定は行わない
   (このFieldに書かれていること自体が「要求」の定義だから)。
3. `targeted_tests`も従来通り常にScanする(Test Commandそのものが
   実行対象を表すため、Negation Windowでの緩和は行わない)。
4. 自由記述の`purpose`/`task_id`のみ、D0102.4.1.1 F04の
   `_has_unnegated_marker()`と同型の「Marker出現の直前に既知の
   否定Cueが近接していれば、その出現は要求ではない」という
   狭いWindow Checkを適用する(Closed Listの否定Cue+固定Window幅の
   みで判定し、汎用文法解析は行わない)。
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

# DEV-AUTO-02.1: `purpose`/`task_id`の自由記述にのみ適用するNegation
# Cue(Closed List)。Markerの直前`_NEGATION_WINDOW`文字以内にこれらの
# いずれかが出現していれば、そのMarker出現は「要求」ではなく
# 「禁止/否定の言及」だと判定する。汎用NLPではなく固定Window+
# 固定語彙のみを見る決定論的Checkである点はD0102.4.1.1 F04の
# `_has_unnegated_marker()`に倣う。
_NEGATION_CUES: tuple[str, ...] = (
    "no ",
    "not ",
    "n't ",
    "without ",
    "never ",
    "forbid",
    "prohibit",
    "disallow",
    "must not",
    "should not",
    "avoid",
    "excluding",
    "except ",
    "do not",
    "does not",
)
_NEGATION_WINDOW = 40


def _is_negated_mention(text: str, match_start: int) -> bool:
    """`match_start`より前、`_NEGATION_WINDOW`文字以内に既知の
    否定Cueがあれば、その出現は「要求」ではなく「禁止/否定の言及」だと
    みなす(DEV-AUTO-02.1、D0102.4.1.1 F04の`_has_unnegated_marker()`
    と同型の狭いWindow Check)。"""
    window_start = max(0, match_start - _NEGATION_WINDOW)
    window = text[window_start:match_start].lower()
    return any(cue in window for cue in _NEGATION_CUES)


def _free_text_has_unnegated_match(text: str, pattern: re.Pattern[str]) -> re.Match[str] | None:
    """`purpose`/`task_id`のような自由記述Text専用: Negationされて
    いないMatchが1件でもあればそれを返す(無ければ`None`)。"""
    for match in pattern.finditer(text):
        if not _is_negated_mention(text, match.start()):
            return match
    return None


# DEV-AUTO-01 §9: Old Bad Commitへの参照(Rebase/Cherry-Pick/Reset対象
# としての指定)を禁止する。
_PROHIBITED_COMMIT_PREFIXES: tuple[str, ...] = ("e8eb683",)


def requires_human_approval(manifest: TaskManifest) -> str | None:
    """該当すれば理由文字列、しなければ`None`を返す。呼び出し側は
    `None`以外を`AcceptanceVerdict.HUMAN_APPROVAL_REQUIRED`へMapする。

    DEV-AUTO-02.1: `forbidden_actions`は定義上「要求」ではないため
    Scan対象から除外する。`requested_actions`/`targeted_tests`は
    明示的な実行対象であるため常にScanする。`purpose`/`task_id`は
    自由記述であり、Prohibition表現(「do not run H0001」等)がそのまま
    Falseに誤判定されないよう、Negation Windowを考慮する。"""
    if manifest.requires_human_approval:
        return "task manifest explicitly sets requires_human_approval=True"

    # 常にScan対象(要求そのものを表すStructured Field)。
    for text in (*manifest.requested_actions, *manifest.targeted_tests):
        for pattern in _HUMAN_GATED_PATTERNS:
            if pattern.search(text):
                return f"human-gated boundary detected: pattern={pattern.pattern!r} matched={text!r}"

    # 自由記述: Negationされていない出現のみを「要求」として扱う。
    for text in (manifest.task_id, manifest.purpose):
        for pattern in _HUMAN_GATED_PATTERNS:
            match = _free_text_has_unnegated_match(text, pattern)
            if match is not None:
                return f"human-gated boundary detected: pattern={pattern.pattern!r} matched={match.group(0)!r} in={text!r}"

    return None


def is_h0001_request(manifest: TaskManifest) -> bool:
    """DEV-AUTO-01 §8専用Guard: H0001/2025 Locked Testが実際に
    「要求」されている場合のみ`True`(`forbidden_actions`は除外、
    `purpose`/`task_id`はNegation Windowを考慮する。DEV-AUTO-02.1)。"""
    h0001_pattern = re.compile(r"h0001|2025[\s_-]*locked", re.IGNORECASE)

    for text in (*manifest.requested_actions, *manifest.targeted_tests):
        if h0001_pattern.search(text):
            return True

    for text in (manifest.task_id, manifest.purpose):
        if _free_text_has_unnegated_match(text, h0001_pattern) is not None:
            return True

    return False


def is_prohibited_commit_reference(ref: str) -> bool:
    """Old Bad Commit(`e8eb683`)へのRebase/Cherry-Pick/Reset対象指定を
    防ぐ(DEV-AUTO-01 §9)。"""
    normalized = ref.strip().lower()
    return any(normalized.startswith(prefix) for prefix in _PROHIBITED_COMMIT_PREFIXES)


__all__ = ["is_h0001_request", "is_prohibited_commit_reference", "requires_human_approval"]
