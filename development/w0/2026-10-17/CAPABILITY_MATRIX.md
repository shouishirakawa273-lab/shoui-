# W0: research capability static audit

基準SHA: `0e915c81fafc26535001680e5fbd0b9c5fc1eb67`。HEAD一致・git status --short空を確認。2026-10-17。ユーザー添付`84e48d40-23f6-4650-854e-79f81ce73ed4/貼り付けたテキスト.txt`を読取。W0限定、既存コード/文書/Git/データ変更なし、秘密・env未読、ネット取得/テスト/Locked実行/収益値再分析なし。本ノートのみ作成。

以下パスはすべて基準SHAのrepository相対。仕様/実装の存在と、独立検証成功・実データ正式受入を別に記す。以前のDECISIONS/READINESSの自己申告は「記録あり」であり今回の再実証ではない。

## P0-1の検証結果

**現行の通常backtest signal呼出はprice barsのみ。財務・開示のPIT取得機能は存在するが、backtestへの直接接続は未整備という指摘を支持。** 全モジュールが価格しか扱えない/エンジン再利用不可能との拡張解釈は支持しない。

- `Japanese_Equity_Lab/lib/backtest/engine.py:502–512`: `run`はconfig/price_history/benchmark/calendar、`signal_fn: Callable[[Sequence[AdjustedOHLCVBar]], bool]`、sector/universeを取る。財務、開示、decision_atをsignalに渡す型はない。
- 同:559–580:銘柄/decision_date loopで`decision_at=session_close_at(...)`、PIT universe選択、`price_history.bars_up_to(code, as_of=decision_at)`、`signal_fn(bars_up_to_decision)`。signalからcode/cutoffを直接受け取れない。
- `scripts/jquants_lab_pipeline.py:198`、`scripts/phase5_v1_short_term_reversal.py:265–273`、`scripts/phase5_v1_1_h0001_real_data.py:424–432`でprice strategyの`as_buy_signal_fn`を渡す。`lib/research/runner.py:109,192`も同型を引き渡す。
- `lib/fundamentals/view.py:25–74`に`as_of_by_semantics`/`fundamentals_as_of`実在。MARKET_PUBLIC_ATはpublished_at、PROVIDER_AVAILABLE_ATは確認されたprovider availabilityを区別し、UNKNOWNを安全側で除外。`lib/disclosures/view.py:28–76`に開示as-ofあり。
- 呼出検索で財務viewはcompany valuation/evidenceおよびstage3 scriptsに利用。backtest engine/research runner/上記通常backtest scriptから財務viewをsignalへ渡す経路は発見せず。
- `DECISIONS.md:6072–6118` D0061、`PHASE5_READINESS.md:80–108,473–483`も同じWIRING_UNDESIGNED境界を記録。
- `lib/research/preregistration.py:46–57`は旧Phase5 v1のforbidden capabilitiesにfundamentals/disclosures/evidence等を含む。closureで型を回避できるかだけでなく、旧研究契約にも適合する新設計が必要。

### W4へ残す静的選択肢（実装/推奨確定なし）

1. 凍結engine外のevent→(code,decision_at) signal map adapter。現型ではcode/cutoff伝達が暗黙となり、空bars・同一bars・呼出順依存・価格欠測で曖昧にならない契約が必要。単純closureで既に安全に解決済みとはしない。
2. 専用event-study evaluatorが既存calendar/execution/benchmark primitiveを再利用。凍結変更回避は可能候補だが重複測定仕様と検証量を要する。
3. 明示context付き新wrapper/APIを設計し既存engineと境界を確定。凍結engine直接変更はW0許可外。

いずれも公開時刻≠売買可能時刻、銘柄識別、取引時間変更、翌営業日、価格欠測/企業行動、cost/benchmark、split隔離を設計してから選択。今回は実装しない。

## Capability別の状態

| Capability | 仕様 | 実装 | 独立検証証拠 | 実データ受入/不足 |
|---|---|---|---|---|
| PIT価格 | あり。D0034/35,READINESS | `lib/backtest/price_history.py:32–117`、`lib/schemas/price_data.py:120–272`。AsOfAdjustedがdecision毎調整、Staticはas_of無視 | 既存test/記録あり。今回独立実行なし、特定SHAの実行原証拠まで照合していない=UNKNOWN | READINESS:80はREAL_DATA_VALIDATEDと申告。現契約/全銘柄/全期間適格性はUNKNOWN、W3対象 |
| 財務・開示 | あり。D0042以降 | view/normalize/model/disclosures viewあり | test_fundamentals_view/model/normalize/integration/pit_real_dates等ファイルあり。実行成功・独立性は今回未照合 | READINESS:82は4銘柄のparse validation記録。歴史的provider availability、backtest signal接続は未受入 |
| 研究事前登録 | あり。`lib/research/preregistration.py:1–31` | 同:98–173でsplit時系列非重複、core hash、改訂系譜。`research/registry.py:62–90`追記 | `13_tests/test_research_validation_pipeline.py`存在。現行の独立実行証拠未照合=UNKNOWN | H0001文書に登録/利用記録あり。新仮説・新期間の独立性は未確定 |
| Experiment Registry | あり、全結果分母保持 | `lib/registry/experiment_registry.py:71–98`、`registry/provenance.py` | test_experiment_registry.pyあり。独立原証拠未照合=UNKNOWN | 既存実験ファイルあり。存在≠研究妥当性/全利用履歴完全性 |
| Locked Test | あり、research/locked_test.py:1–18 | 同:39–118とFileBacked wrapper:136以降、runner:138–144でTEST gate | test_research_validation_pipeline.py存在。再実行禁止につき未実行。過去監査記録あり | **experiment ID単位**で再unlock拒否、actorは非空文字列。ユーザー本人認証や仮説横断period汚染台帳ではない。実利用記録の存在まで、収益値未読 |
| 財務/開示→signal | D0061では未設計を明記 | 通常3script/runner/engineに接続発見なし | 接続の独立検証なし | 未受入。P0-1支持 |
| 前向き予測記録 | D0107/09/0110.4の契約あり | `lib/evaluation/model.py:258–441`PredictionRecord初回/改訂、store.py:244。forecasting/engine.py:386–454橋、macro plan/input/compareあり | 新macro系はDECISIONS:19200–19219に独立実行記録。ただし日本株研究予測の実運用を保証しない | 保存APIとmacro収集は別。実投資仮説の継続的前向きprediction運用の受入証拠は今回未発見=UNKNOWN |
| Paper Trading | schema/roadmapあり | `lib/schemas/paper_trade.py:19–36`frozen理由付きrecord | test_paper_trade_schema.py存在。独立実行証拠未照合 | production/scripting検索でPaperTrade生成利用経路を発見せず。持続的paper運用・実データ受入はUNKNOWN |
| Knowledge蓄積 | schema/roadmapあり | `lib/schemas/knowledge.py:27–62`Knowledge/SurpriseLog、provenance関連参照 | test_knowledge_schema.py存在。独立実行証拠未照合 | 実験→失敗原因→知識→次研究の継続運用経路の受入証拠を今回未発見=UNKNOWN |

補足: `development/2026-10-17_RESEARCH_PATH_RESULT.md:7,22`はcompany exposure→valuation→D0111の合成public API連結と独立検証の記録。これは**バックテストのfinancial-event signal連結や実投資研究受入を意味しない**。同名researchの混同を避ける。

## 過去使用期間:所在の確認のみ

- `Japanese_Equity_Lab/04_hypotheses/H0001_2026-08-19_short_term_reversal.md:16,90–106`に旧2022-01-04〜2024-12-30 pipeline利用、H0001-R1 Train2022-01-04〜2023-12-29、Validation2024-01-04〜2024-12-30、Locked2025-01-06〜2025-12-30と4銘柄の記録。
- `scripts/phase5_v1_1_h0001_real_data.py:32–49,82–90,110–122`に廃案期間との区別、過去使用との重複、実行引数例。例の存在だけで全期間実行済みとも未見とも断定しない。
- `Japanese_Equity_Lab/06_backtests/locked_test_audit.jsonl`、`locked_test_audit_real.jsonl`、`12_reports/experiment/BT_PHASE5_V1_H0001_SMOKE_V2_2026-08-19_report.md`、`BT_PHASE5_V1_1_H0001_R1_2026-08-19_report.md`、`JQS_STD_02_7203_HISTORICAL_VALUATION_2026-09-08_report.md`のファイル所在まで確認。レポート収益値/監査JSON本文は今回開かず、再計算なし。
- W1で期間利用台帳の原証拠を照合するまで、2025/2026その他を未見/新Lockedとして再予約しない。既存gateは同じ期間を別experiment IDで使う汚染まで自動排除しない。

## W0結論と残る確認

既存部品を破棄せずW1データ利用台帳→W2安全CI→W3データ適格性→W4接続設計の順序を支持。W0では新adapter/新研究/return再分析を行わない。上記UNKNOWNを『未実装』や『検証失敗』へ置換しない。旧READINESSのREAL_DATA_VALIDATEDも今回のlive疎通/現プラン/投資有用性の証明へ昇格しない。
