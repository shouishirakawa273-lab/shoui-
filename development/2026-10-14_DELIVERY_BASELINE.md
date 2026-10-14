# 開発開始：完成品棚卸しと最小経路の検証

対象はPRODUCT_ACCEPTANCEで定義したマクロ→会社業績→評価→シナリオ期待リターンの研究経路。
Lab全体の完成率ではない。2026-10-14、主担当・実装担当・設計監査・独立検証の4役を起動した。
実装担当はコード追加の必然性を検討し、既存会社fixture経路の限定確認を最小作業として選んだ。

## 固定対象

- 受入文書: 60019a0fe69e0ec49076c0653d3e0e0ad28e1cd0。
- 既存受入済み開発base: 071cff9c18632461c207a08c20e7c721a983221b。
- PR #3: a698832337a9b0d70f0a1a8c09cd74769ec60f2d。
- PR #4: fba60cbc42b76021000a24663dce34fd51b13aea。

各担当は固定commitを参照。PR #3/#4は兄弟branchであり、統合済み経路として扱わない。

## 初期棚卸し

以下は独立検証担当によるコード・テスト内容の読取評価案。領域内4成果物を均等配分。
0.25は直接支える実装契約を確認、0はこの完成経路に必要な成果物が未提供、未評価は証拠未調査。
既存の正式受入やCIを無効扱いするものではなく、今回独立に証明できた下限だけを数える。

| 領域（配分） | 成果物 | 確認下限 |
|---|---|---|
| 実データ20 | 会社数値/株価取得、元資料/版/hash、利用可能時刻/cutoff、実会社+macro vintage bundle | 0.25 / 0.25 / 0.25 / 未評価 |
| マクロ→業績25 | exposure/感応度、driver方向/範囲、baseline/共同適用/重複、会社業績接続 | 各0.25 |
| 評価/return20 | 同指標forecast接続、倍率/net debt/株数、scenario期待return契約、実会社統合artifact | 0.25 / 0.25 / 0 / 0 |
| 全体再現25 | immutable保存/replay、時点/版違反検知、別process全経路CLI、過去実会社E2E比較 | 0.25 / 0.25 / 0 / 0 |
| 説明/運用10 | 採否audit、lineage/tamper、全経路report/手順、独立監査運用 | 0.25 / 0.25 / 0 / 0.25 |

コード根拠: data_sources/jquants.py、fetch_jquants_local_snapshot.py、PR #3 company_exposure、PR #4 profit_impact model/calculation/store、base valuation/engine、evaluation/model、開発workflow。
PR #4のSMM fixtureは税引前・範囲/方向/過去availability等が未知。base valuationは営業利益を消費する。
scenario期待returnは既存のvaluation出力には存在せず、paper_tradeの同名入力fieldで代替しない。

この分解案で確認下限は17.5/100ポイント、未評価bundleは5ポイント分。
これは静的実装証拠の下限であり、単一branchで提供可能な完成品率ではない。未評価bundleだけの変動幅17.5〜22.5も将来完成率の予測ではない。
設計監査担当は異なる分解案で下限16.875、未評価32.5を提示した。差は成果物定義と探索範囲によるもので、平均して数字を作らない。
初期基準は上表を棚卸し候補として保持し、全体率の正式表示は未算定を維持する。次回は分解と未評価bundleの証拠を固定して更新する。
必須Gate: G1/G5未確認、G2/G3/G4未受入。完成品としての合格Gateはゼロ。

## 指定1件の実行

PR #4固定HEADで次の既存テストだけを実行した。
`python -m pytest Japanese_Equity_Lab/13_tests/test_profit_impact.py::test_company_table_fixture_retains_unknown_historical_times -q -p no:cacheprovider`
既存.venv、workspace-local TEMP/TMP、bytecode生成なし。結果は1 passed in 0.89s。
raw logはチャットworkspace validation/delivery-20261014-source-record.logへ保存。
ソース変更なし、実行後HEAD一致・作業ツリーclean。H0001/Locked Test未実行。

検証対象はfixtureからの保存・再読込・未知時刻保持・32/36/22億円の円単位正規化。
原PDFの再取得・意味の独立照合・実PIT計算・符号付き会社予測・営業利益接続は検証対象外。
synthetic helperのlimitationsが残るため、テスト生成物を実会社入力の正本へ昇格しない。

## 次の最小開発単位

新規の手動資料preflightは、入力資料の存在・hash・版・会社/期/指標・未知時刻と未充足条件を一覧化し、利益予測を生成しない範囲に限定する。
既存経路が不足する場合だけ新規script/testを追加し、凍結モジュールを変更しない。実会社履歴の時刻を補わない。
まず受入仕様を固定して設計監査し、実装担当1人が書込、別担当が固定SHAを検証する。
G3の期待return契約や全面的E2E runnerは後続計画であり、今回の小工程に混ぜない。

## 時間

今回の実テスト時間は0.89秒。棚卸し・調整を含むwall timeと開発作業量は別。
全体の完成時期はまだ未算定。受入準備の初期1.5〜5時間を全製品へ流用しない。
次のpreflight仕様/実装/検証は初期計画上1〜3時間、資料不足・権限待ちは別。実績で再見積もりする。
