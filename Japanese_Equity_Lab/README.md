# Japanese Equity Research Lab

個人用の日本株投資リサーチ基盤。株価予測AIでも銘柄ランキングアプリでもない。

日本株市場を継続的に観察し、投資アイデアを仮説化し、過去データで厳密に検証し、
Paper Tradingで検証し、成功・失敗の両方を再利用可能な知見として蓄積するための研究プラットフォーム。

> 実際の証券口座への自動発注は実装しない。最終的なBUY / HOLD / SELL判断と注文は必ず人間が行う。

方針文書:

- [CLAUDE.md](./CLAUDE.md) — AI向けの短い規約(このディレクトリ配下限定)
- [INVESTMENT_POLICY.md](./INVESTMENT_POLICY.md) — 投資方針(対象・時間軸・目的)
- [RESEARCH_RULES.md](./RESEARCH_RULES.md) — 検証ルール(bias排除・Benchmark・Multiple Testing等)
- [DECISIONS.md](./DECISIONS.md) — 実装中に生じた仕様変更の記録

## ディレクトリ構成

```
Japanese_Equity_Lab/
  00_config/            実行時設定(ユニバース定義・ポートフォリオルール等)
  01_data/              raw/processed/prices/fundamentals/corporate_events/market/sectors/point_in_time
  02_company_research/  企業固有の調査ノート(例: 8056_BIPROGY/)
  03_idea_inbox/        投資アイデアの受信箱(youtube/x/papers/manual)
  04_hypotheses/        Hypothesis Registry(バックテスト前に事前登録)
  05_strategies/        Strategy定義(Signal + ライフサイクル状態)
  06_backtests/         Experiment Registry・バックテスト結果
  07_paper_trading/     Paper Trade記録(未来データでの検証)
  08_portfolio/         holdings/watchlist/shadow_portfolio/decision_log
  09_knowledge/         再利用可能な知見(validated/failed/regimes/sector/biases/surprises)
  10_agents/            サブエージェントの役割定義
  11_skills/            Skillカタログ(分析手順の外部化)
  12_reports/           daily/weekly/experiment レポート
  13_tests/             pytest テスト(lib/ と1対1対応)
  99_archive/           削除ではなく退避したデータ・実験
  lib/                  UI非依存の共有Pythonロジック(schemas / backtest / registry /
                         market_calendar / point_in_time / universe / data_sources / snapshot)
```

親リポジトリの `scripts/jquants_lab_pipeline.py` で、Data取得 -> Feature -> Signal ->
Decision -> Execution -> Return -> Benchmark比較 -> Experiment Registry -> Provenance を
一本通しで実行できる(`--source fixture` は合成データでの動作確認用、
`--source jquants` はローカル環境での実データ実行用)。

`lib/` はこの構成案に対する追加提案(詳細は DECISIONS.md)。数字プレフィックスの各ディレクトリは
成果物置き場、`lib/` はそれらを生成・検証するコード置き場という役割分担。

## ファイル命名規則

「分析.md」「test2.csv」「new.md」のような曖昧な名前は禁止。
日付・ID・企業コード・内容が名前だけで分かるようにする。例:

```
04_hypotheses/H0001_2026-08-16_earnings_revision_underreaction.md
06_backtests/BT0001_H0001_2026-08-16.json
09_knowledge/validated_patterns/earnings_revision_underreaction.md
02_company_research/8056_BIPROGY/2026-08-16_Q1_notes.md
```

## セットアップ

このディレクトリは親リポジトリ(`shoui-`)のPython環境(`.venv`)をそのまま利用する。
追加の依存パッケージは発生した時点で親リポジトリの `requirements*.txt` に追記する
(現時点のPhase1では標準ライブラリのみで完結)。

```bash
cd ..   # リポジトリルート
pytest Japanese_Equity_Lab/13_tests/ -q
```

## 現在の状態(Phase 2)

Phase1〜1.1(フォルダ構造・方針文書・主要schema・東証取引時間の制度変更対応・
Close-to-Close look-ahead防止・Corporate ActionのPoint-in-Time安全性)に加え、
Phase2で以下を実装した。

- `lib/data_sources/`: `DataSourceAdapter` Interfaceと`JQuantsAdapter`(実データ)・
  `FixtureDataSourceAdapter`(合成データ)。両者は同じInterfaceを満たす。
- `lib/snapshot.py`: Raw SnapshotのImmutable保存(manifest付き、認証情報の混入を検知)。
- `lib/market_calendar.TradingCalendar`: 実データに基づく取引日カレンダー
  (祝日等をデータから判定し、範囲外は失敗させる)。
- `lib/strategies/fixed_pipeline_validation.py`: Pipeline検証専用の固定Strategy。
- `lib/backtest/engine.BacktestEngine.run()`: Data〜Benchmark比較までの実装。
- `lib/reproducibility.py`: 再現性検証用のhash計算。

**既知の制約**: このセッションは外部API(J-Quants含む)へ一切疎通できない
ネットワークポリシー下で動作しているため、実際のJ-Quants接続での検証は行えていない。
Pipeline配線は`FixtureDataSourceAdapter`(合成データ、`13_tests/fixtures/README.md`参照)で
検証済み。ローカル環境で`.env`にJQUANTS_REFRESH_TOKENを設定した上で
`python scripts/jquants_lab_pipeline.py --source jquants` を実行し、実データで疎通確認すること。
TOPIX等のインデックス取得・Corporate Actions(株式分割等)の取得元はPhase3のTODO。
