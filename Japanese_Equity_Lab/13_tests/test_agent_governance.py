"""Agent Governance Structural Tests(4A.5.1-2)。

D0044は「Reviewer Agentはtool allowlistにWrite/Edit/Bashを含まない」
「phase-closeは`disable-model-invocation: true`」等をMain Claudeが手動で
1回だけ確認して記録した(DECISIONS.md D0044「Structural Validation」節)。
このFileはそれをPermanent Regression Testへ変える。

**方針(2026-08-17実装Round、ユーザー指示)**: 「Reviewerへwrite command
を自然言語で出したらどうなるか」というModel Behavior Testは書かない
(非決定的で、毎回同じ結果を保証できない)。代わりに`tools:`Frontmatter
というConfig/Permission/Tool Allowlistの**Deterministic Property**のみを
検証する。既にMachine Enforcementが存在する項目には新しいHookを重複
追加しない(このFileはTestのみで、`.claude/settings.json`は変更しない)。

**訂正済みの前提(前Round pit-auditor Review、DECISIONS.md D0051参照)**:
`phase-close`の`disable-model-invocation: true`は現在存在しない
(D0046 §0で意図的に削除、User以外の正当なPhase Close呼び出しをHard
Errorにしていたため)。したがってこのFileは、そのFieldの存在を確認する
Testを持たない(存在しないFieldをMachine Enforcementとして検証すること
自体がD0051で訂正済みの誤りだったため)。代わりに、Description本文の
Guidance文言が将来の編集で失われていないかを緩やかに確認するSoft Check
を1本だけ置く(厳密なAccess Controlではないことを明記する)。

**「Main Claude → writer capability維持」について**: Main Claude(この
Session自体)には`.claude/agents/`配下に対応するConfig Fileが存在しない
(Subagentではなく既定のSession Agentであるため)。したがってこの性質は
Frontmatter経由で機械的にTestできず、このFileでは扱わない(省略している
ことをここに明記する。省略の理由を隠さない、Documentation Integrity原則)。
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_AGENTS_DIR = _REPO_ROOT / ".claude" / "agents"
_SKILLS_DIR = _REPO_ROOT / ".claude" / "skills"

# Write権限を持たない(＝Reviewer/Researcher Role)ことを検証する対象。
# 3体とも共通してRepositoryへ書き込む手段(Write/Edit/Bash)を持たない設計。
_NO_REPO_WRITE_AGENTS = ("pit-auditor", "skeptic-reviewer", "data-source-researcher")

_FORBIDDEN_WRITE_TOOLS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})


def _parse_frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path} はFrontmatterで始まっていません"
    _, frontmatter_text, _ = text.split("---\n", 2)
    data = yaml.safe_load(frontmatter_text)
    assert isinstance(data, dict), f"{path} のFrontmatterがMapping形式ではありません"
    return data


def _agent_frontmatter(name: str) -> dict:
    path = _AGENTS_DIR / f"{name}.md"
    assert path.exists(), f"Agent定義が見つかりません: {path}"
    return _parse_frontmatter(path)


def _tools_set(frontmatter: dict) -> set[str]:
    tools_raw = frontmatter.get("tools", "")
    if isinstance(tools_raw, str):
        return {t.strip() for t in tools_raw.split(",") if t.strip()}
    return set(tools_raw or [])


# ============================================================
# Reviewer/Researcher Agentは書き込み不可(pit-auditor/skeptic-reviewer/
# data-source-researcher → write禁止)
# ============================================================


@pytest.mark.parametrize("agent_name", _NO_REPO_WRITE_AGENTS)
def test_reviewer_agent_tools_allowlist_excludes_write_tools(agent_name: str) -> None:
    tools = _tools_set(_agent_frontmatter(agent_name))
    forbidden_present = tools & _FORBIDDEN_WRITE_TOOLS
    assert not forbidden_present, f"{agent_name}のtools allowlistにWrite系Toolが含まれています: {forbidden_present}"


# ============================================================
# Reviewer/Researcher Agentはcommit不可(Bashを持たない → commit禁止)
# ============================================================


@pytest.mark.parametrize("agent_name", _NO_REPO_WRITE_AGENTS)
def test_reviewer_agent_tools_allowlist_excludes_bash(agent_name: str) -> None:
    tools = _tools_set(_agent_frontmatter(agent_name))
    assert "Bash" not in tools, f"{agent_name}がBashを持っています(git commit/push等の実行が可能になってしまう)"


# ============================================================
# Phase Status変更権限なし(Write/Edit/NotebookEditが無ければDECISIONS.md/
# README.md等のCOMPLETE記述を書き換えられない — 上記2Testの論理的帰結を
# 明示的に記録する)
# ============================================================


@pytest.mark.parametrize("agent_name", _NO_REPO_WRITE_AGENTS)
def test_reviewer_agent_cannot_change_phase_status_files(agent_name: str) -> None:
    """`DECISIONS.md`/`README.md`等のPhase Status記述は、File書き込み手段
    (Write/Edit/MultiEdit/NotebookEdit)を通じてしか変更できない。上記の
    Write Tool禁止Testで確認済みの内容から論理的に導かれる帰結だが、
    「Reviewerがcommitできない」ことと「Reviewerがphase statusを変更
    できない」ことは別の懸念(ユーザー4A.5.1-2 spec上も別項目)として
    明示的に区別して記録する。"""
    tools = _tools_set(_agent_frontmatter(agent_name))
    assert not (tools & _FORBIDDEN_WRITE_TOOLS), (
        f"{agent_name}がFile書き込みToolを持っているため、Phase Status(DECISIONS.md等)を変更できてしまう可能性があります"
    )


# ============================================================
# Allowlist方式であることの確認(Denylistへの変更は将来Toolを暗黙許可する)
# ============================================================


def test_reviewer_agents_use_allowlist_not_denylist() -> None:
    for agent_name in _NO_REPO_WRITE_AGENTS:
        fm = _agent_frontmatter(agent_name)
        assert "tools" in fm, f"{agent_name}に`tools`(Allowlist)が定義されていません"
        assert "disallowedTools" not in fm, f"{agent_name}がDenylist方式(disallowedTools)へ変更されています"


# ============================================================
# Skill/Agent名の重複なし(D0044の一度きり確認をPermanent Regression化)
# ============================================================


def test_skill_names_are_unique() -> None:
    names = []
    for skill_file in sorted(_SKILLS_DIR.glob("*/SKILL.md")):
        fm = _parse_frontmatter(skill_file)
        names.append(fm["name"])
    assert names, "Skillが1件も見つかりませんでした(Path/検出Logic自体を疑う)"
    assert len(names) == len(set(names)), f"Skill名が重複しています: {names}"


def test_agent_names_are_unique() -> None:
    names = [_parse_frontmatter(p)["name"] for p in sorted(_AGENTS_DIR.glob("*.md"))]
    assert names, "Agentが1件も見つかりませんでした(Path/検出Logic自体を疑う)"
    assert len(names) == len(set(names)), f"Agent名が重複しています: {names}"


def test_agent_frontmatter_name_matches_filename() -> None:
    for agent_file in sorted(_AGENTS_DIR.glob("*.md")):
        fm = _parse_frontmatter(agent_file)
        assert fm["name"] == agent_file.stem, (
            f"{agent_file.name}: frontmatterのname({fm['name']})とFilename({agent_file.stem})が一致しません"
        )


# ============================================================
# 各SubagentのPreload Skillが実在すること
# ============================================================


def test_agent_preload_skills_exist() -> None:
    checked_any = False
    for agent_file in sorted(_AGENTS_DIR.glob("*.md")):
        fm = _parse_frontmatter(agent_file)
        for skill_name in fm.get("skills", []) or []:
            checked_any = True
            skill_path = _SKILLS_DIR / skill_name / "SKILL.md"
            assert skill_path.exists(), f"{agent_file.name}が参照するSkill'{skill_name}'が存在しません"
    assert checked_any, "Preload Skillを持つAgentが1件も見つかりませんでした(検出Logic自体を疑う)"


# ============================================================
# phase-close: 明示的呼び出し原則のGuidanceが失われていないこと(Soft Check、
# Machine Enforcementではないことを明記)
# ============================================================


def test_phase_close_description_still_documents_explicit_invocation_discipline() -> None:
    """`disable-model-invocation: true`は現在存在しない(D0046 §0で意図的に
    削除、DECISIONS.md D0051で訂正済み)。したがってこれはMachine
    Enforcementの確認ではなく、Description本文のGuidance文言が将来の
    編集で消えていないかを緩く確認するだけのSoft Checkである。"""
    fm = _parse_frontmatter(_SKILLS_DIR / "phase-close" / "SKILL.md")
    description = fm.get("description", "")
    assert "never spontaneously" in description, (
        "phase-closeのdescriptionから、自己判断での起動を戒めるGuidance文言が失われています"
    )


# ============================================================
# 既知のGap(参考、Test化せず記録): Main Claude Single Writer原則
# ============================================================

# Main Claude(既定Session Agent)には.claude/agents/配下の対応Config Fileが
# 無いため、"writer capability維持"はFrontmatter経由で機械的にTestできない。
# 現状はCLAUDE.mdの文章のみに依拠する(PHASE4A5_1_PLAN.md §H参照、Hookでの
# 強制は見送り済み)。
