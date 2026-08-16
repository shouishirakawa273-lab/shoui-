# 99_archive/06_backtests/

`BacktestMetrics`のフィールドをPhase2完了後の指摘対応で2回変更したため、
その都度、現行の`ExperimentRegistry`では読み込めなくなった過去の
`experiment_registry.jsonl` / `provenance.jsonl`(いずれも合成データによる
デモ実行結果)をここへ退避している(削除はしない)。

- `*_phase2a_pre_metrics_schema_change.jsonl`: Phase2.1で`sample_size`→
  `unique_tickers`への改名、`signal_count`/`executed_count`/`unexecuted_count`/
  `execution_rate`/`execution_outcomes`/`unique_entry_dates`を新設した際に退避。
- `*_phase2_1_pre_execution_metrics_split.jsonl`: Phase2.2で`unexecuted_count`/
  `execution_rate`を廃止し、`policy_skipped_count`/`order_attempt_count`/
  `execution_failed_count`/`signal_to_trade_rate`/`order_execution_rate`へ
  再編した際に退避(Policy SkipとExecution Failureを区別するため)。

`06_backtests/`には、その時点の最新コードで再実行したデモ結果を改めて保存している。
