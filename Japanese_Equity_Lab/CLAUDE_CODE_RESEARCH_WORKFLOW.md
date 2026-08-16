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
`skeptic-reviewer`をスキップしてよい。`phase-close`は常にUserが明示的に
起動する(Skill自体が`disable-model-invocation: true`)。

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

## このPhaseで導入していないもの

Hooksは自動導入していない(`HOOKS_PROPOSAL.md`参照、提案のみ)。
Phase4B実装・新Connector・投資判断ロジック・AI Research Agent実装は
このPhase(4A.5)のScope外。
