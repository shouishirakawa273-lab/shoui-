# Global News Data Architecture(Phase4E-3)

このDocumentは、Phase4E-3(Global News Data Foundation)の設計判断を
まとめる。実装詳細は各Moduleのdocstringを参照し、ここでは全体像と
Japan News(Phase4E-2)からの拡張方針・Sourceを跨いだ設計判断のみを記す。

## 目的とScope

日本株研究に影響しうる、海外発のNews記事Metadata(見出し・公開時刻・
出所・多言語・配信経路・Provenance)をPIT-safe/multilingual-aware/
timestamp-aware/provenance-preservingな形でこのLabへ取り込むための
Data Foundation。**Sentiment判定・Event抽出・Impact Scoring・日本株への
Mapping・Investment Conclusion・BUY/SELLはこのPhaseのScope外**であり、
`lib/news/`のどのModuleも生成しない(DECISIONS.md D0059参照)。

## 最重要の設計判断: 専用Modelを作らず、既存`NewsArticleRecord`を拡張した

Phase4E-3要件§3は「まずPhase4E-2のNewsArticleRecord/原則を確認し、専用の
Global News Modelを即座に作らない」ことを明示的に求めた。Repository
Reality Checkの結果、既存`lib.news.model.NewsArticleRecord`は`language`
Fieldを既にPhase4E-2からFirst-classで持っており、Global News固有の追加
要件(多言語Identity・Syndication・地理・Timezone Provenance)は全て
**既定`None`のOptional Field追加のみ**で表現可能と判断した。専用の新規
Modelを作ると、Japan News/Global Newsという人為的な二分法がCommon Core
に生まれ、将来「日本語で書かれた海外発記事」のような境界事例を扱えなく
なる(そもそも`language`はSource非依存のFieldであり、国境と言語を
一致させる前提そのものが§22の「言語からCountryを推測しない」原則に反する)。

追加した9Fieldは全て`= None`Default:

| Field | 目的 | 対応要件 |
|---|---|---|
| `original_article_id` | 翻訳元(原文)記事のID | §9〜11 Multilingual Identity |
| `translated_from_article_id` | 直接の翻訳元記事ID | 同上 |
| `language_variant` | Sourceが明示するEdition/Variant(例: "en-US") | 同上 |
| `wire_origin` | 記事の原典Wire Service(例: "Reuters") | §12 Syndication |
| `publisher` | 実際に掲載したWebsite/媒体 | 同上 |
| `country` | Source構造化Metadataが明示する国 | §22 Geography |
| `region` | 同上、地域 | 同上 |
| `jurisdiction` | 同上、法域 | 同上 |
| `source_declared_timezone` | Sourceが記事に添えたTimezone文字列(生Text) | §14 Timezone Provenance |

**検証方法**: 既存Japan News Test(`test_news_model.py`/`test_news_pit.py`、
計53件)をこの拡張後に無変更のまま再実行し、全て成功することを確認した
(Phase4E-3要件§3「既存Semanticsを壊さない」を実測で確認、憶測に留めない)。

## `lib/news/normalize.py`/`view.py`/`evidence.py`はGlobal News向けに一切変更していない

Phase4E-3要件§27は「既存`news_as_of()`がGlobal Newsに安全に再利用できる
かを確認し、必要な場合のみ最小限拡張する」ことを求めた。このRoundでは
**Function本体を1行も変更していない**——代わりに`13_tests/test_global_
news_pit.py`(GNEWS-001〜018、24Test)を新設し、既存Function群を
Global Newsの実際のシナリオ(複数Timezoneを跨ぐPublished/Provider
Availability・翻訳記事・Syndication・曖昧Timezone略称)で駆動して、
既存Semanticsがそのまま正しく機能することを直接確認した。「拡張が要る
かどうかを確認する」という要件を、確認Testを書くことで文字通り実行した
形になる。

## Multilingual Identity(最重要、§9)

同じ出来事(Underlying Event)についての英語記事・日本語記事・フランス語
記事は、**必ずしも同じArticleではない**(§9)。Article Identityと
Event Identityを分離する:

- Article Identity判定は既存の`source_id`+`source_native_id`(Safe Tier)
  のみを使う。`language`/`original_article_id`/`translated_from_
  article_id`/`language_variant`は**Article Identity判定には一切使わ
  ない**(GNEWS-006で構造的に確認: 翻訳記事が自動的にDuplicateとして
  Flagされないことをテスト)。
- `original_article_id`/`translated_from_article_id`/`language_variant`
  は**Sourceが明示的に確認できた場合のみ**設定する。翻訳内容の類似度
  (Content Similarity)だけからこれらのFieldを推測することは、
  Common Coreのどの関数からも行わない。
- `language`が`None`の場合、これは「英語」を意味しない
  (GNEWS-018で確認、Language Unknown Is Not English)。

## Syndication: Publisher / Wire Origin / Retrieval Source の3層分離(§12)

Source Integration Skillの`SOURCE-005`(TDnet統合で確立した
`publishing_entity`/`disclosure_system`/`delivery_provider`の3層分離)を
News Syndicationへ適用した:

- `wire_origin`: 記事のClaim Source、原典となるWire Service(例:
  "Reuters")。
- `publisher`: 実際に掲載したWebsite/媒体(例: 提携先地方紙)。
- `source_id`(既存Field): このLabが実際にどこから取得したか
  (Retrieval Source、例: RSS/APIのEndpoint)。

3つは独立に記録し、いずれかからいずれかを推測しない。同じ`wire_origin`
を持つが`publisher`が異なる記事は、自動的に同一Articleとはみなさない
(GNEWS-008)。またReutersとBloombergがそれぞれ同じEventについて書いた
記事は、Article自体は別物である——Cross-source Duplicateの自動判定は
行わない(GNEWS-007、Article Identity != Event Identity、§20)。

## Timezone Safety(最重要、§14)

- `published_at`/`provider_available_at`/`retrieved_at`は、既存の
  Japan News原則通り**tz-aware datetimeのみ**を受け付ける(naive
  datetimeの構築自体を拒否、`__post_init__`)。
- 曖昧なTimezone略称(EST/CST/IST等)は、それだけで一意のIANA
  Timezoneへ対応しない(例: CSTは米国中部標準時・中国標準時・キューバ
  標準時のいずれもありうる)。このLabのどのModuleも略称からIANAへの
  自動変換を実装しない。
- `source_declared_timezone`(新規Field)はSourceが実際に添えた
  Timezone文字列を**そのまま**保持するProvenance専用Fieldであり、
  `lib/news/`のいずれのFunction(`normalize`/`view`/`evidence`)からも
  計算に使われないことをAST走査で構造的に固定した
  (GNEWS-004、`test_gnews004_source_declared_timezone_is_never_read_
  by_normalize_view_or_evidence`)。曖昧な略称値("CST"等)もそのまま
  文字列として保持され、解析・変換されない
  (`test_gnews004_ambiguous_abbreviation_stored_as_is_without_iana_
  conversion`)。
- 実際の`published_at`/`provider_available_at`はReal `zoneinfo.
  ZoneInfo`によるtz-aware datetimeとして構築された場合のみ設定でき、
  異なるTimezone(例: US Eastern基準のpublished_atとCET基準の
  provider_available_at)でも`news_as_of()`が正しくUTC比較で動作する
  ことをGNEWS-001/GNEWS-003で確認した。
- 日付のみ判明しExact Timestampが不明な場合は、既存Japan News原則
  (§12)と同じく時刻を推測せず`published_date`のみを設定する(§15)。

## Copyright/Compliance: UNKNOWN != ALLOWED(§24)

`ContentAvailability`(既存Phase4E-2 Enum、`FULL_TEXT`/`HEADLINE_ONLY`/
`METADATA_ONLY`/`REFERENCE_ONLY`/`UNKNOWN`)をGlobal Newsでも無変更で
再利用する(§26)。Source候補の全文保存・再配布可否はいずれも未確認
(`EGRESS_BLOCKED`により一次規約文書が未読)のため、`lib/news/catalog.py`
のGlobal News候補は`known_limitations`へ正直に未確認である旨を記録した
(GDELTはそもそも全文配信ではなくEvent-level Metadataであるため
`REFERENCE_ONLY`が上限、SEC press releaseはTerms自体を含め未読)。
Paywall/Loginのbypass、認証情報のRaw Metadataへの保存はいずれのAdapter
Design(未実装)にも含めていない(§25)。

## D0057との境界(維持、解決しない)

`lib.news.evidence.news_article_to_evidence()`は既存Function のまま
Global Newsの記事にも適用可能だが、**このRoundでもBacktest/Decision
Engineへ一切接続しない**(§28)。D0057(ARCHITECTURE_GAP、Validation
Backlog #21)が確認した通り、Evidence経路の`available_at`(`retrieved_
at`基準)と`news_as_of()`のCanonical Availability Semantics
(`published_at`/`provider_available_at`基準)は独立した推定戦略で
あり、両者を統合する設計判断はこのRoundでも行わない。既存
`test_news015_*`(Phase4E-2)の構造的固定に加え、GNEWS-016
(`test_gnews016_news_evidence_module_never_imports_retrieval_or_
filter_usable_at`)でGlobal Newsの文脈でも同じ境界をAST走査で再確認
した。

## `lib.evidence.news.NewsEvent`との境界(維持)

Phase4E-2で確立した「`lib/news/`(Metadata Ingest層)と`lib.evidence.
news.NewsEvent`(Event層、Phase3D)は恒久的に分離したまま維持する」
方針をこのRoundでも継続する。`NewsArticleRecord`拡張後も`event_type`
Fieldは追加していない。統合Layerの設計は依然として未着手であり
(Validation Backlog行26、変更なし)、既存Structural Test
(`test_news_modules_never_import_evidence_news_event_scaffold`)は
このRoundの拡張後も無変更のまま成功する。

## Source Candidate Landscape(data-source-researcher Agent、2026-08-18)

Reuters/LSEG・Bloomberg・AP・AFP・SEC・Federal Reserve・US Treasury・
ECB・Bank of England・英国政府(gov.uk)・EC Press Corner・PBOC・GDELT・
NewsAPI.org・Google News RSS・LSE RNS・Nasdaqを調査した。結果は全て
`EGRESS_BLOCKED`のためSEARCH-SNIPPET-DERIVED(UNVERIFIED)に留まった。

**分類結果**:

- **Wire Service(Reuters/LSEG・Bloomberg・AP・AFP)**: いずれも
  Enterprise契約前提であり、個人がローカル実行するという本Labの前提
  (ルートCLAUDE.md)にそぐわないため今回は候補から除外。
- **政府/中央銀行RSS(SEC・Federal Reserve・US Treasury・ECB・Bank of
  England・gov.uk・EC Press Corner)**: 概ね無料・認証不要だが、PIT
  関連の詳細(Timestamp Field仕様・Timezone表現・Correction挙動)が
  軒並み未確認。SECのRSSが"EST"という年間固定Timezone Labelを使って
  いる可能性(D0056で確認済みの`ZoneInfo("EST")`固定UTC-5問題と同型)、
  US Treasuryの過去RSSに実際の2021年Replay Bug(古いItemの再配信)が
  報告されている点が、Government RSS全般に対する具体的なPIT Risk事例
  として特に重要と判断した。PBOCは公式RSS/APIそのものが確認できな
  かった。
- **取引所/操作Feed(LSE RNS・Nasdaq)**: LSE RNSは一般Newsではなく
  上場企業自身の開示System(Disclosure Systemに相当、日本のTDnetに
  近い性質)であり、Nasdaqの候補Feedは個別Ticker Trading Halt通知等
  Narrowな運用情報でありGeneral Newsではないため、いずれも候補から
  除外(対象が異なるため)。
- **GDELT DOC 2.0/Bulk Export**: Global News候補の中で最もTimezone
  Documentation(UTC既定/DST関連の明示的記述との示唆)が明確だが、
  配信されるのはNews記事の全文ではなくEvent-level Metadata(URL・
  出典・言語・トーン等)である。「Unrestricted use...without fee」と
  いうLicense主張のSnippetもあるが本文自体は未読のため確定させない。
- **NewsAPI.org**: 明示的なTermsのSnippetがあるが、全Planで全文の
  再配布が不可とされており、全文保存を前提とするこのLabの用途に合わ
  ない。
- **Google News RSS**: 非公式・無Document(Googleの公式Product/API
  ではない)であり、このLabの「Structured/公式Sourceを優先する」
  原則(§7)に反するため候補から除外。

**最終的にCatalogへ登録した候補は2件のみ**(`lib/news/catalog.py`):

| dataset_id | 対象 | Authority Class | 判明した制約 |
|---|---|---|---|
| `gdelt_doc_2` | GDELT DOC 2.0(Event-level Metadata) | VERIFIED_SECONDARY | 全文ではなくMetadata配信(REFERENCE_ONLY止まり)。UTC既定/Licenseいずれも未読。data-source-researcher推奨順位1位 |
| `sec_press_release` | SEC 報道発表資料/Litigation Release RSS | PRIMARY_OFFICIAL | "EST"年間固定Label疑義(IANA自動変換はしない方針)。EDGAR Acceptance Datetime != Filing Dateの区別が未確認。参考: US TreasuryのRSS Replay Bug(2021年、未採用) |

いずれも`implementation_status=NOT_IMPLEMENTED`、Validation Status=
`DESIGN_COMPLETE_AWAITING_SPEC_VERIFICATION`。

## No Sentiment / No Event Inference / No Japanese Stock Mapping(§30/§31/§21)

`lib/news/`のいずれのModule(拡張後も含む)も、以下を一切生成しない:

- Sentiment(Positive/Negative/Hawkish/Dovish/Risk-on/Risk-off)判定。
- Event分類(戦争/制裁/金利決定/M&A/決算/製品発表等)。
- 見出しText MatchingからのEntity推定・日本株Ticker Mapping
  (GNEWS-013で確認: 見出しに"Toyota Motor"を含んでいても`entity_id`は
  自動設定されない)。
- Country推測: Article言語(例: 英語)からCountryを推測しない
  (GNEWS-013で確認)。

Hedge Phrase("Sources say"/"reportedly"/"expected to"/"considering"
等)を含む記述はClaimでありConfirmed Factではない(§23)。
`news_article_to_evidence()`が生成するEvidence Contentは本文Textや
Hedge表現を一切取り込まず、「この見出しの記事が公開された」という
Meta-level FACTのみを記述する(GNEWS-017で確認)。

## Common Coreへ含めないもの

Source固有のSemantics(GDELT GKG/CAMEO Code Mapping、SEC RSS Field名
Mapping、Timezone略称解決規則等)は将来`lib/news/providers/`配下に
閉じ込め、Common Core相当の`lib/news/model.py`/`normalize.py`/
`view.py`/`evidence.py`へは一切追加しない設計とする(Phase4B/4C/4D/
4E-1/4E-2と同じ境界原則)。

## Validation Status(実装状況とは別軸)

Global News候補2件とも`implementation_status=NOT_IMPLEMENTED`、
Validation Status=`DESIGN_COMPLETE_AWAITING_SPEC_VERIFICATION`
(`lib/news/catalog.py`の`known_limitations`へ自由記述、そのためだけの
新規Schema Fieldは追加しない)。

## Known Limitations

- GDELTのUTC Timezone Documentation・Licenseはいずれも未読
  (`EGRESS_BLOCKED`)。実装前にLocal Environmentからの一次文書確認が
  必要。
- SECのRSS Timezone表記("EST"年間固定Label疑義)・EDGAR Acceptance
  Datetime対Filing Dateの区別、いずれも未読。
- US TreasuryのRSS Replay Bug(2021年)はGovernment RSS全般に対する
  実例として記録したが、Treasury自体は候補として採用していないため
  直接のRegression Testは書いていない(Known Limitationとしてのみ
  記録)。
- `original_article_id`/`translated_from_article_id`/`language_variant`
  を実際に設定する経路(Source側の翻訳関係Metadataの検出方法)は未設計
  (実Adapter実装時の課題として残す、Japan Newsの`updated_at`検出経路が
  未設計であるのと同型のGap)。
- D0057(Backlog #21、ARCHITECTURE_GAP)はこのRoundでも未解決のまま
  維持する。
- `lib.evidence.news.NewsEvent`との統合Layer(Validation Backlog行26)
  はこのRoundでも未着手のまま維持する。
