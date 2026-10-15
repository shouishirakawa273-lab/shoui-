# D0110.4 保存計画と明示入力による比較操作

開始113a0c54dd0030ae96cc478b8cb0c8c837980fbf。D0110対象、D0111/新モデル/データ取得対象外。
既存比較APIの操作経路を補完する。D0110の受入要件自体を追加するものではない。
計算/PIT/凍結288ファイルを変更しない。

## 受入条件

- 新規CLIは保存計画をread_planで読み、明示JSON samplesを既存compare_macro_forecastsへ渡す。
- 入力はschema_versionとsamplesのみ。各sampleはevent/consensus/release/prediction/snapshot/syntheticのみ。
  event必須、他4recordは明示null可。syntheticはbool必須。レコードは既存の全fieldを損失なく扱う。
- 未知/欠落field、重複JSONkey、不正型、非有限数、naive時刻、改竄hashを拒否。暗黙str/int変換は禁止。
  nested forecast等も厳密に検証し、既存APIの経済的identity/PIT判定は重複再実装しない。
- 不足・不整合が既存APIで理由付き判定される場合、その理由とstatusをそのままJSON出力。
  出力は全比較結果/hash/計算版、由来未認証表示を保持する。実証認定を追加しない。
- 評価時刻は実現在UTC。過去時刻指定、欠測の捏造、将来releaseを成熟扱いする経路なし。
- 入力/plan storeを書き換えない。未知pathを作らない。stdout JSON、異常はstderrと非zero終了。
  任意cwdから絶対scriptpathで実行できる。
- 合成完全pair/不足/null/PIT不整合/改竄/重複key/未知field/誤型/異cwd/不作成を明示allowlistで検証。
- 一人writer。固定完全SHAで読取設計監査・独立検証、初回1回と必要な阻害closure1回。
  H0001/Locked Test/merge/FROZEN禁止。既存comparison/凍結/既存test変更禁止。

実データ真正性、モデル定義、収集サービス、予測値の新規生成、統計認定は対象外。

## 利用経路とJSON表現

`python <repo>/Japanese_Equity_Lab/scripts/macro_compare.py --store <plans.jsonl> --id <experiment_id> --input <samples.json>`
を任意cwdから実行する。3path引数には必要に応じ絶対pathを使う。
入力形は `{"schema_version":1,"samples":[]}`。空配列は登録roster全件のMISSING_EVENTを返す。
各sampleはevent/consensus/release/prediction/snapshot/syntheticの6fieldを必ず含め、event以外のrecordはnull可。
recordのfieldは既存macro_events.storeとevaluation.storeの対応to_dict codecと同一。
Decimalは有限数を表すJSON文字列、datetimeはtimezone-aware ISO文字列、tupleはarray、enumは既存enum値文字列。
optional文字列はnull/空/空白も損失なく保持。各recordは既存hash規約のrecord_hash必須。
独自にhashが合う入力を作ることは出所認証にならず、出力も由来未認証のまま。
比較APIが返す不足/PIT不整合は理由付きJSON、形式不正/hash不一致はstderrと非zero終了。
時刻をCLI引数で指定する経路はない。結果は保存せずstdoutへ全fieldを出力する。
