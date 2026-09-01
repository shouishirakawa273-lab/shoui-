# Validation Backlog

「Code Complete」(実装済み)と「Real-world Validated」(実際のSourceに接続し
確認済み)は別軸である(Phase4C要件§24/§25)。このDocumentは、実装済みだが
まだReal-world Validationが完了していない項目を一覧化する。**詳細は各項目の
Authoritative Docへのリンクのみを持ち、内容を重複して書き直さない**(重複
管理を避けるため)。

新しいBacklog項目が発生した場合は、この表へ追加するのみで良い(既存項目の
詳細説明を移動・複製しない)。

## 現在のBacklog

| # | 項目 | 現在Status | 阻害要因 | Authoritative Doc |
|---|---|---|---|---|
| 1 | TDnet Add-on Local Validation | `CODE_COMPLETE_AWAITING_ADDON_LOCAL_VALIDATION` | Userのローカル環境でのAdd-on契約確認・実接続確認が必要 | `TDNET_LOCAL_VALIDATION_GUIDE.md`、DECISIONS.md D0048 |
| 2 | Company IR Live Validation #1 | `CODE_COMPLETE_AWAITING_LOCAL_LIVE_VALIDATION` | このSession自身のNetwork Egressが組織Policyにより一貫してBlocked(`EGRESS_BLOCKED`、2026-08-18確認)。Compliance確認込みでUserのローカル環境が必要 | `COMPANY_IR_LOCAL_VALIDATION_GUIDE.md`、DECISIONS.md D0053追記 |
| 3 | Company IR Live Validation #2(if needed) | 未着手 | #1と同じ | 同上 |
| 4 | EDINET Forward Snapshot Observation | 未着手(PoC設計のみ) | 継続的な観測実行そのものが未実施 | `EDINET_LOCAL_VALIDATION_GUIDE.md` §J |
| 5 | J-Quants `weekly_margin_interest`(信用取引週末残高) | `NOT_IMPLEMENTED`(Adapter未着手) | Endpoint仕様が全てSEARCH-SNIPPET-DERIVED(UNVERIFIED)。Standard Plan以上が必要という情報あり(未検証)、Publication Lag不明 | `POSITIONING_ARCHITECTURE.md`、`lib/positioning/catalog.py`、DECISIONS.md D0054 |
| 6 | J-Quants `short-ratio`(業種別空売り比率) | `NOT_IMPLEMENTED`(Adapter未着手) | 同上 | 同上 |
| 7 | J-Quants `short-sale-report`(個別銘柄空売り残高報告) | `NOT_IMPLEMENTED`(Adapter未着手) | Endpoint Path自体が未解決の矛盾(2検索結果が不一致) | 同上 |
| 8 | J-Quants `trades_spec`(投資部門別売買状況) | `NOT_IMPLEMENTED`(Adapter未着手) | 唯一Light Plan利用可能の可能性(単一の未検証情報源)、認証済みDashboard確認またはLocal接続確認が最優先候補 | 同上 |
| 9 | JPX直接公開の需給統計(信用取引残高・空売り集計・投資部門別売買状況) | 未着手(候補として記録のみ) | URL Pattern・Format(PDF/Excel)がScript化に適しているか未確認、Index Page Scrapeが必要な可能性 | `POSITIONING_ARCHITECTURE.md`、DECISIONS.md D0054 |
| 10 | Positioning Price-derived Metric(price_derived_liquidity) Local Real Data Validation | `CONNECTED`(Code)/`FIXTURE_VALIDATED`(Validation) | 合成Bar Dataでの検証のみ実施、実J-Quants Priceに対するEnd-to-End確認は未実施(上流のRawOHLCVBar自体は別Phaseで既にReal Data確認済み) | `POSITIONING_ARCHITECTURE.md`、DECISIONS.md D0054 |
| 11 | e-Stat CPI(全国CPI総合・コアCPI・コアコアCPI) | `NOT_IMPLEMENTED`(Adapter未着手) | 全情報がSEARCH-SNIPPET-DERIVED(UNVERIFIED)。5候補中最も裏付けが強いが、Wire Schema・認証Parameter・Rate Limit・Timestamp Field未確認。Local Spec Verification最優先候補 | `MACRO_ARCHITECTURE.md`、`lib/macro/catalog.py`、DECISIONS.md D0055 |
| 12 | 日本銀行 政策金利(時系列統計データ検索サイトAPI) | `NOT_IMPLEMENTED`(Adapter未着手) | 5候補中最も根拠が弱い(2026-02-18付通知見出し+SNS投稿要約のみ)。API新設主張自体の真偽確認が先決 | 同上 |
| 13 | 内閣府/ESRI GDP速報(QE) | `NOT_IMPLEMENTED`(Adapter未着手) | 1次速報/2次速報/確報という公式Revision Stage名称は複数Snippetで一致(未読)。専用API有無不明 | 同上 |
| 14 | 総務省統計局 労働力調査(完全失業率) | `NOT_IMPLEMENTED`(Adapter未着手) | e-Stat CPIと同一Endpointで取得可能か未確認。情報が他候補より薄い | 同上 |
| 15 | 厚生労働省 毎月勤労統計調査(賃金) | `NOT_IMPLEMENTED`(Adapter未着手) | PDF中心の公開形式が示唆。2024年1月Benchmark更新による指数断層の記述は具体的だが未読 | 同上 |
| 16 | FRED/ALFREDのVintage Query機構(`realtime_start`/`realtime_end`) | 未着手(検証最優先) | 複数第三者Wrapper経由のSnippetのみが根拠、FRED自身の一次文書は未読。実際に文書通り機能するか未確認——これまでのLab Sourceの中で最も具体的な前向きPIT保証候補のため優先度が高い | `GLOBAL_MARKET_ARCHITECTURE.md`、DECISIONS.md D0056 |
| 17 | FRED `SP500`(S&P 500 Price Index) | `NOT_IMPLEMENTED`(Adapter未着手) | 全情報がSEARCH-SNIPPET-DERIVED(UNVERIFIED)。FRED/S&P DJI間の2014年Licensing Agreementによる過去10年Rolling Window制約が複数Snippetで収斂(未読)。Total Return版の存在有無もUNCONFIRMED | `GLOBAL_MARKET_ARCHITECTURE.md`、`lib/global_market/catalog.py`、DECISIONS.md D0056 |
| 18 | FRED `DEXJPUS`/`DEXUSEU`(USD/JPY・EUR/USD) | `NOT_IMPLEMENTED`(Adapter未着手) | 「NY正午Buying Rate」という歴史的記述と2019年H.10算出方法変更の関係が未確認。EUR/JPYはFRED上に直接系列が無くCross Rate計算が必要 | 同上 |
| 19 | FRED `DGS10`(US 10年国債利回り) | `NOT_IMPLEMENTED`(Adapter未着手) | 米財務省がおよそ15:30 ET時点の気配値から算出という記述が見つかったが未読。`home.treasury.gov`自身の値とのCross-Check未実施 | 同上 |
| 20 | FRED `VIXCLS`(CBOE VIX) | `NOT_IMPLEMENTED`(Adapter未着手) | CBOEのRTH算出Window(9:30am-4:15pm ET)・原典CBOE/配信FREDの分離、いずれもCBOE自身の一次文書は未読 | 同上 |
| 21 | Evidence経路(`retrieved_at`基準)とas_of経路(`resolve_available_at`基準、Session Close等のMarket Observation Completion Time推定)、どちらをBacktest System Bの正とするかの設計判断 | `ARCHITECTURE_GAP`と分類確定(D0057)。Semantic Contract Testで固定済み(`test_pit_gate_cross_capability_semantics.py`)、Code変更は未実施(意図的、原則Backlog維持の方針) | 両経路とも本番Pipelineに未接続のためCURRENT_DEFECTではない(D0057 Repository Reality Check)。Fundamentals/Disclosures/Positioning(CONNECTED)/Macro/Global Marketいずれにも共通するCommon Core既存Pattern。将来Backtest System B(Evidence経由でPIT判定する実際のPipeline)を配線する設計Roundで、2経路の統合方針(EvidenceRecordへのAvailabilityBasis相当Field追加要否を含む)をユーザーの判断で決定する必要がある | DECISIONS.md D0057、D0056(発端のpit-auditor Finding)、`lib/evidence/model.py`、`lib/evidence/retrieval.py`、`13_tests/test_pit_gate_cross_capability_semantics.py` |
| 22 | PR TIMES 全文保存・再配布Terms確認 | `NOT_IMPLEMENTED`(Adapter未着手) | 企業規約第6条相当(未読)が全文保存・再配布を制限している可能性。`prtimes.jp/main/html/kiyaku`のLocal Live確認が最優先候補 | `JAPAN_NEWS_ARCHITECTURE.md`、`lib/news/catalog.py`、DECISIONS.md D0058 |
| 23 | PR TIMES 公開側Timestamp Field粒度確認 | `NOT_IMPLEMENTED`(Adapter未着手) | 著者用UI側の10分刻みScheduling機能からの示唆のみで、公開Article/RSSが実際に露出するTimestamp Field仕様は未確認 | 同上 |
| 24 | JPX News Releases / FSA報道発表資料 / METI News Release RSS仕様確認 | `NOT_IMPLEMENTED`(Adapter未着手) | いずれもRSS Feedの存在はSnippetで示唆されたが未読。pubDateの粒度・Timezone表現・Correction挙動未確認 | 同上 |
| 25 | BOJ「What's New」RSSとMacro `boj_policy_rate`のCatalog統合方針 | 未着手(重複可能性のみ記録) | News/Macro双方のCatalogに同一Source候補が跨って現れうる——このRoundでは新規News Catalog登録を見送った | `JAPAN_NEWS_ARCHITECTURE.md`、DECISIONS.md D0058 |
| 26 | `lib/news/`(Metadata Ingest層)→`lib.evidence.news.NewsEvent`(Event層、Phase3D)への変換Layer設計 | 未着手(境界維持のみ、Structural Testで固定済み) | skeptic-reviewer Finding(Phase4E-2): 2つの並行するNews表現を恒久的に維持する設計判断自体は妥当だが、統合Layerの設計はまだ着手していない。`test_news_modules_never_import_evidence_news_event_scaffold`で現状の分離は固定済み | `JAPAN_NEWS_ARCHITECTURE.md`、DECISIONS.md D0058、`lib/evidence/news.py`、`13_tests/test_news_pit.py` |
| 27 | GDELT DOC 2.0 Timezone Documentation(UTC既定/DST関連)・License("Unrestricted use...without fee"主張)の一次文書確認 | `NOT_IMPLEMENTED`(Adapter未着手) | 全情報がSEARCH-SNIPPET-DERIVED(UNVERIFIED)。News全文ではなくEvent-level Metadataの配信である点は確認済みだが、Timezone/License本文はこのSessionから未読(`EGRESS_BLOCKED`) | `GLOBAL_NEWS_ARCHITECTURE.md`、`lib/news/catalog.py`、DECISIONS.md D0059 |
| 28 | SEC press release/litigation release RSS: Timezone表記("EST"年間固定Label疑義)・EDGAR Acceptance Datetime対Filing Dateの区別 | `NOT_IMPLEMENTED`(Adapter未着手) | 公式RSS Feedの存在はSnippetで示唆されたが未読。D0056で確認済みの`ZoneInfo("EST")`固定UTC-5問題と同型の懸念がSEC自身のDocumentationにも存在する可能性 | `GLOBAL_NEWS_ARCHITECTURE.md`、`lib/news/catalog.py`、DECISIONS.md D0059 |
| 29 | Government RSS全般のPIT Risk実例(US Treasury 2021年RSS Replay Bug)の一般化・監視方針 | 未着手(参考事例として記録のみ) | US Treasury自体は候補として不採用だが、将来Government RSS Sourceを採用する際に同種のReplay/再配信Riskを検知する仕組みが必要になりうる | `GLOBAL_NEWS_ARCHITECTURE.md`、DECISIONS.md D0059 |
| 30 | QUICK Consensus 個人向けTier確認 | `NOT_IMPLEMENTED`(Adapter未着手) | 個人/自営業者でも契約可能なTierを持つか未確認(Qr1 Personalに Consensus Dataが含まれるかも未確認)。data-source-researcher推奨順位1位のため最優先検証対象 | `CONSENSUS_ARCHITECTURE.md`、`lib/consensus/catalog.py`、DECISIONS.md D0060 |
| 31 | FactSet Estimates PIT Consensus License/Timestamp仕様確認 | 未着手(Catalog未登録、Architecture Doc参照用) | ENTERPRISE専用と判断され`lib/consensus/catalog.py`への登録を見送った(skeptic-reviewer Finding、Phase4E-4: 他ENTERPRISE専用候補への除外基準と統一)。Timestamp Semantics(Local Midnight基準のTimezone)・実際のPricing・個人向けTierの有無、いずれも未確認のまま`CONSENSUS_ARCHITECTURE.md`にのみ記録 | `CONSENSUS_ARCHITECTURE.md`、DECISIONS.md D0060 |
| 32 | IFIS Japan Bulk Data Service仕様・個人向けTier確認 | `NOT_IMPLEMENTED`(Adapter未着手) | Wire Schema・API有無(Bulk/File配信のみの可能性)・License/Redistribution Terms・個人向けTierの有無、いずれも未確認。PIT/Vintage主張自体が他候補より弱い | 同上 |
| 33 | Consensus `entity_id`(Canonical Entity Registry)へのMapping手法設計 | 未着手 | Provider固有Symbol/Ticker/企業IDをEntity Registryへ安全にMapping する手法が未設計(実Adapter実装時の課題) | `CONSENSUS_ARCHITECTURE.md`、DECISIONS.md D0060 |

## 運用ルール

- 新規Sourceを追加する際、Real-world Validationが完了しない場合は必ずこの
  表へ追加する(黙って`NOT_IMPLEMENTED`/`SKELETON`のまま放置しない)。
- 項目がValidated完了した場合、その項目の行を削除し、対応する
  `ImplementationStatus`/Validation Statusを更新した理由をDECISIONS.mdへ
  記録する(このFile自体には完了履歴を残さない、単なる進行中Backlogとして
  維持する)。
- どの項目も、未検証のままStatusを`LIVE_VALIDATED`/`CONNECTED`(実データ
  確認済みの意味で)へ変更しない。
