# BLS CPI単一系列capture 実装・運転結果

開始ba4155405b1d92ed30d0bfef7974826e6422e582。新規capture-only取込を実装し、実予定取得まで確認した。
運転コードSHA f075802dcafd35451b84f301ec00907c74536738 / normalizer bls-capture-2。
既存凍結288ファイル・既存production/testsは無変更。未merge・未FROZEN。

## 実際に動いた範囲

- 固定BLS公開API、CUUR0000SA0（米CPI-U都市平均総合NSA、1982-84=100の指数水準）を1attemptで取得。
- HTTP entity bytes、実UTC、出典、hash、成否をimmutable bundleへ保存。
  既存MacroRecordとAppendOnlyRecordStoreを再利用し、raw再解釈との照合でshowする。
- 月次33件を保持（PRESENT32、MISSING_OR_UNSPECIFIED1）、M13年平均2件を除外。
  明示欠測は2025-10、raw_value='-'、value=None。原応答の既知footnote理由を検査し、0/補間値を作らない。
- 実予定JST12:51:31と12:52:31の2回で取得成功、各bundle再読込も独立確認。
- 隔離したネット通信なしの模擬503は、FAILED receipt/終了code1を確認。
  これは実BLSの503ではない。一時検証taskは証拠保存後に削除し、本番taskは維持。

全記録は取得時点のcurrent snapshotであり、過去初報・市場公開時刻・前年比を認定しない。
market_public_at=None/UNKNOWN、vintage_label=None、利用可能時刻は実観測UTC/OBSERVEDのみ。

## 独立検証の対象と限界

| 対象 | 実行 | 結果 |
|---|---|---|
| 初回69c3fced1f3a53aa775f71b2f3315bfafe9a9988 | collector/macro_model/macro_pit/macro_catalogの4file | 85 passed / exit0 |
| HTTP阻害解消17adb2415e441a2fb394611c333c4f1fdffa1fd0 | 不完全受信・受信時刻の実名node | 7 passed / exit0 |
| 実データ適用f075802dcafd35451b84f301ec00907c74536738 | 実fixture/既知欠測/未知欠測拒否の実名node | 6 passed / exit0 |

別実行を合計して最終98件一括再実行とはしない。いずれも前後完全SHA一致、status clean、凍結288変更ゼロ。
設計監査は初回1回＋HTTP阻害closure1回。以後の実入力確認は限定受入試験で、全面再レビューしていない。
実運転の別読取照合は配布zip hash/166内包fileの生bytes一致、実2予定実行、保存再読込を確認。
通常Git表示の改行変換と原bytesを混同しない。実bundleはZIPで公開し、内包bytesとmanifestを保持する。

## 実運転までに発見した問題

1. 実装中、成功受信時刻が開始時刻のままになる箇所を修正し、独立検証前に回帰test追加。
2. 初回設計監査でHTTP途中切断/Content-Length不一致の取りこぼしを検出。
   不完全応答は部分bytesとHTTP状態をFAILED保存し、正常recordを生成しないよう限定修正。
3. 実取得で公式欠測表現が判明。初回runtimeは安全に拒否しFAILEDbundleを残した。
   source gateは接続/外形確認までだったため、この経済値の欠測は実受入時に判明した。
   既存enumによる欠測保持へ限定対応し版を2に更新。旧失敗bundle/runtimeは上書きしていない。
4. 模擬失敗taskの最初の予定は未実行だった。主task同等の電源条件へ合わせ再予約し、1回の予定失敗を確認。

## 定期運転と保存場所

Windows task: JapaneseEquityLab-BlsCpiCapture。毎日00:15 Japan/Tokyo、次回2026-10-17。
実行は固定snapshot（ops/bls-runtime-f075802）と既存venvのpythonwを使用し、開発branchの切替に依存しない。
保存先はworkspace直下ops/bls-data-v2。毎日の取得データをGitへ自動commit/pushしない。
Windows起動・ユーザーログインと、この実行用フォルダ/Python環境の維持が条件。
WakeToRun/StartWhenAvailableは設定したが24時間運転を保証しない。停止中の過去観測時刻は補完しない。
既存チャットheartbeatはPAUSEDのまま。データ取得taskとは別であり、D0111開発が裏で自動進行中とは表示しない。

状態確認: `Get-ScheduledTaskInfo -TaskName JapaneseEquityLab-BlsCpiCapture` とbundle receipt。
LastTaskResult 0が正常、失敗は非zeroとFAILED receipt（保存先到達前の障害はOS終了結果）で確認する。
運用停止は当該taskのDisableで行える。成功run-idのfetch再実行は検証のみで通信・上書きしない。
初報/consensus/独自モデル/実験計画は未登録・未開始。原資料収集と予測比較の時計は別。

## 証拠・次工程

development/evidence/bls-capture/に独立ログ、運転照合、予定実行結果、実成功bundle ZIPを保存。
テストのfixtureは原応答の経済内容を使用し、原HTTP bytesの証明には実bundle ZIPを用いる。
新形式や未知欠測は引き続き隔離。全source/企業/常時ホスト/通知UIの拡張は今回対象外。
最小取込の技術運転gateは充足。以後収集を続けながらD0111型付きAPIと合成計算へ進行可能。
実予測モデル/consensus/事前登録条件は並行して確定が必要。完成品全体率と予測有効性は未算定/未受入。
H0001/Locked Test、既存sources変更、merge/FROZENは行っていない。

出典: https://www.bls.gov/developers/api_signature.htm 、https://www.bls.gov/cpi/factsheets/cpi-series-ids.htm 。
BLS取得日と出所はreceiptへ保持し、取得後の分析品質をBLSが保証しないことを明示している。
