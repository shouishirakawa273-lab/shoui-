# Japan News Data Architecture(Phase4E-2)

このDocumentは`lib/news/`の設計判断をまとめる。実装詳細は各Moduleの
docstringを参照し、ここでは全体像とSourceを跨いだ設計判断のみを記す。

## 目的とScope

日本語Newsの記事Metadata(見出し・公開時刻・出所・Provenance)を
PIT-safe/provenance-preserving/reproducibleな形でこのLabへ取り込むための
Data Foundation。**Sentiment判定・Event抽出・Investment Conclusion・
BUY/SELLはこのPhaseのScope外**であり、`lib/news/`のどのModuleも生成しない
(DECISIONS.md D0058参照)。

「News Source -> Raw Article Metadata -> Canonical NewsArticleRecord ->
Pure as_of View -> (Optional)Evidence変換」までがこのPhaseの範囲。News →
Event → Investment Conclusionという先のLayerには着手しない。

## `lib.evidence.news.NewsEvent`との境界(最重要の設計判断)

Phase3D由来の`lib.evidence.news.NewsEvent`は既に存在するが、**このRoundでは
再利用・拡張しなかった**。理由:

- `NewsEvent`は`event_type`(必須Field)・`entities`・`affected_sectors`・
  `affected_codes`・`confidence`を持ち、そのModule Docstring自身が
  「News Feed -> Metadata ingest -> Deduplication -> **Event extraction**
  -> ... -> Relevant Retrieval」というPipelineの**後半**(Event抽出後)を
  担うSchemaだと明記している。Phase4E-2要件はEvent抽出を明示的に禁止して
  おり(§24)、`event_type`必須Fieldを持つSchemaへ「Event未確認」の記事を
  流し込むこと自体が設計上の矛盾になる。
- `NewsEvent.classify_news_relation()`は見出し正規化のみで`EXACT_
  DUPLICATE`/`SYNDICATED_COPY`を**自動**判定する。これはPhase4E-2要件§28
  (「Headline Similarity Is Not Duplicate」、見出し類似度だけでの
  Duplicate判定禁止)より緩い基準であり、そのまま踏襲すると新しいRoundの
  原則を既存Scaffoldが破ることになる。

したがって`lib/news/`を**その手前の層(Metadata Ingest層)**として新設した。
既存`lib/evidence/news.py`・`13_tests/test_evidence_news.py`はいずれも
無変更のまま(`git status`で確認)。将来、`lib/news/`のOutput(`NewsArticle
Record`)を`NewsEvent`(Event層)へ変換するLayerが必要になった場合は、別
Roundで明示的に設計する(このRoundでは着手しない)。

## Document-shaped、Series-shapedではない(Disclosuresの前例を踏襲)

Positioning/Macro/Global Marketは「同じMetricの時系列」を扱うため
`RevisionHistory`/`SourceVersion`ベースのLong-form Series設計だったが、
News記事はそれぞれ独立した意味を持ち、同じ会社についての複数記事が
同時に「見えている」状態が正しい(古い記事が新しい記事にRevisionとして
置き換わるわけではない)。この性質は`DisclosureDocument`と同じであるため、
`lib/news/`は**Disclosures Common Coreの構造を踏襲した**:

- `NewsArticleRecord`は`DisclosureDocument`と同型のField構成
  (`published_at`/`published_at_basis`、`provider_available_at`/
  `provider_available_at_basis`、`retrieved_at`)。
- `news_as_of()`は`disclosures_as_of()`と同じ「Set Filter」(Latest-winsで
  はない、decision_at時点で利用可能な記事の集合を返す)。
- `news_article_to_evidence()`のavailable_at優先順位も`disclosure_
  document_to_evidence()`(D0050)と同一: (1) `provider_available_at`が
  確認済みならそれを使う、(2) 確認できなければ`retrieved_at`。
  `published_at`へは決してFallbackしない(D0049/D0050原則)。

## Published Time != Provider Availability != Retrieved Time != Event Time

記事本文に「昨日発表した」等のEvent Time言及があっても、それは記事自体の
`published_at`(公開時刻)とは別概念であり、本文からのEvent Time抽出は
このRoundでは行わない(Phase4E-2要件§15)。`published_at`はSourceが
確認済みの正確なTimestamp(tz-aware)を渡した場合のみ設定し、日付のみ
確認できる場合は`published_date`のみを保持し時刻を推測しない(§12)。

## Article Identity(URLだけをIdentityにしない)

`source_native_id`(Source自身が付与する記事ID)を優先Identity候補とする。
`canonical_url`は参照用Fieldでありidentity判定には使わない——同じ記事が
URL変更・Mobile URL・転載URL・Archive URLで複数存在しうる(§11)。

## Duplicate Handling(Safe Tierのみ、Potential Tierは実装しない)

`lib.news.normalize`は以下のみを提供する:

- `find_same_source_native_id_signals()`: 同一`source_native_id`を持つ
  記事間のSignal(Safe、構造的に確認可能)。
- `find_exact_raw_content_duplicate_groups()`: Raw Payload内の行全体
  Content Hash完全一致による重複候補検出(Safe、Pagination境界重複等の
  検出用途)。

見出し類似度・URL類似度・時刻近接からの自動Duplicate判定(Potential
Tier)は**このRoundでは実装しない**——`test_news007_no_headline_or_url_
based_duplicate_function_exists_in_normalize`で、`lib.news.normalize`の
Public関数名に"headline"/"url"を含む関数が存在しないことを構造的に固定
した。将来必要になった場合、既存`lib.evidence.news.classify_news_
relation()`(Event層のHeuristic)とは別に、明示的にPotential-Onlyの
Candidate生成として設計する必要がある。

## Mutable URL Problem(推測でRevisionと判定しない)

同一URLの本文が後から変わりうる(§17)。Raw SnapshotはRawSnapshotStoreの
Append-only保存で確認できるが、Raw Hash変化そのものを「Revisionが確認
された」とは自動的に解釈しない(RAW-002原則と同じ)。`updated_at`は
Sourceが明示的に確認済みのUpdate/Correction Timestampを提供した場合の
みEvidence元Recordへ設定し、URLの内容変化から推測しない。

## Compliance / Copyright(News Content Storage)

Source固有のTerms/Licenseにより全文保存可否が異なるため、`ContentAvailability`
(`FULL_TEXT`/`HEADLINE_ONLY`/`METADATA_ONLY`/`REFERENCE_ONLY`/`UNKNOWN`)
という状態をCommon Model Fieldとして明示する。「全文保存必須」という
前提をCommon Coreへ埋め込まない(Source-specific Policyとして扱う、
§19/§34)。Company IR(Phase4B-4)で確立したCompliance Pattern
(COMPLY-001〜003: 自動取得可否はCallerが明示確認、認証情報らしきURLは
除外、保存HeaderはAllowlistのみ)は、将来実Adapterを実装する際にそのまま
再利用できる(`lib/disclosures/providers/company_ir.py`の`Compliance
CheckResult`Pattern参照)。

## Entity Mapping(見出しText Matchingでは確定しない)

`entity_id`はSourceが構造化されたEntity識別子(会社Code等)を提供した
場合のみ設定する。見出し・本文の会社名Text Matchingでは設定しない
(曖昧な場合は`None`のまま、§21)——見出しText由来のEntity推定はEvent
抽出と同種のInferenceであり、このRoundのScope外。既存`lib.sources.
entity_registry.EntityRegistry`は、将来実Adapterが構造化Entity識別子を
提供するようになった時点で再利用できる(新規Entity Mapping機構は作らない)。

## D0057との境界(重要)

`news_article_to_evidence()`が生成する`EvidenceRecord`は技術的には
`lib.evidence.retrieval.filter_usable_at()`へ渡せるが、**このRoundでは
一切接続しない**(§25)。D0057(ARCHITECTURE_GAP、Validation Backlog #21)
が確認した通り、Evidence経路の`available_at`(`retrieved_at`基準)と
`news_as_of()`のCanonical Availability Semantics(`published_at`/
`provider_available_at`基準)は独立した推定戦略であり、両者を統合する
設計判断はこのRoundでは行わない。`test_news015_*`で、`lib/news/`の
いずれのModuleも`lib.evidence.retrieval`をImportしないことを構造的に
固定した。

## このRoundで実装したSource

**なし**。`data-source-researcher` Agent(2026-08-18)がPR TIMES・JPX News
Releases・FSA・METI・BOJ「What's New」・Nikkei・Reuters/Refinitiv・
Bloomberg・Kyodo/Jiji等を調査したが、このSession自身のNetwork Egressが
全ての候補Provider Domainへ一貫してBlockされており(`EGRESS_BLOCKED`)、
全ての情報がSEARCH-SNIPPET-DERIVED(UNVERIFIED)に留まった。検索Snippet
のみを根拠にAdapterを実装しない(Phase4E-2要件§8)。

## Source候補(未実装、NOT_IMPLEMENTED)

`lib/news/catalog.py`に4件のDescriptorとして登録済み:

| dataset_id | 対象 | Authority Class | 判明した制約 |
|---|---|---|---|
| `prtimes_press_release` | PR TIMES(企業Press Release配信) | COMPANY_PRIMARY(発行企業) | data-source-researcher推奨順位1位。会社別/リリース別RSSの存在は複数独立Snippetで裏付けられたが、公式Public APIは未確認。全文保存・再配布Terms(企業規約第6条相当)が制限的な可能性(未読)。公開Article/RSS自体が実際に露出するTimestamp Fieldの粒度も未確認(著者用UI側の示唆のみ) |
| `jpx_news_releases` | JPX(取引所自体からのお知らせ、TDnetとは別) | PRIMARY_OFFICIAL | RSS Feedの存在は示唆されたが未読。pubDateの粒度・Timezone表現未確認 |
| `fsa_press_release` | 金融庁 報道発表資料 | PRIMARY_OFFICIAL | RSS Feed(SESC向け別Feedも含む)の存在は示唆されたが未読 |
| `meti_news_release` | 経済産業省 News Release | PRIMARY_OFFICIAL | RSS Feed(3系統と示唆)の存在は示唆されたが未読。Live Site Archive Depthが「過去3年度分」に限られるという記述あり(未確認) |

BOJ「What's New」RSSはPhase4E-1で既に登録済みの`boj_policy_rate`
(Macro Capability)と対象が重複しうるため、このRoundでは新規登録せず
Known Limitationとして記録するに留める(§下記参照)。Nikkei・Reuters/
Refinitiv・Bloomberg等は「構造化Feedより優先度が高いScraping/高額
Enterprise契約」に該当するため、このLabの「Web Scraping を標準手段に
しない」「Structured Sourceを優先する」原則により今回は候補から除外した
(§7)。

## Q(最重要PIT論点): PR TIMESの公開Timestamp Fieldの実際の粒度

data-source-researcher Agentの調査で見つかった最も重要な未確認事項は、
PR TIMESの**著者用UI側**が10分刻みのSchedule機能を持つという示唆だけで、
**公開側(Article/RSS)が実際に露出するTimestamp Field**そのものは未確認
という点である。著者側の入力粒度と公開側の露出Fieldは別概念であり
(D0043の「Provider Update Policyの『頃』表現をExact Timestampへ変換
しない」と同じ原則)、この差を安易に埋めない。

## Common Coreへ含めないもの

Source固有のSemantics(RSS Field名Mapping・PR TIMES company_id ↔ Canonical
Entity RegistryのMapping・Compliance確認手順)は将来`lib/news/providers/`
配下に閉じ込め、Common Core相当の`lib/news/model.py`/`normalize.py`/
`view.py`/`evidence.py`へは一切追加しない設計とする(Phase4B/4C/4D/4E-1
と同じ境界原則)。

## Validation Status(実装状況とは別軸)

4候補全て`implementation_status=NOT_IMPLEMENTED`、Validation Status=
`DESIGN_COMPLETE_AWAITING_SPEC_VERIFICATION`(`lib/news/catalog.py`の
`known_limitations`へ自由記述、そのためだけの新規Schema Fieldは追加
しない——Positioning Phase4C/Macro Phase4D/Global Market Phase4E-1と
同じ方針)。

## Known Limitations(NEWS-016含む)

- NEWS-016(Historical API Response Is Not Historical Snapshot)は
  Adapter自体が無く、実際に再現するExecution Pathが無いため、Macro/
  Global Marketと同じくCode Testではなくこの文書上のKnown Limitation
  として記録する: 将来Newsの過去記事取得APIを実装する場合、現在のAPI
  Responseが過去のProvider Snapshotと同一である保証は無い(EDINET
  D0046の「Historical List Is Mutable」と同じ懸念パターン)。
- `lib.news.model.NewsArticleRecord`は`updated_at`Fieldを持つが、これを
  実際に設定する経路(Source側のUpdate/Correction通知の検出方法)は
  未設計(実Adapter実装時の課題として残す)。
- BOJ「What's New」RSSは既存Macro Catalog(`boj_policy_rate`)との対象
  重複可能性があり、このRoundでは新規Catalog登録を見送った——将来
  News/Macro双方のCatalog統合方針を検討する余地がある。
