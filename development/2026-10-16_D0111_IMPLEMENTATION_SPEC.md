# D0111 最小シナリオ計算 実装契約

開始28fb26edcc9439833370949e4501264beb286e97（Draft PR #13）。ユーザー続行指示によりD0111合成実装へ。
同日D0111_PARALLEL_SPEC_DRAFTを今回の開発基準として採用。過去の未取得要求全文を回復したとはしない。
既存valuation/forecast/凍結288を変更せず、新lib/scenario_returns/、専用test、必要最小合成demoのみ。

## 型と受入条件

- baseline/replayは既存ValuationResult。hash整合、両側SUCCESS、BULL/BASE/BEAR一意全件必須。
- 会社/currency/target_period/cutoff/modelID版/multiple/BSは両側同一。forecast参照とresult来歴IDは別でよい。
- 単一共有入力で基準価格、期間mapping、配当/entry/exit cost、share basisを明示し両側に適用する。
  すべて有限Decimal、価格>0、D/Ce/Cx>=0、valuation per-share>=0、shares>0。欠測は0補完しない。
- 価格observed<=available<=decision cutoff<exit_at、すべてaware。cutoff<=result計算時刻。
  入力valuation計算時刻はcutoff後も許容するが、今回計算時刻より未来なら拒否。
  multiple/BS/価格/配当cost/mapping/basis根拠のavailabilityはcutoff以下。
- ExitMappingは財務target_periodとexit_atを明示的に束縛し、根拠reference/availabilityを持つ。
  配当仮定は(cutoff,exit_at]区間。基準価格は仮想比較基準で、約定再現とは表示しない。
- ShareBasisAttestationは両valuationのhash、価格ID、share_count、basis根拠と確認状態を束縛。
  共通文字列だけで整合証明とせず、UNKNOWN/欠落/不一致は拒否。確認はcaller-attestedで独立認証ではない。
- macro対象scenario集合は非空・重複なし・対応enumのみ。非対象scenarioの経済field変更は拒否。
  他条件一致でもマクロ因果寄与やforecast原資料の真正性を認定しない。
- 各側gap=(V-P)/P、gross=(V+D-P)/P、net=(V+D-Cx-P-Ce)/(P+Ce)。downside=max(0,-bearnet)。
  同名指標差=replay-baseline。単位は小数比率、税前・非年率、確率加重なし。
- 結果に全入力hash/参照、計算契約版、SCENARIO_IMPLIED/OBSERVATIONAL_ONLY/NO_PROBABILITY_WEIGHTING/
  CALLER_ATTESTED_BASISを保持し、既存integrity primitiveでhash化。入力は不変。
- Decimal contextは呼出元から独立（precision50/HALF_EVEN/明示EminEmax/traps/flags）。
  contextの変更、循環小数を含む入力でも結果/hash再現、呼出元context不変を検証。
- 失敗は理由付きtyped outcomeで成功scenarioを返さないか、構造不正を明示ValueErrorとする。

## 検証範囲

既存公開evaluate_forward_valuation APIから両側3scenarioを作る合成test、独立算式で非ゼロ配当/cost/差を確認。
各PIT/identity/basis/hash/欠測/非対象scenario不整合を一つずつ投入して拒否する。
新専用testと必要既存valuation/会社bridge integrationだけの明示allowlist。H0001/Locked Test禁止。
唯一writer、固定完全SHAで設計監査・独立検証。初回1回＋阻害解消1回、細かな任意改善は後回し。

実会社入力取得・価格/配当予測・実リターン有効性・確率calibration・売買・merge/FROZENは対象外。
BLS日次collectorは既存固定runtimeを維持し、本開発のbranch切替や新入力へ自動接続しない。
完成品全体率は未算定。合成動作確認と実データ受入は別gate。

## 公開APIと利用方法

`lib.scenario_returns.compare_scenario_returns(baseline=..., replay=..., terms=..., calculated_at=...)`
は`ReturnComparison`を返す。不足・不整合は理由付き`ValueError`で全体を拒否し、部分成功を返さない。
共有`SharedTerms`は`PriceReference`、`CashTerms`、`ExitMapping`、`ShareBasisAttestation`と
decision_cutoff、macro_scenarios、macro_reference、syntheticをすべて必須とするfrozen dataclass。
CashTermsのsource_ref/available_atは配当とentry/exit costすべてをカバーする明示の共同根拠であり、
coverage_start=cutoff（開区間）、coverage_end=exit_at（閉区間）。価格は仮想比較基準。
ShareBasisAttestationはconfirmed=Trueと、両valuation hash/価格ID/株数/各basis根拠を必須とする。
呼出元による宣言であり独立のcorporate-action認証ではない。

既存ValuationResultのhash/有限値/通貨/株数/PIT/全scenarioと同条件は検査する。
ただしsource算式を異なるDecimal contextで再計算して正しさを再認証する機能は採用しない。
`SOURCE_ARITHMETIC_NOT_REVALIDATED`を明示し、出所やforecastの真正性も認証しない。
各シナリオのper-share評価額からD0111自身のgap/gross/net算式だけを固定contextで計算する。
`ReturnComparison.terms`に全根拠・時刻・cash・basisを保持し、terms_hashと両valuation hash/IDを記録する。

任意の作業ディレクトリから、リポジトリのPythonで`Japanese_Equity_Lab/scripts/d0111_demo.py`の
絶対パスを実行すると、公開forecast/valuation/scenario_returns APIをつないだ合成JSONを出力する。
test helperはimportしない。出力synthetic=true、empirical_validation=falseで実会社や実証成績と区別する。
