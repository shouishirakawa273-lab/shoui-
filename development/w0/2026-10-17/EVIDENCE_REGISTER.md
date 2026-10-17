# W0 データ契約・証拠監査（読取専用）

基準SHA: `0e915c81fafc26535001680e5fbd0b9c5fc1eb67`。以下の参照pathはworkspace-relative。既存変更、API取得、credential/env/key読取、試験・株価return計算なし。

| Claim | Repository証拠 | 判断/一次log有無 |
|---|---|---|
| 現在の契約plan | `Japanese_Equity_Lab/DECISIONS.md:13452`, `:13672`、`LOCAL_DATA_FETCH_GUIDE.md:20` | **CURRENT_PLAN=UNKNOWN**。2026-09-08時点のStandard-era実効観測はあるが、現在契約dashboard/契約書/現時点probeは確認していない。adapterはplan判定しない。Standard activeをhardcodeしない方針。 |
| 約10年の価格/指数履歴 | `DECISIONS.md:13479–13496` | 2026-09-08時点の7203 price/TOPIX境界2016-09-08をHTTP400/200で確認したと記録。「全API10年/現在も10年保証」としない。原HTTPlogは今回探索範囲では未発見、一次response全文なし。decision本文は結果要約。 |
| 財務summary期間 | `DECISIONS.md:13493`, `:13814`; `lib/data_sources/jquants.py:209–217` | 2026-09-08の7203は41件、2016-11-08〜2026-08-04。code指定時from/toで絞られず全取得可能履歴が返るとの過去実測。requested windowとactual coverageを分離。他銘柄/全finance APIへ一般化不可。 |
| 実績と予想 | `lib/data_sources/jquants.py:201`; `lib/fundamentals/normalize.py:119–157`, `:208–217`; `RESEARCH_RULES.md:660` | summaryは実績・会社予想・修正を扱い、normalizerに当期/翌期会社予想mappingあり。市場consensusとは異なる。現時点planで全予想が即時・非欠損・網羅的に供給されることは未証明。 |
| 詳細財務/配当 | `DECISIONS.md:13525–13538`, `:13555–13566` | 当時details/dividend/breakdownはsubscription外403と記録。summaryは詳細BS/PL/CFではなくEDINET依存解消なし。これを2026-10-17現在のアクセス確定にしない。 |
| rate/runtime | `lib/data_sources/jquants.py:44`, `:220–228`; `DECISIONS.md:13469–13474`, `:13701–13703` | 実装throttle1.05秒、過去probe1.1秒。60req/minは旧user提示条件、STD-01Aでは再検証していない。現在plan/endpoint全体の正式rate上限はUNKNOWN。現環境の認証/疎通もUNKNOWN（再取得せず）。 |
| 旧無料/Light記述 | `RESEARCH_RULES.md:77–78`, `:520`, `:616`; `DECISIONS.md:13707–13711` | 約12週間遅延の無料プラン文は現契約根拠にできない。Light章と18:00例示は歴史/説明用に残したことがSTD-01Aに明記。無料/Light/Standardを混同しない。 |
| STD-02実測coverage | `12_reports/experiment/JQS_STD_02_7203_HISTORICAL_VALUATION_2026-09-08_report.md:25–33`, `:54–67`, `:89–119` | 価格2051/calendar3068/summary41のsnapshot ID/hash記載あり。raw期間と採用月次観測n82（2017-05〜2024-10、約7.42年）は異なる。n98候補から分母不足8/企業行動8を除外との記録、status PARTIAL。今回再測定なし。 |

## 一次データ・保存実測logの所在

- reportと`DECISIONS.md:13802–13816`は`Japanese_Equity_Lab/01_data/raw/jquants/SNAP_JQS_STD_02_7203_*`（gitignore）を所在として記録している。
- このcheckoutの指定raw/jquantsディレクトリは今回存在を確認できず、対象snapshot/manifestや独立HTTP実測logを読めていない。report内hashは**照合未実施**。対象trackedファイルはreportと`scripts/jqs_std02_7203_historical_valuation_remeasurement.py`。
- `validation/tmp-broad-*`等のSNAP0001/FIN_OFFLINEはtest出力であり、STD-02実データの代替証拠ではない。
- 保存済み報告の存在、過去の測定報告、今回の再現/生データ検証を区別。過去成功を現在の契約・稼働・coverageへ昇格しない。

## W0へ引き継ぐ不足

1. current planおよび現在の利用可能期間/API権利はUNKNOWN。credentialを調べるのでなく、必要なら機密を除いたユーザー契約申告/証明で別途確認。
2. 当時STD-02のraw/manifest/logの保全所在が不足。再取得で上書きせず、現存する元成果物の所在確認を別工程へ。
3. API別のcoverage・会社予想availability・改訂/公表/取得時刻・rate/runtimeを個別に契約化する必要がある。W0では実装/取得しない。

## GitHub・CI・公開資料の証拠

- GitHub REST repository/branches/pullsの観測はremote_state.json。公開repo、既定branch、各SHA・PR状態を保存。これは実行ログや受入の証明ではない。
- 既定branchのgit treeにはLabなし。調査元.github/workflows/ci.ymlでは3ファイルignoreとnot h0001 and not locked。導入commit9e9d98279a99de46b3bb162e2b5dbe905f547278。既定CIはpytest -qだが、Labを含まないため同じ保護問題とは扱わない。
- 現行CIの成功から除外研究テストの検証成功は推論できない。今回はCI実行も過去全check-runの照合も行っていない。
- Git履歴のローカルhome path検索で18ファイルに一致。DECISIONS、EDINET/TDNET onboarding、development/evidence配下のログ・before JSON等。資格情報ファイルは読まず、path値は再掲しない。一致は秘密や個人保有資産の漏えいを意味しない。
- 独立性: data/capability調査は読み取り担当による静的確認。既存testファイルの存在を独立実行成功とは呼ばない。W0の最終独立確認は別紙。
