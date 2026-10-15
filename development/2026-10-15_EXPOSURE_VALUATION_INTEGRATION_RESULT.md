# 合成exposure→営業利益forecast→valuation：独立検証結果

ユーザーの続行指示による限定開発。base a698832337a9b0d70f0a1a8c09cd74769ec60f2d（PR #3）。
レビュー対象b0d2dd9972a32f23c9c3200b16029c9ff674ceef。
コード変更は新規integration test1fileのみ。仕様・本記録・DEC末尾追記を併せて保存する。
既存production/test/manifestと凍結288パスは無変更。資料追加探索・PR #4以降の合流はしていない。

## 確認できた接続

合成fixtureを使ってcompute_exposure_bridgeのbaseline_forecast/replay_forecastを既存evaluate_forward_valuationへ実際に入力した。
JPY営業利益100→120、倍率8、純負債50 JPY、株数10を同条件として、一株価値75→91、差16を独立算式で確認した。
式はEV=営業利益×倍率、equity=EV−net debt、per-share=equity/shares。
実replay営業利益を基準に、target/replay差とmoney quantumでの丸め契約も確認した。
未選択Bull/Bearのforecast/valuation経済値と元request hash/integrityが不変。
成功入力から倍率のavailabilityだけ、または純負債availabilityだけをcutoff後へ移すとPIT_INVALIDでscenario出力なし。

## 独立性と実行証拠

1実装担当が新testを書き、別の設計監査が事前仕様と固定実装を読取確認、別の検証担当が固定SHAを独立実行した。
初回判断前に実装の自己評価を監査/検証担当へ渡していない。検証中はコード書込停止。
独立実行はnewintegration test、既存company_exposure_bridge、既存valuation_forward_reverseの明示3files。
結果122 passed / 1 deselected、exit0。開始/終了HEAD一致、status clean、凍結288変更0、production変更0。
除外nodeidはtest_valuation_forward_reverse.py::test_modules_do_not_touch_h0001。
これはsource textを調べる既存guardでありH0001研究の実行ではないが、独立確認では厳密なnodeidで除外した。
実装担当は専用3件と関連suite、ruff/formatを確認。独立ログはチャットworkspace validation/exposure-valuation-independent-tests.log。
設計監査・独立検証とも重大findingなし。追加修正・全面再レビューは不要。

## 認定範囲と進捗

新たに証明したのは、既存3層の合成module接続が検証可能なこと。新規の本番評価機能を実装したわけではない。
実会社、マクロeventからの自動入力、原PDF、税引前利益接続、完全E2E、historical PIT、因果予測、期待returnは未認定。
製品G1/G5未確認、G2/G3/G4未受入を維持。5/7工程を完成品71%としない。
未統合枝を含む約18ポイントの静的確認下限と、実会社完成率を区別する。今回の証拠だけで全体の完成率を引き上げない。
マージ/FROZEN、H0001研究/Locked Test、D0111は実施していない。
公開後のPR/CIはlocal実行と別に確認する。
