# 13_tests/fixtures/

`synthetic_jquants_daily_quotes.json` は**合成データ**です。実際の株価ではありません。

このセッションはネットワークポリシーによりJ-Quants等の外部APIへ疎通できないため
(`api.jquants.com`・Yahoo Finance・`example.com`等いずれも接続不可を確認済み)、
Phase2のPipeline全体(Data -> Feature -> Signal -> Decision -> Execution -> Return ->
Benchmark比較 -> Experiment Registry)が最後まで正常に動くことを、`FixtureDataSourceAdapter`
経由でこのfixtureを使って検証した。`FixtureDataSourceAdapter`と`JQuantsAdapter`は同じ
`DataSourceAdapter` Interfaceを実装しているため、Backtest Engine側のコードは
呼び出し先を一切区別しない。実際のJ-Quants接続での検証は、ローカル環境で
`.env`にJQUANTS_REFRESH_TOKENを設定した上で `scripts/jquants_lab_pipeline.py --source jquants`
を実行して行うこと。

内容:

- `daily_quotes`: 3銘柄分の合成日次OHLCV(7203/6758は右肩上がり、9984は右肩下がり)
  + 合成Benchmark系列(`TOPIX_SYNTH`、実際のTOPIXではない)
- `trading_calendar`: 2026-01-05から130暦日分(平日)のうち2日を「祝日相当」の
  休場日として明示(土日以外の休場をCalendarデータから処理できることを示すため)

## `portfolio_scenario.json`(System Behavior Test専用、Strategy Performance評価には使わない)

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
