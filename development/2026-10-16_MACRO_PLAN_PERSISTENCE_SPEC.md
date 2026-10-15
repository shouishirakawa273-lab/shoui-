# D0110.4 実験計画の保存と操作

最新指示に基づく必須実装。起点313201e0ce0476265a1c37415289ec94fa83c3e0、branch codex/d0110-experiment-persistence。
既存比較機能のRegisteredMacroPlanを再起動後も同一内容で使えるようにする。独自予測器や実値を生成する機能ではない。

CLI register は実際の現在UTCのみで新規登録する。library store は正当に過去登録されたplanの保存復元も可能だが、過去登録の証明や数値・履歴の認定は行わない。

## 受入条件

1. 新規lib/macro_experiments/store.pyで既存D0107 AppendOnlyRecordStoreを再利用する。
2. plan全fieldとnested ExperimentSpec/EvaluationContractをJSONでlossless保存復元。元hash/計算契約を改竄しない。
3. 同一experiment IDは同一内容でも無条件reject。改竄hash、unknown/missingfield、wrongtype/boolean混同を拒否。
4. register_macro_planで再構成したcanonical planとの一致を検証。nested hash、登録前contract、roster、period/unit等既存契約を再利用。
5. 新規scripts/macro_plan.pyで明示JSON入力のregister/showを提供。test helperへ依存しない。
6. registerは実際の現在UTCを登録時刻として使用し、過去時刻入力を認めない。created_atを利用者に偽装させない。
7. event roster/window/model version/dimension/unit/contract/minimum/syntheticは利用者が明示。未指定値を科学的根拠なしに補完しない。
8. showは既存fileを読むだけで新dir/fileを作らない。未知ID/不正入力は非zero exitと理由、成功stdoutはJSON。
9. synthetic/observational/不足証拠を区別。plan保存は実験実行/性能認定/原資料認証ではない。
10. 専用test: 全field/hash再読込、duplicate、nested/outer tamper、strictschema、CLI異cwd、未来window必須、show無副作用。

既存production/tests/manifestとfrozen288は無変更。既存comparison.pyは変更しない。
新store/CLI/testのみと仕様/結果/DEC追記。ネットワーク取得なし、H0001/Locked Test/merge/FROZENなし。
1writer、固定SHA独立設計/検証、レビュー初回1回と阻害解消1回。任意改善は後回し。

## CLI/config schema and use

Run the absolute path to `Japanese_Equity_Lab/scripts/macro_plan.py` with Python from any working directory:

```
python <repo>/Japanese_Equity_Lab/scripts/macro_plan.py register --input <config.json> --store <plans.jsonl>
python <repo>/Japanese_Equity_Lab/scripts/macro_plan.py show --store <plans.jsonl> --id synthetic-plan
```

Paths passed as relative paths resolve against the caller's working directory. `register` writes one append-only record, `show` reads only. One writer at a time is required: existing D0107 persistence has no concurrent transaction/locking guarantee. Store hashes detect inconsistent records, not malicious rewriting with recomputed hashes or authenticity of source claims.

All keys below are required and additional keys are rejected, including `created_at`. JSON duplicate object keys are rejected. Strings must be nonempty except `horizon_rule`, which losslessly preserves any string including empty/whitespace or null; timestamps must be timezone-aware ISO strings. `minimum_samples` is a positive JSON integer (not boolean); `synthetic` must be JSON boolean. Roster is a nonempty unique string array. Contracts is a nonempty array with unique IDs and target periods. `metric` must be `ABSOLUTE_ERROR`; target must equal dimension. The registration window must start strictly after actual current UTC. Version is positive integer; horizon_rule is string or null. Contract and experiment creation timestamps are both the actual registration UTC, not the age of prior source material. CLI does not import preexisting contracts or permit backdating. Example is an UNVALIDATED SYNTHETIC schema illustration only; update future window before running. It is not a real CPI model, scientific sample-size claim, or a registered real experiment:

```json
{
  "experiment_id": "synthetic-plan", "event_type": "CPI", "dimension": "CPI_YOY",
  "unit": "percent", "entity_id": "US", "model_version": "UNVALIDATED_SYNTHETIC_V1",
  "event_ids": ["synthetic-event"], "minimum_samples": 1, "synthetic": true,
  "window_start": "2099-01-01T00:00:00+00:00", "window_end": "2099-02-01T00:00:00+00:00",
  "contracts": [{
    "evaluation_contract_id": "synthetic-contract", "evaluation_contract_version": 1,
    "target": "CPI_YOY", "target_period": "2099-01",
    "actual_truth_description": "synthetic first release", "metric": "ABSOLUTE_ERROR",
    "evaluable_at_policy": "after first release", "horizon_rule": null
  }]
}
```

The library store losslessly restores complete RegisteredMacroPlan, ExperimentSpec, and EvaluationContract fields, verifies nested/outer hashes, and rejects plans differing from register_macro_plan canonical reconstruction. Low-level store is suitable for restoring historically registered records; it does not itself certify historical registration. Use CLI for current registration. Successful stdout is the complete JSON plan; errors go to stderr with nonzero exit. This step stores plans only, not predictions, evaluation results, or verified source bytes.
