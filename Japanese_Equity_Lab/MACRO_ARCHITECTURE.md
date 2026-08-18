# Japan Macro Data Architecture(Phase4D)

このDocumentは`lib/macro/`の設計判断をまとめる。実装詳細は各Moduleの
Docstringを参照し、ここでは全体像とSourceを跨いだ設計判断のみを記す。

## 目的とScope

日本のMacro/Economic Data(CPI・GDP・失業率・賃金・政策金利等)を
PIT-safe/revision-aware/source-aware/reproducibleな形でこのLabへ取り込む
ためのData Foundation。**Economic Forecast・Regime Detection・BUY/SELL
判断はこのPhaseのScope外**であり、`lib/macro/`のどのModuleも生成しない
(DECISIONS.md D0055参照)。

「Official Macro Source -> Raw Observation -> Canonical Macro Record ->
Revision-aware History -> Pure as_of View」までがこのPhaseの範囲。

## Series Identity(Entity中心ではなくSeries中心)

Positioning/Fundamentals/DisclosuresがEntity(発行体・銘柄)中心だったのに
対し、MacroはSeries Identity(どの統計・どの系列か)が中心になる。CPI総合・
コアCPI・コアコアCPIを混同しない。Display Name(表示名)だけで同一Series
と判定せず、Provider公式のSeries Code/Table Codeがあれば`series_code`
として保持する(無ければ`None`のまま、推測しない)。

## Long-form、既存PIT Primitiveの再利用

`MacroRecord`(`lib/macro/model.py`)はseries × reference_period × source
単位のLong-form 1レコード。PIT/Revision管理は`lib.evidence.model.
RevisionHistory`/`SourceVersion`/`AvailabilityBasis`をそのまま再利用し、
Macro専用の新しいVersioning Primitiveは作らなかった(Fundamentals/
Positioningと同一のPrimitive)。

## Vintage(Preliminary/Revised/Final)はRevisionHistoryで表現する

「1次速報 -> 2次速報 -> 確報」のような複数Versionは、新しいVintage専用
概念を発明せず、既存`SourceVersion`の系列(同一`series_id`に対する複数
Version)としてそのまま表現できる。`vintage_label`はSourceが明示的に確認
できた場合のみ保持する自由記述Fieldであり、公開順序だけから推測しない
(EVIDENCE-003と同じ原則)。`supersedes_version_id`/`is_correction`は常に
未設定のまま扱う(Positioning/Fundamentalsと同じ設計判断)。

## Reference Period != Availability、Quarter Leakage禁止

`reference_period_start`/`reference_period_end`(この統計が対象とする期間)
と、それが実際に利用可能になった時刻(`market_public_at`/`SourceVersion.
available_at`)は別軸。Quarter終了時点でそのQuarterのGDPが利用可能とは
限らない。`lib/macro/view.py`の`macro_as_of()`はこの分離を`RevisionHistory.
as_of()`の`available_at`基準フィルタへ委譲するのみで、独自のPeriod解釈
ロジックを持たない。

## Date-only Publicationから時刻を推測しない

Sourceが日付のみ(例: "2026-08-19")しか提供しない場合、08:30や15:00等の
時刻を推測して埋めない(Phase4D要件§11)。`AvailabilityBasis`を実際の
確信度より強く主張しない。

## Provider Availability != Market Public Time

このSourceからいつ実際に参照可能になったか(`provider_available_at`
相当)が確認できない場合はUNKNOWNのまま保持し、`market_public_at`(公式
公表時刻)への安全でないFallbackは行わない(PIT-003と同じ原則)。

## Seasonal Adjustment / Unit / Frequencyは別Metricとして保持する

季節調整値(SA)と原数値(NSA)、YoY%とIndex、Monthly SeriesとQuarterly
Seriesを自動変換・混同しない。`SeasonalAdjustment`enumと`Frequency`enum
(Phase4Cから昇格、QUARTERLY/ANNUAL追加)で明示する。

## Source固有semanticsを共通Scoreへ潰さない

`metric_name`(例: "CPI_HEADLINE"、"UNEMPLOYMENT_RATE")はSource固有の
まま保持する。総務省のCPIと別Sourceの類似Seriesを、Field名だけで自動統合
しない。

## このRoundで実装したSource

**なし**。`data-source-researcher` Agent(2026-08-18)がe-Stat(CPI・
失業率)・日本銀行(政策金利)・内閣府/ESRI(GDP QE)・厚生労働省(賃金)の
5候補を調査したが、このSession自身のNetwork Egressが全ての公式Document
URLへ一貫してBlockされており(`EGRESS_BLOCKED`、`EDINET_SOURCE_
ONBOARDING.md`と同じ制約)、全ての情報がSEARCH-SNIPPET-DERIVED
(UNVERIFIED)に留まった。検索Snippetのみを根拠にAdapterを実装しない
(Phase4D要件§33、`推測だけでArchitectureを増やさない`という追加指示にも
従う)。

## Source候補(未実装、NOT_IMPLEMENTED)

`lib/macro/catalog.py`に5件のDescriptorとして登録済み:

| dataset_id | 対象 | data-source-researcher推奨順位 | 判明した制約 |
|---|---|---|---|
| `estat_cpi` | e-Stat経由CPI(総合・コアCPI・コアコアCPI) | 1位 | 5候補中最も強く裏付けられたAPI構造(Version管理REST API、appId登録Flow)だが未読。Vintage問い合わせ機構の有無不明 |
| `boj_policy_rate` | 日本銀行 政策金利 | 2位 | 根拠が最も弱い(2026-02-18付通知見出し+SNS投稿要約のみ)。API新設主張自体が未検証 |
| `esri_gdp_qe` | 内閣府/ESRI GDP速報(QE) | 3位 | 1次速報/2次速報/確報という公式Revision Stage名称は複数Snippetで一致(未読)。専用API有無不明 |
| `estat_unemployment_rate` | 総務省統計局 労働力調査(完全失業率) | e-Stat CPIと同時検証可能性 | 情報が他候補より薄い |
| `mhlw_monthly_labour_survey` | 厚生労働省 毎月勤労統計調査(賃金) | 4位 | 5候補中最も具体的なRevision/Benchmark更新の記述(2024年1月断層)が見つかったが未読 |

## Q5(最重要PIT論点): Vintage/Revision-History問い合わせ機構の有無

data-source-researcher Agentの調査では、5候補いずれについても「過去の
ある時点で公表されていた通りの値を後から取得できるAPI機構」の証拠が
見つからなかった(Inconclusive、Leaning Negative)。判明したのは
「Rebasing(Base Year改定時の接続指数によるContinuity Patch)」であり、
これはVintage Archiveとは別物(現在時点での継続性を後付けする仕組み)。
**この所見を設計制約として明記する**: 真のPIT再構築が必要な場合、この
Labが実際に保存したRaw Snapshot自体(Forward Snapshot、下記参照)が
唯一信頼できるVintage記録になる可能性が高い(EDINET D0046の「Historical
List Is Mutable」所見と同じ結論パターン)。

## Forward Snapshot(将来必要、このRoundでは実装しない)

Revision/Vintageを実際に観測するため、Current Response・Raw Hash・
retrieved_at・series・periodをForward方向へ保存し続ける価値がある
(Phase4D要件§39)。ただしこのRoundでは常時Collectorを作らない(手順・
将来要件としてここに記録するのみ)。

## Common Coreへ含めないもの

Source固有のSemantics(Field名Mapping・Rebasing処理・PDF/Excel Parse)は
将来`lib/macro/providers/`配下に閉じ込め、Common Core相当の`lib/macro/
model.py`/`normalize.py`/`view.py`へは一切追加しない設計とする(Phase4B/
4Cと同じ境界原則)。

## Validation Status(実装状況とは別軸)

5候補全て`implementation_status=NOT_IMPLEMENTED`、Validation Status=
`DESIGN_COMPLETE_AWAITING_SPEC_VERIFICATION`(`lib/macro/catalog.py`の
`known_limitations`へ自由記述、そのためだけの新規Schema Fieldは追加しない
——Positioning Phase4Cと同じ方針)。
