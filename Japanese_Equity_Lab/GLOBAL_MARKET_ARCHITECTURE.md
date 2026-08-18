# Global Market Data Architecture(Phase4E-1)

このDocumentは`lib/global_market/`の設計判断をまとめる。実装詳細は各
Moduleのdocstringを参照し、ここでは全体像とSourceを跨いだ設計判断のみを
記す。

## 目的とScope

海外の株価指数・為替・国債利回り・コモディティ・Volatility Indexを
PIT-safe/timezone-aware/source-aware/reproducibleな形でこのLabへ取り込む
ためのData Foundation。**Market Regime判定・Investment Signal・
日本株結論(「NASDAQ下落=日本IT株SELL」等)はこのPhaseのScope外**であり、
`lib/global_market/`のどのModuleも生成しない(DECISIONS.md D0056参照)。

「Official Global Market Source -> Raw Observation -> Canonical
GlobalMarketRecord -> Revision-aware History -> Pure as_of View」までが
このPhaseの範囲。

## Repository Reality Check(実装前に確認した既存資産)

- `lib.market_calendar`は日本市場の休日・取引日判定に特化しており、
  Timezone処理は**固定UTC+9 Offset**(`timezone(timedelta(hours=9))`)で
  実装されている。これは日本にDSTが無いため正しいが、米国/欧州市場へ
  そのまま再利用すると**DST期間中は1時間ズレる**ため、Global Market用に
  流用しなかった(下記「Timezone/DST」節参照)。
- `lib.sources.catalog.DataCapability.GLOBAL_MARKET`はPhase3Dの時点で
  既に定義済みだった(未使用のまま)。新規Enum追加不要だった。
- `lib.evidence.model.RevisionHistory`/`SourceVersion`/
  `AvailabilityBasis`/`ValueAvailability`/`Frequency`はPositioning/
  Macroが再利用してきたPrimitiveであり、Global Marketもそのまま再利用
  した。Global Market専用のVersioning Primitiveは作らなかった。
- 既存Repositoryに海外市場Dataへの接続は一切無かった(Positioningの
  Price-derived Seriesのような「ゼロリスクで再利用できる既存接続」に
  相当するものが無い)。

## Timezone/DST(このPhase最大の設計論点)

`GlobalMarketRecord.market_timezone: str`はIANA Timezone名(例:
`"America/New_York"`)を保持する。`lib.market_calendar`の固定Offset方式は
**採用しない**。実際のAvailability判定(`resolve_available_at`)は
`zoneinfo.ZoneInfo`で実際にDST-aware datetimeを構築する(このRoundの
Test内で`_us_close_resolver`として実装、`GLOBAL-003`で1月=EST(UTC-5)と
7月=EDT(UTC-4)のUTC Offsetが実際に異なることを直接検証)。将来Adapterも
この方式を踏襲する(固定Offsetの独自実装を禁止)。

## Series Identity(Entity中心でもTicker中心でもなくSeries中心)

Price Index(`SP500_PRICE_INDEX`)とTotal Return Index(`SP500_TOTAL_
RETURN`)、Spot(`WTI_SPOT`)とContinuous Futures(`WTI_CONTINUOUS`)を、
表示名(「S&P 500」等)だけで同一Seriesと判定しない。`InstrumentCategory`
(EQUITY_INDEX/FX/RATE/COMMODITY/VOLATILITY_INDEX)は粗い分類のみを担い、
経済的な意味の区別自体は`IndexReturnType`/`PriceType`という**構造的・
閉じたVocabulary**のCommon Model Fieldへ昇格させた(Macroの
`SeasonalAdjustment`と同じ正当化根拠——Source固有のField名Mappingとは
異なり、これらは複数Sourceに横断して現れる経済的に意味のある区別軸)。
`series_code`(Provider公式Ticker/Symbol)は確認できた場合のみ保持し、
無ければ`None`のまま推測しない。

## series_idはCaller/Adapterの責務(Macro D0055の教訓を先取り適用)

`GlobalMarketRecord`自体は`series_id`の一意性を構造的に強制しない。
呼び出し側/将来Adapterが、Source・`metric_name`・`frequency`・
Instrument固有の軸(`index_return_type`/`price_type`)、そして**
`session_date`**を`series_id`へ一意に含める責務を負う。これを怠ると
`build_revision_histories()`のSeries_idのみによるGroupingが異なる
SessionのRecordを同一Seriesへcollapseさせ、過去のSessionが`*_as_of()`
から永続的に到達不能になる。この失敗モードはMacro Phase4Dの
skeptic-reviewer Findingと同型であるため、今回は独立して発見されるのを
待たず、実装と同時に`test_series_id_without_session_date_causes_cross_
session_collapse_known_limitation`としてPinning Testを追加した。

## Japan Decision-Time Leakage禁止(最重要PIT論点)

日本株Researchの`decision_at`(JST等)から見て、その時刻までに実際に
終了・観測可能だったGlobal Market Dataのみ使える。`global_market_as_of()`
は`decision_at`がどのTimezoneのtz-aware datetimeでも受け取り、Python
datetime比較の内部UTC正規化にPIT判定を委譲する(`lib/global_market/
view.py`)。同一瞬間をUTC表現とJST表現で渡しても判定結果が一致すること
(`GLOBAL-002`)、日本時間の同日朝には前日の米国市場Closeがまだ観測不可能
であり翌朝には観測可能になること(`GLOBAL-001`)を直接Testで検証した。

## Session Date != Availability

Equity Indexの`session_date`(例: 2026-08-18の取引日)はそれ自体では
Availabilityを意味しない。同日のUS Market Close以前は`None`を返す
(`GLOBAL-004`)。

## FXにEquity Close Semanticsを強制しない

FXは近24時間市場であり、Equityの16:00 Local大引けのようなSession Close
概念を強制しない。`resolve_available_at`はSource固有のCallbackであり、
FX用のResolverはEquity用と全く別のReference Time定義(例: Provider固有の
UTC基準時刻)を持てることを`GLOBAL-006`で確認した。実際のFX Providerの
Daily Close定義はProvider固有であり、このRoundでは特定のSemanticsを
Common Modelへ埋め込んでいない。

## Adjusted/Raw、Continuous Futures Roll、Total/Price Returnは推測しない

`AdjustmentStatus`(ADJUSTED/UNADJUSTED/PROVIDER_TRANSFORMED/UNKNOWN)は
既定`UNKNOWN`。Provider側の補正仕様が未確認の場合は推測で`ADJUSTED`等へ
倒さない。Continuous FuturesのRoll Methodologyはこのラウンドでは一切
実装せず(`PriceType.CONTINUOUS_FUTURES`という区別のFieldのみ用意し、
Roll自体のLogicは将来の別Derived Layerに委ねる設計を明記するのみ)。

## Currency/Unitは第一級かつ独立した軸

`currency`(USD/JPY等)と`unit`(index points/percent等)を混同しない。
Equity Index(`currency=None`、`unit="index points"`)とFX(`currency="JPY"`、
`unit="JPY"`)を同列に扱わないことを`GLOBAL-008`で確認した。

## Raw/Provenance、Current Historical API Risk

Raw値はimmutable。同一Session再取得時の値/Hash変化は、それだけで
「Revision」と自動判定しない(Macro/Positioningと同じRAW-002原則)。
`build_revision_histories()`は常に`is_correction=False`で`SourceVersion`
を構築し、時系列だけからRevision関係を推測しない。現在のHistorical API
Responseが過去のProvider Snapshotと同一である保証は無い(Known
Limitation、将来のForward Snapshot観測課題としてVALIDATION_BACKLOG.md
に記録)。

## as_of View、Determinism

`global_market_as_of()`はNetwork Access・現在時刻参照を一切行わない
Pure Function。同じ`RevisionHistory`集合・同じ`decision_at`なら常に同じ
結果を返す(`GLOBAL-011`)。

## No Investment Interpretation

`global_market_record_to_evidence()`が生成するEvidence Contentは
「{series_id}: {metric_name}({session_date}, {market_timezone},
{frequency})={value}」という機械的なFACT記述のみで、bullish/bearish/
buy/sell/好調/悪化/強気/弱気/輸出株/資源株等の解釈語を一切含めない
(`GLOBAL-012`)。`source.available_at`には常に`record.retrieved_at`を
使い、`market_public_at`へのFallbackは行わない(Fundamentals D0049/D0050
・Positioning/Macroと同じPIT-003原則)。

## Missing Is Not Zero

`raw_value=None`/`value=None`のRecordは`SourceVersion.value`が空文字列
`""`になり、`"0"`には決してならない(`GLOBAL-013`)。

## Naive Datetime Rejected

`GlobalMarketRecord.__post_init__`は`retrieved_at`/`observation_time`/
`market_public_at`のtz-aware性を検証し、`global_market_as_of()`の
`decision_at`と`build_revision_histories()`の`resolve_available_at`が
返す`available_at`もtz-awareであることを実行時に強制する
(`GLOBAL-014`)。

## Common Coreへ含めないもの

Source固有のSemantics(Field名Mapping・認証方式・Rate Limit対応・
Vintage/Revision実装)は将来`lib/global_market/providers/`配下に閉じ込め、
Common Core相当の`lib/global_market/model.py`/`normalize.py`/`view.py`
へは一切追加しない設計とする(Phase4B/4C/4Dと同じ境界原則)。

`AvailableAtResolver`パターン(`Callable[[RecordType], tuple[datetime,
AvailabilityBasis]]`)はPositioning/Macroと意図的に同型の独立実装として
`lib/global_market/normalize.py`へ再実装した(共通Protocol抽象化はしない
——各RecordのField名が異なるため無理な共通化はPremature Generalizationと
Phase4C/4D双方のskeptic-reviewerで判断済み)。

## このRoundで実装したSource

**なし**。`data-source-researcher` Agent(2026-08-18)がFRED(セントルイス
連銀)・ECB(Frankfurter経由)・CBOE・US Treasury・Yahoo Finance・Alpha
Vantage・Twelve Data・Nasdaq Data Link等を調査したが、このSession自身の
Network Egressが全ての公式Document URLへ一貫してBlockされており
(`EGRESS_BLOCKED`)、全ての情報がSEARCH-SNIPPET-DERIVED(UNVERIFIED)に
留まった。検索Snippetのみを根拠にAdapterを実装しない(Phase4E-1要件§8)。

## Source候補(未実装、NOT_IMPLEMENTED)

`lib/global_market/catalog.py`に5件のDescriptorとして登録済み:

| dataset_id | 対象 | Category | 判明した制約 |
|---|---|---|---|
| `fred_sp500` | FRED `SP500`(S&P 500 Price Index) | EQUITY_INDEX | FRED/S&P DJI間の2014年Licensing Agreementにより過去10年分Rolling Windowのみ(複数独立Snippetで収斂、未読)。Total Return版の存在有無UNCONFIRMED |
| `fred_dexjpus` | FRED `DEXJPUS`(USD/JPY、H.10由来) | FX | 「NY正午Buying Rate」という歴史的記述と2019年H.10算出方法変更の関係が未確認。市場実勢Rateとは別概念 |
| `fred_dexuseu` | FRED `DEXUSEU`(EUR/USD、H.10由来) | FX | DEXJPUSと同型の未確認事項。EUR/JPYは直接系列が無くCross Rate計算が必要(実装時は明示的Derived Value Pipelineとして設計) |
| `fred_dgs10` | FRED `DGS10`(US 10年国債利回り) | RATE | 米財務省がおよそ15:30 ET時点の気配値から算出という記述が見つかったが未読。個別値のSilent Restate有無は未確認 |
| `fred_vixcls` | FRED `VIXCLS`(CBOE VIX、原典CBOE・配信FRED) | VOLATILITY_INDEX | CBOEのRTH算出Windowは9:30am-4:15pm ET(Closeは4:15pm ETでありEquity市場4:00pm Closeと異なる) |

data-source-researcherはFREDを「単一APIキーでEquity Index/FX/Rate/
Volatilityを横断できるUmbrella候補」として最優先で推奨した。Commodity
(WTI/Brent/Gold/Copper)はSnippet上は有望な候補(特にLBMA AM/PM Gold
Fixは明確なSpot Benchmark)が複数見つかったが、Agent自身の推奨でも
次Round以降に見送られており、このRoundでは登録していない。

## Q7相当の所見: FRED/ALFREDのVintage Query機構(最重要の前向き所見)

data-source-researcher Agentの調査で見つかった最も具体的なPIT関連の
所見は、**FRED/ALFRED APIが`realtime_start`/`realtime_end`Parameterに
よるVintage Query機構を持つ**という記述(複数独立した第三者Wrapper
(`fredapi`等)のFRED API説明を通じた収斂、FRED自身のPageは未読)。もし
これが文書通りに機能するなら、これまでのLab Source(EDINET: Historical
Listがmutable、Macro: 5候補いずれもVintage機構の証拠見つからず)より
明確に強いPIT保証をProvider側から得られる可能性がある。**ただし、この
Mechanism自体を実際にFRED自身の一次文書またはLocal Live Callで確認する
ことが、次のAdapter実装より優先すべき検証項目**として記録する
(VALIDATION_BACKLOG.md参照)。

## Validation Status(実装状況とは別軸)

5候補全て`implementation_status=NOT_IMPLEMENTED`、Validation Status=
`DESIGN_COMPLETE_AWAITING_SPEC_VERIFICATION`(`lib/global_market/
catalog.py`の`known_limitations`へ自由記述、そのためだけの新規Schema
Fieldは追加しない——Positioning Phase4C/Macro Phase4Dと同じ方針)。
