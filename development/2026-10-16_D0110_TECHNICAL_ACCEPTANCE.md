# D0110 技術受入と実証保留

判定日: 2026-10-16（日本時間）。対象0d344ddd7f1c250158841f73a1b0d4ac2e6a6d95、Draft PR #8。
本記録は主担当による合成機能の技術受入であり、正式FROZEN、merge、実会社実証の承認ではない。

| 対象 | 判定 | 確認した範囲 |
|---|---|---|
| D0110.1/.2 | 既存受入を維持 | surprise、非因果の観測反応と明示linkをdemoで使用 |
| D0110.3 | 合成機能の技術受入 | 独立注入の期間仮定→営業利益forecast→valuation |
| D0110.4 | 比較基盤の技術受入 | 事前登録、同じfirst releaseでの対比較、欠測/履歴不足、固定Decimal契約 |
| 実会社PIT/資料真正性 | 保留 | 原資料bytes/意味/経済条件と過去観測の証明が不足 |
| 独自予測の有効性 | 未評価 | 独自予測器、実履歴、holdout、統計/昇格基準が不足 |

全体コード再レビューは増やさず、既に終了した初回監査と阻害解消確認を証拠として採用。
受入整理担当は仕様/保存記録を読み取り照合し、合成技術受入可能と判断。追加テストは行っていない。
完成品全体率は未算定。D0110全体の実証完了率を4/4=100%とは表示しない。

## 正本と依存関係

PR #8はPR #7に、PR #7はPR #3に依存する未マージstack。
現在branchで一式は実行できるが、受入済み開発branchへ統合済みではない。
PR #4〜#6の税引前利益/保存経路は今回営業利益demoの依存ではない。各Draftを維持。
利用手順と残条件は2026-10-15_D0110_COMPLETE_DELIVERY.md / D0110_DELIVERY_RESULT.md。

## 保存証拠と記録の限界

同時公開evidence/d0110/の4logは既存ローカルログの原文コピー。新実行で作り直していない。
initial-tests.logは28be858、306passed/exit0と前後SHA、closure-tests.logは3cfd8e3、47passed/exit0と前後SHAを保持。
両ログには正確なpytestコマンド/cwd/deselect一覧がない。欠落した履歴を推測で追記しない。
initial-probe.logはSHA付き集約JSON、closure-probe.logは結果hashと集約JSONのみ。
probeの各exit、開始終了SHAは保存ログだけでは完全に再構成できない。
初回コードはvalidation/d0110_independent_probe.py（underscore表記）で発見しinitial-probe.py.txtへ原文保存。
コードは固定SHA/cleanチェックを含むが、実行コマンド・exitを新たに証明するものではない。
コードのROOT/REPOは元のworkspace配置を前提とし、公開コピーをその場で実行するための入口ではない。
closure probe実行コードは今回回収できていない。
従ってprobeの詳細は担当者報告を伴う補助証拠であり、完全な再現用実行パッケージではない。

GitHub check-runsで対象SHAのpush run38756294391/PR run38756502635がsuccessと直接確認。
後者job116496229715はlint/format/mypyとH0001/Locked除外pytestの各step success。
リモートpytest件数はcheck-runsだけでは確認できず、ローカル件数と混同しない。
H0001戦略/Locked Test実行、凍結変更、merge/FROZENは行っていない。

## 次の必須境界

技術基盤の任意改善は保留。実データ受入へ進めるには新たな原資料根拠または前向きに取得した履歴が必要。
同一SMM資料の2回探索を繰り返さず、過去SYSTEM_OBSERVEDを捏造しない。
未完了条件を満たす根拠なしに、合成成功を実会社・予測性能受入へ昇格しない。
