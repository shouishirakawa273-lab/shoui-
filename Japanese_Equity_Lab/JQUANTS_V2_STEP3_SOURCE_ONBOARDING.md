# J-Quants API V2 — Source Onboarding Report (Step 3 未達項目)

作成: 2026-11-22、`source-onboarding` skill に従う。**調査のみ。** Adapter・Normalizer・
Fetch Logicの実装は含まない。API Keyの取得・要求・取り扱いも行っていない。

## 0. 調査範囲と環境

方針書 §4 Step 3 の出力仕様のうち未達の3項目を埋めるための調査。

| Step 3 出力 | 現状 | 本調査の対象 |
| --- | --- | --- |
| PER・PBR・配当利回りの現在値と分位 | 未実装 | ○ |
| ROEの10年推移 | 未実装 | ○ |
| 直近の決算発表予定日 | 未着手 | ○ |

J-Quants は既接続Sourceなので、Identity/Auth/Licenseは既存記録
(`DATA_SOURCE_ARCHITECTURE.md`、D0034/D0043)を引き継ぐ。本報告は**新規Field・
新規Endpointに限って**チェックリストを埋める。

**環境**: EDINET調査時(`EDINET_SOURCE_ONBOARDING.md`)と異なり、本セッションから
J-Quants公式ドキュメント(`jpx-jquants.com`)へのアクセスは成功した。以下の
`PRIMARY_OFFICIAL` と記した項目は公式仕様ページを直接読んで確認している。

---

## 1. Identity & access

| 項目 | 確認結果 |
| --- | --- |
| Source identity | J-Quants API V2(JPX総研)。既存記録のとおり |
| Originating Source / Delivery Provider | 開示は上場会社→東証、配信はJPX総研。既存記録のとおり |
| 新規Endpoint 1 | `GET /v2/equities/valuation`(バリュエーション指標)。`PRIMARY_OFFICIAL` |
| 新規Endpoint 2 | `GET /v2/fins/earnings-date`(決算発表予定日、全上場銘柄)。`PRIMARY_OFFICIAL` |
| 既存Endpointへの追加Field | `/v2/fins/summary` に `ShEq`/`NCShEq`/`ROE`/`NCROE` が**2026年に追加**された。`PRIMARY_OFFICIAL`(リリースノート) |
| 認証 | 既存と同じ `x-api-key` ヘッダ。`PRIMARY_OFFICIAL` |
| プラン要件 | `/equities/valuation` は全プラン。`/fins/earnings-date` は全プラン。`ShEq`/`ROE` の追加も全プラン。`PRIMARY_OFFICIAL` |
| 追加コスト | なし(現行Standardプラン月額3,300円の範囲内) |
| License / 再配布 | 既存記録を引き継ぐ。本調査で新しい制約は確認していない |

**`/v2/fins/announcement` は V2 に存在しない。** V1の `/v1/fins/announcement` は
`/v2/equities/earnings-calendar` に移行した(`PRIMARY_OFFICIAL`、V1→V2移行表)。
さらに2026年に別物として `/fins/earnings-date` が新設され、従来のものは
「決算発表予定日(3・9月期決算会社のみ)」へ改称された。**この2つは別Endpointで
別物**なので混同しない。

---

## 2. Coverage & availability

| 項目 | 確認結果 |
| --- | --- |
| `/fins/summary` 格納期間 | 2008-07-07〜。Standardプランは10年前まで。`PRIMARY_OFFICIAL` |
| `/equities/valuation` 格納開始 | `UNKNOWN`。仕様ページに開始日の記載がない。ただし2008〜2010年頃のカバレッジは不完全な場合があると明記。`PRIMARY_OFFICIAL` |
| `/fins/earnings-date` 格納期間 | 2014-09-01〜。Standardプランは10年前まで。`PRIMARY_OFFICIAL` |
| `/fins/dividend` プラン要件 | **Premiumのみ**(Free/Light/Standard は利用不可)。格納期間2013-02-20〜。`PRIMARY_OFFICIAL` |
| `/fins/details` プラン要件 | **Premiumのみ**。`PRIMARY_OFFICIAL` |
| `/fins/summary` 更新頻度 | **Premiumプランは随時更新、その他プランは日次。** 更新時刻は速報18時頃・確報24時半頃。`PRIMARY_OFFICIAL` |
| `/equities/valuation` 更新 | 開示結果は原則**翌営業日**から反映。`PRIMARY_OFFICIAL` |
| `/fins/earnings-date` 更新 | 日次、10:05頃。新規報告・変更分が追加される。`PRIMARY_OFFICIAL` |
| Rate limit | 本調査で新しい記載を確認していない。既存記録(D0034/D0043)を引き継ぐ |
| Pagination | `/equities/valuation` は `pagination_key` 方式。既存Endpointと同じ。`PRIMARY_OFFICIAL` |
| Bulk download | Lightプラン以上でCSV/Bulk API対応。Standardは該当する。`PRIMARY_OFFICIAL` |

---

## 3. Revision & correction semantics

**本報告で最も重要な節。** 2件の確定した制約がある。

| 項目 | 確認結果 |
| --- | --- |
| `/fins/summary` の訂正 | **同一 `DiscNo` のまま訂正されると行が上書きされ、訂正前の値は取得できない。** `PRIMARY_OFFICIAL` |
| `/equities/valuation` の訂正 | 不備・欠落の修正のためデータが追加・上書きされることがあり、**訂正履歴と訂正前データはAPI・CSV等いずれの手段でも提供されない**。`PRIMARY_OFFICIAL` |
| 削除 | `/fins/dividend` には `StatCode`(1=新規/2=訂正/3=削除)がある。`PRIMARY_OFFICIAL`。`/fins/summary` の削除表現は `UNKNOWN` |
| Revision の親子関係 | `/fins/summary` について確認できず。別 `DiscNo` で出た訂正は別レコードとして並ぶが、元レコードとの確定的な対応関係を示すFieldは `UNKNOWN`。本Labが独立時系列として保持する現行方針は妥当 |

### この制約の帰結(重要)

**過去を後から取得した場合、PIT正しさは原理的に保証できない。** 同一 `DiscNo` で
上書き訂正された行は、訂正後の値が**元の `DiscDate`/`DiscTime` のまま**返る。
2021年に公表された値として読めるが、中身は2026年に訂正された値である可能性があり、
APIからはそれを判別できない。これは Look-ahead leakage そのものである。

防御手段は**本Labが開示直後に取得したSnapshotを持っていること**のみ。
`RawSnapshotStore` の存在意義が、設計上の良い習慣ではなく**唯一の防御策**で
あることが公式仕様から確定した。

同時に、**W0の未解決事項と同じ制約がここにも効く。** `PREREG0001_R1` の実データ
Snapshotは本リポジトリからは原本照合できない(`period_usage_ledger.md`)。つまり
H0001の実データラウンドが見た値が訂正前か訂正後かは `UNKNOWN` である。

---

## 4. PIT timestamp semantics

| 項目 | 確認結果 |
| --- | --- |
| Public timestamp | `/fins/summary` の `DiscDate`/`DiscTime`(開示日・開示時刻)。既存実装が `MARKET_PUBLIC_AT` に使っているもの。`PRIMARY_OFFICIAL` |
| Provider availability timestamp | **提供されない。** `/equities/valuation` 仕様は、各項目が利用可能になった時刻をproviderは提供しないと明記。`PRIMARY_OFFICIAL` |
| Retrieved timestamp | providerは提供しない。本Lab自身の取得時刻のみ |
| 開示順序 | **`DiscNo` は順序を保証しない。`DiscDate` と `DiscTime` で判定すること。** `PRIMARY_OFFICIAL` |
| TDnetとの同期 | `/fins/summary` はTDnet適時開示インデックスと同期していないため、開示直後は財務情報が取得できない場合がある。`DiscNo` で対応付けは可能。`PRIMARY_OFFICIAL` |

### 既存実装との照合(2件とも問題なし)

1. **`DiscNo` 順序**: `normalize.py:57` は「`DiscNo` からDisclosure Date/Timeを推測
   しない」と既に明文化し、実観測例(`DiscNo=20220204580837` に対し
   `DiscDate=2022-02-09`)も記録している。`forecast_revisions.py` の並べ替えも
   `published_at` 基準で `DiscNo` を使っていない。**公式仕様に適合している。**
   なお V1 の旧仕様ページには「開示番号で昇順に並んでいます」との記載があり、
   V2仕様と食い違う。V2の記載に従う。

2. **`PROVIDER_AVAILABLE_AT` が常に UNKNOWN**: Phase4Aでこれを UNKNOWN とし、
   既定で除外する設計は、**providerが当該時刻を提供しないという公式仕様と一致する。**
   実装の未完ではなく、Source側の制約を正しく反映した結果である。
   `availability_basis=UNKNOWN` は埋めるべき穴ではない。

### 新たに判明した論点

Standardプランでは `/fins/summary` が**日次更新**である(随時更新はPremiumのみ)。
したがって本Labのパイプラインが実際にデータを取得できた最速時点は、開示時刻では
なく**その日の取り込み完了後**になる。`PROVIDER_AVAILABLE_AT` を厳密に扱うなら
「開示日の確報取り込み(24:30頃)以降」が下限の候補になるが、
**各レコードの実際の取り込み時刻は提供されないため、これを確定値として使うことは
できない。** 推測で埋めない方針を維持し、UNKNOWN のままとする。

---

## 5. Identity mapping

| 項目 | 確認結果 |
| --- | --- |
| 識別子 | 5桁銘柄コード。`/equities/valuation` は4桁も受理するが、普通株・優先株の両方が上場している場合は4桁指定で普通株のみを返す。`PRIMARY_OFFICIAL` |
| Code mapping | 既存の `normalize_provider_code_to_internal` / `lib/sources/entity_registry.py` を経由する。新規Endpointでも raw provider code を直接joinしない |

---

## 6. Schema

### 6.1 `/v2/fins/summary` — 追加確認できたField

すべて `PRIMARY_OFFICIAL`(`jpx-jquants.com/ja/spec/fin-summary`)。

**株式数**

| Field | 定義 |
| --- | --- |
| `ShOutFY` | 期末発行済株式数(自己株式を含む) |
| `TrShFY` | 期末自己株式数 |
| `AvgSh` | 期中平均株式数 |

公式ヘルプは、自己株式を除く期末発行済株式数を `ShOutFY - TrShFY` で算出できると
明記している。**この減算は公式が示した導出であり、本Labの推測ではない。**

**自己資本・純資産**

| Field | 定義 |
| --- | --- |
| `ShEq` / `NCShEq` | 自己資本 / 同_非連結 |
| `Eq` / `NCEq` | 純資産 / 同_非連結 |
| `BPS` / `NCBPS` | 一株あたり純資産 / 同_非連結 |

**ROE**

| Field | 定義 |
| --- | --- |
| `ROE` / `NCROE` | 自己資本利益率 / 同_非連結 |

**配当(実績)**

| Field | 定義 |
| --- | --- |
| `Div1Q` / `Div2Q` / `Div3Q` / `DivFY` | 一株あたり配当実績_各四半期末 / 期末 |
| `DivAnn` | 一株あたり配当実績_合計 |
| `DivUnit` | 1口当たり分配金(REIT等) |
| `DivTotalAnn` | 配当金総額 |
| `PayoutRatioAnn` | 配当性向 |

**配当(当事業年度予想)**: `FDiv1Q` / `FDiv2Q` / `FDiv3Q` / `FDivFY` / `FDivAnn` /
`FDivUnit` / `FDivTotalAnn` / `FPayoutRatioAnn`

**配当(翌事業年度予想)**: `NxFDiv1Q` / `NxFDiv2Q` / `NxFDiv3Q` / `NxFDivFY` /
`NxFDivAnn` / `NxFDivUnit` / `NxFPayoutRatioAnn`

予想Fieldの `F` / `NxF` 接頭辞は既存の `_current_year_forecast` /
`_next_year_forecast` の区別にそのまま対応する。

### 6.2 `/v2/equities/valuation` — 全Field

すべて `PRIMARY_OFFICIAL`。11項目。

| Field | 定義 | 算出方法(公式記載) |
| --- | --- | --- |
| `Date` | 日付 | — |
| `Code` | 5桁銘柄コード | — |
| `EPS` | 一株当たり利益(実績、円) | 直近12ヶ月(TTM)の純利益に基づく |
| `FwdEPS` | 同(予想、円) | 進行期の会社予想純利益に基づく |
| `BPS` | 一株当たり純資産(円) | 直近開示の期末自己資本を使用 |
| `ROE` | 自己資本利益率(実績) | TTM純利益 ÷ TTM期間の期首・期末自己資本の平均 |
| `FwdROE` | 同(予想) | 予想純利益 ÷ 直近開示の期末自己資本 |
| `PER` / `FwdPER` / `PBR` | 各倍率 | 株価は当日終値(売買不成立時は基準値) |
| `MktCap` | 時価総額(百万円) | 株価 × 自己株式控除後株式数。**分割・併合を反映** |

**単位の注意**: `ROE`/`FwdROE` は小数(0.2310 = 23.1%)でパーセントではない。
指標は小数2桁、ROE系は4桁に丸められ、JSONでは末尾の0が落ちることがある。

### 6.3 `/v2/fins/earnings-date`

| 項目 | 確認結果 |
| --- | --- |
| 検索キー | 銘柄コード / 公表日 / 決算発表予定日 のいずれか1つ必須。`PRIMARY_OFFICIAL` |
| レスポンスField一覧 | **`UNKNOWN`。** 仕様ページを本セッションから取得できていない |

### 6.4 空欄・Null semantics

| 項目 | 確認結果 |
| --- | --- |
| `/fins/summary` の空文字列 | **値の記載がなかったことのみを示す。** 変更の有無、予想の撤回、未定を意味しない。`PRIMARY_OFFICIAL` |
| `/equities/valuation` のnull | 必要データが揃わない場合にnull。新規上場、決算期変更期、未開示銘柄を含む。`PRIMARY_OFFICIAL` |
| 有無フラグ | 「有」=`"true"`、「無」=`"false"`、記載なし=`""`。既存実装の `_KNOWN_BOOLEAN_LITERALS` と一致。`PRIMARY_OFFICIAL` |
| 経常利益 | **IFRS・米国基準では空欄になる**(当該基準に該当項目がないため)。`PRIMARY_OFFICIAL` |

**空文字列の意味が公式に確定した。** 本Labの `MISSING_OR_UNSPECIFIED`
(「Provider側で空だが確定的な理由が無い」)は、この仕様の正確な写しである。
`NOT_DISCLOSED` と決めつけない設計が公式仕様に裏付けられた。

**経常利益のNOT_APPLICABLEが IFRS だけでなく米国基準でも確定した。**
`normalize.py` の `_NOT_APPLICABLE_UNDER_STANDARD` は IFRS と `USGAAP` の両方に
`ordinary_profit` を登録しており、**公式記載と一致する。**

### 6.5 Observed wire schema との差

本調査は宣言Schemaのみを扱う。Observed wire schema は実データでの照合待ち。
特に `ShEq`/`ROE` は**2026年に追加されたField**であり、**過去の行に値が入って
いるかは `UNKNOWN`。** ローカル実データ照合で確認する必要がある
(`local-validation` skill)。

---

## 7. Storage

| 項目 | 確認結果 |
| --- | --- |
| Raw保持 | 既存の `RawSnapshotStore` 方針を引き継ぐ。新しい制約は確認していない。§3のとおり、Snapshotは訂正上書きに対する唯一の防御策 |
| ファイル/XBRL | `/fins/details` はEDINET XBRLタクソノミのラベルをキーとするが Premium のみ。Standardでは利用できない。`PRIMARY_OFFICIAL` |
| Checksum | providerによる提供は `UNKNOWN`。本Lab側のhashのみ |

---

## 8. Known limitations(UNKNOWN と確定した制約の一覧)

### 確定した制約

1. **訂正の上書き**: `/fins/summary` は同一 `DiscNo` で上書きされ訂正前の値を取得
   できない。`/equities/valuation` は訂正履歴・訂正前データを一切提供しない。
   後から取得した過去のPIT正しさは原理的に保証不能
2. **Provider availability timestamp は提供されない**。`PROVIDER_AVAILABLE_AT` を
   EXACT/OBSERVED で埋める手段が Source 側に存在しない
3. **一株当たり配当は遡及調整されない**: 株式分割・併合を反映せず、決算短信の記載を
   そのまま収録する。`PRIMARY_OFFICIAL`。**EPSと同じ不連続がDPSにも生じる**
4. **レンジ形式の業績予想は収録されない**: 幅で開示された予想は空欄になる。
   空欄は「未開示」ではなく「レンジで開示された」可能性を含む
5. **REITは `/equities/valuation` でほぼ空**: ETF・ETN・優先株は全指標null、
   REIT等は `MktCap` のみで他指標はnull(REIT対応は予定とされている)
6. **配当利回りは `/equities/valuation` に含まれない**(11項目に存在しない)
7. **`/fins/dividend` と `/fins/details` は Premium のみ**。Standardでは利用不可
8. **決算期変更を直接示すFieldがない**: `CurFYEn` の変化で判断するほかない
9. **Standardプランの `/fins/summary` は日次更新**(随時更新はPremiumのみ)
10. **`/equities/valuation` の2008〜2010年頃のカバレッジは不完全な場合がある**

### UNKNOWN(推測で埋めない)

- `/equities/valuation` のデータ格納開始日
- `/equities/valuation` の `EPS`/`FwdEPS`/`BPS` が使用する株式数(`MktCap` は
  自己株式控除後と明記されているが、他の一株当たり指標については記載がない)
- `/equities/valuation` の `EPS`/`BPS` 等が分割・併合を反映するか(`MktCap` のみ
  反映すると明記されている。他項目についての記載がない)
- `/equities/valuation` の負の利益の扱い(PERの符号・null化)
- `/fins/earnings-date` のレスポンスField一覧
- `/fins/summary` の削除semantics
- `/fins/summary` の訂正レコードと元レコードの確定的な対応関係
- `ShEq`/`ROE` の過去行における充填状況
- 開示書類種別(DocType)の公式一覧。**米国基準DocType(`*_Consolidated_US`)が
  `_DOC_TYPE_TO_ACCOUNTING_STANDARD` に未登録で、7203の2017〜2020年が
  `accounting_standard=None` にfail closedしている。** 公式のDocType一覧ページが
  存在することは確認したが未取得

---

## 9. 実装判断のための整理(判断は行わない)

skillの定めによりここでは実装せず、選択肢とトレードオフのみ記録する。

### Step 3 の3つの穴に対して

| 穴 | 取得手段 | 計算の必要 |
| --- | --- | --- |
| ROE | `/fins/summary` の `ROE`、または `/equities/valuation` の `ROE` | **不要**(どちらも開示値) |
| PBR | `/equities/valuation` の `PBR`、または `BPS` と株価 | `/equities/valuation` なら**不要** |
| PER分位 | `/equities/valuation` の `PER` の日次系列 | **不要**(分位は系列から直接) |
| 配当利回り | `DivAnn` と株価から導出 | **必要**(どのEndpointにも無い) |
| 決算発表予定日 | `/fins/earnings-date` | 不要 |

**3項目が開示値そのままで取れる。** ルート `CLAUDE.md` の「数値を推測で埋めない」
「取得できない項目を他の値から計算して埋めることは禁止」に抵触しない形で Step 3 の
出力仕様を満たせる。配当利回りのみ導出が必要で、ここは別途の判断を要する。

### `/equities/valuation` を使う場合の論点

- 利点: 日次系列なので「過去10年の分位」が系列から直接求まる。算出方法が公式に
  文書化されており、本Labが定義を決めない
- 論点1: **REITでほぼ空**。これまでのREIT中心の作業には使えない
- 論点2: 訂正履歴が提供されないため、Snapshotを取らない限り過去はPIT非保証
- 論点3: 一株当たり指標の分割調整の有無が `UNKNOWN`。`MktCap` のみ反映と明記
  されているのは、他項目が反映しない可能性を示唆するが、**断定しない**

### `per_share.py` の対象拡大

制約3により、`DivAnn` 等をマッピングした場合、`lib/screener/per_share.py` の
`PER_SHARE_METRICS` に一株当たり配当を加える必要がある。EPSで見つかった不連続と
同じ種類の読み違えが配当にも起きる。ただし本報告では実装しない。

### 次の工程

1. 本報告のレビュー(どのEndpointを使うかの判断)
2. `local-validation` skill に従い、実データで Observed wire schema を照合
   (特に `ShEq`/`ROE` の過去行充填、`/equities/valuation` のREIT挙動)
3. `source-integration` skill のRule-IDチェックリストに従って実装
4. 開示書類種別の公式一覧を取得し、米国基準DocTypeの未登録を解消

---

## 出典

- `https://jpx-jquants.com/ja/spec/fin-summary`(財務情報、Field定義・留意点)
- `https://jpx-jquants.com/en/spec/eq-valuation`(バリュエーション指標、算出方法・留意点)
- `https://jpx-jquants.com/ja/spec/data-spec`(プラン別利用可否・格納期間)
- `https://jpx-jquants.com/ja/spec/data-update`(更新頻度・更新時刻)
- `https://jpx-jquants.com/ja/spec/release`(2026年リリース: バリュエーション指標API、
  決算発表予定日API、`ShEq`/`ROE` 追加)
- `https://jpx-jquants.com/ja/spec/migration-v1-v2`(V1→V2 Endpoint対応表)
- `https://jpx-jquants.com/ja/help/data`(発行済株式数の算出、累計値の扱い)
- `https://jpx-jquants.com/ja/spec/eq-earnings-cal`(3・9月期決算会社のみの予定日)
- `https://jpx-jquants.com/en/spec/fin-dividend`(配当金情報のField、Premium限定)

いずれも `SourceAuthorityClass = PRIMARY_OFFICIAL`。本報告で `VERIFIED_SECONDARY`
以下の出典に依拠した確定記載はない。

---

# 追補(2026-11-22) — 設計判断と残ギャップ3件の解消

## 10. 採用した設計判断

オーナー判断により以下を確定。実装はまだ行っていない。

| 決定 | 内容 |
| --- | --- |
| PER・PBR・ROEの一次ソース | **併用。** 普通株等は `/equities/valuation`、REITは `/fins/summary` |
| 配当利回り | **現在値のみ。** 10年分位は出さない |
| 米国基準DocType | **今回の作業に含める** |

### 10.1 併用の必須条件: nullでフォールバックしない

`/equities/valuation` のnullは、REITだけでなく新規上場・決算期変更・未開示でも
発生する(§6.4)。したがって「nullなら `/fins/summary` から計算する」という実装は、
**本当に取得不可な値を自作値で埋めることになり、ルートCLAUDE.mdの
「取得できない項目を他の値から計算・推測して埋めることは禁止」に正面から違反する。**

**値を見てから選ぶのではなく、銘柄種別でソースを決め打ちする。** 選んだソースが
nullを返したら「取得不可」とする。別ソースへ黙って切り替えない。

### 10.2 `ROE`/`EPS`/`BPS` は両ソースで別物

同一指標の2つの測定値ではない。**どちらの定義で出しているかのラベルが必須。**

| 指標 | `/fins/summary` | `/equities/valuation` |
| --- | --- | --- |
| ROE | 会社が開示した自己資本利益率(年次・開示時点) | TTM純利益 ÷ TTM期首期末平均自己資本(JPX算出・日次) |
| EPS | 開示された一株当たり当期純利益 | TTM純利益ベース |
| BPS | 開示された一株あたり純資産 | 直近開示の期末自己資本ベース |

両者は正当に異なる値になる。平均しない。優先順位で片方を「正」としない。

## 11. ギャップ解消1: 銘柄種別の判定 — `ProdCat`

`/equities/master` の `ProdCat`(商品区分コード)で判定できる。`PRIMARY_OFFICIAL`。

| コード | 名称 |
| --- | --- |
| 011 | 内国株券 |
| 012 | 優先出資証券 |
| 013 | REIT |
| 014 | ETF |
| 021 | 外国株券 |
| 022 | 外国REIT |
| 023 | 外国ETF |
| 024 | 外国株預託証券 |

公式記載の性質:

- 銘柄マスタに記録された値を無修正で返す
- コード定義は全期間(2008-05-07開始)を通じて同一
- **全期間・全銘柄で値が存在し、欠損はない**(バックフィル不要)
- **`011`(内国株券)には優先株等も含まれるため、`ProdCat` だけでは普通株を特定できない**
- ETN・インフラファンドに専用コードはない
- JPXサイト上の市場・商品区分との公式な対応表は提供されない

### ルーティング方針(実装時に適用)

`ProdCat` は「REITかどうか」を確定できるので§10.1の決め打ちに使える。ただし
`011` 内に優先株が混ざるため、**`011` の銘柄が `/equities/valuation` でnullを
返した場合、それは優先株だった可能性を含む。§10.1のとおり「取得不可」とし、
`/fins/summary` へ切り替えない。** この挙動は正しい: 優先株のPERを自作することに
意味はない。

`ProdCat` は日付ごとのマスタ値なので、PIT的には**判定時点の値**を使う。

## 12. ギャップ解消2: 開示書類種別(DocType)公式一覧

`PRIMARY_OFFICIAL`。全42種別。会計基準の接尾辞は **`_JP` / `_US` / `_IFRS` /
`_JMIS` / `_Foreign` / `_REIT`** の6種。期種別は `FY` / `1Q` / `2Q` / `3Q` /
`OtherPeriod`。連結区分は `Consolidated` / `NonConsolidated`。

**決算短信系(38種)**

| 会計基準 | 連結 | 非連結 |
| --- | --- | --- |
| 日本基準 `_JP` | FY/1Q/2Q/3Q/OtherPeriod | FY/1Q/2Q/3Q/OtherPeriod |
| 米国基準 `_US` | FY/1Q/2Q/3Q/OtherPeriod | (一覧に無い) |
| ＩＦＲＳ `_IFRS` | FY/1Q/2Q/3Q/OtherPeriod | FY/1Q/2Q/3Q/OtherPeriod |
| ＪＭＩＳ `_JMIS` | FY/1Q/2Q/3Q/OtherPeriod | (一覧に無い) |
| 外国株 `_Foreign` | FY/1Q/2Q/3Q/OtherPeriod | FY/1Q/2Q/3Q/OtherPeriod |
| REIT `_REIT` | FY のみ | (一覧に無い) |

**修正系(4種)**: `DividendForecastRevision`(配当予想の修正) /
`EarnForecastRevision`(業績予想の修正) /
`REITDividendForecastRevision`(分配予想の修正) /
`REITEarnForecastRevision`(利益予想の修正)

### 実装時の注意(3点)

1. **`_JMIS` はＪＭＩＳ(修正国際基準)であり、ＩＦＲＳとは別の会計基準。**
   IFRSへマップしてはならない。名前が似ているが別物である
2. **経常利益のNOT_APPLICABLE拡張は行わない。** 公式記載は「IFRS・米国基準では
   経常利益が空欄」までであり、`_JMIS` / `_Foreign` / `_REIT` について同じことが
   言えるかは `UNKNOWN`。JMISはIFRSベースなので空欄になりそうだが、**それは推測
   なので登録しない。** `normalize.py` が `_JP` に対して取っている態度と同じ
3. 一覧に無い組み合わせ(非連結の米国基準等)は引き続き未知DocTypeとして
   fail closedする。一覧が全てだと断定しない

これで7203の2017〜2020年(`FYFinancialStatements_Consolidated_US` 等)が
`accounting_standard=None` になっている原因は解消できる。**`_US` は公式一覧に
「決算短信（連結・米国基準）」として明記されており、substring heuristicではなく
明示的なマッピングとして登録できる。**

## 13. ギャップ解消3: `/fins/earnings-date` — 部分的

| 項目 | 確認結果 |
| --- | --- |
| 検索キー | `code` / `date`(公表日) / `scheduled_date`(予定日) のいずれか1つ必須。`PRIMARY_OFFICIAL`(CLI仕様)および `SECONDARY` が一致 |
| レスポンスField | **`PRIMARY_OFFICIAL` では未取得。** 公式仕様ページに本セッションから到達できなかった |
| Field名(参考) | `PubDate`(公表日)と `SchDate`(予定日)を含むとされる。**出典は `SECONDARY`(サードパーティクライアントのIssue)。確定情報として扱わない** |
| 予定日未定時 | `SchDate` が空文字になるとされる。`SECONDARY` |

### PIT安全な使い方(公式記載から導ける)

公式リリースノートは、**予定日で検索した場合、訂正された予定日については現在
有効なものだけが取得できる**と明記している。つまり:

- **`scheduled_date` で検索してはいけない。** 過去に報告され後に訂正された予定日が
  見えなくなり、「その時点で市場が知っていた予定日」を再現できない
- `code` または `date`(公表日)で検索し、**(公表日, 予定日) の対を全て保持する。**
  これが予定日の改定履歴になる

この方針は公式記載のみから導けるので、Field名が `SECONDARY` 止まりでも
**使い方の判断は確定できる。** 実際のField名は実データ照合で確認する。

## 14. 更新後のUNKNOWN一覧

§8から解消されたもの: 銘柄種別の判定手段、開示書類種別の公式一覧。

残るUNKNOWN:

- `/equities/valuation` のデータ格納開始日
- `/equities/valuation` の `EPS`/`FwdEPS`/`BPS` が使用する株式数
- `/equities/valuation` の一株当たり指標が分割・併合を反映するか(`MktCap` のみ明記)
- `/equities/valuation` の負の利益の扱い
- `/fins/earnings-date` のレスポンスField**公式**一覧
- `/fins/summary` の削除semantics
- `/fins/summary` の訂正レコードと元レコードの確定的な対応関係
- `ShEq`/`ROE` の過去行における充填状況
- `_JMIS` / `_Foreign` / `_REIT` における経常利益の存否
- 公式DocType一覧が網羅的かどうか(非連結・米国基準等が実データに現れないか)
- ETN・インフラファンドの `ProdCat` 値

## 15. 次工程(実データ照合で確認すべきこと)

`local-validation` skill に従う。実APIはオーナーのローカル環境から叩く。

1. `ShEq` / `ROE` が**過去の行にも入っているか**(2026年追加Fieldのため最重要)
2. REIT銘柄の `/equities/valuation` 応答(`MktCap` 以外が本当に全てnullか)
3. REIT銘柄の `/fins/summary` で `DivUnit` / `FDivUnit` が取れるか
4. `/equities/valuation` の一株当たり指標が分割をまたいで連続するか
   (7203の2021年10月前後で確認できる)
5. `/fins/earnings-date` の実際のレスポンスField
6. `ProdCat` が対象銘柄で期待通りの値か
7. 実データのDocType集合が公式一覧に収まるか

---

# 追補2(2026-11-24) — 実データ観測の結果

`scripts/jquants_step3_schema_diagnostic.py` を 7203(普通株・ProdCat 011)と
89510 日本ビルファンド(REIT・ProdCat 013)で実行した結果。宣言Schemaではなく
**Observed Wire Schema** であり、以下は観測事実である。

## 16.1 §15の7項目の結果

| # | 確認項目 | 結果 |
| --- | --- | --- |
| 1 | `ShEq`/`ROE` の過去行充填 | **充填されている。** 詳細は16.2 |
| 2 | REITの `/equities/valuation` | `MktCap` 以外 2440/2440 すべてnull。仕様書どおり |
| 3 | REITの `/fins/summary` | **取れる。ただしField集合が普通株と異なる。** 16.2 |
| 4 | 分割前後の一株当たり指標 | **未調整。** 権利落ち日に段差。16.3 |
| 5 | `/fins/earnings-date` のField | `PubDate`/`SchDate`/`FQName`/`FYE`/`Code`/`CoName`/`CoNameEn` |
| 6 | `ProdCat` | 72030→`011`、89510→`013`。ルーティング可能 |
| 7 | DocType集合 | 公式42種の部分集合。一覧外の値なし |

## 16.2 普通株とREITはFieldが入れ替わる

同じ概念に別のFieldが使われており、**「REITは値が少ない」のではなく別マッピング**
である。

| Field | 7203(普通株) | 89510(REIT) |
| --- | --- | --- |
| `ShEq` 自己資本 | 41/41 | **0/27** |
| `Eq` 純資産 | 41/41 | 20/27 |
| `ROE` | 11/41(FY行) | 20/27 |
| `BPS` | 11/41(FY行) | 20/27 |
| `ShOutFY` / `TrShFY` | 41/41 | 20/27 |
| `AvgSh` 期中平均株式数 | 41/41 | **0/27** |
| `DivAnn` 一株当たり配当 | 10/41 | **0/27** |
| `DivUnit` 1口当たり分配金 | **0/41** | 20/27 |
| `FDivUnit` | 0/41 | **0/27** |
| `OdP` 経常利益 | **0/41** | 20/27 |

帰結:

1. **REIT対応は DocType→会計基準の1行追加では済まない。** 自己資本↔純資産、
   一株当たり配当↔1口当たり分配金の読み替えが必要になる
2. **`ROE`/`BPS` はFY開示にのみ入る**(両方の銘柄種別で共通)。年次推移には十分
3. **`ShEq` はREITで空、`Eq` は入る。** REITのBPS系をShEq経由で組むと全て取得不可になる
4. **REITは半期開示。** FY開示20件/約10年 = 年2回。日本ビルファンドの決算期は
   6月と12月。「10年推移」はREITでは20点になる

### 経常利益のNOT_APPLICABLEが実データで裏付けられた

`OdP` は **7203で0/41、REITで20/27**。7203はIFRS(7期)と米国基準(14行)のみで
構成されており、全41行で空。公式記載「IFRS・米国基準では経常利益が空欄」が
実データで確認できた。

同時に、**`_REIT` を `_NOT_APPLICABLE_UNDER_STANDARD` に追加してはならない**ことも
確定した。REITは経常利益を開示している。§12の注意2で「JMISはIFRSベースだから
空欄になりそうだが推測なので登録しない」としたのと同じ理由で、**推測しなかったのが
正しかった**ことになる。

### `FDivUnit` は0件だが「無い」とは言えない

REITで `FDivUnit` は0/27。しかしDocTypeに `REITEarnForecastRevision` が7件あり、
**REITも予想の修正を開示している。** 分配金予想がどのFieldに入るかは `UNKNOWN`
であり、「REITの分配金予想は取得できない」と結論してはならない。

## 16.3 分割: 比率は連続、水準は不連続

`/equities/valuation`、7203の権利落ち日(2021-09-29):

| | 09-28 | 09-29 | 比 |
| --- | --- | --- | --- |
| EPS | 1067.36 | 213.47 | **5.0000倍** |
| BPS | 8634.65 | 1726.93 | **5.0000倍** |
| PER | 9.73 | 9.71 | 連続 |
| PBR | 1.2 | 1.2 | 連続 |

**PER・PBRの10年分位は分割の処理が不要。** 株価と一株当たり価値が同時にずれて
打ち消し合う。Step 3の「PER・PBRの現在値と分位」はこれで素直に満たせる。

一株当たりの水準は別で、**段差は権利落ち日に立つ**。`/fins/summary` のBPSが
決算期の境界で段差を作るのとは**アンカーが違う**。

`/fins/summary` のBPS(FY行)の前期比: 1.094 / 1.061 / 1.062 / 1.154 /
**0.228** / 1.097 / 1.216 / 1.084 / 1.113。FY2022で基準が切り替わっている。
`per_share.py` の `PER_SHARE_METRICS` に **BPSを追加する必要がある**(±25%で
0.228は余裕で検知する)。ROEは比率なので影響を受けない。

## 16.4 `from`/`to` は無視されている

`code` のみ41件、`code`+`from`+`to` も41件。公式パラメータ表は `code`/`date`/
`cursor` の3つのみ。**Adapterは何もしないパラメータを2つ送っている。**

PITの漏れは生じない(正規化層が `decision_at` で絞る)。しかし
`fetch_financial_statements` は**実際には絞っていない範囲を引数で受け取っており、
契約が実態と合っていない**。`raw_disclosure_date_range` も要求より広い範囲を
報告する。要修正。

## 16.5 診断スクリプト自体の誤り(記録)

監視対象に `OpP` という**存在しないField名**を入れた。営業利益の実際のField名は
`OP`(`normalize.py` の `_METRIC_FIELD_MAP`、D0043で確認済み)。

`OpP` は 7203で0/41、REITで0/27 となり、**REITの結果だけ見て「REITは営業利益を
開示しない」と読みかけた。** 存在しないFieldは常に0件になるので、
**充填率0は「開示されていない」の証拠にならない。**

スクリプトに存在チェックを追加した。監視対象がRaw Payloadのキー集合に無い場合、
充填率ではなく「Schemaに存在しないField名(観測ではなく名前の誤り)」として
別枠で警告する。これで同種の誤読が黙って通らない。

**REITの営業利益の有無は現時点で `UNKNOWN`。** `OP` での再観測待ち。

## 16.6 更新後のUNKNOWN

解消: `ShEq`/`ROE` の過去行充填、REITの `/fins/summary` 挙動、
`/fins/earnings-date` のField、`/equities/valuation` の一株当たり指標の分割調整、
`/equities/valuation` の格納開始日(2016-11-24が最古として観測)、
`_REIT` における経常利益の存否。

残る:

- REITの営業利益(`OP`)の有無 ← 次の実行で解消
- REITの分配金予想がどのFieldに入るか
- `/equities/valuation` の負の利益の扱い
- `/fins/summary` の削除semantics
- 訂正レコードと元レコードの確定的な対応関係
- `_JMIS` / `_Foreign` における経常利益の存否
- 公式DocType一覧が網羅的かどうか(7203とREITでは収まっていた)
- ETN・インフラファンドの `ProdCat` 値
