# 06_backtests/

Experiment Registry・バックテスト結果。`lib/schemas/experiment.Experiment` /
`lib/registry/experiment_registry.ExperimentRegistry` に対応する。

- `experiment_registry.jsonl`: 追記専用(append-only)のExperiment記録
  (`ExperimentRegistry` は上書き・削除のAPIを提供しない)。`reproducibility`
  フィールド(run_id/dataset_hash/strategy_hash/config_hash/code_commit)で
  同一Inputからの再現性を検証できる。
- `provenance.jsonl`: 追記専用のProvenanceリンク台帳(`lib/registry/provenance.ProvenanceStore`)。
  Experiment -> Hypothesis -> Strategy -> Processed Dataset -> Raw Snapshot -> Source Request
  まで逆引きできる。
- 個別のBacktestレポートは `BT<連番>_<hypothesis_id>_<日付>.md`。

`scripts/jquants_lab_pipeline.py`(親リポジトリの`scripts/`)を実行すると、
Data取得からExperiment Registry記録・Provenance記録までを一本通しで実行できる
(`--source fixture`はネットワーク接続なしで動作確認用、`--source jquants`は
ローカル環境での実データ実行用)。

**良い結果だけを選択して表示しない**。`generated / tested / rejected / pending / paper / validated`
の分母を必ず併記する(`ExperimentRegistry.summary()`)。
