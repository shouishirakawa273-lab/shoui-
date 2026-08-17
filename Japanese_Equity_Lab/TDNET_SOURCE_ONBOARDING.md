# TDnet Source Onboarding Report(Phase4B-3)— J-Quants API V2 TDnet/適時開示情報アドオン

作成: `data-source-researcher` subagent(`source-onboarding` skill)、2026-08-17。
Main Claudeによる直接の追記なし(subagentの調査結果をそのまま保存)。
Read-only調査。Connector/Adapterコードは一切書いていない。APIキーの要求・
取り扱いも行っていない。

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

## Bottom line

この報告書をTDnet Adapter/Normalizer実装の根拠として使用すべきではない。
実質的なClaimはすべて、ブロックされたHostからの`WebSearch`合成Snippetに
遡り、その一部は自分のQueryの言い回しのEchoである可能性があり、タスクの
最優先項目(訂正/削除/`DiscStatus`/`RevNo`意味論)と第2優先項目
(`DiscDate`/`DiscTime`のPIT上の意味)のいずれも、**ゼロ**件の裏付け
Sourceしか得られなかった。推奨される次のステップはEDINETの前例と
全く同じ: `jpx-jquants.com`/`jpx.gitbook.io`へ直接到達できる環境から
Local Validationを行い、実際のSpec Pageを読み、訂正/削除Claimを信頼する
前に — `EDINET_LOCAL_VALIDATION_GUIDE.md`がD0046を生んだLocal Real Data
Validationを主導したのと同じように — 実際に訂正または取下げられたTDnet
開示を実際のAPI経由で観測すること。それまでは、`DATA_SOURCE_
ARCHITECTURE.md`のTDnet行は`implementation_status = NOT_IMPLEMENTED`の
ままとし、Phase4B-3は`lib/disclosures/providers/tdnet.py`の実装へは
進まない。

**このAgentがコンテキストとして読んだ既存リポジトリファイル(編集なし):**
- `/home/user/shoui-/Japanese_Equity_Lab/DATA_SOURCE_ARCHITECTURE.md`
- `/home/user/shoui-/Japanese_Equity_Lab/lib/data_sources/jquants.py`
- `/home/user/shoui-/Japanese_Equity_Lab/lib/sources/entity_registry.py`
- `/home/user/shoui-/Japanese_Equity_Lab/lib/disclosures/model.py`
- `/home/user/shoui-/Japanese_Equity_Lab/lib/disclosures/providers/edinet.py`
- `/home/user/shoui-/Japanese_Equity_Lab/EDINET_SOURCE_ONBOARDING.md`
