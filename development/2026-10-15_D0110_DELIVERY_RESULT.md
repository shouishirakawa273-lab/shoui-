# D0110全体 最初の動作候補

状態: 技術受入候補、未マージ・未FROZEN。実会社/予測性能実証は保留。
base PR #7 de42298ca3a6871c5db1ed3e8e51bce722f5c42e。
初回独立対象28be858e580552072a08b2a6e9508f3fc8e3852c。
阻害解消対象3cfd8e3068b7224e0fd376127c4a258df17e2b0c。

## 動く範囲

リポジトリで `.venv/Scripts/python.exe Japanese_Equity_Lab/scripts/d0110_demo.py` を実行する。
既存.1surprise、.2observed response/link、.3会社感応度→D0109営業利益→D0110評価、.4比較をJSONで確認可能。
surprise0.2pp、FX観測150→151.5、独立した期間銅仮定100→110、営業利益100→120、1株評価75→91。
観測から期間仮定の自動変換はしない。税引前→営業利益暗黙変換なし、D0111なし。
.4はown3.2/consensus3.1を同じfirst release3.3に対してD0107で評価。1sample/minimum2でINSUFFICIENT_HISTORY。
minimumは利用者の事前policyで統計優位基準ではない。合成は合成と表示、実証認定false。

## 独立証拠

初回明示allowlist306 passed/exit0。start/end同SHA clean。source文字列guard3件はdeselect prefix誤りで含まれたが、禁止戦略/Locked Testは実行していない。
独立CLI異cwd2回stdout一致。D0107既存5種record全field/hash保存復元、重複reject。
初回設計指摘はDecimal計算context依存1件。新wrapperで固定Contextと計算契約版を導入。
closureで新2testfile47 passed/exit0、別probeでも低precision/異なる丸め/指数範囲/全traps下で値/hash一致、caller設定不変。
初回306とclosure47を最終一括353件成功とは扱わない。設計closureで当初阻害解消、追加阻害なし。
凍結288path無変更。既存production/tests/manifest無変更、DECISIONSは結果追記のみ。
詳細実行ログはローカルvalidation/d0110-independent-{tests,probe,closure,closure-probe}.log。
RegisteredMacroPlan専用storeはない。D0107記録の保存確認とplan永続化を混同しない。

## 残る実証条件と後回し事項

住友金属鉱山原資料bytes/意味/経済条件と営業利益接続、過去SYSTEM_OBSERVED証明は未受入。
同一資料の探索上限2回を消化済み。未知を埋めず保留。
独自予測器・十分な実履歴・holdout/統計優位/昇格は未実証。
注入first releaseの真正性とEvidenceRecord poolは本比較APIで認証しない。常にEVIDENCE_NOT_INDEPENDENTLY_VERIFIED。
実データ利用前のjurisdiction/entity対応契約は後回し一覧。
従って『D0110機能一式の合成動作候補』であり『実会社PITと独自予測有効性まで完成』ではない。
完成品全体率は未算定。マージ/FROZENは行わない。
