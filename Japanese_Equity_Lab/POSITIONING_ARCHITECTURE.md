# Positioning / 需給 Data Architecture(Phase4C)

このDocumentは`lib/positioning/`の設計判断をまとめる。実装詳細は各Moduleの
Docstringを参照し、ここでは全体像とSourceを跨いだ設計判断のみを記す。

## 目的とScope

投資家ポジション・信用需給・空売り・株式貸借・売買主体・株主構成変化・流動性
等をPIT-safe/source-aware/reproducibleな形でこのLabへ取り込むためのData
Foundation。**Investment Signal(Short Squeeze Score・Overhang Score・
Crowding Score等)・BUY/SELL判定はこのPhaseのScope外**であり、`lib/
positioning/`のどのModuleも生成しない(DECISIONS.md D0054参照)。

「Raw/Canonical Data -> Point-in-Time safe observation -> Source-specific
normalization -> reusable as_of view」までがこのPhaseの範囲。

## Long-form、既存PIT Primitiveの再利用

`PositioningRecord`(`lib/positioning/model.py`)はentity × metric × period ×
source単位のLong-form 1レコードであり、Wide Tableを作らない。共通化するのは
identity/time/value/unit/frequency/provenance/availabilityの構造までであり、
`metric_type`(Economic Meaning)はSource固有のまま保持する(信用買残・空売り
比率・海外投資家売買代金等を単一の`positioning_score`へ潰さない)。

PIT/Revision管理は新しいPrimitiveを作らず、`lib.evidence.model.
RevisionHistory`/`SourceVersion`/`AvailabilityBasis`/`ValueAvailability`を
そのまま再利用する(`lib.fundamentals`と同じPrimitive)。`lib/positioning/
normalize.py`の`build_revision_histories()`はSource非依存であり、Source固有の
Availability Semantics(いつ利用可能になったと言えるか)は呼び出し側が
`resolve_available_at`Callbackとして明示的に渡す設計にした(normalize.py自身は
どのSourceの`available_at`計算方法も知らない、Source Integration Skill v1
SOURCE-001の精神)。

## Observation Period != Availability

`observation_start`/`observation_end`(このMetricが対象とする観測期間)と、
それがいつ利用可能になったか(`SourceVersion.available_at`)は別軸。週次
データの週初日からの利用可能扱い・月次データの月内全期間利用可能扱いは
いずれも禁止する(Period-end leakage禁止)。`lib/positioning/view.py`の
`positioning_as_of()`はこの分離を`RevisionHistory.as_of()`の`available_at`
基準フィルタへ委譲するのみで、独自のPeriod解釈ロジックを持たない。

## Source #1: Price/Volume-derived Liquidity(`lib/positioning/derived/price_derived.py`)

既存`lib.schemas.price_data.RawOHLCVBar`/`AdjustedOHLCVBar`(J-Quants
`/v2/equities/bars/daily`経由で既にCONNECTED)から、追加の外部Source統合
無しに決定論的に導出する。`TURNOVER_VALUE`(売買代金、close×volume、未調整
Rawから算出、単日)と`VOLUME_MOVING_AVERAGE_ND`(トレーリングN日平均出来高、
株式分割調整済みAdjustedから算出、window/minimum_periodsを明示Parameter化)
の2 Metricを実装した。

**Availability**: `session_close_at(observation_end)`(東証大引け時刻)を
`AvailabilityBasis.INFERRED`として使う。これは新しい規約ではなく、既存
`lib.schemas.price_data.provider_event_available_at()`
(AdjFactor由来Corporate Action Eventの利用可能時刻)や`lib.backtest.engine`
が`PointInTimeRecord.available_at`として既に採用している確立済みの規約を
そのまま再利用したもの(「その日のBarデータ自体が取得可能になる時刻」という
同じ論理)。

**market_public_atは常にNone/UNKNOWN**: 価格Barの取引そのものには、個別の
「公表」時刻という概念が無い(取引自体が終日Publicに行われている)ため、
確認できないA系統Timestampを推測で埋めない。

## Source候補(未実装、NOT_IMPLEMENTED)

Phase4C開始時点で`data-source-researcher` Agentが調査した4件のJ-Quants
Positioning Endpoint候補(`lib/positioning/catalog.py`に`NOT_IMPLEMENTED`
Descriptorとして登録済み):

| dataset_id | 対象 | 判明した制約 |
|---|---|---|
| `jquants_weekly_margin_interest` | 銘柄別信用取引週末残高 | Standard Plan以上が必要(未検証)、Publication Lag不明 |
| `jquants_short_ratio` | 業種別空売り比率 | Standard Plan以上が必要(未検証)、業種単位で銘柄別ではない |
| `jquants_short_sale_report` | 個別銘柄空売り残高報告(0.5%以上) | Endpoint Path自体が2つの検索結果で矛盾、未解決 |
| `jquants_trades_spec` | 投資部門別売買状況 | 唯一Light Plan(現契約)で利用可能な可能性、ただし単一の未検証情報源のみ |

いずれも実装しなかった理由: 全ての情報がWebSearch由来のSEARCH-SNIPPET-
DERIVED(UNVERIFIED)であり、公式Documentへ直接接続できていない(このSession
自身のNetwork Egressが一貫してBlockされているため、`EDINET_SOURCE_
ONBOARDING.md`と同じ制約)。Field名・Wire Schema・Publication Lag・Revision
表現のいずれも未確認のまま実装すると、Fundamentals(Phase4A)で実際に発生した
Field名推測ミスと同種のRiskを繰り返すことになる(推測禁止原則、Phase4C要件
§5/§28)。詳細は`DECISIONS.md`「D0054」・`VALIDATION_BACKLOG.md`参照。

JPX(東証)がこれらのDataを自社Website上で直接公開していることも確認した
(信用取引残高・空売り集計・投資部門別売買状況、いずれもPUBLIC_BUT_MANUAL、
URL PatternがScriptによる自動取得に適しているか未確認、特に空売り集計日次
PDFは日付ごとに不透明なHash的Path segmentを持ち単純なTemplate化ができない
可能性が高い)。JPX直接ソースはCatalogへは登録していない(技術的形状が
Endpoint Path・Format双方で未確認であり、構造化Descriptorとして記述するには
時期尚早と判断、`VALIDATION_BACKLOG.md`に候補として記録するに留めた)。

## Entity Mapping

Source #1(Price-derived)は`RawOHLCVBar`/`AdjustedOHLCVBar`の`code`
(既に`lib.data_sources.ticker_codes`で正規化済みのLab内部Code)をそのまま
`entity_code`へ使う。Company名やURLからのTicker推測は一切行わない。将来
J-Quants以外のPositioning Sourceを追加する場合、Provider識別子が異なれば
既存`lib.sources.entity_registry.EntityRegistry`(PIT-aware Identifier
Mapping)を再利用する(Phase4Cでは新規Entity Mapping機構を作らない)。

## Common Coreへ含めないもの

Compliance判定・URL Safety等(Company IR固有)と同様、Positioning固有の
Semantics(Frequency解釈・Window/minimum_periods計算・Source固有Field名)は
`lib/positioning/derived/`(または将来`lib/positioning/providers/`)配下に
閉じ込め、Common Core相当の`lib/positioning/model.py`/`normalize.py`/
`view.py`へは一切追加しない。

## Validation Status(実装状況とは別軸)

`ImplementationStatus`(Catalog Schema上の正式なField)とValidation Status
(FIXTURE_VALIDATED/LOCAL_VALIDATED/LIVE_VALIDATED/PENDING/EGRESS_BLOCKED)を
分離して記録する(Phase4C要件§25)。そのためだけの新規Schema Fieldは追加
せず、`DatasetDescriptor.known_limitations`への自由記述で表現する。Source #1
(price_derived_liquidity)は`implementation_status=CONNECTED`
(上流のJ-Quants Price Bar Connection自体は既にCONNECTED実績あり)だが、
Validation Status=`FIXTURE_VALIDATED`(合成Bar Dataでの検証のみ、この
Round自身では実J-Quants Dataに対するEnd-to-End Local Validationは未実施)。
