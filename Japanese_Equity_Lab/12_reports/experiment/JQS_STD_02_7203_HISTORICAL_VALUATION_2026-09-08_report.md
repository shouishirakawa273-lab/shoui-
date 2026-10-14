# JQS_STD_02_7203_HISTORICAL_VALUATION — Standard-Era Re-Measurement Record

7203(Toyota)のLATEST_REPORTED_FY_PER_HISTORICAL_CONTEXT(Stage 3.15、
D0089/D0090)を、JQS-STD-01で確認したStandard-eraの拡張履歴(価格/指数:
2016-09-08〜、Financial Summary: 2016-11-08〜、DECISIONS.md参照)で
再測定した結果。**これは投資判断のEvidenceではない**(Research != Decision、
本Roundの目的はCoverage/Bottleneck測定のみ)。

Frozen Stage 3.15 Artifact(`scripts/verify_stage3_15_7203_closure.py`、
`01_data/raw/local_snapshot_input/`)は一切変更・再実行していない。本測定は
別Snapshot(`SNAP_JQS_STD_02_7203_*`、`01_data/raw/jquants/`、Gitignore対象)・
別Script(`scripts/jqs_std02_7203_historical_valuation_remeasurement.py`)を
使う独立した測定。

## Facts

- Entity: 7203(Toyota Motor)。As-Of Target: 2024-11-15T15:00 JST(Stage 3.15と同一)。
- Reused Production Logic(無変更): `lib.valuation.builder.build_latest_reported_fy_per()`・
  `lib.valuation.historical_context_builder.build_latest_reported_fy_per_historical_context()`・
  `lib.fundamentals.view.fundamentals_as_of()`・`lib.fundamentals.normalize.
  parse_financial_summary_payload()`/`build_revision_histories()`・
  `lib.market_calendar`・`lib.data_sources.jquants.JQuantsAdapter`・
  `lib.snapshot.RawSnapshotStore`。
- New Raw Snapshot(Immutable、`lib.snapshot.RawSnapshotStore`経由、APIキー非含有):

  | snapshot_id | record_count | content_hash(sha256) |
  |---|---|---|
  | `SNAP_JQS_STD_02_7203_equity_bars` | 2051 | `10e5d4953a5e4e147bd99887460fc613be13379b37859db5425fc36ca7d69ad9` |
  | `SNAP_JQS_STD_02_7203_trading_calendar` | 3068 | `29182c3595c48232ff7149e0d5fffcbc75896a192482d79e3ce58b963b72f31c` |
  | `SNAP_JQS_STD_02_7203_financial_summary` | 41 | `ba6c339b043a43220018542a1628b1442ae8ace90d0b4d79cf384699ee43582e` |

- Raw History Acquired: Price/Calendar from 2016-09-08(JQS-STD-01確認境界)、
  Financial Summary from 2016-11-08(実観測、from/toで絞り込まれない)。

## Orchestration Note(Production Code変更なし、§5)

拡張履歴には、Toyotaの会計基準移行(旧DocType `*_Consolidated_US`が
`parse_financial_summary_payload()`の既知DocTypeパターンと一致せず
`accounting_standard=UNKNOWN`へfail closedする、既存Parserの意図した挙動、
無変更)により、実績FY EPSのSeries(`series_id`)が2件に分かれていることを
観測した(`actual_eps_series_count=2`)。旧Frozen Harnessは単一Seriesを
前提としていたが(狭い2020-2026 Windowでは会計基準移行前のDataが含まれず
問題化しなかった)、本Roundでは呼び出し側(測定Script)で「各Anchor時点で
Series横断的にcurrent_period_endが最も新しいVersionを採用する」という
選定Logicを追加した——これは`historical_context_builder.py`自身の
Docstringが明示する「Anchor選定・EPS/Price取得はOrchestration側の責務」
「複数のFY Denominator RegimeをHistorical Distributionへ混在させること
自体はLATEST_REPORTED_FY_PERのMetric Semantics上正しい」という既存設計
方針の範囲内であり、`lib/valuation/*`・`lib/fundamentals/*`いずれも
1行も変更していない。

## Measurement Result(実測値)

| 指標 | Frozen Stage 3.15(旧) | JQS-STD-02(新) |
|---|---|---|
| sample_count(n) | 30 | **82** |
| first observation(as_of) | 2022-05-31T15:00 JST | **2017-05-31T15:00 JST** |
| last observation(as_of) | 2024-10-31T15:00 JST | 2024-10-31T15:00 JST(不変) |
| 表現期間(年) | 約2.42年 | **約7.42年** |
| historical_min | 6.947860304968027545499262174 | 6.947860304968027545499262174(不変) |
| historical_median | 10.23607659698874433562344686 | 10.24322267606404264701257864 |
| historical_max | 21.12887947846436730372764250 | 21.12887947846436730372764250(不変) |
| current_per | 7.285347324698037929715253867 | 7.285347324698037929715253867(不変、同一As-Of/EPS/Price) |
| current_percentile | 3.333333333333333333333333333% | **1.219512195121951219512195122%** |
| current_minus_historical_median | -2.950729272290706405908192993 | -2.957875351366004717297324773 |
| context_status | PARTIAL | PARTIAL(不変) |
| distinct_denominator_regime_count | 3(FY2022/3=12、FY2023/3=12、FY2024/3=6) | **8**(FY2017/3〜FY2024/3、詳細下記) |

新Denominator Regime内訳(`context_record.denominator_regimes`実測値):

| fiscal_period_end | observation_count |
|---|---|
| 2017-03-31 | 12 |
| 2018-03-31 | 12 |
| 2019-03-31 | 12 |
| 2020-03-31 | 12 |
| 2021-03-31 | **4**(Corporate Action Guardにより一部Reject、下記参照) |
| 2022-03-31 | 12 |
| 2023-03-31 | 12 |
| 2024-03-31 | 6 |

`current_per`が新旧で完全一致していることは、新規取得したRaw Snapshotが
2024年時点の価格・EPSについてFrozen Stage 3.15 Snapshotと整合しているという
強いInternal Consistency Checkとして機能する(同じEntity/同じAs-Of/同じ
Denominator選定であれば同じ結果になるべきで、実際に25桁以上一致した)。

## Rejected Observations(§10/§11、価値ある情報として記録)

- `attempted_anchor_count=98`(2016-09〜2024-10の完了暦月)のうち:
  - `unavailable_denominator_count=8`(2016-09〜2017-04の8か月、FY2017/3
    実績報告(市場公表 ~2017-05)がまだ利用可能でないため除外)。
  - `corporate_action_excluded_count=8`(Toyotaの2021-10-01 Share Split
    関連と推定される、FY2021/3実績(period_end=2021-03-31)を分母とする
    Anchor月のうちSplitを跨ぐWindowを持つもの。この結果、FY2021/3 Regimeは
    本来12件に達しうるところ4件のみとなった——Raw/Adjusted Price定義を
    混在させない既存Guard[`has_share_basis_action_in_window`]がそのまま
    正しく機能した結果であり、Guardを緩めていない)。
  - `sample_count=82` = 98 - 8 - 8(Bookkeeping一致、Builder自身の
    Defense-in-depth Checkで再検証済み)。
- `duplicate_period_vintages_observed=true`: PL系Metric(sales/operating_
  profit/net_profit/ordinary_profit/eps)のうち、少なくとも1つのSeriesで
  同一`series_id`に複数Versionが存在することを観測した(拡張履歴で新たに
  可視化された、狭いWindowでは出現しなかった事象)。
- `revision_relationship_resolved=false`: `build_revision_histories()`は
  設計上常に`supersedes_version_id=None`(「関係不明」として保持、D0043)
  のため、これは既存設計通りの結果であり本Roundで新たに発見した欠陥ではない。

## Coverage Classification(§9)

`lib.valuation.model.HistoricalContextStatus`のDocstringが明示する通り、
v1 Builderは`PARTIAL`のみを生成し、`SUPPORTED`への昇格基準(Window長・
Regime数・Source Vintage検証状況等)は「このStageでは未定義・未実装」と
既に明記されている(D0079/D0087/D0088から継続する原則)。したがって:

- `COVERAGE_CLASSIFICATION_RULE_MISSING = NO`(推測で新設する必要はない、
  既存Docstringに既に明文化されたRuleがある)。
- `OLD_COVERAGE_STATUS = PARTIAL`
- `NEW_COVERAGE_STATUS = PARTIAL`(Sample数が30→82に増えても、Rule自体が
  「Sample数だけを理由に機械的にSUPPORTEDへ格上げしない」と明記している
  ため、この実測結果はRule通りであり異常ではない)。

## Bottleneck Re-Measurement(§15)

**PARTIALLY_RESOLVED**。

- Resolvedな部分: Stage 3.15 Artifactが記録していたDataGap
  (「Historical Contextは存在するが約2.4年のみで、より長いHistoryが不足
  している」)は、実測ベースで解消した——表現期間は約2.42年→約7.42年、
  Sample数は30→82(2.7倍)。これは推測ではなく、既存Production Builderに
  実際の拡張Raw Dataを通した結果として直接観測した。
- Resolvedしていない部分: `context_status`(PARTIAL/SUPPORTED)というArtifact
  自体のCompleteness分類は、Sample数・Window長を理由に変わる設計になって
  いない(v1 Builderの既存Docstringで明示的にDeferred)。したがって
  「より長いHistoryがあればSUPPORTEDになる」という期待自体が、現在の
  Architecture上そもそも成立しない——これはStandardへのUpgradeでは解決
  できないSeparate Bottleneck(SUPPORTED昇格基準の未策定)である。
- 副次的に新たな複雑性(会計基準移行によるSeries分岐・Duplicate Period
  Vintage)が可視化されたが、これは既存Guard(Corporate Action Window・
  Fail-Closed DocType分類)が正しく機能した結果であり、隠れた欠陥ではない。

## Efficiency Decision(§16)

**A. No valuation code changes needed; reuse existing builder going forward.**

理由: `lib/valuation/*`・`lib/fundamentals/*`は本Roundで1行も変更して
いない。既存Builderは拡張履歴をそのまま正しく受理した(会計基準Series分岐
への対処はOrchestration層[測定Script]の責務内で完結し、Builderの契約
[要件v1]を一切変更する必要が無かった)。`SUPPORTED`昇格基準の策定は
別Topicであり、本Round(Coverage測定のみ)のScopeでは着手しない
(Bを選ばない理由: 「1件の小さなFollow-up」を要求するほどの具体的な
production Blockerは見つからなかった。Cを選ばない理由: 長期Historyは
実際にSample数・Window長という具体的な改善をもたらしており「価値が
薄い」とは言えない)。
