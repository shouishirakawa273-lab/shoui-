# TDnet Source Onboarding Report(Phase4B-3)— J-Quants API V2 TDnet/適時開示情報アドオン

作成: `data-source-researcher` subagent(`source-onboarding` skill)、2026-08-17。
Main Claudeによる直接の追記なし(subagentの調査結果をそのまま保存)。
Read-only調査。Connector/Adapterコードは一切書いていない。APIキーの要求・
取り扱いも行っていない。

**下記§0〜Bottom lineは、本セッション(Blocked状態)で作成された当初の
調査結果であり、そのまま履歴として保持する。その後、別のRoundで
`EXTERNAL_OFFICIAL_SPEC_VERIFICATION`(下記新設セクション参照)が追加され、
実装のGround Truthとして使用されているのはそちらである。** 以下の
`§0`〜`Bottom line`部分の「未確認」という記述は、あくまで**このセッション
自身が到達できなかった**ことを表しており、後述のExternal Verificationに
よって多くの項目が別の経路で確認されたことと矛盾しない(両者は別物として
併記する)。

---

## EXTERNAL_OFFICIAL_SPEC_VERIFICATION(2026-08-17、別Round追記)

**Provenance(重要、必ず最初に読むこと)**: 以下の内容は、本セッション
(Claude Code、このRepository/Session自身)が`jpx-jquants.com`・
`jpx.gitbook.io`・`www.jpx.co.jp`へ直接接続して確認したものでは**ない**。
ユーザーが、別のWeb-access環境(本セッションとは異なる、Egress制限の無い
環境)から2026-08-17時点のJ-Quants/JPX公式ページを直接確認したとして、
その結果をこのSessionへ報告した内容をそのまま記録したものである。

- Provenance Tag: `USER_SUPPLIED_OFFICIAL_VERIFICATION` /
  `EXTERNAL_OFFICIAL_SPEC_VERIFICATION`(ユーザー指示により、この2つの
  タグを同義として扱う)。
- **`data-source-researcher`(`WebSearch`/`WebFetch`)がこのSession内で
  独自に到達・確認したものではない。** 上記§0の`SEARCH-SNIPPET-DERIVED
  (UNVERIFIED)`という確度クラスとは異なる、別の確度クラスとして扱う:
  「ユーザーが実際に一次資料ページを閲覧して確認したと申告した内容」
  であり、「Claude自身が一次資料を直接Fetchして確認した」(EDINETの
  `EdinetAdapter`がユーザーのローカル環境からの実際の疎通で確認したのと
  同種の確度)とも異なる。この報告内容自体をClaude/このSessionが独立に
  検証する手段は無い(本セッションからは引き続き該当Hostへ接続できない)。
- checked_at: 2026-08-17(ユーザー申告)。

### 確認済み(ユーザー申告)Source URL一覧

- J-Quants API Reference:
  - `https://jpx-jquants.com/en/spec/td-list`
  - `https://jpx-jquants.com/en/spec/td-files`
  - `https://jpx-jquants.com/en/spec/td-bulk`
  - `https://jpx-jquants.com/en/spec/rate-limits`
- JPX TDnet overview: `https://www.jpx.co.jp/equities/listing/disclosure/tdnet/index.html`
- JPX 2026-05-18 J-Quants TDnet Add-on release:
  `https://www.jpx.co.jp/corporate/news/news-releases/6020/20260518-01.html`

### 1. Product Identity

対象は「J-Quants API」(個人向け)の「TDnet/Company Disclosure Timely
Disclosure Add-on」であり、**J-Quants Proではない**(§0で指摘した製品
混同リスクが、ユーザー申告によりこの方向で解消された)。

JPX公式発表(ユーザー申告): 2026-05-18提供開始、Light plan以上、月額
11,000円(税込)、個人投資家向け、過去5年、API、CSV bulk download。

### 2. `GET /v2/td/list`(ユーザー申告)

- 認証: `x-api-key`(既存`JQuantsAdapter`と同一Header、`jquants.py`の
  既存Auth/Session Patternを再利用できる)。
- TimelyDisclosure add-on必須。
- Historical availability: 過去5年。
- 公式Response Field(ユーザー申告): `DiscNo`/`Code`/`Name`/`DiscDate`/
  `DiscTime`/`Title`/`DiscStatus`/`RevNo`/`DiscItems`/`Docs`/`cursor`/
  `pagination_key`。
- **現在の実装挙動(ユーザー申告、Provider-declared Schemaとは別軸)**:
  - Title訂正はReturnされるAPI Dataに反映**されない**。
  - 開示File自体が訂正された場合、新しい`DiscNo`が発行され、**新規
    Recordとして扱われる**(既存`DiscNo`が更新されるわけではない)。
  - 削除された開示も返り続ける。
  - `DiscStatus`は現在常にnull。
  - `RevNo`は現在常に1。
- **Provider宣言Schema意味論(ユーザー申告、Current Implementation
  Behaviorとは別軸、`TDNET_ARCHITECTURE.md` §2の設計をそのまま適用)**:
  - `DiscStatus`: null=新規、`revision`=訂正、`delete`=削除。
  - `RevNo`: 1〜99。
  - **Current Implementation BehaviorとSchema-Declared Semanticsは
    区別したまま保持し続けること**(ユーザー自身の指示、以下Normalizer
    実装で厳密に踏襲する)。

### 3. Query Semantics(ユーザー申告)

- `date`または`code`のいずれかが必須。
- `code`指定: 過去5年。
- `code` + `from` + `to`: 期間クエリ。
- 4桁Code: ProviderがTrailing `0`を付与する(既存`lib.data_sources.
  ticker_codes.normalize_provider_code_to_internal()`の5桁+末尾ゼロ
  パディング規約[D0036、`Code`の実データ確認]とパターンが一致 — 直接
  再利用可能、重複した正規化ロジックを新設しない)。Raw Provider Codeを
  破壊しないこと(既存原則をそのまま踏襲)。
- `discItems`によるFilterが存在する(具体的なCode List・意味論は未申告
  — このAdapterでは`discItems`をOpaqueなRaw Query Parameterとしてのみ
  扱い、値の意味論をこのSessionが解釈・Mapping Tableへ組み込むことは
  しない)。

### 4. Cursor / Pagination(ユーザー申告)

- `cursor`: 当日Dataに対するReal-time差分取得用のRetrieval State。
- `pagination_key`: Pagination State(既存`JQuantsAdapter._get_all_
  pages`と同じ意味論)。
- **両者は同時指定不可**(`TdnetRetrievalCursorState`の設計[Phase4B-3
  第1Round]がこの制約を前提に構築されていたこととも整合)。
- `cursor`を以下のいずれとしても解釈しないこと(ユーザー明示の指示、
  `TDNET_ARCHITECTURE.md` §4の既存原則をそのまま踏襲):
  - `market_public_at`
  - `provider_available_at`
  - Disclosure Timestamp

### 5. `GET /v2/td/files`(ユーザー申告)

- 認証: `x-api-key`。
- `discNo`必須。
- `docs`任意: `g`=Full PDF、`s`=Summary PDF、`x`=XBRL(§0/§10で未確認
  だった短縮Codeが、この経路で確認された)。
- Response Field: `discNo`・`files.pdf`・`files.summaryPdf`・
  `files.xbrl`。
- 署名付きDownload URLは**15分で失効**(§0/§11で確認できなかった具体的
  数字が、この経路で確認された)。**したがってEphemeral URLを恒久的な
  Canonical Locatorとしてはならない**(`TDNET_ARCHITECTURE.md` §5の
  既存原則をそのまま踏襲、以下の実装でも厳密に遵守する)。

### 6. `GET /v2/td/bulk`(ユーザー申告)

- 認証: `x-api-key`。
- Response: `lastUpdated`・`url`。
- CSV: gzip圧縮。
- Coverage: 過去5年。
- URL: 15分で失効。
- CSV Field: `DiscNo`/`Code`/`Name`/`DiscDate`/`DiscTime`/`Title`/
  `DiscStatus`/`RevNo`/`DiscItems`/`Docs`。
- CSV差異: `DiscItems`・`Docs`はPipe(`|`)区切り(JSON表現[List経由]とは
  異なるEncoding)。
- **`lastUpdated` != Disclosure Time**(このField自体をPIT用Timestampと
  して扱わないこと、ユーザー明示の指示)。

### 7. TDnet Market Public Time(ユーザー申告、PIT上最重要)

JPX公式TDnet Documentation(ユーザー申告)は、TDnet経由で情報が開示
された時、同じ会社情報がTDnetの開示Timeに、適時開示情報閲覧サービス上で
同時に公衆縦覧可能になることを確認しているという。公衆縦覧という措置は、
その情報がそこへ掲載された時点で完了する。

**したがって、Mapping意味論をこのDocumentへ明示した上で**、
`DiscDate` + `DiscTime`(Asia/Tokyo)を`market_public_at`として
Market Information Study(A系統)に使用できる(下記`tdnet_normalize.py`
で`AvailabilityBasis.EXACT`として実装)。

**ただし**: `market_public_at` != J-Quants `provider_available_at`。
過去のJ-Quants Provider Availability(このLabが当時実際にJ-Quants経由で
取得可能だった時刻)は、実際に観測されない限り`UNKNOWN`のままとする —
Fallbackは行わない(`TDNET_ARCHITECTURE.md` §3「Historical Market Time
vs Historical Provider Time」の既存原則をそのまま踏襲)。

### 8. Rate Limit(ユーザー申告)

TDnet/Company Disclosure Add-on APIは100リクエスト/分(通常Plan Rate
Limitとは独立)。429はBack offする。

### 9. Provenance再確認(重要、繰り返し明記する)

上記1〜8は、いずれも本Repository/Sessionが自ら`jpx-jquants.com`等へ
接続して確認したものではない。`TDNET_SOURCE_ONBOARDING.md`の§0〜Bottom
lineに記録されたBlocked状態(egress遮断)は、本セッション自身に関する
限り現在も有効なままである。実装コード(`lib/disclosures/providers/
tdnet.py`・`tdnet_normalize.py`)は、このセクション(ユーザー申告の
External Official Verification)を根拠に構築するが、Field名・Endpoint
名・挙動の記述箇所にはすべて`EXTERNAL_OFFICIAL_SPEC_VERIFICATION`
(または同義の`USER_SUPPLIED_OFFICIAL_VERIFICATION`)という出典Tagを
明示し、Claude自身がFetchして確認した(EDINETの`EdinetAdapter`のように
ユーザーのローカル環境からの実際のHTTP疎通で確認された)ものとは区別
して記録する。**真の意味でのLocal Real Data Validation(実際にAdd-on
契約済みのAPI Keyで`/v2/td/list`等を呼び出し、Response実物を観測する
こと)はまだ行われていない** — それが行われるまで、Phase4B-3全体の
Completion Statusは`CODE_COMPLETE_AWAITING_ADDON_LOCAL_VALIDATION`の
ままとする。

---

## 0. Environment / Access Finding(まず読むこと)

**本セッションから、このTopicにとってのほぼ全ての一次/二次資料候補への
Outbound Egressがブロックされた**(前回EDINETセッションからの類推ではなく、
今回改めて直接試行して確認)。

Blocked(`EGRESS_BLOCKED`、今回改めて確認済み。Main Claude自身も`curl`で
`jpx-jquants.com`・`jpx.gitbook.io`への独立した再現確認済み、いずれも
`CONNECT tunnel failed, 403`):

- `https://www.jpx.co.jp/corporate/news/news-releases/6020/20260518-01.html`
  (TDnetアドオンを発表したと思われるJPXプレスリリース)
- `https://jpx-jquants.com/*`(公式「J-Quants APIリファレンス」ドキュメント
  ホスト — `/ja/spec/release`・`/ja/spec/data-spec`・`/ja/spec/bulk`・
  `/ja/spec/bulk-list`・`/ja/spec/rate-limits`・`/ja/spec/response-status`・
  `/ja/help/*`・`/termsofservice`等、すべてこの1ドメイン配下でブロック)
- `https://jpx.gitbook.io/*`(`j-quants-ja`[個人向けAPIリファレンス]・
  `j-quants-pro-ja`[別製品「J-Quants Pro」]の両方 — 下記の製品混同に関する
  重要な注記参照)
- `https://x.com/JPX_official/...`(JPX公式アカウントの告知投稿)
- `https://qiita.com/j_quants/items/7f59b0e9e34d023d0cc6`(JPX運営の公式
  Qiitaアカウント自身によるTDnet解説記事 — JPX/J-Quants公式アカウントが
  書いたものであってもHost自体がブロックされている)
- `zenn.dev`、`note.com`、`web.archive.org`、`*.translate.goog`、
  `webcache.googleusercontent.com`

到達できたHost:
- `github.com` / `raw.githubusercontent.com`(`J-Quants` GitHub Organization
  のリポジトリ群)
- `pypi.org`(`jquants-api-client`パッケージページ)

`/root/.ccr/README.md`の方針により、403/407系のegress拒否は組織ポリシーで
あり、再試行・回避は試みていない。

**結果として**: 公式J-Quants APIリファレンス(`jpx-jquants.com`)・公式
GitBook APIドキュメント(`jpx.gitbook.io`)・JPX自身のプレスリリースの
いずれも直接読むことができなかった。以下の内容は`WebSearch`が生成した
要約スニペットのみに基づいており、生のページ本文は一度も見ていない。
これはEDINET Onboarding Report(`EDINET_SOURCE_ONBOARDING.md`)と同じ
`SEARCH-SNIPPET-DERIVED (UNVERIFIED)`という確度クラスであり、通常の
二次資料引用よりさらに一段低い確度である。

**さらに今回固有の新たなリスクを追記する**: `WebSearch`のQuery文字列自体に
タスク側で仮定したEndpoint名/Field名(例: `"/v2/td/list"`)をそのまま
含めたところ、それらの文字列を「確認」するかのような回答がToolから返って
きた場合があった。これはSearch Toolが実在するページのTitle/Snippetを本当に
見つけている可能性(=真の裏付け)とも、確証Bias的な失敗モード(=自分が
入れた文字列がそのまま返ってくる)とも整合するため、いずれのケースも
「Confirmed」へは昇格させていない。

実際にある程度の忠実さで読めたのはGitHub上の2ファイルのみであり(§1参照)、
弱い**否定的**Evidenceとしてのみ使った。

**推奨(EDINETの前例を踏襲)**: 実際にTDnet Adapter/Normalizerを実装する
前に、`jpx-jquants.com`・`jpx.gitbook.io`へ実際に到達できる環境
(=ユーザーのローカル環境)から、このChecklistを再実行または少なくとも
スポットチェックする必要がある(EDINETに対する`EDINET_LOCAL_VALIDATION_
GUIDE.md`と同じ役割)。それまでは、以下すべての項目は`UNKNOWN`または
`SEARCH-SNIPPET-DERIVED (UNVERIFIED)` / `REQUIRES_LOCAL_VALIDATION`とし、
いずれも実装のGround Truthとしてコード化しない。

### 調査中に判明した重要な混同リスク(以下を読む前に必ず確認)

検索結果には、いずれも「TDnet」という文字列を含む**2つの異なる製品**が
混在して出現した。これらを混同してはならない:

1. **「J-Quants API」(個人向け)** — `lib/data_sources/jquants.py`が
   既に接続している製品と同じもの(Light/Standard/Premiumプラン、
   `x-api-key`認証、`api.jquants.com`)。タスクで指定された「TDnet/
   適時開示情報アドオン」(月額11,000円、Lightプラン以上への追加機能)は
   **この製品**の機能とされている。DocumentホストはおそらくJPX-jquants.
   com / jpx.gitbook.io/j-quants-ja。
2. **「J-Quants Pro」(法人向け)** — 検索結果は「法人向け」と明記する、
   **別契約の**Enterprise製品(API・SFTP・**Snowflake**経由で配信)で
   あり、独自のDocumentホスト`jpx.gitbook.io/j-quants-pro-ja`を持つ。
   「TDnet on Snowflake」(`/snowflake/timely_disclosure`)というPage
   タイトルや、`jpx.gitbook.io/j-quants-pro/api-reference/`配下の
   `/markets/share_buyback_tdnet`というREST Endpointが検索結果に出現した。

複数の検索結果が、同じQueryの下で両方のDocument Treeからの引用を混在
させていた。**したがって、以下で議論するEndpoint名/Field名
(`/v2/td/list`等)が、実際に製品(1)に属するものなのか、それとも
製品(2)のDocumentが混入した結果なのかを確認できていない**
(いずれのDocument Treeも直接読んでいないため)。これはLocal
Validationが最初に解決すべき、実務上重要な曖昧性である — あるField/
Endpoint主張がどちらの製品のDocumentationに由来するのかを確認してから
信頼すること。

---

## 1. Identity & Access

| 項目 | 内容 |
| --- | --- |
| Originating Source | TDnet(東京証券取引所の適時開示情報伝達システム)、JPX運営。 |
| Delivery Provider | J-Quants API(株式会社JPX総研)、具体的には個人向けJ-Quants APIの「TDnet/適時開示情報アドオン」— **J-Quants Proではない**(上記の製品混同注記参照)。`originating_source="TDnet"`、`delivery_provider="J-Quants"`(D0042/D0043のOrigin/Delivery分離パターンを踏襲、`DATA_SOURCE_ARCHITECTURE.md`の既存TDnet行が既に想定していた形と一致)。 |
| 公式ドキュメントURL | `SEARCH-SNIPPET-DERIVED (UNVERIFIED)`: `https://jpx-jquants.com/ja/spec/*`(APIリファレンスサイト)、および`https://jpx.gitbook.io/j-quants-ja/api-reference`の可能性(同一Documentのミラーか否か不明)。JPXプレスリリース: `https://www.jpx.co.jp/corporate/news/news-releases/6020/20260518-01.html`。いずれも直接未読。`REQUIRES_LOCAL_VALIDATION`。 |
| APIバージョン | 既存`JQuantsAdapter`が対象とするV2と同じである可能性が高い(アドオンは同じ製品の拡張として説明されているため)が、この主張は一次資料から読んだものではない。`UNKNOWN`。 |
| 認証方式 | **`x-api-key`と同一である確認は取れていない。** 複数の`WebSearch`要約はTDnet Endpointが同じJ-Quants API V2製品の一部であると説明しており、それは同じHeaderの再利用と整合的だが、TDnetアドオンEndpointが同じHeaderを使うと明示的に述べたSource(未検証のスニペットレベルでも)は見つからなかった。`UNKNOWN`、`REQUIRES_LOCAL_VALIDATION`。`jquants.py`の既存Auth/Session/Throttleパターンを再利用する強いArchitecture上の動機はあるが、それは「事実として書くべきもの」ではなく「ローカルでTestすべき作業仮説」として扱うべき。 |
| プラン/アドオン要件・コスト | `SEARCH-SNIPPET-DERIVED (UNVERIFIED)`だが、複数の独立したQuery/Snippet(JPXプレスリリースのTitle、JPX運営Qiita記事のTitle、複数の`WebSearch`要約)にまたがって裏付けあり: 個人向け「J-Quants API」(J-Quants Proではない)へのアドオン、**Lightプラン以上が必要**、**月額11,000円(税込)**、**2026-05-18**開始。タスク側の想定と整合的。それでも一次ページからの読み取りではないため、正確な価格/日付を課金目的で信頼する前に`REQUIRES_LOCAL_VALIDATION`。 |
| Lightプランキーがアドオン無しでアクセスした際のエラー応答 | `UNKNOWN`。ある`WebSearch`要約は、スニペット中の「プランエラー」という語句からの推測として「403 プランエラー」を挙げたが、実際のResponse Body・Status Code意味論・単一の明確なCode/Shapeを提示できなかった。これはまさに、防御的に推測でコード化してはならない類のClaimである(EDINETの`metadata.status`がHTTP 200内に埋め込まれていた驚き、D0046と同種のリスク — ここで誤った仮定[`raise_for_status()`だけで検知できると仮定する等]をすると、「アドオン無し」を「今日はDataが無い」と静かに誤分類しかねない)。`REQUIRES_LOCAL_VALIDATION`、優先度高。 |
| ライセンス/再配布制限 | `SEARCH-SNIPPET-DERIVED (UNVERIFIED)`、TDnetアドオン固有ではない一般的なJ-Quants API利用規約: 取得した生Dataの再配布/直接共有は禁止と説明され、派生した分析(チャート/レポート)の共有は許可されると説明され、契約解約後のData削除が必要と説明され、「継続的/反復的」な公開再配布(例: 定期的なYouTube Data配信)は個人利用に該当しないと説明されている。いずれも`jpx-jquants.com/termsofservice`から直接読んだものではない。TDnetアドオンのPDF/XBRL添付ファイルが同じ利用規約下にあるのか、それともより厳格な規約下にあるのか(TDnet文書自体が著作権のある開示書類であるため)は`UNKNOWN`。`RawSnapshotStore`へAttachment bytesを長期保存する前に`REQUIRES_LOCAL_VALIDATION`。 |

---

## 2. Coverage & Availability

| 項目 | 内容 |
| --- | --- |
| 過去データ範囲 | `SEARCH-SNIPPET-DERIVED (UNVERIFIED)`、繰り返し一貫して: アドオン経由で適時開示Index Dataの「過去5年」。Rolling 5年Windowなのか、アドオン開始日(2026-05-18)からの固定Windowなのかは`UNKNOWN`。 |
| 現在の可用性/更新Timing | `SEARCH-SNIPPET-DERIVED (UNVERIFIED)`: TDnet開示後「数分〜数十分(ピーク時最大約1時間程度)」でのIntraday配信と説明され、基本J-Quants製品の日次Batch Cadenceと対比されている。これは`provider_available_at`意味論にとって最も実務上重要なClaimだが、一次資料から読んだものではない — `REQUIRES_LOCAL_VALIDATION`、確認済みAvailability Basisとしてコード化不可。 |
| レート制限(アドオン固有) | `SEARCH-SNIPPET-DERIVED (UNVERIFIED)`: 「100リクエスト/分」、List EndpointとFiles Endpointで共有されると説明。基本プランの60req/分(D0039)の**上に追加**なのか、**それを置き換える**のか、**独立**なのかは**未確認** — つまり`/v2/td/*`呼び出しが`jquants.py`の既存Plan全体のThrottle(`_RATE_LIMIT_INTERVAL_SEC`)を消費するのか、それとも`/v2/fins/summary`について検討された(D0043)のと同様独自のThrottleが必要なのかは不明。`UNKNOWN`、`REQUIRES_LOCAL_VALIDATION`。 |
| Pagination機構 | `SEARCH-SNIPPET-DERIVED (UNVERIFIED)`: 2つの別々の、相互排他的な機構として説明 — `pagination_key`(同一Queryの残りを取得し続ける、`JQuantsAdapter._get_all_pages`の既存`pagination_key`使用法と同じ意味論)と`cursor`(前回Cursor以降新規追加された開示のみを取得、当日Differential Pollingのため)。ある要約は「cursorとpagination_keyは同時指定不可」と明示していたが、これは未検証のParaphraseであり、読んだSpec文そのものではない。`REQUIRES_LOCAL_VALIDATION`。 |
| Bulk/File Download可用性 | `SEARCH-SNIPPET-DERIVED (UNVERIFIED)`: 別のBulk Endpointが存在すると説明(gzip CSV、Index Data「5年分」)、Cursor-based Incremental Pollingへ切り替える前のInitial Seedとして位置づけられている。Format/圧縮/Coverage Claimは未確認。 |

---

## 3. Revision & Correction Semantics(タスク上最重要項目 — 未解決のまま扱う)

**タスクの(a)/(b)/(c)いずれのClaimも、実際に読めたどのSourceからも
確認/反証できなかった。** `WebSearch`合成結果のみであり、その一部は
Claim本文そのものを含むQueryから生成された(§0のBiasリスク参照):

- **(a) 訂正された開示が新しい`DiscNo`を持つ独立したRecordになる** —
  これを明示するSourceは、公式・非公式問わず一件も見つからなかった。
  `UNKNOWN`。
- **(b) 削除/取下げられた開示もAPIから返り続ける** — この点に触れる
  Sourceは一件も見つからなかった。`UNKNOWN`。
- **(c) `DiscStatus`は現在の実装では常にnull、`RevNo`は常に1** —
  この具体的で反証可能なClaimは、到達できたどのSourceにも**見つから
  なかった**。この点に触れるChangelog/Release Noteのエントリも
  見つけられなかった。`UNKNOWN`。

`lib/disclosures/model.py`の明示的なRule(「`DocumentRelationship`は、
Providerが明示するか、公式Metadataで確認できる場合のみ設定する…
時系列だけからの推測は禁止する」)と、EDINETに対する本プロジェクトの
既存の前例(`parentDocID`を`CORRECTS`の意味だと仮定せず`UNKNOWN`のまま
残した)を踏まえ、**(a)/(b)/(c)のいずれも、実際のCorrected/Withdrawn
Disclosureを直接観測して確認できるまで、Normalizerへ組み込んではならない**
し、`DiscNo`/`RevNo`から`DocumentRelationshipKind.CORRECTS`Recordを
自動生成してはならない(EDINETのLocal Real Data Validationが
`DocumentRelationship`に触れる前に必要だったのと同じ理由)。
`REQUIRES_LOCAL_VALIDATION`であり、特に実際のCorrected/Withdrawn
Disclosureを実環境で観測する必要がある(Schema Table を読むだけでは
(c)で主張されているRuntime挙動は証明されないため)。

---

## 4. `/v2/td/list` Query Semantics

すべて`SEARCH-SNIPPET-DERIVED (UNVERIFIED)`、Sourceからの直接読み取りなし:

- Endpoint存在/名称: `/v2/td/list`・`/v2/td/files`・`/v2/td/bulk`として
  繰り返し報告されたが、これらの文字列を一次ページから確認したことは
  一度もない — `WebSearch`の合成回答Text内でのみ見た。少なくとも1件は
  自分のQuery文字列自体に候補Endpoint名を含めていた。厳密には`UNKNOWN`
  (自分でQuery文字列を生成し、それが確認されて返ってきたものは
  独立したEvidenceとして扱えない)。
- 必須/任意パラメータ(`date` vs `code`、`from`/`to`との組み合わせ可否):
  `UNKNOWN`。実際の必須パラメータRuleを示すSourceは見つからなかった。
- `code`指定時の5年Coverage Window: §2と同じ「5年」という数字、出所が
  Bulk EndpointなのかList EndpointなのかProduct全体の説明なのか、
  読んだ内容からは判別できなかった。
- **`/v2/td/list`固有の**4桁 vs 5桁Code/末尾ゼロパディング意味論: 見つけた
  資料のどこにも触れられていない。見つけた(未確認の)一般的なClaimは、
  基本J-Quants APIの銘柄Codeが5桁で末尾桁が株式種別Variantを示し、4桁
  入力も受理される、というものだが、これは`/v2/equities/*`についての
  説明でありTDnetアドオンについてのものではなく、そのまま転用できると
  仮定してはならない。

---

## 5. `/v2/td/list` Response Schema

`UNKNOWN` / `SEARCH-SNIPPET-DERIVED (UNVERIFIED)`。タスクが提案した
Field名(`DiscNo`/`Code`/`Name`/`DiscDate`/`DiscTime`/`Title`/
`DiscStatus`/`RevNo`/`DiscItems`/`Docs`)は`WebSearch`要約に繰り返し
出現したが、複数のQuery自体にこれらの正確な文字列を含めていたため、
その再出現を独立した確認として扱うことはできない。**Verbatim な
Field表・実際のJSON Response例・Field単位の説明**は、実際に読めた
Sourceには一件も見つからなかった。`pagination_key`/`cursor`という
Field名についても同様の留保。**これらのField名は、独立した(ローカルでの)
確認なしにNormalizerのMapping Tableへハードコードしてはならない**
— これは本Labが既に`/v2/fins/summary`(D0043)やEDINETのDocuments
List Field(D0046)へ適用済みの基準と同じ。

---

## 6. Cursor vs `pagination_key` Semantics

§2で既述 — `SEARCH-SNIPPET-DERIVED (UNVERIFIED)`のみ。主張されている
2機構分離設計(`pagination_key`=同一Queryの残り、`cursor`=当日分の
Differential Retrieval)と主張されている相互排他性は、他の適時開示
Feedで典型的な`cursor`利用法と整合的でPlausibleではあるが、Plausibility
はEvidenceではない。`REQUIRES_LOCAL_VALIDATION`。

---

## 7. `DiscTime`/`DiscDate` Semantics(PIT上最重要)

**`UNKNOWN`。** これはEDINETの`submitDateTime`/`opeDateTime`曖昧性
(`EDINET_SOURCE_ONBOARDING.md`がPIT上最大のリスクとして指摘した)の
TDnet版に相当するが、`DiscDate`/`DiscTime`が真の公表Timestamp
(適時開示情報閲覧サービス経由での公表)を表すのか、それとも何らかの
J-Quants側のIngestion/処理Timestampを表すのかを述べたSourceは、
一次・二次を問わず**一件も見つからなかった**。この区別についての
JPX公式声明は本セッションから到達できなかった。`lib/disclosures/
model.py`自身の既定方針に従い、これが実際のSpec本文を読む、または
既知の実世界TDnet開示の公開時刻とAPIが報告する`DiscDate`/`DiscTime`を
比較することで確認されるまで、TDnet由来Recordの`market_public_at_
basis`/`provider_available_at_basis`はいずれも`AvailabilityBasis.
UNKNOWN`のまま維持すること。`REQUIRES_LOCAL_VALIDATION`、優先度高
(EDINETの同種項目が受けたのと同じSeverity分類)。

---

## 8. Correction/Deletion/Revision Semantics — §3参照(最重要項目として
そこにまとめて記載)。

---

## 9. `DiscItems`

`UNKNOWN`。ある`WebSearch`合成結果は「商品分類(1桁)+ 会社分類(1桁)+
開示項目(3桁)」というAppendix Code Schemeを説明していたが、実際の値の
List自体は得られず、桁数構造すら実際のSpec Appendixを読まずに検証する
方法はない。**この情報からMapping Tableを作ってはならない。**
`REQUIRES_LOCAL_VALIDATION` — これはまさにEDINETのForm Code List
(そちら§10)について、Substring Heuristic的な推測を避けるため
(`lib/disclosures/model.py`の明示的な禁止事項)Unmappedのまま残した
のと同種の、公式Appendix限定の項目である。

---

## 10. `Docs` Field(`g`/`s`/`x`等)

`SEARCH-SNIPPET-DERIVED (UNVERIFIED)`。ある合成結果は3つのFile種別
Category — 「GENERAL」(一般/全文開示PDF)・「SUMMARY」(要約/決算短信
スタイルPDF)・「XBRL」 — を説明しており、タスクが仮定した`g`/`s`/`x`
形式の短縮Code Schemeと整合的ではあるが、実際の短縮CodeそのものをSourceで
確認したことはなく、英語のCategory名のParaphraseを見ただけである。
`g`/`s`/`x`が文字通り正しいとSpec本文や実際のResponse観測での確認なしに
仮定してはならない。`UNKNOWN`。

---

## 11. `/v2/td/files` Semantics

`UNKNOWN`。読めた(または自分のQuery文字列と独立と信頼できる)どの
Sourceも、必須/任意パラメータ(`discNo`/`docs`)・Response Shape・
タスクが挙げた具体的な「15分でURL失効」というClaimのいずれも説明
していなかった — この具体的な詳細は、Queryの言い回しを変えても
`WebSearch`結果に一度も出現しなかった。15分という数字は、単に確度が
低いというより**完全に未確認**として扱うこと。`REQUIRES_LOCAL_
VALIDATION`。

---

## 12. `/v2/td/bulk` Semantics

`SEARCH-SNIPPET-DERIVED (UNVERIFIED)`: gzip圧縮CSV Bulk Download、
Index Data「5年分」、Cursor-based Incremental Pollingへ切り替える前の
Initial Seed用途として位置づけ。**Response Shape(`lastUpdated`/`url`
Field)の具体的なClaim、およびCSV内での`DiscItems`/`Docs`のPipe(`|`)
区切りEncodingというClaim(タスクが挙げたCSV vs JSON表現の相違Claim)の
いずれも確認できなかった。** 本Lab自身のD0043前例(`/v2/fins/summary`の
宣言 vs 観測Schemaの相違)を踏まえれば、CSV表現がJSON API表現と実際に
異なることは一般論としてPlausibleだが、この具体的なClaim自体は未確認。
`UNKNOWN`。

---

## 13. Rate Limits

§2で既述。`SEARCH-SNIPPET-DERIVED (UNVERIFIED)`の100req/分という数字、
`/v2/td/list`と`/v2/td/files`で共有。基本プランの60req/分(D0039)との
関係、および`JQuantsAdapter`の既存`_RATE_LIMIT_INTERVAL_SEC` Throttleとの
関係は未確認。ルートCLAUDE.mdのRule 5(「外部APIのレート制限を守る」)と
本LabのD0043パターン(`effective_limit = min(plan_limit, endpoint_limit)`)
に従い、TDnet Clientは検証されるまで**より保守的な未確認の数字**を既定と
すべきであり、既存の57req/分相当のThrottleをそのまま流用して安全だと
黙って仮定すべきではない — 独立してThrottleされる別Endpointには独自の
Throttle Windowが必要になりうる、という拡張ポイントは`jquants.py`の
Docstring自身が既に「未実装」として指摘している。

---

## 14. 保存するTDnet-via-J-Quants Dataのライセンス/再配布条件

`SEARCH-SNIPPET-DERIVED (UNVERIFIED)`、一般的なJ-Quants利用規約のみ
(§1参照) — TDnetアドオン固有の再配布条項(基礎となるTDnet PDF/XBRL
文書が、J-Quants自身の利用規約を超えてJPX/TSE著作権による追加制限を
持つかどうか)は見つからなかった。`UNKNOWN`。本Lab自身の
`UNKNOWN_RESTRICTIONS → 保存を制限する`という既定方針
(`DATA_SOURCE_ARCHITECTURE.md`「News Licensing / Storage Policy」節を
一般化したもの)に従い、**これが確認されるまでAttachment生bytes
(PDF/XBRL)を`RawSnapshotStore`へ自由に長期保存できると仮定すべきでは
ない**(EDINETに対して既に適用済みの慎重さを踏襲)。

---

## Known Limitations(明示、隠さない)

1. 本セッションはこのTopicについて公式J-Quants/JPXページを一件も直接
   読むことができなかった — `jpx-jquants.com`・`jpx.gitbook.io`
   (`j-quants-ja`・`j-quants-pro-ja`両方)・`www.jpx.co.jp`いずれも
   `EGRESS_BLOCKED`、今回改めて直接試行して確認済み(前回EDINETセッション
   からの類推ではない)。
2. 二次資料(JPX自身のQiitaアカウント、X/Twitter、Zenn、note.com、
   archive.org、Google Translate Proxy)もすべてブロックされた。到達
   できたのは`github.com`/`raw.githubusercontent.com`と`pypi.org`のみ。
3. 上記の実質的内容はすべて`WebSearch`のAI合成した Snippet要約に由来し、
   生のSnippet Textすら見ておらずParaphraseのみを見ている。複数のQuery
   がTask本文の候補文字列をそのまま含んでおり、返ってきた「確認」の
   独立性を弱めている。ここに書かれたいかなる内容も`SEARCH-SNIPPET-
   DERIVED (UNVERIFIED)`以上には昇格させない。
4. **今回セッションで判明した、真に新しく実務上重要な発見**: 「TDnet」に
   ついて言及する**2つの異なるJ-Quants製品ライン**が存在するように見える
   — 個人向け「J-Quants API」(Lightプランアドオン、タスクの実際の対象)
   と、法人向け「J-Quants Pro」(Snowflake/API/SFTP配信、無関係な別契約)。
   検索結果は両者からの引用を繰り返し混在させていた。Local Validationは
   まず、あるEndpoint/Field Claimが実際にどちらの製品のDocumentation
   由来なのかを確認する必要がある — 混同すれば重大かつSilentな誤りになる。
5. タスクの項目8(訂正/削除/改版意味論、特に`DiscStatus`常にnull /
   `RevNo`常に1というClaim)— タスク自身の「最重要項目」— は確認も反証も
   できなかった。いかなる確度クラスのSourceもこれに触れていない。
6. `DiscDate`/`DiscTime`のPIT意味論(タスク項目7)— 本Labの
   `market_public_at`/`provider_available_at` Modelにとって最も重要な単一
   項目 — も裏付けとなるSourceがゼロだった(未検証のものすら無い)。
7. `/v2/td/files`について主張されている15分URL失効(タスク項目11)は、
   いかなる検索結果にも一度も出現しなかった。
8. アドオン固有の認証方式(V2の他Endpointと同じ`x-api-key`か、アドオン
   固有の何かか)は未確認。
9. アドオン無しLightプランキーの具体的なエラー挙動(Status Code・Body
   Shape)は未確認。EDINETの前例(Errorが`raise_for_status()`では検知
   できないHTTP 200 Body内に埋め込まれていた)を踏まえ、直接観測なしに
   単純な403だと仮定してはならない。
10. `DiscItems`のCode List、`Docs`の`g`/`s`/`x`(または同等の)短縮Code
    Mappingはいずれも未確認であり、見つかった情報からMapping Tableを
    構築することはできない。
11. アドオン(主張100/分)と基本プラン(D0039で確認済みの60/分、ただし
    基本製品についてのみ)のRate Limit関係は未確認。
12. TDnet由来PDF/XBRLコンテンツ固有のライセンス/再配布条件(J-Quants
    一般利用規約とは別に)は未確認。

---

## `lib/disclosures/model.py`へのマッピング — 現状: すべて保留

EDINETに対して本Labが既に適用した規律(`EDINET_SOURCE_ONBOARDING.md`
§13)にならい、`DisclosureDocument`/`DisclosureAttachment`のいかなる
FieldもまだTDnetの仮定Field Mappingから値を埋めるべきではない。

- `market_public_at`/`market_public_at_basis` → `DiscDate`/`DiscTime`
  意味論(§7)が確認されるまで`UNKNOWN`。
- `provider_available_at`/`provider_available_at_basis` → `UNKNOWN`
  (Model自身の既定方針、`market_public_at`へFallbackしない)。
- `document_kind` → 公式Appendix Code List(§9)を実際に読むまで
  `DiscItems`から導出できない。Substring/Heuristic Mappingなし。
- `DocumentRelationship` → §3/§8の訂正意味論が実際のCorrected/
  Withdrawn Disclosureの直接観測で確認されるまで、`DiscNo`/`RevNo`から
  Recordを作らない。
- `entity_id` → TDnetの`Code` Field形式(4桁 vs 5桁、Padding規約)が
  J-Quants既存の5桁規約(D0039)と一致するか確認されるまで
  `EntityRegistry`経由で解決できない — 一致すると仮定しない。
- `AttachmentKind`/`AttachmentAvailability` → §10の未解決な`Docs` Code
  Mappingによりブロックされている。

## Bottom line(当初調査時点、履歴として保持)

この報告書(§0〜ここまで)を**単独で**TDnet Adapter/Normalizer実装の
根拠として使用すべきではない、という当初の結論はそのまま履歴として
残す。実質的なClaimはすべて、ブロックされたHostからの`WebSearch`合成
Snippetに遡り、その一部は自分のQueryの言い回しのEchoである可能性があり、
タスクの最優先項目(訂正/削除/`DiscStatus`/`RevNo`意味論)と第2優先項目
(`DiscDate`/`DiscTime`のPIT上の意味)のいずれも、**ゼロ**件の裏付け
Sourceしか得られなかった。

**その後(別Round、2026-08-17)**、上記「EXTERNAL_OFFICIAL_SPEC_
VERIFICATION」セクションが追加され、ユーザーが別のWeb-access環境から
これらの項目(最優先2項目を含む)を確認したと申告した。この申告内容を
根拠に、Phase4B-3は`lib/disclosures/providers/tdnet.py`(Adapter)・
`tdnet_normalize.py`(Normalizer)の実装を再開した(D0048参照)。ただし、
この申告はClaude自身による一次資料の直接確認ではなく(本セッション自身は
依然`jpx-jquants.com`等へ接続できない、Provenance Tag`EXTERNAL_
OFFICIAL_SPEC_VERIFICATION`参照)、真の意味でのLocal Real Data
Validation(実際にAdd-on契約済みのAPI Keyで`/v2/td/list`等を呼び出し、
Response実物を観測すること)でもない。したがってPhase4B-3全体の
Completion Statusは、実装が完了した後も`CODE_COMPLETE_AWAITING_ADDON_
LOCAL_VALIDATION`のまま維持する。`TDNET_LOCAL_VALIDATION_GUIDE.md`に
記載の手順(ユーザーのローカル環境からの実際のAdd-on呼び出し)が完了
するまで、`COMPLETE`へは昇格しない。

**このAgentがコンテキストとして読んだ既存リポジトリファイル(編集なし):**
- `/home/user/shoui-/Japanese_Equity_Lab/DATA_SOURCE_ARCHITECTURE.md`
- `/home/user/shoui-/Japanese_Equity_Lab/lib/data_sources/jquants.py`
- `/home/user/shoui-/Japanese_Equity_Lab/lib/sources/entity_registry.py`
- `/home/user/shoui-/Japanese_Equity_Lab/lib/disclosures/model.py`
- `/home/user/shoui-/Japanese_Equity_Lab/lib/disclosures/providers/edinet.py`
- `/home/user/shoui-/Japanese_Equity_Lab/EDINET_SOURCE_ONBOARDING.md`
