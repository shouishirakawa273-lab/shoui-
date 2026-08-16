# 06_backtests/

Experiment Registry・バックテスト結果。`lib/schemas/experiment.Experiment` /
`lib/registry/experiment_registry.ExperimentRegistry` に対応する。

- `experiment_registry.jsonl`: 追記専用(append-only)のExperiment記録
  (`ExperimentRegistry` は上書き・削除のAPIを提供しない)。
- 個別のBacktestレポートは `BT<連番>_<hypothesis_id>_<日付>.md`。

**良い結果だけを選択して表示しない**。`generated / tested / rejected / pending / paper / validated`
の分母を必ず併記する(`ExperimentRegistry.summary()`)。
