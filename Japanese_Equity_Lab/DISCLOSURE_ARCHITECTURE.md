# Disclosure Architecture(Phase4B-1、D0045)

TDnet / EDINET / Company IRを将来同じArchitecture上で扱うための、
Source非依存のDisclosure Common Coreを説明する。**このPhase(4B-1)では
実Sourceへ一切接続していない。** 実装は`lib/disclosures/`。

## Core Principle: Document != Event != Claim != Fact about business reality

```
Document publication itself is a fact.        <- Phase4B-1が扱う範囲
Document content requires later extraction/classification.  <- 将来Phase
```

「2026-xx-xx xx:xxにこの会社がこのTitleの文書を公開した」は**FACT**として
扱える(公開されたという事実そのもの)。しかし文書**本文**に書かれている
内容(会社予想・経営陣の見通し・計画・経済状況の説明等)は、公開されたと
いう事実とは別物であり、自動的にFACTへ変換しない:

- **Document** ≠ **Event**(「上方修正が起きた」等のEventはDocumentから
  導出される解釈であり、Phase4B-1では抽出しない)
- **Document** ≠ **Claim**(本文中の会社予想・経営陣見通しは`EvidenceType.
  CLAIM`/`INTERPRETATION`相当であり、`FACT`ではない、`lib.evidence.model.
  EvidenceType`参照)
- **Document** ≠ **Fact about business reality**(「業績が良い」という
  business上の解釈は本文を読んで人間またはAIが判断すべきものであり、
  Documentの存在自体が保証するものではない)

Phase4B-1が保証するのは「公開された」という事実の記録・PIT管理・重複検知
までであり、本文Semantic Extraction(数値抽出・Event分類・Claim抽出・
LLM要約)は将来Phaseへ完全に切り離す。

## Pipeline

```
[将来: TDnet/EDINET/Company IR API/File]
              |
              v (Phase4B-2以降、未実装)
     Immutable Raw Snapshot (lib.snapshot.RawSnapshotStore)
              |
              v  parse_disclosure_payload()  (lib.disclosures.normalize)
      DisclosureDocument + DisclosureAttachment
              |
              +--- DocumentRelationship (確認済みの場合のみ、明示的Basis必須)
              |
              v  disclosures_as_of(decision_at, availability_semantics)
                 (lib.disclosures.view、Set Filter、Latest-winsではない)
              |
              v  disclosure_document_to_evidence()  (lib.disclosures.evidence)
        EvidenceRecord (FACT、公開Metadataのみ、本文解釈なし)
              |
              v  (将来Phase、未実装)
   Claim Extraction / Event Classification / Hypothesis Generation
```

## DisclosureDocument

`lib.disclosures.model.DisclosureDocument`。Source非依存。最低限のField:
`internal_document_id`(**1回の`parse_disclosure_payload()`呼び出し内では
常に一意**。Raw行のIndexから生成するため、同一`Code`/`source_document_id`
を持つ複数行が混在しても衝突しない。**ただし複数回の呼び出しをまたいだ
一意性は保証しない**(pit-auditor Finding、D0045追記)。Phase4B-2以降で
複数Snapshotをまたいで蓄積するStoreを設計する場合は、`retrieved_at`や
`source_snapshot_id`を含めたID生成、またはContent Hashベースの生成方式へ
拡張すること)、`source_document_id`(Provider側ID、UNKNOWN=`None`可)、`entity_id`
(Canonical Entity Registry参照)、`title`、`document_kind`、
`originating_source`/`delivery_provider`(D0042の分離をそのまま継承)、
`market_public_at`/`market_public_at_basis`、`provider_available_at`/
`provider_available_at_basis`、`retrieved_at`、`source_version`(不透明な
Provider側Version識別子、Revision Relationship推測には使わない)、
`raw_snapshot_ref`、`language`、`attachments`。

**Fundamentals(`lib.fundamentals.model.DisclosureEnvelope`)との意図的な
違い**: FundamentalsのEnvelopeは`market_public_at_basis`のみを個別に持ち、
`provider_available_at`は`FundamentalMetric`側の`SourceVersion.
availability_basis`(Revision管理用)としてのみ存在した。Disclosure
Documentでは、`market_public_at`と`provider_available_at`のそれぞれの
確からしさを独立に追跡する必要があるため(本文Revisionの概念とは別に、
Document自体の公開時刻とこのLabでの利用可能時刻がそれぞれ別々の確からしさを
持ちうる)、両方を`DisclosureDocument`自身に持たせている。

## DisclosureAttachment

`lib.disclosures.model.DisclosureAttachment`。Document 1件に対し複数の
Attachment(PDF/XBRL/HTML/CSV/XML/OTHER/UNKNOWN)。Phase4B-1は実Downloadを
行わないため、`availability`は既定で`METADATA_ONLY`(存在は分かるが内容は
未取得)、`content_hash`は通常`None`。`source_locator`はURL等の不透明な
参照文字列として保持するのみで、このLab自身が解決・取得することはない。

## Document Version / Relationship

`lib.disclosures.model.DocumentRelationship`。`CORRECTS`/`RESTATES`/
`REPLACES`/`REFERENCES`/`RELATED_TO`/`UNKNOWN`。**Providerが明示する場合、
または公式Metadataで確認できる場合のみ**設定する。「後から出た文書だから
前を訂正した」という時系列だけからの推測は禁止する。`parse_disclosure_
payload()`はDocumentRelationshipを一切生成しない(構造的な確認は
`13_tests/test_disclosures_normalize.py`の
`test_parse_disclosure_payload_never_creates_relationship_records`/
`test_module_never_references_corrects_or_restates_kind_automatically`参照)。

過去のDisclosureDocumentは新しいDocumentで上書きされない(Append-only)。
`DocumentRelationship`は別のRecordとして両者を結びつけるのみ。

## Forecast Revision != Correction(Fundamentals Phase4Aの原則を継承)

会社予想が100→120へ変わった場合、100は当時有効なDisclosureだったのであり
「誤りだった」わけではない。Correction/Restatementは過去の開示内容
そのものの訂正という別概念であり、公式仕様/Metadataで確認できない限り
両者を同一視しない(`lib.fundamentals.normalize`の`is_correction=False`
固定と同じ原則)。

## PIT / Availability

`market_public_at`(市場公表時刻)と`provider_available_at`(このLabの
Pipelineから利用可能になった時刻)を区別する。`provider_available_at`は
実際の観測ログが無い限り常に`availability_basis=UNKNOWN`とし、
`market_public_at`へFallbackしない(D0043の原則をそのまま継承)。

`disclosures_as_of(documents, decision_at, availability_semantics)`
(`lib.disclosures.view`)は2つのAvailabilitySemanticsを切り替え可能:

- **Market Information Study**(A系統、`AvailabilitySemantics.
  MARKET_PUBLIC_AT`): `market_public_at`を基準にする。
- **Reproducible System Simulation**(B系統、既定、
  `AvailabilitySemantics.PROVIDER_AVAILABLE_AT`): `provider_available_at`
  を基準にする。`availability_basis=UNKNOWN`の文書は既定で除外する
  (`include_unknown_availability=True`で明示的opt-inのみ許容)。

**単純なDate比較は禁止**: 同日でも時刻がdecision_atより後なら除外する
(tz-aware `datetime`同士で比較、`13_tests/test_disclosures_view.py`の
`test_same_day_later_time_document_excluded`参照)。

### Fundamentals `fundamentals_as_of()`との設計上の違い(重要)

Fundamentalsの`FundamentalMetric`は同じ指標の異なる時点の値がSeriesを
構成し、`fundamentals_as_of()`はそのSeriesの「その時点で最新のVersion」を
1件返す(Latest-wins)。DisclosureDocumentはそれぞれが独立した意味を持つ
文書であり、同時に複数の文書が「見えている」状態が正しい。そのため
`disclosures_as_of()`は「Latest-winsで1件返す」のではなく、「decision_at
時点で利用可能な文書の**集合**を返す」(Set Filter)。この違いはPIT安全性
原則を弱めるものではなく、Documentという概念の性質から来る自然な設計選択
である。

## Historical List Is Mutable(Phase4B-2、D0046で発見、一般原則として追記)

**「現在時点でSourceのDocuments Listを取得すること」と「過去のある時点で
実際に観測可能だったDocuments Listを再現すること」は別概念であり、混同
してはならない。**

EDINETのLocal Real Data Validation(2026-08-17)で確認された通り、Disclosure
SourceのDocuments List(一覧API)は、単なる「新しい行の追記」ではなく
**過去日付のRecordそのものが後から書き換わる**ことがある: 縦覧期間満了・
書類の取下げ(withdrawal)・財務局職員による書類情報修正等により、
過去に提出された文書のFieldが後日変化する(例: 縦覧期間満了後、`docID`等の
一部Fieldを残して他のFieldがnullへ更新される)。

したがって、**「`date=2024-05-08`のDocuments Listを2026年に取得する」ことは、
「2024-05-08時点で市場参加者が実際に観測できたDocuments List」とは
同一ではない**。この区別は、単に「未来の情報が見えてしまう」という通常の
Look-ahead Bias(本Labが既に`disclosures_as_of()`等で防いでいるもの)とは
別種のリスクである — 過去日付を指定して取得しているにもかかわらず、
その中身自体が「現在」の状態を反映してしまう。

**この制約への対応方針**:

1. 現在のRetrievalは常に`retrieved_at`(いつ取得したか)を伴う「今の観測」
   として扱い、`decision_at`が過去である場合にそのRetrieval結果を
   その過去時点のUniverseの代替として使わない。
2. Historical Backtestで真にPIT安全なDisclosure Universeが必要な場合は、
   (A) その過去時点で実際に取得・保存したImmutable Raw Snapshotを使うか、
   (B) Historical Point-in-Time Snapshotを保証する別のSourceを使うか、
   のいずれかが必要である。現在のAPIから遡って取得したものだけでは
   代替できない。
3. 将来、日次/定期的にDocuments ListをRaw保存する Forward Collection
   Architecture(継続的なSnapshot蓄積)を検討できるが、これは将来Phaseの
   Scopeであり、Phase4B-2ではSchedulerを実装しない。

この原則はEDINETに限らず、Documents Listを提供するDisclosure Source全般
(TDnet等、将来接続時)に適用しうる一般原則として、ここへ明示的に記録する。

## Entity Registry Integration

Provider Codeを直接Entity IDとして使わず、`lib.sources.entity_registry.
EntityRegistry.resolve(provider_name=..., provider_identifier=...,
as_of=...)`を経由する(PIT-aware、Fundamentals Phase4Aと同じ経路)。

## Evidence Integration

`disclosure_document_to_evidence()`(`lib.disclosures.evidence`)は
「公開された」という事実のみをFACTとして記述する(例:「7203が
『2024年3月期 決算短信』(FINANCIAL_RESULTS)を公開」)。本文の内容は
一切含めない。`EvidenceRelation`(SUPPORTS/CONTRADICTS等)は付与しない
(`EvidenceRecord`自体にRelation Fieldが無い既存Schema設計、D0040)。
`source_authority_class`はSource非依存のこのModuleでは決め打ちせず、
呼び出し側が明示的に指定する(実SourceのAuthority Class、例えばTDnet/
EDINETは`PRIMARY_OFFICIAL`、Company IRは`COMPANY_PRIMARY`は、実接続時に
呼び出し側が判断する)。

**既知の制約(pit-auditor Finding、D0045追記)**: 既存`SourceMetadata`
(`lib.sources.catalog`)には`availability_basis`相当のFieldが無いため、
`document.provider_available_at_basis=UNKNOWN`という情報は
`EvidenceRecord`へ変換した時点で失われる。`disclosures_as_of()`のUNKNOWN
Basis除外という安全側Filterを経由せず、この`EvidenceRecord`を
`lib.evidence.retrieval`の汎用PIT Filterへ直接渡すと、`available_at`
(=`market_public_at`)だけで「利用可能」と誤判定されうる。実際の
Decision/Backtestで使う場合は、必ず`disclosures_as_of()`でPIT Filterした
Documentのみを変換すること。この制約はFundamentals Phase4Aの
`disclosure_metric_to_evidence()`にも同様に存在する既存の設計上の制約で
あり、`EvidenceRecord`/`SourceMetadata`自体への`availability_basis`
追加は将来Phase(実Source接続前)で検討する。

## Deduplication(最小基盤、Phase4B-1)

`lib.disclosures.normalize`の2関数のみ:

- `find_exact_content_duplicate_groups(payload)`: Raw行全体の
  Content Hash(`lib.reproducibility.hash_json_safe`を再利用)が完全一致
  する行をグルーピングする(例: Pagination境界での重複取得の検出)。
- `find_same_source_document_id_signals(documents)`: 同一`source_
  document_id`を持つ複数Documentを候補として検出する。

**Title/PublicDate/Codeだけを見たHeuristic判定は行わない**(この2関数の
入力にTitleは一切含まれない)。TDnet/EDINET/Company IRの同一Eventへの
束ね(Event Clustering)は将来Phaseへ延期。

### Raw Artifact Identity != Document Content Identity(Phase4B-2、D0046追記)

**一般原則**: ZIP/XBRL Package等のContainer形式でDownloadされる
Attachment/Documentについて、「Retrievalで実際に返ってきたRaw bytesの
同一性(Raw Artifact Identity)」と「その中に含まれる実際のDocument内容の
同一性(Document Content Identity)」は別概念であり、混同してはならない。

EDINETのLocal Real Data Validation(2026-08-17)で、同一`docID`・同一
`download_type`を2回Downloadしたところ、ZIP Member(実データ)は完全に
一致したにもかかわらず、outer ZIP自体のbytes/SHA-256は毎回異なった
(ZIP Member自体のTimestampがRetrievalごとに変わっていた)。原因は
断定しない(`OBSERVED_BEHAVIOR`として記録するのみ、`DECISIONS.md` D0046
参照)。

したがって、既存の`find_exact_content_duplicate_groups()`
(Documents ListのJSON行全体をHashする、Container形式ではない)自体は
この問題の影響を受けないが、**Container形式のAttachment/Documentへ
Dedup機能を拡張する場合、単純にRaw bytesのHash一致だけをExact Content
Duplicateの判定基準にしてはならない**。EDINETでは
`lib.disclosures.providers.edinet_zip.compute_canonical_zip_content_hash()`
がContainer Metadata(Timestamp・圧縮方式・Member順序)を除外した
Canonical Content Hashを提供する。

`raw_retrieval_hash`(Raw Artifact Identity)の不一致だけをもって
「Documentが訂正・改版された」と自動推論することも禁止する。少なくとも
1回、原因を断定できない形でContainer側のみの差異(内容は完全一致、
Timestampのみ相違)が実際に観測されている(2026-08-17)。したがって、
Outer Hashが不一致であるという事実だけでは、それがContainer側だけの
差異なのか実際のDocument内容変化なのかを判別できない — 判別が必要な
場合は必ずCanonical Content Hashを使う、というのが論理的な帰結である
(skeptic-reviewer Finding: 「Retrievalごとの差異である可能性が高い」と
いう一般的な確率を1件の観測から主張しない、D0046追記2)。

**既存Common Core(`lib.disclosures.model.DuplicateRelationKind`)は
このPhaseでは変更しない**(最小変更を優先する判断、`DECISIONS.md` D0046
参照)。将来、Container形式のAttachmentに対するDedup/Relationship
Modelingが本格的に必要になった時点で、`EXACT_RAW_ARTIFACT_DUPLICATE`/
`EXACT_CANONICAL_CONTENT_DUPLICATE`のような概念分離を検討する。

## Data Catalog

`build_disclosure_common_core_dataset_descriptor()`
(`lib.disclosures.catalog`)が`DataCapability.DISCLOSURE`配下へ
`implementation_status=FIXTURE_ONLY`として登録する。実Source接続時
(Phase4B-2以降)は、この登録を書き換えるのではなく、Source別の
DatasetDescriptorを別途追加登録すること。

## Offline Reproducibility

`disclosures_as_of()`/`disclosure_document_to_evidence()`はいずれも
外部呼び出しを一切持たない純粋関数(`fundamentals_as_of()`と同じ
Offline-by-construction設計、D0042)。統合Testで、Snapshot保存 →
(Session再起動を模した)再読み込み → 正規化、を2回独立実行して結果が
完全に一致することを確認済み(`13_tests/test_disclosures_integration.py`)。

## Future Event Extraction(将来Phase、未実装)

以下はPhase4B-1のScope外であり、将来Phaseで別途設計する:

- 本文からのClaim/Estimate/Plan抽出
- Forecast Revision Event(`FORECAST_UPWARD_REVISION`等)の自動生成
  (Fundamentals Phase4Aの`§21`と同じ理由で慎重に扱う)
- TDnet/EDINET/Company IRの同一出来事へのEvent Clustering
- News統合(`lib.evidence.news`との接続)
- Hypothesis生成・Skeptic Agent・BUY/SELL判断

## 発行体 / Disclosure System(Venue) / Delivery Provider の三層分離(Phase4B-3、D0047で追記、一般原則)

D0042のOrigin/Delivery分離(`originating_source`/`delivery_provider`)は、
「制度・Venue自体」と「配信経路」が同一Provider内で完結する場合
(EDINETを直接叩く場合等)は2層で十分だったが、TDnet(Phase4B-3、
`TDNET_ARCHITECTURE.md` §1)で以下のように3層へ細分化する必要が生じた:

1. **`publishing_entity`**: 実際に開示を行った主体(上場会社)。
2. **`disclosure_system`**: 制度・Venue自体(TDnet)。
3. **`delivery_provider`**: このLabへ実際にDataを届ける経路(J-Quants API)。

**Delivery Providerが観測した状態(例: J-Quantsが返す`DiscStatus`)を、
Disclosure System(Venue)上の現在の権威ある状態と同一視してはならない。**
Providerの実装挙動とVenueの実態が乖離しうることは、確認が取れるまで
常に想定する。この3層分離は、Delivery ProviderがVenueを直接叩かない
構成を持つ任意のSource(TDnetに限らない)に適用しうる一般原則として、
ここへ明示的に記録する。EDINETのように制度・Venue自体(FSAが運営する
EDINET)と配信経路(EDINET API、同じくFSA提供)が同一主体である場合は、
`disclosure_system`と`delivery_provider`のみが collapse して引き続き
2層(`originating_source=delivery_provider="EDINET"`)のままで良い。

**注意**: この2層への収束は`disclosure_system`と`delivery_provider`
の間でのみ起こるものであり、`publishing_entity`(実際に開示した上場
会社そのもの)は常に別軸のまま残る。EDINETについても、`entity_id`
(発行体識別子)は現時点で未解決(`UNKNOWN`)のままであり
(`DATA_SOURCE_ARCHITECTURE.md`のEDINET行「Entity mapping」参照、
D0046)、2層への収束が発行体識別の解決を意味するわけではない。3層/2層
という区別は「Venueと配信経路が同一か」という軸のみを表し、発行体解決
の状態(常に別途確認が必要)とは独立している。

なお、この一般原則は現時点でTDnet(未確認の候補的裏付けのみ)という
単一の動機事例にのみ基づいており、実際にDelivery ProviderとVenueが
乖離する具体的な確認済み事例はまだ無い(TDnetの`DiscStatus`/`RevNo`
挙動自体が`TDNET_SOURCE_ONBOARDING.md` §3/§8の通り未確認のため)。
将来、別のSourceでも同様の3層分離が必要になった時点で、この一般化の
妥当性を再確認すること。

## 既知の限界(Phase4B-1時点、Phase4B-2でEDINETについて追記、Phase4B-3でTDnetについて追記・D0048で更新)

- Provider-neutralなFixture Schemaのみで検証済み。Company IRの
  Field名・DocKind値は未確認。EDINETは
  Phase4B-2でLocal Real Data Validation完了(D0046、`DATA_SOURCE_
  ARCHITECTURE.md`のEDINET行参照)、ただし`document_kind`Mapping・
  `entity_id`解決・PIT Field反映はいずれも未実装のまま。TDnetは
  D0047時点ではSource Onboarding調査が公式資料アクセスを一切得られず
  Adapter/Normalizerコード自体を実装していなかったが、D0048で
  `EXTERNAL_OFFICIAL_SPEC_VERIFICATION`(ユーザーが別のWeb-access環境
  から確認したと申告した内容)に基づき`lib.disclosures.providers.
  tdnet.TdnetAdapter`・`lib.disclosures.providers.tdnet_normalize`を
  実装した(`market_public_at`は`DiscDate`/`DiscTime`から`EXACT` Basis
  で構築、`entity_id`は既存Code正規化を再利用、`document_kind`は
  `DiscItems`公式Code List未確認のため引き続き`UNKNOWN`)。ただしこの
  申告はClaude自身の一次資料直接確認でも真のLocal Real Data Validation
  でもないため、Source Catalog上は`implementation_status=NOT_
  IMPLEMENTED`のまま維持する(`TDNET_SOURCE_ONBOARDING.md`
  「EXTERNAL_OFFICIAL_SPEC_VERIFICATION」・`DECISIONS.md` D0047/D0048
  参照)。
- `DisclosureDocument.internal_document_id`の生成方式(`f"DOC_{internal_
  code}_{index}"`、Raw行のIndex依存)は、`lib.fundamentals.normalize`の
  `envelope_id`生成(`f"ENV_{internal_code}_{disc_no or index}"`)と同様、
  Raw値(ここでは`source_document_id`)を直接使わずIndexを主に使う設計へ
  修正済み(Phase4B-1開発中に発見: 複数行が同一`source_document_id`を
  共有する場合、Raw値優先の生成方式だと`internal_document_id`が衝突する
  ため)。Fundamentals側の`envelope_id`生成は本Phaseでは意図的に変更して
  いない(Research Logic無変更の制約)。将来、同種の衝突リスクが顕在化
  した場合は個別に確認すること。
