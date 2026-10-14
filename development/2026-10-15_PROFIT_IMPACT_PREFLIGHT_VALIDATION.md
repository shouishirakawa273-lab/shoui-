# 入力確認機能：実装・独立検証記録

2026-10-15。branch codex/profit-impact-preflight、base fba60cbc42b76021000a24663dce34fd51b13aea（PR #4）。
新規preflight module、CLI、専用test、仕様、本文書、DEC末尾追記。元production/test/manifest・凍結288ファイルは無変更。

## 実装と使用

既存ProfitImpactRequest保存形式のJSONを入力し、raw payload hashとschemaを確認する。
`python Japanese_Equity_Lab/scripts/profit_impact_preflight.py request.json`
stdoutへ決定的JSONreportを返す。invalid schema/JSONはstderrへerror種別のみ、exit2。
構造的archive判定と、部分的計算不足一覧を分離。計算NOT_EVALUATED、原bytes/意味未確認、storehistory未評価を固定表示。
source authority/values_verifiedはcaller申告として表示し、未知方向・時刻・limitationsを保持する。
JSON duplicate keys、NaN/Infinity、rawhash改ざん、duplicate componentIDs、参照/identity不整合を検出する。
元ファイル・store・出力ファイルを書き込まず、CLIのlocalimportでbytecodeも生成しない。
ネットワーク、利益計算、shock生成、時刻補完、営業利益変換は行わない。

## 担当と固定証拠

設計監査は仕様を事前確認し、実装後も固定8bfb90b45b5479ed0f81df459ec64423261e6b21を読取監査。
コード書込は実装担当1人。主担当は仕様・履歴・公開。別担当が差分とテストを独立確認した。
独立検証の初回pytestは8bfb90bで98 passed / 1 deselected、exit0、終了HEAD/status clean。
除外1件は"locked"フィルタが通常の"blocked"名に一致したもので、禁止テストではない。
追加riskcase確認中に主担当が修正担当を起動し、変更が観測された。その追加実行は固定SHA合格証拠へ採用しない。
限定修正はunknown driver+unitNoneを明示的に不足検出する条件とtest1件。
closure SHA e69304c615ae45111d78433a8d9d20068d6fcd03で、独立担当が新caseと前回除外caseの2nodeidを実行し2 passed。
closure終了HEAD一致・status clean、凍結288パスの変更0。全100件をclosureで一括実行したとは主張しない。
実装担当の最終専用18件、ruff/format、strict mypy成功。初回とclosureの独立判定に重大な未解決findingなし。

rawlogsはチャットworkspaceのvalidation/preflight-independent-tests.log、preflight-independent-riskcases.log、preflight-independent-closure.log。
これらのローカルログをGitHub rawartifactとして公開済みとは主張しない。本記録はその証拠の要約。
H0001/Locked Test未実行。マージ/FROZEN未実施。

## 限界と進捗

検査は部分的で、原calculatorの全失敗条件との同等性を保証しない。publication date/timezoneの日付整合、optional proof chronology/reference、composition/context等の全条件は列挙しない。
archive STRUCTURALLY_READYは保存実行結果でも、過去storeとの整合合格でもない。
今回完成したのは小さな入力診断機能1つ。完成品の観測下限約18ポイントを、この機能だけで全体率へ格上げしない。
G1/G5未確認、G2/G3/G4未受入を維持。実会社計算や全体の再現実行へは残作業がある。
次の通常作業は実会社手動入力bundleの保存条件を、この診断で確認し、保存可能な範囲と計算保留条件を固定すること。
公開後のbranch/PR/CI状態は別途追記する。
