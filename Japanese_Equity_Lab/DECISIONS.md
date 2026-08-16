# DECISIONS.md

仕様上の指示にない、または既存要件と衝突するために下した実装判断を記録する。
既存のコードやHypothesis/Strategyを書き換える判断は行わず、常に追記する。

---

## D0001 — 2026-08-16: `Japanese_Equity_Lab/` を既存リポジトリのサブディレクトリとして配置

**変更内容**: 提案されたトップレベル構成をリポジトリ直下に直接展開するのではなく、
`Japanese_Equity_Lab/` というサブディレクトリの下に配置した。

**理由**: リポジトリルートには既に日本株・米国株スクリーニングツール用の `CLAUDE.md` /
`README.md` / `core/` / `app.py` / `tests/` が存在する。新設計が要求する
`CLAUDE.md` / `README.md` をルート直下に上書きすると既存ツールの規約・ドキュメントが失われる。

**メリット**: 既存のスクリーニングツールをそのまま維持できる。Claude Codeはディレクトリスコープの
`CLAUDE.md` を認識するため、`Japanese_Equity_Lab/CLAUDE.md` はこのサブツリー内でのみ有効な
追加規約として機能し、ルートの規約(コーディング規約・postEdit品質ゲート等)とも両立する。

**デメリット**: 提案されたディレクトリツリーとパスが1階層深くなる(例:
`04_hypotheses/` ではなく `Japanese_Equity_Lab/04_hypotheses/`)。

---

## D0002 — 2026-08-16: 共有Pythonロジック用に `lib/` を新設

**変更内容**: 提案された `00_config` 〜 `99_archive` の番号付きディレクトリに加えて、
`Japanese_Equity_Lab/lib/`(schemas / backtest / registry)を新設した。

**理由**: 提案構成には成果物(データ・Markdown・JSON)の置き場はあるが、それらを生成・検証する
共有Pythonコードの置き場が明示されていない。`10_agents/` `11_skills/` はエージェント/Skillの
役割定義用であり、汎用のschemaクラスやBacktest Engineを置く場所として適切ではない。

**メリット**: 既存リポジトリの `core/` ↔ `tests/` という「UI非依存ロジックとテストを1対1対応させる」
規約をそのまま踏襲できる。`13_tests/` が `lib/` の各モジュールに対応する。

**デメリット**: 提案されたディレクトリツリーに存在しない階層が増える。

---

## D0003 — 2026-08-16: Phase 1のスコープを「骨格」に限定

**変更内容**: Backtest Engineは実際に価格データを読み込んで売買シミュレーションを行う実装ではなく、
インターフェース・データ構造・Point-in-Timeガード・Benchmark比較の計算ロジックのみを実装した。
Agents(10_agents/)・Skills(11_skills/)は役割定義のREADMEのみとし、実行可能なコードは実装していない。

**理由**: 依頼文中の「Ver.1で最初に作るもの」Phase 1の定義が
「フォルダ構造・schema・Backtest Engineの骨格・Benchmark比較・Experiment Registry・Provenance管理」に
限定されており、実データでの実行(Phase 2)やAgents/Skillsの本格実装(Phase 4)は明示的に後続フェーズ。

**メリット**: 一度に巨大な実装をせず、各要素を独立してレビュー・テスト可能にする。

**デメリット**: このセッションの成果物だけでは実際にバックテストを1件も実行できない
(Phase 2で価格データ取得ロジックを追加する必要がある)。

---

## D0004 — 2026-08-16: `lib/schemas/*` は `kw_only=True, frozen=True` のdataclassで統一

**変更内容**: 既存の `core/models.py` は可変(非frozen)な位置引数対応dataclassだが、
`Japanese_Equity_Lab/lib/schemas/` の全schemaは `RecordMeta` を継承し
`kw_only=True, frozen=True` で統一した。リストではなく `tuple[str, ...]` を使う。

**理由**: 本要件は「raw dataはimmutable」「Paper Tradeの理由は後から書き換えない」
「LOCKED後のHypothesisは書き換えない」など、値の不変性そのものが検証ルールの一部になっている。
frozen dataclassにすることで、誤った書き換えを実行時エラー(`FrozenInstanceError`)として
検知できる。変更は常に `dataclasses.replace()` で新しいインスタンスを作る。
`kw_only=True` はフィールド数が多いschemaで、デフォルト値の有無によるフィールド順序制約を
なくし、また誤った位置引数渡しを防ぐ。

**メリット**: 不変性が型システム・実行時エラーで保証される。テストでも
`test_paper_trade_reason_cannot_be_rewritten` のように直接検証できる。

**デメリット**: `core/models.py` とスタイルが異なる(既存コードとの一貫性は薄れる)。
このスタイル差は意図的なものとして、このファイルに明記する。

---

## D0005 — 2026-08-16: `lib/` を独立したトップレベルパッケージとしてimportする

**変更内容**: `Japanese_Equity_Lab/13_tests/conftest.py` は repo root ではなく
`Japanese_Equity_Lab/` ディレクトリ自体を `sys.path` に追加する。
そのため `lib/` 配下のコードは `from lib.schemas.idea import Idea` のように
`Japanese_Equity_Lab.` プレフィックスなしでimportする。

**理由**: `00_config` 〜 `99_archive` は先頭が数字のためPythonの正式なパッケージ名にできない
(例: `13_tests` は `import 13_tests` できない)。そのため `Japanese_Equity_Lab/` 自体を
`__init__.py` 付きのパッケージにする設計は採用せず、既存リポジトリの
`core/`(repo rootを`sys.path`に追加し `from core.models import ...` する)と同じパターンを、
1階層下の `Japanese_Equity_Lab/` を基準に踏襲した。`13_tests/` には `__init__.py` を置かない
(pytestのprepend importモードで、ディレクトリ名がPython識別子でなくても収集できる)。

**メリット**: 既存の `tests/conftest.py` と全く同じパターンで一貫性がある。

**デメリット**: `Japanese_Equity_Lab/` を独立したPythonパッケージとして
外部から `import Japanese_Equity_Lab.lib...` することはできない
(将来UI等から呼び出す場合は同様に `sys.path` 操作が必要)。

---

## Phase 1.1(2026-08-16): Phase1完了後のレビュー指摘に対する修正

Phase1完了報告に対し、東証取引時間の制度変更未反映・Close-to-Close look-ahead・
mypy対象範囲・record versioning・Corporate ActionのPIT安全性・Survivorship bias対応の
前提(Universe)の6点の指摘を受け、以下の判断を行った。

## D0006 — 東証取引時間をmarket_calendar.pyに集約し、2024-11-05の延長を反映

**変更内容**: `lib/point_in_time.py` に直書きしていた `TSE_MARKET_CLOSE = 15:00` 固定値を廃止し、
新設した `lib/market_calendar.py` に `session_close_at()` / `session_open_at()` /
`SessionSchedule` を集約した。東証現物市場の後場終了時刻は2024-11-05に15:00→15:30へ
延長されたため、`market_close_time()` は日付が2024-11-05以降かどうかで15:00/15:30を
切り替える。

**理由**: 制度変更は今後も起こりうる。ハードコードを1箇所(market_calendar.py)に
集約しておけば、次に取引時間が変わってもここだけ直せばよい。

**メリット**: `lib/backtest/engine.py` の Close-to-Close判定など、大引け時刻に依存する
全てのロジックが自動的に正しい時刻を参照するようになる。

**デメリット**: 2024-11-05より前の日付を扱うバックテストで、この日付境界の実装ミスが
あると誤ったCloseを使ってしまうリスクがある(テスト`test_session_close_before_20241105_is_1500`
/ `test_session_close_from_20241105_is_1530` で境界日を直接検証して軽減)。

## D0007 — Close-to-Close禁止のため DecisionWindow に `information_used_at` を追加

**変更内容**: `DecisionWindow` を `(decision_at, execution_at)` の2フィールドから
`(information_used_at, decision_at, execution_at)` の3フィールドに変更した。
Point-in-Timeガード(`assert_no_lookahead`)は `decision_at` ではなく
`information_used_at` を基準にするよう変更。さらに、`decision_at` がその日の
大引け時刻と一致し、かつ `execution_at` が同日中(`execution_at.date() <= decision_at.date()`)
の場合は無条件に `LookAheadBiasError` を送出するようにした。Ver.1のデフォルト
Execution Modelを体現する `build_close_to_next_open_window()` を追加し、次の取引日は
呼び出し側に明示的に渡させる(祝日カレンダーが無い状態で `+1日` を自動計算すると
休場日を執行日にしてしまうため)。

**理由**: `available_at <= decision_at` だけでは、「当日Closeの情報でシグナルを作り、
その同じClose価格で約定する」という現実には実行不可能な取引を防げない
(Close時点でその日の出来高・最終気配は既に確定しており、同じ価格で新規に
売買を成立させることはできない)。

**メリット**: Ver.1のデフォルト運用(Close情報→翌営業日Open執行)を型レベルで強制できる。
Closing Auction等の特殊なExecution Modelは `ExecutionModel` enumに列挙だけしておき、
実装はしない(将来別モデルとして追加)。

**デメリット**: `DecisionWindow` のコンストラクタが3引数必須になり、既存の呼び出し箇所
(テスト含む)を全て更新する必要があった。

## D0008 — Corporate ActionのPoint-in-Time安全性は `announced_at` 基準で判定

**変更内容**: `apply_split_adjustments_as_of(raw_bars, actions, as_of=...)` を追加。
`effective_date <= as_of` ではなく `announced_at <= as_of` を基準に、反映してよい
Corporate Actionを絞り込む。`announced_at` が無い(None)Corporate Actionは
`LookAheadBiasError` で拒否する(黙って除外しない)。

**理由**: 分割の「発表」と「効力発生(effective_date)」は別時点であり、
発表済みの将来効力発生イベントを織り込むこと自体は正当な公開情報の利用だが、
**未発表の将来イベント**で過去の調整済み価格を計算するのは典型的なlook-ahead bias
(未来の分割を知っている前提で過去のFeatureを綺麗にしてしまう)。

**メリット**: Raw priceは一切書き換えず、Adjusted OHLCVの生成ロジックだけで
PIT安全性を保証できる。

**デメリット**: `announced_at` を持たない既存の `apply_split_adjustments()`
(全件反映版)と、PIT対応版の2関数が並存する。全件反映版は「最新の調整済み系列を
表示用に作る」等、PIT安全性が要求されない用途向けとして残す。

## D0009 — UniverseProviderはPhase1.1ではInterface + synthetic実装のみ

**変更内容**: `lib/universe.py` に `UniverseProvider` Protocol、`ListingRecord` schema、
`ListingBasedUniverseProvider`(synthetic data向けの素朴な実装)を追加した。
`listings` が空の場合は `UniverseResolution.DATA_UNAVAILABLE` を返し、
「投資可能銘柄が0件だった」という架空の結論を出さない。

**理由**: 依頼は「Phase1.1ではInterface + synthetic testのみで構わない」と明示していた。
実データソース(証券コード一覧、上場/廃止日等)は現時点で疎通確認できていないため、
実装をここで急ぐと未検証のフィールド名・API仕様に依存する結果になる
(README.mdに記載の既存の制約と同じ理由)。

**メリット**: Survivorship bias対応の型・Interfaceだけ先に固定できる。Phase2で
実データソースと接続する実装を追加する際、この Protocol を満たせばよい。

**デメリット**: Phase1.1時点ではPaper Trading/Backtestからこの Universe が実際には
まだ使われていない(接続はPhase2)。

## D0010 — Record versioning(record_id/record_version/supersedes_record_id/content_hash)は見送り

**検討内容**: 全schema共通で汎用的な版管理フィールド(`record_id` / `record_version` /
`supersedes_record_id` / `content_hash`)を導入するかどうかを検討した。

**判断**: Phase1.1では導入しない。`Hypothesis` には既に専用の系譜追跡
(`parent_hypothesis_id` + `locked_terms_hash`、LOCK時のみhash確定)があり、これは
「条件を勝手に変えない」というHypothesis固有の要求から生まれた設計であって、
他のschema(Idea/Strategy/Knowledge/PaperTrade等)に同じ粒度の改訂追跡が必要かは
現時点で実運用例が無く判断できない。

**理由**: 汎用スキームを先に設計すると、(1) どの単位を「1レコード」とするか
(ファイル単位か、フィールドの論理的なまとまりか)、(2) `content_hash` の対象範囲
(全フィールドか、Hypothesisのように意味のある「terms」のみか)、(3) 既存の
append-only Experiment Registryやfrozen dataclass設計とどう整合させるか、を
決め打ちすることになり、過剰設計になるリスクが高い。

**代わりに行ったこと**: `RecordMeta` に `updated_at` の意味(このスナップショットが
最後に導出・確定した時刻。既存ファイルの書き換えには使わない)を明文化した
(`lib/schemas/base.py` docstring参照)。

**Phase2以降で再検討する条件**: Idea/Strategy/Knowledge等で実際に「同じ対象を
改訂したい」という要求が具体的に発生した時点で、`Hypothesis.revise()` のパターンを
一般化する形で導入を検討する。

---

## D0011(D0008の修正)— Corporate Actionの「known_at」と「adjustable_at」を分離

**問題**: D0008で実装した `apply_split_adjustments_as_of()` は `announced_at <= as_of`
(known_at基準)でCorporate Actionを絞り込んだ後、絞り込んだactionをそのまま
`apply_split_adjustments()` に渡していた。しかし`apply_split_adjustments()`内部の
調整ロジックは `bar.session_date < action.effective_date` のみでfactorを計算するため、
「発表済みだが、まだeffective_dateを迎えていない」Corporate Actionが、`as_of`が
`effective_date`より前であっても調整に反映されてしまうbugがあった
(例: 8/1発表・10/1効力発生の分割を、8/15時点のFeature計算で既に適用してしまう)。
これは指摘の通りlook-ahead biasである(8/15時点で実際に市場で成立していた価格を、
まだ発生していない未来の分割比率で書き換えてしまうため)。

**修正内容**: `is_known_at(action, as_of)`(= `announced_at <= as_of`)と
`is_adjustable_at(action, as_of)`(= `session_open_at(effective_date) <= as_of`)を
分離した関数として定義した。`apply_split_adjustments_as_of()` は:
1. 全actionが`is_known_at`であることを検証する(既知でなければ `LookAheadBiasError`)。
2. その上で`is_adjustable_at`なactionのみを調整対象として`apply_split_adjustments()`に渡す
   (`is_known_at`だが`is_adjustable_at`でないactionは、エラーにはせず単に除外する。
   これは意図した挙動であり、「発表は知っているが、まだ実施されていないので調整しない」
   という正しいPIT境界を表す)。

**メリット**: Event情報としての「知っている」(known_at)と、Price Series調整として
「反映してよい」(adjustable_at)が明確に分離され、テスト
(`test_apply_split_adjustments_as_of_does_not_adjust_before_effective_date` /
`test_apply_split_adjustments_as_of_adjusts_once_effective_date_has_passed`)で
両者の境界を直接検証できるようになった。

**デメリット**: 既存の `apply_split_adjustments_as_of` 呼び出し側(まだ実運用は無い)の
挙動が変わる。announced_atのみで判定していた前提のコードがあれば要修正だが、
Phase1.1〜1.2時点でこの関数の呼び出し実績は無いため影響なし。

---

## Phase 2(2026-08-16): 実データPipelineの実装

## D0012 — このセッションはJ-Quants等の外部APIに一切疎通できない(ネットワークポリシー)

**事実確認**: `api.jquants.com` / Yahoo Finance / `example.com` 等、複数のホストへの
接続を試みた結果、すべてエージェントプロキシのポリシーにより403で拒否された
(`curl: CONNECT tunnel failed, response 403`)。これはこのセッション固有の一時的な
問題ではなく、環境のネットワークポリシーによる恒久的な制限である。

**判断**(ユーザーとの確認の上で決定): `JQuantsAdapter`はJ-Quants公式ドキュメントに
基づいて完全に実装するが、実際の接続確認はこのセッションでは行わない。Pipeline全体の
動作確認は、`DataSourceAdapter` Interfaceを満たす`FixtureDataSourceAdapter`(合成データ)
で行う。合成データであることは`13_tests/fixtures/README.md`、
`lib/data_sources/fixture.py`のdocstring、Snapshot manifestの`source="fixture"`
フィールドなど複数箇所で明示し、実際のJ-Quants出力であるかのように偽装しない。

**メリット**: `DataSourceAdapter`という抽象化のおかげで、Backtest Engine側のコードは
実データか合成データかを一切区別しない。ユーザーがローカル環境で
`.env`にJQUANTS_REFRESH_TOKENを設定した上で
`python scripts/jquants_lab_pipeline.py --source jquants` を実行すれば、
同じPipelineがそのまま実データで動く設計になっている。

**デメリット**: `JQuantsAdapter`のエンドポイント・フィールド名は実レスポンスで検証できて
いない(既存の`core/providers/jquants.py`と同じ既知の制約)。本番投入前に必ず
ローカル環境で疎通確認すること。

## D0013 — TOPIX等のインデックス取得は未実装(Phase3 TODO)

**問題**: J-Quantsの個別銘柄日次株価(`/prices/daily_quotes`)とTOPIX等の指数データは
別エンドポイント(`/indices`等)で提供されている可能性が高いが、このセッションからは
実際のAPI仕様を検証できないため、確度の低い実装を「TOPIX取得」として書くことを避けた。

**判断**: `JQuantsAdapter`は個別銘柄用の`fetch_daily_quotes`のみを実装し、指数専用の
fetchメソッドは実装しない(Phase3で実データ疎通確認後に追加する)。Pipelineの
Benchmark比較機能そのものは、fixtureデータに含めた合成Benchmark系列(`TOPIX_SYNTH`、
実際のTOPIXではないことを明示)で動作確認した。

**デメリット**: `--source jquants`で実行する場合、呼び出し側が`--benchmark-code`に
実在する個別銘柄コードを指定しない限り、真のTOPIX Benchmark比較はできない
(Phase3で`/indices`相当のfetchメソッドを追加するまでの既知の制約)。

## D0014 — 🚫 BLOCKING TODO: Corporate Actionsの取得元が未実装のため、Phase2のPipelineはsplit調整なし

**判断**: `scripts/jquants_lab_pipeline.py`は`RawOHLCVBar` -> `AdjustedOHLCVBar`の変換に
`apply_split_adjustments(bars, actions=[])`を使う(=常に無調整)。理由は、
J-Quantsから「株式分割の公表時刻(announced_at)」を取得する具体的なエンドポイントを
このセッションでは検証できておらず、確度の低い実装をするより「未調整であることを
明示する」方が安全なため。RawとAdjustedを明示的に分離する変換ステップ自体は必ず通す
(=`RawOHLCVBar`をそのまま返さず、`AdjustedOHLCVBar`(factor=1.0)へ変換してから
Backtest Engineに渡す)。

**🚫 BLOCKING(Phase2.1で格上げ)**: これは単なるTODOではなく、**実際の日本株を対象にした
(投資判断に使う)Backtestを開始する前に必ず解決しなければならないBLOCKING TODO**である。
対象期間・対象銘柄に株式分割等があった場合、無調整のまま計算されたリターンは誤りになる。
`scripts/jquants_lab_pipeline.py`は`--source jquants`実行時にこの警告を必ず表示する。

**Phase3 TODO**: J-Quants(または他のソース)からCorporate Actionsを
`announced_at`付きで取得する方法を確定し、`apply_split_adjustments_as_of`を
Pipelineに組み込む。

## D0015 — Provenanceの6段階チェーンは単純な線形モデルとして実装

**内容**: 「Experiment -> Hypothesis -> Strategy -> Processed Dataset -> Raw Snapshot ->
Source Request」を、各ノードが直接の親を1つだけ持つ線形チェーンとして実装した
(`lib/registry/provenance.py`の`ProvenanceStore`は元々D0009時点でこの制約を持つ)。

**理由**: 実際には1つのExperimentが複数のRaw Snapshot(価格+カレンダー等)や
複数のHypothesis由来のIdeaに依存しうるため、真に正確なモデルは有向非巡回グラフ(DAG)
だが、Phase2の目的は「Pipelineが最後まで一本通る再現可能な経路を持つこと」であり、
完全なDAG追跡の実装は過剰設計と判断した。`trace_to_origin()`は代表的な1系統
(daily_quotes snapshot経由)のみを遡る。

**Phase3以降で再検討する条件**: 複数の親を辿る必要が実運用で生じた場合、
`ProvenanceStore.all()`で全リンクを取得した上で、DAG探索に拡張する。

## D0016 — Raw Snapshot(実データ)は`.gitignore`対象、fixture Snapshotのみ追跡

**内容**: `Japanese_Equity_Lab/01_data/raw/jquants/`を`.gitignore`に追加した。
`01_data/raw/fixture/`(このセッションで動作確認した合成データのSnapshot)は
追跡対象のまま残す(Pipelineが実際に動いた証跡として、小さく再現可能なため)。

**理由**: 実データのRaw Snapshotは銘柄数・期間が増えると容量が大きくなり、
個人の取得タイミングに依存する(誰が実行しても同じ内容にはならない)ため、
`data/*.sqlite3`が既存リポジトリでgitignoreされているのと同じ理由で追跡しない。

**Phase3Aでの追記**: `LocalSnapshotAdapter`(`--source local`)が生成するRaw Snapshot
(`01_data/raw/jquants_local/`)も同じ理由で`.gitignore`へ追加した(D0025)。このセッションで
scratch検証用に生成した`jquants_local/`配下のファイルはコミット対象から外し、ローカルの
作業ディレクトリからも削除した(実データでも合成scratch dataでもない中途半端な検証物を
恒久的な証跡として残さないため)。同じ理由で、fixture Snapshotについても、既存の
デモとメトリクスが完全に一致するだけの重複した動作確認runは追加コミットしない
(`06_backtests/experiment_registry.jsonl`・`provenance.jsonl`は既存のPhase2.2デモのままで、
Phase3Aの動作確認(D0025のリファクタリング前後比較)はDECISIONS.mdの記述と
`13_tests/`のテストで裏付ける)。

---

## Phase 2.1(2026-08-16): Backtest Sample Metrics厳密化・Execution Outcome記録・再現性強化

Phase2完了報告に対し、sample_sizeの曖昧さ・Event StudyとPortfolio Simulationの区別・
価格欠損時のsilent skip・available_at/retrieved_atの混同確認・reproducibilityへの
git_dirty追加・Corporate ActionのBLOCKING TODO明示の6点の指摘を受け、以下を実施した。

## D0017 — `BacktestMetrics.sample_size`を廃止し、signal/execution関連の指標を明示

**変更内容**: `sample_size`(意味が曖昧: 銘柄数なのかトレード数なのか不明瞭だった)を
`unique_tickers`に改名した。さらに`signal_count` / `executed_count` / `unexecuted_count` /
`execution_rate` / `unique_entry_dates` / `execution_outcomes`を新設した。
`TradeResult`に`entry_date: date`を追加(`unique_entry_dates`計算に必要)。

**理由**: 「trade_countが多い」ことと「独立した検証を多数行った」ことは同義ではない。
holding期間が重なるtradeは統計的に独立なサンプルとみなせない。`unique_entry_dates`を
`trade_count`と並べて表示することで、この違いを利用者が見落とさないようにする。
また、「シグナルは出たが執行できなかった」件数を隠さず`unexecuted_count`として
表示することも、Multiple Testingの原則(良い結果だけを見せない)をシグナル単位にも
拡張する狙いがある。

**デメリット**: `BacktestMetrics`のフィールド数が増え、`compute_metrics()`の呼び出しが
やや複雑になった(`signal_count`/`execution_outcomes`を渡さない場合は
`execution_rate=None`になる後方互換動作とした)。

## D0018 — Portfolio SimulationのデフォルトをNO_REENTRY_WHILE_POSITION_OPENとし、
Event Studyとの違いを明文化

**変更内容**: `PositionPolicy`(現時点では`NO_REENTRY_WHILE_POSITION_OPEN`のみ)を
`BacktestRunConfig`に追加し、`BacktestEngine.run()`の既定動作とした。同一銘柄で
既にポジションを保有している間に出た追加シグナルは`ExecutionOutcome.SKIPPED_POSITION_OPEN`
として記録し、新規建てしない。RESEARCH_RULES.mdに「Event StudyとPortfolio Simulationの
違い」を新設し、Event Studyでoverlapping observationsを許容する場合はその旨を明記する
運用ルールを追加した。

**理由**: `run()`が実装するのはPortfolio Simulation(実際に資金を配分する前提)であり、
同一銘柄への重複建てを黙って許すとholding期間の重複によるサンプルの疑似独立性が
生まれてしまう。Event Study的な分析(overlap許容)をしたい場合は`compute_metrics()`を
直接使う経路を用意し、`run()`とは別の関心事として明確に分離した。

## D0019 — Execution Outcomeを必ず記録し、silent skipを廃止

**変更内容**: `ExecutionOutcome`(`EXECUTED` / `UNEXECUTABLE_NO_OPEN` / `MISSING_PRICE` /
`OUTSIDE_DATA_RANGE` / `SKIPPED_POSITION_OPEN`)を導入し、`run()`内の全ての
`continue`(スキップ)経路で対応するoutcomeを`Counter`に記録するようにした。
`BacktestMetrics.execution_outcomes`として最終結果に残す。

**理由**: Phase2完了時点の実装は、価格欠損・Calendar範囲外のトレードを黙って
スキップしており、「何件のシグナルのうち何件が何の理由で執行できなかったか」が
結果から分からなかった。これは「良い結果だけを見せない」というRESEARCH_RULES.mdの
原則に反する。

**テスト時に判明した注意点**: `NO_REENTRY_WHILE_POSITION_OPEN`の下では、ある1回の
価格欠損が「その特定のトレードを消す」とは限らない(翌営業日に再試行して成功しうる)。
このためテストは`trade_count`の増減ではなく`execution_outcomes`の中身を直接検証する
形に修正した(`test_run_skips_trades_with_missing_execution_price_instead_of_fallback`)。

## D0020 — Reproducibility Fingerprintに`git_dirty`を追加

**変更内容**: `lib/reproducibility.is_git_dirty()`(`git status --porcelain`の出力有無で判定、
判定不能ならNone)を追加し、`ReproducibilityFingerprint.git_dirty`として記録するようにした。
`scripts/jquants_lab_pipeline.py`はdirtyな場合、標準出力に警告を表示する。

**理由**: `code_commit`だけでは、そのコミット以降にworking treeを変更した状態で
実行した場合に「完全に同じコードで実行した」ことを保証できない。`git_dirty=True`を
明示することで、再現性が保証されない実行だったことをExperiment記録から追跡できる。

## D0021 — available_atとretrieved_atの分離を専用テストで確認

**変更内容**: `13_tests/test_available_at_vs_retrieved_at.py`を新設し、(1)数年前の市場
データを「今日」取得しても`available_at`は当時の大引けのままであること、(2)仮に
`retrieved_at`を`available_at`として誤用した場合にLook-ahead判定が壊れることの両方を
直接確認した。`lib/data_sources/base.RawFetchResult.retrieved_at`のdocstringに
両者の違いを明記した。

**確認結果**: `BacktestEngine.run()`は`available_at`を常に`lib.market_calendar.session_close_at()`
(市場の大引け)から導出しており、`retrieved_at`を一切参照していないことをソースコード上でも
直接確認した(`test_engine_derives_available_at_from_market_close_not_retrieved_at`)。
既存実装が既にこの意味を満たしていたため、ロジック自体の修正は不要だった。

---

## Phase 2.2(2026-08-16, Phase2 FINAL微修正): Execution Metrics分離・Behavioral Test・Portfolio Scenario Fixture

Phase2.1完了報告に対し、(1)SKIPPED_POSITION_OPENがExecution Failureと同じ
「unexecuted」に丸められている、(2)available_at/retrieved_atのテストがソース読解に
留まっている、(3)Portfolio Simulation固有の挙動(Policy Skip・Execution Failure・
複数銘柄・保有中再Signal)を専用に確認するFixtureが無い、の3点の指摘を受け、
以下を実施した。この対応をもってPhase2をFINALとして扱う(ユーザー指示)。

## D0022 — Policy SkipとExecution Failureを分離した指標へ再編

**変更内容**: `BacktestMetrics.unexecuted_count` / `execution_rate`(Phase2.1で導入)を
廃止し、`policy_skipped_count` / `order_attempt_count` / `execution_failed_count` /
`signal_to_trade_rate` / `order_execution_rate`に置き換えた。`ExecutionOutcome`は
維持しつつ、`POLICY_SKIP_OUTCOMES`(`SKIPPED_POSITION_OPEN`)と
`EXECUTION_FAILURE_OUTCOMES`(`UNEXECUTABLE_NO_OPEN` / `MISSING_PRICE` /
`OUTSIDE_DATA_RANGE`)という2つの分類集合を新設し、`compute_metrics()`は
`execution_outcomes`からこれらを機械的に集計する(呼び出し側が別途カウントを
渡す必要はない)。

**理由**: Phase2.1時点の`unexecuted_count = signal_count - executed_count`は、
「Portfolio Policyにより意図的に見送った」ことと「執行しようとしたが失敗した」ことを
同じ数字に丸めてしまい、Pipelineの健全性(データ欠損がどれだけあるか)と
Portfolio Policyの効き方(重複建てをどれだけ防いでいるか)を区別できなかった。

**デメリット**: またしてもBacktestMetricsのフィールドが変わるため、Phase2.1で
一度archiveした demoデータと同様、Phase2.1時点のexperiment_registry.jsonlも
現行スキーマでは読み込めなくなる。同じ手順(archiveへ退避、コードで再実行)で対応した。

## D0023 — available_at/retrieved_atの分離をBehavioral Testで直接確認

**変更内容**: `13_tests/test_available_at_vs_retrieved_at.py`に、ソースコード読解だけでなく
実際にPipelineを動かして確認するテストを追加した。
(1) 同一payload(同一のavailable_at相当)で`RawFetchResult.retrieved_at`だけを
大きく変えた2つのSnapshotから、変換〜`BacktestEngine.run()`までの全経路を実行し、
`BacktestMetrics`が完全に一致することを確認(`test_retrieved_at_changing_alone_does_not_change_the_investment_decision`)。
(2) `available_at`だけを未来へ変更すると`BacktestEngine.build_signal_input()`が
`LookAheadBiasError`を送出することを確認
(`test_moving_available_at_into_the_future_triggers_lookahead_error_via_engine`)。

**理由**: 「ソースコードにretrieved_atという文字列が出てこない」ことの確認だけでは、
将来別の場所で誤って混同するリグレッションを検知できない。実際の挙動として
「retrieved_atを変えてもInvestment Decisionは変わらない」「available_atを変えると
PIT判定が変わる」という対称的な結果を、同じ形式のテストとして残すことで、
今後この分離が崩れた場合にテストが失敗するようにした。

## D0024 — Portfolio Scenario Fixtureを追加(System Behavior Test専用)

**変更内容**: `13_tests/fixtures/portfolio_scenario.json`を新設した。既存の
`synthetic_jquants_daily_quotes.json`(Pipeline Validation Strategy用、単調な右肩上がり/
右肩下がりデータ)とは別に、Portfolio Simulationの分岐(Policy Skip・Execution Failure・
複数銘柄・異なる日付でのSignal・正常なExecution/Exit)を1本のシナリオへ意図的に
詰め込んだ。Signalの発生日は間接的な条件(モメンタム等)ではなく、fixtureの
`_scenario.signal_dates`が示す日付そのものを使う専用のsignal_fnで直接指定する
(`13_tests/test_portfolio_scenario.py`)。

**理由**: 既存のPipeline Validation Fixtureは単調な価格推移のため、
`SKIPPED_POSITION_OPEN`や`UNEXECUTABLE_NO_OPEN`が「たまたま」発生することはあっても、
狙って発生させたものではなかった。Portfolio Simulation固有の分岐を確実にカバーする
専用のFixtureを用意し、Strategy Performance評価に使うFixtureとは目的を明確に分離した
(fixture冒頭の`_disclaimer`に明記)。

---

## Phase 3A(2026-08-16): 実J-Quantsデータ投入によるPipeline End-to-End検証

Phase2 FINAL後、「Phase2までfixtureで検証したResearch Pipelineに、実際のJ-Quants
日本株データを投入しても、既存設計を壊さずEnd-to-Endで動作するか」を確認する目的で
着手した。本セッションでもD0012同様、J-Quants等の外部APIへ一切疎通できないことを
最初に再確認した(`api.jquants.com`へのCONNECTが403で拒否、D0012時点と同一の症状)。
そのため本Phaseの実データ検証は、ユーザーがローカル環境で取得したJ-Quantsレスポンスを
読み込む`LocalSnapshotAdapter`経由の経路を新設し、その経路で「配管(pipeline plumbing)」を
検証することに主眼を置いた。「実際の市場データでの検証」そのものは、ユーザーが
ローカルでデータを取得してこのPipelineに投入するまで完了しない(Phase3A完了報告参照)。

## D0025 — `LocalSnapshotAdapter`を新設し、`--source local`でPipelineに接続

**変更内容**: `lib/data_sources/local_snapshot.py`に、ユーザーがローカル環境で
あらかじめ取得したJ-Quants JSON/CSVファイル(`daily_quotes_<code>.json`等の命名規約、
モジュールdocstring参照)を読み込み、既存の`DataSourceAdapter` Protocolを満たす
`LocalSnapshotAdapter`を実装した。`scripts/jquants_lab_pipeline.py`に
`--source {jquants,fixture,local}`と`--local-snapshot-dir`を追加し、
`_build_adapter()`で分岐させた。

**理由**: このセッションからは実際にJ-Quantsへ疎通できないため、「Pipelineが実データの
形状(フィールド名・型・欠損パターン)を正しく扱えるか」を、ネットワーク接続なしに
検証する手段が必要だった。ユーザーが自分のPC(ネットワーク制限のない環境)で
J-Quantsから取得したファイルをこのSourceへ渡すことで、Backtest Engine側のコードを
一切変更せずに実データ検証へ移行できる設計にした(`DataSourceAdapter`抽象化の
恩恵、D0012と同じ設計思想)。

**retrieved_atの扱い**: ファイルのmtimeをデフォルトの`retrieved_at`として使う
(コンストラクタで明示的に上書き可能)。ファイルがいつ取得されたかの正確な記録は
ユーザー自身の管理に委ねる(D0021で確認した通り、`retrieved_at`はPIT判定に使われない
ため、多少不正確でもBacktest結果自体には影響しない)。

## D0026 — `DataSourceAdapter`に`fetch_index_prices`/`fetch_listed_info`を追加

**変更内容**: `lib/data_sources/base.DataSourceAdapter` Protocolへ、指数データ
(TOPIX等)取得用の`fetch_index_prices(index_code, start_date, end_date)`と、
銘柄マスタ取得用の`fetch_listed_info(as_of=None)`を追加した。`JQuantsAdapter`
(`/indices`・`/listed/info`)、`FixtureDataSourceAdapter`(既存fixtureへの
後方互換のため`"indices"`/`"listed_info"`キーが無ければ空ペイロードを返す)、
`LocalSnapshotAdapter`の3実装すべてに追加した。

**理由**: D0013(TOPIX取得は未実装、Phase3 TODO)を解消するため。個別銘柄の
`fetch_daily_quotes`と同じ抽象化パターンをそのまま再利用することで、
Backtest Engine・Benchmark比較ロジック側の変更を発生させずに済んだ。

**未検証の前提(引き継ぎ)**: `/indices`のレスポンス形状は`/prices/daily_quotes`と
同じOpen/High/Low/Close/Volumeを持つという前提で`index_prices_payload_to_raw_bars()`を
実装したが、実レスポンスでの検証はできていない。TOPIXの`index_code`も
`"0000"`と仮定しているが未検証(公式ドキュメントからの推測)。ユーザーがローカルで
実際に`/indices`を叩いた結果、形状やコードが異なる場合は、この関数だけを修正すれば
Pipelineの他の部分には波及しない設計になっている。

## D0027 — Corporate Action Hint検出を「前日比の変化」ベースに修正(バグ修正)

**問題**: `detect_split_hints_from_daily_quotes()`の初期実装は、`AdjustmentFactor != 1.0`
であるすべての行を分割候補として抽出していた。手元で用意したJ-Quants形状の
scratch dataで検証したところ、「分割後もAdjustmentFactorが同じ値を保持し続ける」
という(ありうる)convention下で、1回の分割に対し100件以上の重複したhintが
生成されることが判明した。これは実際のJ-Quantsデータでも同様に誤発火しうる
実バグと判断した(単なるテストデータの偶然ではない)。

**変更内容**: 銘柄コードごとに前日の`AdjustmentFactor`を追跡し、
「前日から値が変化し、かつ1.0でない」日だけをhintとして抽出するよう修正した
(`Japanese_Equity_Lab/lib/data_sources/convert.py`)。この方式は、
「変化した初日だけ1.0以外になる」実装・「変化後も同じ値を保持し続ける」実装の
どちらのconventionでも重複なく効力発生日候補を抽出できる。回帰テスト
(`test_detect_split_hints_deduplicates_when_factor_stays_elevated_across_many_days`)
を追加した。

**このhint自体の位置づけ(変更なし)**: `announced_at=None`のまま抽出するため、
既存のPIT-safe変換`apply_split_adjustments_as_of()`に渡すと`LookAheadBiasError`で
拒否される(意図した挙動)。D0014のBLOCKING TODO(announced_at付きCorporate Action
取得元が未実装)は本Phaseでも未解決のまま。このhintは「事後的な参考情報の表示」
以外の用途では使用禁止であることを`_SPLIT_HINT_NOTE`とRESEARCH_RULES.mdに明記する
(Phase3A完了報告参照)。

## D0028 — Universeへ`/listed/info`を接続し、Survivorship Bias自動検出を追加

**変更内容**: `listed_info_payload_to_listing_records()`(`lib/data_sources/convert.py`)で
`/listed/info`ペイロードを`ListingRecord`へ変換し、`scripts/jquants_lab_pipeline.py`が
実データSource(`jquants`/`local`)実行時にこれを`ListingBasedUniverseProvider`へ渡して
`as_of()`を呼ぶようにした。`lib/universe.py`の`UniverseSnapshot`に
`survivorship_bias_unresolved: bool`フィールドを追加し、`ListingBasedUniverseProvider`が
「全listingにdelisting_dateが無い」場合に自動的にTrueを立てるようにした
(`_auto_detect_survivorship_bias()`)。

**理由**: `/listed/info`が(未検証の限りでは)ある時点でのスナップショットに過ぎず、
`listing_date`/`delisting_date`に相当するフィールドを含むかどうかが不明なため、
含まれない場合は正直に`None`のままにし(数値を推測で埋めない方針)、その結果として
「現在の上場銘柄だけを過去へ遡らせている」状態(Survivorship Bias未解消)を
機械的に検出してBacktest結果に警告として残せるようにした。

**この結果に基づくBacktestの解釈上の制約**: Phase3Aで検証した`--source local`経路の
scratch実行では`survivorship_bias_unresolved=True`が常に立った(scratch dataに
delisting_dateを含めなかったため)。実際のJ-Quants `/listed/info`が
delisting_dateを含むかどうかは未検証であり、ユーザーがローカルで実データを
取得した際に確認が必要(Phase3A完了報告のTODO参照)。

## D0029 — 実際の日本の祝日を手動検証したTradingCalendarテストを追加

**変更内容**: `13_tests/test_trading_calendar_real_holidays.py`を新設し、2024年の
実際の祝日・年末年始休場(元日・成人の日・振替休日群・ゴールデンウィーク・
海の日・敬老の日・秋分の日・スポーツの日・文化の日振替・年末休場)を手動で
検証した上で`TradingCalendar`を構築し、(1)平日かつ祝日でない日は取引日、
(2)土日は非取引日、(3)平日だが祝日である日は非取引日(単純な曜日判定では
検出できないケース)、(4)ゴールデンウィークを挟んだ`next_trading_session`/
`previous_trading_session`の解決、(5)範囲外の日付は「平日だから取引日だろう」と
推測せず例外を送出すること、(6)2024-11-05の取引時間変更境界、をそれぞれ確認した。

**理由**: このセッションからは実際のJ-Quants `/markets/trading_calendar`
レスポンスを取得できないため、「機械的な曜日判定ではなく、実際の祝日・休場日を
正しく扱える」ことを、広く確認可能な公知の祝日情報を使って独立に検証した。
このテストは網羅的な祝日カレンダーの提供や祝日判定ロジックの実装ではなく、
既存の`TradingCalendar`(データ駆動、内部にロジックとして祝日を持たない設計)が
正しいtrading_datesさえ与えられれば正しく動くことの確認である。本番運用では
必ずJ-Quants等の実データからTrading Calendarを構築すること(テストファイル冒頭に
明記)。

## D0030 — `scripts/fetch_jquants_local_snapshot.py`を新設し、`LocalSnapshotAdapter`用の
取得手順をコードとして提供

**変更内容**: `JQuantsAdapter`をそのまま再利用してJ-Quants実APIへ接続し、結果を
`LocalSnapshotAdapter`が読める命名規約・JSON形状(`daily_quotes_<code>.json`等)で
`Japanese_Equity_Lab/01_data/raw/local_snapshot_input/`(新規`.gitignore`対象)へ
保存する取得専用スクリプトを追加した。ユーザー向け手順は
`Japanese_Equity_Lab/LOCAL_DATA_FETCH_GUIDE.md`にまとめた。

**理由**: 「ユーザーが手作業でcurl等を叩いてJSONを整形する」手順書だけでは、
エンドポイント名・パラメータ名・認証フローの知識が`JQuantsAdapter`とドキュメントの
2箇所に重複し、どちらかが将来ズレる(ドキュメントの記載が古くなる)リスクがある。
既存の`JQuantsAdapter`をそのまま呼び出すスクリプトにすることで、エンドポイント・
パラメータの唯一の情報源(single source of truth)を`lib/data_sources/jquants.py`に
保つ。取得したペイロード(市場データ)のみをファイルへ書き出し、リフレッシュ
トークン・IDトークンはいかなるファイルにも出力しない(既存の認証情報保護方針を維持)。

**このスクリプトの出力の位置づけ**: `01_data/raw/local_snapshot_input/`は
「ユーザー手元の作業コピー」であり、`lib.snapshot.RawSnapshotStore`が管理する
Immutable Raw Snapshot(`01_data/raw/local/`)そのものではない。正式なSnapshotは
Pipeline実行時(`--source local`)に別途生成される。この区別を明確にするため、
出力先ディレクトリ名を`01_data/raw/jquants/`(D0016で追跡除外済みの、Pipelineが
生成する正式なRaw Snapshot置き場)とは別にした。

---

## Phase 3A.1(2026-08-16): J-Quants API V2 Migration

Phase3A完了報告に対し、ユーザーから「現在の契約プランはLight」「`JQuantsAdapter`が
現行API V2ではなく旧V1仕様をかなり含んでいる」という指摘を受けた。Phase3Bには進まず、
V1依存を全面的に削除しV2へ移行することをPhase3A.1として実施した。

## D0031 — J-Quants API V1依存を全面的に削除し、V2(ユーザー提示仕様)へ移行

**変更内容**: `lib/data_sources/jquants.py`を全面書き換えし、認証方式を
`token/auth_refresh`(リフレッシュトークン→IDトークン)から`x-api-key` Header方式
(環境変数`JQUANTS_API_KEY`)へ変更した。Endpointを以下へ全面差し替えた。

| 旧(V1、削除済み) | 新(V2) |
|---|---|
| `/prices/daily_quotes` | `/v2/equities/bars/daily` |
| `/markets/trading_calendar` | `/v2/markets/calendar` |
| `/indices`(`code="0000"`推測) | `/v2/indices/bars/daily/topix`(TOPIX専用) |
| `/listed/info` | `/v2/equities/master` |
| (無し) | `/v2/indices/bars/daily`(一般指数、既定Pipelineでは未使用) |

Field名も`Open/High/Low/Close/Volume`から`O/H/L/C/Vo`(+`Va`/`AdjFactor`/`AdjO`〜`AdjVo`/
`UL`/`LL`/`MktCap`/`ExRT`)へ、Trading Calendarの`HolidayDivision`から`HolDiv`へ変更した。
レスポンスは`{"data": [...], "pagination_key": ...}`形式を前提とし、`pagination_key`が
返る限り追加リクエストして結合する処理を`JQuantsAdapter._get_all_pages()`に実装した。
`DataSourceAdapter` Protocolのメソッド名も`fetch_daily_quotes`→`fetch_equity_bars`、
`fetch_index_prices`→`fetch_topix_bars`(+`fetch_general_index_bars`)、
`fetch_listed_info`→`fetch_equities_master`へ改名し、`FixtureDataSourceAdapter`・
`LocalSnapshotAdapter`双方も同じInterfaceへ揃えた。V1形状のfixtureファイル
(`synthetic_jquants_daily_quotes.json`・`portfolio_scenario.json`)は
`99_archive/13_tests/fixtures/`へ退避し(削除しない)、V2形状の新fixture
(`synthetic_jquants_v2_bars.json`・`portfolio_scenario_v2.json`)と、Endpoint別の
小さなGolden Fixture(`equities_bars_daily_v2.json`等4種)を新設した。

**Endpoint・Field名の情報源についての重要な注記**: このセッションはJ-Quants公式API・
公式ドキュメント(`jpx.gitbook.io`)のいずれにもネットワークポリシーにより疎通できない
(`WebFetch`でも同一の`EGRESS_BLOCKED`を確認、D0012/D0025と同じ制約)。したがって
上記のV2 Endpoint・Field名は、**ユーザーがこのセッション内のメッセージで明示した仕様を
Canonical Specificationとしてそのまま実装したものであり、このセッション自身が公式資料や
実APIで検証したものではない**。`HolDiv`の値("1"が取引日、等)の意味は特にユーザーからも
明示されなかったため、V1時代の理解(未検証)を暫定的に引き継ぎつつ、
`trading_calendar_payload_to_calendar()`に`trading_hol_div_values`引数を追加し、
実データ確認後に呼び出し側で上書きできるようにした(推測を恒久的な既定値として
固定しないための設計)。ローカル環境での疎通確認後、Field名や値の意味が異なると
判明した場合は`lib/data_sources/jquants.py`・`lib/data_sources/convert.py`のみを
修正すればよい(`BacktestEngine`側は無変更)。

## D0032 — Corporate Actionを「Case A(Announcement Signal)」と「Case B(Price
Series連続化)」に分離し、Case Bはannounced_at無しでもPIT-safeに扱えると判断

**問題**: 既存の`apply_split_adjustments_as_of()`は、`announced_at`が無いCorporate
Actionを一律`LookAheadBiasError`で拒否していた。V2の`AdjFactor`/`ExRT`は公表時刻を
伴わないため、この設計のままではPrice Series連続化(株価が分割で不連続になることを
防ぐ用途)すら一切できなかった。

**判断**: Corporate Actionの用途を以下の2つに明確に分離した。

- **Case A(Announcementを取引Signalとして使う)**: 「将来分割される」という情報を
  事前に知って売買判断に使う用途。これには本物の公表時刻(`announced_at`)が必須であり、
  V2の`equities/bars/daily`にはこの情報が無い(公表時刻を返す別のDisclosure系Endpointが
  必要だが、今回は対象外)。既存の`apply_split_adjustments_as_of()`はこのCase A専用として
  そのまま維持した(挙動・シグネチャとも変更なし)。
- **Case B(Price Seriesの連続化)**: 過去のPrice Featureが分割によって不連続にならない
  ようにする用途。V2の`AdjFactor`/`ExRT`はEvent当日のBar行そのものに機械的に付与される
  (=事前の公表を経由しない)。したがって、その日のBarデータ自体が取得可能になる時刻
  (`session_close_at(effective_date)`、既存のRawOHLCVBarのavailable_atと同じ導出元)を
  過ぎていれば、このEventも同時に「知り得る」情報であり、別途`announced_at`を要求する
  必要は無いと判断した。新設した`build_provider_derived_adjusted_bars()`
  (`lib/schemas/price_data.py`)がこのCase Bを担う。`as_of`時点でまだ取得可能でないはずの
  Eventが混入していれば`LookAheadBiasError`で拒否する(Case Aの「未公表」ケースと同様、
  黙って除外しない)。

**Event検出ロジックの変更(V1→V2)**: `detect_split_hints_from_daily_quotes()`
(前日との差分を見る、Phase3AでD0027として一度修正した実装)を廃止し、
`detect_corporate_action_events_from_equity_bars()`に置き換えた。V2では
「AdjFactorはCorporate Actionの権利落ち日のrecordそのものに記録される」という
ユーザー提示仕様に基づき、前日比較ではなく「その行が`AdjFactor != 1`または`ExRT`が
設定されているか」だけでEvent当日を判定する(ユーザー指定のsynthetic test: Day1
`AdjFactor=1` / Day2 `AdjFactor=0.5,ExRT="1"` / Day3 `AdjFactor=1` →Day2の1件のみ認識、
`test_convert_phase3a.py`で確認)。検出したEventは新設の
`CorporateActionType.ADJUSTMENT_EVENT`(分割か併合かを断定しない汎用型)として扱う。

**未解決のまま残した点(重要)**: `build_provider_derived_adjusted_bars()`は
`raw_adj_factor`をRaw価格へ「乗算」する慣習(`adjusted = raw × Π(未来イベントのfactor)`)を
仮定しているが、この向き(掛けるか割るか)はJ-Quants V2公式ドキュメントで確認できて
いない(このセッションは疎通できない)。誤った向きで適用すると価格を桁違いに歪める
リスクがあるため、`scripts/jquants_lab_pipeline.py`は**この関数を実際のBacktest実行には
まだ組み込まず**(`apply_split_adjustments(bars, [])`のまま、無調整)、Corporate Action
Eventの検出・件数表示のみ行う。したがって、D0014のBLOCKING TODOは実データBacktestに
ついて実質的に残ったままである(理由がCase A/B未分離からAdjFactorの向き未検証へ変わった)。
`LOCAL_DATA_FETCH_GUIDE.md`に、実データ入手後にAdjFactorの向きをJ-Quants自身の`AdjC`と
突き合わせて検証する手順を追記した。

## D0033 — `DataSourceCapabilities`の導入とUniverse/Company Nameまわりの修正

**変更内容**:

1. `lib/data_sources/base.DataSourceCapabilities`を新設し、`daily_prices` /
   `trading_calendar` / `topix` / `listed_master` / `general_indices`の利用可否を
   表現できるようにした。既定値`LIGHT_PLAN_ASSUMED`はユーザー申告のLightプランを
   踏まえた**未検証の推測**であり、契約状況の確認はユーザー自身に委ねる。
   Adapterの`fetch_*`は、この構造体を理由に事前ブロックはしない(実際のAPI呼び出しに
   任せ、利用不可なら本物のエラーがそのまま`DataSourceError`として伝わる設計。
   他Providerへのsilent fallbackは行わない、RESEARCH_RULES.md参照)。
2. Universeを`/listed/info`から`/v2/equities/master`へ接続先変更した
   (`equities_master_payload_to_listing_records()`)。
3. `ListingRecord`に`company_name`フィールドを追加し、`lib.universe`に
   `check_company_name_consistency(expected_names, listings)`を新設した。手入力の
   Ticker→会社名対応をCanonical Dataとして扱わず、Masterと矛盾する場合に警告文字列を
   返す(例外にはしない)。`scripts/jquants_lab_pipeline.py`は実データSource利用時に
   これを呼び出し、警告があれば標準出力に表示する。
4. **誤りの訂正**: `LOCAL_DATA_FETCH_GUIDE.md`等で「3626 = TOKAIホールディングス」と
   誤って記載していた。正しくは3626 = TIS株式会社、TOKAIホールディングス = 3167。
   ユーザーからの指摘を受けて全箇所を修正した。今後はコード上の会社名ラベルも
   手入力ではなく`equities_master`から解決することを推奨する
   (`check_company_name_consistency`参照)。

---

## Phase3A.1 追補(2026-08-16): HolDiv/AdjFactorの公式仕様確定

Phase3A.1完了報告に対し、ユーザーからHolDivの値の意味とAdjFactorの公式計算方法を
確定情報として提示された。D0031〜D0033で「未検証の推測」としていた箇所のうち、
この2点は確定情報へ差し替えた。

## D0034 — HolDiv/AdjFactorを公式仕様(確定)へ差し替え、Price Continuity Adjustmentを
PIT-safeに実装

**HolDiv(確定)**: `lib/data_sources/convert.py`に公式の値と意味を定数として明記した。

```
0 = Non-business day
1 = Business day
2 = Day of TSE Half-Day Trading Sessions
3 = Non-business day (with holiday trading)
```

日本株現物Backtestのデフォルトを`tradable = {1, 2}`(`_TRADING_HOL_DIV_DEFAULT`)、
`non_tradable = {0, 3}`とした(現物Cash Equity Pipelineでは3も非取引日として扱う、
ユーザー確定仕様)。`trading_hol_div_values`引数によるConfigurable設計は維持しつつ、
既定値はもはや「未検証の推測」ではなく確定仕様として扱う。HolDiv 0/1/2/3それぞれの
Test(`test_trading_calendar_payload_to_calendar_uses_official_hol_div_semantics`)を追加した。

**AdjFactor(確定)**: J-Quants V2のAdjFactorはCorporate Actionのex-dateのrecordに
記録され、以下の計算方法が公式仕様であることが確定した。

```
Adjusted Price  = Raw Price  × Π(そのバー日より後にeffectiveなAdjFactor)
Adjusted Volume = Raw Volume ÷ Π(そのバー日より後にeffectiveなAdjFactor)
```

ユーザー提示の例(2024-01-10 C=980,AdjFactor=1.0 / 2024-01-11 C=480,AdjFactor=0.5(ex-date)
/ 2024-01-12 C=500,AdjFactor=1.0 → Adjusted Closeは01-10=490, 01-11=480(ex-date当日は
無調整), 01-12=500)で確認したところ、D0032で実装した`build_provider_derived_adjusted_bars`
の「イベント効力発生日より前のバーにのみ乗算する」ロジックは、既にこの公式仕様と
**一致していた**(「乗算慣習」という一般論からの推測だったが、結果的に正しい向きだった)。
したがって計算式自体の変更は無く、ドキュメント上の「未検証」という表現を確定仕様の説明へ
差し替えた。出来高の除算(`volume / cumulative_factor`)も同様に既存実装のまま確定した。
公式の3ケース(as_of=ex-date前日・ex-date当日close・ex-date翌日)をそれぞれ
`test_build_provider_derived_adjusted_bars_scenario_{before,at,after}_ex_date`として
`13_tests/test_convert_phase3a.py`に追加し、ユーザー提示の数値と完全一致することを確認した。

**PIT-safe gateの挙動変更(重要)**: これまで`build_provider_derived_adjusted_bars`は、
as_of時点でまだ効力発生日のBarが取得可能でないはずのEventが混入していた場合
`LookAheadBiasError`で拒否していた(Case Aの「未公表」ケースを模した設計)。しかし
ユーザーの提示したCase A(as_of=2024-01-10、1/11の未来Eventが存在しても例外にならず、
単に無調整のまま980を返す)を踏まえ、**エラーではなく黙って調整対象から除外する**
挙動へ変更した。理由: Case Bのイベントには「発表済みだがまだ効力未発生」という
Case A的な中間状態が無く、単に「まだ効力発生日のBarが取得可能になっていないだけ」
という通常の時系列進行にすぎない。Backtest Pipelineがある時点までの全Raw/Event Dataを
保持したまま複数のdecision_atで繰り返しこの関数を呼ぶ運用を想定すると、「まだ知り得ない」
Eventが渡された集合に含まれること自体はむしろ通常の状態であり、それをエラー扱いすると
実用上扱いづらい。異常なのは「未来のEventを適用してしまう」ことであり、本関数は
それを構造的に防ぐことで安全性を担保する。

**ExRTとの役割分離**: `AdjFactor != 1`のみをPrice Adjustmentの対象とし、`ExRT`が
設定されているだけの行(`AdjFactor == 1`)は独自の補正係数を推測して適用しない
よう明示的にガードした(数学的には1.0を掛けても無害だが、設計意図を明示するため)。
`ExRT`はCorporate Action / ex-right eventのmetadataとして`CorporateAction`に
保持され続ける(`detect_corporate_action_events_from_equity_bars`は引き続き
`AdjFactor != 1`または`ExRT`ありの行をEventとして検出する)。

**依然として実Backtestへ適用しない理由(BLOCKING TODOの性質が変化)**:
`build_provider_derived_adjusted_bars`自体は上記の通りPIT-safeに実装済みだが、
`scripts/jquants_lab_pipeline.py`はまだこれを`price_history`の構築へ組み込んでいない。
理由は新たに判明した設計上の制約: `BacktestEngine.run()`(`lib/backtest/engine.py`)は
`price_history`を**1回だけ事前計算**し、各`decision_at`ではそこから
`session_date <= decision_date`のスライスを取り出すだけの設計になっている。仮に
`build_provider_derived_adjusted_bars`を単一の固定`as_of`(例えば実行時点や対象期間の
終端)で事前計算すると、Walk-Forwardで複数のdecision_atを横断する場合、**一部の
decision_atにとっては「まだ知り得ないはずの将来のCorporate Actionで調整された価格」を
見てしまう**(=事前計算時のas_ofより前の全decision_atに対して一律に同じ調整後価格を
渡すことになるため)。これは関数自体のバグではなく、「事前計算1回+スライス」という
既存Engineアーキテクチャと「decision_atごとに異なるAs-of Adjusted Seriesが必要」という
Case Bの要件が噛み合わないことによる、より上位の設計課題である。この配線変更
(price_historyをdecision_atごとに再計算する、あるいはEngine内でCorporate Action
イベントを直接扱えるようにする等)は、既存Backtest Engineの構造変更を伴うため、
「必要性がない限り変更しない」というPhase3Aの指示を踏まえ、Phase3A.1では見送り、
Phase3B以降の検討事項とした。したがって`scripts/jquants_lab_pipeline.py`は引き続き
`apply_split_adjustments(bars, [])`(無調整)のままである。

---

## Phase3A.2(2026-08-16): PIT-safe Corporate Action AdjustmentのEngine配線

Phase3A.1をFINALとした上で、D0034で特定した「全期間共通の事前計算済みAdjusted
price_historyを使い回すため、Walk-Forwardの一部decision_atが未来のCorporate Actionで
調整された価格を見てしまいうる」という問題**だけ**を解消することをPhase3A.2として
実施した(新機能追加はせず、この問題の修正に限定)。

## D0035 — `PriceHistorySource` Protocolを導入し、`BacktestEngine`をdecision_atごとの
As-of Adjustmentへ対応させる

**変更内容**: `lib/backtest/price_history.py`を新設し、以下を実装した。

- `PriceHistorySource`(Protocol): `bars_up_to(code, as_of)` /
  `bar_on(code, session_date, as_of=...)`の2メソッドのみを持つ。`BacktestEngine`は
  このInterfaceにしか依存せず、Corporate Action Adjustmentの具体的な実装
  (Provider固有ロジック含む)を一切知らない(ユーザー要求のとおり)。
- `StaticPriceHistory`: 既に確定したBar列をそのまま返す(Corporate Action調整をしない)。
  Phase3A.1以前の`price_history`引数(plain dict)と完全に同じ挙動を再現する
  (fixture・株式分割を扱わないテスト向け)。
- `AsOfAdjustedPriceHistory`: Raw Price History + Corporate Action Eventsから、
  呼び出しのたびに(=decision_atごとに)`build_provider_derived_adjusted_bars`を
  呼び出してPIT-safeなAdjusted Bar列を構築する。銘柄ごとに独立して計算するため、
  Ticker間の影響が構造的に混入しない。

`lib/backtest/engine.py`の`BacktestEngine.run()`は、`price_history`引数の型を
`Mapping[str, Sequence[AdjustedOHLCVBar]]`から`PriceHistorySource`へ変更した。
内部の実装は、以前は`price_history`(dict)を一度だけ`code`でスライスして
`bars_for_code`を作り、それをループ全体で使い回していたが、これを廃止し、
decision_dateごとに`price_history.bars_up_to(code, as_of=session_close_at(decision_date))`
を呼ぶよう変更した。全期間共通の事前計算済みSeriesを保持する変数は存在しない。

**Trade Entry/Exit価格の扱い(スコープ拡張の必要性)**: Feature/Signal計算だけでなく、
Entry/Exitの約定価格取得(旧`bars_by_date.get(execution_date)`)も同じ`price_history`
(廃止された単一の全期間Series)から取っていたため、これも`price_history.bar_on()`
経由に変更する必要があった。Entry/Exitは両方とも`trade_as_of = session_close_at(exit_date)`
という同一のas_ofで取得する(保有期間中にCorporate Actionが発生していても、Entry/Exitを
同じ基準で調整することでReturn計算の連続性を保つ。これはdecisionのPIT制約とは別の関心事:
「未来の情報を意思決定に使う」のではなく、「既に確定した実現ReturnをEntry/Exit間で
正しく測定する」ための処理であり、Look-ahead Biasには当たらない)。これは
「新機能追加」ではなく、旧アーキテクチャで暗黙に存在した「単一の全期間Series」を
削除する以上、Entry/Exit価格の取得元も必然的に何らかのas_of基準を持つ必要があった
ための、D0034問題の修正に不可欠な変更として扱った。

**Future Eventの扱い(仕様変更)**: D0032/D0034時点の`build_provider_derived_adjusted_bars`
は、as_of時点でまだ取得可能でないはずのEventが渡されると`LookAheadBiasError`を
送出していた。しかしユーザー提示のTest A(as_of=2024-01-10、1/11の未来Splitが存在しても
例外にはならず980を返す)を踏まえ、**Raw Dataset自体にdecision_atより未来のCorporate
Action Eventが存在することは正常**という理解に立ち、例外を送出せず黙って調整対象から
除外する挙動へ既に変更済み(Phase3A.1追補、DECISIONS.md参照)。Phase3A.2ではこの挙動を
そのまま利用し、Engine配線側で追加のフィルタリングは行っていない(Dataset自体に未来情報が
存在することと、それをdecisionに使うことを区別する、という設計をEngineレベルでも維持)。

**Provenance**: `lib/schemas/experiment.PriceAdjustmentProvenance`
(`adjustment_method` / `as_of_policy` / `corporate_action_source` /
`raw_snapshot_ids`)を新設し、`Experiment.price_adjustment`(Optional、既定None)に
記録する。`adjustment_method`はバージョン識別子として扱う
(`PIT_AS_OF_ADJFACTOR_V1` = decision_atごとのPIT-safe調整、`NONE` = 無調整)。
既存の`ExperimentRegistry`は`price_adjustment`キーが無い過去のレコードも
問題なく読み込める(Optionalフィールドの既定値、後方互換テストで確認)。

**Pipeline統合**: `scripts/jquants_lab_pipeline.py`に`--price-adjustment {none,pit}`
(既定`pit`)を追加した。`pit`は`AsOfAdjustedPriceHistory`(V2 AdjFactor Eventから
生成したPIT-safe As-of Adjustment)を、`none`は`StaticPriceHistory`(無調整、
Phase3A.1以前と同じ)を使う。Corporate Action Announcementを取引Signalとして使う
機能(Case A)は、`announced_at`付きデータSourceが無いため引き続き未実装のまま
(Price Series連続化=Case Bとは独立)。

**Performance**: 正確性を優先し、`AsOfAdjustedPriceHistory`はdecision_atごとに
その銘柄のRaw bars/Eventsをas_ofで絞り込んで`build_provider_derived_adjusted_bars`を
再計算する(as_of単位のcacheや累積factorの差分更新は行わない)。銘柄ごとの事前index
(コンストラクタで`session_date`昇順にソート済みのリストを保持)により、将来
最適化を追加しやすい構造にはしているが、Phase3A.2では最適化自体を主目的としていない。

**Regression確認**: Corporate Actionが存在しないDatasetでは、`StaticPriceHistory`経由と
`AsOfAdjustedPriceHistory`(空Events)経由とでBacktestMetricsが完全一致し、かつ両者とも
Phase3A.1時点で確認済みの値(`13_tests/test_pit_as_of_adjustment.py`の
`test_G_no_corporate_action_dataset_matches_pre_phase3a2_metrics_exactly`)と一致することを
確認した。既存の`test_backtest_engine.py`等の呼び出し箇所は`price_history`引数を
`StaticPriceHistory(...)`でラップするよう機械的に更新したのみで、テストの意図・
アサーションは変更していない。

---

## Phase3A.2 追補(2026-08-16): 実SmokeTestで判明したProvider Code(5桁)の正規化

ユーザーがローカル環境で実際にJ-Quants API V2への最小Smoke Testに成功し、以下の
事実を確認した: 内部Code(普通株、例: "7203")をrequestすると、Provider側の
responseでは``"Code": "72030"``(5桁)として返る。その他のField(equity_bars/
equities_master)は現在の実装の想定と一致していた。

## D0036 — Provider Code(5桁)とResearch Lab内部Code(4桁)を明確に分離し、安全に
正規化する

**変更内容**: `lib/data_sources/ticker_codes.py`を新設し、
`normalize_provider_code_to_internal(provider_code)`を実装した。

- 5桁の数字文字列で末尾が"0"(普通株、実データで確認済みの唯一のパターン) ->
  先頭4桁を内部Codeとして返す。
- 4桁の数字文字列(Endpointによっては4桁のまま返る可能性への保守的なフォールバック) ->
  そのまま返す。
- 数字のみで構成されているが上記に当てはまらない場合(5桁だが末尾が"0"でない=
  優先株等の可能性、3桁・6桁等)は、実際のProvider Codeの可能性があるあいまいな
  ケースとして`TickerCodeNormalizationError`を送出する(無条件に末尾を削る実装は
  しない、というユーザー指示を反映)。
- 数字以外の文字を含む場合(fixture/testの合成ラベル、"TOPIX_SYNTH"等)は、実際の
  J-Quants Provider Code(数字のみ)ではありえないため、そのまま変更せず返す
  (合成データの識別子は正規化対象ではない)。

`RawOHLCVBar` / `CorporateAction` / `ListingRecord`に`provider_code: str | None`
フィールドを追加し、`code`(内部Code)とは別に、Providerが実際に返した生の値を
保持できるようにした(provider_codeとinternal_codeを混同しないというユーザー要求)。
`lib/data_sources/convert.py`の`equity_bars_payload_to_raw_bars` /
`detect_corporate_action_events_from_equity_bars` /
`equities_master_payload_to_listing_records`は、`row["Code"]`を正規化した上で
`code`(内部)と`provider_code`(生値)の両方をセットする。

**Raw Snapshotは変更しない**: `RawSnapshotStore`が保存する`RawFetchResult.payload`
(Raw Snapshot)は、Provider APIが返したJSONそのものであり、この正規化とは無関係
(Raw Snapshotには常にProviderの生の値"72030"がそのまま残る)。正規化は
`convert.py`がRaw PayloadをInternal Schema(`RawOHLCVBar`等)へ変換する段階でのみ
適用される。

**Master解析はエラーではなく警告でスキップ(非対称な扱い)**: `equity_bars_payload_to_raw_bars`
等(ユーザーが明示的に指定した少数の銘柄コードのみを対象とする)は、正規化に失敗すると
例外を送出しPipeline全体を止める(想定外のデータ不整合の可能性が高いため)。一方、
`equities_master_payload_to_listing_records`は全上場銘柄(ETF・優先株等、確認済み
パターンに一致しないProvider Codeを含みうる)を対象とするため、正規化に失敗した行は
例外にせず`logging.warning`でスキップする(Phase3Aは普通株のみを対象とするため、
無関係な銘柄種別でMaster全体の解析が止まることを避ける。黙って無視するのではなく、
ログで追跡可能にする)。

**テスト**: `13_tests/test_ticker_codes.py`(正規化関数の単体テスト、確認済みパターン・
あいまいなケースでの例外送出・合成ラベルのpass-through・Provider Code集合からの
index構築とcollision検知)、`13_tests/test_convert_phase3a.py`の
`test_provider_code_72030_and_internal_code_7203_join_correctly_in_backtest_and_universe`
(Provider Code "72030"由来のequity_bars/equities_masterが、内部Code "7203"を使う
`BacktestRunConfig.universe_codes`・`UniverseProvider`と正しくjoinし、価格系列を
実際に見つけられることを直接確認)を追加した。`--source local`の手動scratch検証
(equity_bars/equities_masterの"Code"を全て5桁化したデータ)でも、4桁のみのデータと
完全に同じBacktestMetricsが得られることを確認済み(正規化が透過的であることの
実行時確認)。

**この確認をもって、実データ取得(`LOCAL_DATA_FETCH_GUIDE.md`の手順)を継続してよい
状態とする。** equity_bars/equities_masterのField名自体は既存の想定(V2 Canonical
Specification)と一致していたため、Provider Code正規化以外の追加修正は不要。

---

## Phase3B前の修正(2026-08-16): 実データ初回E2E Backtestで判明したEnd-of-Sample Censoring

ユーザーがローカル環境で実J-Quantsデータによる初回End-to-End Backtest
(RUN_20260816T162453577518、2022-01-04〜2024-12-30、4銘柄)に成功した。Pipeline自体は
最後まで完走したが、`OUTSIDE_DATA_RANGE`(execution_failed_countに算入)の内訳を
確認したところ、その多くがBacktest期間終了間際のSignalによるものと判明した。

## D0037 — Right Censoring(`CENSORED_END_OF_SAMPLE`)をExecution Failureから分離する

**問題**: `BacktestEngine.run()`は、holding_period_days(60営業日)分のExit Dateが
Trading Calendarの範囲(`TradingCalendarResolutionError`)を解決できない場合、
`ExecutionOutcome.OUTSIDE_DATA_RANGE`として記録し、これを`EXECUTION_FAILURE_OUTCOMES`
(真の執行失敗)に分類していた。しかし、`decision_date`は常に`trading_calendar.
trading_dates`由来(`TradingCalendar.__post_init__`で`range_start`〜`range_end`内で
あることが保証済み)であり、`next_trading_session` / `nth_next_trading_session`が
この経路で`TradingCalendarResolutionError`を送出しうるのは「dより後の取引日が
`range_end`(実運用では`BacktestRunConfig.end_session`と一致)を超えて存在しない」
場合に限られる(`lib/market_calendar.py`の実装より、他の失敗モードは無い)。
すなわちこれは「Backtest期間終了によりExit Dateをまだ観測できていないだけ」という
Right Censoringであり、「執行を試みたが失敗した」という真のExecution Failureとは
性質が異なる。両者を同じ`execution_failed_count`へ合算すると、期間終端付近に
Signalが集中する戦略・短い評価期間ほど「執行失敗が多い」という誤った印象を生む。

**変更内容**:

1. `ExecutionOutcome.CENSORED_END_OF_SAMPLE`を新設し、`run()`内の該当箇所
   (`next_trading_session`/`nth_next_trading_session`の`TradingCalendarResolutionError`)
   はこれを記録するよう変更した。`OUTSIDE_DATA_RANGE`はEnum・
   `EXECUTION_FAILURE_OUTCOMES`には引き続き残す(過去に記録されたExperimentとの
   互換性のため)が、`run()`はもうこれを送出しない。
2. `CENSORING_OUTCOMES`(`CENSORED_END_OF_SAMPLE`のみ)を新設し、
   `POLICY_SKIP_OUTCOMES` / `EXECUTION_FAILURE_OUTCOMES`と並ぶ第3の分類とした。
3. `BacktestMetrics`に`censored_count`(Right Censoringされた件数)・
   `eligible_order_attempt_count`(`order_attempt_count - censored_count`、
   評価可能期間内で実際に成否を判定できた注文数)を新設した。
   `execution_failed_count`の分母を`order_attempt_count`から
   `eligible_order_attempt_count`へ変更し(= `eligible_order_attempt_count -
   executed_count`)、Censoringを含まない真の失敗率になるよう修正した。
   `order_execution_rate`も同様に分母を`eligible_order_attempt_count`へ変更した
   (`executed_count / eligible_order_attempt_count`、「評価可能だった注文の約定率」)。
   `order_attempt_count`・`signal_to_trade_rate`の定義・分母は変更していない
   (Policy Skip・Censoringどちらも「シグナルからトレードへの転換」という文脈では
   実際に起きた事実であり、隠す必要が無いため)。
4. `signal_count == policy_skipped_count + censored_count + execution_failed_count +
   executed_count`という会計恒等式が常に成り立つことを
   `13_tests/test_backtest_engine.py`の
   `test_signal_accounting_identity_across_policy_skip_censoring_and_execution_failure`
   で直接確認した(Policy Skip・Censoring・真のExecution Failureが同時に発生する
   1本のシナリオで4分類すべてが独立に集計されることを確認)。

**BacktestMetricsスキーマ変更に伴うアーカイブ**: 既存の`06_backtests/
experiment_registry.jsonl` / `provenance.jsonl`(合成データによるデモ)は新フィールド
無しでは読み込めなくなるため、`99_archive/06_backtests/*_pre_d0037_censoring_split.jsonl`
へ退避し、最新コードで再実行したデモへ差し替えた(D0017/D0022と同じ手順)。

**Before/After確認(合成fixtureデータ)**: 同じfixtureデータで修正前後を比較したところ、
`trade_count`(2件)・各tradeの`net_pretax_return`(`average_return=
0.03208160645601388`等)は完全に一致し、`execution_failed_count`のみ88→0、
新設の`censored_count`が0→88、`order_execution_rate`が0.0222→1.0(評価可能だった
2件は両方EXECUTEDだったため)へ変化した。これはSignal/Executionの判定ロジック自体を
一切変更せず、ExecutionOutcomeの分類方法のみを修正したことの直接的な証拠である。

**実データSnapshotでの確認について(既知の制約)**: このセッションはネットワーク
ポリシーにより実J-QuantsデータのRaw Snapshotへアクセスできない(ユーザーの
RUN_20260816T162453577518はユーザー自身のローカル環境で生成されたもので、
`01_data/raw/jquants/`はgitignore対象のためこのセッションには存在しない)。
そのため実データでのBefore/After比較は、ユーザー自身が同一コマンド(同一期間・
同一銘柄)をこの修正後のコードで再実行し、`trade_count`・トレードごとのReturnが
修正前と一致すること、`execution_outcomes`の内訳(特に`CENSORED_END_OF_SAMPLE`の
出現と`execution_failed_count`の減少)を確認する必要がある(完了報告参照)。

**Multiple Testingへの影響**: 2022-01-04〜2024-12-30・当該4銘柄・当該固定Strategyの
組み合わせは、このInfrastructure Validation Runで結果を観測済みのため、今後
Hidden Test(未見のOut-of-Sample期間)として扱わないことをRESEARCH_RULES.mdへ記録した
(「Infrastructure Validation Runと戦略性能Testを区別する」節)。

---

## Phase3C(2026-08-16): 固定4銘柄からPoint-in-Time Universeへ

Phase3Bの実J-Quants E2E Validation(RUN_20260816T164133244945)完了後、ユーザーより
Phase3Cの開始指示があった。目的は「固定4銘柄ではなく、日本株のPoint-in-Time Universeを
安全に扱えるようにすること」であり、特に`survivorship_bias_unresolved=True`
(D0028で自動検出のみ導入済みだったが、未解消のまま放置されていた)の解決を最優先とする。

## D0038 — Point-in-Time Universe: `PARTIAL` Resolutionの明示、普通株Universeの
明示的な定義、`BacktestEngine`のdecision_atごとのUniverse再解決

**問題**: それまでの`ListingBasedUniverseProvider`は、`survivorship_bias_unresolved`を
自動検出(全listingに`delisting_date`が無ければTrue)するところまでは実装済み
(D0028)だったが、(1)この場合でも`UniverseSnapshot.resolution`は`RESOLVED`のままで、
「Survivorship Biasが残ったままRESOLVEDと自称する」矛盾した状態だった。また
(2)ETF・REIT・優先株等(普通株以外)を明示的に除外する経路が無く、(3)
`BacktestEngine.run()`は`universe_codes`(呼び出し側が指定したCode一覧)をそのまま
使うのみで、`UniverseProvider`をdecision_atごとに問い合わせて銘柄の適格性を
判定する経路が無かった(=Universeの観点ではPIT-safeではなかった)。

**変更内容**:

1. `UniverseResolution`に`PARTIAL`(RESOLVEDとUNRESOLVEDの間)を新設した。
   `ListingBasedUniverseProvider.as_of()`は、`survivorship_bias_unresolved=True`の
   場合(自動検出 or 明示指定)は`resolution=PARTIAL`を返すよう修正した
   (以前は`RESOLVED`のままだった)。`note`には「delisting_dateが無いlistingのみのため、
   廃止銘柄を捕捉できていない可能性がある(Survivorship Bias未解消、Universe下限のみ判明)」
   という理由を明記する。`survivorship_bias_unresolved=False`の場合のみ`RESOLVED`。
2. `build_common_stock_universe()`を新設し、呼び出し側が明示的に渡す
   `common_stock_market_codes`(MarketCodeの許可リスト)に基づいて普通株Universeを
   構築するようにした。**このモジュール自身は実際のJ-Quants MarketCodeの値・意味を
   検証しておらず、値を推測で決め打ちしない**(許可リストが空、またはMarketCodeが
   不明な場合は安全側=除外側に倒す)。除外した銘柄とMarketCode別件数は
   `CommonStockFilterResult.excluded_market_codes`で必ず追跡できるようにした
   (監査可能性)。
3. `BacktestEngine.run()`に`universe_provider: UniverseProvider | None = None`を
   追加した(省略時は従来通り`config.universe_codes`をそのまま使い、完全後方互換)。
   指定した場合、`decision_date`ごとに`universe_provider.as_of(decision_at)`を
   再解決し(D0035の`PriceHistorySource.as_of()`と同じ設計思想:全期間分を
   一度だけ事前計算して使い回すと、Universeの観点でLook-ahead biasを生みうるため)、
   その時点のUniverseに含まれないCodeについては`signal_fn`自体を呼ばない
   (Signal評価対象から除外する)。decision_dateごとの重複解決を避けるため、
   実行1回あたりの`dict[date, frozenset[str]]`キャッシュのみ保持する
   (Provider自体は毎回問い合わせる)。
4. `scripts/jquants_lab_pipeline.py`は、実データSource(`jquants`/`local`)利用時に
   `/v2/equities/master`から構築した`universe_provider`を、**表示用のSnapshot取得**
   だけでなく`engine.run(..., universe_provider=universe_provider)`として実際の
   Backtest実行にも渡すよう修正した(修正前はSnapshotを取得・表示するのみで、
   Backtestの銘柄適格性判定には使われていなかった)。

**普通株Universeフィルタ(`build_common_stock_universe`)をPipelineへまだ接続していない
理由**: 実際のJ-Quants MarketCodeの値・意味(どの値がPrime/Standard/Growth=普通株で、
どの値がETF/REIT/優先株か)はこのセッションでは未検証。要件上「値を推測で決め打ちしない」
ため、確認できていない値を許可リストとして決め打ちしてPipelineへ組み込むことはしない。
関数自体はTest済み・利用可能な状態にしてあるので、ユーザーがローカル環境で実際の
MarketCode値を確認した後、その確定値を許可リストとして渡す形でPipelineへ接続する
(D0038、下記「未確認事項」参照)。

**未確認事項(推測で埋めていない項目、DECISIONS.mdとして明示)**:

- `/v2/equities/master`の`date`パラメータ(`fetch_equities_master(as_of=...)`)が、
  指定日時点の真のPoint-in-Time上場状況(当時存在したが現在は廃止済みの銘柄を含む)を
  返すのか、単に「現在の上場状況」を返すだけなのかは未検証。後者であれば、
  Masterから`delisting_date`を持つ`ListingRecord`は原理的に得られず、
  Survivorship Biasを構造的に解消できない(`survivorship_bias_unresolved=True`の
  ままになる)。
- Masterが上場廃止銘柄を(過去日付を指定した場合であっても)そもそも一切含まないか
  どうかも未検証。
- MarketCodeの実際の値・意味(どれが普通株の市場区分か)は未検証。
- 2022年4月のTSE市場再編前後で、単一時点のMasterスナップショットから過去の市場区分を
  復元することは構造的にできない(`lib/universe.py`のモジュールDocstring参照)。

**ローカル環境での確認方法(ユーザー向け、実行推奨)**: 上記の未確認事項のうち
「Masterの`date`パラメータが真のPIT Snapshotを返すか」は、少量のリクエストで
安全に確認できる。過去に上場廃止されたことが分かっている銘柄コードを1つ選び、

```
python scripts/fetch_jquants_local_snapshot.py \
    --master-pit-check <廃止前の日付> <廃止後の日付> --master-pit-check-code <銘柄コード>
```

のように前後の日付でMasterを取得し、廃止前の`as_of`ではその銘柄が含まれ、廃止後の
`as_of`では含まれなくなるかを確認する。含まれる場合は真のPIT Snapshotとみなせるが、
含まれない場合(=常に「現在の状態」しか返らない)は、Light Planでは
`/v2/equities/master`単体ではSurvivorship Biasを解消できないと結論できる
(その場合、`resolution=PARTIAL`が恒常的な状態になる。これは仕様上の制約であり、
コード側の不具合ではない)。**この確認は実際にD0039で実行され、確認済みとなった
(下記D0039参照)。**

**このPhaseでやらないこと**: 全市場規模でのUniverse実データ取得・普通株許可リストの
決め打ち・戦略パラメータの探索や最適化は行っていない(要件どおり、Infrastructure
Validationとしての固定20営業日Momentum/60営業日Hold Strategyのみを対象とする)。

---

## D0039 — Phase3Cを閉じる: Master date paramのPIT実データ確認、Universe Resolutionの
RESOLVED経路追加、Instrument Type/Market Scopeの分離、Rate Limit訂正、Bulk取得方針の明文化

**背景**: ユーザーがローカル環境で`scripts/fetch_jquants_local_snapshot.py
--master-pit-check 2023-12-19 2023-12-21 --master-pit-check-code 6502`を実行し、
6502(東芝)がas_of=2023-12-19では含まれ(4330件中)、as_of=2023-12-21では含まれない
(4331件中)ことを実データで確認した。これは`/v2/equities/master`の`date`パラメータが
真のPoint-in-Time上場状況を返すことの直接的な証拠であり、D0038で「未検証」としていた
最重要の未確認事項が解消された。あわせて、J-Quants Light Planの実際のレート制限が
60リクエスト/分であること(D0038時点で暫定採用していた「5リクエスト/分」相当の
安全マージンは古い前提だった)もユーザーから確認情報として提供された。

**変更内容**:

1. **Master date paramのPIT性: 未確認 → 確認済み**。`lib/universe.py`の
   モジュールDocstringおよびD0038の該当記述を「未検証」から「6502実データ確認済み」へ
   更新した。ただし、この確認結果が保証するのは「decision_atごとにその日付を指定して
   Masterへ再問い合わせした場合」のみである点に注意が必要(下記2参照)。単一の
   Masterスナップショット(例: 期間末日1回分)を全decision_atへ使い回す
   `ListingBasedUniverseProvider`の既存の使い方(`scripts/jquants_lab_pipeline.py`の
   現状の配線)は、この確認結果だけでは`RESOLVED`にならない
   (Survivorship Biasは依然として残る、`PARTIAL`のまま)。
2. **Universe ResolutionにRESOLVED経路を追加**: 新設した`PitCoverage`
   (`confirmed_from`/`confirmed_until`、実データで確認できた範囲を呼び出し側が明示的に
   渡す)と`PitMasterUniverseProvider`(`lib/universe.py`)により、decision_atごとに
   `master_fetcher`(通常は`adapter.fetch_equities_master(as_of=decision_date)`)を
   実際に再呼び出しし、その結果を`_is_tradable_on`でフィルタして`RESOLVED`を返す経路を
   新設した(D0035の`PriceHistorySource.as_of()`と同じ「全期間を一度だけ事前計算して
   使い回さない」設計)。`confirmed_coverage`の範囲外のas_ofについては、Master自体への
   問い合わせを行わず(不要なAPI呼び出しを避ける)、安全側の`PARTIAL`を返す。
   `master_fetcher`が空集合を返した場合は`DATA_UNAVAILABLE`とする。
   **`scripts/jquants_lab_pipeline.py`はまだ`PitMasterUniverseProvider`へ切り替えていない**
   (下記5「このDecisionでやらないこと」参照。切り替えるとdecision_atの数だけMasterへ
   実際に問い合わせることになり、これは全市場規模データ取得と同種の「大規模な実データ
   取得」に該当するため、Phase3Cの停止点を越える)。
3. **Instrument TypeとMarket Scopeの分離**: `ListingRecord`に`instrument_type`
   (商品区分、普通株/ETF/REIT/優先株等)を新設し、`market`(投資対象の市場Scope、
   Prime/Standard/Growth等)とは別概念として扱うようにした。`build_common_stock_universe`
   のフィルタ基準を`listing.market`から`listing.instrument_type`へ変更し
   (`CommonStockFilterResult.excluded_market_codes`は`excluded_instrument_types`へ改名)、
   `common_stock_market_codes`パラメータは`common_stock_instrument_types`へ改名した。
   `equities_master_payload_to_listing_records`(`lib/data_sources/convert.py`)は
   `row.get("ProdCat") or row.get("ProdCatName")`から`instrument_type`を取る
   (Field名はユーザー提供情報に基づく想定であり、正確な値の列挙・Field名の最終確認は
   ローカル環境での実データ確認が必要。MarketCodeの実際の値と同様、依然として
   `build_common_stock_universe`の実データPipelineへの接続は保留する。下記5参照)。
4. **Rate Limitの訂正**: `lib/data_sources/jquants.py`の`_RATE_LIMIT_INTERVAL_SEC`を
   「5リクエスト/分」想定の`12.5`秒から、確認済みの「60リクエスト/分」に基づく`1.05`秒へ
   変更した。**この変更は`Japanese_Equity_Lab/lib/data_sources/jquants.py`
   (Research Lab独自のV2 Client)にのみ適用する。ルート`CLAUDE.md`が言及する
   「J-Quants: 5リクエスト/分」は既存Screening Toolの`core/providers/jquants.py`
   (別実装、V1)についての記述であり、これは別システムのため変更していない**
   (既存Screening Toolを変更しない方針を厳守)。
5. **全市場日次株価取得の方針(ポリシーとして明文化、実装はしない)**: 数千銘柄規模の
   `equity_bars`取得は、銘柄ごとに`/v2/equities/bars/daily`を逐次呼び出す方式を
   Defaultにせず、Light Plan以上で利用可能なFile Download/Bulk取得エンドポイントを
   優先する方針をRESEARCH_RULES.mdへ記録した。**ただし、実際のBulk/File Download
   エンドポイントの仕様(URL・パラメータ・レスポンス形式)はこのセッションでは
   未確認であり、推測でのクライアント実装は行っていない**(値を推測で決め打ちしない
   方針)。Bulk取得したデータであっても、Raw Snapshotの不変性・hash・provenanceという
   既存原則(`lib.snapshot.RawSnapshotStore`)は変更せずそのまま適用し、PIT Universeは
   引き続きdecision_atごとに解決してBacktestへ投入する構造(`UniverseProvider.as_of()`)
   を維持する方針を明記した。実際のBulk Endpoint接続はPhase3Dの設計時に扱う。

**このDecisionでやらないこと(Phase3Cの停止点を維持)**:

- `scripts/jquants_lab_pipeline.py`を`PitMasterUniverseProvider`へ切り替えることは
  していない(decision_atの数だけMasterへ実際に再問い合わせすることになり、これは
  「大規模な実データ取得」の一種であるため、Phase3Cの停止点を越える)。
- `build_common_stock_universe`(instrument_type基準)を実データPipelineへ接続することは
  していない(実際のinstrument_type値がこのセッションでは未確認のため)。
- 全市場規模のBulk/File Download Endpointの実装はしていない(仕様未確認、Phase3Dで扱う)。
- 戦略パラメータの探索・最適化は行っていない。既存Screening Tool(`core/` `app.py`
  `tests/`)は無変更。

**回帰確認**: `pytest`(Lab 180件、既存Screening Tool 37件)・`ruff check`・
`ruff format --check`・`mypy`(52ファイル)いずれもclean。`git diff --stat`で
`core/` `app.py` `tests/`への変更が無いことを確認済み。

---

## Phase3D(2026-08-16): Multi-Source Data Foundation

Phase3C完了後、ユーザーより「J-Quantsだけに依存しない、日本株投資研究所の情報基盤を
作ること」を目的にPhase3Dの開始指示があった。最優先は実データの大量収集ではなく、
Data Lake → Source Catalog → Normalization → Point-in-Time/Provenance →
Relevant Retrieval → Evidence Packet → 将来のAgent/Hypothesis/Backtestという
共通基盤を作り、将来Sourceが増えても研究所本体を作り直さずに済む構造にすること。

## D0040 — Multi-Source Data Foundationの共通Schema/Architectureを新設する
(J-Quants以外のSourceへは接続しない)

**背景**: これまでの実装はJ-Quants(株価・Master)専用だった。将来EDINET/TDnet/
Company IR/日本マクロ統計/Global Market Data/News/Consensus/Idea Source等を
追加接続する際、Source固有の実装が研究所本体(BacktestEngine/Universe等)へ
直接染み出すと、Source追加のたびに本体を作り直すことになる。また、情報源の
性質(FACT/CLAIM/OPINION等)を区別せず「Evidence」として一律に扱うと、
Confirmation Bias(仮説を支持する情報だけを集めてしまう)を構造的に防げない。

**変更内容(新設モジュール、`Japanese_Equity_Lab/lib/`配下)**:

1. **`lib/sources/catalog.py`**: `DataCapability`(MARKET_PRICE/FUNDAMENTAL/
   DISCLOSURE/POSITIONING/EXPECTATIONS/MACRO/GLOBAL_MARKET/NEWS/IDEA)、
   `SourceAuthorityClass`(PRIMARY_OFFICIAL/COMPANY_PRIMARY/VERIFIED_SECONDARY/
   SECONDARY/SOCIAL/USER_SUPPLIED)、`SourceMetadata`(source_id/source_type/
   provider_name/source_authority_class/primary_or_secondary/retrieved_at/
   published_at/available_at/effective_at/source_url/license_or_usage_note/
   content_hash/provenance_id)、`DatasetDescriptor`(Coverage・更新頻度・PIT可否・
   `ImplementationStatus`等)、`SourceCatalog.find()`(capability/code/country/
   sectorで検索)。**`SourceAuthorityClass`が高いからといって内容の解釈まで
   正しいとは限らない**ことをDocstringで明示する(「会社が発表した数字」と
   「経営陣の将来見通し」は別、後述Evidence Type参照)。
2. **`lib/sources/providers.py`**: Capability-based Design。1つの巨大Interfaceへ
   詰め込まず、`MarketDataProvider`/`FundamentalDataProvider`/`DisclosureProvider`
   (EDINET/TDnet/Company IRを1つのProtocolでまとめる、文書という共通の形のため)/
   `MacroDataProvider`/`GlobalMarketDataProvider`/`NewsProvider`/
   `ConsensusProvider`/`IdeaSourceProvider`の8Protocolへ分割し、各Providerは
   `ProviderCapabilities`で自己申告する。**既存`lib.data_sources.jquants.
   JQuantsAdapter`は一切変更していない**が、`MarketDataProvider`と同じ
   メソッド名・シグネチャで設計したため、`isinstance(adapter, MarketDataProvider)`
   が構造的に成立する(`13_tests/test_source_providers.py`で確認)。
3. **`lib/sources/entity_registry.py`**: Canonical Entity Registry。J-Quants Code・
   EDINET Code・法人番号・社名/旧社名を直接joinせず、`issuer_id`を介して対応付ける。
   `EntityIdentifierMapping`(issuer_id/security_id/provider_identifiers/aliases/
   canonical_name/valid_from/valid_until/mapping_provenance/mapping_confidence)、
   `EntityRegistry.resolve(provider_name, provider_identifier, as_of)`はPIT対応
   (社名変更・コード変更等で有効期間が異なる複数Mappingを登録でき、有効期間外は
   `None`、重複一致は`ValueError`とし、黙ってどちらかを選ばない)。
4. **`lib/evidence/model.py`**: `EvidenceType`(FACT/CLAIM/INTERPRETATION/
   OPINION/IDEA。`Hypothesis`は別schemaのためEvidence Typeに含めない)、
   `DataLayer`(RAW/NORMALIZED/DERIVED)、`EvidenceRelation`(SUPPORTS/
   CONTRADICTS/ALTERNATIVE_EXPLANATION/NEUTRAL/UNKNOWN、Hypothesisが存在する
   場合のみ付与するDerived Relationであり、`EvidenceRecord`自体には保持しない)、
   `AvailabilityBasis`(EXACT/OBSERVED/INFERRED/UNKNOWN。UNKNOWNの場合、
   `available_at`をpublished_at等から推測補完しない)、`SourceVersion`/
   `RevisionHistory`(source_record_id/source_version_id/supersedes_version_id/
   is_correction/event_at/published_at/first_seen_at/available_at/retrieved_at/
   source_version_at。`RevisionHistory.as_of(decision_at)`は将来のRevisionを
   過去Decisionへ流用しない。既定で`availability_basis=UNKNOWN`のVersionを
   除外する安全側デフォルト、`include_unknown_availability=True`で明示的opt-in)、
   `AiDerivedProvenance`(model_provider/model_name/model_version/prompt_version/
   prompt_hash/input_evidence_ids/retrieval_plan_hash/generated_at。
   `EvidenceRecord.ai_derived_provenance`が設定されている場合、`layer`は
   `DERIVED`である必要があると`__post_init__`で強制し、AI生成DataがRaw/
   Normalizedを名乗ることを禁止する)、`EvidenceRecord.is_usable_at()`
   (`source.available_at`基準のPITフィルタ、`retrieved_at`の新しさに影響されない)。
5. **`lib/evidence/news.py`**: `NewsScope`(JAPAN/GLOBAL)、共通`NewsEvent`
   Schema(published_at/scope/country/event_type/entities/affected_sectors/
   affected_codes/source/headline/summary/confidence/provenance)。Dedup
   Semanticsとして`EXACT_DUPLICATE`/`SYNDICATED_COPY`/`SAME_EVENT_CLUSTER`/
   `DISTINCT`を区別する簡易ヒューリスティック(`classify_news_relation`)を実装し、
   `cluster_news()`は`EXACT_DUPLICATE`であっても記事情報そのものを削除せず
   クラスタとして全メンバーを保持する(Contradictory reportingを保持する)。
   Global Event → Economic Transmission → Japanese Sector → Japanese Company
   という伝播関係の推論(例: 「US Data Center Capex増 → 電力需要増 → 変圧器需要増
   → 銅需要増 → 日本の電気機器メーカー」)はPhase3Dでは実装しない
   (`NewsEvent.affected_sectors`/`affected_codes`は将来Agent/人手が設定する
   プレースホルダとしてのみ持つ)。
6. **`lib/evidence/retrieval.py`**: `ResearchQuestion`/`RetrievalDecision`/
   `RetrievalPlan`/`plan_retrieval()`/`retrieve_evidence()`。「Dataが多いほど
   全部AIに渡す」設計を禁止し、`plan_retrieval()`は`DataCapability`全種について
   含める/除外する理由を必ず記録する(空文字列の理由を許容しない、監査可能性)。
   LLMによるRetrieval Selection(「関連しそうなCapabilityをAIが選ぶ」)は
   Phase3Dでは実装しない(呼び出し側が明示的に指定した`requested_capabilities`
   に基づいて機械的に判定するのみ)。
7. **`lib/evidence/packet.py`**: `EvidencePacket`(research_question/as_of/
   included_evidence_ids/excluded_candidate_sources/retrieval_reason/
   missing_expected_sources/positive_evidence/negative_evidence/
   alternative_explanation_evidence/contradictory_evidence/unknowns/
   provenance_id)。**Conclusion/Verdict/Supportedに相当するFieldを意図的に
   持たない**(Evidence不足を自動でPositive/Negativeへ昇格させる経路が
   Schema上そもそも存在しないことを`13_tests/test_evidence_packet.py::
   test_evidence_packet_has_no_overall_verdict_field`で直接確認する)。
   `build_evidence_packet()`は呼び出し側から明示的に与えられた
   `relations: Mapping[evidence_id, EvidenceRelation]`をそのままカテゴリへ
   振り分けるだけで、件数による判定・上書きを一切行わない(情報件数の多数決禁止、
   下記Anti-Confirmation Test参照)。`conflicting_evidence_ids`を指定した
   Evidenceは`relations`での分類に関わらず`contradictory_evidence`へ入り、
   Conflicting Sourcesの自動統合(どちらか一方を機械的に選ぶこと)を避ける。
8. **`lib/evidence/decision_log.py`**: `DecisionEvidenceLog`(log_id/decision_at/
   evidence_packet_id/used_evidence_ids/not_used_or_unavailable_evidence_ids/
   main_drivers/contradictions/unknowns/predicted_outcome/actual_outcome/
   provenance_id)。**BUY/SELL Agentは一切実装しない**。
   `predicted_outcome`/`actual_outcome`は将来の検証用に空のまま保存できる
   Fieldとして用意するのみ。
9. **`lib.schemas.experiment.Experiment.used_data_capabilities`**
   (`tuple[str, ...]`、既定`()`、後方互換)を新設し、将来のAblation比較
   (例: Fundamental+Momentum vs +News vs +Macro)のため、どの`DataCapability`を
   使用したExperimentかを追跡可能にした。Ablation Engine自体はPhase3Dでは
   実装しない。既存`06_backtests/experiment_registry.jsonl`の過去Experimentは
   `used_data_capabilities=()`(「未記録」、「何も使っていない」という意味では
   ない)としてそのまま読み込める(`_experiment_from_dict`で`tuple(d.get(...)
   or ())`のように安全にdefaultへfallbackする、D0037/D0038と同じ後方互換手法)。
10. **Provenance/Lineageは新機構を作らず既存`lib.registry.provenance.
    ProvenanceStore`を再利用する**。Raw Snapshot → Normalized Evidence →
    Derived Evidence → EvidencePacket → Decision Evidence Logという新しい
    Node種別の連鎖も、既存の`trace_to_origin()`でそのまま遡れることを
    `13_tests/test_evidence_lineage.py`で確認した。

**Current Official Facts Cleanup**: J-Quants V2 `/v2/equities/master`の
Field名について、公式仕様上、市場Scopeは`Mkt`/`MktNm`、商品区分は`ProdCat`で
あることをユーザーが確認した。D0038/D0039で「ProdCat相当・Field名未確定」と
していた記述を訂正し、`lib/data_sources/convert.py`の
`equities_master_payload_to_listing_records()`を`MarketCode`/`MarketCodeName`
から`Mkt`/`MktNm`へ、`ProdCat`(単独、`ProdCatName`という架空のFallbackを削除)へ
変更した。既存Fixture(`13_tests/fixtures/equities_master_v2.json`)・テスト
(`13_tests/test_convert_phase3a.py`)の`"MarketCode"`キーも`"Mkt"`へ機械的に
置換した(値そのものは変更していない)。**ただし各Fieldが取りうる値の列挙
(どの値がPrime/Standard/Growthか、どの値が普通株か)は依然として未検証であり、
値そのものを推測で決め打ちしない**(`build_common_stock_universe`の許可リストは
引き続き呼び出し側が確認した値を渡す設計を維持、実データPipelineへの接続も
引き続き保留する)。

**Anti-Confirmation Test(`13_tests/test_evidence_packet.py`)**: 以下を直接確認した。

- Positive Evidenceしか無いFixtureでも、`missing_expected_sources`で
  「反証探索を行っていないこと」自体を明示的に表現できる(隠さない)。
- Social Opinion(SOCIAL Authority)が10件`SUPPORTS`でも、Primary Official
  Fact(PRIMARY_OFFICIAL Authority)1件の`CONTRADICTS`は消えない・上書きされない
  (件数による上書きロジックがこのモジュールのどこにも存在しないことの直接証拠)。
- `EvidencePacket`に`verdict`/`conclusion`/`supported`等に相当するFieldが
  一切存在しないことを`dataclasses.fields()`で構造的に確認した。
- Conflicting Sources(2件のFACTが矛盾する数値を報告)は、どちらか一方へ
  自動的に統合されず、両方が`contradictory_evidence`へ保持される。
- Evidence皆無(`evidence_pool=[]`)の場合でも、`positive_evidence`等へ
  自動的に何かが昇格することはない(Fieldがそもそも存在しないことと合わせて、
  構造的に不可能であることを確認)。

**Phase3Dで実装していないもの(スコープ境界、Phase5/Phase6へ送る)**: LLMによる
Retrieval Selection、Positive/Negative自動分類、News Relevance AI、
Hypothesis生成、Skeptic Agent、Ablation Engine、BUY/SELL判断、実際のBOJ/e-Stat等
Skeleton Adapter(公式仕様をこのセッションでは確認できないため、推測実装をしない
方針上、意図的に見送った)、実際のBulk/File Download Endpoint接続(仕様未確認)、
外部API Key取得・有料契約・大量Download・Web Scraping・News Crawling・TDnet
Add-on契約・Consensus契約は一切行っていない。

**回帰確認**: `pytest`(Lab 233件 = 従来180件+新規53件、既存Screening Tool
37件)・`ruff check`・`ruff format --check`・`mypy`(62ファイル)いずれもclean。
`git diff --stat`で`core/` `app.py` `tests/`への変更が無いことを確認済み。
戦略パラメータの探索・最適化は行っていない。

---

## D0041 — Phase4開始前のDocumentation/Planning Cleanup(Phase3Dは引き続きCOMPLETE)

**Phase3Dのstatusは変更しない。** 本Decisionは、Phase4着手前にユーザーから指摘された
2点の設計上の誤解・誤情報を、実装ではなくドキュメント上で正すためのCleanupである
(Phase3Dの再オープンではない)。

**変更内容**:

1. **`SourceAuthorityClass`は信頼度の単純な順位・点数ではなく、Sourceの性質を表す
   カテゴリであることを明文化した。** `PRIMARY_OFFICIAL=100点、SOCIAL=10点`の
   ような単純なスコアリングや、Authority Classに基づく多数決・重み付け投票に
   将来使ってはならないことを、`lib/sources/catalog.py`の`SourceAuthorityClass`
   Docstring、`EVIDENCE_MODEL.md`、`RESEARCH_RULES.md`(「0.5 情報収集の上位
   原則」)、`README.md`へ明記した。企業IR(`COMPANY_PRIMARY`)の例
   (「営業利益予想100億円」という発表事実=FACTは強いSourceだが、「今後も需要は
   堅調」という経営陣の見通し=CLAIMの真偽までは自動的に高信頼としない)を
   全箇所で共通の説明として使う。**Source Authority(出所の位置づけ)と
   Evidence Content(内容そのものの信頼性)は分離して扱う**ことを明示した。
   既存Schema(`SourceAuthorityClass`のEnum値自体)は変更していない
   (Docstring/ドキュメントの追記のみ)。
2. **Phase4の最初の実データ接続順を訂正した。** 完了報告で「TDnet」を最初と
   述べていたが、正しくは**J-Quants V2 Fundamentals/Financial Summaryから
   開始する**。理由: (a) J-Quants V2認証は既にPhase3Bで実データ動作確認済みであり、
   新規Provider認証という未知数を増やさずにFoundation自体を検証できる、
   (b) Raw Snapshot/PIT/Provenance/Entity Mappingとの統合を最も小さい追加
   リスクで検証できる、(c) Phase3D Foundationを本物の企業財務データで最初に
   実戦テストできる、(d) 「Foundation自体の問題」と「TDnet/EDINET等、新規Source
   固有の接続問題」を切り分けやすい。`DATA_SOURCE_ARCHITECTURE.md`へ
   「Phase4 Roadmap」節を新設し、Phase4A(J-Quants Fundamentals)→
   4B(TDnet+EDINET+Company IR)→4C(Positioning/需給)→4D(Japan Macro)→
   4E(Japan News/Global Market/Global News/Consensus)の順を明記した
   (Idea SourcesはCrawlingを伴うため引き続きPhase6)。
3. **Phase4Aで最優先する原則を明記した。** Phase4Aは「好決算銘柄を探す」ことを
   目的にしない。最優先は`J-Quants Financial Raw -> Normalized Fundamental
   Record -> Canonical Entity -> PIT -> Revision History -> Catalog ->
   Evidence -> Provenance`という経路が実データで正しく通ることであり、
   **最重要Validation項目は「後日修正された会社予想・財務データを、修正前の
   DecisionへLeakさせないこと」**(`RevisionHistory.as_of()`の実データ確認)。
   Phase4Aでは戦略探索・パラメータ最適化・BUY/SELL判断は一切行わない
   (`DATA_SOURCE_ARCHITECTURE.md`「Phase4 Roadmap」節参照)。

**Phase4Aの実装自体には、本Decisionの時点ではまだ着手していない。**

**回帰確認**: `pytest`(Lab 233件、既存Screening Tool 37件)・`ruff check`・
`ruff format --check`・`mypy`いずれもclean。`git diff --stat`で`core/` `app.py`
`tests/`への変更が無いことを確認済み。既存Schema(Enum値・Field構成)は無変更、
Docstring/ドキュメントの追記のみ。

---

## D0042 — Phase4開始前のArchitecture Cleanup(Phase3Dは引き続きCOMPLETE)

**Phase3Dのstatusは変更しない。** 目的はPhase1〜3Dを作り直すことではなく、
Phase4以降でFundamental/Disclosure/News等の実データを接続した際に、後から
高コストな設計変更が発生するのを防ぐこと。既存Schemaの破壊的変更は行っていない
(全て既定値付きのOptional Field追加、または新規クラス追加)。

**変更内容**:

1. **Source AuthorityとDelivery Providerを分離した。** `SourceMetadata`へ
   `originating_source`(情報の原典、例: `"EDINET"`)・`delivery_provider`
   (それをResearch Labへ届けたProvider、例: `"JQUANTS"`)を追加(両方Optional、
   既定`None`、既存構築箇所は無変更で動作する)。EDINET由来の情報をJ-Quants
   経由で取得した場合と直接EDINET APIから取得した場合を区別でき、Provider障害・
   遅延・変換による差異の追跡やProvenanceの正確な保持に使う。
2. **Backtest/Experimentの完全Offline原則を明文化し、`FrozenPitUniverseProvider`
   (`lib/universe.py`)を新設した。** Historical Backtestの実行中にdecision_at
   ごとに外部APIへ問い合わせる構造を本番Defaultにしない
   (`External Provider -> Acquisition -> Immutable Raw Snapshot ->
   Normalized PIT Dataset -> Frozen Dataset -> Backtest(Network無し)`)。
   `PitMasterUniverseProvider`(D0039、`master_fetcher`をdecision_atごとに
   呼び出す)は取得・診断用途として引き続き有効だが、実験本番では
   `FrozenPitUniverseProvider`(事前取得済みSnapshotのみから解決、Callable引数を
   一切持たず構造的に外部呼び出し不可能)を将来Defaultにする方針とした。
   **`scripts/jquants_lab_pipeline.py`は元々decision_atごとの外部呼び出しを
   行っていない**(D0039で`PitMasterUniverseProvider`をまだ実データPipelineへ
   接続していなかったため)ことを確認し、この原則が現状のPipelineで既に
   暗黙に守られていることをRESEARCH_RULES.mdへ明記した。
3. **market_public_atとprovider_available_atを概念上分離し、2種類のPIT研究
   (Market Information Study / Reproducible System Simulation)を区別した。**
   既存の`published_at`(market_public_at相当)/`available_at`
   (provider_available_at相当)/`retrieved_at`のField自体は増やさず、
   Semanticsを`SourceMetadata`のDocstringへ明文化した。どちらの基準を
   使用したExperimentかを追跡できるよう、`lib.evidence.model.
   AvailabilitySemantics`(MARKET_PUBLIC_AT/PROVIDER_AVAILABLE_AT)Enumと
   `Experiment.availability_semantics`(`str | None`、既定`None`)を新設した。
   このLabのPIT判定(`EvidenceRecord.is_usable_at()`等)は既定でB系統
   (`available_at`基準)であることを明記した。
4. **Revision/Correction ContractへFundamental向けの`revision_reason`を
   追加した。** `SourceVersion`に`revision_reason: str | None = None`
   (訂正理由、任意)を追加し、既存のRevision非Leak保証
   (`RevisionHistory.as_of()`)をPhase4Aの財務データでも同じ仕組みで使う
   前提を明確にした。
5. **Phase4A Fundamental Schema Contract(設計指針のみ、未実装)を
   `DATA_SOURCE_ARCHITECTURE.md`へ追記した。** Fundamental Dataを
   `code/date/sales/profit`のような単純なWide Tableへ早期に潰さず、
   actual/company_forecast/next_year_forecast、四半期区分(1Q/2Q/3Q/FY)、
   累計vs単独、連結/非連結、fiscal_period/fiscal_year、開示日時・番号、
   document_type、accounting_standard(JGAAP/IFRS/USGAAP)、Revision、
   currency/unitを区別可能であることを設計指針として明記した。
   **NULLを0へ変換しない契約を型で表現する下地**として、
   `lib.evidence.model.ValueAvailability`(NOT_YET_FETCHED/NOT_APPLICABLE)を
   予約Sentinelとして新設した(実際のFundamental Record Schema確定実装は
   Phase4Aで行う、ここでは契約のみ予約)。
6. **Storage Architecture(将来要件)を`DATA_SOURCE_ARCHITECTURE.md`へ
   予約した。** Raw(compressed JSON/CSV、既存`RawSnapshotStore`維持)→
   Normalized(Parquet)→Analytical Query(DuckDB)→Catalog/Provenance
   (SQLite/DuckDB)→Long-form Document/News(File/Object Storage +
   Metadata DB)という方向性のみ記録。現時点でのStorage Migrationは
   不要(実装していない)。Raw Provider PayloadをParquet変換後に削除しない、
   Derived/NormalizedはRawから再生成可能にする、という原則を明記した。
7. **News Licensing/Storage Policy(将来要件)を`DATA_SOURCE_ARCHITECTURE.md`へ
   予約した。** `FULL_CONTENT_ALLOWED`/`METADATA_ONLY`/`REFERENCE_ONLY`/
   `DERIVED_SUMMARY_ALLOWED`/`UNKNOWN_RESTRICTIONS`という将来のPolicy分類を
   記録(UNKNOWNの場合は安全側=保存範囲制限側に倒す)。Phase4Eで実装、
   Phase4Aでは実装しない。
8. **Hidden Test隔離(Phase5必須要件)をRESEARCH_RULES.mdへ追記した。**
   Locked Hidden TestをHypothesis Agent/Knowledge Agent/Retrieval Agent/
   Strategy Generatorから原則アクセス不能にする、Dataset Access Layer
   (RESEARCH → VALIDATION → LOCKED_TEST → FUTURE/PAPER_TRADE)による隔離が
   必要であることをPhase5のRoadmapとして明記した(Phase3D/Phase4Aでは未実装)。
9. **SourceAuthorityClassの意味の明文化(D0041で着手済み)を維持・補強した。**
   `13_tests/test_source_catalog.py`へ、`SourceAuthorityClass`が
   `IntEnum`ではないこと、モジュール内に`score`/`weight`/`rank`を含む
   スコアリング関数・定数が存在しないことを構造的に確認するテストを追加した。
10. **Anti-Confirmation原則(D0040)は維持した。** DEFAULT PROCESS =
    ADVERSARIAL、CONCLUSION = NEUTRAL UNTIL SUPPORTED。Evidenceそのものへ
    Positive/Negativeを固定せず、Hypothesisに対するRelation
    (SUPPORTS/CONTRADICTS/ALTERNATIVE_EXPLANATION/NEUTRAL/UNKNOWN)としてのみ
    扱う。`INSUFFICIENT_EVIDENCE`/`UNKNOWN`を正式な結果として維持する。変更なし。

**このDecisionでやらないこと**: Phase4A実装・Real Fundamental Data取得・
Strategy探索・Parameter Optimization・BUY/SELL判断・AI Agent実装・News取得・
全市場Bulk Downloadには着手していない。既存Screening Tool(`core/` `app.py`
`tests/`)は無変更。

**回帰確認**: `pytest`(Lab 246件 = 従来233件+新規13件、既存Screening Tool
37件)・`ruff check`・`ruff format --check`・`mypy`(62ファイル)いずれもclean。
`git diff --stat`で`core/` `app.py` `tests/`への変更が無いことを確認済み。
