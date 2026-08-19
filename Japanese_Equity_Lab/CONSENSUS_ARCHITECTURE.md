# Consensus / Expectations Inputs Data Architecture(Phase4E-4)

このDocumentは`lib/consensus/`の設計判断をまとめる。実装詳細は各Module
のdocstringを参照し、ここでは全体像とSourceを跨いだ設計判断のみを記す。

## 目的とScope

将来のExpectations Engineに必要となる「その時点でProviderが観測して
いたAnalyst Consensus/Estimate」を、PIT-safe/vintage-aware/source-
aware/provenance-preserving/reproducibleな形でこのLabへ取り込むための
Data Foundation。**Beat/Miss・Surprise・Priced-in・Earnings Reaction
予測・BUY/SELL・Expectations Engine本体・Backtest統合はこのPhaseの
Scope外**であり、`lib/consensus/`のどのModuleも生成しない(Phase4E-4
要件§1)。

「Consensus Source -> Raw/Source Observation -> Canonical Consensus
Record -> Forecast Vintage History -> Pure as_of View -> 将来Actual/
Guidanceと安全に比較可能なIdentity」までがこのPhaseの範囲。

## Consensus != Truth(最重要Concept)

Consensusは以下のいずれでもない: 市場参加者全員の期待(Market
Price-Implied Expectation)、客観的なTruth・将来の実際の着地値、特定
Providerを離れた普遍的な「Analystの見解」。Consensusは常に「特定
Provider(`source_id`)が、特定Analyst Universeを、特定Method
(`statistic_type`)で集計した、特定時点(Vintage)のForecast
Observation」として扱う。Provider AのMeanとProvider BのMeanは、
Analyst Universeが異なれば同じ「Consensus」を意味しない(Phase4E-4
要件§6/§29)。

## 6つの別概念(Phase4E-4要件§5)

A. Company Guidance(既存`lib.fundamentals`側)/ B. Analyst Consensus
(このModuleの主対象)/ C. Individual Analyst Estimate(v1では扱わない、
将来拡張余地のみ残す)/ D. Market Price-Implied Expectation(将来
Expectations Engine)/ E. Actual Result(既存`lib.fundamentals`側)/
F. Investment Conclusion(このModuleはObservationまで)。

## 最重要の設計判断: 既存Primitiveの再利用(専用Consensus Versioning機構を作らない)

Repository Reality Checkの結果、以下を確認しそのまま再利用した(Phase4E-4
要件§7/§33):

- **`lib.evidence.model.RevisionHistory`/`SourceVersion`/
  `AvailabilityBasis`**: Vintage管理(Fundamentals/Positioning/Macro/
  Global Marketと同一Primitive)。`lib.consensus.normalize.
  build_revision_histories()`は`lib.macro.normalize`とほぼ同型の
  小さな関数として書いた(Cross-Capability抽象化は導入しない、既存の
  設計判断を踏襲)。
- **`lib.fundamentals.model.PeriodType`**(1Q/2Q/3Q/4Q/5Q/FY/OTHER)・
  **`ConsolidationScope`**(CONSOLIDATED/NON_CONSOLIDATED): そのまま
  再利用する(独自の重複Enumを作らない)。将来Consensus vs Actual
  FundamentalMetric vs Company Guidanceの比較を可能にするため
  (Phase4E-4要件§21)。`accounting_scope`はOptional(`None` = 未確認)
  としており、Fundamentals自身のEnumにUNKNOWN Memberを追加する変更は
  一切行っていない(Fundamentalsの既存Behaviorへの影響ゼロ)。
- **`lib.evidence.model.ValueAvailability`**: Missing Estimateの表現に
  再利用(Missing != 0)。
- **`DataCapability.EXPECTATIONS`**: Phase3D由来の既存Enum Memberが
  そのまま使えたため、新規Capability種別の追加は不要だった。

新設したのは`StatisticType`(MEAN/MEDIAN/HIGH/LOW/STANDARD_DEVIATION/
COUNT/OTHER/UNKNOWN)と`ForecastHorizon`(CURRENT_QUARTER/NEXT_QUARTER/
CURRENT_FY/NEXT_FY/NEXT_NEXT_FY/EXPLICIT_PERIOD/UNKNOWN)のみ——いずれも
既存Capabilityに相当する概念が存在しない、Consensus固有の区別軸である。

## Vintage(最大のPIT Risk)

FY2027 EPS Consensusが2026-06-01に100、2026-07-01に105、2026-08-01に
103と観測された場合、これらは**別Vintage**である。「現在取得した
FY2027 Consensus」を「FY2027当時に利用可能だったConsensus Vintage」
として扱うことは絶対禁止(Historical Consensus Leakage、Phase4E-4要件
§12、CONS-001/CONS-002でPin)。

## Forecast Evolution != Correction(Phase4E-4要件§32)

100→105→103という推移は通常Analystの見解が更新されただけであり、訂正
(Correction/Revision Error Fix)ではない。`build_revision_histories()`
は`is_correction`を常に`False`のまま構築する(Sourceが明示的に
Correctionと述べない限り`True`へ変更しない、EVIDENCE-003原則、
`lib.macro.normalize`/`lib.positioning.normalize`と同じ扱い、CONS-006/
CONS-023でPin)。

## consensus_as_of の意味は Source-specific(Phase4E-4要件§13〜14)

Providerが返す"As of YYYY-MM-DD"のようなFieldは、Snapshot計算時刻・
Analyst Cutoff時刻・Website表示日・API生成日時のいずれを意味するかが
Source固有であり、統一的な意味を持たない。`ConsensusRecord.provider_
stated_as_of`(生のProvider "as of"値)としてそのまま保持するのみとし、
これを`provider_available_at`へ自動Mappingしない。**命名の工夫**:
Record Fieldを`provider_stated_as_of`、PIT View Functionを`lib.
consensus.view.consensus_as_of()`と意図的に区別する命名にした(混同
防止)。`provider_stated_as_of`が`lib/consensus/normalize.py`/`view.py`
/`evidence.py`のいずれからも実際にAttribute Accessされないことを
AST走査で構造的に確認した(CONS-003)。

## Fiscal Period Identity(最重要、日本株特有の厳密さ)

Current FY/Next FY/Next-next FYとCalendar Yearを同一視しない(例:
2027年3月期 != Calendar 2027)。`period_type`(Fundamentals由来、四半期/
通期区別)・`target_period_start`/`target_period_end`(Explicit
Period)・`provider_target_period_id`(Provider Native識別子)を優先
Identityとし、`forecast_horizon`(Relative Label)は補助情報に留める
(Observation時点により意味が変わるため、CONS-011/CONS-025でPin)。
`fiscal_year_end`(発行体固有の決算期末日)を独立Fieldとして保持し、
Calendar Yearとの混同を防ぐ(CONS-026)。

## Statistic Type / Analyst Count(Phase4E-4要件§23〜24)

Consensus値は単一Fieldへ潰さない。`statistic_type`にDefault値を持たせず
呼び出し側が必ず明示する(Mean != Medianを型で強制、CONS-008/CONS-021)。
`analyst_count`はProviderが明示した場合のみ保持し(`None` = 未提供、
0ではない、CONS-009/CONS-024)、Analyst Countが多い方が信頼できるという
解釈はこのModuleでは行わない。

## Series Identity(呼び出し側の責務、既存Common Coreと同じ設計)

`series_id`は**`source_id`(Provider)**・entity・metric_type・target
period・statistic_type・accounting_scope・currencyのうち区別すべき軸を
全て一意に含める責務を呼び出し側/将来Normalizerが負う(Fundamentals/
Macro/Global Marketと同じ責務分担)。`source_id`を明示的に一覧の先頭へ
含めているのは、このRound最大の原則「Provider AのMean != Provider Bの
Mean」(Consensus != Truth)を`series_id`構築の場面でも徹底するためで
あり、`lib.macro.model.MacroRecord`のDocstringがSourceを責務一覧の
筆頭に挙げているのと同じ位置付けである(skeptic-reviewer Finding、
Phase4E-4: 当初の一覧からSourceが抜けており、Macroの前例より弱い記述に
なっていたため訂正した)。Current FY MeanとNext FY Meanを同一Seriesへ
潰さない(CONS-022)。Mean SeriesとMedian Seriesを同一Seriesへ潰さない
(CONS-021)。**既知のCommon-Core Limitation(RevisionHistory
Tie-break)**: 同一`available_at`を持つ複数`SourceVersion`が存在する
場合の順序はInput Order依存であり(Positioning/Macro/Global Marketと
同じKnown Limitation、Phase4E-4要件§42)、このRoundでは実Sourceで
このケースが具体的に発生しない限りCommon Coreを変更しない。

## Company Guidance / Actual Boundary(Phase4E-4要件§28〜29)

`ConsensusRecord`にはGuidance/Actual専用に見えるField名(`guidance_
value`/`actual_value`/`actual_or_forecast`等)を一切持たない
(CONS-012/CONS-013で確認)。ただしこれは「その名前のFieldが無い」こと
の確認に限られ、`value: Decimal | None`自体はFundamentalsの`value`
Fieldと同型のGeneric Numeric Fieldであり、Guidance/Actual/Consensus
分離は最終的にはこのModuleをどう呼び出すか(呼び出し側/将来Adapterの
責務)というModule境界のConvention Levelで担保される(skeptic-reviewer
Finding、Phase4E-4: CONS-029/030が既に採用している「Mechanical
Pinning、意味論的証明ではない」という自己限定的な説明を、この確認にも
一貫して適用した)。Company GuidanceもActual Resultも既存`lib.
fundamentals`側の責務であり、このModuleへ複製しない。将来Join可能な
Identity(entity/metric/target period/accounting scope/unit/currency)
だけを揃える。

## No Surprise / No Priced-in / No BUY-SELL Inference(Phase4E-4要件§30〜31)

`lib/consensus/`のいずれのModuleも、Beat/Miss/Surprise/Priced-in/Buy/
Sell/Bullish/Bearishという語を(このModule自身のDocstringにおける「〜を
生成しない」という説明を除き)一切含まない——CONS-014/CONS-015/CONS-028
が、Module DocstringからForbidden Term Scanが誤検出しないようDocstring
除外Textで直接確認する(単純な全文字列探索は自己言及するDocstringに
よって誤検出することが分かったため、AST Docstring除外という一段厳密な
手法を採用した、後述「Reviewer教訓の反映」参照)。

## Entity Mapping(Ambiguous Mapping Fails Closed)

`entity_id`(正規化されたEntity識別子)はEntityRegistryが確認できた場合
のみ設定し、Ambiguousな場合は`None`のまま(CONS-017)。`source_entity_
identifier`(Providerの生Symbol/Ticker/企業ID)はMapping成否によらず
常に保持する(Provenance維持)。

## D0057との境界(維持、解決しない)

`consensus_record_to_evidence()`はEvidenceを生成できるが、このRoundでも
一切Backtest/Decision Engineへ接続しない(Phase4E-4要件§43)。D0057
(ARCHITECTURE_GAP、Validation Backlog #21)は未解決のまま維持し、
CONS-020(`test_cons020_evidence_module_never_imports_retrieval_or_
filter_usable_at`)でFully Qualified Path AST走査により`lib.evidence.
retrieval`をどのModuleもImportしないことを確認した。

## Source Candidate Landscape(data-source-researcher Agent、2026-08-19)

LSEG/Refinitiv I/B/E/S・Bloomberg BEst・FactSet Estimates・S&P Capital
IQ・Visible Alpha・QUICK・IFIS Japan・Nikkei NEEDS/Compass・Alpha
Vantageを調査した。ほぼ全てが`EGRESS_BLOCKED`だったが、data-source-
researcher Agentが2つの非公式Client Code(`RomelTorres/alpha_vantage`
のPythonライブラリ、`alphavantage/alpha_vantage_mcp`のREADME、いずれも
GitHub上で実際に読めた、`VERIFIED_SECONDARY`)を確認し、**Alpha
Vantageの`EARNINGS_ESTIMATES`Endpointの存在自体が確認できなかった**
(このLabの`EARNINGS`関数はSurprise計算用の単一Estimateを含むのみで、
専用のConsensus Statistics Endpointではない)。

**分類結果**:

- **Wire Enterprise勢(LSEG/Refinitiv I/B/E/S・Bloomberg BEst・
  **FactSet Estimates PIT Consensus**・S&P Capital IQ・Visible
  Alpha)**: いずれもTerminal/Platform契約前提のEnterprise専用と判断
  され、個人がローカル実行するという本Labの前提(ルートCLAUDE.md)に
  そぐわないためCatalog未登録(skeptic-reviewer Finding、Phase4E-4:
  当初FactSetのみ「Benchmark参照目的」という別基準で例外的にCatalog
  登録していたが、これは同じ理由[ENTERPRISE専用]で他4候補を除外して
  いた基準と直接矛盾しており、Catalog自体の目的[実装候補の検索可能な
  一覧、恒久的Documentation参照用ではない]とも合わないと判断し、他の
  ENTERPRISE専用候補と同じ扱いへ統一した)。以下、参考情報として記録
  する:
  - LSEG/Bloombergは Point-in-Time Consensus主張自体はあったが
    (「Historic Estimates Snapshot」「Point-in-Time Historical」)、
    詳細なTimestamp Semanticsは確認できなかった。
  - S&P Capital IQは"since August 2016"というChange-Capture開始時期の
    主張があり、それ以前のVintageは再現不能な可能性がある。
  - **FactSet Estimates PIT Consensus**は調査した全候補中、Timestamp
    Semantics(「Local Midnight Snapshotで計算対象を確定、それ以降
    入力されたデータは含まない」)について最も具体的な記述が見つかった
    (SEARCH-SNIPPET-DERIVED、未読)。FactSet自身の記述でも「未確認の
    状態で消えたBroker見積・QA訂正・Default Currency変更は反映され
    ない」という明示的な除外事項があり、完全な過去再現ではないことも
    正直に記録しておく。「Local Midnight」がどのTimezone基準か
    (発行体所在地/取引所/FactSet自身のいずれか)は未確認。Japan
    Coverageは東洋経済(Toyo Keizai)由来の可能性が示唆され、FactSet
    自身のSell-side Panelとは別軸である可能性がある(未確認)。将来
    Timestamp Semantics設計時の参照値として、このArchitecture Doc上
    にのみ記録する(Catalogには登録しない)。
- **QUICK Consensus**: Japan Coverage最強の主張(2005年以降の中小型株
  含む)、Point-in-Time Consensus主張あり、個人向け製品Line(Qr1
  Personal)の存在が示唆されたが、Consensus自体がそこに含まれるかは
  未確認。data-source-researcher推奨順位1位としてCatalogへ登録した。
- **IFIS Japan**: Japan-domestic、JP-GAAP特有科目(経常利益等)を含む
  広いMetric Setだが、PIT/Vintage主張自体が見つからず(QUICK/FactSet
  より弱い)。参考候補としてCatalogへ登録した。
- **Nikkei NEEDS**: PIT主張なし、Sell-side Consensus自体の存在すら
  未確認(Derived Multipleのみの可能性)。登録見送り。
- **Nikkei Compass**: Service終了(Discontinued)を確認。除外。
- **Alpha Vantage**: `EARNINGS_ESTIMATES`Endpoint自体の存在が未確認
  (存在しない可能性が高い)。登録見送り(存在未確認のEndpointを前提に
  したCatalog登録はしない、Phase4E-4要件§9)。

Catalog登録した2候補(QUICK/IFIS)全て`implementation_status=
NOT_IMPLEMENTED`、Validation Status=`DESIGN_COMPLETE_AWAITING_SPEC_
VERIFICATION`。

## Reviewer教訓の反映(Phase4E-2/4E-3からの直接継承)

このRoundは最初から以下を反映した(前Roundのpit-auditor/skeptic-
reviewer Findingを踏まえた予防的設計):

- 「Fieldが読まれていないこと」の確認はAST Attribute Access走査
  (`ast.Attribute`のNode)を使う——単純な全文字列探索はDocstring内の
  言及(Field名自体への言及)を誤検出する(Phase4E-3 pit-auditor
  Finding、GNEWS-004のAST走査という表現の不正確さの教訓)。
- 「Moduleをimportしていないこと」の確認は`from X import Y`形も含め
  Fully Qualified Pathを組み立てて判定する(Phase4E-3 pit-auditor
  Finding、GNEWS-016の検出漏れの教訓、CONS-020で最初から反映)。
- Forbidden Term Scan(Beat/Miss/Buy/Sell等)は、Module自身のDocstring
  が「〜を生成しない」と説明するために使う語自体を誤検出しないよう、
  AST Docstring除外Textで実施する(このRound自身で最初に遭遇し、
  実装中に修正した——`lib.consensus.model`のDocstringが"beat"という語を
  含んでいたため)。
- Cross-source比較Test(CONS-029/CONS-030)は、実際に何を証明している
  か(series_idの責務分担というMechanical Pinning)を過大に説明しない
  (Phase4E-3 skeptic-reviewer Finding、GNEWS-007/008の教訓)。

## Common Coreへ含めないもの

Source固有のSemantics(QUICK/FactSet/IFISのField名Mapping・Entity
Identifier Mapping・Compliance確認手順)は将来`lib/consensus/
providers/`配下に閉じ込め、Common Core相当の`lib/consensus/model.py`/
`normalize.py`/`view.py`/`evidence.py`へは一切追加しない設計とする
(Phase4B/4C/4D/4E-1/4E-2/4E-3と同じ境界原則)。

## Validation Status(実装状況とは別軸)

Consensus候補2件(QUICK/IFIS)とも`implementation_status=NOT_IMPLEMENTED`、
Validation Status=`DESIGN_COMPLETE_AWAITING_SPEC_VERIFICATION`
(`lib/consensus/catalog.py`の`known_limitations`へ自由記述)。

## Known Limitations

- CONS-016(Historical API Response Is Not Historical Vintage)は
  Adapter自体が無く再現するExecution Pathが無いため、Code Testでは
  なくこの文書上のKnown Limitationとして記録する: 将来Adapterを実装
  する場合、現在のAPI Responseが過去のProvider Vintageと同一である
  保証は無い(EDINET D0046の「Historical List Is Mutable」・News
  NEWS-016と同じ懸念パターン)。
- `entity_id`(Canonical Entity Registry)へのMapping手法は未設計
  (実Adapter実装時の課題として残す、Japan/Global Newsの`entity_id`
  Mappingと同型のGap)。
- QUICK Consensusが個人/自営業者でも契約可能なTierを持つかが最大の
  未解決論点。IFIS Japanの無料Web Viewer("IFIS株予報")がConsensus
  Dataを含むかも未確認。
- Individual Analyst Estimate(v1では扱わない、Phase4E-4要件§26)は
  `ConsensusRecord`のField構成に含まれておらず、将来拡張が必要になった
  場合は別Round設計となる。
- D0057(Backlog #21、ARCHITECTURE_GAP)はこのRoundでも未解決のまま
  維持する。
- **CONS-020(`_module_never_imports`)のAST走査に残存するBlind Spot**
  (pit-auditor Finding、Phase4E-4、LOW): 相対Import(`from ..evidence
  import retrieval`のような形、`ast.ImportFrom.module`はDots解決前の
  末端名のみを保持するため一致しない)・`from lib import evidence`の
  ような形でPackage自体をImportした後に`evidence.retrieval`と属性
  経由でAccessするCase(同一Pytest実行内で`lib.evidence.retrieval`が
  既に他所でImport済みであれば、Python Module CacheによりAST上は
  検出されないままRuntimeでは解決してしまいうる)・`importlib.import_
  module()`等の動的Importは、いずれもこのAST走査単体では検出できない。
  現時点では`lib/consensus/`のいずれのFileもAbsolute Importのみを
  使っており(Grep確認済み)実際の違反は無いが、将来Refactorでこの
  Guardの厳密性に依存する場合はFunctional Check(実際に`sys.modules`
  を確認する等)の追加を検討する必要がある。
