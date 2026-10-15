# 合成exposure→営業利益forecast→valuation接続確認

開始SHA: a698832337a9b0d70f0a1a8c09cd74769ec60f2d（PR #3）。
ユーザーの「続き」に基づく自律開発の小工程。既存の資料調査上限は維持し、追加公式資料の探索はしない。
対象は新規integration test1ファイルと仕様・結果の文書、DEC末尾の追記のみ。production/FROZEN/既存test変更なし。
PR #4/#5/#6を合流せず、PRETAX、実会社データ、期待return、D0111は扱わない。

## 受入条件

1. PR #3のsynthetic helperを合成と明記して使用し、同一会社識別子・期間・cutoffのbaseline/replayを得る。実会社開示値として表現しない。
2. bridge SUCCESSと丸め差/quantum契約を確認。同一multiple/net debt/sharesでbaseline_forecast/replay_forecastを既存evaluate_forward_valuationへ渡す。
3. 金額通貨・単位を明示し、選択scenarioの実replay利益値から独立算式を使ってEV・equity・per-share値と差を確認する。原targetとreplayの微差を丸め契約なしに同一視しない。
4. 非選択scenarioのforecast経済値とvaluation経済値は変わらない。result IDs等の来歴fieldは同一を要求しない。
5. 成功ケースからmultipleまたはbalance-sheet availabilityだけをcutoff後に移し、PIT_INVALIDとper-share成功結果なしを確認。異なる不正を同時に投入しない。
6. baseline入力hash不変。利益指標は合成連結営業利益を維持し、税引前利益のラベル変換をしない。

実装担当が新規testを書き、別の検証担当が固定commitを独立に確認する。設計監査は事前仕様を確認済み。
対象testと関連する既存bridge/valuation testだけを必要に応じて実行する。H0001/Locked Testは実行しない。
レビュー1回＋阻害解消確認1回まで。レビュー中は書込を停止する。
成功は合成module接続の検証であり、実会社、完全E2E、過去PIT、因果予測、期待return、製品Gate合格ではない。
マージ/FROZENは行わず、結果はGitHubへ保存する。
