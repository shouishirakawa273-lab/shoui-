# D0110 前向き検証の開始条件と運用protocol

## 状態・根拠

開始a35220f3704d994f791fe2ed8a6e68faf573bc91（Draft PR #11）。
ユーザーは、前向き履歴の蓄積と、待ち時間を使ったD0110実データ確認/D0111依存調査を並行する方針を承認。
旧工程の「D0111対象外」はその工程の履歴。今回はD0111依存調査と最小仕様案まで扱う。
禁止事項（凍結変更、H0001/Locked Test、merge/FROZEN、sources書込）は継続。

この文書は運用整理。実験登録済み/予測履歴蓄積開始とはしない。
現在保存された実CPIはSCHEDULE_ONLYであり、own forecast/consensus/初報は未収集。
独自モデルの計算式と実consensus取得元は、既存文書の読取2回で確定した正本を発見できなかった。
過去会話全文や未取得原資料に存在しないと断定するものではない。

根拠: MACRO_COMPARISON_CLI_RESULT.md、MACRO_PLAN_PERSISTENCE_RESULT.md、
D0110_TECHNICAL_ACCEPTANCE.md、CPI_FORWARD_OBSERVATION.md（いずれも2026-10-16）。
実装契約はlib/macro_experiments/comparison.pyとstore.pyを優先する。

## 固定できる評価protocol

1. 事前登録にevent type/dimension/unit/entity/model version、明示event roster、period別contract、
   評価window、正のminimum_samplesを保存する。標本数は事前の運用policyであり統計優位の閾値ではない。
2. 登録は評価window開始、自前予測作成、consensus snapshot作成のすべてより前。
   登録前に作られたconsensusを後から持ち込んで今回の前向きpairとしない。
3. 自前予測は有限Decimal scalar、固定モデル版、非改訂の初回予測のみ。
   ResearchSnapshotの根拠cutoff/作成時刻、予測作成、実公表時刻を別々に保持する。
   公表予定時刻を実公表時刻へ流用しない。
4. consensusは同event/dimension/unitの明示snapshotを使う。provider、出典、snapshot/availability/
   作成時刻を保存。自前予測とconsensusは初報公表より厳密前。
5. 初報は実公表、利用可能、保存時刻を保持し、後日改定値で上書きしない。
   両群を同一初報に対してABSOLUTE_ERRORで比較。全rosterを期待件数として残し、欠測理由とpaired/expectedを表示。
   MAEの分母は有効pair件数。全roster未充足ならINSUFFICIENT_HISTORYで、欠測を黙って合格扱いしない。
6. 実UTCで成熟した入力だけを評価する。MAEとown-minus-consensus MAE差を記述する。
   標本未達/欠落はINSUFFICIENT_HISTORY、揃ってもDESCRIPTIVE_ONLY。
   原資料未認証、OBSERVATIONAL_ONLY、NO_PROMOTIONを維持する。
7. D0110.4のマクロ予測誤差とD0111の株式リターンは別指標。片方から他方の有効性を認定しない。

## 蓄積開始の未充足gate

| gate | 必要な具体物 | 現在 |
|---|---|---|
| M モデル定義 | 計算式、入力系列/出典、cutoff、欠測処理、版を持つ再現可能なモデル文書 | 未定義 |
| C consensus | 発表前に保存できるprovider/取得経路/対象指標と取得時刻付きsnapshot | 未確定 |
| P 計画 | roster、period契約、window、minimum_samples、M/Cと整合する登録記録 | 未登録 |
| O 観測運用 | 入力根拠、予測、初報の実取得時刻と保存先・失敗記録 | 保存APIあり、実運用未開始 |

M/C/Pが揃う前に架空モデル名/値で実計画を登録しない。観測開始前の時刻をSYSTEM_OBSERVEDとして作らない。
統計検定/holdoutの未定義は別gateに残し、記述比較の履歴開始に統計優位認定を要求しない。

## モデルを固める次の限定作業

既存の独自モデルが回復できなければ、新規モデル設計であることを明記して入力・式・版を定義する。
例えば同指標の直近期間の真正な初報を据え置く単純持続モデルは、検討候補の一つにできる。
これは既存採用モデルでも予測優位性の根拠でもなく、実モデルを選定/登録したことにはしない。
比較対象を増やすためだけに指標・企業・イベントを無制限に追加しない。
モデル定義と利用可能な入力取得経路が揃ってから、実現在UTCで登録→根拠保存→予測保存へ進む。

## 並行して進める範囲

- D0110.1/.2: 取得可能な履歴と取得時点の証拠を切り分ける。過去SYSTEM_OBSERVEDを捏造しない。
- D0110.3: 既存資料の不足は保留。同一SMM論点の調査2回上限を再開しない。
- D0111: 別紙D0111_PARALLEL_SPEC_DRAFTの入力/算式/失敗gateを設計する。
  合成計算は前向き履歴を待たず進められるが、実会社受入や投資有効性を主張しない。

資料読取2回で打ち切り、今回は追加Web調査/実データ登録/モデル実装/本番変更なし。
完成品全体率は未算定。未merge文書は正式FROZEN正本ではない。
