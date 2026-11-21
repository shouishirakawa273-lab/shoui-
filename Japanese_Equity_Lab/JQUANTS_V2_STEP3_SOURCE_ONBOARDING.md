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
