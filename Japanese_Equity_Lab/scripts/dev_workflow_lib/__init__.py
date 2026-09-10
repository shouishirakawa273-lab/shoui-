"""DEV-AUTO-01/DEV-AUTO-02: Japanese Equity Lab Development Workflow
Automation。

Build → Targeted Validation → Independent Read-Only Review → Finding
Classification → Narrow Fix → Closure Validation → Commit/Push → Freeze
Recommendation という、D0102系Roundで実際に繰り返してきたEngineering
Loopを、Capability-Basedな最小限のData Model + Deterministic Gate
Logic + Bounded Orchestration Flowとして機械的に扱えるようにする。

**このPackageは投資判断・市場データ取得・Model呼び出し・Evidence統合を
一切行わない**(`INVESTMENT_LOGIC_CHANGED = NO`)。Automation対象は
Software Engineering Process自体のみ(Build/Test/Review/Fix/Commit/
Push、DEV-AUTO-01 §15/DEV-AUTO-02 §17)。新しいAgent Framework・外部
Orchestration Library・Product/Plan名(CLAUDE/CODEX/GPT_PLAN等)への
Dependencyはいずれも存在しない(Capability名のみを使う、DEV-AUTO-01
§1/§16、DEV-AUTO-02 §2)。

## Module構成

- `model.py`: Capability/Role/WorkflowState/Severity/FindingStatus/
  ReviewerVerdict/AcceptanceVerdict(全Closed StrEnum)、`Finding`/
  `TaskManifest`(frozen dataclass、JSON (de)serialization付き)。
- `gates.py`: Read-OnlyなGit Repository Gate(期待HEAD一致確認・Scope
  Diff確認)。書き込み系Git操作はここでは一切実行しない。
- `human_gate.py`: H0001/2025 Locked Test等、Human Approvalが必須な
  Boundaryの検出(Closed Pattern List、Silent Substitutionはしない)。
- `acceptance.py`: Deterministic Acceptance Gate(LLM Score不使用)+
  Closure Audit Narrowing(既にCLOSEDのFindingを再監査しない)。
- `prompts.py`: Task ManifestからWRITER/REVIEWER/CLOSURE WRITER/
  CLOSURE REVIEWER Prompt Templateを機械的に生成する(手作業での
  書き直しをしない)。
- `executor.py`(DEV-AUTO-02): Capability-Based Agent Execution
  (`AgentExecutor` Protocol・`LocalCommandExecutor`・
  `ExecutorRegistry`)。Command TemplateはConfigurationとして常に
  明示的に供給される(Vendor CLI FlagをHard-codeしない)。
- `agent_results.py`(DEV-AUTO-02): Writer/Reviewer結果の機械可読
  JSON Envelope(`WriterResult`/`ReviewerResult`)、Malformed Inputは
  必ずFail Closed。
- `run_record.py`(DEV-AUTO-02): 最小限のJSON Run Record(DB不使用、
  自動Resumeも実装しない——Crashした実行を黙って再開する経路が
  構造的に存在しない)。
- `orchestrator.py`(DEV-AUTO-02): `run_task()`(唯一のSanctioned
  Orchestration Flow)。Human Approval Boundary確認 → Writer実行 →
  Targeted Validation → Read-Only Reviewer実行(実行前後のGit状態を
  比較しReviewerがRepositoryを変更していればSTOP)→ Deterministic
  Acceptance Gate → 必要なら`MAX_CLOSURE_ROUNDS`(既定2)で打ち切る
  Bounded Closure Loop。

Public Entrypointは `Japanese_Equity_Lab/scripts/dev_workflow.py`
(CLI、`validate`/`gate`/`render-prompt`/`run`/`status`の5 Subcommand
のみ)。このPackage自体の名前は`dev_workflow_lib`(CLI Entrypoint
`dev_workflow.py`とのModule名衝突を避けるため)。
"""

from __future__ import annotations
