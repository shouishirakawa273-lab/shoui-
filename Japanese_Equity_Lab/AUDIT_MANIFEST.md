# AUDIT_MANIFEST.md — Post-Phase5 Complexity Audit Manifest

このDocumentは、Repositoryを独立監査可能な「Audit Unit」へ分割した
地図である。**分割そのものが目的であり、各Unit内のDead Code判定・
Refactor提案はこのRoundでは行っていない。** 全て2026-08-20時点の
Actual Repository(Python file inventory・import grep・LOC計測)から
確認した事実に基づく。Codexへ個別Unitの独立監査を委譲する際の
Scope定義として使う想定。

## A. Repository Audit Map

```
shoui- (root)
├── core/ + app.py + tests/          [PROTECTED, Screening Tool、Lab非依存]
├── scripts/                          8 files, 2,019 LOC (Lab連携CLI)
├── Japanese_Equity_Lab/
│   ├── lib/                          103 files, 約12,636 LOC
│   │   ├── backtest/                 3 files,    764 LOC  [Unit1]
│   │   ├── point_in_time.py, market_calendar.py,
│   │   │   universe.py, errors.py, reproducibility.py,
│   │   │   snapshot.py               7 files,    802 LOC  [Unit1/Unit2に分属]
│   │   ├── research/                 5 files,    732 LOC  [Unit2]
│   │   ├── registry/                 2 files,    175 LOC  [Unit2]
│   │   ├── strategies/               2 files,    157 LOC  [Unit2]
│   │   ├── schemas/                  9 files,    729 LOC  [Unit2/Unit5に分属]
│   │   ├── data_sources/             6 files,  1,041 LOC  [Unit3]
│   │   ├── fundamentals/             5 files,    900 LOC  [Unit4]
│   │   ├── disclosures/ (+providers) 14 files, 3,114 LOC  [Unit4、最大]
│   │   ├── positioning/ (+derived)   6 files,    654 LOC  [Unit4]
│   │   ├── macro/                    5 files,    503 LOC  [Unit4]
│   │   ├── global_market/            5 files,    555 LOC  [Unit4]
│   │   ├── news/                     5 files,    707 LOC  [Unit4]
│   │   ├── consensus/                5 files,    631 LOC  [Unit4]
│   │   ├── evidence/                 5 files,    724 LOC  [Unit5]
│   │   └── sources/                  3 files,    448 LOC  [Unit5]
│   ├── 13_tests/                     84 files, 約16,070 LOC [Unit6]
│   └── *.md (29 files) + DECISIONS.md(7,119行) + RESEARCH_RULES.md(728行)
│                                                          [Unit7]
└── scripts/phase5_v1_1_h0001_real_data.py (579 LOC、Unit2のLive Entrypoint)
```

Lab側`lib/`(約12,636 LOC)よりTest(約16,070 LOC)の方が大きい
(Codexへ委譲する際、Unit6は複数の小Taskへさらに分割してよい)。
`lib/disclosures/`(3,114 LOC)単体がPhase4系Unitの中で最大で、
他の全Phase4 Capability合計(fundamentals+positioning+macro+
global_market+news+consensus=3,950 LOC)にほぼ匹敵する。

`core/`/`app.py`/root`tests/`から`Japanese_Equity_Lab/`への import は
grep上ゼロ(逆方向も無し)— 2つの独立したApplicationとして存在する。

## B. Phase5 v1.1 Actual Live Core

`scripts/phase5_v1_1_h0001_real_data.py`の実際のTop-level Import
(`grep '^from lib\.'`)から再構成した、実際に実行される依存Closure:

```
scripts/phase5_v1_1_h0001_real_data.py
├─ lib.backtest.engine (DataSplit)
│    └─ lib.backtest.price_history / lib.errors / lib.market_calendar
│       / lib.point_in_time / lib.schemas.price_data / lib.universe
├─ lib.backtest.price_history (AsOfAdjustedPriceHistory)
├─ lib.data_sources.convert / lib.data_sources.jquants
├─ lib.errors
├─ lib.market_calendar (TradingCalendar, session_close_at)
├─ lib.registry.experiment_registry / lib.registry.provenance
├─ lib.reproducibility
├─ lib.research.dataset_contract / locked_test / preregistration
│    / registry / runner
│       └─ runner.py内部で lib.backtest.engine / lib.backtest.price_history
│          / lib.market_calendar / lib.research.locked_test
│          / lib.research.preregistration / lib.schemas.price_data
│          / lib.universe を再度参照(上と重複)
├─ lib.schemas.experiment / lib.schemas.price_data
├─ lib.snapshot
├─ lib.strategies.short_term_reversal
└─ lib.universe
```

**この依存Closureに`lib.fundamentals`/`lib.disclosures`/
`lib.positioning`/`lib.macro`/`lib.global_market`/`lib.news`/
`lib.consensus`/`lib.evidence`/`lib.sources`は一切含まれない**
(D0061 Forbidden Capability一覧と一致することを確認済み、
`test_realval007_script_never_imports_forbidden_capabilities`が
これを構造Testとして保証している)。Phase4系Capabilityは現時点で
Import Graph上も完全に未接続であり、「使われていないから消してよい」
ではなく「まだ接続されていない将来Capability」という位置づけ
(D0061 Readiness Gate)。

## C. Audit Units

### Unit 1 — Backtest / PIT / Universe Core

- **Scope**: `lib/backtest/`(engine.py, price_history.py, benchmark.py)、
  `lib/point_in_time.py`、`lib/market_calendar.py`、`lib/universe.py`、
  `lib/schemas/price_data.py`、`lib/errors.py`(LookAheadBiasError等の
  定義元)。
- **Responsibility**: Point-in-Time安全なBacktest実行機構そのもの。
  Decision Timing・Execution Timing・Corporate Action PIT調整・PIT
  Universe解決・Trading Calendar・Look-ahead防止のCore実装。
- **Current Status**: `LIVE_CORE`。Phase5 v1.1実データRunで実際に
  実行された(D0067 Final PIT Audit CLEAN)。
- **Important Dependencies**: Unit2(`lib.research.runner`が本Unitを
  呼び出す)。本Unit自体は`lib.schemas`以外のLab固有Packageに依存
  しない(Fundamentals/Disclosures等への依存ゼロ、Import grep確認済み)。
- **Safety Criticality**: **HIGH**。PIT・Look-ahead防止・Corporate
  Action Timing・UNKNOWN/Fail-closed Semanticsの本丸。
- **Approximate Size**: 11 files、約1,566 LOC(backtest 764 + 上記
  top-level 7 files 802のうち本Unit該当分)。
- **Recommended Independent Audit**:
  1. `BacktestEngine.run()`のDecision→Execution Timing経路が
     `assert_no_lookahead`を必ず経由するか。
  2. `SplitBoundaryLeakageError`のGateが全呼び出し経路で回避不能か。
  3. `AsOfAdjustedPriceHistory`のCorporate Action(Case B)適用が
     Ex-date境界を跨がないか。
  4. `market_calendar.py`(D0068でSessionSchedule削除済み)の残存API
     に他の未使用Symbolが無いか。
  5. `TradingCalendarResolutionError`のFail-closed経路に平日推測等の
     抜け道が無いか。
- **Audit Cost**: MEDIUM(Engine本体が複雑、ただし外部依存が薄いため
  Context量は抑えられる)。

### Unit 2 — Phase5 Research Validation & Registry

- **Scope**: `lib/research/`(dataset_contract.py, locked_test.py,
  preregistration.py, registry.py, runner.py)、`lib/registry/`
  (experiment_registry.py, provenance.py)、`lib/reproducibility.py`、
  `lib/snapshot.py`、`lib/strategies/`(short_term_reversal.py,
  fixed_pipeline_validation.py)、`lib/schemas/experiment.py`、
  `lib/schemas/hypothesis.py`、`lib/schemas/base.py`、
  `scripts/phase5_v1_1_h0001_real_data.py`、
  `scripts/phase5_v1_short_term_reversal.py`。
- **Responsibility**: Preregistration固定・Immutability・Locked Test
  隔離・Append-only Experiment/Preregistration Registry・Provenance・
  Reproducibility Fingerprint・実際のReal-data/Synthetic Experiment
  CLI。
- **Current Status**: `LIVE_CORE`。Phase5 v1.1がCOMPLETE、実データで
  Train/Validation/Locked Test完走済み(D0067)。
- **Important Dependencies**: Unit1(`run_split`が`BacktestEngine`を
  直接呼ぶ)、Unit3(`JQuantsAdapter`/`convert.py`をReal-data Script
  経由で使用)。
- **Safety Criticality**: **HIGH**。Preregistration Immutability・
  Locked Test一度限りUnlock・Append-only Registry・Reproducibility
  Hashの本丸。
- **Approximate Size**: 10 files(+2 scripts)、約1,795 LOC
  (research 732 + registry 175 + strategies 157 + schemas該当分
  約200 + scripts 931)。
- **Recommended Independent Audit**:
  1. `Preregistration.revise()`/`assert_not_mutated()`が全実行経路
     (`_run_and_record`等)で呼ばれているか。
  2. `LockedTestGate`/`FileBackedLockedTestGate`の重複Unlock拒否が
     File再構築後も保持されるか(`restore()`のDuplicate検知含む)。
  3. `ExperimentRegistry`/`PreregistrationRegistry`のAppend-only
     保証(`AppendOnlyViolationError`)に迂回経路が無いか。
  4. `phase5_v1_1_h0001_real_data.py`と`phase5_v1_short_term_
     reversal.py`(Synthetic版)の2 CLIの重複ロジック実態
     (Deferred Refactor候補の事前調査のみ、統合はしない)。
  5. `lib.reproducibility`のHash計算対象がCore Fields全体を
     カバーしているか(パラメータ変更が検知されない抜け道の有無)。
- **Audit Cost**: MEDIUM〜LARGE(Phase5固有の文脈[Preregistration
  Lineage・D0062〜D0067]の理解がある程度必要)。

### Unit 3 — J-Quants Data Sources & Ingestion Pipelines

- **Scope**: `lib/data_sources/`(base.py, convert.py, fixture.py,
  jquants.py, local_snapshot.py, ticker_codes.py)、
  `scripts/jquants_lab_pipeline.py`、
  `scripts/fetch_jquants_local_snapshot.py`、
  `scripts/lab_source_health.py`、`scripts/check_provider.py`、
  `scripts/jquants_financial_summary_diagnostic.py`、
  `scripts/schema_health_check.py`。
- **Responsibility**: J-Quants API V2 Client・Raw→Adjusted OHLCV
  変換・Corporate Action Event検出(convert.py)・Local Snapshot
  読み込み・疎通確認/Health Check系CLI。
- **Current Status**: `LIVE_CORE`(`jquants.py`/`convert.py`は
  Unit1/2からReal-data経路で直接利用)+ `LIVE_SUPPORT`
  (Health/Diagnostic系CLIは開発補助)。
- **Important Dependencies**: Unit1/2から呼ばれる(convert.py→
  Corporate Action Event→AsOfAdjustedPriceHistory)。
- **Safety Criticality**: **MEDIUM-HIGH**。`convert.py`の
  Corporate Action Event検出・Timestamp変換がUnit1のPIT保証の
  入力になるため、ここでのTimestamp誤りはUnit1へ伝播する。
- **Approximate Size**: 6 files + 6 scripts、約2,264 LOC
  (data_sources 1,041 + scripts大半 1,223)。
- **Recommended Independent Audit**:
  1. `convert.py`の`detect_corporate_action_events_from_equity_bars`
     がCase A/Case Bの区別を正しく維持しているか(D0032)。
  2. `JQuantsAdapter`がAPI Keyをログ・例外・Snapshotへ一切出力
     しないか(D0031既存保証の再確認)。
  3. `jquants_lab_pipeline.py`のRate Limit実装(60 req/min)が
     全Endpoint呼び出し経路をカバーしているか。
  4. Health/Diagnostic系4 scriptsが本番Pipelineから独立している
     ことの確認(誤って本番Pathへ混入していないか)。
- **Audit Cost**: MEDIUM。

### Unit 4 — Phase4 Capability-Specific Data Foundations(Future Capability)

- **Scope**: `lib/fundamentals/`、`lib/disclosures/`(+`providers/`
  以下のEDINET/TDnet/Company IR)、`lib/positioning/`(+`derived/`)、
  `lib/macro/`、`lib/global_market/`、`lib/news/`、`lib/consensus/`。
- **Responsibility**: Phase4A〜4Eで構築した、各種データSource
  (決算/開示/ポジション/マクロ/グローバル市場/ニュース/コンセンサス)
  ごとのModel/Normalize/View/Evidence/Catalog四点セット。
- **Current Status**: `FUTURE_CAPABILITY`。D0061 Phase5 Readiness
  Gateにより、Phase5 v1.1のLive Pathからは構造的に排除されている
  (Import Graph上も未接続、B節参照)。Dead Codeではない
  — 将来Phase(Phase5 v2以降)で接続される設計上の予定Capability。
- **Important Dependencies**: Unit5(`lib.evidence`/`lib.sources`を
  共通基盤として利用)。Unit1/2への依存は無い(逆方向の依存も無い)。
- **Safety Criticality**: **MEDIUM**。現在Liveでないため直接の
  研究結果への影響は無いが、UNKNOWN/PIT原則の一貫性(将来接続時に
  同じ品質を保つため)という意味で軽視できない。
- **Approximate Size**: 40 files、約6,964 LOC(`disclosures/`単体で
  3,114 LOC、他6 Capability合計3,950 LOC)。**LOC規模最大の
  Unit**であり、単一のCodex Taskに収めるにはやや大きい
  (G節でDisclosuresを別Task化することを推奨)。
- **Recommended Independent Audit**:
  1. 各Capability(fundamentals/disclosures/positioning/macro/
     global_market/news/consensus)がModel/Normalize/View/Evidence/
     Catalogの4〜5点セット構造を一貫して守っているか(構造的
     重複の実態調査、Refactor提案はしない)。
  2. `lib/disclosures/providers/`(EDINET ZIP正規化・TDnet Cursor・
     Company IR)がそれぞれ独立したProvider固有Logicとして分離
     されているか(共通化の余地があるかの調査のみ)。
  3. 各CapabilityのUNKNOWN/Fail-closed Semanticsの実装一貫性。
  4. Import Graph上、本当にUnit1/2/3から未参照であることの
     再確認(B節の主張の裏取り)。
  5. 各CapabilityがまだAdapter段階(NOT_IMPLEMENTED)かNormalize
     まで到達しているかのStatus一覧化。
  6. Test Coverageの規模(このUnit用Testは13_tests内に相当数
     存在、Unit6側から要参照)。
  7. 7 Capability間でのCode Duplication実態(Normalize/View
     PatternがどれだけCopy-Pasteされているか、数値で報告するのみ)。
- **Audit Cost**: LARGE(全体を1 Taskにすると大きすぎるため、
  G節では2〜3 Sub-taskへの分割を推奨)。

### Unit 5 — Evidence / Cross-Capability Core & Misc Lab Schemas

- **Scope**: `lib/evidence/`(model.py, decision_log.py, news.py,
  packet.py, retrieval.py)、`lib/sources/`(catalog.py,
  entity_registry.py, providers.py)、`lib/schemas/idea.py`、
  `lib/schemas/knowledge.py`、`lib/schemas/paper_trade.py`、
  `lib/schemas/portfolio_rules.py`、`lib/schemas/strategy.py`。
- **Responsibility**: 全Phase4 Capability共通のEvidence Model
  (PIT/Revision拡張・Anti-confirmation Guardrail・Decision Evidence
  Log)、Source Catalog・Canonical Entity Registry、および現時点で
  未接続なLab用スキーマ群(Idea/Knowledge/Paper Trade/Portfolio
  Rules/Strategy — `03_idea_inbox`/`07_paper_trading`/`08_portfolio`
  ディレクトリ自体、README.mdのみでコード実体はまだ無い)。
- **Current Status**: 混在。`lib.sources.catalog`/
  `lib.evidence.model`はD0057(未解決)にも関連するため
  `FUTURE_CAPABILITY`寄りだが概念的にはUnit4を跨ぐ共通基盤。
  `idea.py`/`knowledge.py`/`paper_trade.py`/`portfolio_rules.py`/
  `strategy.py`はImporter数ゼロ(`lib/schemas`外から一切参照
  されていないことをgrepで確認)— `UNKNOWN`(Future予定か
  Legacy残骸か、このRoundでは判定しない)。
- **Important Dependencies**: Unit4から広く参照される(Evidence
  Model/Source Catalogは全Capabilityの共通基盤)。
- **Safety Criticality**: **MEDIUM**(D0057 Cross-Capability PIT
  Gate Consistencyが未解決のまま残っている領域)。
- **Approximate Size**: 8 lib files + 5 schema files、約1,472 LOC。
- **Recommended Independent Audit**:
  1. `idea.py`/`knowledge.py`/`paper_trade.py`/`portfolio_rules.py`/
     `strategy.py`の各Importer数を再確認し、UNKNOWN分類の妥当性を
     検証(Codexが独自に再Grepしてよい)。
  2. `lib.evidence.model`のPIT/Revision拡張が実際にどのCapability
     から呼ばれているか(呼ばれていないなら理由をD0057文脈で確認)。
  3. D0057(未解決)がこのUnitのどこに影響しているかの再整理。
- **Audit Cost**: SMALL〜MEDIUM。

### Unit 6 — Test Infrastructure

- **Scope**: `Japanese_Equity_Lab/13_tests/`(84 files、約16,070 LOC、
  `fixtures/`サブディレクトリ含む)。
- **Responsibility**: 上記Unit1〜5に対応する回帰Test群(概ね1
  Module=1 Test Fileの慣習)、原則ベースTest(`test_pit_principles.py`
  等)、Structural/Adversarial Test(`test_agent_governance.py`等)。
- **Current Status**: `TEST_INFRASTRUCTURE`。lib本体(約12,636 LOC)
  より大きい(約16,070 LOC)。
- **Important Dependencies**: 全Unit(1〜5)に対応。
- **Safety Criticality**: 直接のCode Executionとしては該当しない
  が、Principle/Semantic/Adversarial Testはこの Repositoryの
  Research-Safety保証そのものであり、変更・削除は極めて慎重に
  扱うべき(このRoundでは一切変更しない)。
- **Approximate Size**: 84 files、約16,070 LOC。単一のCodex Task
  には大きすぎるため、G節ではUnit1〜5対応分ごとに分割することを
  推奨。
- **Recommended Independent Audit**:
  1. 各Testファイルの対応する`lib/`Moduleとの1:1対応関係の一覧化
     (対応が無い/複数対応のTestを洗い出す)。
  2. Fixture(`13_tests/fixtures/`)の重複・未使用ファイルの実態調査
     (削除提案はしない、実態報告のみ)。
  3. Principle-based Test(`test_pit_principles.py`)・Governance
     Test(`test_agent_governance.py`)・Adversarial Testの一覧化と
     カバレッジ範囲の明確化。
  4. Codex提案済みの「Catalog Invariant Test Parameterization」
     候補(D0068で見送り済み)の再検証(Semantic Equivalence確認)。
- **Audit Cost**: LARGE(全体)。Unit別分割(例: Unit1対応Test/
  Unit2対応Test/Unit4対応Test)ならMEDIUM×3程度。

### Unit 7 — Documentation / Context Architecture / Decision History

- **Scope**: `Japanese_Equity_Lab/DECISIONS.md`(7,119行)、
  `RESEARCH_RULES.md`(728行)、`CLAUDE_CODE_RESEARCH_WORKFLOW.md`、
  `PHASE5_VALIDATION_ARCHITECTURE.md`、`PHASE5_READINESS.md`、他
  Architecture文書(`DATA_SOURCE_ARCHITECTURE.md`・各Capability別
  `*_ARCHITECTURE.md`等、計29 Markdownファイル)、`.claude/skills/`、
  `.claude/agents/`、Root`CLAUDE.md`/`README.md`/`CONTRIBUTING.md`。
- **Responsibility**: Decision History(Append-only)・研究原則・
  Agent/Skill定義・各Phase/Capabilityの設計判断記録。
- **Current Status**: `DOCUMENTATION`。
- **Important Dependencies**: 全Unitの設計判断根拠。特に
  `DECISIONS.md`はUnit1〜6全てを跨いで参照される。
- **Safety Criticality**: **LOW**(直接のCode Executionには関与
  しない)が、Research Integrityの説明責任という意味でHigh Value
  (Negative Evidence・過去の失敗・D0057のような未解決事項が
  ここにのみ記録されている)。
- **Approximate Size**: 29+ Markdown Files、DECISIONS.mdだけで
  7,119行(Repository最大の単一ファイル)。
- **Recommended Independent Audit**:
  1. `DECISIONS.md`内でNumbering重複・矛盾する記述が無いか
     (D0001〜D0068の連番整合性)。
  2. 各Capability`*_ARCHITECTURE.md`が対応する`lib/`実装と
     現時点で乖離していないか(Doc Drift調査のみ、修正はしない)。
  3. `VALIDATION_BACKLOG.md`に記録済みの未解決事項一覧と、
     実際にコード上残っている未解決Markerとの突合。
- **Audit Cost**: MEDIUM(DECISIONS.mdの分量が大きいが、
  Grep主体の調査で十分)。

### Unit 8 — Screening Tool(Protected、別Application)

- **Scope**: `core/`(cache.py, comparison.py, errors.py, forecast.py,
  lookup.py, models.py, providers/, screening.py, validation.py,
  watchlist.py)、`app.py`、Root`tests/`。
- **Responsibility**: 個人投資用の日本株・米国株横断スクリーニング・
  比較ツール(Japanese Equity Labとは独立したApplication、
  Root`CLAUDE.md`参照)。
- **Current Status**: `LIVE_CORE`(Labとは別Productとして)。
- **Important Dependencies**: `Japanese_Equity_Lab/`とのImport
  依存はゼロ(相互に独立、A節で確認済み)。
- **Safety Criticality**: このRepositoryのProtected Path Policy
  により**変更対象外**。Research-Safety(PIT等)の枠組みそのものが
  適用対象外(別Domainのため)。
- **Approximate Size**: 14 files、約904 LOC(core/)+ 211 LOC
  (app.py)+ 423 LOC(root tests/)。
- **Recommended Independent Audit**: このRepositoryのProtected
  Path Policy上、Codexへの独立監査対象として推奨しない
  (D0068で`core/cache.py`のDELETE_CANDIDATEが既に提示された際も
  Policyにより不採用とした)。監査自体を行いたい場合はPolicy解除
  の是非をユーザーに個別確認すること。
- **Audit Cost**: N/A(このRepositoryの文脈では対象外)。

## D. Unit Dependency Overview

```
Unit1 (Backtest/PIT/Universe Core)  ←── Unit2 (Phase5 Research Validation)
   ↑                                        ↑
   └── Unit3 (J-Quants Data Sources) ───────┘
                                                Unit4 (Phase4 Capabilities)
                                                   ↑
                                                Unit5 (Evidence/Cross-Capability)

Unit6 (Tests) は Unit1〜5 全てに対応Testを持つ(横断)
Unit7 (Documentation) は Unit1〜6 全てを記述(横断)
Unit8 (Screening Tool) は他の全Unitから独立(依存ゼロ、双方向)
```

Unit4/5(Phase4系)からUnit1/2/3への依存は無い。逆にUnit1/2/3から
Unit4/5への依存も無い(D0061 Readiness Gateが意図した分離が
実際のImport Graphでも保たれている)。

## E. Safety-Critical Boundaries

以下は、どのUnitを監査対象にする場合でも変更してはならない
(Codex Taskへ明示的にExclusionとして伝えること):

- **PointInTimeRecord**(Unit1、`lib/point_in_time.py`)
- **PIT Universe semantics**(Unit1、`lib/universe.py`の
  `UniverseResolution`/`survivorship_bias_unresolved`判定Logic)
- **AsOfAdjustedPriceHistory**(Unit1、`lib/backtest/price_history.py`)
- **Corporate Action PIT semantics**(Unit1/Unit3境界、
  `lib/schemas/price_data.py`の`build_provider_derived_adjusted_bars`
  と`lib/data_sources/convert.py`の検出Logic)
- **Preregistration immutability**(Unit2、`lib/research/
  preregistration.py`の`preregister()`/`assert_not_mutated()`/
  `revise()`)
- **Locked Test isolation**(Unit2、`lib/research/locked_test.py`)
- **Experiment / Research Registry semantics**(Unit2、
  `lib/registry/experiment_registry.py`・`lib/research/registry.py`
  のAppend-only保証)
- **Provenance**(Unit2、`lib/registry/provenance.py`)
- **Reproducibility hashes**(Unit2、`lib/reproducibility.py`)
- **Append-only history**(Unit2、全Registry/Preregistration File)
- **Negative evidence**(Unit7、DECISIONS.md・Conclusion Recordの
  記述内容)
- **UNKNOWN / fail-closed semantics**(Unit1/Unit4/Unit5横断)
- **Principle / Semantic / Adversarial tests**(Unit6、特に
  `test_pit_principles.py`・`test_agent_governance.py`・
  `test_pit_gate_cross_capability_semantics.py`)

## F. Recommended Audit Order

- **P1**: Unit6(Test Infrastructure、Unit1/2対応分優先) —
  他Unitの監査品質を担保する土台であり、まずTest CoverageのMapが
  無いと他Unitの安全な監査ができない。Maintenance Benefit高、
  Audit Suitability高(機械的な対応関係調査中心)、Research Safety
  Risk最低(調査のみ)。
- **P1**: Unit3(J-Quants Data Sources) — 比較的小規模(約2,264 LOC)
  でCodex 1 Taskに収まりやすく、Unit1/2への入力になるためEarly
  Confidence構築に有効。
- **P2**: Unit4(Phase4 Capabilities、まずDisclosures単体) —
  規模最大でMaintenance Benefitも高いが、Live実行に影響しないため
  Urgency自体は低い。Sub-task分割前提でP2とする。
- **P2**: Unit5(Evidence/Cross-Capability) — Unit4の共通基盤である
  ため、Unit4の一部Sub-taskと合わせて監査すると効率的。
- **P2**: Unit7(Documentation) — Doc Drift調査はいつでも実施
  可能だが緊急性は低い。
- **P3**: Unit1(Backtest/PIT Core) — Safety Criticality
  HIGHであるため、独立監査自体はいつか実施する価値が高いが、
  D0067でFinal PIT Audit(CLEAN)を通過したばかりであり、直近の
  優先度としては他Unitより下げる(Research Safety Riskが相対的に
  高いため、慎重にScopeを絞ったTaskとして別途設計すべきで、
  今回のManifestだけでは着手しない)。
- **P3**: Unit2(Phase5 Research Validation) — 同上、D0067の直後
  であり、Locked Test関連コードへの監査は特に慎重なScope設計が
  必要(調査であってもLocked Testを誤って実行させない Task設計が
  前提)。
- 対象外: Unit8(Screening Tool、Protected Path Policyにより
  このRepository文脈では非対象)。

## G. Codex-Sized Task Breakdown

以下は各Unitを実際にCodexへ渡す際の粒度イメージ(Prompt本文は
まだ作らない、Scope定義のみ)。

| Task | Unit | Exact Scope (files/dirs) | Relevant Tests | Exclusions |
|---|---|---|---|---|
| T-A | Unit6 (Unit1対応分) | `13_tests/test_backtest_engine.py`, `test_market_calendar.py`, `test_point_in_time.py`, `test_pit_as_of_adjustment.py`, `test_universe.py`, `test_universe_survivorship.py`, `test_trading_calendar_real_holidays.py`, `test_price_data.py`, `test_benchmark.py` | (これ自体がTest調査) | Unit1本体コードの変更提案は別Task |
| T-B | Unit3 | `lib/data_sources/` 全体、`scripts/jquants_lab_pipeline.py`, `scripts/fetch_jquants_local_snapshot.py`, `scripts/lab_source_health.py`, `scripts/check_provider.py`, `scripts/jquants_financial_summary_diagnostic.py`, `scripts/schema_health_check.py` | `test_data_sources.py`, `test_convert_phase3a.py`, `test_local_snapshot.py`, `test_ticker_codes.py`, `test_lab_source_health.py` | `lib/backtest/`, `lib/research/`(呼び出し先の詳細は見なくてよい、Interface契約のみ確認) |
| T-C | Unit4 (Disclosures単体) | `lib/disclosures/` 全体(`providers/`含む) | `test_disclosures_*.py`, `test_edinet_*.py`, `test_tdnet_*.py`, `test_company_ir_*.py` | `lib/fundamentals/`, `lib/positioning/`, 他Phase4 Capability |
| T-D | Unit4 (残り6 Capability) | `lib/fundamentals/`, `lib/positioning/`, `lib/macro/`, `lib/global_market/`, `lib/news/`, `lib/consensus/` | 対応する`test_fundamentals_*.py`, `test_positioning_*.py`, `test_macro_*.py`, `test_global_market_*.py`, `test_news_*.py`, `test_consensus_*.py`, `test_global_news_*.py` | `lib/disclosures/`(T-C側) |
| T-E | Unit5 | `lib/evidence/`, `lib/sources/`, `lib/schemas/{idea,knowledge,paper_trade,portfolio_rules,strategy}.py` | `test_evidence_*.py`, `test_entity_registry.py`, `test_source_catalog.py`, `test_source_providers.py`, `test_idea_schema.py`, `test_knowledge_schema.py`, `test_paper_trade_schema.py`, `test_strategy_schema.py` | `lib/fundamentals/`等の具体的なCapability実装 |
| T-F | Unit7 | `DECISIONS.md`, 全`*_ARCHITECTURE.md`, `RESEARCH_RULES.md`, `VALIDATION_BACKLOG.md` | N/A(Doc調査) | コード変更提案は別Task |

各Taskは他Unitの詳細実装を読む必要が無いよう、依存先は
「Public Interfaceの契約のみ」("D節"参照)で足りる設計にしている。

## H. First Recommended Codex Task

**T-B(Unit3: J-Quants Data Sources & Ingestion Pipelines)を最初の
Task候補として推奨する。**

理由: (1) 比較的小規模(約2,264 LOC)でCodexが1 Contextで十分
読み切れる、(2) Unit1/2への入力であるため、ここでのFinding
(命名の重複・未使用Helper等)が今後のUnit1/2監査の前提整理にも
役立つ、(3) Codexが既にPhase5関連の文脈(D0064〜D0068)を把握
済みであるため、隣接領域として調査コストが低い、(4) SessionSchedule
(D0068)で確立した「Spot-check→採用」フローをもう一度小さく回して
検証できる。

Scope骨子(Promptの完全な文面はこのRoundでは作らない):

- 対象: `lib/data_sources/`全体(base.py, convert.py, fixture.py,
  jquants.py, local_snapshot.py, ticker_codes.py)+ 6 scripts
  (T-B行のExact Scope参照)。
- 除外: `lib/backtest/`・`lib/research/`の内部実装(Interface
  契約[`PriceHistorySource`Protocol・`DataSourceAdapter`Protocol
  等]のみ参照可)。
- Relevant Tests: T-B行に記載の5 test files。
- 出力形式: Codex Auditの既存形式(Exact Path/Symbol/Caller
  Search/Import Search/Dynamic Reachability/Relevant Tests/
  Temporary Removal Test)をそのまま踏襲。
- 明示的に伝えるSafety Boundary: E節のCorporate Action PIT
  semantics(`convert.py`のCorporate Action Event検出Logic自体は
  変更対象外、Dead Code/Duplication調査のみ)。
