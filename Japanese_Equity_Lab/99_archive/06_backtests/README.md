# 99_archive/06_backtests/

Phase2.1で`BacktestMetrics`のフィールド(`sample_size`→`unique_tickers`への改名、
`signal_count`/`executed_count`/`unexecuted_count`/`execution_rate`/
`execution_outcomes`/`unique_entry_dates`の新設)を変更したため、Phase2A時点の
`experiment_registry.jsonl` / `provenance.jsonl`(合成データによるデモ実行結果)は
現行の`ExperimentRegistry`では読み込めなくなった。

削除はせず、ここへ退避した。`06_backtests/`には、Phase2.1のコードで再実行した
新しいデモ結果を改めて保存している。
