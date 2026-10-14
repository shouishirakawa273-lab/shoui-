# 13_tests/fixtures/

`synthetic_jquants_v2_bars.json` / `portfolio_scenario_v2.json` は**合成データ**です。
実際の株価ではありません。Phase3A.1でJ-Quants API V2形状(`equity_bars`/`HolDiv`等)へ
全面移行した(V1形状の旧ファイルは`99_archive/13_tests/fixtures/`に退避、DECISIONS.md
D0031参照)。

このセッションはネットワークポリシーによりJ-Quants等の外部API・公式ドキュメントへ
疎通できないため(`api.jquants.com`・`jpx.gitbook.io`・Yahoo Finance・`example.com`等
いずれも接続不可を確認済み)、Pipeline全体(Data -> Feature -> Signal -> Decision ->
Execution -> Return -> Benchmark比較 -> Experiment Registry)が最後まで正常に動くことを、
`FixtureDataSourceAdapter`経由でこのfixtureを使って検証した。`FixtureDataSourceAdapter`と
`JQuantsAdapter`は同じ`DataSourceAdapter` Interfaceを実装しているため、Backtest Engine
側のコードは呼び出し先を一切区別しない。実際のJ-Quants接続での検証は、ローカル環境で
`.env`にJQUANTS_API_KEYを設定した上で `scripts/jquants_lab_pipeline.py --source jquants`
を実行するか、`LOCAL_DATA_FETCH_GUIDE.md`の手順で行うこと。

## `synthetic_jquants_v2_bars.json`(Pipeline Validation Fixture)

- `equity_bars`: 3銘柄分の合成日次Bar(7203/6758は右肩上がり、9984は右肩下がり)
  + 合成Benchmark系列(`TOPIX_SYNTH`、実際のTOPIXではない)。全行`AdjFactor=1.0`/
  `ExRT=null`(Corporate Action無しのシナリオ)。
- `trading_calendar`: 2026-01-05から130暦日分(平日)のうち2日を「祝日相当」の
  休場日として明示(土日以外の休場をCalendarデータから処理できることを示すため)

## `portfolio_scenario_v2.json`(System Behavior Test専用、Strategy Performance評価には使わない)

Portfolio Simulationの挙動(Policy Skip・Execution Failure・正常Execution/Exitの区別)を
確認するためだけの、より小さく意図的に作り込んだfixture。モメンタム等の間接的な条件では
なく、`_scenario.signal_dates`に列挙された日付でSignalを発火させる専用のsignal_fnと
セットで使う(`13_tests/test_portfolio_scenario.py`参照)。

- `PSIM_A` / `PSIM_B`: 異なる日付でSignalが出る2銘柄
- `PSIM_A`は保有中に2回目のSignalが出るよう設計(→`SKIPPED_POSITION_OPEN`)
- `PSIM_A`の3回目のSignalの執行日はOpenを意図的に欠損させている(→`UNEXECUTABLE_NO_OPEN`)
- `PSIM_A`の4回目・`PSIM_B`の1回目のSignalは正常にExecution/Exitが完了する
- `PSIM_BENCH`: 合成Benchmark系列(実際の指数ではない)

このfixtureの価格推移自体には投資判断としての意味はない(挙動確認用に設計された値)。

## V2 Golden Fixtures(Endpoint別のRawレスポンス形状確認専用)

以下は「Pipeline全体を通す」ためのものではなく、`convert.py`の各parser・
`LocalSnapshotAdapter`が個々のEndpointのレスポンス形状(``{"data": [...],
"pagination_key": null}``)を正しく扱えることを確認するための、小さく焦点を絞った
Golden Fixture(合成データ)である。

- `equities_bars_daily_v2.json`: `/v2/equities/bars/daily`。7203の3日分、うち中日を
  Corporate Action Event日(`AdjFactor=0.5`, `ExRT="1"`)として作り込んでいる。
- `markets_calendar_v2.json`: `/v2/markets/calendar`。
- `topix_bars_daily_v2.json`: `/v2/indices/bars/daily/topix`。
- `equities_master_v2.json`: `/v2/equities/master`。7203/6758/3626の3銘柄
  (Company Name/Ticker整合性チェックのテストにも使う)。

いずれもField名はユーザーがセッション内で明示したV2仕様に基づく実装であり、
このセッション自身が公式ドキュメントやAPIで検証したものではない
(README.md/DECISIONS.md D0031参照)。
