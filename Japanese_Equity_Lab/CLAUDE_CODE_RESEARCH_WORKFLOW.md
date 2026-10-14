# Claude Code Research Workflow(Phase4A.5)

このファイルは、Japanese Equity Labの開発で使う **Claude Codeの Skills /
Subagents の使い方**を説明する。研究Logic自体(データ取得・PIT判定・
Backtest等)の説明は `RESEARCH_RULES.md` / `DATA_SOURCE_ARCHITECTURE.md` /
`EVIDENCE_MODEL.md` を参照。このファイルはツール面(開発Workflow)のみを扱う。

**`10_agents/README.md` との違いに注意**: `10_agents/` は将来のResearch
Pipeline内AIエージェント構想(Portfolio Manager / Data / Fundamental / Quant
/ Macro / Hypothesis / Skeptic / Knowledge、Phase5/6以降で実装予定の概念)を
説明したものであり、このFileが説明する `.claude/agents/` の実Subagent
(Claude Code開発Tooling)とは別物である。前者は「研究パイプラインが将来持つ
AI役割」の設計文書、後者は「今このセッションで実際に呼び出せるClaude Code
Subagent」の実装である。

## Separation of Reviewer and Author(重要なArchitecture Rule)

- **Main Claude**: Author / Development Lead。実装を書く。
- **`pit-auditor`**: Independent PIT Reviewer。Point-in-Time Leakageのみを
  専門に監査する。
- **`skeptic-reviewer`**: Independent Adversarial Reviewer。実装・仮説の
  隠れた前提・biasを専門に監査する。
- **`data-source-researcher`**: Specification Researcher。新規Data Source
  接続前の公式仕様調査を専門に行う。

Reviewer Agent(`pit-auditor`/`skeptic-reviewer`)は、**自分で発見した
IssueをMain Claudeへ返すのみで、その場で修正しない。** Main Claudeが修正し、
必要ならReviewer Agentへ再監査を依頼する。これにより
**Author == Reviewerになることを避ける**(自分の実装を自分だけでレビューして
見落としを見逃すリスクを構造的に減らす)。3つのReviewer/Researcher Agentは
いずれも書き込み系Tool(`Write`/`Edit`/`Bash`)を持たない(`tools`
frontmatterのAllowlistで`Read`/`Grep`/`Glob`のみ、`data-source-researcher`
のみ`WebFetch`/`WebSearch`を追加)。

## Workflow: 通常の実装変更

```
Main Claude
  |
  v
Implementation(コード変更)
  |
  v
pit-auditor          <- PIT関連の変更がある場合(fundamentals/universe/
  |                      revision/backtest timing)
  v
skeptic-reviewer      <- 実装・仮説にadversarial reviewが必要な場合
  |
  v
Main Claude
  |
  v
Fix(Reviewer Findingsへの対応、Main Claudeのみが行う)
  |
  v
phase-close           <- Userが明示的に呼び出す。Tests/Status判定
```

PIT関連でない小さな変更(Docのみの更新等)では`pit-auditor`/
`skeptic-reviewer`をスキップしてよい。**[2026-08-17訂正]** `phase-close`
は「常にUserが明示的に起動する」という記述は、実際には現状と異なる
(D0046 §0で`disable-model-invocation: true`は意図的に削除済み、User以外の
正当なPhase Close呼び出しをHard Errorにしていたため)。現在は
Frontmatterによる強制ではなく、Skillの`description`本文が「Userが
実際にPhase Close/Completeを求めた時のみ呼び出す、自発的には呼び出さない」
というGuidanceを明示している(Access ControlではなくBehavioral
Guidance、`13_tests/test_agent_governance.py::test_phase_close_
description_still_documents_explicit_invocation_discipline`で
Description文言自体は継続確認する)。

## Workflow: 新しいData Sourceの追加(Phase4B以降)

```
data-source-researcher
  |
  v
Source Onboarding Report(確認済み事実 + UNKNOWN一覧)
  |
  v
Main Claude implementation(Adapter実装)
  |
  v
pit-auditor           <- PIT semantics(published_at/provider_available_at等)
  |                       の実装が正しいか
  v
skeptic-reviewer       <- Provider Semantics Mismatch等、隠れた前提の検証
  |
  v
phase-close
```

`local-validation` Skillは、このWorkflowのどの段階でも、実APIへこの
セッションから接続できない場合に使う(現状、このセッション自体は外部APIへ
一切疎通できない、DECISIONS.md参照)。

## Skills一覧(`.claude/skills/`)

| Skill | 呼び出し | 用途 |
| --- | --- | --- |
| `pit-audit` | Claude自動 or `/pit-audit` | PIT Leakage監査(`pit-auditor`がPreload) |
| `adversarial-review` | Claude自動 or `/adversarial-review` | Adversarial Review(`skeptic-reviewer`がPreload) |
| `phase-close` | `/phase-close`のみ(自動起動しない) | Phase終了時の標準Procedure |
| `source-onboarding` | Claude自動 or `/source-onboarding` | 新規Data Source調査(`data-source-researcher`がPreload) |
| `local-validation` | Claude自動 or `/local-validation` | ローカル実データ検証手順の生成 |
| `source-integration` | Claude自動 or `/source-integration` | Data Source Adapter/Normalizer実装・レビュー時のRule ID付きChecklist(4A.5.1-4、Preload Subagentなし) |

すべて`paths: Japanese_Equity_Lab/**`でScopeし、Lab配下のFileを扱っている
ときのみ自動起動対象になる(Screening Toolの作業では自動起動しない。明示的な
`/`起動はどこからでも可能)。

## Subagents一覧(`.claude/agents/`)

| Subagent | tools | Preload Skill | 出力 |
| --- | --- | --- | --- |
| `pit-auditor` | `Read, Grep, Glob` | `pit-audit` | Findings Reportのみ |
| `skeptic-reviewer` | `Read, Grep, Glob` | `adversarial-review` | PASS/PASS_WITH_CONCERNS/FAILのみ |
| `data-source-researcher` | `Read, Grep, Glob, WebFetch, WebSearch` | `source-onboarding` | Source Onboarding Reportのみ |

いずれも`Write`/`Edit`/`Bash`を持たない(`tools`はAllowlistなので、
明示していないToolは一切使えない)。

## Context Architecture(4A.5.1-3、2026-08-17追加)

このLabは既に暗黙のうちにContextを階層化して運用している(このFile自体が
Phase4A.5でCLAUDE.mdから「詳細なWorkflowはこちらへ」と分離された経緯が
その一例)。ここではその暗黙の実践を、4段階のClassificationとして明文化
する。**新しいTooling・新しいContext管理Systemを作るものではない**
(ユーザー2026-08-17実装Round指示: 「新しい巨大Systemは作らない」)。

| Classification | 意味 | 実例 |
| --- | --- | --- |
| `ALWAYS` | 常に必要な最小原則。全Sessionの冒頭で読まれる | ルート`CLAUDE.md`(コーディング規約)・`Japanese_Equity_Lab/CLAUDE.md`(研究原則、PIT/UNKNOWN/Reviewer分離等の短いRuleのみ) |
| `ON_DEMAND` | Taskの種類に応じて必要な時だけ読む | `.claude/skills/*/SKILL.md`(5件)・このFile自体・`RESEARCH_RULES.md`・`*_ARCHITECTURE.md`・`DECISIONS.md`の該当Section(`grep -n "^## D00"`で特定してから該当箇所のみ`offset`/`limit`指定Read、全文Readしない) |
| `TASK_ONLY` | 今回のRoundにだけ必要、Round終了後は破棄してよい | 各Round冒頭のUser Task Prompt(Goal/Scope/Files/Acceptance Criteria/禁止事項) |
| `EVIDENCE_ONLY` | 必要な部分だけ取得、全件を読み込まない | `01_data/raw/`配下のRaw Snapshot・`13_tests/fixtures/`・Provider生Response |

**重要な運用原則(既に実践中、これを明文化するだけ)**:

1. **`DECISIONS.md`(268KB超)を毎回丸ごとContextへ入れる設計にしない。**
   必要なSectionだけをGrep/Offset指定で読む、という現在のPracticeを
   維持する。このFile自体を要約・圧縮してSizeを削減するプロジェクトは
   行わない(要約によるRule消失を防ぐ、下記2項)。
2. **Semantic Compressionによる重要Rule消失を防ぐ。** 具体的な禁止事項
   (`market_public_atへFallbackしない`等)・UNKNOWN Semantics・
   Timestamp Semantics・Fail-closed Behavior・既知の制約は、要約時に
   「PITに気をつける」のような抽象語へ潰さない。
3. **`ALWAYS`層は増やさない。** 新しい原則が生まれた場合、まず
   `ON_DEMAND`層(Skill/Architecture Doc)へ置けないか検討し、それでも
   全Session常時必要と判断される場合のみ`ALWAYS`(CLAUDE.md)へ追記する
   (`ALWAYS`層が肥大化すると本来のOn-demand設計の意味が薄れるため)。

## Token-Efficient AI Development Policy(D0071、2026-08-26追加)

このLabのAI開発(Claude Code / Codex / Sub-agent)は、**品質・Research
Safetyを一切落とさずに不要なToken消費を減らす**ことを目的として以下を
運用する。目的は「AIに読む量を我慢させること」ではなく「不要なContextを
読ませないこと」である。**Quality / Research Safety > Token Saving**は
常に優先される(下記「Token節約が上書きしないもの」参照)。同時に
「More Context/Agent/Token = Better Quality/Research」でもない
(目的に対して過剰な調査・並列化はそれ自体がNoise)。

### Context層(既存のContext Architecture表を精緻化するだけ、新体系は作らない)

上記の`ALWAYS`/`ON_DEMAND`/`TASK_ONLY`/`EVIDENCE_ONLY`表がこのLabの
唯一のContext層分類である。`ON_DEMAND`層は実務上さらに3つの読む順序を
持つため、ここで明示する(表自体・列名は変更しない):

1. Task関連の`.claude/skills/*/SKILL.md`(Skills一覧参照)
2. 今回のTaskに直接関係する`DECISIONS.md`の該当Section・`*_ARCHITECTURE.md`
   (Grep/Offset指定、全文Readしない、既存原則のまま)
3. 実Code(変更対象のPrimary Scope、下記「Primary Scope Policy」参照)

**毎TaskでProject History全文・Repository全体を再探索しない。** 本節冒頭の
`Repo Reality First`(HEAD/status/branch確認 → 関係文書のみ選択的に読む)を
既定の開始手順とする。

### Task Prompt Policy(Thin Task Router)

新規Task Promptは、毎回同じProject-wide原則(PIT/UNKNOWN/Reviewer分離等)
を複製したMaster Promptにしない。最低限:

- Goal / Primary Scope / Safety Boundary / Required References /
  Acceptance Criteria / Stop Condition

だけを都度指定し、Project-wide原則自体はこのFile・`RESEARCH_RULES.md`・
`Japanese_Equity_Lab/CLAUDE.md`・`DECISIONS.md`を参照させる(Single
Source of Truth、下記「Documentation Policy」参照)。

### Primary Scope Policy

各Taskに`PRIMARY_SCOPE`(対象File/Directory)を明示し、Claude
Code/Codex/SubagentはまずPrimary Scopeだけを読む。Scope外を読むのは
dependency確認・caller確認・safety verification・曖昧さの解消など、
実際に必要な場合のみとし、拡大した場合は理由を簡潔に記録する。Primary
Scopeは厳密なSandboxではなく探索の起点であり、Safety目的のScope拡大は
常に許可される。Safety-Critical Boundary(PIT・Preregistration・Locked
Test・Append-only History等)の一覧は重複させず`AUDIT_MANIFEST.md`
§E("Safety-Critical Boundaries")を参照する。

### Claude Code Role(既存の「Separation of Reviewer and Author」を補足)

Claude Codeは引き続きMain Writer / Final Integrator(最終設計判断・
Production変更・Integration・Final Verification)である。ただし毎Taskで
Repository全体調査から始めない。`AUDIT_MANIFEST.md`のUnit分割・Codex
Mapping等が既に存在する場合はNavigationとして利用してよい。**重要:
Codex Report(あるいは任意の外部/独立調査Reportの示唆)は Source of Truth
ではない。** 変更対象のSymbol/Pathについては、Main Claude自身が必ず
Actual Repositoryで再確認してから実装する(D0068・D0070で実際に運用した
「Spot-check後に採用/一部不採用」という既存慣行の明文化であり、新Ruleでは
ない。D0070ではAudited HEADがこのRepositoryのどのBranchにも存在せず、
Finding本文中の「既に実装済み」という前提の一部が実際には誤りだったことを
実Grep/Readで発見した実例がある)。

### Codex Role(Engineering Investigator / Adversarial Reviewer)

Codexは、実Caller追跡・Import追跡・Entrypoint到達性・Dead-code検証・
PIT/Look-ahead監査・意味論監査・再現性監査・Cross-module Mapping・
実装Reviewのような、**答えが明確な調査質問**に使う。ゼロから巨大な
Architectureを考えさせることをDefaultにしない。原則: **1 Codex Task
= 1つの明確な調査質問**。全Repo監査をDefaultにしない。具体的な
Task粒度・Repo Access Gateの前提は重複させず`AUDIT_MANIFEST.md`
§G/H("Codex-Sized Task Breakdown"/"First Recommended Codex Task")を
参照する。

**Codex Evidence Rule**: Codex Findingは常にCANDIDATE_EVIDENCE_BACKED_
FINDING(検証待ちの候補)として扱う。重要なFindingには実際のHEAD・
Exact Path・Exact Symbol・実Caller/Import・関連Test・実際のSearch
Evidenceを要求する。Repo Access Gateを通過した報告であっても無条件に
真実扱いせず、Claude Codeが変更対象について独立に再検証する。

### Agent Policy(Claude Code Subagent)

**Task Independence > Agent数。** Agent数自体を成果指標にしない。
Agentを使うのは、Taskを独立した探索空間へ実際に分割できる場合のみ
(例: 独立したCapability領域をAgentごとに調査する等)。同じ問いを
複数Agentへ並列に考えさせる使い方や、同一Fileを複数Agentで競合編集する
使い方はしない。**既定は0 Agentでもよい。** このLabの既存3 Subagent
(`pit-auditor`/`skeptic-reviewer`/`data-source-researcher`、上記
「Subagents一覧」参照)は、いずれもRead-only・単一目的のReviewer/
Researcherとして運用する現行方針を維持する(Author自身がReviewerを
兼ねない、という既存原則、変更なし)。

Agent/Subagentの出力は短くする: STATUS / CONFIRMED FINDINGS / EXACT
PATHS・SYMBOLS / RISKS / RECOMMENDATIONの5点で十分とし、Finding数を
無理に増やさない。長いNarrative ReportをDefaultにせず、必要な箇所だけ
Main Claudeが該当File/Sectionへ戻って再読する。

### Task Complexity / Token Budget

Taskを概ね次の4種に分類し、検証の厚みを合わせる:

| 分類 | 目安 | Codex | Agent | Verification |
| --- | --- | --- | --- | --- |
| SMALL | 1〜3 files程度 | 不要 | 不要 | targeted testsのみ |
| MEDIUM | Subsystem内 | Optional | 0〜2 | Subsystem関連tests |
| LARGE | Cross-module | Mapping推奨(`AUDIT_MANIFEST.md`参照) | 独立Subtaskのみ | 段階的Verification(下記) |
| SAFETY_CRITICAL | PIT/available_at/Locked Test/Preregistration/Evidence semantics/Corporate Actions/Research Conclusion/Portfolio・Capital Allocation | Token節約より検証品質を優先(省略しない) | — | Reviewer Agent必須検討 |

**Investigation Stop Rule**: 必要なEvidenceが得られたら調査を止める
(例: Findingの証明に3件のCallerで十分ならRepository全体を理由なく
追加探索しない)。逆にSAFETY_CRITICALなTaskではEvidence Thresholdを
高く保つ(調査を早めに切り上げない)。

### File Re-read Policy

同一Task内で、変更していない大きなFileを理由なく何度も読み直さない。
一度得たSymbol位置・Caller関係・意味論的結論はTask Context内で再利用し、
変更・矛盾が発生した場合のみ再確認する。

### Verification Staging

Verificationを段階化する: 実装中はTargeted Tests、Subsystem完了時は
関連Tests、最終完了前にFull Required Regression Suiteを実行する(この
順序は本Session内の実運用パターンの明文化であり新Ruleではない)。
失敗していないTestの巨大stdoutをContextへ投入しない(`1009 passed`
程度で十分)。失敗時のみFailing Test・関連Traceback・関連Codeを読む。

### Diff / Log Policy

巨大なLog/Diffを最初から全文読まない。`git diff --stat` → 必要な
Changed Fileだけdiff → 必要ならHunkのみ、と段階化する。生のAPI
Payload・pytest全Log・生成済みJSONLを理由なく全文Contextへ投入しない。

### Stage Handoff Summary

各主要Stage終了時、次Taskのための短いState Summary(STATUS / WHAT
EXISTS / WHAT CHANGED / SAFETY BOUNDARIES / KNOWN GAPS / NEXT LIKELY
TASK)を残す。ただしSummaryはEvidenceの代替ではない。矛盾や不確実性が
あれば必ずActual Repositoryへ戻って確認する。

### Documentation Policy

Token効率化を理由にDocumentationを大量新設しない。Single Source of
Truthを優先し、同じ原則を`CLAUDE.md`・Skill・`DECISIONS.md`・別Policyへ
重複記載しない。このSection自体がその実践例であり、Context Architecture
(4A.5.1-3)・Codex Task Breakdown(`AUDIT_MANIFEST.md`)・Reviewer Agent
分離(本File冒頭)を重複させず参照するのみに留めている。詳細は既存文書へ
リンクし、Policy自体は短く保つ。

### Token節約が上書きしないもの

Token削減を理由に以下を省略しない: PIT verification・availability
checks・provenance・falsification・contradictory evidence・UNKNOWN
handling・Locked Test rules・preregistration integrity・append-only
history・backward compatibility・final regression verification。これらは
`Japanese_Equity_Lab/CLAUDE.md`「安全原則・禁止事項」「Claude Code
Guardrails」・`RESEARCH_RULES.md`が既に定める既存原則であり、このPolicy
はそれらを一切緩めない(「Costが高いからSafety Checkをしない」は禁止)。

### Desired Operating Flow(既存の2つのWorkflow図を置き換えない)

上記「Workflow: 通常の実装変更」「Workflow: 新しいData Sourceの追加」を
より一般化した形で示す(既存2図はそのまま有効、こちらは追加の俯瞰図):

```
Task Router(Thin Prompt)
  |
  v
Relevant Skill / Decision(必要な範囲のみ)
  |
  v
Codex Mapping <- 必要な場合だけ(AUDIT_MANIFEST.md参照)
  |
  v
Main Claude: 対象Symbolのみ実Repoで再確認
  |
  v
Implementation
  |
  v
Targeted Verification
  |
  v
Safety-critical Review <- 必要な場合だけ(pit-auditor/skeptic-reviewer)
  |
  v
Full Regression
  |
  v
Short Stage Summary
```

## このPhaseで導入していないもの

Hooksは自動導入していない(`HOOKS_PROPOSAL.md`参照、提案のみ)。
Phase4B実装・新Connector・投資判断ロジック・AI Research Agent実装は
このPhase(4A.5)のScope外。Token-Efficient AI Development Policy
(D0071)も新しいTooling/Hook/Agent種別を追加するものではなく、既存の
運用実践を明文化・相互参照しただけである。
