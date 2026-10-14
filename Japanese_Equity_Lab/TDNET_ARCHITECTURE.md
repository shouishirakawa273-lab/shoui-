# TDnet Architecture(Phase4B-3、D0047/D0048)

**現状(2026-08-17時点、D0048追記)**: `lib/disclosures/providers/tdnet.py`
(Adapter)・`lib/disclosures/providers/tdnet_normalize.py`(Normalizer)は
実装済み。ただしこれは`TDNET_SOURCE_ONBOARDING.md`「EXTERNAL_OFFICIAL_
SPEC_VERIFICATION」セクション(ユーザーが別のWeb-access環境から確認したと
申告した内容、Provenance Tag`EXTERNAL_OFFICIAL_SPEC_VERIFICATION`)を
根拠とした実装であり、Claude自身がこのSession内で一次資料をFetchして
確認したものではなく、真の意味でのLocal Real Data Validation(実際に
Add-on契約済みのAPI Keyで呼び出し、Response実物を観測すること)でもない。
それが完了するまでSource Catalog上の`implementation_status`は
`NOT_IMPLEMENTED`のまま、Phase4B-3全体は`CODE_COMPLETE_AWAITING_ADDON_
LOCAL_VALIDATION`のままとする(D0048)。Cursor Retrieval State骨格
(`lib.disclosures.providers.tdnet_cursor.TdnetRetrievalCursorState`)は
D0047時点で先行実装済みだったものをそのまま利用する(Adapterとの接続方法は
`lib.disclosures.providers.tdnet_normalize.extract_retrieval_cursor_fields`
経由、`DisclosureDocument`とは引き続き完全に分離)。

`DISCLOSURE_ARCHITECTURE.md`(Phase4B-1のCommon Core原則)・
`EDINET_SOURCE_ONBOARDING.md`/EDINET関連Decision(Phase4B-2、D0046)の
教訓をすべて継承する。以下はTDnet固有の追加原則(D0047策定、D0048で
実装へ反映済み)。

---

## 1. 三層分離: 発行体 / Disclosure System(Venue) / Delivery Provider

TDnetを扱う際は、単純なOrigin/Delivery分離(D0042)をさらに3層へ分ける:

1. **`publishing_entity` / `claimant`** = 上場会社(実際に開示を行った
   主体)。
2. **`disclosure_system` / `venue`** = TDnet(東証の適時開示制度・
   閲覧サービス)。
3. **`delivery_provider`** = J-Quants API(このLabへ実際にDataを届ける
   経路)。

**TDnet Venue上で「現在」表示される状態と、J-Quants `/v2/td/list`が
返すProvider Stateは同一と仮定しない。** `TDNET_SOURCE_ONBOARDING.md`
「EXTERNAL_OFFICIAL_SPEC_VERIFICATION」セクション(D0048、ユーザーが
別のWeb-access環境から確認したと申告した内容、Claude自身の直接確認・
真のLocal Real Data Validationのいずれでもない)で申告された以下の
挙動は、この区別が必要になりうる典型例:

- TDnet公開閲覧サービス側では、Title訂正・削除State等が実際に画面上
  表示されうる。
- J-Quants側の`/v2/td/list`は、Title訂正がReturnされるDataへ反映
  されない、削除された開示も返り続ける、`DiscStatus`は現在の実装では
  常にnull、`RevNo`は常に1、といった挙動が申告されている(EXTERNAL_
  OFFICIAL_SPEC_VERIFICATION、`TDNET_SOURCE_ONBOARDING.md`該当
  セクション参照 — 真のLocal Real Data Validationでの独立確認は未実施)。

したがって、**「J-Quantsのレコード」==「現在の権威あるTDnet Venue状態」**
という主張は禁止する。「Providerからの観測」(J-Quants経由で何が返って
きたか)と「Venue State」(TDnet上で実際に何が起きているか)は別の
概念として明確に分離して扱うこと。

## 2. Provider宣言Schema vs 現在の実装挙動

`DiscStatus`/`RevNo`のようなFieldについては、以下の2つを別々に保持・
文書化する:

- **Provider-declared schema semantics**: 公式仕様がこのFieldに対して
  定義しているTake得る値の範囲・意味(例: `DiscStatus`が
  null/revision/delete等の状態を表しうる、`RevNo`が1〜99を取りうる、
  という仕様上の定義)。
- **Current implementation behavior**: 実際に観測される、現在時点での
  Runtime挙動(例: 現在は常にnull・常に1、EXTERNAL_OFFICIAL_SPEC_
  VERIFICATIONとして申告済み、D0048。真のLocal Real Data Validation
  での独立確認は未実施)。

**現在の実装挙動をLifecycle判定に使用しない**(D0048でこの挙動主張
自体はユーザー申告として記録されたが、これはClaude自身の直接確認でも
真のLocal Real Data Validationでもない — たとえ将来Local Validationで
独立に確認できたとしても、それは「現在の実装挙動」であって「Schemaが
将来もそうあり続けることの保証」ではない)。

**Schema Evolution追跡**: 将来Providerの実装が変わった場合に、過去に
既に正規化済みのRecordをSilentに遡及的に再解釈しない。最低限、以下の
Versioning情報でSchema変化を追跡できるようにする(将来Normalizer実装時):

- `provider_schema_version`: Provider側が宣言するSchema定義のVersion
  (未確認の場合は`UNKNOWN`)。
- `normalizer_version`: このLab側のNormalizer実装Version
  (`lib.disclosures.model.NORMALIZER_VERSION`と同じ命名規約、EDINETの
  `EDINET_NORMALIZER_VERSION`と同様のPattern)。
- `observed_behavior_documented_at`: 「現在の実装挙動」をいつ観測・
  文書化したか(日付)。

これにより、「2026年8月時点でRevNoは常に1だった」という観測記録と、
「2027年以降Providerの実装が変わりRevNoが実際に意味を持つようになった」
という将来の変化を、明確に別のVersionとして区別できる設計にする。

## 3. Historical Market Time vs Historical Provider Time

Phase4A(D0043)・Phase4B-1(D0045)から継続する原則を、TDnetの文脈で
再確認する:

- **Market Information Study(A系統)**: `DiscDate`+`DiscTime`の
  公式TDnet意味論はEXTERNAL_OFFICIAL_SPEC_VERIFICATION(D0048、
  `TDNET_SOURCE_ONBOARDING.md`「EXTERNAL_OFFICIAL_SPEC_VERIFICATION」
  §7)として申告され、`market_public_at`の値としては使用しているが、
  この確認根拠が又聞きであるため`AvailabilityBasis`は`EXACT`ではなく
  `UNKNOWN`のまま維持する(`tdnet_normalize.py`実装、`disclosures_
  as_of()`の既定安全側除外がそのまま適用される)。真のLocal Real Data
  Validationで独立に確認できた時点で`EXACT`への昇格を検討する。
- **Reproducible System Simulation(B系統)**: 今日取得した5年分の
  Bulk/List Dataは、**当時実際にJ-Quants経由で観測できたSnapshotとは
  異なる**。現在のBulk Retrievalから過去の`provider_available_at`を
  復元することは禁止する。B系統で使えるのは、実際にその時点で保存された
  Retrieval/Cursor Snapshotのみ。

将来、Forward Collection(定期的な`/v2/td/list` + Cursorによる差分取得を
継続的にImmutable Snapshotとして蓄積する仕組み)を行えば、
Provider-observed Timelineを将来に向けて蓄積できるが、**Schedulerは
このPhaseでは実装しない**(Cursor State Modelの骨格のみ用意、
§4参照)。

## 4. CursorはRetrieval Stateのままであり続ける

Cursorは以下のいずれでもない:

- Disclosure Timestamp
- `market_public_at`
- `provider_available_at`

あくまでIncremental/Differential Retrievalの進捗を表すState(「どこまで
取得したか」)である。Cursor Payloadをたとえ何らかの方法でDecodeできた
としても、その内部値からAvailability Timestampを推測することを禁止する。
`pagination_key`(同一Queryの残りページ取得)とも別概念であり、両者は
同時指定不可と申告されている(EXTERNAL_OFFICIAL_SPEC_VERIFICATION、
D0048)。

Cursor Stateを保持する場合は、`lib.disclosures.providers.tdnet_cursor.
TdnetRetrievalCursorState`(実装済み、Adapter未接続)のように、
`retrieved_at`・`query_date`・`cursor_value`・`previous_cursor`・
`response_snapshot_hash`から成るRetrieval Provenanceとして保持し、
`DisclosureDocument`/`AvailabilityBasis`とは完全に分離する。

## 5. Ephemeral File URL Safety

`/v2/td/files`・`/v2/td/bulk`が返すDownload URLは15分で失効すると
申告されている(EXTERNAL_OFFICIAL_SPEC_VERIFICATION、D0048、
`TDNET_SOURCE_ONBOARDING.md`「EXTERNAL_OFFICIAL_SPEC_VERIFICATION」
§5/§6参照 — Claude自身の直接確認・真のLocal Real Data Validationでの
独立確認は未実施)。したがって、URLを:

- `canonical_source_locator`
- `permanent_attachment_url`

として保存・長期依存してはならない。

**長期Provenanceの中心は以下であるべき**(URLではなく):

- `discNo`(またはそれに相当する確認済み識別子)
- Document Role(Full PDF / Summary PDF / XBRL等、公式Code確認後)
- `delivery_provider`("J-Quants")
- `retrieved_at`
- Raw File Hash(SHA-256、EDINET Phase4B-2の`raw_retrieval_hash`と
  同じ設計、`DISCLOSURE_ARCHITECTURE.md`「Raw Artifact Identity !=
  Document Content Identity」原則を継承)
- Raw Snapshot Reference(`RawSnapshotStore`のSnapshot ID)

URLが必要な場合も、以下のようなTransient Metadataとしてのみ扱う
(将来Adapter実装時の設計指針):

- `ephemeral_download_url`
- `url_observed_at`
- `expiry_semantics`(既知であれば)

**Offline ReplayはURL無しで成立すること** — 保存済みRaw Snapshotから
Normalize・As-of View構築・Evidence変換のすべてが、外部URLへの
再アクセス無しに完結する設計にする(D0042 Offline原則の継続)。

## 6. Document分類とEvent方向判定の分離

`DiscItems`やTitleから、以下を**このPhaseでは**一切生成しない:

- 業績予想の上方修正/下方修正
- Positive/Negative Catalyst
- BUY/SELL

例えば、あるDocumentの`DiscItems`(公式Code List確認後)が「業績予想
修正」に対応するCategoryだと判明したとしても、それは「Document種別が
確認できた」ことを意味するだけであり、「上方修正か下方修正か」という
Revision Directionの判定は、本文の実際の数値比較を要する別のPhaseの
仕事である。

**Document Classification(このDocumentは何の種類か) != Event
Interpretation(何が起きたと解釈すべきか)。** Phase4B-1のCore Principle
(「Document != Event != Claim」)をTDnetの文脈で再確認する。

## 7. Real Validation Completion基準(将来、Add-on利用可能時)

**現状(D0048)**: `TdnetAdapter`(Raw Fetch)・`tdnet_normalize`
(Normalize)は実装済みだが、いずれも`EXTERNAL_OFFICIAL_SPEC_VERIFICATION`
(ユーザー申告)に基づくものであり、以下のいずれもまだ満たしていない。

TDnet Add-onが実際に利用可能であることが確認できた場合、Phase4B-3を
`COMPLETE`とするには最低限、以下がすべて必要:

1. 実際の`/v2/td/list`呼び出し成功(Claude自身ではなく、ユーザーの
   ローカル環境から実際のAdd-on契約済みAPI Keyで — `TDNET_LOCAL_
   VALIDATION_GUIDE.md`参照)
2. 実際の`/v2/td/files`呼び出し成功
3. 実際に1件のFile Downloadに成功
4. Content-Type観測
5. Byte Length観測
6. Raw SHA-256
7. File Signature/Magic Byte観測
8. Offline Replay確認
9. pit-auditor Review
10. skeptic-reviewer Review

`/v2/td/bulk`の実Downloadは必須ではない — 公式仕様のみ確認できれば
`SPEC_CLAIM_ONLY`として明示した上で`COMPLETE`にできる(EDINETの
`EdinetDownloadType`でtype=2〜5をSPEC_CLAIM_ONLYとして扱った前例と同じ
設計判断)。

**BASE_URL(`https://api.jquants.com/v2`共有)・Response Envelope形状
(`{"data": [...], "cursor": ..., "pagination_key": ...}`)もMain Claudeに
よる推論であり、Local Real Data Validationで最優先に確認すべき項目に
含める**(`TDNET_LOCAL_VALIDATION_GUIDE.md`参照、ユーザー申告そのもの
ではないため)。

Add-onが利用可能と確認できない場合は、`CODE_COMPLETE_AWAITING_ADDON_
LOCAL_VALIDATION`として正常に停止する(D0047/D0048参照)。
