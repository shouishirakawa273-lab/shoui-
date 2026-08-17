# DATA_SOURCE_ARCHITECTURE.md

Multi-Source Data Foundation(Phase3D、DECISIONS.md D0040)のアーキテクチャ文書。
「J-Quantsだけに依存しない情報基盤」を、将来Sourceが増えても研究所本体
(BacktestEngine/Universe等)を作り直さずに済む形で用意することが目的。

**このPhaseでは実データへの接続は行っていない。** 以下は共通Schema/Interfaceの説明であり、
接続状況は各Sourceの表の「Current Implementation Status」列を参照すること
(Catalogに記述があること自体は「実装済み」を意味しない)。

## 全体構成

```
Provider(実API/ファイル) -- Capability-based Provider Protocol --
  -> RawFetchResult -> RawSnapshotStore(Immutable, 既存)
  -> Normalize -> EvidenceRecord(lib.evidence.model, DataLayer=NORMALIZED)
  -> (任意) AI要約等 -> EvidenceRecord(DataLayer=DERIVED, AiDerivedProvenance付き)
  -> ResearchQuestion + plan_retrieval() -> RetrievalPlan
  -> retrieve_evidence() -> EvidencePacket(lib.evidence.packet)
  -> (将来)Agent判断 -> DecisionEvidenceLog(lib.evidence.decision_log)
```

Lineageはすべて既存`lib.registry.provenance.ProvenanceStore`(Phase1.1〜)で
`trace_to_origin()`により終点から起点まで遡れる(新しいProvenance機構は作らない)。

## Data Catalog(`lib/sources/catalog.py`)

- `DataCapability`: MARKET_PRICE / FUNDAMENTAL / DISCLOSURE / POSITIONING /
  EXPECTATIONS / MACRO / GLOBAL_MARKET / NEWS / IDEA
- `SourceAuthorityClass`: PRIMARY_OFFICIAL / COMPANY_PRIMARY / VERIFIED_SECONDARY /
  SECONDARY / SOCIAL / USER_SUPPLIED(内容の正しさではなく出所の位置づけ)
- `SourceMetadata`: source_id / source_type / provider_name /
  source_authority_class / primary_or_secondary / retrieved_at / published_at /
  available_at / effective_at / source_url / license_or_usage_note /
  content_hash / provenance_id
- `DatasetDescriptor`: dataset_id / source_id / capability / authority_class /
  `implementation_status`(NOT_IMPLEMENTED/FIXTURE_ONLY/SKELETON/CONNECTED) /
  coverage_start・coverage_end / update_frequency / pit_available /
  applicable_codes・countries・sectors / cost_or_plan_dependency /
  known_limitations
- `SourceCatalog.find(capability=, code=, country=, sector=, implementation_status=)`

将来Agentが「このResearch Questionに必要なDataは何か」をここから選べる設計。

## Capability-based Provider Protocol(`lib/sources/providers.py`)

1つの巨大Interfaceへ詰め込まず、データの形が本質的に異なるSource種別ごとに
小さなProtocolへ分割する(Interface Explosionへの対策として、形が似ている
Source同士は1つのProtocolへまとめる)。

| Protocol | 対象Source(例) | 備考 |
| --- | --- | --- |
| `MarketDataProvider` | J-Quants | 既存`DataSourceAdapter`と同形状(後方互換) |
| `FundamentalDataProvider` | J-Quants Financials/Dividend(将来) | |
| `DisclosureProvider` | EDINET / TDnet / Company IR | 「開示文書1件」という共通の形でまとめる |
| `MacroDataProvider` | BOJ / e-Stat / 財務省 / 経産省 / 貿易統計 | Revision管理は`RevisionHistory`側で行う |
| `GlobalMarketDataProvider` | FX / 金利 / 海外指数 / Commodity | |
| `NewsProvider` | Japan News / Global News | メタデータ取得のみ、関連度評価は別レイヤ |
| `ConsensusProvider` | Analyst Consensus等 | 実Provider未選定、Interfaceのみ |
| `IdeaSourceProvider` | X / YouTube / 論文 / 手動 | FACTではなくIDEA/OPINION Source |

各Providerは`ProviderCapabilities`(provider_name/capabilities/authority_class)を
自己申告する。既存`lib.data_sources.jquants.JQuantsAdapter`は一切変更していないが、
`MarketDataProvider`と同じメソッド名・シグネチャのため`isinstance(adapter,
MarketDataProvider)`が構造的に成立する(`13_tests/test_source_providers.py`)。

## Canonical Entity Registry(`lib/sources/entity_registry.py`)

J-Quants Code・EDINET Code・法人番号・社名/旧社名を直接joinせず、`issuer_id`を
介して対応付ける。`EntityIdentifierMapping`(issuer_id/security_id/
provider_identifiers/aliases/canonical_name/valid_from/valid_until/
mapping_provenance/mapping_confidence)。`EntityRegistry.resolve(provider_name,
provider_identifier, as_of)`はPIT対応(社名変更・コード変更で有効期間が異なる
複数Mappingを登録でき、有効期間外は`None`、重複一致は`ValueError`)。

## Source Coverage Matrix

各Sourceの役割・権威・PIT特性・実装状況・コスト依存・既知の制約。値が不明な項目は
「取得不可」と明示し、推測で埋めない。

### 1. J-Quants

| 項目 | 内容 |
| --- | --- |
| Role | 日次株価(OHLCV)・TOPIX/指数・銘柄マスタ・財務諸表サマリ(決算短信)・(将来)配当・Corporate Action・需給データ |
| Authority | PRIMARY_OFFICIAL |
| PIT semantics | `/v2/equities/master`の`date`パラメータは実データ確認済みでPIT対応(D0039、6502実データ)。株価はAdjFactorによるPIT-safe As-of Adjustment実装済み(D0034/D0035)。財務諸表(`/v2/fins/summary`)はmarket_public_at(DiscDate+DiscTime、tz-aware)を実装、provider_available_atは実観測ログが無いため常にUNKNOWN(D0043) |
| Current Implementation Status | 株価/Master/Calendar/TOPIX: CONNECTED(実データE2E検証済み、Phase3B)。Financial Summary(`/v2/fins/summary`): CONNECTED(Phase4A COMPLETE、D0043。2026-08-16に4銘柄(7203/6758/8056/3626)でLocal Real Data Validation完了)。Dividend/需給: NOT_IMPLEMENTED |
| Cost/Plan dependency | Light Plan(ユーザー申告)、60req/分(D0039確認済み)。`/v2/fins/summary`はEndpoint固有60req/分と仮定し`effective_limit=min(60,60)=60`(D0043、未検証) |
| Known limitations | 商品区分(ProdCat)・市場区分(Mkt)の値の意味は未検証。全市場規模のBulk取得方式は未接続(D0039)。`/v2/fins/summary`のField名・DocType一覧の一部はLocal Real Data Validationで確認済み(D0043追記)だがPagination仕様・Rate Limit実挙動・JGAAP/USGAAPのDocType値は未検証。`code`指定クエリは`from`/`to`で絞り込まれず対象Codeの全履歴を返すことを確認済み(D0043追記) |

### 2. EDINET

| 項目 | 内容 |
| --- | --- |
| Role | 有価証券報告書・四半期/半期関連開示・大量保有報告書・XBRL |
| Authority | PRIMARY_OFFICIAL(FSA公式。ただし内容の真偽までは保証しない、`SourceAuthorityClass`のDocstring参照) |
| Origin vs Delivery | 直接EDINET APIへ接続する設計のため`originating_source=delivery_provider="EDINET"`(D0042の分離を踏襲。別Provider経由での配信は現時点で未想定) |
| PIT semantics | `submitDateTime`/`opeDateTime`の正確な意味(提出時刻か公衆縦覧可能時刻か)・タイムゾーンいずれも未確認(Phase4B-2、`EDINET_SOURCE_ONBOARDING.md` §4)。`market_public_at`/`provider_available_at`のいずれへも、確認が取れるまで`AvailabilityBasis.UNKNOWN`以外の根拠でマッピングしない |
| Current Implementation Status | `NOT_IMPLEMENTED`。`lib.disclosures.providers.edinet.EdinetAdapter`がDocuments List/Document DownloadのRaw HTTP Fetchのみ実装済み(Phase4B-2)だが、`DisclosureDocument`への正規化(Field Mapping)は一切行っていない — Field名自体が未確認のため |
| Cost/Plan dependency | UNKNOWN(無料と思われるが一次資料で未確認) |
| Known limitations | **本セッションから`api.edinet-fsa.go.jp`・FSA公式資料のいずれへも接続不可**(egressポリシーによりブロック、`curl`で`CONNECT tunnel failed, 403`を独立に確認済み)。`data-source-researcher`によるOnboarding調査も二次情報(WebSearchスニペット)のみに基づく未確認結果に留まり、Document Downloadの`type`パラメータについては情報源間で**相互に矛盾する**値が見つかった。認証方式(クエリパラメータ vs ヘッダ)・`secCode`形式とJ-Quants(D0039)との互換性・`parentDocID`の訂正関係・`withdrawalStatus`の列挙値・過去データ範囲(縦覧期間限定の可能性)、いずれも未確認。詳細は`EDINET_SOURCE_ONBOARDING.md`、ローカル検証手順は`EDINET_LOCAL_VALIDATION_GUIDE.md`参照 |
| Historical coverage vs API coverage | 縦覧期間+延長期間内の書類のみを対象とする可能性が示唆されている(未確認)。もし正しければ「現在APIから取得できる範囲」が「過去の全提出履歴」と一致しないことになる — 確認が取れるまでこの区別を前提に扱う |
| Entity mapping | `lib.sources.entity_registry.EntityIdentifierMapping.provider_identifiers`は元々`{"edinet": "E02166"}`のような形を想定した汎用設計になっており、EDINETコード/secCode/JCNをこのnamespace経由で登録する設計自体はコード変更不要。ただし実際の値の形式確認(特にsecCodeがJ-Quantsの5桁ゼロパディング規約と一致するか)ができるまで、実際のMapping登録は行わない |

### 3. TDnet

| 項目 | 内容 |
| --- | --- |
| Role | 決算短信・業績予想修正・配当・自社株買い・M&A・その他適時開示 |
| Authority | PRIMARY_OFFICIAL(取引所経由の開示) |
| PIT semantics | 開示時刻(15:00以降は翌営業日扱い等の制度)がavailable_atの`AvailabilityBasis.INFERRED`源になりうる(未検証) |
| Current Implementation Status | NOT_IMPLEMENTED |
| Cost/Plan dependency | 無料部分と有料Add-onがある(未確認)。有料契約はPhase3Dでは行わない |
| Known limitations | 公式API仕様未確認 |

### 4. Company IR

| 項目 | 内容 |
| --- | --- |
| Role | 決算説明資料・中期経営計画・補足資料・経営者コメント |
| Authority | COMPANY_PRIMARY(発行体自身の開示だが、将来見通し等はCLAIMとして扱う。FACTとは限らない) |
| PIT semantics | Webサイト掲載日時が不明瞭なことが多い(`AvailabilityBasis.UNKNOWN`になりやすい) |
| Current Implementation Status | NOT_IMPLEMENTED |
| Cost/Plan dependency | 無料(企業サイト) |
| Known limitations | PDF差し替え・削除への対応(Revision管理)は`RevisionHistory`で表現可能だが未接続 |

### 5. Japan Macro(BOJ / e-Stat / 財務省 / 経産省 / 貿易統計等)

| 項目 | 内容 |
| --- | --- |
| Role | 金融政策・物価・GDP・貿易統計等の日本マクロ統計 |
| Authority | PRIMARY_OFFICIAL |
| PIT semantics | Revisionが頻繁に起こる(GDP速報値→改定値等)。`RevisionHistory.as_of()`で過去DecisionへのLeakを防ぐ設計を用意済み |
| Current Implementation Status | NOT_IMPLEMENTED(`MacroDataProvider` Protocolのみ) |
| Cost/Plan dependency | 無料(政府統計) |
| Known limitations | 各統計のRevisionスケジュール・公表時刻の制度は未確認 |

### 6. Global Market Data(FX / 金利 / 株価指数 / Commodity等)

| 項目 | 内容 |
| --- | --- |
| Role | Cross Asset環境の把握(日本株への波及経路分析の材料) |
| Authority | 提供元による(取引所公式なら PRIMARY_OFFICIAL、ベンダー経由ならSECONDARY等) |
| PIT semantics | 通常は準リアルタイムだが、Providerによって遅延が異なる(未検証) |
| Current Implementation Status | NOT_IMPLEMENTED(`GlobalMarketDataProvider` Protocolのみ) |
| Cost/Plan dependency | Provider次第(未選定) |
| Known limitations | Global Event → 日本セクターへの伝播関係(Graph構造)はSchema上の余地のみでPhase3Dでは推論未実装 |

### 7. Japan News

| 項目 | 内容 |
| --- | --- |
| Role | 国内報道(決算報道・業界ニュース等) |
| Authority | VERIFIED_SECONDARY〜SECONDARY(媒体による) |
| PIT semantics | `NewsEvent.published_at`/`source.available_at`で管理。Dedup Semantics(`lib/evidence/news.py`)でExact/Syndicated/Same-Eventを区別 |
| Current Implementation Status | NOT_IMPLEMENTED(`NewsProvider` Protocol・`NewsEvent` Schemaのみ) |
| Cost/Plan dependency | Provider次第(未選定) |
| Known limitations | 全件LLM投入は禁止方針。Relevance Scoring(AI)はPhase5/6 |

### 8. Global News

| 項目 | 内容 |
| --- | --- |
| Role | 海外報道(マクロ・Cross Asset関連ニュース) |
| Authority | VERIFIED_SECONDARY〜SECONDARY |
| PIT semantics | Japan Newsと同じ`NewsEvent`だが`scope=GLOBAL` |
| Current Implementation Status | NOT_IMPLEMENTED |
| Cost/Plan dependency | Provider次第(未選定) |
| Known limitations | Japan Newsと同様 |

### 9. Consensus / Expectations(Analyst Consensus / EPS Revision / Target Price等)

| 項目 | 内容 |
| --- | --- |
| Role | 市場期待値とのGapを測るためのExpectations Data |
| Authority | Provider次第 |
| PIT semantics | Consensus改定履歴はRevision管理が必須(`RevisionHistory`で表現可能) |
| Current Implementation Status | NOT_IMPLEMENTED(実Provider未選定、`ConsensusProvider` Protocolのみ) |
| Cost/Plan dependency | 通常有料。Phase3Dでは契約しない |
| Known limitations | 実Providerが未選定のため、具体的な仕様検討は未着手 |

### 10. Idea Sources(X / YouTube / 学術論文 / 手動入力)

| 項目 | 内容 |
| --- | --- |
| Role | 投資アイデアの種(Hypothesis化される前の段階) |
| Authority | SOCIAL(X/YouTube)〜USER_SUPPLIED(手動)。**FACT Sourceではない** |
| PIT semantics | 既存`lib.schemas.idea.Idea`(`03_idea_inbox/`)と組み合わせる想定 |
| Current Implementation Status | NOT_IMPLEMENTED(Crawling等は行わない方針、`IdeaSourceProvider` Protocolのみ) |
| Cost/Plan dependency | 取得不可(未確認) |
| Known limitations | Crawling自体がPhase3Dのスコープ外(Phase5/6) |

## Phase3Dで実装していないもの

LLMによるRetrieval Selection、Positive/Negative自動分類、News Relevance AI、
Hypothesis生成、Skeptic Agent、Ablation Engine、BUY/SELL判断、実際のBOJ/e-Stat等
Skeleton Adapter(公式仕様未確認のため推測実装しない)、実際のBulk/File Download
Endpoint接続(仕様未確認)、外部API Key取得・有料契約・大量Download・Web
Scraping・News Crawling・TDnet Add-on契約・Consensus契約。これらはPhase5/6以降。

## Phase4 Roadmap(D0041でPlanning、Phase4AはD0043でCOMPLETE)

**最初の実データ接続はJ-Quants V2 Fundamentals/Financial Summaryから開始する**
(TDnetからではない)。理由:

- J-Quants V2認証は既に実データで動作確認済み(Phase3B、`x-api-key`)。
- Raw Snapshot / PIT / Provenance / Entity Mappingとの統合を、新規Provider認証・
  新規APIスキーマという2つの未知数を同時に抱えずに、最も小さい追加リスクで検証できる。
- Phase3D Foundation(Catalog/Provider Protocol/Entity Registry/Evidence Model)を
  本物の企業財務データで最初に実戦テストできる。
- 「Foundation自体の設計に問題があるか」と「TDnet/EDINET等、新規Source固有の
  接続問題か」を切り分けやすい(新規Source認証と新規Foundation検証を同時に
  デバッグしない)。

| Phase | 対象Source | 主な追加DataCapability |
| --- | --- | --- |
| **4A** | J-Quants Fundamentals / Financial Summary | FUNDAMENTAL |
| **4B** | TDnet + EDINET + Company IR | DISCLOSURE |
| **4C** | Positioning / 需給(信用・空売り・投資部門別等) | POSITIONING |
| **4D** | Japan Macro(BOJ / e-Stat / 財務省 / 経産省 / 貿易統計等) | MACRO |
| **4E** | Japan News / Global Market Data / Global News / Consensus | NEWS / GLOBAL_MARKET / EXPECTATIONS |
| (Phase6) | Idea Sources(X / YouTube / Papers) | IDEA |

Idea Sourcesは方針上Crawlingを伴うため後続Phase6へ送る(Phase4には含めない)。

### Phase4Aで最優先する原則

**Phase4Aは「好決算銘柄を探す」ことを目的にしない。** 最優先は、以下の経路が
実データで正しく通ることである。

```
J-Quants Financial Raw -> Normalized Fundamental Record -> Canonical Entity
-> PIT -> Revision History -> Catalog -> Evidence -> Provenance
```

**最重要Validation項目は「後日修正された会社予想・財務データを、修正前の
DecisionへLeakさせないこと」**(`lib.evidence.model.RevisionHistory.as_of()`が
実データでも正しく機能することの確認)。Phase4Aでは戦略探索・パラメータ
最適化・BUY/SELL判断は一切行わない(Phase3Cの固定Strategy検証時と同じ、
Infrastructure/Integration Validationとしての位置づけ)。

### Backtest/Experimentの完全Offline原則

Phase4以降の全Data Sourceについて、Backtest/Experiment実行中に外部Providerへ
問い合わせる構造を本番Defaultにしない(詳細はRESEARCH_RULES.md「Backtest/
Experimentの完全Offline原則」参照)。`lib.universe.FrozenPitUniverseProvider`
(D0042)が、事前取得済みSnapshotのみから解決する構成の実装例。

### Phase4A Fundamental Schema Contract(実装済み、`lib/fundamentals/`、D0043)

Fundamental Dataを`code / date / sales / profit`のような単純なWide Tableへ
潰さず、Disclosure単位の`DisclosureEnvelope`(記述的Envelope)と
Metric単位の`FundamentalMetric`(Long-form)に分離して実装した
(`lib/fundamentals/model.py`)。

```
# 実装済みSchema(lib/fundamentals/model.py、Field名は未検証、DECISIONS.md D0043参照)
actual_or_forecast:  ActualOrForecast(ACTUAL | COMPANY_FORECAST)
fiscal_year_target:  FiscalYearTarget(CURRENT_FISCAL_YEAR | NEXT_FISCAL_YEAR)
period_type:         PeriodType(1Q | 2Q | 3Q | 4Q | 5Q | FY | OTHER)
period_basis:        PeriodBasis(CUMULATIVE | STANDALONE)  # 2Q累計をQ2単独値として扱わない
consolidation_scope: ConsolidationScope(CONSOLIDATED | NON_CONSOLIDATED)
disclosure_date / disclosure_time / disclosure_number  # DisclosureEnvelope
document_type                                            # DisclosureEnvelope
accounting_standard: str | None                          # DocType明示Mapping、未確認はNone
revision:            SourceVersion/RevisionHistoryを流用(D0040、revision_reason含む)
currency / unit
raw_value: str | None / value: Decimal | None / value_availability: ValueAvailability
```

**重要**: NULLを0へ変換しない。会計基準上存在しない指標(例: IFRS等で経常利益
相当Fieldが存在しない場合)を0とみなさない(`lib.evidence.model.
ValueAvailability`、`EVIDENCE_MODEL.md`「Value Availability」参照)。
数値は`float`ではなく`Decimal`でParseし精度を保つ(`raw_value`もそのまま
併せて保持する)。決算期変更(fiscal_period/fiscal_yearのズレ)への耐性は
Phase4Aでは`current_fiscal_year_start/end`等をOptionalとして持つのみで、
自動補正は行わない。

**Actual/Current-forecast/Next-forecastは常に別Record**: J-Quantsの
`Sales`/`OP`/`NP`(実績)、`FSales`/`FOP`/`FNP`(当期予想)、`NxFSales`/
`NxFOP`/`NxFNP`(翌期予想、想定Field名、未検証)は同じ「営業利益」概念でも
互いに上書きしない別`FundamentalMetric`として保持する
(`lib.fundamentals.normalize._METRIC_FIELD_MAP`)。

**As-of View**: `lib.fundamentals.view.fundamentals_as_of(revision_histories,
decision_at, availability_semantics=...)`が外部呼び出しを一切持たない
純粋関数として、Market Information Study(A系統、`published_at`基準)/
Reproducible System Simulation(B系統、`available_at`基準、既定)を
切り替え可能にする(D0042「2種類のPIT研究」参照)。

### Storage Architecture(将来要件、D0042。現時点ではMigration不要)

全市場Price + Fundamentals + Newsへ進む前に検討する方向性のみ予約する
(現時点でのStorage Migrationは不要)。

| データ種別 | 推奨方向 |
| --- | --- |
| Raw Provider Data | Immutable / compressed JSON or CSV(現行`RawSnapshotStore`を維持) |
| Normalized Numerical Data | Parquet |
| Analytical Query | DuckDB |
| Catalog / Metadata / Provenance | SQLite または DuckDB |
| Long-form Document / News | File/Object Storage + Metadata DB |

**重要**: Raw Provider PayloadをParquet変換後に削除しない。Rawは証拠として残す。
Derived/Normalizedは常にRawから再生成可能にする。

### News Licensing / Storage Policy(将来要件、D0042。Phase4Aでは実装不要)

Phase4EでNewsを実装する前に、Sourceごとの保存Policyを必須化する
(Roadmap/Architecture requirementのみ、Phase4Aでは実装しない)。

```
FULL_CONTENT_ALLOWED | METADATA_ONLY | REFERENCE_ONLY |
DERIVED_SUMMARY_ALLOWED | UNKNOWN_RESTRICTIONS
```

`UNKNOWN_RESTRICTIONS`の場合は安全側へ倒す(保存範囲を制限する)。
`SourceMetadata.license_or_usage_note`(既存、自由記述)だけでなく、将来的には
機械的に保存可否を制御できるStorage Policyへ拡張可能にする。
