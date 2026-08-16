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
- [LOCAL_DATA_FETCH_GUIDE.md](./LOCAL_DATA_FETCH_GUIDE.md) — ローカル環境で実J-Quantsデータを
  取得し`--source local`でPipelineを検証する手順(Phase3A、クラウドセッションが外部APIへ
  疎通できない場合用)
- [DATA_SOURCE_ARCHITECTURE.md](./DATA_SOURCE_ARCHITECTURE.md) — Multi-Source Data
  Foundation(Phase3D): Source Catalog・Capability-based Provider・Entity Registry
- [EVIDENCE_MODEL.md](./EVIDENCE_MODEL.md) — Evidence Type・PIT/Revision・Evidence
  Packet・Decision Evidence Log(Phase3D)

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
                         market_calendar / point_in_time / universe / data_sources / snapshot /
                         sources[catalog/providers/entity_registry] / evidence[model/news/
                         retrieval/packet/decision_log])
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

## 現在の状態(Phase 3D)

Phase1〜1.1(フォルダ構造・方針文書・主要schema・東証取引時間の制度変更対応・
Close-to-Close look-ahead防止・Corporate ActionのPoint-in-Time安全性)、Phase2〜2.2
(実データPipelineの実装、Execution Metrics、Reproducibility)に加え、Phase3A・3A.1・3A.2で
以下を実装した。

- `lib/data_sources/`: `DataSourceAdapter` Interface(J-Quants API V2ベース)と
  `JQuantsAdapter`(実データ・API直接接続)・`LocalSnapshotAdapter`(実データ・ローカル
  ファイル経由)・`FixtureDataSourceAdapter`(合成データ)。3者とも同じInterfaceを満たす。
  個別銘柄日次Bar・Trading Calendar・TOPIX専用Endpoint・銘柄マスタ(Master)を扱う。
- `lib/snapshot.py`: Raw SnapshotのImmutable保存(manifest付き、認証情報の混入を検知)。
- `lib/market_calendar.TradingCalendar`: 実データに基づく取引日カレンダー
  (祝日等をデータから判定し、範囲外は失敗させる)。
- `lib/strategies/fixed_pipeline_validation.py`: Pipeline検証専用の固定Strategy。
- `lib/backtest/engine.BacktestEngine.run()`: Data〜Benchmark比較までの実装。
  `price_history`は`lib/backtest/price_history.PriceHistorySource` Protocol経由で
  decision_atごとに取得し、全期間共通の事前計算済みSeriesは保持しない(D0035)。
- `lib/reproducibility.py`: 再現性検証用のhash計算。
- `lib/schemas/price_data.py`: Corporate ActionをCase A(Announcement Signal、
  `announced_at`必須、引き続き未実装)とCase B(Price Series連続化、Provider由来Event、
  `build_provider_derived_adjusted_bars`)に分離(D0032)。Case BはAdjFactorの公式計算
  方法が確定し(D0034)、decision_atごとのPIT-safe As-of Adjustmentとして
  `scripts/jquants_lab_pipeline.py --price-adjustment pit`(既定)で実際のBacktestへ
  適用される(D0035)。

**既知の制約**: このセッションは外部API・公式ドキュメント(J-Quants含む)へ一切疎通できない
ネットワークポリシー下で動作しているため、実際のJ-Quants API V2接続での検証は行えていない。
Pipeline配線は`FixtureDataSourceAdapter`(合成データ、`13_tests/fixtures/README.md`参照)と、
手作業で用意したV2形状のscratch dataによる`--source local`経路で検証済み。ローカル環境で
`.env`にJQUANTS_API_KEYを設定した上で`python scripts/jquants_lab_pipeline.py --source jquants`
を実行するか、`LOCAL_DATA_FETCH_GUIDE.md`の手順で実データ疎通確認すること。Corporate Action
Announcement(Case A)の取得元は引き続き未実装(DECISIONS.md D0031〜D0035参照)。

### Phase3B〜3D

- **Phase3B**: ユーザーのローカル環境で実J-Quants V2データによる初回End-to-End Backtest
  (`RUN_20260816T164133244945`)に成功し、Infrastructure/Integration Validationとして完了。
- **Phase3C**: 固定4銘柄ではなくPoint-in-Time Universeを扱えるようにした。
  `lib/universe.py`の`PitCoverage`/`PitMasterUniverseProvider`(decision_atごとに
  Masterへ再問い合わせ)、`build_common_stock_universe`(普通株の明示的な定義)、
  `UniverseResolution.PARTIAL`(Survivorship Biasを解消できていない場合にRESOLVEDと
  自称しない)。J-Quants Master `date`パラメータの真のPIT性を実データ(6502 東芝)で
  確認済み(D0039)。
- **Phase3D**: J-Quantsだけに依存しない情報基盤(Multi-Source Data Foundation)の
  共通Architectureを新設した(D0040、実データへの接続はまだ行っていない)。
  `lib/sources/`(Data Catalog・Capability-based Provider Protocol・Canonical
  Entity Registry)、`lib/evidence/`(Evidence Type・PIT/Revision History・
  News Dedup・Relevant Retrieval・EvidencePacket・Decision Evidence Log)。
  DEFAULT STANCE = DISCONFIRM, NOT CONFIRMを上位原則としてRESEARCH_RULES.mdへ
  追加し、情報件数の多数決禁止・Evidence不足の自動昇格禁止をSchema/testで
  構造的に強制する(Anti-Confirmation Test、`13_tests/test_evidence_packet.py`)。
  **Source Authority(出所の位置づけ)とEvidence Content(内容そのものの信頼性)は
  分離して扱う**(D0041、`SourceAuthorityClass`は信頼度スコアではない)。
  詳細は`DATA_SOURCE_ARCHITECTURE.md`/`EVIDENCE_MODEL.md`参照。Phase4の
  接続順・優先原則も`DATA_SOURCE_ARCHITECTURE.md`「Phase4 Roadmap」参照。
  Phase4開始前のArchitecture Cleanup(D0042: Source/Delivery Provider分離、
  Backtest/Experimentの完全Offline原則、market_public_at/provider_available_at
  の区別、Fundamental Schema Contract予約)はDECISIONS.mdを参照。
- **Phase4A**: J-Quants Fundamentals/Financial Summary(`/v2/fins/summary`)の
  実装(`lib/fundamentals/`、D0043)。公式仕様(`jpx.gitbook.io`)へは本セッションから
  一切疎通できず(証拠はDECISIONS.md D0043参照)、Field名は未検証のまま実装した。
  Disclosure単位のSchema・Actual/Forecast/当期/翌期/連結非連結の分離・
  `ValueAvailability`(PRESENT/NOT_APPLICABLE/MISSING_OR_UNSPECIFIED/UNKNOWN)・
  Revision非Leak保証(`fundamentals_as_of()`)・Offline再現性はFixtureで検証済み
  (Lab 291テスト)。Status = `CODE_COMPLETE_AWAITING_LOCAL_VALIDATION`
  (実データでのローカル検証待ち、Phase4Bへは未着手)。
