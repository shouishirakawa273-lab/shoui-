# Hooks Proposal(Phase4A.5、提案のみ・未導入)

このPhaseでは`.claude/settings.json`等へHookを自動登録していない。
理由: Hookはdeterministicに発火するため、誤設定すると通常の開発Workflow
(既存の`.claude/settings.json`が持つ`PostToolUse`品質ゲート含む)を妨げる
可能性がある。以下は将来検討する候補の提案のみであり、Userが必要と判断
した場合に別途設定すること。

現在確認できているHook Event(2026-08-16、`code.claude.com/docs/en/hooks`
参照): `PreToolUse`はTool呼び出し前に発火し、`exit 2`または
`"permissionDecision": "deny"`を返すことでTool呼び出しをBlockできる。
`PostToolUse`はTool成功後に発火するがBlockはできない(Feedbackのみ)。

## A. Secret Guard(候補)

**目的**: API Key・`.env`・Token文字列のcommitを防止する。

**発火Event候補**: `PreToolUse`(matcher: `Bash`、`git commit`/`git add`系の
コマンドをPatternでCheck)。

**懸念**: 誤検知(Secretらしき文字列だが実際は違うもの)によって正当な
commitがBlockされる可能性がある。`.gitignore`による`.env`除外と
`lib.snapshot._assert_no_secret_like_keys`(既存、Request Parameterへの
Secret混入検知)で現状は一定カバーされている。

## B. Protected Path Warning(候補)

**目的**: `core/` `app.py` `tests/`(既存Screening Tool)への意図しない変更に
気づけるよう警告する。

**発火Event候補**: `PreToolUse`(matcher: `Edit|Write`、`if`条件で
`core/*`/`app.py`/`tests/*`へのPathをCheck)。

**懸念**: Screening Tool自体の意図的な改修が必要になった場合(このLabの
Scope外だが将来的にありうる)、Hookが毎回ノイズになる。Warning止まりに
すべきかBlockにすべきかはUser判断が必要。

## C. Optional Phase Validation(候補)

**目的**: `phase-close` Skillの一部(pytest/ruff/mypy)を、Commit直前に
自動的に再実行する。

**発火Event候補**: `PreToolUse`(matcher: `Bash`、`git commit`Pattern)。

**懸念**: 実行時間(Lab全体のpytestは現状2秒未満だが、将来的にデータ量が
増えると伸びる可能性がある)。`phase-close`は既にUser明示起動のSkillである
ため、Hookで重複させる必要性は薄いかもしれない。

## 導入しない理由(再掲)

このPhaseの目的はClaude Codeの**Skills/Subagents/Workflow整備**であり、
Deterministicな強制Gateの追加はScope外(item 15、Userへの明示的な確認が
必要)。上記3案はいずれも設定ファイルへ未登録であり、`.claude/settings.json`
は本Phaseで変更していない。
