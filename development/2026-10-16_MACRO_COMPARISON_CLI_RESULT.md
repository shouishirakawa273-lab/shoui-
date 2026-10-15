# 保存計画からの比較操作 実装結果

開始113a0c54dd0030ae96cc478b8cb0c8c837980fbf（Draft PR #10）。
独立監査・検証対象11f72499906ae33128e66cfa55beacbf824321a8。技術受入可能、未merge・未FROZEN。

新input.pyは既存5record codecに渡す前に全field/nestedの型・aware時刻・有限Decimal文字列・enumを検証。
復元hashを確認し、未知/欠落field、重複JSONkey、暗黙型変換、改竄を拒否する。
macro_compare.pyは保存計画と明示samplesを読み、実現在UTCで既存比較APIを呼ぶ。
全結果とhash/計算版/由来未認証表示をJSON出力。入力/storeを変更せず、未知pathを作らない。
欠測はnullのまま既存APIへ渡す。PIT/identity/rosterの判定や既存計算は変更していない。
利用commandと入力schemaは同日MACRO_COMPARISON_CLI_SPEC.md。

## 独立結果

- 設計担当は固定SHA差分4新規fileと仕様を確認し重大阻害なし。test実行・書込なし。
- 検証担当は同SHAでtest_macro_comparison_cli.py/test_macro_experiments.py/test_macro_plan_persistence.pyのみ実行。
  136 passed/exit0、前後SHA同一、status clean。コードwriterの自己評価を先に渡していない。
- 独自probeは空samples→全roster不足理由、結果hash、異cwd CLI、input/store byte不変を確認。
- 凍結288件は開始/固定Git blob同一、固定/working Git差分なし。
  初回事前確認がCRLF/LF生bytes差で停止した際はpytest未実行。これは凍結変更と扱わず、
  raw bytesとGit blobの違いをfrozen.jsonへ分離記録し、初回テストを実行した。
- 初回レビューで阻害なし。closure/全面再レビュー/追加テスト反復は不要。

証拠: development/evidence/macro-comparison/{tests.log,frozen.json,probe.json}。
ログは実引数/cwd/隔離TEMP/TMP/exit/前後SHAを保持する。H0001/Locked Test、ネット取得、merge/FROZENなし。

## 範囲と未充足条件

既存APIの入力・実行経路を補完したもので、D0110受入要件や実証認定を追加していない。
今回確認したデータは合成。実予測器の定義、実consensus/初報/市場観測、十分な前向き履歴は不足。
hashは内部整合性であり、原資料や過去時刻の真正性を認証しない。完成品全体率は未算定。
既存Draft stackに依存し、未merge文書を正式FROZEN正本と扱わない。
