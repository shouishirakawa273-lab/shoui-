# Phase5 Readiness Decision(D0061: Phase4 Integrated Data Foundation Audit)

このDocumentは、Phase4で構築した10個のData Capability(Fundamentals/
EDINET/TDnet/Company IR/Positioning/Japan Macro/Global Market/Japan
News/Global News/Consensus)を横断的に監査し、Phase5(仮説の事前登録・
PIT-safeなDatasetでの反証可能な検証)を開始してよいかを判定した結果を
記録する。**新しいData Sourceは追加していない。** 実装変更はゼロ
(Audit-only Round、後述Reviewer Pass分を除く)。

## 中心原則(このAudit全体を貫く区別)

```
CODE COMPLETE       != REAL-WORLD VALIDATED
DESIGN COMPLETE      != SOURCE CONNECTED
FIXTURE VALIDATED    != REAL DATA VALIDATED
SPEC UNVERIFIED       != USABLE FOR BACKTEST
TESTS PASS            != RESEARCH SEMANTICS CORRECT
REAL DATA CONNECTED   != PIT-SAFE USABLE   ← 今回のAuditで新たに顕在化した第6の区別(EDINET、後述)
```

---

## A. Repository Reality Check — 最重要の発見

**「現在Live/実際に配線されているPIT Pipelineは何か」を実Codeで直接確認
した。** これがPhase5 PIT Source of Truthの判断の土台になる。

- `scripts/jquants_lab_pipeline.py`(Repo Root、`Japanese_Equity_Lab/`
  ではない)が実在し、`sys.path`へ`Japanese_Equity_Lab`を挿入した上で
  `lib.backtest.{engine,price_history}`・`lib.data_sources.*`・
  `lib.universe`・`lib.schemas.{price_data,experiment,hypothesis}`・
  `lib.registry.*`・`lib.reproducibility`・`lib.snapshot`・`lib.
  strategies.fixed_pipeline_validation`・`lib.market_calendar`をImport
  する(pit-auditor Finding、Phase4Audit: 当初の記述は一部Moduleを
  省略した不完全な列挙だった)。**重要なのは列挙の完全性ではなく**、
  この全Import一覧のいずれにも`lib.fundamentals`/`lib.disclosures`/
  `lib.positioning`/`lib.macro`/`lib.global_market`/`lib.news`/
  `lib.consensus`/`lib.evidence.*`のいずれも一切含まれないこと
  (Grep・Function内部のLate Import含め全数確認済み)。
- **`lib.fundamentals`/`lib.disclosures`/`lib.positioning`/`lib.macro`/
  `lib.global_market`/`lib.news`/`lib.consensus`/`lib.evidence.*`の
  いずれも、この実Pipeline Scriptから一切importされていない**(Grep
  で確認、ゼロ件)。
- `lib.backtest.engine.BacktestEngine.run()`の実Signatureを確認した:
  `price_history: PriceHistorySource`・`benchmark_bars`・
  `trading_calendar`・`signal_fn: Callable[[Sequence[AdjustedOHLCVBar]],
  bool]`・`sector_by_code`・`universe_provider: UniverseProvider | None`
  のみを受け取る。`EvidenceRecord`/`RevisionHistory`/Phase4 Data
  Foundation型のいずれも引数に無い。`signal_fn`はPrice Barのみを見る。
- `BacktestEngine.run()`は内部で`lib.point_in_time.PointInTimeRecord`
  (`published_at`/`available_at`のtz-aware必須・`available_at >=
  published_at`を`__post_init__`で強制する、古いが独立したPIT Primitive)
  を構築し、`assert_no_lookahead()`でGateする——これが**唯一の、実際に
  実行されるBacktestで機能しているPIT Gate**である。
- `lib.evidence.model.filter_usable_at()`(Evidence経路のPIT Filter)は、
  `lib/evidence/`自身の外からは**一件も呼び出されていない**(Grep済み、
  `lib/news/evidence.py`・`lib/consensus/evidence.py`・
  `lib/disclosures/evidence.py`のDocstringが「呼ばない」と明記して
  いるのみ)。`lib.fundamentals.evidence.disclosure_metric_to_evidence()`
  /`lib.disclosures.evidence.disclosure_document_to_evidence()`も同様に
  `scripts/`・`lib/backtest/`のいずれからも呼ばれていない。
- `scripts/jquants_lab_pipeline.py`は実際に`ListingBasedUniverseProvider`
  を構築し`BacktestEngine.run(..., universe_provider=universe_provider)`
  として渡している(Phase3C PIT Universeは実際に配線されている)。

**結論**: このLabで「実際に人間がBacktestを実行したときに動くPIT
Pipeline」は、Price(J-Quants OHLCV + Corporate Action As-of Adjustment)
+ PIT Universe + `PointInTimeRecord` Gateの組だけである。Phase4A〜4E-4
で構築したCapability群(Fundamentals含む)は、**Data Foundationとしては
実在するが、どれ一つとして自動化されたSignal評価には未接続**。

---

## B. Phase4 Capability Readiness Matrix

### B-1. 一覧(概観)

| Capability | Implementation Status | Validation Status | Official Spec Status | Real Data Status | PIT Confidence | Phase5 Usability |
|---|---|---|---|---|---|---|
| J-Quants Price(参考、Phase3A/3A.1/3A.2) | CONNECTED | REAL_DATA_VALIDATED | 未検証部分あり(HolDiv/AdjFactor公式仕様確定) | 実データ・実Backtest稼働中 | HIGH(`PointInTimeRecord`+As-of Adjustment) | READY_FOR_PHASE5 |
| PIT Universe(参考、Phase3C) | CONNECTED | REAL_DATA_VALIDATED(PARTIAL Resolution明示) | J-Quants `/listed/info`のみ、Universe定義自体は自前 | 実データ・実Backtest稼働中 | HIGH | READY_FOR_PHASE5 |
| Fundamentals | COMPLETE / CONNECTED | REAL_DATA_VALIDATED(4銘柄) | 一部未検証(Field名一部、DocType `_JP`意味等) | 実データ疎通・Parse確認済み | HIGH(構造は健全) だがBacktest未配線 | READY_WITH_RESTRICTIONS(WIRING_UNDESIGNED) |
| EDINET | COMPLETE(Raw Fetch)/ CONNECTED | REAL_DATA_VALIDATED(Raw Fetch/ZIP) だが**PIT不可** | 一部未検証(Type2-5等) | 実データ疎通確認済み | **NONE**(`pit_available=False`固定、Historical PIT Reconstruction不可能とDocstringが明記) | NOT_READY_FOR_PHASE5 |
| TDnet | NOT_IMPLEMENTED(Code Complete、真のValidation未実施) | SPEC_UNVERIFIED(`EXTERNAL_OFFICIAL_SPEC_VERIFICATION`はClaude自身の一次確認ではない) | 未検証(第三者申告のみ) | 未接続(Add-on契約要) | 該当なし(`pit_available=False`) | NOT_READY_FOR_PHASE5 |
| Company IR | SKELETON | SPEC_UNVERIFIED(`EGRESS_BLOCKED`終始) | 未検証(個別企業ごとに異なる) | 未接続 | 該当なし(`pit_available=False`固定) | NOT_READY_FOR_PHASE5 |
| Positioning(price_derived) | CONNECTED | FIXTURE_VALIDATED(合成Barのみ、上流Price自体はREAL_DATA_VALIDATED) | 該当なし(Network I/O無し、既存Price由来) | 上流REAL/自身FIXTURE | MEDIUM-HIGH | READY_WITH_RESTRICTIONS(VALIDATION_PENDING) |
| Positioning(margin/short-ratio等4候補) | NOT_IMPLEMENTED | SPEC_UNVERIFIED | 未検証 | 未接続 | 該当なし | NOT_READY_FOR_PHASE5 |
| Japan Macro | NOT_IMPLEMENTED | SPEC_UNVERIFIED(`EGRESS_BLOCKED`) | 未検証 | 未接続 | 該当なし | NOT_READY_FOR_PHASE5 |
| Global Market | NOT_IMPLEMENTED | SPEC_UNVERIFIED(`EGRESS_BLOCKED`) | 未検証 | 未接続 | 該当なし | NOT_READY_FOR_PHASE5 |
| Japan News | NOT_IMPLEMENTED | SPEC_UNVERIFIED(`EGRESS_BLOCKED`) | 未検証 | 未接続 | 該当なし | NOT_RELEVANT_TO_PHASE5_V1 |
| Global News | NOT_IMPLEMENTED | SPEC_UNVERIFIED(`EGRESS_BLOCKED`) | 未検証 | 未接続 | 該当なし | NOT_RELEVANT_TO_PHASE5_V1 |
| Consensus | NOT_IMPLEMENTED | SPEC_UNVERIFIED(`EGRESS_BLOCKED`) | 未検証 | 未接続 | 該当なし | NOT_RELEVANT_TO_PHASE5_V1 |

News(Japan/Global)とConsensusは「危険だから禁止」ではなく「Phase5 v1の
Scope外」という位置付けのため`NOT_RELEVANT_TO_PHASE5_V1`とした(§45の
原則、将来Validation完了後にFeature化しうる)。Japan Macro/Global Market
は将来Phase5 v2以降でMarket Context Featureとして使う可能性が具体的に
あるため`NOT_READY_FOR_PHASE5`(現時点で使用禁止、将来有望)とした。

**`READY_WITH_RESTRICTIONS`は単一の均質なTierではない(skeptic-reviewer
Finding、Phase4 Audit)**: Fundamentals(`WIRING_UNDESIGNED`)と
Positioning price_derived(`VALIDATION_PENDING`)を同じLabelでまとめると、
両者が同程度に「あと少しでPhase5で使える」状態であるかのように読めて
しまうが、実際の残作業の性質は全く異なる。Positioningは「既に`BacktestEngine`
配線と同型のPrice Bar経路上でCONNECTED、残るのはReal-data End-to-End
Validation(Backlog #10)という検証Taskのみ」。Fundamentalsは
「`BacktestEngine.run()`のSignature自体にまだ存在しない新規接続点を
設計・実装する必要があり(N節item 4、次Roundの独立したDesign
Decision)、検証以前に設計そのものが未着手」。この非対称性を見落とさない
よう、B-1表ではLabelへ`(WIRING_UNDESIGNED)`/`(VALIDATION_PENDING)`の
Sub-tagを付与した。

### B-2. 詳細(Capabilityごと)

#### Fundamentals
- Raw Data Availability: あり(`RawSnapshotStore`、Immutable)。
- Pure as_of: `lib.fundamentals.view.fundamentals_as_of()`(Offline、
  `RevisionHistory`ベース)。
- Evidence Conversion: `disclosure_metric_to_evidence()`あり、
  **Backtestへは未接続**(A節参照)。
- Backtest Wiring: **無し**。
- Entity/Series Identity Confidence: MEDIUM(`series_id`はCaller責務、
  `entity_id`はEntity Registry経由、4銘柄では健全に機能したが大規模
  適用は未検証)。
- Revision/Vintage Confidence: HIGH(D0049 PIT Bugfix済み、4銘柄実データ
  で`RevisionHistory`健全動作確認)。
- Source Catalog Status: 単独Descriptor登録のみ(`SourceCatalog`への
  一元Instantiate無し、他Capabilityと同じ)。
- Known Limitations: Non-Consolidated DocType未確認、USGAAP未確認、
  4Q/5Q未確認、Correction Relationship未確認(§前回Decisions参照)。
- Backlog IDs: 無し(Fundamentals自体はBacklogに項目を持たない、
  COMPLETE)。

#### EDINET
- Raw Data Availability: あり(ZIP、SHA-256確認済み、Canonical Content
  Hash機構あり)。
- Pure as_of: `disclosures_as_of()`は存在するが、EDINET由来Recordは
  `market_public_at`/`provider_available_at`が構造的に`UNKNOWN`のまま
  であり、Filter結果は事実上空になる(**PIT_ARCHITECTURE_GAPではなく、
  Source固有の不可避な制約**、Docstringが明記)。
- Evidence Conversion: あり、Backtest未接続。
- Backtest Wiring: 無し。
- Entity/Series Identity Confidence: LOW(`document_kind`Mapping・
  `entity_id`のRole-aware解決いずれも未実装)。
- Revision/Vintage Confidence: **該当なし**(Historical Point-in-Time
  Reconstruction自体が不可能、Documents Listが日次で書き換わる)。
- Source Catalog Status: 単独Descriptor登録、`CONNECTED`。
- Known Limitations: 上記に加えForward Snapshot Observation未実施
  (Backlog #4)。
- Backlog IDs: #4。

#### TDnet
- Raw Data Availability: Add-on契約が前提、未確認。
- Pure as_of: Code上は存在するが、`pit_available=False`のまま。
- Evidence Conversion: あり、未接続。
- Backtest Wiring: 無し。
- Entity/Series Identity Confidence: 未評価(実データ無し)。
- Revision/Vintage Confidence: 未評価。
- Source Catalog Status: 単独Descriptor、`NOT_IMPLEMENTED`。
- Known Limitations: D0047/D0048参照、`EXTERNAL_OFFICIAL_SPEC_
  VERIFICATION`はClaude自身のPrimary Verificationではない。
- Backlog IDs: #1。

#### Company IR
- Raw Data Availability: 個別URL、未接続(EGRESS_BLOCKED)。
- Pure as_of: Code上は存在するが`pit_available=False`固定(構造的に
  `provider_available_at`を設定する経路自体が無い)。
- Evidence Conversion: あり、未接続。
- Backtest Wiring: 無し。
- Entity/Series Identity Confidence: 未評価。
- Revision/Vintage Confidence: 未評価。
- Source Catalog Status: 単独Descriptor、`SKELETON`。
- Known Limitations: Manual/User-specified URL Firstのv1限定、Compliance
  Gate必須。
- Backlog IDs: #2、#3。

#### Positioning(price_derived_liquidity)
- Raw Data Availability: 該当なし(既存Price Barから導出、新規Network
  I/O無し)。
- Pure as_of: `positioning_as_of()`(Offline、`RevisionHistory`ベース)。
- Evidence Conversion: あり、未接続。
- Backtest Wiring: 無し。
- Entity/Series Identity Confidence: HIGH(Priceと同じEntity識別子を
  再利用)。
- Revision/Vintage Confidence: HIGH(理論上単純、単一Sourceで導出値の
  ため訂正概念自体が薄い)。
- Source Catalog Status: 単独Descriptor、`CONNECTED`。
- Known Limitations: 合成Bar Dataでの検証のみ、実J-Quants Priceに対する
  End-to-End Local Validation未実施(上流Price自体は既にReal Data
  確認済み)。
- Backlog IDs: #10。

#### Positioning(margin/short-ratio/short-sale-report/trades_spec)
- 4候補とも`NOT_IMPLEMENTED`、Backlog #5〜9。実データ未接続、Endpoint
  仕様自体SEARCH-SNIPPET-DERIVED。

#### Japan Macro / Global Market / Japan News / Global News / Consensus
- 5 Capabilityとも共通パターン: **Adapterゼロ、Real Data接続ゼロ**、
  Model/Normalize/View/Evidence/Catalogの各Common Coreは実装・Fixture
  Testで健全動作確認済み(Backlog IDsは各`*_ARCHITECTURE.md`参照:
  Macro #11〜15、Global Market #16〜20、Japan News #22〜26、Global News
  #27〜29、Consensus #30〜33)。
- Pure as_of: 全Capability実装済み(`macro_as_of()`/`global_market_as_of()`
  /`news_as_of()`/`consensus_as_of()`)、いずれもOffline・Deterministic。
- Evidence Conversion: 全Capability実装済み、いずれもBacktest未接続
  (`filter_usable_at()`を一切importしないことをAST走査で構造的に固定
  済み、D0057・D0058・D0059・D0060それぞれで確認)。
- Entity/Series Identity Confidence: `series_id`はいずれもCaller責務
  (§14で詳述)、実Adapterが無いため実データでの検証はゼロ。
- Revision/Vintage Confidence: Macroのみ同一`available_at`Tie-break
  Known LimitationをPinning Test化済み(`test_macro_pit.py`)、他4
  Capabilityは同型のRiskを持つが個別Pinning Testは無い(実Sourceが
  無いため優先度は低いと判断済み、既存Decision通り)。

---

## C. Validation Backlog Classification(33件全件)

既存`VALIDATION_BACKLOG.md`の内容は変更していない(削除・書き換え無し)。
各項目にPhase5 Dependencyを付与する。

| # | 項目 | Phase5 Dependency |
|---|---|---|
| 1 | TDnet Add-on Local Validation | BLOCKS_SPECIFIC_CAPABILITY_ONLY(TDnetをPhase5で使う場合のみ) |
| 2 | Company IR Live Validation #1 | BLOCKS_SPECIFIC_CAPABILITY_ONLY |
| 3 | Company IR Live Validation #2 | BLOCKS_SPECIFIC_CAPABILITY_ONLY |
| 4 | EDINET Forward Snapshot Observation | SHOULD_RESOLVE_BEFORE_PHASE6(EDINETを将来PIT-safe化する前提条件) |
| 5〜9 | Positioning需給5候補(margin等) | LONG_TERM_VALIDATION |
| 10 | Positioning price_derived Real Data Validation | SHOULD_RESOLVE_BEFORE_PHASE6(Phase5 v1で使う場合は先に解消推奨、Blockerではない) |
| 11〜15 | Japan Macro 5候補 | LONG_TERM_VALIDATION(Phase5 v1 Scope外) |
| 16〜20 | Global Market(FRED等)5候補 | LONG_TERM_VALIDATION |
| 21 | D0057 Evidence path vs as_of path(Backtest System Bの正) | **BLOCKS_PHASE5 as designed** ではなく、D節で個別判定(NON_BLOCKER、条件付き) |
| 22〜25 | Japan News候補・BOJ重複 | OPTIONAL(Phase5 v1 Scope外) |
| 26 | NewsArticleRecord ↔ NewsEvent reconciliation | OPTIONAL、F節で個別判定 |
| 27〜29 | Global News候補 | OPTIONAL(Phase5 v1 Scope外) |
| 30〜33 | Consensus候補・entity_id Mapping | OPTIONAL(Phase5 v1 Scope外) |

**重要**: Backlogが33件存在すること自体はPhase5全体のBlockerではない
(§8既定原則通り)。BLOCKS_PHASE5に分類された項目はゼロ——最も重い#21
も「設計判断」であり、次節の通り現状の使い方を守る限りBlockerではない。

---

## D. D0057 / Validation Backlog #21 — Phase5 Blocker判定

**判定: NON_BLOCKER(条件付き)**

判定基準(§34、A/B/C全て要求):

- A. Phase5 v1で実際に使用するか: **いいえ**。A節で確認した通り、
  `filter_usable_at()`/Evidence経路はこのRepositoryのどこからも
  (Backtest含め)呼ばれていない。Phase5 v1がこの経路を新規に呼ばない
  限り、#21のARCHITECTURE_GAPはDormantのまま。
- したがってB・Cを検討するまでもなくNON_BLOCKER。

**ただし条件がある**(L節Blockerリストにも記載): Phase5 v1が
`EvidenceRecord` → `filter_usable_at()` → Backtest/Validationという
経路を**新規に配線する場合**、その瞬間に#21はBLOCKERへ転化する
(Canonical as_of経路とEvidence経路が異なるAvailability推定戦略を
持つため、どちらを「正」とするかを設計判断せずに配線すると、
Capabilityによって異なる基準が暗黙に混在するリスクがある)。今回
このAudit中にCommon Coreを変更すること・#21を解決することはしない
(§11、§35で明示的に禁止)。

Backlog #21はOPENのまま維持する(`VALIDATION_BACKLOG.md`は変更しない)。

---

## E. RevisionHistory Tie-break — Phase5 Blocker判定

**判定: NON_BLOCKER**

判定基準(§12 A〜D)。**最も強い根拠から先に示す(skeptic-reviewer
Finding、Phase4 Audit: 当初「4銘柄で未発生」という Absence-of-
Observation Argumentを主根拠にしていたが、これは「発生し得るか
(Could occur)」という§12 Aの問い自体には弱い回答であり、より強く
根拠のある「そもそもPhase5 v1では起動されない」という理由を主根拠へ
差し替えた)**:

- **主根拠(A節/K節の結論から直接導かれる)**: Fundamentals/Positioning
  いずれも、A節・K節で確認した通りPhase5 v1では`BacktestEngine`の
  自動化されたSignal評価Loopへ一切配線されない(Fundamentalsは
  `WIRING_UNDESIGNED`、Positioningは`VALIDATION_PENDING`だが両者とも
  自動Signal Loop未接続)。したがって`RevisionHistory.as_of()`の
  Tie-break Behaviorが実際にBacktest判断へ影響する実行経路自体が
  Phase5 v1には存在せず、規模に関わらずこのRoundでは発火しえない。
- A. (補助的根拠)Phase5 v1候補で実際に発生し得るか: 同一`series_id`へ
  同一`available_at`を持つ複数`SourceVersion`が実データで観測された
  実績は無い(Fundamentals 4銘柄Real Data Validationでも未発生)。
  **ただしこれはn=4という小標本での非観測に過ぎず、将来Fundamentals
  Coverageが拡大した場合の発生確率を強く保証するものではない**——
  主根拠(Backtest未接続そのもの)ほど強い論拠ではないため、補助的
  根拠として位置付ける。
- B. 発生した場合、結果が変わるか: 理論上は変わりうる(`max()`の仕様上
  最初の候補が勝つ、Pythonのsort安定性に依存)。
- C. Provider-native orderingは存在するか: Fundamentals/Positioningの
  いずれも、Provider側の明示的なVersion順序Fieldを現在利用していない。
- D. Phase5 Blockerか: **いいえ**——主根拠(Phase5 v1では実行経路自体が
  存在しない)により§34の「Concrete Failure Mode」要求を満たさない。
  「将来危険そう」だけではBlockerにしないという§35原則にも合致する。
  **ただしFundamentalsを将来Backtest Signal Loopへ配線する設計
  (N節item 4)を行う際は、この判定を無条件に引き継がず、その時点の
  実Coverage規模で再評価すること。**

既存のMacro向けPinning Test(`test_tie_on_identical_available_at_is_
input_order_dependent_known_limitation`)は維持する。今回、新たな
Secondary Key・Tie-break Logicの追加は行わない(§12末尾の明示禁止)。
`VALIDATION_BACKLOG.md`への新規項目追加は不要と判断した(既存#21の
近傍Riskとして、このDocument自体で十分に記録済みのため——Backlog
項目の重複作成を避ける、§36)。

---

## F. NewsEvent Reconciliation — Phase5 Blocker判定

**判定: NON_BLOCKER**

Japan News/Global NewsはPhase5 v1 Scope外(`NOT_RELEVANT_TO_PHASE5_V1`、
B節)であるため、`NewsArticleRecord` ↔ 既存`NewsEvent`(Phase3D Event層)
の関係整理は現時点でPhase5と無関係。Backlog #26はOPENのまま維持し、
News自体をPhase5で使う判断をする回に再評価する。今回、Event Layer・
Reconciliation Layerいずれも実装しない(§13で明示的に禁止)。

---

## G. Entity / Series Identity Risks

Caller-responsibility(呼び出し側がGroupingを壊さない一意な`series_id`
を構築する責務を負う設計)は、Macro/Global Market/Consensusで共通の
パターン(Fundamentals/Positioningも同型)。

- **Macro**: `series_id`にReference Period・Seasonal Adjustment軸を
  含めない場合のCollapse Failureは、`test_macro_pit.py`でPinning Test
  化済み。
- **Global Market**: `session_date`軸・`index_return_type`軸の
  Collapse Failureは`test_global_market_pit.py`でPinning Test化済み
  (`price_type`/`currency`軸は未Pinning、Known Limitationとして
  D0056に明記済み)。
- **Consensus**: `source_id`(Provider)を含めるべき、という責務が
  D0060 Reviewer Passで明文化済み(直近のPhase4E-4で修正)。
- **News(Japan/Global)**: `series_id`概念自体を持たない
  (Document-shaped、Set Filter方式)ため、この種のCollapse Riskは
  構造的に存在しない。
- **Positioning**: Fundamentalsと同型の`series_id`構築責務。

**結論**: Phase5 v1で実際に使うCapability(Fundamentals/Positioning
price_derived)については、いずれもFixture Testでの検証に加え
Fundamentalsは実データ4銘柄でCollapse無く動作したことを確認済み
(Real Data Validated)。追加のReal-data Series Identity Validationは
不要と判断する。Macro/Global Market/Consensus(Phase5 v1 Scope外)は
Fixture Testのみで現状十分(Adapterが無い以上、Real-data Validationは
不可能かつ不要)。

---

## H. Catalog / Status Consistency Audit

- **Catalog統合状況**: 全10 CapabilityともStandalone Descriptor登録
  のみ(`SourceCatalog([...])`による一元Instantiateは、Production Code
  上どこにも存在しない、Grep確認済み)。これはPhase4を通じた一貫した
  設計(将来の一元登録は別Roundの課題)であり、今回Registry再設計は
  行わない(§15で明示的に禁止)。**Phase5 Blockerではない**(Catalogは
  検索補助Metadataであり、実際のPIT Gateとは独立)。
- **Status矛盾Check**: `ImplementationStatus`(NOT_IMPLEMENTED/SKELETON/
  CONNECTED)と自由記述Validation Status(FIXTURE_VALIDATED/REAL_DATA_
  VALIDATED/EGRESS_BLOCKED等)の組み合わせを全10 Capability分Grep
  確認した結果、`NOT_IMPLEMENTED`+`LIVE_VALIDATED`のような矛盾する
  組み合わせは**発見されなかった**。EDINETの`CONNECTED`+`pit_
  available=False`は矛盾ではなく意図的な区別(「実データ接続できる」
  と「PIT安全に使える」は別軸、A節の第6の区別)。
- **Documentation Truth Audit**: DECISIONS.mdの各Decisionは、後続の
  「追記」形式で上書き・訂正されており(例: D0043→D0043追記→D0043
  追記2でPhase4A最終StatusがCOMPLETEへ確定)、今回の監査ではLater
  Decisionを優先して読んだ。矛盾は発見されなかった。**唯一の実質的な
  Documentation Gapは、`scripts/jquants_lab_pipeline.py`がRepo Root
  (`Japanese_Equity_Lab/`の外)に存在するという事実がLab内Docstring・
  Test Comment上では暗黙の前提としてのみ扱われ、明示的にPath言及
  されている場所が少ないこと**(実害は無し、README.md/LOCAL_DATA_
  FETCH_GUIDE.mdは正しいPathで案内済み)。

---

## I. Phase5 v1 Allowed Data(PHASE5_V1_ALLOWED_DATA)

| Dataset | Source | Validation Level | PIT Mechanism | Known Limitations | Allowed Uses | Forbidden Uses |
|---|---|---|---|---|---|---|
| J-Quants Price(OHLCV、Split調整込み) | J-Quants API V2 | REAL_DATA_VALIDATED、実Backtest稼働中 | `PointInTimeRecord`+`AsOfAdjustedPriceHistory`(D0034/D0035) | HolDiv/AdjFactor一部未確認事項あり(D0034) | Backtest Signal入力、Benchmark計算 | Case A(Announcement-based Signal、未実装のまま) |
| PIT Universe(上場銘柄) | J-Quants `/listed/info` | REAL_DATA_VALIDATED | `ListingBasedUniverseProvider.as_of()` | PARTIAL Resolution明示(D0038) | Universe Eligibility判定 | 将来上場銘柄の知識を過去へ混入させない(既存Guard維持) |
| Fundamentals(Financial Summary) | J-Quants `/v2/fins/summary` | REAL_DATA_VALIDATED(4銘柄) | `fundamentals_as_of()`(Offline、RevisionHistoryベース) | Non-Consolidated/USGAAP/4Q5Q/Correction Relationship未確認 | Research観察・Featureとして**新規配線した上で**使用(Read-only、Offlineのas_of View経由のみ、BacktestEngineへの接続は次Roundの設計課題) | Evidence経路(`filter_usable_at`)経由での使用禁止(D節) |
| Positioning(price_derived_liquidity) | 既存Price Bar由来(導出) | FIXTURE_VALIDATED(Formula)、上流はREAL_DATA_VALIDATED | `positioning_as_of()` | 実Price E2E未検証(Backlog #10) | Research観察のみ、Signal入力前に#10の解消を推奨 | 高度なSignal化(Short Squeeze Score等)への転用 |

---

## J. Phase5 v1 Forbidden Data(PHASE5_V1_FORBIDDEN_DATA)

| Capability | 理由 |
|---|---|
| EDINET | PIT_ARCHITECTURE_GAP相当(`pit_available=False`固定)、NO_HISTORICAL_VINTAGE(Documents Listが日次で書き換わり過去のPIT状態を再現不能) |
| TDnet | SPEC_UNVERIFIED(Claude自身の一次検証なし)、Add-on契約未確認 |
| Company IR | SPEC_UNVERIFIED(EGRESS_BLOCKED終始)、LICENSE_UNVERIFIED(Compliance未確認のまま自動Fetchしない設計) |
| Positioning(price_derived以外の4候補) | SPEC_UNVERIFIED、FIXTURE_ONLY未満(Adapterゼロ) |
| Japan Macro | SPEC_UNVERIFIED、FIXTURE_ONLY |
| Global Market | SPEC_UNVERIFIED、FIXTURE_ONLY |
| Japan News | SPEC_UNVERIFIED、FIXTURE_ONLY、ENTITY_MAPPING_UNVALIDATED |
| Global News | SPEC_UNVERIFIED、FIXTURE_ONLY、ENTITY_MAPPING_UNVALIDATED |
| Consensus | SPEC_UNVERIFIED、FIXTURE_ONLY、ENTITY_MAPPING_UNVALIDATED(Backlog #33) |

Model/Architecture/Fixture Testの存在自体は維持する(§7、架空Adapterは
作らない、既存Codeの削除もしない)。

---

## K. Phase5 PIT Source of Truth(推奨)

**二重Gateを併用しない、という要求(§32)への回答:**

Phase5 v1は**既存の実配線Pipeline**(`BacktestEngine` +
`lib.point_in_time.PointInTimeRecord` + `PriceHistorySource`/
`AsOfAdjustedPriceHistory` + `ListingBasedUniverseProvider`)を、
実際にSignalとして評価されるBacktest Executionの唯一のPIT Source of
Truthとする。

Fundamentals等、Capability-level `*_as_of()` Canonical Viewは、
Backtest Executionへ**まだ接続しない**——Research観察・手動Inspection
専用のOffline Read Pathとして扱う。EvidenceRecord/`filter_usable_at()`
経路はPhase5 v1では一切使用しない(D節)。

**理由(§33、最小Complexity):**

1. `PointInTimeRecord`は既にReal Dataで稼働実績があり(Price/
   Universe/Corporate Action)、新たな信頼構築が不要。
2. Evidence経路は本番Callerがゼロで、D0057が指摘した2経路の不一致
   Riskをまだ内包している(#21解決には設計判断が必要、今回は行わない)。
3. Capability-level `*_as_of()`はOffline/Deterministicで安全に
   Research用途に使えるが、Backtest Signal Loopへ接続するには
   `BacktestEngine.run()`のSignatureを拡張する新規設計が必要
   (今回は実装しない、N節「Proposed Phase5 v1 Scope」で次Roundの
   課題として明示するに留める)。

---

## L. Phase5 Blockers(最終)

**ゼロ件。** §34の基準(A実際に使用 AND B Concrete Failure Mode AND
C 既存Guardで防げない)を満たすBlockerは今回のAuditで発見されなかった。

**条件付きBlocker候補(現時点では発火していない)**: Phase5 v1が
Evidence経路(`filter_usable_at()`)をBacktestへ新規配線した場合、
D0057 #21がその瞬間BLOCKERへ転化する。この配線をしない限りBlocker化
しない。

---

## M. Non-blocking Backlog(要約)

C節Classification参照。合計33件のうち、Phase5開始を妨げる項目は
ゼロ(BLOCKS_PHASE5判定は0件)。TDnet(#1)・Company IR(#2/#3)は
Phase5 v1で当該Capabilityを使わない限りBLOCKS_SPECIFIC_CAPABILITY_
ONLYに留まる。Positioning price_derived(#10)はSHOULD_RESOLVE_BEFORE_
PHASE6として推奨するが必須ではない。残り(Macro/Global Market/News/
Consensus関連、計19件)はLONG_TERM_VALIDATIONまたはOPTIONAL。

---

## N. Proposed Phase5 v1 Scope(実装しない、提案のみ)

既存Repository資産(`ExperimentRegistry`・`Hypothesis` Schema・
`BacktestEngine`・TOPIX/Sector Benchmark比較・`RESEARCH_RULES.md`の
仮説事前登録原則)を踏まえ、次Roundで着手すべき最小Scopeを提案する:

1. **PIT-safe Dataset Contract**の明文化: Phase5 v1が使ってよい
   Datasetを本Documentの I節に固定し、`BacktestEngine`/`signal_fn`が
   これ以外のCapabilityへアクセスしないことをどう保証するか(Import
   制約のStructural Test等)を次Roundで設計する。
2. **1つの単純な仮説**をPrice + PIT Universeのみ(既存Allowed Data)で
   事前登録・Backtest・TOPIX Benchmark比較まで一気通貫させる(Feature
   Engineは作らない、既存`signal_fn`パターンをそのまま使う)。
3. **Train/Validation/Locked Testの分割**を`ExperimentRegistry`上で
   どう表現するか(既存Schemaで足りるか、追加Fieldが要るか)の設計
   確認。
4. Fundamentals(READY_WITH_RESTRICTIONS(WIRING_UNDESIGNED))を実際に
   Signalへ使いたい場合の**新規配線設計**(`BacktestEngine.run()`の
   Signature拡張要否)は、次Roundの独立したDesign Decisionとして扱う
   (v1.0必須ではない)。この設計に着手する際は、E節の主根拠(Phase5
   v1では未接続のためTie-break Blockerではない)がその時点でも成立
   するかを実Coverage規模に基づき再評価すること。

Phase5 v1で使わないCapability(EDINET/TDnet/Company IR/Positioning
需給4候補/Macro/Global Market/News/Consensus)は「Phase4失敗」とは
扱わない。将来Validation完了後にFeature Setへ追加できる設計を維持
している(§45)。
