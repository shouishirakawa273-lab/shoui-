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

---

## D0043 — Phase4A: J-Quants Fundamentals / Financial Summary 統合(Field名未検証、CODE_COMPLETE_AWAITING_LOCAL_VALIDATION)

**目的**: 「好決算銘柄を探す」ことではなく、J-Quants Financial Raw ->
Immutable Raw Snapshot -> Normalized Fundamental Record -> Canonical Entity
-> Point-in-Time -> Revision/Correction History -> Data Catalog -> Evidence
-> Provenance -> Frozen Offline Dataset という経路が実データでも通ることの
検証(Infrastructure/Integration Validation)。Strategy探索・Parameter
Optimization・Factor探索・BUY/SELL判断・Rankingはこのフェーズでは行っていない。

### A. 公式仕様確認の試行結果(重要): 接続不可

本セッションは`/v2/fins/summary`の公式仕様(`jpx.gitbook.io`等)へ**一切疎通できなかった**。
証拠:

- `curl -s -m 10 -o /dev/null -w "%{http_code}\n" https://jpx.gitbook.io/j-quants-en`
  および`https://jpx-jquants.com`・`https://www.google.com` → いずれも
  `curl: (56) Recv failure`相当のconnection failed、HTTPステータス`000`。
- `WebFetch`で`https://jpx.gitbook.io/j-quants-en/api-reference/statements-1`を
  取得試行 → `{"error_type":"EGRESS_BLOCKED","domain":"jpx.gitbook.io",
  "message":"Access to jpx.gitbook.io is blocked by the network egress proxy."}`
- `curl -sS -m 10 "$HTTPS_PROXY/__agentproxy/status"` → `recentRelayFailures`に
  `jpx.gitbook.io`/`jpx-jquants.com`/`www.google.com`いずれも
  `"kind":"connect_rejected","detail":"gateway answered 403 to CONNECT
  (policy denial or upstream failure)"`が記録されている。

**これはPolicyレベルの遮断であり、一時的な障害ではない**(Phase3A以降、毎Phaseで
確認されてきたパターンと一致)。したがって`/v2/fins/summary`のField名
(`DiscNo`/`DocType`/`DiscDate`/`DiscTime`/`CurPerType`/`Sales`/`OP`/`NP`/
`FSales`/`FOP`/`FNP`/`NxFSales`/`NxFOP`/`NxFNP`/`NCSales`/`NCOP`/
`OrdinaryProfit`等)・Pagination仕様・Rate Limit・Null/空文字の意味・
Document Type一覧・会計基準の識別方法は、**このセッションでは未検証のまま**、
ユーザーがセッション内で提示した情報のみに基づく作業仮説として実装した
(既存`RESPONSE_SCHEMA_VERSION`/`_get_all_pages`ページネーションパターンを
そのまま踏襲し、新規のPagination仕様は発明していない)。

**ローカル環境での実データ検証が必須**(下記N参照)。ローカルで確認した実際の
Field名・DocType一覧・Null意味論が、以下の仮定と異なる場合はコードを直接
修正せず、本Decisionへ追記すること。

### B. 実装Architecture

新規`lib/fundamentals/`パッケージ(既存`core/` `app.py` `tests/`は無変更):

- `model.py`: `DisclosureEnvelope`(開示1件の記述的Envelope)・
  `FundamentalMetric`(指標1件、Long-form/Metric-based Schema)・
  `PeriodType`/`PeriodBasis`/`ConsolidationScope`/`ActualOrForecast`/
  `FiscalYearTarget` Enum。`NORMALIZER_VERSION`定数(Provider Schema Evolution
  追跡用)。
- `normalize.py`: Raw Payload(`list[dict]`) -> `(list[DisclosureEnvelope],
  list[FundamentalMetric])`。`_METRIC_FIELD_MAP`(metric_type ->
  Raw Field名・Actual/Forecast・当期/翌期・連結/非連結)、`_DOC_TYPE_TO_
  ACCOUNTING_STANDARD`(DocType文字列からの明示的Mapping、未知はfail closed)、
  `resolve_value_availability()`、`_build_market_public_at()`、
  `_provider_available_at_and_basis()`、`build_revision_histories()`。
- `view.py`: `fundamentals_as_of(revision_histories, decision_at,
  availability_semantics=...)` — 外部呼び出しを一切持たない純粋関数
  (`FrozenPitUniverseProvider`と同じOffline-by-construction設計)。
- `evidence.py`: `disclosure_metric_to_evidence()` — FACTのみ生成、
  解釈語なし、`EvidenceRelation`なし。
- `catalog.py`: `build_financial_summary_dataset_descriptor()` —
  `implementation_status=FIXTURE_ONLY`でCatalog登録。
- `lib/data_sources/jquants.py`/`fixture.py`/`local_snapshot.py`に
  `fetch_financial_statements()`を追加(既存`fetch_equity_bars`等と同じ
  `RawFetchResult`パターン)。`fetch_dividends()`はScope外のため未実装
  (`FundamentalDataProvider` Protocolを完全には満たさない、意図的)。

### C. Fundamental Schema

Wide Tableへ早期に潰さず、Disclosure単位(`DisclosureEnvelope`)+
Metric単位(`FundamentalMetric`、Long-form)に分離した。1つのDisclosure行から
最大12個の`FundamentalMetric`(sales/operating_profit/net_profit ×
actual/current_forecast/next_forecast、および非連結2種、経常利益1種)を生成する。
`series_id = internal_code|metric_type|fiscal_year_target|period_type|
consolidation_scope|accounting_standard`でRevision系列を識別する。

### D. ValueAvailability(Stored Value State)の最終設計

D0042での2値予約(`NOT_YET_FETCHED`/`NOT_APPLICABLE`)を、Additional Safety
Correctionsに基づき4値へ再設計した: `PRESENT` / `NOT_APPLICABLE` /
`MISSING_OR_UNSPECIFIED` / `UNKNOWN`。**`NOT_YET_AVAILABLE`は意図的に含めない**
— これはMetric Valueそのものの属性ではなく、As-of Queryの結果側
(`fundamentals_as_of()`が`None`を返すことで表現)に属する概念であるため。
Raw値が空文字列というだけでは`NOT_APPLICABLE`と断定しない
(`resolve_value_availability()`)。会計基準から明示的に確認できる場合
(現時点ではユーザー確認済みの1事実、IFRS/USGAAPの経常利益相当のみ)に限り
`NOT_APPLICABLE`とし、それ以外の空値は`MISSING_OR_UNSPECIFIED`とする。

### E. Actual/Forecast/Period/Scope

ACTUAL/COMPANY_FORECAST、CURRENT_FISCAL_YEAR/NEXT_FISCAL_YEAR、
CONSOLIDATED/NON_CONSOLIDATEDは常に別Recordとして保持し、上書きしない。
`CurPerType`は公式仕様上1Q/2Q/3Q/4Q/5Q/FYを取りうるとされ、`PeriodType`は
これに`OTHER`を加えた7値。未知の生値はException停止ではなくwarningログ+
`OTHER`へfail closedする(`_parse_period_type()`、Provider Schema Change検知)。
2Q累計をQ2単独値として扱う自動導出はPhase4Aでは一切行わない
(`PeriodBasis`は現状`CUMULATIVE`固定、Standalone導出は将来DERIVED Recordとして
別途実装)。連結/非連結の判定はDocTypeのsubstring heuristicではなく、
値をどのField群(`Sales`/`OP` vs `NCSales`/`NCOP`)から取得したかという構造的
事実で決める。

### F. PIT semantics — market_public_at

`DiscDate`+`DiscTime`の両方が確認できた場合のみ、Asia/Tokyo tz-awareな
`market_public_at`を構築し`AvailabilityBasis.EXACT`とする
(`_build_market_public_at()`)。`DiscTime`が空/不明な場合、15:00や15:30等の
推測補完は一切行わず`market_public_at=None`・`AvailabilityBasis.UNKNOWN`と
する(Fixtureの8056/BIPROGY行で確認)。

### G. Provider availability handling — provider_available_at

**実際の観測ログ(Polling Log)がこのセッションには存在しないため、
`provider_available_at`は常に`AvailabilityBasis.UNKNOWN`とする**
(`_provider_available_at_and_basis()`)。「18:00頃速報」のような
Provider Update Policyの「頃」表現をExact Timestampへ変換することを明示的に
禁止する(Additional Safety Correction #2)。構造上必須の`SourceVersion.
available_at`Fieldには保守的なAnchor(`market_public_at`、無ければ
`retrieved_at`)を入れるが、`availability_basis=UNKNOWN`である限り
`RevisionHistory.as_of()`の既定動作(UNKNOWN Version除外、D0040/D0042)により、
Reproducible System Simulation(B系統)からは自動的に除外される
(架空の「確認済み事実」として誤用されない)。

### H. Revision/Correction handling

同一`series_id`の複数Disclosureは、公式仕様でRevision Relationship
(どのDiscNoが何を訂正したか)を確認できないため、`supersedes_version_id`は
常に`None`(=関係不明)のまま独立した時系列として保持する
(`build_revision_histories()`)。`is_correction`は常に`False`
(Forecast RevisionとCorrection/Restatementは概念上別物であり、Phase4Aでは
自動でCorrectionを検出しない、Additional Safety Correction #4)。
`RevisionHistory.as_of()`は`available_at`/`availability_basis`のみで
「その時点で使えた最新Version」を安全に選択するため、明示的なsupersedes chainが
無くても正しく機能する(Toyota(7203)Fixtureの2回のForecast改定で確認)。

### I. Offline reproducibility

`fundamentals_as_of()`/`as_of_by_semantics()`は外部呼び出しを一切持たない
純粋関数(`FrozenPitUniverseProvider`と同じ設計)。統合テストで、
`RawSnapshotStore.save()` → (Session再起動を模した)`RawSnapshotStore.load()`
→ 正規化 → As-of View、を2回独立実行して結果が完全に一致することを確認した
(`test_fundamentals_integration.py::test_full_pipeline_is_reproducible_offline_from_saved_snapshot`)。

### J. Data Catalog / Evidence integration

`build_financial_summary_dataset_descriptor()`で`DataCapability.FUNDAMENTAL`
配下へ`implementation_status=FIXTURE_ONLY`として登録(実データ疎通前段階を
明示)。`disclosure_metric_to_evidence()`はFACTのみ生成し(例:
「7203: operating_profit_current_year_forecast(CURRENT_FISCAL_YEAR, FY,
COMPANY_FORECAST, CONSOLIDATED)を120000として開示」)、「好調」「Bullish」
「買い」等の解釈語を含まない。`EvidenceRelation`はHypothesisが存在しない限り
付与しない(`EvidenceRecord`自体にRelation Fieldが無いことは既存Schema設計、
D0040のまま)。`originating_source="JQUANTS_SOURCE_DATA"`/
`delivery_provider="JQUANTS"`(D0042の分離を使用)。

### K. Tests

新規45テスト(`test_fundamentals_model.py` 8件、`test_fundamentals_normalize.py`
20件、`test_fundamentals_view.py` 10件、`test_fundamentals_integration.py` 7件)、
および`test_evidence_model.py`の`ValueAvailability`再設計に伴う既存テスト1件の
更新。Lab全体は246件 → 291件。
要求された20項目Fixture Test全てを網羅(Raw Immutable・Provider/Internal
Code混同なし・Actual/Forecast混同なし・当期/翌期混同なし・連結/非連結混同なし・
2Q累計とQ2単独の混同なし・0とNULLの区別・NOT_APPLICABLEと0の区別・
IFRS経常利益blankを0扱いしない・market_public_atのtz-aware性・
provider_available_at UNKNOWN時の自動Fallback禁止・未来Disclosure/Forecast
Revision/Correctionの非Leak・Revision前後のas_of View変化・Entity Registry
Mapping・Raw→Normalized→Evidence Provenance・Frozen Dataset Offline再現性・
既存Price Backtest/Screening Tool無変更)に加え、Property/Invariant Test
(usable_records ⊆ available<=decision_at、t1<t2で未来Leakなし、Revision追加が
過去as_ofを変えない、同一Raw+同一normalizer_versionで同一Normalized Hash)を実装。

### L. 既存Screening Tool無変更の確認

`git diff --stat -- core/ app.py tests/`は空(変更なし)。既存Screening Tool
の37テストは無変更のまま全通過。

### M. 既知の限界

- `/v2/fins/summary`のField名・DocType一覧・Pagination・Rate Limit・
  Null/空文字の意味論は本セッションでは一切実データ検証できていない
  (上記A参照)。ローカル実データで異なる仕様が判明した場合、コードを
  無断で書き換えず本Decisionへ追記すること。
- `_DOC_TYPE_TO_ACCOUNTING_STANDARD`は実際のDocType文字列を含まない
  (Fixture Test専用の仮エントリ`"FYFinancialStatements_Consolidated_IFRS_SYNTH"`
  のみ)。実データでのDocType一覧確認後、正式なMapping Tableへ置き換える必要がある。
  未知のDocTypeは`accounting_standard=None`へfail closedし、warningログを残す
  (Exceptionで全処理停止しない)。
- `provider_available_at`は実データでも当面`availability_basis=UNKNOWN`の
  ままとなる(実際のPolling/Observation Logを構築するまで)。B系統
  (Reproducible System Simulation)のAs-of Queryは、明示的に
  `include_unknown_availability=True`を指定しない限り`None`を返し続ける
  (安全側デフォルト、意図的)。
- Revision Relationship(あるDiscNoが別のDiscNoをsupersedeする関係)は
  公式仕様が未確認のため一切保持しない。実データでDiscNo/DocTypeから
  安全に確認できる方法が判明した場合のみ、将来`supersedes_version_id`を
  埋める設計へ拡張する。
- Rate Limitは`min(plan_limit=60, endpoint_limit=60)=60`req/分と結論し、
  既存の共有`_RATE_LIMIT_INTERVAL_SEC=1.05秒`(~57req/分)で両方を
  満たすため追加のコード変更は行っていない(Endpoint別スロットリングの
  必要が生じた場合の拡張点としてのみ記録)。

### N. Local Real Data Validation(必須、下記PowerShellコマンド参照)

本Phase4Aは`CODE_COMPLETE_AWAITING_LOCAL_VALIDATION`とし、完全COMPLETEとは
自称しない。ユーザーのローカルPC環境(`.env`に`JQUANTS_API_KEY`設定済み)で
以下を実行し、実データでの疎通・PIT/Revision挙動を確認すること
(具体的なコマンドは完了報告(タスク#71)に記載)。

### O. Commit

このDecision自体は実装完了後にコミットする(タスク#71でCommit Hashを記録)。

**このDecisionでやらないこと**: Strategy探索・Parameter Optimization・
Factor探索・BUY/SELL判断・Ranking・「好決算」の定義・News/TDnet/EDINET/
Company IR接続・全市場Bulk Historical Fetch・Portfolio Construction・
AI Interpretationには着手していない。Phase4Bには進んでいない。

---

## D0043 追記 — Phase4A: Local Real Data Validation(7203)結果の反映

2026-08-16、ユーザーがローカルPC環境で実際に`/v2/fins/summary`(7203)へ接続し、
実Raw Responseの一部を確認した。**このセッション自体は引き続き公式ドキュメントへ
接続できない**(上記「A」の状況は不変)。以下は、ユーザー報告に基づく実観測結果を
コード・テスト・ドキュメントへ反映した記録である。「公式仕様で確認済み」と
「Local Real Dataで観測済み」は別物であり、区別して記載する。

### Local Real Dataで確認済み(公式仕様確認ではなく、実Wire Formatの観測)

1. **Field名の実在確認**: `Sales`/`OP`/`OdP`/`NP`/`EPS`/`BPS`/`NxFSales`/
   `SigChgInC`/`RetroRst`/`MatChgSub`/`CurPerSt`/`CurPerEn`/`CurFYSt`/`CurFYEn`/
   `NxtFYSt`/`NxtFYEn`が実在するField名であることを確認。従来の仮Field名
   `"OrdinaryProfit"`は誤りで、正しくは`"OdP"`(`_METRIC_FIELD_MAP`を修正、
   `lib/fundamentals/normalize.py`)。
2. **Wire Format(値の型)**: 数値(大きな整数値・小数値いずれも)、booleanに
   見える値もすべて**文字列**として返る(例: `Sales="15481299000000"`、
   `EPS="109.28"`、`MatChgSub="false"`)。欠損値は空文字列(例: `OdP=""`)。
   → `provider_declared_type`(未確認)と`observed_wire_type`(文字列)と
   `normalized_type`(`Decimal`/`bool | None`)を概念上分離した。Rawを公式型へ
   無理にcoerceしない方針は維持。`lib.fundamentals.normalize.parse_boolean_
   string()`を新設し、`"true"`/`"false"`の明示的literalのみ受理、
   Python truthiness(`bool("false")`が`True`になる罠)は使わず、未知literal
   はNone(UNKNOWN)へfail closedする。数値文字列は既存の`Decimal`Parse
   (`_parse_decimal`)がそのまま安全に扱える(大きな整数値・小数値いずれも)。
3. **DocType実在確認**: `1QFinancialStatements_Consolidated_IFRS`/
   `2QFinancialStatements_Consolidated_IFRS`/
   `3QFinancialStatements_Consolidated_IFRS`/
   `FYFinancialStatements_Consolidated_IFRS`が実在するDocType値であることを
   確認。`_DOC_TYPE_TO_ACCOUNTING_STANDARD`をこれら4件(すべてIFRS)へ更新し、
   Fixture Test専用の仮エントリ(`..._SYNTH`)を置き換えた。JGAAP/USGAAPの
   DocType値は依然未確認のため、引き続き空Mapping(fail closed)。
4. **`DiscNo`とDisclosure Dateの無関係性**: 実観測で`DiscNo=20220204580837`
   (先頭が`2022-02-04`を思わせる)だが`DiscDate=2022-02-09`(実際の開示日は
   異なる)であることを確認。**DiscNoからDisclosure Date/Timeを推測すること
   を明示的に禁止する規約をRESEARCH_RULES.mdへ追加**し、対応するテストを
   追加した(`test_disc_no_is_not_used_to_derive_disclosure_date`)。もともと
   実装はDiscNoを日付Parseに使っていなかった(構造的に安全だった)が、この
   実観測により、その安全性が「たまたま」ではなく「確認済みの理由がある」
   ことになった。
5. **Period/Coverage Semantics(重要)**: `/v2/fins/summary`への`code`指定
   クエリは、Price API(`/v2/equities/bars/daily`)とは異なり、`from`/`to`
   パラメータで期間に絞り込まれるとは**限らない**。実観測: `--start
   2024-01-01 --end 2024-12-31`を指定しても、対象Code(7203)が持つ取得可能な
   全履歴(2021-11-04〜2026-08-04、20件)が返った。

### 上記5の反映によるコード変更

- `lib.data_sources.jquants.JQuantsAdapter.fetch_financial_statements`:
  Docstringへこの事実を明記し、`RawFetchResult.data_period`の値を
  `f"requested_research_window={start}/{end}"`へ変更(「実際に返った範囲」
  ではなく「要求したResearch Window」であることを明示)。
- `lib.data_sources.local_snapshot.LocalSnapshotAdapter.fetch_financial_
  statements`/`lib.data_sources.fixture.FixtureDataSourceAdapter.fetch_
  financial_statements`: **DiscDateによる期間フィルタを削除した。**
  従来はこれらのAdapterがファイル/fixtureを読み込む際にDiscDateで
  Client-side Filteringしており、これは実データでは正しくない挙動を再現する
  だけでなく、フィルタ後の結果がそのまま`RawSnapshotStore.save()`で
  Immutable Raw Snapshotとして保存されうる構造だったため、Rawの一部
  (Research Windowの外にあるDisclosure)が「取得されなかったこと」に
  なってしまうリスクがあった(raw削除禁止原則に抵触しうる)。Research
  Windowによる絞り込みは、Normalized/As-of層(`fundamentals_as_of()`)が
  `decision_at`基準で行う、という既存原則(D0042 Offline原則)に一本化した。
- `lib.fundamentals.normalize.raw_disclosure_date_range(payload)`を新設。
  Raw Payload全体の実際のDiscDate範囲(Raw Coverage)を機械的に返す
  (Research Windowによる絞り込みは行わない)。
- `scripts/fetch_jquants_local_snapshot.py`: `--fetch-financial-summary`
  実行時に各Codeについて`financial_summary_<code>.coverage.json`
  (`query_type=CODE_HISTORY`/`requested_code`/`retrieved_at`/`record_count`/
  `raw_min_disc_date`/`raw_max_disc_date`/`research_window_start`/
  `research_window_end`)を追加保存し、標準出力にもRaw Coverageを表示する
  ようにした(共有`SnapshotManifest`データクラス自体は他Sourceへの影響を
  避けるため変更していない、Sidecar Fileとして追加)。
- `scripts/jquants_financial_summary_diagnostic.py`: `--research-window-
  start`/`--research-window-end`(任意、参考表示のみ・絞り込みはしない)を
  追加し、Raw CoverageとResearch Windowを別々に表示するようにした。Raw
  CoverageがResearch Windowを超えていてもWarningではなく正常な状態として
  扱う。

### Forecast Revision vs Correctionの扱い(変更なし、再確認のみ)

`RetroRst`(Retrospective Restatement)等の実在Field名は確認できたが、これを
`is_correction`の自動判定に使うことは今回行っていない。`RetroRst`の正確な
Semantics(どのDiscNoに対する訂正を意味するか等)は未確認であり、公式仕様で
確認できない限り、Revision Relationshipを推測で確定させない既存原則
(D0043「H」)を維持する。`ChgByASRev`/`ChgNoASRev`/`ChgAcEst`も同様に未実装
(Raw Payloadには保持されるが、Metricへは未マッピング)。

### 依然未検証(Local Real Data Validationでも確認できていない)

`TA`/`Eq`/`EqAR`/`CFO`/`CFI`/`CFF`/`CashEq`/Dividend関連Field/Share Count
関連Field/非連結詳細Field/`ROE`等のField名は実在が報告されたが、
`_METRIC_FIELD_MAP`へのMapping(Metric化)はPhase4Aのスコープとして意図的に
見送った(Raw Payloadには保持され、Normalizerも壊れない。将来必要になった
時点でMapping追加する拡張ポイントとして記録する)。Pagination仕様・Rate
Limitの実際の挙動・JGAAP/USGAAPのDocType値も未確認のまま。

### Tests

新規18テスト追加(`test_fundamentals_wire_format.py` 13件: 大きな整数値
文字列のDecimal変換・小数値文字列のDecimal変換・parse_boolean_stringの
明示的literal受理/fail closed・空文字列と0/Falseの非等価性・IFRS OdPの
NOT_APPLICABLE判定(確認済み実DocType使用)・DiscNo≠DiscDate・
raw_disclosure_date_range、`test_fundamentals_pit_real_dates.py` 5件:
実7203 Disclosure Date(2024-02-06/05-08/08-01/11-06)を用いたMARKET_
PUBLIC_AT系統のas_of境界確認、PROVIDER_AVAILABLE_AT系統のUNKNOWN
Fallback禁止の再確認)。Lab全体は291件→309件。既存45テスト(前回D0043
実装分)は無変更のまま全通過(Field名変更等の後方影響なし)。

**回帰確認**: `pytest`(Lab 309件・既存Screening Tool 37件)・`ruff check`・
`ruff format --check`・`mypy`(69ファイル)いずれもclean。`git diff --stat
-- core/ app.py tests/`で変更が無いことを確認済み。

**Status**: 引き続き`CODE_COMPLETE_AWAITING_LOCAL_VALIDATION`。今回の
Local Real Data Validationは7203の一部Fieldの単発確認であり、ユーザーが
指示した4銘柄(7203/6758/8056/3626)での本格的なValidationはまだ完了して
いない。Phase4Bへは進んでいない。

---

## D0043 追記2 — Phase4A: 4銘柄Local Real Data Validation完了、Phase4A正式COMPLETE

2026-08-16、ユーザーが4銘柄(7203/6758/8056/3626)全てでローカルPCから実際に
`/v2/fins/summary`へ接続し、Validationを完了した。

### 4銘柄Validation結果(ユーザー報告)

| Code | 確認されたDocType Pattern | 確認されたPeriod Type |
| --- | --- | --- |
| 7203 | `*FinancialStatements_Consolidated_IFRS` | 1Q/2Q/3Q/FY |
| 6758 | `*FinancialStatements_Consolidated_IFRS` | 1Q/2Q/3Q/FY |
| 8056 | `*FinancialStatements_Consolidated_IFRS` | 1Q/2Q/3Q/FY |
| 3626 | `*FinancialStatements_Consolidated_JP` | 1Q/2Q/3Q/FY |

Raw CoverageがRequested Research Windowを超える挙動(D0043追記1参照)も
4銘柄すべてで再確認された。

### JP DocType対応(重要: 名称を推測しない)

3626で確認された`*FinancialStatements_Consolidated_JP`を
`_DOC_TYPE_TO_ACCOUNTING_STANDARD`へ追加した(`1Q`/`2Q`/`3Q`/`FY`の4パターン
全て)。**ただし`"_JP"`接尾辞が公式に何を意味するか(例: 日本基準=JGAAPと
同義かどうか)は、公式ドキュメントへ接続できないため確認できていない。**
したがって`"JGAAP"`という名称をMapping先として採用せず、IFRSとは区別
できるが特定の会計基準名を主張しない中立的な識別子
`lib.fundamentals.normalize.ACCOUNTING_STANDARD_PROVIDER_SUFFIX_JP`
(値: `"PROVIDER_SUFFIX_JP"`)を新設し、これへMappingした。`IFRS`用の
Mappingは変更していない(`ACCOUNTING_STANDARD_IFRS`定数として明示化のみ)。
`_NOT_APPLICABLE_UNDER_STANDARD`には`PROVIDER_SUFFIX_JP`を追加していない
(この会計基準で経常利益が存在しない、という事実は確認できていないため)。
公式仕様で`"_JP"`の正式な意味が確認できた時点で、Mapping先のLabelのみを
変更すること(Mappingの構造自体は変更不要)。

### Tests

新規4テスト(`test_fundamentals_wire_format.py`へ追加): JP接尾辞DocTypeが
fail closed(UNKNOWN)にならないこと、IFRSとは異なる値になること、
`"JGAAP"`という名称を採用していないこと、`_NOT_APPLICABLE_UNDER_STANDARD`
へ未確認のまま登録していないこと。Fixtureの3626行のDocTypeを、これまでの
仮値(`SYNTH_DOC_TYPE`)から実在確認済みの`2QFinancialStatements_
Consolidated_JP`へ更新した(既存の「未知Field保持」テストへの影響なし、
CurPerType="2Q"との整合も取れている)。Lab全体は309件→313件。

### Remaining Known Limitations(未確認、推測実装していない)

- Non-Consolidated DocType(連結DocTypeのみ確認済み)
- USGAAPのDocType(IFRS/`_JP`のみ確認済み)
- 4Q/5Qの実データ(1Q/2Q/3Q/FYのみ4銘柄で確認済み)
- Forecast Revision専用DocType(有無・形式とも未確認)
- Correction/Restatement Relationship(DiscNo間の親子関係、未確認のため
  `supersedes_version_id`は引き続き常に`None`)
- Endpoint Paginationの実挙動(複数ページに渡る場合の`pagination_key`挙動)
- `"_JP"`接尾辞の公式な意味(上記参照)
- `TA`/`Eq`/`EqAR`/`CFO`/`CFI`/`CFF`/`CashEq`/配当関連/株式数関連/`ROE`等の
  Field(実在は報告されたがMetricへは未マッピング、Rawには保持)

### Catalog Status更新

`lib.fundamentals.catalog.build_financial_summary_dataset_descriptor()`の
`implementation_status`を`FIXTURE_ONLY`から`CONNECTED`へ更新した(4銘柄での
実データ疎通確認完了を反映)。`known_limitations`も上記Remaining Known
Limitationsへ更新した。

### 既存PIT/Revision/Offline原則(変更なし)

`RevisionHistory.as_of()`のUNKNOWN Basis除外既定、`fundamentals_as_of()`の
Offline-by-construction設計、2種類のAvailabilitySemantics、Forecast
RevisionとCorrectionの概念分離、DiscNoからの日付推測禁止(D0043追記1)、
Raw Coverage/Research Windowの分離(D0043追記1)はいずれも変更していない。

### 回帰確認

`pytest`(Lab 313件・既存Screening Tool 37件)・`ruff check`・
`ruff format --check`・`mypy`(69ファイル)いずれもclean。`git diff --stat
-- core/ app.py tests/`で変更が無いことを確認済み。既存J-Quants Price
Backtestテスト(`test_available_at_vs_retrieved_at.py`等)は無変更のまま
全通過。

### Status変更: Phase4A正式COMPLETE

4銘柄(7203/6758/8056/3626)でのLocal Real Data Validationが完了し、
J-Quants Financial Raw -> Immutable Raw Snapshot -> Normalized Fundamental
Record -> Canonical Entity -> PIT -> Revision History -> Data Catalog ->
Evidence -> Provenance -> Frozen Offline Datasetの経路が実データで機能する
ことを確認した。Field名・DocType値の一部確認、Wire Format(数値・boolean
文字列)の確認、Raw Coverage/Research Window分離の確認、DiscNo≠DiscDateの
確認を含む。上記Remaining Known Limitationsに列挙した未確認事項は残るが、
これらはPhase4Aのスコープ(Infrastructure/Integration Validation)に必須
ではなく、将来Phaseでの拡張ポイントとして記録するのみで足りる、という
ユーザー判断に基づき、**Phase4Aのstatusを`CODE_COMPLETE_AWAITING_LOCAL_
VALIDATION`から`COMPLETE`へ変更する。** Phase4Bには着手していない。

---

## D0044 — Phase4A.5: Claude Code Research Engineering Guardrails

Phase4A COMPLETE後、Phase4B(TDnet/EDINET/Company IR接続)着手前に、
Japanese Equity Labの開発品質を高める目的でClaude Codeの Skills /
Subagents / Workflowのみを整備した。**投資研究機能・Data Source自体は
一切追加していない。** 既存Research Logic(`lib/`配下)・既存Screening
Tool(`core/` `app.py` `tests/`)は無変更。

### 公式仕様確認(実施済み)

このPhaseでは`code.claude.com`(Claude Code公式ドキュメント)への接続が
可能だった(過去PhaseでJ-Quants公式ドキュメントへの接続が拒否されたのとは
異なるHostであり、Egress Policyの対象外だった)。以下を実際に確認した上で
実装した(未確認のfrontmatter fieldやTool名は使用していない):

- SKILL.mdのFrontmatter Field一覧(`name`/`description`/`when_to_use`/
  `argument-hint`/`arguments`/`disable-model-invocation`/`user-invocable`/
  `allowed-tools`/`disallowed-tools`/`model`/`effort`/`context`/`agent`/
  `background`/`hooks`/`paths`/`shell`/`metadata`/`license`/
  `compatibility`)とProject Skillsの配置場所(`.claude/skills/<name>/
  SKILL.md`)。
- Project Subagentのfrontmatter field一覧(`name`/`description`/`tools`/
  `disallowedTools`/`model`/`permissionMode`/`maxTurns`/`skills`/
  `mcpServers`/`hooks`/`memory`/`background`/`effort`/`isolation`/
  `color`/`initialPrompt`)と配置場所(`.claude/agents/`)。**Subagent
  Frontmatterは`disallowedTools`のようにcamelCase、Skill Frontmatterは
  `disallowed-tools`のようにkebab-caseであり、両者は別の命名規約である
  ことを確認した(誤って混同しない)。**
  `context: fork`はSkill側のFieldであり、Subagent自身のFrontmatter
  Fieldには存在しない(Subagent frontmatterに`context: fork`は書けない、
  誤情報を実装しないよう確認した)。
- Skillの`skills` field(Subagentへのpreload機構、`skills: [name, ...]`)。
- Hook Event一覧(`PreToolUse`/`PostToolUse`等31種)、`PreToolUse`のみが
  Tool呼び出しをBlockできること(`PostToolUse`はBlock不可)。

### 実装内容

**5つのProject Skills**(`.claude/skills/`、いずれも`paths: Japanese_
Equity_Lab/**`でLab配下作業時のみ自動起動対象、明示的な`/name`起動は
どこからでも可能):

1. `pit-audit`: PIT/Look-ahead Leakage専門監査。published_at/market_
   public_at/provider_available_at/available_at/retrieved_at/decision_at/
   execution_atの取り違え、Revision/Restatement/Corporate Action/PIT
   Universe/Survivorship/Delisting/Forward-fill Leakage、Fundamentals
   固有(Actual/Forecast、当期/翌期、累計/単独、連結/非連結、会計基準、
   Correction/Revision、Raw Coverage/Research Window)を含む。Findings
   のみ出力(Severity/Evidence/Risk/Suggested Verification)、PASSでも
   何を確認したか明示する。修正はしない。
2. `adversarial-review`: DEFAULT PROCESS = ADVERSARIAL、CONCLUSION =
   NEUTRAL UNTIL SUPPORTED(RESEARCH_RULES.md §0.5と同じ原則を実装/研究
   設計Reviewへ適用)。Hidden Assumption・Confirmation Bias・Survivorship
   Bias・Overfitting・Silent Fallback(`unknown→zero`/`unknown→false`
   等)・Origin Source/Delivery Provider混同等をChecklist化。Claim/
   Counterargument/Alternative Explanation/Evidence Needed/Severityで
   出力。Buy/Sell判断はしない。
3. `phase-close`: `disable-model-invocation: true`(User明示起動のみ)。
   Phase Scope確認からCompletion Status判定までの15Step標準Procedure。
   Completion Status候補はCOMPLETE/CODE_COMPLETE_AWAITING_LOCAL_
   VALIDATION/BLOCKED/PARTIAL。**Commit/Pushはこのskill自身では行わず、
   Task Promptで明示的に要求された場合のみ**、Phaseの自動遷移も行わない
   ことを明記。
4. `source-onboarding`: 新規Data Source接続前(Phase4B以降)の調査
   Checklist。Source Identity/Originating Source/Delivery Provider/公式
   Doc/認証/Plan・契約/Cost/License/Historical Coverage/Rate Limit/
   Pagination/Correction・Deletion・Revision Semantics/PIT Timestamp
   Semantics/Entity識別子/Null意味論/Declared vs Observed Schema/Raw
   保存Policy等。確認できない項目はUNKNOWN(推測禁止)。
   `SourceAuthorityClass`は真実度Scoreではないことを明記。
5. `local-validation`: このセッションから実APIへ接続できない場合の標準
   Procedure(Windows PowerShell)。A〜Iの出力Section(Sync/Key存在確認/
   Smoke Test/Raw Snapshot取得/Raw確認/診断/Offline再実行/期待される
   観測結果/貼り戻すべき出力)。API Key本体を絶対に表示しない(存在確認
   のみ、`if ($env:...)`Pattern)。Mass Downloadを最初から実行しない。

**3つのProject Subagents**(`.claude/agents/`、いずれも`tools`
Allowlistが`Write`/`Edit`/`Bash`を含まない、すなわち構造的にRead-only):

1. `pit-auditor`(`tools: Read, Grep, Glob`、`skills: [pit-audit]`)
2. `skeptic-reviewer`(`tools: Read, Grep, Glob`、
   `skills: [adversarial-review]`)
3. `data-source-researcher`(`tools: Read, Grep, Glob, WebFetch,
   WebSearch`、`skills: [source-onboarding]`)。ConnectorやAPI Keyの取扱い
   は禁止と明記。

**Separation of Reviewer and Author**をArchitecture Ruleとして
`CLAUDE_CODE_RESEARCH_WORKFLOW.md`(新規)へ明文化した。Reviewer Agentは
発見したIssueをMain Claudeへ返すのみで自分で修正しない(Author ==
Reviewerを避ける)。同ファイルに通常の実装変更Workflowと新規Data Source
追加時のWorkflow(`data-source-researcher` → 実装 → `pit-auditor` →
`skeptic-reviewer` → `phase-close`)を図示した。`10_agents/README.md`
(将来のResearch Pipeline内AI Agent構想)とは別物であることも明記した。

`Japanese_Equity_Lab/CLAUDE.md`へ短い常時Ruleのみ追記した(既存内容は
無変更)。長いProcedureはCLAUDE.mdへコピーせず、上記Skillsへ置いた。

`HOOKS_PROPOSAL.md`(新規)でSecret Guard/Protected Path Warning/Optional
Phase Validationの3案を提案のみ記録した。`.claude/settings.json`は
このPhaseで変更していない(既存の`PostToolUse`品質ゲートHookは無変更)。

### Structural Validation

- 5つのSKILL.md全て、Python `yaml.safe_load`でFrontmatter Parseに成功
  (`description`はColonを含むため`>-` Folded Block Scalarを使用、Plain
  Scalarでは`mapping values are not allowed here`エラーになることを
  実際に確認した上で修正)。
- Skill名(`pit-audit`/`adversarial-review`/`phase-close`/
  `source-onboarding`/`local-validation`)は互いに重複せず、既存の
  Bundled Skill名とも衝突しない。
- 3つのSubagent Frontmatter全て、同様にParse成功。Agent名
  (`pit-auditor`/`skeptic-reviewer`/`data-source-researcher`)は互いに
  重複せず、既存Built-in Agent名(`Explore`/`Plan`/`general-purpose`/
  `claude-code-guide`/`statusline-setup`)とも衝突しない。
- 各SubagentのPreload Skill名(`pit-audit`/`adversarial-review`/
  `source-onboarding`)は対応するSkillディレクトリ名と完全一致することを
  確認。
- 3つのSubagentいずれも`tools`にWrite/Edit/Bashを含まないことを機械的に
  確認(Allowlist方式のため、明示していないToolは使用不可)。
- `phase-close`のFrontmatterに`allowed-tools`でgit commit/push系の
  Bash Patternを含めていないことを確認(既定のPermission Flowに従う、
  自動Commit不可)。
- `local-validation`の本文に`echo $env:...`等、Secret値を表示する
  Patternが含まれていないことを確認(存在確認Patternのみ)。
- `git diff --stat -- core/ app.py tests/`が空であることを確認
  (既存Screening Tool無変更)。
- **LOCAL_VALIDATION_NEEDED**: Claude Code自身の`/doctor`等による
  Interactive診断は、このHeadless/非Interactiveセッションでは実行できない
  (`/doctor`はこのセッションで利用可能なSkill一覧に含まれていない)。
  Subagentのライブ再読み込み(Live Change Detection)がSkillと同様に
  Session再起動無しで反映されるかも、公式ドキュメントでSkillについてのみ
  明記されており、Subagentについては未確認。次回Session起動時、または
  Userのローカル環境での`/skills`・Agent一覧表示による目視確認を推奨する。

### 回帰確認

`pytest`(Lab 313件・既存Screening Tool 37件、変更なし)・`ruff check`・
`ruff format --check`・`mypy`(69ファイル)いずれもclean(Pythonコードは
このPhaseで一切変更していないため、件数もPhase4A完了時点から不変)。
`git diff --stat -- core/ app.py tests/`で変更が無いことを確認済み。

### このDecisionでやらないこと

Phase4B実装・TDnet/EDINET/Company IR Connector・投資判断ロジック・
Buy/Sell Logic・AI Research Agent実装・既存Backtest Logicの変更・
Screening Toolの変更・Hookの自動導入(`.claude/settings.json`変更)には
着手していない。

---

## D0045 — Phase4B-1: Disclosure Common Core

Phase4A/Phase4A.5 COMPLETE後、Phase4B(TDnet/EDINET/Company IR接続)の
最初のStepとして、それら3つを将来同じArchitecture上で扱うための
Source非依存Disclosure Common Coreを実装した。**実Sourceへは一切接続して
いない**(TDnet/EDINET/J-Quants TDnet Add-on/Company IR Crawlingいずれも
未実装)。既存Research Logic(`core/` `app.py` `tests/`、および
`lib/fundamentals/`を含む既存`lib/`配下)は無変更。詳細は
`DISCLOSURE_ARCHITECTURE.md`参照。

### 1. Source-independent Disclosure Common Core

新規`lib/disclosures/`パッケージ(`model.py`/`normalize.py`/`view.py`/
`evidence.py`/`catalog.py`)。既存Primitive(Phase3D/Phase4Aの
`SourceCatalog`/`DataCapability`/`SourceMetadata`/`originating_source`/
`delivery_provider`/`EvidenceRecord`/`EvidenceType`/`AvailabilityBasis`/
`AvailabilitySemantics`/`EntityRegistry`/`RawSnapshotStore`)を再利用し、
Disclosure専用に同じ概念を再実装していない。`DataCapability.DISCLOSURE`
は既にPhase3Dで定義済みだったものをそのまま使用。

### 2. Document/Event separation、Document publication vs content semantics

`DISCLOSURE_ARCHITECTURE.md`の「Core Principle」参照。Document公開という
事実のみをFACTとして扱い、本文の内容(Claim/Estimate/Event)はこの
Phaseでは一切抽出・解釈しない(将来Phase)。

### 3. Explicit relationship only、No inferred correction

`DocumentRelationship`(`CORRECTS`/`RESTATES`/`REPLACES`/`REFERENCES`/
`RELATED_TO`/`UNKNOWN`)はProviderが明示するか公式Metadataで確認できる
場合のみ設定する。`parse_disclosure_payload()`はDocumentRelationshipを
一切生成しない(構造的な保証、Testで確認済み)。Forecast RevisionとCorrection
の混同禁止というFundamentals Phase4Aの原則をそのまま継承した。

### 4. PIT timestamp priority

`market_public_at`/`provider_available_at`/`retrieved_at`を区別し、
`provider_available_at`は実観測ログが無い限り常に`availability_basis
=UNKNOWN`とする(D0043の原則を継承)。「公開後の市場閉場後」パターン
(同日でも時刻がdecision_atより後なら除外)を単純なDate比較ではなく
tz-aware `datetime`比較で扱うことをTestで確認した。

**設計上の拡張(意図的)**: `DisclosureDocument`は`market_public_at_basis`
と`provider_available_at_basis`を独立した2つのFieldとして持つ
(Fundamentalsの`SourceVersion.availability_basis`は1つのみだったが、
Documentでは両方の確からしさを別々に追跡する必要があるため)。

**設計上の相違点(意図的、`DISCLOSURE_ARCHITECTURE.md`に詳細記載)**:
`disclosures_as_of()`は`fundamentals_as_of()`と異なりLatest-winsではなく
Set Filter(decision_at時点で利用可能な文書の集合)を返す。Documentは
Fundamentalsの指標のような「同一Seriesの異なるVersion」ではなく、それぞれ
独立した意味を持つため。

### 5. Origin vs delivery separation

`originating_source`/`delivery_provider`をD0042の分離のまま
`DisclosureDocument`/Evidence双方へ伝播させた(TDnetのOriginをJ-Quants
TDnet Add-on経由で取得する等のケースを将来表現可能にする)。

### 6. Exact duplicate vs event cluster separation

`find_exact_content_duplicate_groups()`(Raw行のContent Hash完全一致、
`lib.reproducibility.hash_json_safe`を再利用)と`find_same_source_
document_id_signals()`(同一Provider Document ID)の2種類のみを実装した。
**Title/PublicDate/Codeのみを見たHeuristic判定は行わない**(該当関数の
入力にTitleを一切含めない構造的保証、Testで確認)。TDnet/EDINET/Company
IRの同一Eventへの束ね(Event Clustering)はこのPhaseでは実装せず、
将来Phaseへ明示的に延期した。

### 7. Event extraction deferred

本文からのClaim/Estimate/Plan抽出、Forecast Revision Eventの自動生成、
Event Clustering、News統合、Hypothesis生成は全てこのPhaseのScope外
(`DISCLOSURE_ARCHITECTURE.md`「Future Event Extraction」参照)。

### 8. Attachment Model

`DisclosureAttachment`(PDF/XBRL/HTML/CSV/XML/OTHER/UNKNOWN)をDocumentと
分離。Phase4B-1は実Downloadを行わないため`availability`既定は
`METADATA_ONLY`。未知のAttachmentKindは`UNKNOWN`へfail closed。

### 9. Provider-neutral Fixture

新規Golden Fixture`13_tests/fixtures/disclosure_common_core_v1.json`は
TDnet/EDINET/Company IRいずれの実Wire Formatも模していない、完全に
Provider-neutralな合成Schema(`_disclaimer`に明記)。実Source接続時は
`data-source-researcher` Subagentによる公式仕様確認を経てから、実際の
Field名Mappingを追加すること。

### 開発中に発見した既存コードの潜在的Issue(このPhaseでは修正していない)

`lib.disclosures.normalize.parse_disclosure_payload()`実装中、複数のRaw
行が同一`source_document_id`を共有するケース(Dedup検出Testのために意図的に
作成)で、`internal_document_id`をRaw値優先(`doc_id_raw or index`)で
生成すると衝突することを発見した。`lib/disclosures/`側はIndex優先
(`f"DOC_{internal_code}_{index}"`)へ修正済み。**`lib.fundamentals.
normalize`の`envelope_id`生成(`f"ENV_{internal_code}_{disc_no or
index}"`)も理論上同じパターンだが、このPhaseはFundamentals Research
Logicへの機能変更を行わない制約のため、意図的に未修正のまま残した。**
実データで同一`DiscNo`を持つ複数行が返る実例が確認された場合は、別途
Decisionとして記録した上で修正すること。

### Tests

新規46テスト(`test_disclosures_model.py` 7件、`test_disclosures_
normalize.py` 20件、`test_disclosures_view.py` 10件、`test_disclosures_
integration.py` 9件)。Lab全体は313件→359件。既存313件は無変更のまま
全通過(既存Fundamentals/Price Backtest Regression含む)。

**回帰確認**: `pytest`(Lab 359件・既存Screening Tool 37件)・`ruff check`・
`ruff format --check`・`mypy`(75ファイル)いずれもclean。`git diff --stat
-- core/ app.py tests/`で変更が無いことを確認済み。

### Reviewer Findings(pit-auditor / skeptic-reviewer)

Phase4A.5で新設したSubagentsを今回から実運用した(初回実運用)。両Agentとも
`.claude/agents/`のRead-only Tool制限(`Write`/`Edit`/`Bash`を持たない)通り、
コードを一切変更せずFindings ReportのみをMain Claudeへ返した。

**pit-auditor**(4件、最高Severity MEDIUM):
1. `internal_document_id`は1回の`parse_disclosure_payload()`呼び出し内でしか
   一意性を保証しない(`DISCLOSURE_ARCHITECTURE.md`の記述を訂正)。
2. 衝突修正自体を回帰確認するTestが無かった(追加)。
3. `disclosure_document_to_evidence()`が`provider_available_at_basis
   =UNKNOWN`という情報を失う(Docstring/Architecture Docへ注意書き追加、
   Fundamentals Phase4Aと同型の既存制約であるため機能変更はせず)。
4. `PublicDate`のParseが未Guardで、不正な1行が全体のParseを異常終了させうる
   (`_parse_date_or_none()`を追加しfail closed化、Test追加)。

**skeptic-reviewer**(6件、最高Severity HIGH、総合`PASS_WITH_CONCERNS`):
1. [HIGH] `internal_document_id`一意性の主張(pit-auditor Finding 1と同じ
   論点、より強く指摘)。対応済み(上記)。
2. [HIGH] `_parse_attachments()`の`is_primary=bool(row.get("IsPrimary",
   False))`が、D0043で確認済みのWire Format(`MatChgSub="false"`のような
   文字列Boolean)に対してPython truthinessの罠(`bool("false")==True`)を
   再導入していた。`_parse_is_primary()`(`lib.fundamentals.normalize.
   parse_boolean_string()`と同じ設計)を新設し置き換えた。Test追加。
3. [MEDIUM] `disclosures_as_of()`のDocstringが、A系統でも`market_public_at_
   basis=UNKNOWN`除外が適用されることを明記していなかった(現行Normalizer
   では到達しないが、手動構築されたDocumentでは到達しうる)。Docstring修正
   + Test追加。
4. [MEDIUM] 同一`source_document_id`を持つ複数文書(例: FIX-D-006の後続版)が
   Set Filterの結果へ独立した項目としてそのまま含まれ、集計時の二重計上
   リスクがある。`disclosures_as_of()`のDocstringへ注意書きを追加し、
   `find_same_source_document_id_signals()`との併用を明記。
5. [LOW] `find_same_source_document_id_signals()`の`if document.source_
   document_id:`(truthiness)。調査の結果、これは意図的に正しい実装
   (空文字列同士をGroupingすると無関係な文書間に誤ったDuplicate Signalを
   生成してしまうため)と判断し、コード変更はせず、意図を説明するComment
   のみ追加した。
6. [LOW] `internal_document_id`修正の回帰Testが無い(pit-auditor Finding 2
   と同じ論点)。対応済み(上記)。

全Findingに対応後、新規6テスト追加(cross-call ID衝突の仕様確認1件、
IsPrimary Boolean Parsing 2件、A系統UNKNOWN Basis除外1件、および前回の
pit-auditor対応分2件)。Lab全体は359件→365件。再Reviewは実施していない
(全Finding対応後の最終Regressionで機械的に確認、Severity上限MEDIUM/HIGHは
いずれもDocumentation/Test/局所修正で解消可能な性質であり、再度の
Subagent呼び出しは必要と判断しなかった)。

**最終回帰確認**(全Finding対応後): `pytest`(Lab 365件・既存Screening
Tool 37件)・`ruff check`・`ruff format --check`・`mypy`(75ファイル)
いずれもclean。`git diff --stat -- core/ app.py tests/`で変更が無いことを
再確認済み。

### このDecisionでやらないこと

EDINET/TDnet/J-Quants TDnet Add-on/Company IR Connector・PDF Parse・
XBRL Parse・OCR・LLM Summary・Event抽出・Buy/Sell判断・Strategy変更・
Backtest条件変更・Screening Tool変更には着手していない。Phase4B-2
(EDINET)には進んでいない。

## D0046 — Phase4B-2: EDINET V2 Disclosure Integration(Onboarding調査ブロック、Raw Fetchのみ実装)

### §0 Tooling修正: `phase-close`の`disable-model-invocation`問題

Phase4A.5で`.claude/skills/phase-close/SKILL.md`に設定した
`disable-model-invocation: true`は、ユーザー(`/phase-close`)からしか
呼び出せず、Main Claudeが`Skill`ツール経由で明示的に呼び出そうとしても
ハードエラーで拒否されることが判明した(「意図せず自発的に実行しない」と
「必要な時にMain Claudeも実行できる」の中間を表すFrontmatterフィールドは
存在しない、公式仕様確認済み)。`disable-model-invocation: true`を削除し
(既定=ユーザー・Claude双方から呼び出し可能)、「実際にPhaseのCloseを
求められた時のみ呼び出す」という抑制意図はBody Textのガイダンスへ移した
(Access Controlではなく行動規範として表現)。自動commit/push・自動Phase
遷移の禁止は変更していない。

### §2/§24 Source Onboarding調査: ほぼ全面ブロック

`data-source-researcher` Subagent(`source-onboarding` Skill使用)による
EDINET API V2の公式仕様調査を実施した。**結果は severe**: `WebFetch`で
試みたFSA/EDINET公式URL(仕様書PDF、`disclosure2.edinet-fsa.go.jp`、
`www.fsa.go.jp`等)は全て`EGRESS_BLOCKED`で拒否され、副次資料(ブログ・
Qiita・Zenn・Wikipedia・Web Archive等)への接続もほぼ全て同様にブロック
された。到達できたのは`github.com`(サードパーティ製OSS Wrapper)と
`pypi.org`のみで、いずれもFSA発行コンテンツではない。

**Main Claude自身によるcurlでの独立検証**(Subagent報告を鵜呑みにせず
再現確認): `curl https://api.edinet-fsa.go.jp/...`および
`curl https://disclosure2dl.edinet-fsa.go.jp/...`はいずれも
`CONNECT tunnel failed, response 403`。これはJ-Quants公式ドキュメントが
過去に到達不可だった(D0012/D0025/D0031)のと同種の制約だが、今回は
**API本体(認証前のホスト到達性)まで含めてブロックされている**点がより
厳しい — J-Quantsは少なくともユーザーがCanonical Specificationを
本セッション内で直接明示できたが、EDINETについてはユーザーからの
実仕様提示もなく、調査自体がWebSearchスニペット合成に頼らざるを得な
かった。

得られた情報の質も低い: 認証方式(`Subscription-Key`クエリパラメータ
vs `Ocp-Apim-Subscription-Key`ヘッダ)は未確定、Documents Listの
実フィールド名は複数の断片的な裏付けしかなく体系的な確認はできず、
**Document Downloadの`type`パラメータについては2つの情報源が
互いに矛盾する値を主張していた**(同じ数字が別の形式を指す)。
`submitDateTime`/`opeDateTime`の意味論(PIT判定の核心)も未確認。
詳細は`Japanese_Equity_Lab/EDINET_SOURCE_ONBOARDING.md`に、
Confirmed/Unknown/Requires Local Validationへ分けて記録した
(Confirmedに昇格した項目は実質ゼロ)。

### 実装スコープの決定: Field Mapping/Normalizerは実装しない

上記の状況を踏まえ、`data-source-researcher`自身の明示的な推奨
(「この報告内容をEDINET Adapter/Normalizer実装の根拠にすべきではない」)
に従い、**Phase4B-2ではEDINET専用のNormalizer・DocumentKindマッピング・
Form Codeマッピング・Entity解決・PIT Field Mapping(market_public_at/
provider_available_atへの反映)を一切実装しない**ことを決定した。これは
「未確認のProvider仕様を推測で埋めない」という本Lab全体の原則
(ルートCLAUDE.md・Japanese_Equity_Lab/CLAUDE.md共通)を、情報源が
実際に相互矛盾していた今回のケースで特に厳格に適用した結果である。

一方で、Phase4Aの`JQuantsAdapter`が「ユーザー明示のCanonical
Specification(未検証)に基づくRaw Fetch実装 → 後日ローカル環境で
実データ確認 → Field名を確定」という手順を踏んだ前例に倣い、
**Raw HTTP Fetchのみ**を提供する`lib.disclosures.providers.edinet.
EdinetAdapter`を実装した:

- `fetch_documents_list_raw(target_date, list_type=2)`:
  Documents List APIの候補パラメータ(`date`/`type`)でRaw JSONを取得する
  のみ。日付範囲・銘柄コードによるクエリ対応は未確認のため、そのような
  引数は意図的に持たせていない。
- `fetch_document_raw(source_document_id, *, download_type)`:
  Document Download APIのスモークテスト用。`download_type`
  (`type`パラメータ)は情報源間で矛盾する値しか無いため**既定値を
  持たせず**、呼び出し側に明示的な選択を強制する。レスポンスは
  バイナリと想定されるため、Base64エンコードして
  `lib.snapshot.RawSnapshotStore`(JSON保存)と互換な形で保持する
  (Byte-for-Byteの往復整合性はTestで確認)。
- 認証方式は`auth_style`引数(`"query_param"`/`"header"`)で明示的に
  選択できるようにし、どちらが正しいかは未確定であることをDocstringで
  明記した。
- `RawFetchResult.request_parameters`(Snapshotへそのまま記録される側)
  には認証方式にかかわらずAPIキーを一切含めない設計とし、Testで確認。
- `DisclosureDocument`/`DocumentKind`/`normalize`/`view`のいずれも
  importしないことを構造的にTestで確認(未確認Field名が正規化ロジックへ
  混入する経路自体が存在しないことを保証)。

### Source Catalog登録

`lib.disclosures.catalog.build_edinet_dataset_descriptor()`を新設し、
`implementation_status=NOT_IMPLEMENTED`(`SKELETON`ではない — Raw Fetch
用のコードは存在するが、対象Field名・Query仕様自体が未確認のため、
「実仕様に基づく骨格」とは言えない)、`authority_class=PRIMARY_OFFICIAL`、
`pit_available=False`として登録した。`originating_source=
delivery_provider="EDINET"`(直接接続、D0042のOrigin/Delivery分離を
踏襲)。`known_limitations`に`EDINET_SOURCE_ONBOARDING.md`参照を明記。
`disclosure_common_core`(Phase4B-1、Architecture自体のDescriptor)は
書き換えず、新規Descriptorとして追加した(既存Descriptor不変更の原則)。

### Entity Registry: コード変更不要と判断

`lib.sources.entity_registry.EntityIdentifierMapping.provider_
identifiers`は元々`Mapping[str, str]`の汎用設計で、Docstring自体が
`{"edinet": "E02166"}`のような形を例示していた。EDINETコード/secCode/
JCNをこのnamespace経由で登録する設計自体に新規コードは不要と判断した。
ただし、secCode形式がJ-Quantsの5桁ゼロパディング規約(D0039)と一致するか
未確認のため、実際のMapping登録(実際の値の投入)はローカル検証完了まで
行わない。

### ローカル検証手順

`local-validation` Skillの手順(A-I)に従い
`Japanese_Equity_Lab/EDINET_LOCAL_VALIDATION_GUIDE.md`を新設した。
git同期・`EDINET_API_KEY`有無確認(値非表示)・Documents List 1日分の
Smoke Test(両認証方式を順に試す)・Raw Snapshot保存・生JSON確認・
Offline再実行・期待される観測結果・貼り付けてよい/悪い内容、を明記した。
このPhaseの主目的はJ-Quants Phase3A/Phase4Aと異なり「既に実装した
Normalizerの実データ確認」ではなく「そもそもの仕様確認とField名の
発見」であるため、手順Eで実際に観測されたFieldをユーザーに報告して
もらうことを次のPhaseへのゲートとして明記した。

### Reviewer Findings(pit-auditor / skeptic-reviewer)

Phase4A.5/Phase4B-1に続き、両Subagentを今回も実運用した(§22の
Author/Reviewer分離Workflowを継続)。両Agentとも`.claude/agents/`の
Read-only Tool制限通り、コードを一切変更せずFindings Reportのみを
Main Claudeへ返した。

**pit-auditor**(5件、最高Severity MEDIUM):
1. [MEDIUM] `fetch_documents_list_raw`の`list_type=2`が暗黙の既定値を
   持ち、同じ確度で未確認な`fetch_document_raw`の`download_type`
   (既定値なし)と一貫しない。対応済み(下記)。
2. [MEDIUM] `pit_available=False`/`NOT_IMPLEMENTED`は`SourceCatalog`の
   どのコードからも読まれておらず、Runtime上の強制力を持たない
   Documentation専用のFlagである(Catalog全体に既存する設計上の制約で
   あり、本Phaseで新規導入した問題ではない)。今回のEDINETがPIT安全に
   見える実際の保護は、このFlagの値そのものではなく「EDINETデータから
   `DisclosureDocument`/`EvidenceRecord`を一切構築していない」という
   実装の不在によって成立している。既知の制約として明示的に受け入れ、
   Test(`test_edinet_pit_available_false_is_documentation_only_not_
   a_runtime_gate`)で回帰確認できるようにした。
3. [LOW] `raise ... from None`は`__suppress_context__`を立てるのみで、
   捕捉した例外オブジェクト(query_param認証方式ではAPIキーを含む
   URLを保持しうる)が新しい例外の`__context__`から依然参照可能なままに
   なる。`raise`文を`except`節の外側へ移動する形に修正し、
   `__context__`自体が`None`になることまでTestで確認するよう強化した。
4. [LOW] `test_edinet_known_limitations_references_onboarding_report`
   が文字列存在のみを確認する弱いTestだった。実際に未確認と判定された
   具体的項目名(`EGRESS_BLOCKED`/`submitDateTime`/`secCode`)を含む
   ことまで確認するよう強化した。
5. [LOW] `test_edinet_adapter_default_auth_style_is_query_param`が
   private属性(`_auth_style`)への直接assertで、`_request()`が既定値を
   無視するBugを検知できなかった。実際のHTTPリクエスト内容(`session.
   calls`)を確認する形へ書き換えた。

**skeptic-reviewer**(4件、最高Severity MEDIUM、総合`PASS_WITH_CONCERNS`):
1. [MEDIUM] `EDINET_SOURCE_ONBOARDING.md`のBottom Lineは
   「現時点の情報を**EDINETアダプタ**/Normalizerを書く根拠として使用
   すべきではない」と明記していた(「Normalizer」だけでなく「アダプタ」
   とも明記)。それにもかかわらず`EdinetAdapter`というAdapterを実装した
   ことは、この推奨を額面通りには守っていない。**この点を直接認める**:
   本Decisionが実際に踏んだ線引きは「Field-level Semanticsを持つ
   Adapter/Normalizer(=Providerの意味論を推測で埋める必要があるもの)を
   書かない」であり、「Raw HTTP Fetch(=Providerの意味論に一切依存せず、
   確認された既存Infrastructure(`RawSnapshotStore`)へそのまま渡すだけの
   コード)まで一律禁止する」ことまでは意図していなかった、という
   Main Claude側の解釈である。`data-source-researcher`自身の報告文は
   「アダプタ」を無限定に使っており、この解釈を明示的に是認したもの
   ではない。実際に生じている実害(未確認Field意味論が`DisclosureDocument`
   /PIT/Entity Registryへ混入すること)がStructural Test(`test_edinet_
   adapter_module_does_not_import_disclosures_normalize_or_view`)で
   構造的に防がれていることは事実だが、これは「推奨の文言を狭く解釈した
   ことの正当化」であって「推奨と矛盾しないことの証明」ではない、という
   Reviewerの指摘を正しいものとして記録する。今後、同種の状況
   (Onboarding Reportが「Adapterを書くな」と明確に述べた場合)では、
   Raw Fetchのみであっても実装に進む前に、この線引きの是非をユーザーへ
   明示的に確認することを今後の運用上の注意点とする(本Phaseでは
   実装後に気づいたため、事後にこの形で記録するに留める)。
2. [MEDIUM] pit-auditor Finding 1と同一の指摘(`list_type`の暗黙の既定値
   が`download_type`との一貫性を欠く)。両Reviewerが独立に同じ問題を
   検出したことは、この不整合が実際に目につきやすいものであったことの
   傍証と捉え、優先して対応した(下記)。
3. [LOW] `EDINET_API_KEY`がリポジトリルートの`.env.example`に追加されて
   いなかった(既存の`JQUANTS_API_KEY`等と並べる既存Discoverabilityの
   慣行から外れていた)。対応済み(下記)。
4. [LOW] Reviewer自身がRead-only Tool制限のため`git diff`を実行できず、
   `core`/`app.py`/`tests/`無変更の主張を`Grep`による代替確認に留めた、
   というReviewer側の制約の記録(Main Claude側でのFinding対応は不要、
   Main Claude自身が別途`git diff --stat`で確認済み)。

**対応**:
- `list_type`の既定値を削除(`download_type`と同じく必須Keyword-only
  引数化)。全呼び出し箇所(Test・`EDINET_LOCAL_VALIDATION_GUIDE.md`)を
  明示的な`list_type=2`指定に更新。新規Test
  (`test_fetch_documents_list_raw_requires_explicit_list_type`)追加。
- `_request()`の例外送出を`except`節の外側へ移動し、`__context__`が
  実際に`None`になることを確認するTestへ強化。
- `.env.example`へ`EDINET_API_KEY`エントリを追加(値取得元は
  `EDINET_SOURCE_ONBOARDING.md`/`EDINET_LOCAL_VALIDATION_GUIDE.md`参照
  で未確認である旨を明記)。
- 弱いTest2件(`known_limitations`文字列存在チェック、private属性への
  直接assert)を強化。
- `pit_available`がDocumentation専用でRuntime強制力を持たないことを
  明示するTestを新規追加。
- skeptic-reviewer Finding 1(「アダプタを書くな」推奨の文言と実装の
  乖離)は、コード変更ではなくこのDecisionへの明示的な記録という形で
  対応した(上記)。

再Reviewは実施していない(全Findingが局所的なTest強化・既定値削除・
例外Chain修正・Documentation追記で解消可能な性質であり、Severity上限
MEDIUMはいずれもField-level Semanticsの混入(このPhaseが最も警戒すべき
リスク)には至っていないため)。

**最終回帰確認**(全Finding対応後): `pytest`(Lab 384件・既存Screening
Tool 37件)・`ruff check`・`ruff format --check`・`mypy`(77ファイル)
いずれもclean。`git diff --stat -- core/ app.py tests/`で変更が無いことを
再確認済み。

### このDecisionでやらないこと

EDINET専用Normalizer・DocumentKind/Form Codeマッピング・Entity Mapping
の実値投入・Document Download本文の解析・XBRL/PDFパース・LLM要約・
Event抽出・Buy/Sell判断・Strategy変更・Backtest条件変更・Screening Tool
変更・TDnet(Phase4B-3)には着手していない。

## D0046 追記 — Phase4B-2: Local Real Data Validation結果の反映、正式実装

2026-08-17、ユーザーが`EDINET_LOCAL_VALIDATION_GUIDE.md`の手順に従い
ローカル環境から実際にEDINET API V2へ接続し、Documents List・Document
Downloadの実疎通・実Field構造を確認した(`EDINET_SOURCE_ONBOARDING.md`
「追記」参照)。以下、確認内容と、それに基づく実装変更を記録する。

### Confirmed By Official Spec(ユーザーがローカル環境で参照した公式仕様書)

**skeptic-reviewer Finding(このFinding自体への対応として本節末尾に追記)**:
「Confirmed By Official Spec」という区分は、D0043のLocal Real Data
Validation(実際のHTTP応答という再現可能な一次証拠)と同列に扱うには
確度が弱い — ユーザーが一度読んだ文書の記述の要約であり、この
Session/Repository自身が参照した仕様書の正確な版・URLを特定できていない
(`EDINET_SOURCE_ONBOARDING.md`が指摘した2024年7月版/2026年6月版のいずれか
不明)。特にDocument Downloadの`type`値は、実際にDownloadして観測したのは
`type=1`のみで、`type=2〜5`は仕様書の記述をそのまま反映したに過ぎない
(下記「Confirmed By Local Observation」との違いに注意)。誤った対応関係が
あっても、現在の成功判定(Content-Type Allowlist)はそれを検知できない。
`lib.disclosures.providers.edinet.EdinetDownloadType`のDocstring・
`build_edinet_dataset_descriptor()`の`known_limitations`へ、この区別を
明示した(`OBSERVED` vs `SPEC_CLAIM_ONLY`)。

- Document Downloadの`type`パラメータ: `1`=提出本文書及び監査報告書
  (ZIP、**OBSERVED**)、`2`=PDF、`3`=代替書面・添付文書(ZIP)、
  `4`=英文ファイル(ZIP)、`5`=CSV(ZIP)(`2`〜`5`は**SPEC_CLAIM_ONLY**、
  未Download確認)。ZIP成功時`Content-Type: application/octet-stream`、
  PDF成功時`Content-Type: application/pdf`、失敗時
  `Content-Type: application/json; charset=utf-8`。
- `withdrawalStatus`("0"=その他/"1"=取下書/"2"=取り下げられた書類)・
  `docInfoEditStatus`("0"=その他/"1"=財務局職員が修正した情報/"2"=修正
  された書類)・`disclosureStatus`("0"=その他/"1"=不開示開始情報/
  "2"=不開示中書類/"3"=不開示解除情報)・`legalStatus`("0"=閲覧期間満了等/
  "1"=縦覧中/"2"=延長期間中)の正式な列挙値。
- `submitDateTime`(提出日時)・`opeDateTime`(財務局職員による書類情報
  修正・不開示・磁気ディスク提出・紙面提出等の操作日時)・
  `processDateTime`(Documents List自体の更新日時、Document公開日時では
  ない)の区別。日時はJapan time。
- 「訂正」(提出者が新しい書類管理番号で訂正報告書を提出)と「書類情報
  修正」(財務局職員がHeader等を修正、書類管理番号は不変)は別概念。
  `parentDocID`の存在だけから`CORRECTS`を推論しない方針を維持。
- **過去日付のDocuments Listは日次更新され、縦覧期間満了・取下げ・書類
  情報修正により後から書き換わる**(最重要の発見、下記「Critical PIT
  Finding」参照)。

### Confirmed By Local Observation(実際に観測)

- `Subscription-Key`クエリパラメータ認証: 成功。
- Documents List: `date=2024-05-08&type=2` →
  `metadata.status="200"`・`metadata.message="OK"`・
  `metadata.resultset.count=239`。実Field一覧(`seqNumber`/`docID`/
  `edinetCode`/`secCode`/`JCN`/`filerName`/`fundCode`/`ordinanceCode`/
  `formCode`/`docTypeCode`/`periodStart`/`periodEnd`/`submitDateTime`/
  `docDescription`/`issuerEdinetCode`/`subjectEdinetCode`/
  `subsidiaryEdinetCode`/`currentReportReason`/`parentDocID`/
  `opeDateTime`/`withdrawalStatus`/`docInfoEditStatus`/
  `disclosureStatus`/`xbrlFlag`/`pdfFlag`/`attachDocFlag`/
  `englishDocFlag`/`csvFlag`/`legalStatus`)を確認。
- Document Download: `docID=S100TD9S`、`type=1` →
  `Content-Type: application/octet-stream`、`byte_length=16397`、
  `sha256=2515dd689d673c9dbd32148b5450fc34f0aa0ddd7ba8831f5e5c08067b2a4d1c`、
  magic bytes `50 4b 03 04`(ZIP)。公式仕様と一致。
- `secCode`実例: 7203(Toyota)で`"72030"`(5桁string)。
- `withdrawalStatus="0"`/`docInfoEditStatus="0"`/`disclosureStatus="0"`/
  `xbrlFlag="1"`/`pdfFlag="1"`/`attachDocFlag="0"`/`englishDocFlag="0"`/
  `csvFlag="1"`/`legalStatus="1"`等、いずれも文字列型であることを確認
  (Python truthinessの罠、`bool("0")==True`を再び回避する必要がある
  ことの直接的な確認)。
- `docID`のみ存在し他の多くのFieldがnullになったRecordを確認(縦覧期間
  満了・取下げ等)。
- 大量保有報告書で`filer(提出者) != issuer(発行会社)`の実例を確認。
- `docTypeCode`の実例(`"140"`=四半期報告書、`"135"`=確認書、
  `"180"`=臨時報告書、`"350"`=大量保有/変更報告、`"150"`=訂正四半期
  報告書、`"236"`=訂正内部統制報告書等)を、`docDescription`という
  Local観測時の説明文から間接的に確認。**ただしこれを根拠に
  `DocumentKind`へMappingすることはしない**(下記参照)。

### Critical Fix: HTTP 200 + `metadata.status`エラー表現の検知漏れ

Local Validation中、EDINET APIが認証失敗時(`StatusCode=401`相当)にも
HTTP 200を返し、実際のStatusを`metadata.status="401"`という形でJSON
Body内に埋め込むことが判明した。既存`EdinetAdapter`は
`requests.Response.raise_for_status()`(Transport層のHTTP 4xx/5xxのみ
検知)にしか依存しておらず、この種のApplication層エラーを検知できず、
Smoke Testが`SUCCESS`と誤表示していた。

**修正**: `fetch_documents_list_raw()`は(1) HTTP成功、(2) JSONとして
解釈可能、(3) `metadata.status == "200"`、(4) `results`がlistとして
存在、の4条件すべてを満たす場合のみ成功とし、いずれかを満たさない場合
`EdinetApiError`(新設、`DataSourceError`のサブクラス)を送出する。
`fetch_document_raw()`は(1) HTTP成功、(2) Content-Typeが
`{application/octet-stream, application/pdf}`のいずれか(Allowlist方式)、
の2条件を満たす場合のみ成功とし、`application/json`系Content-Typeは
エラーBodyとみなして`EdinetApiError`を送出、それ以外の未知Content-Type
もfail closedで拒否する。エラーメッセージには`metadata.status`/
`metadata.message`のみを含め、APIキーやRequest URLは含めない
(`_safe_error_message()`)。

### 実装スコープの拡張: Raw Fetchのみ → Normalizer実装

前回のD0046(本文冒頭)時点では、Field名・意味論が確認できなかったため
Normalizer実装を見送っていたが、上記のLocal Real Data Validationにより
確認できたField(§上記)についてのみ、`lib.disclosures.providers.
edinet_normalize`を新設して実装した。この際、以下の設計判断を行った:

**Provider-neutral Common Coreへは含めないEDINET固有情報**:
`DisclosureDocument`(Phase4B-1のProvider-neutral Schema)へEDINET固有の
Field名を持ち込まず、`EdinetDocumentMetadata`という別Dataclassへ保持し、
`document_internal_id`経由で対応付ける。理由: TDnet/Company IR接続時に
同じField名の衝突・混同を避けるため(Phase4B-1の原則をそのまま踏襲)。

**`market_public_at`/`provider_available_at`への自動反映はしない**:
`submitDateTime`が「提出日時」であることは公式仕様で確認したが、それが
市場が実際に知りえた時刻(Market Public)と一致する保証、あるいは
EDINET APIでの反映Timing(Provider Available)を示す保証はいずれも
未確認。`submitDateTime`のParse結果は`EdinetDocumentMetadata.
submitted_at`という別名で保持し、Common CoreのPIT Fieldは`None`/
`AvailabilityBasis.UNKNOWN`のまま残す。EDINET公式FAQで「開示とAPI反映
には通常1分程度の時間差があり解消される」との言及があるとのユーザー
情報提供があったが、この「1分」を機械的にhistorical provider_
available_atとして加算することは明示的に禁止する(D0043のOfficial FAQ
非機械的Anchor化の原則と同じ)。

**`document_kind`は常にUNKNOWN(このPhaseではMappingしない)**:
`docTypeCode`の意味はLocal観測時の`docDescription`という説明文から
間接的に読み取れたに過ぎず、公式別紙1(Form Code List)そのものは未確認。
Local Descriptionだけからの推測Mappingは、本Labが一貫して禁止している
Substring Heuristicと同じ危険性を持つ(「説明文にそれらしい文字列が
含まれるから」という理由でCodeの意味を決めることになる)。`doc_type_code`
はRaw値のまま`EdinetDocumentMetadata`へ保持し、将来公式Code Listが
確認できた時点で明示的Mapping Tableを追加する。

**`entity_id`は常にNone(Role-aware Entity Mappingは未実装)**:
`secCode`はFiler(提出者)の証券コードであり、大量保有報告書等では
`issuerEdinetCode`(発行会社)・`subjectEdinetCode`(公開買付対象)が
別に存在する(Local実データで`filer != issuer`を確認済み)。単一の
`entity_id`へ機械的に決め打ちすると誤ったRole混同を招くため、
`DisclosureDocument.entity_id`は常に`None`のままとし、Role別の識別子
(`filer_edinet_code`/`filer_sec_code`/`issuer_edinet_code`/
`subject_edinet_code`/`subsidiary_edinet_code`)は`EdinetDocumentMetadata`
の個別Fieldへ保持する。`lib.sources.entity_registry.
EntityIdentifierMapping.provider_identifiers`は元々`{"edinet": "E02166"}`
のような形を想定した汎用設計であり、正式なEntity Registry統合(実際の
Mapping登録)自体にコード変更は不要と判断したが、`secCode`形式が
J-Quantsの5桁ゼロパディング規約(D0039)と一致するかは別途確認が必要
なため、実際の値投入は将来Phaseへ据え置く。

**"0"/"1" Flag・Multi-state Lifecycle Statusの型安全なParse**:
`xbrlFlag`等5つのFlagは文字列`"0"`/`"1"`のみを明示的Literalとして受理し
(`bool("0")==True`という既知のPython truthinessの罠、D0043/D0045と
同じパターンをここでも回避)、`None`(欠損)は`None`のまま保持し`False`
へ変換しない。`withdrawalStatus`等4つのLifecycle Statusは、Booleanへ
落とさずTyped StrEnum(`EdinetWithdrawalStatus`等)として保持し、
未知の非null値は各EnumのUNKNOWNメンバーへfail closedする(警告ログ
付き)。**Fieldが欠損/null(`raw is None`)の場合は`None`を返し、
UNKNOWNメンバーとは区別する** — 「値が無いこと」と「値はあるが認識
できないこと」は異なる情報であり、混同しない(D0046 §13 Null
Semanticsの直接的な実装)。

### Critical PIT Finding: Historical List Is Mutable

**最重要の発見**。EDINET公式仕様では、過去分Documents Listは日次更新
され、過去の日付のFileも差し替えられる。閲覧期間満了・withdrawal・
non-disclosure・document information editによって、過去File Dateの
Record自体が後から更新される(例: 閲覧期間満了後、`docID`等以外がnull
へ更新される。取下げ後にも過去Recordが更新される)。

したがって、**`date=2024-05-08`を2026年に取得することは、2024-05-08
時点で実際に観測可能だったDocuments Listと同一である保証がない**。
これは通常のLook-ahead Bias(未来の情報が見えてしまう)とは異なる種類
のリスクであり、過去日付を指定して取得しているにもかかわらず、その
中身自体が「現在」の状態を反映してしまう。

現在取得したHistorical Listを使って「2024-05-08時点で市場が知っていた
EDINET universe」を完全再現できると主張することを明示的に禁止する。
Historical BacktestでのEDINET metadata利用には、(A) 当時取得・保存した
Immutable Snapshot、または(B) Historical Point-in-Time Snapshotを保証
するSourceが必要である。今後の運用では、日次/定期的にEDINET Documents
ListをRaw保存するForward Collection Architecture(継続的なSnapshot
蓄積)を検討できるが、このPhaseではSchedulerを実装しない。

この原則は`DISCLOSURE_ARCHITECTURE.md`「Historical List Is Mutable」
セクションへ、EDINETに限らずDisclosure Source全般に適用しうる一般原則
として記録した。

### Source Catalog更新

`build_edinet_dataset_descriptor()`の`implementation_status`を
`NOT_IMPLEMENTED`から`CONNECTED`へ更新した(実際に接続・Parseできる
ことを確認したため)。ただし`pit_available`は`False`のまま — 「取得
できる」ことと「PIT安全なAs-of Viewを提供できる」ことは別であり、後者
はまだ達成していない(`market_public_at`/`provider_available_at`は
依然`UNKNOWN`のまま)。

### Reviewer Findings(pit-auditor / skeptic-reviewer)

両Subagentを実運用した(§21で指定された重点項目に沿って)。

**pit-auditor**: `PIT AUDIT: CLEAN`。指定された6項目(Historical list
mutation、submitDateTime誤用、processDateTime誤用、Retroactive
withdrawal/nullified records、filer/issuer mapping、availability
fallback)すべてPASS、加えて今回のCritical Fix(HTTP 200 +
metadata.statusエラー検知)自体もTestが実際にその経路を演習している
ことをコード読解で確認(Tautologicalでない)。[LOW]1件: 既存(この
Round非対象)の`disclosure_document_to_evidence()`の`available_at =
market_public_at or retrieved_at`Fallbackは、将来EDINET Documentを
このEvidence変換経路へ直接(disclosures_as_of()を経由せず)投入した
場合にPIT-unsafeになりうるという既知の注意喚起(Phase4B-1から継続、
今回変更なし、対応不要)。

**skeptic-reviewer**: `PASS_WITH_CONCERNS`。[MEDIUM]2件、[LOW]2件、
[LOW/procedural]1件:
1. [MEDIUM]「Confirmed By Official Spec」の確度がD0043のLocal Real
   Data Validationと同列に扱うには弱く、特に`EdinetDownloadType`の
   `type=2〜5`は未Download確認のまま。**対応済み**(上記「Confirmed By
   Official Spec」節・`EdinetDownloadType`Docstring・Catalog
   `known_limitations`へOBSERVED/SPEC_CLAIM_ONLYの区別を明示)。
2. [MEDIUM] `test_edinet_pit_available_false_is_documentation_only_
   not_a_runtime_gate`のDocstringが「DisclosureDocument/EvidenceRecord
   を一切構築していない」という、`edinet_normalize.py`追加により事実と
   異なる説明をそのまま残していた。**対応済み**(Docstringを修正し、
   実際の保護機構(`AvailabilityBasis.UNKNOWN` + `disclosures_as_of()`
   のNoneタイムスタンプ除外)を明示する新規Test`test_edinet_pit_
   safety_comes_from_availability_basis_unknown_not_from_no_
   construction`を追加)。
3. [LOW] Catalogの`known_limitations`がValidationのSample Size(1日分・
   1文書のみ)を明示していなかった。**対応済み**(上記の通り追記)。
4. [LOW] `docDescription`欠損時のTitle Placeholder
   (`f"[EDINET docID=...: docDescription unavailable]"`)は、機械的に
   「合成された値」と判別できるStructural Signalを持たない(文字列の
   見た目のみ)。現時点でEDINET Documentを`disclosure_document_to_
   evidence()`等の実運用経路へ投入する呼び出し元は存在しないため、
   実害はまだ無い(skeptic-reviewer自身もSeverity LOW・将来のDesign
   Hygiene注意として位置づけ)。**対応**: コード変更はせず(呼び出し元が
   存在しない段階での構造追加は過剰実装と判断)、このDecisionへ既知の
   制約として明示的に記録するに留める。EDINET Documentを実際にEvidence
   Pipelineへ接続する将来Phaseで、このPlaceholder Titleを機械的に
   識別する必要が生じた場合は、Boolean Field(例: `title_is_
   placeholder`)の追加を検討すること。
5. [LOW/procedural] skeptic-reviewer自身はBash Toolを持たずgit diffを
   実行できなかった(内容Grepでの代替確認のみ)。Main Claude側で別途
   `git diff --stat -- core/ app.py tests/`を実行し空であることを確認
   済み(下記「最終回帰確認」)。

再Reviewは実施していない(全Finding対応がDocstring修正・known_
limitations追記・Test追加という局所的な変更で完結し、Field-level
Semantics自体への変更を伴わないため)。

### 最終回帰確認

(全Finding対応後): `pytest`(Lab 429件・既存Screening Tool 37件)・
`ruff check`・`ruff format --check`・`mypy`(78ファイル)いずれもclean。
`git diff --stat -- core/ app.py tests/`で変更が無いことを再確認済み。

### このDecisionでやらないこと

XBRL本文Parse・ZIP展開・財務抽出・PDF Parse・LLM本文解釈・大量保有分析・
Event Extraction・Buy/Sell判断・Strategy変更・Backtest条件変更・
Screening Tool変更・TDnet(Phase4B-3)には着手していない。

## D0046 追記2 — Phase4B-2: Document Download再取得の非決定性、Raw Artifact Identity != Document Content Identity

### A. Real Observation

同一`docID=S100TD9S`・同一`download_type=1`を2回Downloadしたところ:

- Outer ZIP SHA-256: OLD
  `2515dd689d673c9dbd32148b5450fc34f0aa0ddd7ba8831f5e5c08067b2a4d1c`、
  NEW `2a30a239deeb2beeb477443f645a2a6ea1202da813190491a507889a24d98db6`
  (Outer bytes identical = False)。
- ZIP内部比較: same member names = True、全member size一致、全member
  CRC一致、全member content SHA-256一致。
- 唯一の差: ZIP Member自体のTimestamp(OLD `2026-08-17 21:56:12` /
  NEW `2026-08-17 22:33:08`、全memberで同一Pattern)。

**原因は`OBSERVED_BEHAVIOR`として記録し、断定しない**(「EDINETが必ず
取得時刻をZIP Timestampとして再生成している」という未確認の説明を
公式仕様であるかのように書かない)。Confirmed Factは: 「same document
retrieval → outer ZIP bytes/hash changed → member contents unchanged
→ ZIP member timestamps changed」まで。

### B. Raw vs Canonical Hash設計

`lib.disclosures.providers.edinet.EdinetAdapter.fetch_document_raw()`の
Payload Fieldを`content_sha256`から`raw_retrieval_hash`へRename した
(意味を正確に表す名前へ変更、「今回のRetrievalで実際に返ってきたRaw
bytesそのもの」のHashであり、Document Content Identityではないことを
名前自体で示す)。

新設`lib.disclosures.providers.edinet_zip.compute_canonical_zip_content_hash()`:
ZIP Container Metadata(Timestamp・圧縮方式・Member順序)を除外し、
各Member(Directory Entryを除く)の`filename`・`byte length`・
`SHA-256(member raw content)`をfilenameでSortしてDeterministicに
直列化し、その全体のSHA-256を計算する。ZIP展開先へのDisk書き出しは
行わない(メモリ上でのみ読み取る)。

**A. raw_retrieval_hash**(`EdinetAdapter`が計算): Provenance・Snapshot
Integrity・「このRetrievalで実際に取得したArtifactそのもの」の識別に
使う。同じdocIDでもRetrievalごとに変わりうる。

**B. canonical_content_hash**(`edinet_zip`が計算、呼び出し側が必要な
時に別途実行): 実Document Content Identity比較に使う。Container
Metadataに依存しない。

### C. Duplicate Semantics

`lib.disclosures.model.DuplicateRelationKind`(Phase4B-1のCommon Core、
Documents ListのJSON行全体Hashを対象とする既存機能)は**このPhaseでは
変更しない**(既存Common Coreを壊さない最小変更を優先する、ユーザー
指示通り)。Outer ZIP Hash不一致は「Document内容が変わった」ことを
意味せず、Outer ZIP Hash一致は「同じRetrieval Bytes」を、Canonical
Content Hash一致は「同じ抽出済みMember内容」を意味する、という3種類の
判定を明確に区別する。将来、Container形式のAttachmentに対する正式な
Dedup/Relationship Modelingが必要になった時点で、
`EXACT_RAW_ARTIFACT_DUPLICATE`/`EXACT_CANONICAL_CONTENT_DUPLICATE`の
ような概念分離を検討する(このPhaseでは導入しない)。

### D. Snapshot Behavior

`RawSnapshotStore`は既存のAppend-only設計(同一`snapshot_id`への上書き
拒否)をそのまま踏襲する — 新規コードは追加していない。同一docIDを
複数回Downloadして保存する場合は、`snapshot_id`にRetrieval時刻・連番を
含めることで別Artifactとして共存させる設計とし、`EDINET_LOCAL_
VALIDATION_GUIDE.md`のStep Dへその慣習を追記した。Canonical Content
Hashが一致する場合の`CONTENT_UNCHANGED`的なDerived Observationは、
このPhaseでは実装しない(Lifecycle/Event Inferenceを過度に増やさない、
ユーザー指示通り)。

### E. PIT / Revision Implication

Outer Raw Hashの変化だけで「Documentが訂正・改版・変更された」と判定
することを明示的に禁止する(`edinet_zip.py`が`DocumentRelationship`/
`DuplicateRelationKind`のいずれもImportしないことを構造Testで確認、
`test_edinet_zip_module_never_constructs_document_relationship`)。
今回の観測(Outer変化・Canonical不変)自体は、`document content change
evidence = NONE`として扱う(Canonical Content Hashが一致している限り、
内容変更の証拠は無い)。

### F. Safety(Canonical Hash生成時)

ZIP展開先へのDisk書き出しをしない(メモリ上のみ)、Path Traversal対策
(絶対Path・`..`セグメントをFail Closed)、Symlink等の特殊Entryを
Fail Closed、重複Filenameを明示的にFail Closed、Malformed ZIPを
Fail Closed、暗号化ZIP(General Purpose Bit Flag bit 0)をFail Closed。
HTML/XML/XBRL内部のWhitespace・Encoding・属性順序等のSemantic
Normalizationは一切行わない(Member Raw Bytesが異なればCanonical
Content Hashも異なる。意味的同一性判定は将来Phase)。

### G. Tests

`13_tests/test_edinet_zip_canonicalize.py`(18件): Local Observationの
直接再現(同一Member内容・異なるZIP Timestamp → Outer異なりCanonical
一致)、Member Content/Filename変更・追加・削除でCanonical Hashが変わる
こと、Member順序のみ変更・圧縮方式のみ変更ではCanonical Hashが変わら
ないこと、Malformed/重複Filename/Path Traversal/Symlink/暗号化ZIPが
それぞれFail Closedすること、Directory Entry除外、Offline再現性
(Pure Function)、Raw Bytes不変性、`DocumentRelationship`/
`DuplicateRelationKind`を一切Importしないことの構造確認。

### Reviewer Findings(pit-auditor / skeptic-reviewer)

両Subagentを、ユーザー指定の重点項目(同一docID再取得によるSnapshot
上書き・後続Retrievalによる過去Evidence書き換え・Raw Hashの訂正判定
流用/Canonicalizationによる実変更の隠蔽/安全でないZIP展開/Outer Hash
不一致=訂正という思い込み/都合の良いSynthetic Fixture)に沿って実運用
した。

**pit-auditor**: `PIT AUDIT: 2 FINDINGS`(最高Severity LOW)。指定3項目
(同一docID再取得によるSnapshot上書き、後続Retrievalによる過去Evidence
書き換え、Raw Hashの訂正判定流用)すべて実害無しと確認、加えて
`compute_canonical_zip_content_hash()`のOrder非依存性・Content感応性・
各Safety Check(Path Traversal/Symlink/暗号化/重複Filename/Malformed)が
Tautologicalでない実Fixtureで演習されていることも確認。
[LOW]1件: 「`DocumentRelationship`/`DuplicateRelationKind`を一切構築
しない」ことの構造Testが`edinet_zip.py`のみを対象としており、実際に
`raw_retrieval_hash`を所有する`edinet.py`自身・`edinet_normalize.py`は
対象外だった(Grepによる独立確認では現状漏れは無し)。**対応済み**
(下記)。[LOW]1件: 構造Testが文字列一致であり厳密なAST解析ではない
(現実的なEvasionリスクは低いとpit-auditor自身も評価、対応不要と判断)。

**skeptic-reviewer**: `PASS_WITH_CONCERNS`。[MEDIUM]3件、[LOW]1件、
[PASS]複数:
1. [MEDIUM] `_is_unsafe_member_name()`のPath Traversal対策がPOSIX形式
   (先頭`/`・`..`セグメント)のみを検知し、Windows Drive Letter絶対Path
   (`C:\...`)を検知できていなかった(Diskへ展開しない設計のため現在の
   実害は無いが、Docstring/DECISIONS.mdの「絶対Pathを拒否」という主張と
   実装が一致していなかった)。**対応済み**(下記)。
2. [MEDIUM] 展開後サイズの上限(Zip Bomb対策)が存在せず、「Safety」
   節の記述が完全な脅威網羅であるかのように読める一方、実際には
   メモリ枯渇への対策が欠けていた。**対応済み**(下記)。
3. [MEDIUM/LOW] `DISCLOSURE_ARCHITECTURE.md`の「それは単にRetrieval
   ごとのContainer側の差異である可能性が高く」という一文が、1件の
   観測から一般的な確率を主張しており、ユーザー自身の「原因を断定
   しない」という指示の精神からわずかに逸脱していた。**対応済み**
   (下記)。
4. [MEDIUM/LOW] 18件のTestはすべてSynthetic Fixture(`zipfile`モジュール
   で1から構築)であり、実際の観測されたOLD/NEW ZIP bytesに対して
   `compute_canonical_zip_content_hash()`を実行した結果(実Canonical
   Hash値)は記録されていない(実Bytes自体は§16の方針により保存して
   いないため、当然そのものは再現できない)。**対応**: 今回のRound
   ではコード変更・数値の捏造はせず、次回ユーザーが再度Local
   ValidationでEDINET Document Downloadを行う機会があれば、`compute_
   canonical_zip_content_hash()`を実際のBytesに対して実行し、結果の
   Hex Digestを(Byte列自体は保存せず)記録することを今後のFollow-up
   として明示する(このDecisionへの新規追記、コード変更は伴わない)。
5. [LOW] Serialization Scheme(`\x00`区切り)自体のCollision耐性は
   Reviewer自身が独立に追跡し、実際にはCollisionが起こりえないことを
   確認(Filename中の`\x00`はSafety Checkで既に拒否されているため)。
   ただし改行文字(`\n`/`\r`)はFilenameとして許容されたままだった
   (Collisionには寄与しないが、Hygiene上望ましくない)。**対応済み**
   (下記、Path Traversal対策と合わせて拒否)。
6. [PASS] Directory Entry除外・Member順序非依存・圧縮方式非依存・
   `core`/`app.py`/`tests/`無変更・`DuplicateRelationKind`無変更、
   いずれも確認。

**対応**:
- `_is_unsafe_member_name()`へWindows Drive Letter絶対Path検知
  (正規表現`^[A-Za-z]:[/\\]`)を追加。
- 改行文字(`\n`/`\r`)を含むFilenameもfail closedへ追加。
- 展開後サイズの上限(Member単体200MB・累計500MB、公式仕様上の上限は
  未確認のため安全側の暫定値と明記)を追加し、`zf.read()`を呼ぶ前に
  宣言サイズを検査してZip Bombをfail closedする設計にした。
- `DISCLOSURE_ARCHITECTURE.md`の該当箇所を、1件の観測から一般的確率を
  主張しない表現へ修正(「Canonical Hashを使うべき」という規範自体は
  論理的必然として維持しつつ、原因についての推測を含めない)。
- 新規Test6件追加: Windows Drive Letter絶対Path・改行含みFilename・
  裸の`..`Filenameのfail closed確認、Member単体/累計サイズ上限超過の
  fail closed確認、上限内であれば正常処理される確認、`edinet.py`/
  `edinet_normalize.py`を対象とした`DocumentRelationship`/
  `DuplicateRelationKind`非構築の構造確認(pit-auditor Finding対応)。

再Reviewは実施していない(全Findingが局所的なSafety Check追加・Test
追加・Documentation表現修正で完結し、Canonicalizationの基本設計
(Sort-by-filename・Content-hash直列化)自体には変更が無いため)。

### 最終回帰確認

(全Finding対応後): `pytest`(Lab 452件・既存Screening Tool 37件)・
`ruff check`・`ruff format --check`・`mypy`(79ファイル)いずれもclean。
`git diff --stat -- core/ app.py tests/`で変更が無いことを再確認済み。

### このDecisionでやらないこと

XBRL/PDF/HTML本文の意味解析・Semantic Normalization・`CONTENT_
UNCHANGED`等のDerived Event生成・`DuplicateRelationKind`のEnum拡張・
`DocumentRelationship`の自動生成・Buy/Sell判断・Strategy変更・
Backtest条件変更・Screening Tool変更・TDnet(Phase4B-3)には着手して
いない。

## D0047 — Phase4B-3: J-Quants TDnet Disclosure Integration(Onboarding調査が二重にブロック、Adapter/Normalizerは未実装のまま停止)

### §1 Source Onboarding調査: EDINET初回Round(D0046)よりさらに深刻なブロック

`data-source-researcher` Subagentによる、J-Quants API V2のTDnet/適時開示
情報Add-onに関する公式仕様調査を実施した。**結果はEDINET初回Roundより
一段severe**:

- 本セッションから`jpx-jquants.com`・`jpx.gitbook.io`のいずれへも一切
  接続できず(`WebFetch`は`EGRESS_BLOCKED`)、得られた情報はすべて
  `WebSearch`の合成Snippetのみに基づく`SEARCH-SNIPPET-DERIVED
  (UNVERIFIED)`だった。
- **Main Claude自身によるcurlでの独立検証**(Subagent報告を鵜呑みに
  しない、D0046と同じ方針): `curl https://jpx-jquants.com/...`および
  `curl https://jpx.gitbook.io/...`はいずれも`CONNECT tunnel failed,
  response 403`。EDINET(FSA)と同種のEgressブロックが、J-Quants
  ドキュメント側にも及んでいることを確認。
- タスク上**最重要の2項目**がいずれも裏付けゼロだった:
  1. `DiscStatus`/`RevNo`の訂正・削除意味論(「Title訂正が反映され
     ない」「削除された開示も返り続ける」「`DiscStatus`は常にnull」
     「`RevNo`は常に1」という報告があるが、いずれも一次資料での
     確認が取れていない)。
  2. `DiscDate`/`DiscTime`が`market_public_at`として使える意味論を
     持つかどうか。
- **新たに判明したリスク**: WebSearch結果が「J-Quants API」(個人向け、
  今回の対象)と「J-Quants Pro」(法人向け、無関係な別契約・別Document
  Tree)を混同していた可能性がある。これにより、候補として得られた
  Endpoint名(`/v2/td/list`・`/v2/td/files`・`/v2/td/bulk`)自体が
  どちらの製品に属するかすら確定できない。`data-source-researcher`の
  検索Queryが調査対象のField/Endpoint名自体を含んでいたため、返って
  きた「確認」がQuery自体のEchoに過ぎない可能性がある(確認バイアス
  リスクとして明示的に記録)。

詳細は`Japanese_Equity_Lab/TDNET_SOURCE_ONBOARDING.md`に、EDINET版と
同じConfirmed-by-Official-Spec/Confirmed-by-Local-Observation/Unknown
の区分で記録した(Confirmedに昇格した項目は実質ゼロ、Bottom Lineで
「この報告書をTDnet Adapter/Normalizer実装の根拠として使用すべきで
ない」と明記)。

### §2 実装スコープの決定: EDINET初回Roundよりさらに保守的

上記の複合的な不確実性(公式資料アクセス不可 + 最重要2項目の裏付け
ゼロ + 製品帰属不明)を踏まえ、`data-source-researcher`自身の明示的な
推奨に従い、**Phase4B-3では`lib/disclosures/providers/tdnet.py`
(Adapter/Normalizer)を一切実装しない**ことを決定した。

これはEDINET初回Round(D0046)の判断よりさらに保守的である。EDINET
初回RoundではField名の裏付けは弱いながらも複数の断片的な情報源が
存在し、Raw HTTP Fetch専用の`EdinetAdapter`(Field Mappingを一切
行わない)を実装できた。今回のTDnetでは、それを上回る不確実性
(タスク上最重要項目の裏付けがゼロ、かつEndpoint名の製品帰属自体が
不確実)に直面したため、Raw Fetch用のコードさえ書かないという判断を
下した。**未確認のProvider仕様を推測で埋めない**という本Lab全体の
原則(ルートCLAUDE.md・Japanese_Equity_Lab/CLAUDE.md共通)を、EDINET
より厳格な状況へ厳格に適用した結果であり、Phase4B-3の進め方を
機械的にEDINETの前例通りに反復したわけではない。

このPhaseで実装したのは以下の3点のみ:

1. `lib.disclosures.catalog.build_tdnet_dataset_descriptor()`:
   `implementation_status=NOT_IMPLEMENTED`・`pit_available=False`で
   Source Catalogへ登録。`known_limitations`に上記の未確認項目を
   具体名で記録(`DiscStatus`/`DiscDate`/`DiscTime`等)。
2. `lib.disclosures.providers.tdnet_cursor.TdnetRetrievalCursorState`:
   将来Adapterを実装する際に「CursorをDocument Timestampと混同
   しない」設計を先に固定するための、純粋なArchitecture骨格(実
   Endpoint呼び出しは一切行わない)。`DisclosureDocument`/
   `AvailabilityBasis`のいずれもImportしないことを構造Testで確認。
3. `TDNET_ARCHITECTURE.md`: 実装前に固定しておくべき設計原則の文書化
   (下記§3参照、Field名の推測は一切含まない)。

### §3 ユーザー追加指示(Safety Corrections)の統合

Phase4B-3本体の指示の途中で、以下8点の追加Safety Correctionsが提示され、
すべて`TDNET_ARCHITECTURE.md`へ反映した:

- **三層分離**: `publishing_entity`(発行体)/`disclosure_system`
  (TDnet、Venue)/`delivery_provider`(J-Quants API)。D0042の
  Origin/Delivery分離をさらに1段細分化したもの。J-Quantsが観測した
  状態を、TDnet Venue上の現在の権威ある状態と同一視することを明示的に
  禁止(`DISCLOSURE_ARCHITECTURE.md`へも一般原則として追記)。EDINETの
  ように`disclosure_system`(Venue)と`delivery_provider`(配信経路)が
  同一主体(FSA)である場合は、この2つのみがcollapseして引き続き2層
  (`originating_source=delivery_provider="EDINET"`)のままで良い —
  ただし`publishing_entity`(上場会社自身、`entity_id`)は常に別軸の
  ままであり(EDINETでも`entity_id`は未解決のまま、D0046)、2層への
  収束は発行体識別の解決を意味しない。この一般原則は現時点でTDnetという
  単一の未確認事例のみに基づくため、別Sourceでの検証を待って一般性を
  再確認する必要がある(pit-auditor Finding対応、下記§5参照)。
- **Provider宣言Schema vs 現在の実装挙動**: `DiscStatus`/`RevNo`等に
  ついて、公式仕様が定義する値の範囲(Schema)と、実際に観測される
  Runtime挙動(Current Implementation Behavior)を別々に文書化する
  方針。将来Normalizer実装時は`provider_schema_version`/
  `normalizer_version`/`observed_behavior_documented_at`で
  Schema Evolutionを追跡し、Providerの実装が将来変わっても過去の
  正規化済みRecordをSilentに遡及的再解釈しない。
- **Historical Market Time vs Historical Provider Time**の再確認
  (D0043/D0045からの継続): 今日取得したBulk/List Dataから過去の
  `provider_available_at`を復元することを禁止。
- **CursorはRetrieval Stateのまま**: Timestampのいずれでもなく、
  Decodeできたとしてもそこから可用性Timestampを推測しない。
  `pagination_key`とも別概念として扱う。
- **Ephemeral File URL Safety**: `/td/files`・`/td/bulk`のDownload
  URLを`canonical_source_locator`/`permanent_attachment_url`として
  長期保存しない。長期Provenanceの中心はURLではなくdiscNo相当識別子・
  Role・Provider名・`retrieved_at`・Raw Hash・Snapshot Referenceとする。
  Offline ReplayはURL無しで成立する設計を継続する(D0042 Offline原則)。
- **Document Classification != Event Interpretation**の再確認
  (Phase4B-1の「Document != Event != Claim」原則の継続): `DiscItems`
  からRevision方向・Catalog極性・BUY/SELLをこのPhaseでは一切生成
  しない。
- **Real Validation Completion基準**(10項目チェックリスト、
  `TDNET_ARCHITECTURE.md` §7): 将来Add-onが利用可能と確認できた
  場合のみ適用する、`COMPLETE`への昇格条件。
- Reviewer(`pit-auditor`/`skeptic-reviewer`)の追加Focus項目
  (三層混同・Provider挙動の遡及的再解釈・Cursorの誤用・Ephemeral
  URLの永続化・Event方向の早期生成等)を、次回Reviewer Pass実施時の
  観点として記録(実装コード自体が存在しないため、今回のReviewer
  Passでは「未実装であることの妥当性」の確認が中心になる)。

### §4 Source Catalog / Cost・Plan Dependency

`cost_or_plan_dependency`は「J-Quants LightプランへのAdd-on、月額
11,000円[税込]」というSearch-Snippet由来の未確認情報として記録した
上で、**Current Userがこのアドオンを契約済みとは仮定しない**ことを
明記した(ユーザー指示§26「Do NOT Require Purchase」: Phase4B-3を
進めるためにユーザーへ契約を要求しない)。Add-on契約の要否・金額の
確定は今回のDecisionの対象外。

### §5 Reviewer Findings(pit-auditor / skeptic-reviewer)

`pit-auditor`・`skeptic-reviewer`(いずれもRead-only、コード自体は
変更しない)へ、Catalog登録・Cursor Provenance骨格・新規/更新済み
Documentation一式(実装コードが存在しないため、「未実装であることの
妥当性」自体の確認が中心)のReviewを依頼した。

**pit-auditor(5件、最高でMEDIUM/HIGH)**:

1. [MEDIUM] `test_tdnet_cursor_module_never_imports_disclosure_document_
   or_availability_basis`の禁止Import検知が単純な部分文字列一致であり、
   `from lib.disclosures import model`のような別の書き方や
   `importlib.import_module()`経由の動的Importを見逃す(現時点で実際の
   違反は無いが、Test自体の堅牢性が不足)。**対応済み**(下記)。
2. [MEDIUM/HIGH] `DISCLOSURE_ARCHITECTURE.md`/このDecision(§3)の
   三層分離説明が、「発行体自身が同時にDelivery Providerでもある」と
   いう誤った表現でEDINETの2層収束を説明しており、`publishing_entity`
   (発行体)と`disclosure_system`/`delivery_provider`を概念的に
   混同していた(EDINETの`entity_id`は実際には未解決[D0046]のまま
   であり、2層への収束は発行体解決を意味しない)。**対応済み**
   (`DISCLOSURE_ARCHITECTURE.md`該当箇所・本Decision §3いずれも
   修正、下記参照)。
3. [MEDIUM] `TdnetRetrievalCursorState.query_date`が、`cursor_value`/
   `previous_cursor`と同水準の「Timestampとして誤用しない」明示的
   警告を欠いていた(`date`型を持つ唯一のFieldであり、将来
   「その日Retrievalされた全Documentの`market_public_at`の代替」
   として誤用される具体的リスクがある)。**対応済み**(下記)。
4. [LOW/MEDIUM] `pit_available=False`/`NOT_IMPLEMENTED`は`SourceCatalog.
   find()`のFilter条件として一切使われておらず(Test以外での参照は
   ゼロ)、Metadata止まりで構造的な強制力が無い。ただしこれはEDINET
   Descriptorにも共通する既存の設計上のGapであり、D0047固有の新規
   問題ではないため今回は変更しない(将来、`SourceCatalog`利用側の
   Orchestrationコードが実装される時点で別途対応)。
5. [LOW] `AvailabilityBasis.INFERRED`の「15:00以降翌営業日扱い」という
   例示(`DATA_SOURCE_ARCHITECTURE.md`のTDnet行)は、`lib/evidence/
   model.py`の既存Docstringに既にある一般的な例示であり本Decisionで
   新規に主張したものではないが、`TDNET_SOURCE_ONBOARDING.md` §7の
   `DiscDate`/`DiscTime`裏付けがゼロであることと併記が薄いと誤解を
   招きうる。将来Adapter実装時に、この15:00 Ruleを未確認のまま
   `INFERRED` Basisへ暗黙に採用しないことを確認する(このRoundでは
   コード変更なし、既に`(未検証)`と明記済みのため追加対応は見送り)。

**skeptic-reviewer(PASS_WITH_CONCERNS、4件)**:

1. [MEDIUM] `TDNET_LOCAL_VALIDATION_GUIDE.md` §Eの最小Raw Probeが、
   `Authorization: Bearer`ヘッダを未確認のまま既定値として使用して
   おり、既に確認済みのJ-Quants V2 Core APIの実際の認証方式
   (`x-api-key`ヘッダ、`lib/data_sources/jquants.py`)と異なっていた。
   これにより、ヘッダ形式の誤りによる401/403を「Add-on未契約」と
   誤解する具体的なリスクがあった。**対応済み**(下記)。
2. [LOW] `test_tdnet_notes_do_not_claim_any_adapter_code_exists`が
   `descriptor.notes`内の文字列存在確認のみ(Tautologicalに近い)で、
   実際に`tdnet.py`が存在しないことを構造的に確認していなかった。
   **対応済み**(下記)。
3. [LOW] 三層分離を「一般原則」と呼ぶ根拠が、実質的にTDnet(未確認)
   というN=1の事例のみに基づいていた。**対応済み**(上記pit-auditor
   Finding 2の修正と合わせて、この限界を明記する一文を追加)。
4. [LOW] `test_tdnet_authority_class_is_primary_official_but_not_used_
   as_truth_score`がDescriptor自身のHardcoded値を再主張するに留まる
   構造的限界を持つ(EDINET側の同種Testにも共通する既存の限界であり、
   D0047固有の新規劣化ではないため変更しない)。

**対応**:

- `test_tdnet_cursor.py`の禁止Import検知Testを`ast`ベースの解析
  (`ImportFrom`/`Import`ノードを`module`・`names[].name`両方について
  検査)へ書き換え、`from lib.disclosures import model`のような分割
  記法も検知できるようにした。
- `tdnet_cursor.py`の`query_date`Field Docstringへ、`market_public_at`
  の代替として下流へ伝播させてはならないという明示的な警告を追加した。
- `DISCLOSURE_ARCHITECTURE.md`・本Decision §3の三層分離説明を、
  「`disclosure_system`と`delivery_provider`のみがCollapseする」
  という正確な表現へ修正し、`publishing_entity`/`entity_id`が常に
  別軸のまま残ること、この一般原則が現時点でTDnetというN=1の未確認
  事例のみに基づくことを明記した。
- `TDNET_LOCAL_VALIDATION_GUIDE.md` §Cへ認証方式確認項目を追加し、
  §Eの認証ヘッダ推測(既存確認済みの`x-api-key`パターンとの関係)を
  明示するコメントを追加した。
- `test_tdnet_catalog.py`の`test_tdnet_notes_do_not_claim_any_
  adapter_code_exists`を、`Path`で実際に`lib/disclosures/providers/
  tdnet.py`が存在しないことを直接確認する構造的Testへ強化した(文字列
  存在確認のみのTautologyから脱却)。

再Reviewは実施していない(全FindingがDocumentation表現修正・Test
堅牢性強化・Docstring追記で完結し、実装コード自体が存在しないため
Architecture上の新規リスクは無いと判断)。

### 最終回帰確認

`pytest`(Lab 462件・既存Screening Tool 37件)・`ruff check`・`mypy`
(TDnet関連2ファイル)いずれもclean。`git status`/`git diff --stat --
core/ app.py tests/`で変更が無いことを再確認済み(空Diff)。

### Completion Status

`CODE_COMPLETE_AWAITING_ADDON_LOCAL_VALIDATION`。以下の両方が確認
できるまで`COMPLETE`へは昇格しない:

1. J-Quants TDnet Add-onへの契約状況(未確認、契約を前提にしない)。
2. `TDNET_SOURCE_ONBOARDING.md`の最重要2項目(訂正/削除/`DiscStatus`/
   `RevNo`意味論、`DiscDate`/`DiscTime`のPIT意味論)の公式資料による
   確認、および製品帰属(J-Quants API vs J-Quants Pro)の確定。

`TDNET_LOCAL_VALIDATION_GUIDE.md`にユーザーのローカル環境から上記を
確認するための手順(仕様書の直接確認を最優先、Add-on契約済みの場合の
み最小限のRaw Probeを実行)を用意した。

### このDecisionでやらないこと

`lib/disclosures/providers/tdnet.py`(Adapter/Normalizer)の実装・
Field Mapping・DocumentKind/DiscItems Mapping・Entity Registry統合・
Forward Collection Scheduler・Company IR(Phase4B-4)・本文の意味解析・
Event抽出・Buy/Sell判断・Strategy/Backtest変更・Screening Tool変更
には着手していない。

## D0048 — Phase4B-3再開: EXTERNAL_OFFICIAL_SPEC_VERIFICATIONに基づくTDnet Adapter/Normalizer実装

### §1 経緯: D0047のBlockedを解消したユーザー申告

D0047で記録した通り、Phase4B-3のSource Onboarding調査(`TDNET_SOURCE_
ONBOARDING.md`)は本セッションから`jpx-jquants.com`・`jpx.gitbook.io`
いずれへも接続できず、タスク上最重要の2項目(`DiscStatus`/`RevNo`の
訂正・削除意味論、`DiscDate`/`DiscTime`のPIT意味論)いずれも裏付け
ゼロのまま、`lib/disclosures/providers/tdnet.py`を実装せずCatalog登録
(`NOT_IMPLEMENTED`)・Cursor Provenance骨格・設計原則文書のみで停止した。

その後、ユーザーから以下の申告があった: 「本セッションではjpx-jquants.
comへの接続が403でSource Onboardingを完了できなかったが、別のWeb-access
環境から2026-08-17時点のJ-Quants/JPX公式ページを直接確認した」として、
D0047で未確認だった項目の多くについて具体的な内容(Field名・Endpoint
仕様・現在の実装挙動)が提示された。

**Provenance(最重要)**: ユーザー自身がこの申告を、Claude自身がWebで
確認した事実として記録せず、明示的に`USER_SUPPLIED_OFFICIAL_
VERIFICATION`/`EXTERNAL_OFFICIAL_SPEC_VERIFICATION`としてProvenanceを
明示するよう指示した。この指示は本Lab全体の原則(「未確認のSource仕様を
推測で埋めない」「実際の外部Field名・意味論を推測・仮定しない」)と
完全に整合するため、そのまま厳格に適用した:

- 申告内容はすべて`EXTERNAL_OFFICIAL_SPEC_VERIFICATION`
  (`USER_SUPPLIED_OFFICIAL_VERIFICATION`と同義)としてProvenance Tag
  付けし、コード(`tdnet.py`/`tdnet_normalize.py`)・Docstring・
  `TDNET_SOURCE_ONBOARDING.md`・本Decisionのすべてに明記した。
- **Claude自身がこのSession内で一次資料をFetchして確認したものでは
  ない**ことを、既存のEDINET/J-Quants Core APIの確度分類(実データで
  疎通確認済み)とは明確に区別して記録した。
- **真の意味でのLocal Real Data Validation**(実際にAdd-on契約済みの
  API Keyで`/v2/td/list`等を呼び出し、Response実物を観測すること)は
  まだ行われていない。この申告を実装の根拠として採用しても、それだけで
  Phase4B-3を`COMPLETE`とはしない(下記§7参照)。

### §2 ユーザー申告の内容(要約、詳細は`TDNET_SOURCE_ONBOARDING.md`
「EXTERNAL_OFFICIAL_SPEC_VERIFICATION」セクション参照)

1. **Product Identity**: 対象は「J-Quants API」(個人向け)の「TDnet/
   Company Disclosure Timely Disclosure Add-on」であり、J-Quants Pro
   ではない(D0047で指摘した製品混同リスクがこの方向で解消)。JPX
   2026-05-18提供開始、Lightプラン以上、月額11,000円(税込)。
2. **`GET /v2/td/list`**: `x-api-key`認証。Response Field: `DiscNo`/
   `Code`/`Name`/`DiscDate`/`DiscTime`/`Title`/`DiscStatus`/`RevNo`/
   `DiscItems`/`Docs`/`cursor`/`pagination_key`。現在の実装挙動として
   Title訂正が反映されない・削除済み開示も返り続ける・`DiscStatus`は
   常にnull・`RevNo`は常に1(タスク上最重要項目)。Provider宣言Schema
   意味論としては`DiscStatus`(null=新規/`revision`=訂正/`delete`=
   削除)・`RevNo`(1〜99)が別途定義されており、**現在の実装挙動と
   Schema宣言意味論を混同しないこと**が明示された。開示File自体が
   訂正された場合は新しい`DiscNo`が発行され独立した新規Recordとして
   扱われる(既存`DiscNo`が更新されるわけではない)。
3. **Query Semantics**: `date`または`code`必須。`code`+`from`+`to`で
   期間クエリ。4桁Codeへの末尾ゼロパディング(既存D0036パターンと一致)。
4. **Cursor/Pagination**: `cursor`(当日差分)と`pagination_key`
   (Pagination)は同時指定不可。`cursor`をTimestampとして解釈しない。
5. **`GET /v2/td/files`**: `discNo`必須、`docs`(`g`/`s`/`x`)任意。
   Download URLは15分で失効。
6. **`GET /v2/td/bulk`**: `lastUpdated`/`url`を返す、gzip CSV、過去5年、
   URL15分失効、`lastUpdated`はDisclosure Timeではない。
7. **TDnet Market Public Time(PIT上最重要)**: TDnet開示Timeと適時開示
   情報閲覧サービスでの公衆縦覧可能時刻が同時であることをJPX公式TDnet
   Documentationが確認しているという申告に基づき、`DiscDate`+
   `DiscTime`(Asia/Tokyo)を`market_public_at`(`AvailabilityBasis.
   EXACT`)として使用できるとした。ただし`market_public_at` !=
   `provider_available_at`であることは明示的に維持され、Fallbackは
   引き続き禁止。
8. **Rate Limit**: 100リクエスト/分(通常Plan Rate Limitとは独立)。

### §3 実装スコープ

上記を根拠に、以下を新規実装した:

- `lib.disclosures.providers.tdnet.TdnetAdapter`: `fetch_documents_
  list_raw()`(`/v2/td/list`、date/code XOR必須・cursor/pagination_key
  同時指定禁止をコードレベルでfail closed検証)・`fetch_files_raw()`
  (`/v2/td/files`)・`fetch_bulk_raw()`(`/v2/td/bulk`、Metadata取得の
  みでFile本体はDownloadしない)。`x-api-key`(`JQUANTS_API_KEY`を再利用)。
  429時は`Retry-After`Headerを尊重してBack off(最大3回)、それ以外の
  HTTPエラーはTransport層(`raise_for_status()`)のみに依拠する
  (EDINETのようなHTTP-200-masks-error Patternの有無はTDnet Add-onに
  ついて未確認のため、確認されていないError Envelope形状を推測で
  コード化しない、`TdnetApiError`のDocstring参照)。
- `lib.disclosures.providers.tdnet_normalize`: `parse_tdnet_documents_
  list_payload()`(`DisclosureDocument`+`TdnetDocumentMetadata`ペアへ
  変換)。`TdnetDiscStatus`(Schema宣言値のみをParse、現在の実装挙動
  [常にnull]をLifecycle判定へ使わない)・`RevNo`(単なるRaw値保持、
  Revision回数のEvidenceとして解釈しない)・`entity_id`(既存
  `normalize_provider_code_to_internal`を再利用、失敗時は推測せず
  `None`へfail closed)・`market_public_at`(`DiscDate`+`DiscTime`から
  `EXACT` Basis、`lib.fundamentals.normalize._build_market_public_at`
  と同じ設計)・`provider_available_at`(常に`UNKNOWN`、Fallbackしない)・
  `document_kind`(`DiscItems`公式Code List未確認のため常に`UNKNOWN`)・
  `DiscItems`/`Docs`(Opaque Raw値として保持、意味論を一切解釈しない)。
  `extract_retrieval_cursor_fields()`で`cursor`/`pagination_key`を
  `DisclosureDocument`とは完全に分離したまま取り出せるようにした
  (`TdnetRetrievalCursorState`との接続点、D0047の設計をそのまま利用)。
- **最重要の禁止事項(タスク上明示)**: 新しい`DiscNo`が過去の`DiscNo`を
  訂正した、という関係性Record(`DocumentRelationship`)を一切自動生成
  しない。この型名自体を`tdnet.py`/`tdnet_normalize.py`のいずれにも
  一切記述せず(EDINETの既存Discipline、D0046を踏襲)、構造的Testで
  非出現を確認する。
- `lib.disclosures.catalog.build_tdnet_dataset_descriptor()`:
  `implementation_status=NOT_IMPLEMENTED`のまま維持(下記§7参照)。
  `cost_or_plan_dependency`・`known_limitations`・`notes`を今回の
  実装状況を反映して更新。
- Attachment実体化は行わない(`DisclosureDocument.attachments`は常に
  `()`)。`/v2/td/files`/`/v2/td/bulk`が返す15分失効のDownload URLが
  Common Coreの永続的Fieldへ紛れ込む経路が存在しないことを、`docs_raw`
  (`TdnetDocumentMetadata`側のOpaque Raw値)への隔離と回帰Testで確認
  した(`TDNET_ARCHITECTURE.md` §5「Ephemeral URL Safety」)。

### §4 BASE_URL・Envelope形状についての推論(Main Claudeによる補完、明示)

ユーザー申告は`GET /v2/td/list`等のPath形式のみで、完全なHost名や
実際のJSON構造例までは示さなかった。以下2点はMain Claudeによる妥当な
補完であり、EXTERNAL_OFFICIAL_SPEC_VERIFICATIONの直接申告そのものでは
ないことを明示する:

1. **BASE_URL**: TDnet Add-onが「J-Quants API」(個人向け、既存
   `JQuantsAdapter`と同一製品)の機能であることが確認されたため、
   既存の確認済みHost(`https://api.jquants.com/v2`、D0039)を共有
   すると推論した。
2. **Response Envelope形状**: `{"data": [...], "cursor": ...,
   "pagination_key": ...}`という形状は、既存`JQuantsAdapter._get_all_
   pages`が前提とする既存製品共通のEnvelope規約からの類推である。

いずれも`TDNET_LOCAL_VALIDATION_GUIDE.md`・`TDNET_ARCHITECTURE.md` §7
へLocal Real Data Validationで最優先に確認すべき項目として明記した。

### §5 Reviewer Findings(pit-auditor / skeptic-reviewer)

`pit-auditor`・`skeptic-reviewer`(いずれもRead-only)へ、新規実装
(`tdnet.py`/`tdnet_normalize.py`/対応するTest群/Catalog更新/Docs更新)
のReviewを依頼した。

**pit-auditor(4件、最高MEDIUM)**:

1. [MEDIUM] `internal_document_id`がPayload内Index(`{DiscNo}_{index}`)を
   含む(EDINETの既存Pattern踏襲)ため、同一`disc_no`が別々の`/v2/td/list`
   呼び出し(Cursorによる当日差分Pollingで重複Windowを持ちうる)で異なる
   Indexを持って出現すると、`internal_document_id`が呼び出しごとに
   異なってしまう。**対応済み**(下記)。
2. [LOW-MEDIUM] `_parse_entity_id`のDocstring「正規化できない場合は
   Noneへfail closed」という主張が、数字以外のCode値については実際には
   成り立っていなかった(`normalize_provider_code_to_internal()`は
   数字以外の文字列をそのまま変更せず返す既存設計、合成Fixture用の
   Raw Labelを想定したもの)。**対応済み**(下記)。
3. [LOW] `TDNET_ARCHITECTURE.md` §1〜§6本文が、D0048で新たに`EXTERNAL_
   OFFICIAL_SPEC_VERIFICATION`として記録された項目についても「未確認」
   という古い表現のまま残っていた。**対応済み**(下記)。
4. [LOW] Fail Closed Validation Testが、実際にNetwork呼び出し前に
   検証が発生していることまでは構造的に確認していなかった
   (Code読解では確認済みだが、Test自体がそれを保証していなかった)。
   **対応済み**(下記)。

**skeptic-reviewer(PASS_WITH_CONCERNS、3件)**:

1. [MEDIUM/HIGH] `market_public_at`に`AvailabilityBasis.EXACT`を
   割り当てるのは、確認根拠(EXTERNAL_OFFICIAL_SPEC_VERIFICATION、
   ユーザーの又聞き)に対して確信度を過大表示している。EDINETは実際に
   `api.edinet-fsa.go.jp`へHTTP疎通し`submitDateTime`Fieldの実在自体は
   確認済み(D0046、CONNECTEDまで昇格)という、これより強い証拠を
   持ちながらも、`submitDateTime`が真にMarket Public Timeと一致するか
   という意味論的結びつき自体は未確認だったため`market_public_at`を
   `UNKNOWN`のまま維持した(`edinet_normalize.py`)。TDnetの`DiscDate`+
   `DiscTime`→`market_public_at`という意味論的結びつきの確認根拠は、
   EDINETのそれよりもさらに弱い(一次資料への直接Fetch自体が一度も
   行われていない)。**対応済み**(下記)。
2. [MEDIUM] `TDNET_ARCHITECTURE.md`本文・`DISCLOSURE_ARCHITECTURE.md`
   の三層分離節が、D0048の`EXTERNAL_OFFICIAL_SPEC_VERIFICATION`確認
   状況と矛盾する古い「未確認」表現を随所に残していた(pit-auditor
   Finding 3と同一問題)。**対応済み**(下記)。
3. [LOW] `TdnetDiscStatus.NEW`(raw null→この値)という命名が、現在の
   実装挙動として毎回この値が付与される(常にnull)ことを踏まえると
   「訂正されていないことの主張」であるかのように読める可能性がある。
   ただしDocstringでの警告が3箇所で繰り返され、実際にこの値を消費する
   コードが現時点で存在しない(`implementation_status=NOT_IMPLEMENTED`と
   整合)ため、Reviewer自身がSeverityをLOWと判定し、将来この値を実際に
   消費するLogicが追加される時点での対応を推奨した。**対応見送り**
   (Reviewer自身の推奨通り、現時点では変更しない)。

Verdict: `PASS_WITH_CONCERNS`。Provenance Labelingの丁寧さ(コード内の
`EXTERNAL_OFFICIAL_SPEC_VERIFICATION`明示、Main Claude推論とユーザー
申告の分離、`implementation_status=NOT_IMPLEMENTED`の維持、D0048 §5/§6の
Placeholder明示)は「拙速な巻き返し」ではないと評価された一方、`EXACT`
Basisの割り当てとDocumentation不整合の2点は実際の修正が必要と判定された。

**対応**:

- `tdnet_normalize.py`の`_build_market_public_at()`を、値は構築しつつ
  Basisは`AvailabilityBasis.EXACT`ではなく`AvailabilityBasis.UNKNOWN`を
  返すよう変更した(EDINETの前例に倣う保守的判断)。`disclosures_as_of()`
  の既定安全側除外がTDnetにもそのまま適用されるようになった。
  `test_market_public_at_value_built_from_disc_date_and_disc_time_but_
  basis_stays_unknown`・`test_normalized_document_flows_into_evidence_
  and_market_information_study_view`(A系統既定では非表示、明示的
  `include_unknown_availability=True`でのみ表示)を更新した。
- `_parse_entity_id`へ、`normalize_provider_code_to_internal()`へ委譲
  する前に明示的な数字Onlyチェックを追加し、非数字Codeを`None`へ
  正しくfail closedするようにした。回帰Test追加。
- `internal_document_id`のPayload内Index依存というリスクについて、
  `_parse_row`Docstringへ明示的な警告(将来Cursorベース継続的Ingestion
  Pipeline構築時に`find_same_source_document_id_signals()`を必須Stepと
  すること)を追加し、この挙動を実際に再現するRegression Test
  (`test_same_disc_no_across_separate_cursor_fetches_gets_different_
  internal_document_id`)を追加した。
- `TDNET_ARCHITECTURE.md` §1/§2/§3/§4/§5、`DISCLOSURE_ARCHITECTURE.md`
  三層分離節の「未確認」表現を、D0048の`EXTERNAL_OFFICIAL_SPEC_
  VERIFICATION`確認状況(Claude自身の直接確認・真のLocal Real Data
  Validationのいずれでもないという限定付きで)と整合する表現へ更新した。
- `test_tdnet_adapter.py`の4件のFail Closed Validation Testへ、
  `session.calls == []`のAssertionを追加し、実際にNetwork呼び出し前に
  検証が発生していることを構造的に保証した。

再Reviewは実施していない(全FindingがBasis変更・Docstring追記・Test
強化・Documentation表現修正で完結し、Adapter/NormalizerのCore設計
[Raw Fetch責務分離、Provider-neutral Common Core、訂正Relationship
非構築]自体には変更が無いため)。

### §6 最終回帰確認

`pytest`(Lab 523件・既存Screening Tool 37件)・`ruff check`・`ruff
format --check`・`mypy`(62ファイル)いずれもclean。`git status`/`git
diff --stat -- core/ app.py tests/`で変更が無いことを再確認済み(空
Diff)。

### §7 Completion Status

`CODE_COMPLETE_AWAITING_ADDON_LOCAL_VALIDATION`(D0047から変更なし)。
Adapter/Normalizerコードは実装されたが、以下の両方が確認できるまで
`COMPLETE`へは昇格しない:

1. J-Quants TDnet Add-onへの実際の契約状況(未確認、契約を前提にしない)。
2. `TDNET_LOCAL_VALIDATION_GUIDE.md`に基づく真のLocal Real Data
   Validation(ユーザーのローカル環境から実際にAdd-on契約済みのAPI Keyで
   `/v2/td/list`等を呼び出し、Response実物を観測すること)。BASE_URL・
   Envelope形状の推論(§4)・`EXTERNAL_OFFICIAL_SPEC_VERIFICATION`
   申告内容そのものの検証を含む。

`build_tdnet_dataset_descriptor()`の`implementation_status`は
`NOT_IMPLEMENTED`のまま(`CONNECTED`への昇格はLocal Real Data
Validation完了後)。

### このDecisionでやらないこと

`DiscItems`公式Code Listの取得・`document_kind`Mapping・`Docs`の
g/s/x以外の詳細意味論・Attachment実体化(File本体のDownload)・
Entity Registry本格統合(現状は既存Code正規化の再利用のみ)・Forward
Collection Scheduler・Company IR(Phase4B-4)・本文の意味解析・Event
抽出・Revision Direction判定・Buy/Sell判断・Strategy/Backtest変更・
Screening Tool変更には着手していない。

## D0049 — Phase4A Fundamentals: Evidence PIT Bugfix(`available_at`のmarket_public_atへのFallback禁止)

Phase4B-3(TDnet、D0047/D0048)とは独立した、既存Phase4A Fundamentalsの
Evidence生成に対する小規模な単独Bugfix。TDnet/EDINET/Company IRのいずれ
にも触れていない(`git diff --stat`で確認、下記§最終回帰確認参照)。
Phase4B-3のStatus(`CODE_COMPLETE_AWAITING_ADDON_LOCAL_VALIDATION`)は
このBugfixによって変更しない。

### §1 Root Cause

`lib.fundamentals.evidence.disclosure_metric_to_evidence()`の旧実装は
`available_at = envelope.market_public_at or envelope.retrieved_at`
としていた。`market_public_at`(市場公表時刻、A系統)は通常
`provider_available_at`(Provider経由で実際に参照可能になった時刻、
B系統)より**早い**。この早い時刻を`EvidenceRecord.is_usable_at()`が
直接参照する`available_at`(`self.source.available_at <= decision_at`)
へ代入すると、実際にはまだ研究所側で取得可能でなかった時点を「利用
可能だった」と誤認する(Future Leakage)。

例: `market_public_at=15:00`、実際のProvider配信=15:05、
`retrieved_at=15:06`の場合、旧実装は`available_at=15:00`となり、
`decision_at=15:03`時点でEvidenceが誤って「利用可能」と判定されうる。

### §2 Fix

`DisclosureEnvelope`/`FundamentalMetric`/`SourceMetadata`のいずれも
確認済みの`provider_available_at`を保持するFieldを持たない(現行Schema
の制約、新規Field追加は行わない、最小変更優先)。したがって
`source.available_at`には常に`envelope.retrieved_at`
(Observed Factとしての下限)を使う。`market_public_at`は
`source.published_at`(A系統)としてのみ設定し、`available_at`へは
Fallbackしない。

`retrieved_at`をFallbackとして使うこと自体はB系統PITでも許容される
(「少なくともこの時刻には研究所が実際に取得していた」という
Observed Factであり、Providerの真のAvailabilityを早く見積もる方向
ではなく、通常は遅く評価する保守的なBoundになるため)。**禁止するのは
`provider_available_at`がUNKNOWNの場合に`market_public_at`へ
Fallbackすることのみ**であり、`retrieved_at`へのFallbackは区別して
扱う。

旧Docstringの「market_public_atはprovider_available_at以前なので
保守的であり、available_atを過大評価しない」という説明は論理が逆
だった(過小評価ではなく、実際より早く使えたと誤認する方向の過大
評価だった)。この説明を修正した。

併せて、Module Docstringの例示(「会社がFY営業利益予想を100→120へ
変更した」)が、単一の`FundamentalMetric`のみを受け取るこの関数の
実際の挙動と矛盾していた(旧Value/新Valueの比較を含む文言は、この
関数からは生成できないし、生成すべきでもない)ため、単一値開示の例へ
差し替え、単一Metricからのrevision推論禁止を明記する段落を追加した。

### §3 外部Review(Copilot形式)への対応

**訂正の記録**: このDecisionの初回版には、外部Review未提示の時点で
「ユーザーが別Review Toolの結果を提示したが評価した」という趣旨の記述が
誤って含まれていた。実際には外部Reviewはこの§3の初回執筆**後**に提示
された。この誤りはユーザー自身の指摘により判明し、以下は実際に外部
Reviewを受け取った後、その内容を実コードと照合して評価した結果として
書き直したものである(未検証のことを検証済みとして書かない、という
本Lab全体の原則に従う)。

外部Review(Verdict: PASS_WITH_CONCERNS、Finding A〜J)を受け取り、
Findingをそのまま採用せず、実際のCodebase(`grep`による直接確認)を
根拠に個別評価した:

- **Finding A(retrieved_at Semantics Ambiguity、`retrieval_mode`
  Provenance Flag提案)**: 却下。本Labは「ingest worker/replay
  loader/proxy cache」のような複数Subsystem構成を持たない、個人用
  単一Process Offline Research Tool(`Japanese_Equity_Lab/CLAUDE.md`)
  であり、`parse_financial_summary_payload()`は`retrieved_at`を必須
  Keyword引数として要求し、内部で`datetime.now()`等を呼び出す経路が
  無いことを`grep`で直接確認した(新規回帰Test`test_normalize_
  pipeline_never_regenerates_retrieved_at_internally`)。新Schema
  Field追加は不要と判断。
- **Finding B/C(provider_available_atの信頼Flag・Provider別意味論
  Mapping)**: 却下。`grep`で確認した通り、EDINET/TDnet/Fundamentals
  いずれのAdapter/Normalizerも確認済みの`provider_available_at`実値を
  一切設定していない(常に`AvailabilityBasis.UNKNOWN`)。存在しない
  値を信頼する経路自体が無いため、この懸念は現状のCodebaseには適用
  されない。
- **Finding D/E(Event Extractor/Indexer/EvidenceCandidateへのRuntime
  Assertion)**: 却下。`grep`で確認した通り、これらのComponent自体が
  Codebaseに存在しない(Event抽出は将来Phaseへ明示的に延期済み、
  `lib.disclosures.model`のDocstring参照)。存在しないConsumerへの
  対策は追加できない。
- **Finding F(Naive Datetime)**: 既に対応済みと確認。`DisclosureEnvelope.
  __post_init__`が`retrieved_at`・`market_public_at`いずれもtz-naive値を
  Construction時にfail closedでRejectする(既存Model挙動)。回帰Test
  (`test_envelope_construction_rejects_tz_naive_market_public_at`)を
  追加してこれを明示的に固定した。
- **Finding G(`lib/fundamentals/normalize.py`のDocstring不整合)**:
  採用。pit-auditor Findingと同一Finding(D0048ではなくこのDecision
  §5参照)であり、`_provider_available_at_and_basis()`のDocstringに
  残っていた「market_public_atは保守的」という逆の論理を、
  `lib.fundamentals.evidence`と同じ表現へ修正した(挙動は変更せず、
  Docstringのみ)。あわせて、`include_unknown_availability=True`を
  明示した場合にこのAnchorが実際に`market_public_at`を返す(=既知の
  Gap)ことを、Prose説明だけでなく実際のコード実行結果として固定する
  回帰Test(`test_include_unknown_availability_true_reproduces_market_
  public_at_anchor_as_documented_gap`)を追加した(Gap自体の修正は
  §5-1のFollow-upとしてこのRoundでは行わない、Anchor挙動変更は
  既存呼び出し箇所への影響分析を要する設計判断のため)。
- **Finding I(`is_usable_at()`のTie-breaker、境界値の扱い変更)**:
  却下。`<=`(境界値を利用可能側に含む)という規約は、`RevisionHistory.
  as_of()`・`lib.disclosures.view.disclosures_as_of()`を含むCodebase
  全体で既に統一的に使われている既存規約であり、この関数だけ例外的な
  Provenance依存Tie-breakerを導入すると、既存規約との一貫性が崩れる。
  新規Enumも追加しない(最小変更優先の原則)。
- **Finding J(Cross-Layer Scan網羅性へのRuntime Assertion補完)**:
  部分的に採用。単純な`grep`だけでなく、`pit-auditor`(独立Subagent、
  Code読解ベース)による横断調査を実施済み(§5参照)であり、これは
  `grep`単体より網羅的な確認手段である。ただし存在しないConsumer
  (Finding D/E)へのRuntime Assertion追加はできないため、Documentation
  記録(§5のFollow-up)にとどめる。

### §4 Cross-Layer Scanの結果(新規実装は行わない、記録のみ)

`grep -rn "market_public_at or\|available_at.*=.*market_public_at"
lib/`を実施し、以下を確認した:

1. `lib/fundamentals/evidence.py`(このRoundで修正済み)。
2. `lib/fundamentals/normalize.py::_provider_available_at_and_basis()`
   (`build_revision_histories()`から呼ばれる)は、`anchor =
   market_public_at if market_public_at is not None else
   retrieved_at`という、一見同種のPatternを持つ。ただし常に
   `availability_basis=UNKNOWN`を返すため、既定(`include_unknown_
   availability=False`)では`RevisionHistory.as_of()`が除外し、
   安全側で機能する(`test_fundamentals_view.py`/`test_fundamentals_
   pit_real_dates.py`で回帰確認済み)。ただし呼び出し側が明示的に
   `include_unknown_availability=True`を指定した場合は、
   `market_public_at`がそのまま`available_at`として使われ、
   Evidence.pyで修正したのと同じ形のLeakageが再現しうる
   (pit-auditor Finding、下記§5参照)。**このRoundでは変更しない**
   (Fundamental Evidence issueのみが対象、最小変更優先、既に
   `AvailabilityBasis.UNKNOWN`による安全側デフォルトで守られている
   ため緊急性は低いと判断)。Docstringの「market_public_atが最も
   保守的なAnchor」という説明も、Evidence.py同様に論理が逆であり、
   将来修正が必要(§5)。
3. `lib/disclosures/normalize.py::_provider_available_at_and_basis()`
   (EDINET/TDnet Common Core版)も同型のPatternを持つが、これはPhase
   4B-3の管轄でありこのRoundの対象外(D0045/D0046で既に安全側
   Defaultとして設計済み、`disclosures_as_of()`が同じ除外Mechanismを
   持つ)。
4. `lib/disclosures/evidence.py::disclosure_document_to_evidence()`
   (`available_at: datetime = document.market_public_at or document.
   retrieved_at`、56行目)は、このRoundで修正した`lib.fundamentals.
   evidence`と**文字通り同一のBug**を持つ。Docstring自体が過去の
   pit-auditor Finding(D0045追記)によりこのリスクを既に自覚し、
   呼び出し側に`disclosures_as_of()`を経由するよう警告している。
   現在このEvidence生成関数は本番Pipelineへ未接続(Test以外の呼び出し
   元が無い)ため、実害は潜在的なもの(EDINET/TDnet Phase進展時に本番
   接続される前に対応が必要)。**このRoundでは変更しない**(TDnet/
   EDINETへは触れないというユーザー指示の明示的Scope外)。

### §5 既知のFollow-up項目(Anchor自体の挙動変更はこのRoundでは対応しない、将来Round向けに記録)

1. [MEDIUM、pit-auditor Finding、外部Review Finding Gと同一箇所]
   `lib/fundamentals/normalize.py::_provider_available_at_and_basis()`
   の**Docstringは§3で修正済み**(「market_public_atは保守的」という
   逆の論理を訂正、実際の安全性の根拠が`AvailabilityBasis.UNKNOWN`に
   よる既定除外であることを明記)。ただし**Anchor自体の挙動
   (`market_public_at`優先)は変更していない** — `include_unknown_
   availability=True`を明示指定した呼び出し側でのみ顕在化する
   Leakage経路であり、既定Pathは`AvailabilityBasis.UNKNOWN`除外で
   安全(この既知のGap自体を固定する回帰Test`test_include_unknown_
   availability_true_reproduces_market_public_at_anchor_as_documented_
   gap`を追加済み)。Anchor自体を`retrieved_at`固定へ変更するかは、
   既存`include_unknown_availability=True`呼び出し箇所への影響分析を
   要する設計判断のため、次のFundamentals関連Roundでユーザーの判断を
   仰ぐ。
2. `lib/disclosures/evidence.py::disclosure_document_to_evidence()`
   (EDINET/TDnet Common Core)に同型のBugが残っている(§4-4参照)。
   本番Pipeline未接続のため緊急ではないが、Phase4B-3以降でこの関数を
   実際に接続する前に、このRoundと同じ修正(`available_at =
   document.retrieved_at`固定)を適用する必要がある。

### §6 Regression Tests

`Japanese_Equity_Lab/13_tests/test_fundamentals_evidence_pit.py`
(新規、15件、うちH〜Jは§3の外部Review対応で追加):

- A. `market_public_at`<`retrieved_at`、`available_at`が`retrieved_at`
  になること(`market_public_at`にはならないこと)の直接確認 + `None`
  ケースを含むParametrize Sweep。
- B. `market_public_at`がNoneの場合でも`available_at`が常に
  `retrieved_at`であること。
- C. `decision_at`が`market_public_at`と`retrieved_at`の間(15:03)では
  `is_usable_at()`が`False`、`retrieved_at`と一致(15:06)では`True`、
  `market_public_at`より前(14:59)では`False`であることの直接確認
  (Bug Reportの数値例をそのまま再現)。
- D. tz-aware維持(`available_at`/`published_at`)、tz-naive
  `retrieved_at`のConstruction時Reject確認。
- E. Evidence Contentが解釈語(bullish/buy/sell/好調/割安/強気等)を
  一切含まないこと。
- F. 単一Metricから「100→120」等のRevision文を生成しないこと、
  関数SignatureがMetricを1つしか受け取らないことの構造的確認。
- G. Offline ReplayがManifest経由で`retrieved_at`を保存時点の値の
  まま保持し、Replay実行時刻へ上書きしないこと(`RawSnapshotStore`
  実際の保存・再読込Round-tripで確認)。
- H(外部Review Finding F対応). tz-naive`market_public_at`のConstruction
  時Reject確認(`retrieved_at`と同様の既存Model挙動を明示的に固定)。
- I(外部Review Finding A対応). `parse_financial_summary_payload()`が
  `retrieved_at`を必須引数として要求し、内部で`datetime.now()`等を
  一切呼び出さないことの構造的確認(Offline Replay時にRetrieved_atが
  暗黙にReplay実行時刻へ上書きされる経路が無いことの直接証明)。
- J(§5-1のFollow-up Gapを固定). `include_unknown_availability=True`
  明示時に`_provider_available_at_and_basis()`のAnchorが実際に
  `market_public_at`を返すという既知のGapを、Prose説明だけでなく
  実際のコード実行結果として回帰Test化(Gap自体の修正ではない)。

既存Test(`test_fundamentals_integration.py`の`test_disclosure_
metric_to_evidence_carries_source_authority_and_pit_fields`等)は
`available_at is not None`のみを確認しておりmarket_public_atとの
関係性に依存していなかったため、無変更のまま成功する。

### §7 Reviewer Pass

`pit-auditor`(Read-only)を実施。Finding: `lib/fundamentals/evidence.py`
の修正自体は「完全かつ正確」と判定(Residual Fallback経路なし、
Schema制約の主張は実際のModel定義と整合、新規Testは意味のある
回帰確認[旧実装であれば失敗する]、`fundamentals_as_of()`はこの
Bugfixと重複せず独立して機能、Revision文言修正も完全)。追加で
§4-2/§5-1の`lib/fundamentals/normalize.py`側Finding(MEDIUM)を
独立に発見・報告した(このDecision §4-2/§5-1へ反映済み)。
skeptic-reviewerは実施していない(小規模Bugfixのため、ユーザー指示
通り過剰なReviewer Roundを追加しない)。

外部Review(Copilot形式、§3)は`pit-auditor`とは独立したSecond Opinion
として受け取り、Findingごとに実Codebaseとの照合結果を§3に記録した
(採用: Finding F/G、部分採用: Finding J、却下: Finding A/B/C/D/E/I、
根拠付きで個別評価)。

### §8 最終回帰確認

`pytest`(Lab 538件・既存Screening Tool 37件)・`ruff check`・
`ruff format --check`・`mypy`(Lab: `lib/`全体、Root: `core app.py
scripts Japanese_Equity_Lab/lib`)いずれもclean。`git diff --stat --
core/ app.py tests/`で変更が無いことを確認済み(空Diff)。今回の変更
File一覧に`tdnet*`/`edinet*`ファイルが含まれないことを確認済み
(TDnet/EDINETへ触れていないことの直接確認)。

### このDecisionでやらないこと

`lib/fundamentals/normalize.py`の`_provider_available_at_and_basis()`
修正(§5-1、Follow-up)・`lib/disclosures/evidence.py`の同型Bug修正
(§5-2、Follow-up、TDnet/EDINET Scope外)・新しいEvent Candidate
Lifecycle・TDnet Revision Handling・Correction Engine・新しいReplay
Architecture・Global PIT Compliance Suite・新しいAvailability Enum/
Schema・Phase4B-4(Company IR)・Phase4A.5.1には着手していない。
Phase4B-3のStatus(`CODE_COMPLETE_AWAITING_ADDON_LOCAL_VALIDATION`)は
変更していない。

## D0050 — Disclosure Common Core: `lib/disclosures/evidence.py`のPIT Bugfix(D0049 Follow-up Findingの確定)

D0049(§4-4/§5-2)で「`lib/disclosures/evidence.py::disclosure_document_to_
evidence()`にFundamentals Evidence(D0049で修正済み)と同型のBugが残って
いる可能性がある」とpit-auditor Findingを記録しつつ、TDnet/EDINET Scope
外として当時は修正しなかった。このDecisionはその確認結果を確定し、
実際にBugだったため最小修正した記録である。

### §1 判定: C. ACTUAL_BUG(Guardなし)

`lib/disclosures/evidence.py`の実装(修正前)を直接確認した:

```python
available_at: datetime = document.market_public_at or document.retrieved_at
```

これはD0049で修正した`lib.fundamentals.evidence.disclosure_metric_to_
evidence()`の旧実装と文字通り同一のPatternだった。

**既存Guardの有無**: `SourceMetadata`(`lib.sources.catalog`)には
`availability_basis`相当のFieldが無く、`EvidenceRecord.is_usable_at()`
(`self.source.available_at <= decision_at`)はBasis情報を一切参照せず
`available_at`だけで判定する。旧Docstring自身が「実際のDecision/
Backtestで使う場合は、必ず先に`disclosures_as_of()`でPIT Filterした
上でEvidenceへ変換すること」と注意喚起していたが、これは**呼び出し側の
規約(Prose上の注意)であり、構造的なGuardではない**。この関数を直接
呼び出せば(実際に`test_tdnet_integration.py`の既存Testが直接呼び出して
いた)、`disclosures_as_of()`によるFilterを経由せずBugがそのまま顕在化
する。したがって`B. SAFE_BY_EXISTING_GUARD`ではなく`C. ACTUAL_BUG`と
確定する。

### §2 15:00/15:06の時刻例での確認結果

修正前のコードで市場公表時刻market_public_at=15:00、
provider_available_at=UNKNOWN、retrieved_at=15:06のDocumentから
`disclosure_document_to_evidence()`を呼び出すと:

- `evidence.source.published_at == 15:00`(修正前後で変化なし、正しい)
- `evidence.source.available_at == 15:00`(**Bug**、`market_public_at`と
  同じ値になっていた)
- `decision_at=15:03`で`evidence.is_usable_at(15:03)`が`True`を返して
  いた(**Future Leakage**、実際には15:06まで取得していない)

修正後:

- `evidence.source.published_at == 15:00`(変化なし)
- `evidence.source.available_at == 15:06`(`retrieved_at`、`market_
  public_at`とは異なる値)
- `decision_at=15:03`で`evidence.is_usable_at(15:03)`が`False`を返す
  (正しい、`test_evidence_is_not_usable_at_decision_at_between_
  market_public_at_and_retrieved_at`で確認)
- `decision_at=15:06`で`True`を返す(正しい)

### §3 Fix(最小修正)

`DisclosureDocument`は`market_public_at`/`market_public_at_basis`とは
別に`provider_available_at`/`provider_available_at_basis`をField
として持つ(Fundamentalsの`DisclosureEnvelope`には無いField、
`lib.disclosures.model.DisclosureDocument`Docstring参照)。この点で
Fundamentals[D0049]とはSchema上の前提が異なるため、修正内容も単純な
`retrieved_at`固定ではなく、以下の優先順位とした:

1. `provider_available_at`が確認済み(`provider_available_at_basis
   != AvailabilityBasis.UNKNOWN`)であればそれを使う。
2. 確認できなければ`document.retrieved_at`(Observed Factとしての
   下限)を使う。

**`market_public_at`へは決してFallbackしない**(D0049と同じ原則)。
現在(D0050時点)EDINET/TDnetいずれのNormalizerも`provider_available_at`
を確認済み値として設定しない(常に`UNKNOWN`Basis)ため、実際には常に
(2)の経路が使われる — ただし将来Providerが確認済み値を提供するように
なった場合にも自動的に活用できる設計であり、新規Schema Field追加は
行っていない(既存Fieldを正しく使うようにしただけ)。

旧Docstringの「market_public_atは保守的だからavailable_atを過大評価
しない」という説明も、D0049と同じ理由で逆だったため修正した。

### §4 Cross-Layer影響確認: EDINET/TDnet

`lib/disclosures/evidence.py`はProvider-neutralなCommon Coreであり、
EDINET/TDnetいずれの正規化済み`DisclosureDocument`もこの関数を経由し
うる。ユーザー指示通り、**EDINET Adapter/Normalizer・TDnet Adapter/
Normalizer自体はSource固有のBugが見つからなかったため変更していない**
(`lib/disclosures/providers/edinet.py`・`edinet_normalize.py`・
`tdnet.py`・`tdnet_normalize.py`はいずれも無変更、`git status`で
確認済み)。

- **EDINET**: `edinet_normalize.py`は`market_public_at`/`provider_
  available_at`いずれも常に`None`/`UNKNOWN`のまま構築する(D0046の
  既存方針、意味論未確認のため)。したがって修正後もEDINET由来の
  Evidenceは常に`retrieved_at`を使う(旧実装でも結果的に`retrieved_at`
  だった — `market_public_at`が常に`None`だったため`or`句が`retrieved_
  at`側に落ちていた。**EDINETについては旧実装でも実害顕在化はしていな
  かった**、`test_edinet_style_document_uses_retrieved_at_since_
  provider_available_at_stays_unknown`で回帰確認)。
- **TDnet**: `tdnet_normalize.py`は`market_public_at`の値自体は
  `DiscDate`+`DiscTime`から構築する(D0048、`AvailabilityBasis.UNKNOWN`
  付き)が、`provider_available_at`は常に`None`/`UNKNOWN`のまま。
  **TDnetについては旧実装で実際にBugが顕在化していた**
  (`market_public_at`が値を持つため、`available_at`が誤って15:00相当の
  値になっていた)。既存`test_tdnet_integration.py::test_normalized_
  document_flows_into_evidence_and_market_information_study_view`が
  この誤った挙動(`available_at == market_public_at`)をそのまま
  Assertしていたため、修正済みの正しい挙動(`available_at ==
  retrieved_at`)へ更新した。

### §5 以前のpit-auditor Finding(D0049)についての確定

D0049 §4-4/§5-2でpit-auditorが「本番Pipeline未接続のため実害は潜在的」
と評価していたが、これは**部分的に不正確だった**ことが今回判明した:
`disclosure_document_to_evidence()`自体は本番Backtest Pipelineへは
確かに未接続だが、**既存Test Suite自身(`test_tdnet_integration.py`)が
Bugのある挙動をそのままAssertしており、Bugが「発生しうる」のではなく
「Test上ですでに発生・肯定されていた」**。この区別(未接続だから安全、
と、Testが誤った挙動を固定してしまっている、は別問題)は当時のFinding
記録では明示されていなかった。今回、実コードとTestを直接確認したことで
初めて判明したため、ここに追記する(以前の判断の不正確さもAudit
Historyとして記録する、というLabの方針に従う)。

### §6 Regression Tests

既存Testで今回の挙動がすでに証明されていたわけではない
(`test_tdnet_integration.py`は逆に旧Bugのある挙動をAssertしていた、
§4参照)。したがって次のTestを追加・修正した:

**新規**: `Japanese_Equity_Lab/13_tests/test_disclosures_evidence_pit.py`
(10件):

- A系統(`provider_available_at`未確認、Root Causeの直接再現):
  `test_available_at_uses_retrieved_at_not_market_public_at_when_
  provider_available_at_unknown`(15:00/15:06の数値例そのもの)、
  `test_available_at_never_falls_back_to_market_public_at_when_
  market_public_at_is_none`、`test_available_at_always_equals_
  retrieved_at_when_provider_available_at_unknown`(3ケース
  Parametrize)。
- B系統(`provider_available_at`確認済みの優先): `test_available_at_
  uses_confirmed_provider_available_at_when_basis_is_not_unknown`
  (`basis=EXACT`なら`provider_available_at`を使う、Fundamentalsには
  無いCommon Core固有の分岐)、`test_available_at_ignores_provider_
  available_at_when_basis_is_unknown_even_if_value_present`(値が
  あってもBasisがUNKNOWNなら信頼しない)。
- C系統(`is_usable_at()`境界、ユーザー指定の時刻例そのもの):
  `test_evidence_is_not_usable_at_decision_at_between_market_public_
  at_and_retrieved_at` — `decision_at=15:03`で`False`、`15:06`で
  `True`、`14:59`で`False`を直接確認。
- D系統(EDINET/TDnet別の実際の出力形を模した確認): `test_edinet_
  style_document_uses_retrieved_at_since_provider_available_at_
  stays_unknown`、`test_tdnet_style_document_uses_retrieved_at_not_
  market_public_at_despite_exact_value`。

**修正**: `Japanese_Equity_Lab/13_tests/test_tdnet_integration.py`の
`test_normalized_document_flows_into_evidence_and_market_information_
study_view` — 旧Assert(`evidence.source.available_at == document.
market_public_at`、旧Bugのある挙動をそのまま固定していた)を、修正後
の正しい挙動(`available_at == document.retrieved_at`かつ`!=
document.market_public_at`)へ更新。**この修正が意味のある回帰確認で
あることを、旧実装に対してこのAssertが実際にFailすることを先に確認
した上で**(修正前Codeに対し新Assertを当てて`AssertionError`を実際に
観測)、修正後Codeに対して通ることを確認する手順を踏んだ(Tautological
Testではないことの直接証拠)。

`test_disclosures_integration.py`・`test_edinet_catalog.py`は
`available_at is not None`等の弱いAssertのみで`market_public_at`との
関係性に依存していなかったため無変更のまま成功する。

Reviewer Pass(pit-auditor/skeptic-reviewer)は、今回のTaskがD0049の
pit-auditor Findingを直接コードで確認・確定させる作業であり、ユーザー
指示(今回のMessage §1-§8)にもReviewer再実施の要求が無かったため実施
していない(Scope外の追加Reviewer Roundを増やさない、という判断。
やらなかったことの記録として明示する)。

### §7 最終回帰確認

`pytest`(Lab 548件・既存Screening Tool 37件、いずれもPASS)・
`ruff check`・`ruff format --check`・`mypy`(Lab: `lib/`全体62 source
files、Root: `core app.py scripts Japanese_Equity_Lab/lib`82 source
files)いずれもclean。`git diff --stat -- core/ app.py tests/`は空Diff
(既存Screening Toolに触れていないことを再確認)。`git status --short`
で今回変更・新規File一覧が次の3件のみであることを確認済み:

```
 M Japanese_Equity_Lab/13_tests/test_tdnet_integration.py
 M Japanese_Equity_Lab/lib/disclosures/evidence.py
?? Japanese_Equity_Lab/13_tests/test_disclosures_evidence_pit.py
```

`tdnet.py`・`tdnet_normalize.py`・`edinet.py`・`edinet_normalize.py`
（Adapter/Normalizer本体）はいずれも含まれておらず、ユーザーの明示的
Scope制約(EDINET/TDnet Adapter自体は変更しない)を満たしている。

### §8 Completion Status

`CODE_COMPLETE`。D0049 §4-4/§5-2のFollow-up Finding(`lib/disclosures/
evidence.py`の同型Bug疑い)は`C. ACTUAL_BUG`と確定・修正済み。Phase4B-3
のStatus(`CODE_COMPLETE_AWAITING_ADDON_LOCAL_VALIDATION`)は変更して
いない。

### このDecisionでやらないこと

新規Schema Field追加(`provider_available_at`相当のFieldはFundamentals
側にも今回追加していない、D0049のFollow-up Gapのまま)・新しいEvent
Engine・Indexer・Replay Architecture・TDnet Adapter/Normalizer再設計・
EDINET Adapter/Normalizer再設計・`lib/disclosures/providers/`配下の
いずれのFileへの変更・大規模なCommon Core変更・Phase4A.5.1・
Phase4B-4(Company IR)には着手していない。
