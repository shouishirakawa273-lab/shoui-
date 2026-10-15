# D0110 全体の最小完成計画

ユーザーの最新承認: D0110全体(.1〜.4)をまず動く一式にし、任意改善は後に回す。D0111対象外。
開始HEAD de42298ca3a6871c5db1ed3e8e51bce722f5c42e。新規branch codex/d0110-complete-delivery。
この文書は開発受入条件でありFROZEN記録ではない。既存PRはmergeしない。

## 最小条件

1. .1 event/consensus/first release/surprise保存とPIT判定を既存APIで利用可能。
2. .2 observed responseを非因果の観測として計算・保存可能。
3. .3 明示された会社感応度と期間前提から利益差を算出。営業利益経路は既存forecast/valuationへ接続。
   税引前利益を営業利益へ暗黙変換しない。実会社資料の根拠不足は理由付き拒否。
4. .4 事前に固定した実験契約でown forecastとconsensusをfirst releaseに対して同条件で比較。
   D0107のPredictionRecord/EvaluationContract/absolute errorを再利用。データ不足や未成熟は不足と返す。
5. 合成機能検証と実データ性能評価を分離。実履歴がなければ全体の実証完了とは報告しない。

## .4 最初の実装契約

新規lib/macro_experiments/と専用testのみ。既存凍結production/testsは変更しない。
immutable事前登録に対象event type/dimension/unit、model version、評価期間、minimum sample数を固定しhash化。
標本は既存MacroEvent/ConsensusSnapshot/FirstReleaseとD0107 PredictionRecord/ResearchSnapshotを明示注入。
各recordのhash、event/target/period/unit/entity/snapshot identity、有限Decimal、aware時刻を検証。
own/consensusはfirst public releaseより厳密前。own snapshot/evidence cutoff/created_atの整合とモデル版を確認。
評価はrelease.available_at/created_at以後。first release以外への差替えは不可、重複eventは拒否。
事前登録は全予測より前、実験開始より前。比較対象の欠測を黙って除外せず理由を残す。
同一dimension/unit/periodのactualでD0107 absolute errorを両者に適用、mean absolute error差を記録。
最小標本未達ならINSUFFICIENT_HISTORY。十分でもDESCRIPTIVE_ONLYで、自動昇格/売買/統計優位を主張しない。
synthetic表示を必須にし、実データと混在させない。未来時刻の捏造なし。

## 完了までの順序

.4実装と独立監査→既存APIを呼ぶ単一合成demo→全体の利用手順と受入証拠を一式化。
読取設計でPR #4/#5/#6の税引前利益/資料保存経路は今回営業利益demoの必須依存でないと確認。
既存Draftを維持し、今回branchへ不要な統合をしない。
scripts/d0110_demo.pyはtest helperに依存せず、.1surprise/.2observed link/.3別途期間仮定とvaluation/.4比較のstatus/id/hashをJSON表示。
合成履歴不足のケースも確認する。独立予測の精度認定と完全な実会社接続を明示的にfalseとする。
受入条件に達しない実データ要件は具体的に残し、技術完成/実証保留を区別する。
H0001/Locked Test禁止、sources読取専用、凍結288path保護。レビュー初回1回+阻害解消確認1回。
既存の小工程完了で停止する計画は本承認で置き換える。全体受入候補まで通常承認待ちなし。

## 実装エントリポイント

- `.4`: `lib.macro_experiments.comparison.register_macro_plan` / `compare_macro_forecasts`。
  事前登録時に対象event ID rosterとperiod別EvaluationContractを明示。欠測も分母に残す。
  不完全pairまたは利用者指定minimum未達ならINSUFFICIENT_HISTORY。完全でもDESCRIPTIVE_ONLY。
  結果は両EvaluationRecordとconsensus用derived PredictionRecord/ResearchSnapshotを返すため、既存D0107 storeへ保存可能。
  consensus用snapshotは注入consensus IDへのDERIVED_CONSENSUS_AUDIT_REFERENCE_V1であり、own snapshotを流用しない。
  EvidenceRecord pool/原資料認証は本API対象外。EVIDENCE_NOT_INDEPENDENTLY_VERIFIEDを常に表示。
- 一式demo: `python Japanese_Equity_Lab/scripts/d0110_demo.py`。外部通信・ファイル書込なし、JSONを標準出力へ返す。
  固定synthetic CPI3.3/consensus3.1 → surprise0.2pp → USDJPY150→151.5の5分観測を関連付ける。
  会社経路は独立注入の研究期間COPPER100→110仮定。step10当たり利益20、売上1000/margin10からOI100→120、
  multiple8/net debt50/shares10で1株評価75→91へ接続。FX観測からCOPPER仮定を自動生成しない。
  `.4`は同じCPI first releaseにown3.2/consensus3.1を対比較し、absolute error0.1/0.2を返す。
  minimum2に対し1sampleなのでINSUFFICIENT_HISTORY。synthetic=true、empirical_certified=falseを明示。
- demoはテストhelperをimportしない。future consensus/post observation/driver availabilityは経路別拒否を専用testで確認。

これらは技術接続の検証であり、実履歴での予測性能や原資料first-releaseの真偽を証明しない。
