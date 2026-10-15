# D0111 並行開発の最小仕様案

## 回復済み方針と今回の新規案を区別する

基準a35220f3704d994f791fe2ed8a6e68faf573bc91。
handoff/2026-10-14_Japanese_Equity_Lab_HANDOFF.md §5は、提供会話から回復した基本方針を示す。
Bull/Base/Bear Return、Downside、Valuation Gap、マクロあり/なし同条件比較、
v1確率加重Expected Returnなし、D0110.4履歴待ちでもD0111へ進行可、がその範囲。
番号付きD0111要求全文・正式詳細仕様は今回発見していない。sourcesに列挙可能なファイルもなかった。
参照handoffはローカル二次監査記録でありGitHub内の正式D0111正本ではない。過去会話全文は未取得。
以下の算式・入力policyは今回の新規仕様案であり、過去に承認された詳細要件として扱わない。
実装/FROZEN/正式受入記録ではない。通常の開発判断は統括が記録し、憶測で原設計を補完しない。

## 既存APIと境界

既存evaluate_forward_valuationのValuationResultを新moduleで受け取る。凍結valuation/forecastは変更しない。
ValuationResult SUCCESSでもshares/per-shareが欠ける場合があるため、それだけでD0111計算可とはしない。
既存Company Exposure bridgeは選択scenarioのみを変更する。全scenarioをマクロ反映済みと表示しない。
D0110.4 MAE、イベント観測、因果推定は今回計算の入力に自動変換しない。

## 明示入力案

- 同一会社のbaseline/replay ValuationResult、両hash、macro適用の説明と対象scenario参照。
- 基準価格P（正の有限Decimal）、currency、会社、price observed/available at、source参照、share basis。
- 判断cutoff、計算時刻、想定exit date。財務target_periodとexit dateを別fieldで保持する。
- 同一share basisの期間配当D、entry cost Ce、exit cost Cx（いずれも1株当たり非負の有限Decimal）。
  値とともにcurrency、根拠、availabilityを明示。ゼロも明示値であり、欠測をゼロへ置換しない。
- 税の扱いは固定labelで明記。v1案は税前・非年率。税や年率を暗黙に計算しない。

想定exit dateで評価額Vが実現するという条件付き比較であり、D0110の財務年度評価額を
将来市場価格と認定しない。対応関係の明示なしに期間リターンを算出しない。
時刻はaware datetimeへ統一し、price observed <= price available <= 共通decision cutoff < exit_atを要求する。
基準時点はdecision cutoffであり約定時点を再現しない。配当は(cutoff, exit_at]区間の事前仮定を入力する。
V対応はtarget_period/exit_at/assumption reference/available_atを持つ明示mappingとし、
そのavailabilityもcutoff以下とする。将来実績配当や将来判明のmappingを遡及投入しない。

## 算式案（比率、小数単位）

scenarioごとに次を区別する。自動確率加重・採用判定・売買推奨は出さない。

- valuation gap = (V - P) / P。評価額と基準価格の差であり、配当/費用/保有期間を含めない。
- gross scenario return = (V + D - P) / P。
- net-before-tax scenario return = (V + D - Cx - P - Ce) / (P + Ce)。
- downside magnitude = max(0, -bear net-before-tax scenario return)。
  選択Bearシナリオの損失幅であり、最大損失・VaR・確率下限ではない。
- baseline/replay各scenarioの同名指標の差を返す。因果効果と表示しない。

D/Ce/Cxが明示ゼロならgapとreturnが一致することがある。別の経済概念を重複成果として数えない。
負のper-share評価額は投資リターンにそのまま変換せず不足/不適用として拒否し、ゼロへfloorしない案。
Decimalは呼出元設定に依存しない明示計算contextと版を持ち、結果と入力参照をhash化する。

## fail-closedと同条件比較

hash改変、片側非SUCCESS、3scenario欠落/重複、価格非正、per-share/shares欠落、非有限値は拒否。
会社/currency/財務period/cutoff/model版/multiple/net debt/shares/share basis/価格/exit/配当cost条件を照合。
基準価格・multiple・BS・根拠のavailabilityがcutoff後なら拒否。価格時刻とavailabilityを混同しない。
valuationのcalculated_atは知識の取得時刻ではない。過去cutoffでの再計算を一律未来情報とはしない。
macro有無の比較では異なるforecast参照自体は許容し、他の条件を同一に保つ。
対象scenario外の経済field変化は拒否するが、hash一致だけでmacro寄与の因果認証をしない。
実装案では価格/期間/mapping/配当cost/currency/share basisを単一共有入力で渡し、両側で同じ条件を使う。
macro対象scenario rosterを明示し、対象外scenarioの経済field変化は拒否する（result ID/来歴の差は許容）。
share basisは共通文字列だけで整合認定せず、価格basisと両valuationのshare count/basisを結ぶ根拠参照と
確認状態を必要とする。基礎根拠が不明な実データは保留し、合成例の整合確認と分ける。
このbasis宣言はcaller-attestedであり、本moduleによる独立のcorporate-action調査認証ではない。

## 合成受入条件

1. 既存公開valuation APIからBull/Base/Bearの両側を作り、独立算式でgap/gross/net/downside/差を確認。
2. 配当/entry/exit costを非ゼロにして分母と控除を確認。ゼロケースだけで正しさを認定しない。
3. 上記不正条件を一つずつ投入して拒否し、比較条件不一致を黙って補正しない。
4. Decimal contextを変えて結果/hash再現と呼出元不変、入力hash不変を確認。
5. 新module/新専用testのみ、既存凍結288は無変更、禁止test/merge/FROZENなし。
6. 全結果はSCENARIO_IMPLIED/OBSERVATIONAL_ONLY/NO_PROBABILITY_WEIGHTING。
   合成機能確認、実会社受入、履歴による有効性評価は別gate。

次の小工程は本案に基づく型付きAPIの具体化と合成実装。今回の初回文書監査は完了。
初回文書監査で挙がった時刻順序/配当区間/mapping、共有条件/対象外scenario gate、basis根拠を上記へ追記した。
旧D0110.4履歴待ちを理由にこの設計を止めない。実履歴待ちはD0111の実効性認定にも必要だが、算式検証の前提ではない。
