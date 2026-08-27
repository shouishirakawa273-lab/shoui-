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

## D0051 — Phase4A.5.1: Research Engineering Hardening 設計固定(実装は次Round)

**このDecisionはDesign/Scope/Implementation Orderの確定のみを記録する。
コード実装・Schema変更・Hook作成・Skill変更・Agent変更・Test追加・Phase
Status変更は一切行っていない。** 詳細な設計は新規
`Japanese_Equity_Lab/PHASE4A5_1_PLAN.md`(全文)を参照、ここではDECISIONS.md
の慣例に従い要約のみ記録する(268KBの本File自体をこれ以上肥大化させない
ため、詳細をDECision本文へ複製しない)。

### 背景

D0049(Fundamentals Evidence PIT Bugfix)・D0050(Disclosure Common Core
PIT Bugfix)で、`market_public_at`への`available_at`Fallbackという**同型の
Bugが2つの独立したModuleに存在していた**こと、および既存Testがその誤った
挙動をそのままAssertしていた(`ALL TESTS PASS != SEMANTICALLY CORRECT`)
ことが判明した。この教訓を「思想・Documentation・Reviewerの記憶」から
「機械的に検知可能なGuardrail」へ進める設計をUserから要求された。

### Repository Reality Check(実施済み、`PHASE4A5_1_PLAN.md` §A)

実際に`lib/`・`13_tests/`・`.claude/skills/`・`.claude/agents/`・
`.claude/settings.json`・DECISIONS.md該当箇所(D0042/D0044/D0046追記2)を
読んだ結果、最も重要な新発見は次の点である:

**Construction-time Ordering Invariantの不在**: `lib/point_in_time.py::
PointInTimeRecord`(旧Price PIT層)は`available_at < published_at`を
Constructor(`__post_init__`)でRejectしているが、`lib/sources/catalog.py::
SourceMetadata`・`lib/evidence/model.py::SourceVersion`・
`lib/disclosures/model.py::DisclosureDocument`(Evidence層、D0049/D0050の
Bugが実際に存在した層)はいずれもtz-aware確認のみでこの順序を一切検査して
いない。**D0049/D0050のBugが2箇所で独立に発生し得た構造的根本原因は
ここにある。** ただし`available_at >= published_at`が全Sourceで常に真である
と断定してよいかはUser確認が必要な事項として残した(Open Question、下記)。

その他、Reviewer Agentの構造的Read-only化・Raw Snapshot Immutability・
UNKNOWN Basis既定除外・Entity Registry as-of解決・EDINET Raw/Canonical
Hash設計は、いずれも既に十分実装済み(`EXISTS`)であることを確認した。
PIT Compliance Test・Agent Governance Regression Test・Context分類・
Rule ID体系・Golden Prompt Parity Audit・Lab向けSystem Healthは`MISSING`
または`PARTIAL`であることを確認した(詳細は`PHASE4A5_1_PLAN.md` §A表)。

### Implementation Order(確定、次Round以降で実施)

ユーザー提示のCandidate Orderを、依存関係(Agent Governance/Hookは
独立で低Cost、Skill化はContext分類の後が安全、Forward Snapshot PoCは
User側の長期実行が必要で最後)に基づき一部並べ替えた:

```
4A.5.1-1  PIT Compliance Test Suite(新規 13_tests/test_pit_principles.py)
4A.5.1-2  Agent Governance Structural Tests
4A.5.1-3  Deterministic Hook: Protected Path Warning のみ
4A.5.1-4  Context Architecture 分類表
4A.5.1-5  Artifact Difference Workflow 一般化Doc
4A.5.1-6  Lightweight System Health 読み取り専用Script
4A.5.1-7  Golden Prompt Parity Audit
4A.5.1-8  Source Integration Skill v1
4A.5.1-9  Forward Snapshot PoC Procedure Doc(EDINET、実行はUser側)
```

### PIT Compliance Test Design(設計のみ、8件、`PHASE4A5_1_PLAN.md` §D)

既存Module別Testの重複を避け、Principle単体から導出されたTestのみを
新設`test_pit_principles.py`へ集める。最重要2件: `test_no_test_file_
asserts_the_pre_fix_available_at_equals_market_public_at_pattern`
(D0049/D0050のBugそのものの形を将来のTestが再びAssertしないことをGrep
ベースで機械的に保証するMeta-test)、および`test_unknown_availability_
boundary_15_03_vs_15_06_parametrized_across_fundamentals_and_disclosures`
(Fundamentals/Disclosures 2Moduleが将来分岐しないことを同一Parametrizeで
保証)。Current-State Leakage(Entity Registry)・Snapshot Overwriteは
既存Testで十分と判断し、重複追加しなかった(この判断根拠もPlanへ明記)。

### Hook Plan

Protected Path Warning(`core/`/`app.py`/`tests/`への編集を検知し
Warning、Blockはしない)のみを`Do Now`候補とした。Secret Guard(Commit時)
は既存`_assert_no_secret_like_keys`と`.gitignore`で主要経路は既にCover
されているため`SHOULD`止まり、Optional Phase Validationは既存PostToolUse
品質ゲートと機能重複するため`NOT_NOW`とした。

### Artifact Difference Workflow / Forward Snapshot

EDINETのRaw/Canonical Hash設計(D0046追記2)は既に実装済みで追加不要。
**TDnetは現状Document本体(PDF)を一切Fetchしていないことを実際に
確認した**(`tdnet_normalize.py`の`Docs`Fieldは`docs_raw`としてOpaque値の
まま保持するのみ)ため、一般化の対象コードが今は存在しない
(`NOT_NEEDED`、検討対象自体が無い)。Forward Snapshot PoCはProcedure
文書化のみこのPhaseの候補とし、実行はTDnet Add-on Local Validation後に
User側ローカル環境で行う。

### Open Question(User確認が必要)

`available_at >= published_at`をConstructor Levelで将来Rejectする設計へ
変更すべきか。Repositoryには「常に真であるべき」との明文原則は無く、
ユーザー自身が「Source semanticsによって成立し得る場合は勝手にinvalidと
決めない」と指示しているため、Main Claudeが独断で決めず次Round開始時に
確認する。このRoundではTripwire Test(現状Rejectしていないことを明示的に
記録するTest)として設計するに留め、Constructor自体は変更しない。

### このDecisionでやらないこと

コード実装・Schema変更・`.claude/settings.json`変更・`.claude/skills/`
変更・`.claude/agents/`変更・Test追加・Event Engine・Indexer・Replay
Architecture・大規模Observability Infrastructure・Phase4B-4(Company
IR)・TDnet Local Validationのいずれにも着手していない。Phase4B-3の
Status(`CODE_COMPLETE_AWAITING_ADDON_LOCAL_VALIDATION`)は変更していない。

### 追記 — pit-auditor Reviewの結果と訂正(Audit History)

上記Plan(`PHASE4A5_1_PLAN.md`)についてユーザー指示§19通り`pit-auditor`
Reviewを実施した。`PIT AUDIT: 7 FINDINGS(highest severity: HIGH)`。
全FindingをMain Claude自身が実Codeへ当たって検証し(Grep/Read)、7件
すべてCONFIRMEDと判定、Planへ反映した(コードは変更していない、Plan
Document自体の訂正のみ)。**このLabの方針「以前の判断が間違っていたこと
自体もAudit Historyとして残す」に従い、以下は隠さず記録する**:

1. **[HIGH、CONFIRMED]** Planは当初`phase-close`の`disable-model-
   invocation: true`を`EXISTS`(Machine Enforcement)としていたが誤り。
   実際にFrontmatterを確認したところ存在せず、Grepでも0件。**遡って
   確認したところ、D0046 §0で意図的に削除された経緯があった**
   (User以外がPhase Closeを正当に必要とする場合にHard Errorになる
   ことが判明したため、Access ControlからBody Text Guidanceへ変更
   済み)。D0044時点の記述をそのまま引き写し、D0046 §0による後続の
   訂正をこのPlan作成時にGrepし直さなかったことが原因。
2. **[HIGH、CONFIRMED]** Planは既存PostToolUse Hook(`post_edit_
   quality_gate.sh`)を単純に`EXISTS`とし、これを根拠に「Optional
   Phase Validation Hookは機能重複するためNOT_NOW」と結論していたが、
   実際にはこのHookのpytest行(line 26)は`tests/`(Root、既存
   Screening Tool)のみを実行し、`Japanese_Equity_Lab/13_tests/`は
   一度も実行しない。したがってこのPlanが提案するPIT Compliance
   Test Suiteを含むLabの全Testは、`/phase-close`をUserが明示的に
   呼ぶまで自動実行されない。
3. **[MEDIUM-HIGH、CONFIRMED]** Repository Reality Check(§A)が、
   `lib/fundamentals/normalize.py`・`lib/disclosures/normalize.py`
   両方に今も存在する`anchor = market_public_at if market_public_at
   is not None else retrieved_at`という既知のGuarded Gap(D0049
   §5-1で記録済み、`AvailabilityBasis.UNKNOWN`既定除外で安全)を
   見落としていた。D0049 §5-1をGrepし直さずPlanを書いたことが原因。
4. **[MEDIUM]** 提案Test T8(Meta-test、「Bugの形をAssertするTestが
   無いことを確認」)が、`test_fundamentals_evidence_pit.py`の既存
   Test(上記3の既知Gapを固定する回帰Test)と単純Grepでは衝突する
   ことを見落としていた。Allowlist設計を追記して解消。
5. **[MEDIUM、CONFIRMED]** 提案Test T4(Evidence層でのFuture
   Injection)が、既存`test_evidence_model.py::test_filter_usable_
   at_excludes_future_evidence`と重複することを見落としていた。
   MUST新規Testから除外(7件→7件、数値は変わらず内訳を訂正)。
6. **[LOW、CONFIRMED]** 些細な引用誤り3件(EDINET ZIP Test件数
   「18件」が実際は22件、Snapshot Overwrite Testの引用File名の
   取り違え、`AppendOnlyViolationError`の定義File取り違え)。

**このRoundでコードは一切変更していない**(訂正はすべて`PHASE4A5_1_
PLAN.md`本文と本追記のみ)。訂正の結果、次Round最優先Stepとして
`4A.5.1-0`(既存Hookのpytest行へLab `13_tests/`を追加する1行修正)を
新たにOpen Question付きで追加した(「Hook作成」への該当性は次Round
開始時にUser確認)。

## D0052 — Phase4A.5.1: Research Engineering Hardening 実装(D0051設計の実装)

D0051(設計固定)を基礎に、ユーザーがExternal Copilot Red Teamの
Findingを評価した最終判断(§1不採用5件・§2採用5件)を適用して実装した。
**コード実装・Test追加・Hook追加を含む(D0051は設計のみ、このRoundが
初めてコードを変更した)。**

### 不採用としたExternal Reviewer Finding(ユーザー指示§1、そのまま適用)

`retrieval_mode`/`retrieval_provenance`新Schema、Event Extractor/
Indexer Runtime Assertion、`EvidenceCandidate` Provisional Lifecycle、
Per-source Provider Timestamp Mapping新設、`is_usable_at`のEquality
Tie-breaker追加 — いずれも「現在のRepositoryに存在しないComponentを
新設してReviewer Findingを満たす」ことに該当するため実装しなかった
(CURRENT REPOSITORY REALITY > EXTERNAL REVIEWER CLAIMの原則)。

### 実装した Component(4A.5.1-0〜9、各Step 1 Commit)

- **4A.5.1-0**: `.claude/hooks/post_edit_quality_gate.sh`のpytest行が
  Root `tests/`のみを実行し`Japanese_Equity_Lab/13_tests/`を一度も
  実行していなかったCoverage Bugを1行修正(`bash 473e7f1`)。Existing
  Guardrail Coverage Bugfixとして扱い、Hook Architecture自体は
  再設計していない。
- **4A.5.1-1**: `13_tests/test_pit_principles.py`(新規、16件)。
  PIT-P01〜P07をArchitecture Principleから直接導出(実装Behaviorの
  コピーではない)。Fundamentals/Disclosures 2 Moduleを横断する
  Builder Registry構造により、将来3つ目のEvidence Moduleが増えても
  同じParametrizeが自動適用される設計(`bash d937b9c`)。
- **4A.5.1-2**: `13_tests/test_agent_governance.py`(新規、15件)。
  D0044の一度きり手動確認をPermanent Regression化。Model Behavior
  Testではなく`tools:`FrontmatterのDeterministic Propertyのみを検証
  (`bash bb15682`)。
- **4A.5.1-3**: `CLAUDE_CODE_RESEARCH_WORKFLOW.md`へContext
  Architecture分類表(ALWAYS/ON_DEMAND/TASK_ONLY/EVIDENCE_ONLY)を追記
  (`bash aaa0a38`)。
- **4A.5.1-4**: `.claude/skills/source-integration/SKILL.md`(新規)。
  PIT-001〜004・RAW-001〜003・EVIDENCE-001〜003・SOURCE-001〜005
  (最終、後述2件のGap対応込み)。全RuleがEDINET/TDnet実統合Incidentを
  出典として明記(`bash f968dad`)。
- **4A.5.1-5**: `GOLDEN_PROMPT_PARITY.md`(新規)。原Prompt逐語Textが
  このSession Contextに存在しないため`DECISIONS.md`を権威ある代替
  出典として使用する限定を明記した上で、22行(後に23行)の
  Requirement-by-Requirement Mapping実施(`bash 001dfd7`)。
- **4A.5.1-6**: `.claude/hooks/protected_path_warning.sh`(新規、
  Non-blocking)。`core/`/`app.py`/`tests/`編集時にWarning(`bash
  f1bb2e0`)。
- **4A.5.1-7/8**: `EDINET_LOCAL_VALIDATION_GUIDE.md` §J(Forward
  Snapshot PoC Procedure、実行はまだしない)・`DISCLOSURE_
  ARCHITECTURE.md`(Artifact Difference Workflow、EDINET原則の一般化と
  TDnetへの非適用理由)(`bash c4043ac`)。
- **4A.5.1-9**: `scripts/lab_source_health.py`(新規、Read-only診断
  Script)。既存`SourceCatalog`/`RawSnapshotStore`Manifestのみを読む、
  新規DB/Daemon/Server無し(`bash 775b2e0`)。

### Reviewer Pass(3回実施、全FindingをEvidence再確認の上で採否判定)

1. **pit-auditor(4A.5.1-1/2完了後、Checkpoint A)**: `3 FINDINGS`
   (最高MEDIUM)。全件CONFIRMED: (a)`*_basis`既定値確認TestがDocstring
   の「全て」主張に反し`DisclosureEnvelope`を含んでいなかった、(b)
   PIT-P05が`market_public_at=None`のみで検証しておりFallback Bug
   再発を検知できない構造だった、(c)Defense-in-depth Allowlist
   Heuristicの限界(Fail Closed方向のため実害無しと判断)。(a)(b)を
   修正(`bash 001dfd7`)。
2. **skeptic-reviewer(4A.5.1-4/5完了後、Checkpoint B)**: `PASS_WITH_
   CONCERNS`(2 MEDIUM、1 LOW)。全件CONFIRMED: (a)Auditスコープに
   明記していたD0047からの行が1件も無く、Publishing Entity/
   Disclosure System/Delivery Provider 3層分離(D0047 §3)が完全に
   漏れていた、(b)`RAW-002`の実文言がRaw Hash比較のみを対象とし
   時系列推測禁止を明文化していなかった、(c)出典のD0045/D0043の
   優先順位。`SOURCE-005`(3層分離)・`EVIDENCE-003`(時系列推測禁止の
   分離)を追加、出典を訂正(`bash e5a84be`)。
3. **pit-auditor(Phase Close前、最終Sweep)**: `1 FINDING`(MEDIUM)。
   CONFIRMED: `DISCLOSURE_ARCHITECTURE.md`「既知の限界」節が、TDnetの
   `market_public_at_basis`を`EXACT`と誤記載したまま(D0048追記の
   skeptic-reviewer Finding対応で実際には`UNKNOWN`へ修正済みだった
   にもかかわらず、この1節だけ未反映)。修正済み(`bash c67508c`)。
   このRoundで発生した新規Bugではなく、D0048時点からの既存Doc Drift
   をこのRoundのReview Scopeが偶然発見したもの。

**Audit Historyとしての記録**: 3回のReviewer Passいずれも複数の
CONFIRMED Findingを返し、その都度実Code/DECISIONS.mdへ当たって
検証した上で修正した。特にCheckpoint Bの発見(D0047からの行が0件)は、
「要件の落ちを見つけること」自体がこのGolden Prompt Parity Auditの
目的であったにもかかわらず、初版がまさにその種の落ちを1件出していた
ことを意味し、隠さず記録する。

### 最終回帰確認

`pytest`(Lab 588件・既存Screening Tool 37件、合計625件)・`ruff
check`・`ruff format --check`・`mypy`(83 source files)いずれもclean。
`git diff --stat -- core/ app.py tests/`で変更が無いことを確認済み
(全11 commit、`40ca140`から`c67508c`まで)。

### Completion Status

`COMPLETE`。Phase4A.5.1のCompletion Gate(ユーザー指示§11、11項目)を
満たしたと判断する: (1)Quality GateがLab 13_testsを実際にcover、
(2)Principle-based PIT Compliance Tests green、(3)Agent Governance
Structural Tests green、(4)Context Architecture明文化、(5)Source
Integration Skill v1完成、(6)Golden Prompt Parity Requirement Mapping
完成、(7)Reviewer Passで発見されたSemantic Loss(Gap)はすべて修正済み、
(8)必要なReviewer Pass(pit-auditor×2、skeptic-reviewer×1)完了、
(9)Artifact Difference Workflow明文化、(10)Forward Snapshot PoC
Procedure明文化、(11)Full Regression clean。Phase Complete必須外の
項目(Live EDINET Snapshot長期収集・TDnet Add-on Validation・Heavy
Hooks・新Provenance Schema・Event Engine・Indexer・Replay
Architecture)にはいずれも着手していない。

### このDecisionでやらないこと

Phase4B-4(Company IR)には着手していない。TDnetのStatus
(`CODE_COMPLETE_AWAITING_ADDON_LOCAL_VALIDATION`)は変更していない。
Golden Prompt Parity Auditの23行はDECISIONS.mdを代替出典として使った
限定版であり、真の逐語Prompt Parity監査ではない(このScope限定は
`GOLDEN_PROMPT_PARITY.md`冒頭に明記済み)。`SOURCE-005`
(3層分離)・`EVIDENCE-003`(時系列推測禁止)いずれも専用回帰Testは
まだ無く、次Round以降の追加候補として記録するに留めた。

## D0053 — Phase4B-4: Company IR Source Integration(Manual/User-specified URL First v1、Source Integration Skill v1のField Test)

D0052で構築した`.claude/skills/source-integration/SKILL.md`(v1)を、
旧来の巨大な設計Promptを再注入せずに使うことで、新しいSourceの統合でも
Research Integrityが保たれるかを実地検証する「Field Test」として実施
した。対象SourceはCompany IR(個別上場企業のIR Website)で、EDINET/TDnet
(規制当局・取引所が運営する単一の公開API)とは性質が異なり、企業ごとに
異なるWebsiteへの個別アクセスとなる。

### v1の基本方針: Manual / User-specified URL First

このRoundで実装したのは「URL入力 → Compliance確認 → 許可されていれば
Download → Raw Artifact保存 → Metadata/Provenance記録 → 必要ならCommon
Core接続」という単線Flowのみ。以下は明示的にこのRoundのScope外とし、
実装していない(ユーザー指示の禁止事項一覧をそのまま適用): 全上場企業を
対象にしたCrawler、検索エンジンCrawling、Google Scraping、Sitemap
全域Crawling、IR自動発見Engine、Selenium等Browser自動操作、無制限再帰
Crawling、robots.txt/利用規約Bypass、Cloudflare/CAPTCHA/ログイン壁
Bypass、高度なPDF意味解析、LLMによるEvent/強気弱気/売買判断、自動改版
検出、Company IR専用Event/News/Consensus/Portfolio Engine、監視Daemon・
Scheduler、大規模並列Agent。

### Source Identity(発行体・掲載Website・取得元・研究System)

Claimant/Issuer(実際に開示を行う上場企業自身)、Publishing Website
(そのIR Website)、Retrieval Source(実際にHTTP GETしたURL/Endpoint、
CDN含む)、Research System(このLab自身)の4者を区別する設計とした。
CDNやStorage経由のRedirectを企業自身と混同しない(下記Redirect
Safety参照)。

### Compliance First(Fail Closed、自動robots.txt/ToS解析Engineは作らない)

「Webで公開されている」ことは「自動取得・保存・再配布してよい」ことを
意味しない、という原則をArchitectureで強制するため、`ComplianceCheck
Result`(`terms_checked`/`robots_checked`/`automated_retrieval`/
`redistribution`/`retention`/`attribution_required`という各Status軸を
`ALLOWED`/`DISALLOWED`/`UNCLEAR`/`NOT_CHECKED`で持つDataclass)を
`fetch_document_raw()`の**必須引数**とした。あえて自動でrobots.txt/
利用規約をParse・判定するEngineを作らなかった(ユーザーが「不注意に
Common Coreへ追加しないよう警告」した設計判断そのもの)。`automated_
retrieval`が`ALLOWED`以外(`UNCLEAR`/`DISALLOWED`/`NOT_CHECKED`)であれば
`ComplianceError`を送出し、Network I/Oより前にFail Closedする
(`lib/disclosures/providers/company_ir.py`の`assert_retrieval_allowed()`、
IR-004/IR-005 Testで確認)。

### Retrieval v1(HTTP GET単発、Header Allowlist、Credential-like Query検出)

`CompanyIrAdapter.fetch_document_raw()`はHTTP GET 1回のみ実行する。
`requested_url`/`final_url`/`redirect_chain`/`requested_at`/
`retrieved_at`/`http_status`/`content_type`/`content_length_observed`/
`ETag`/`Last-Modified`をRaw Payloadへ記録するが、Headerは全件保存せず
Content-Type/Content-Length/ETag/Last-Modifiedのみを明示的にAllowlist
する(`_recorded_headers()`)。Fetch前にURLをScanし、Basic-Auth形式や
`token`/`key`/`secret`等Credential-likeなQuery Parameterを含むURLは
Compliance判定と同じくFail Closedで拒否する(`_assert_url_has_no_
credential_like_query_params()`、IR-013)。RawへSecret値そのものは
一切書き込まれない。

### Redirect Safety / Raw Artifact / Artifact Identity

Redirect自体は禁止しないが、`requested_url`(要求したURL)と`final_url`
(実際に到達したURL)、`requested_domain`/`final_domain`を常に分離して
Provenanceとして保持する(IR-006)。Raw Artifactは既存`RawSnapshotStore`
(Append-only)をそのまま再利用し、新規Storage機構は作らなかった
(IR-002)。Raw Hash(`raw_retrieval_hash`)の不一致はDocument改版を意味
しない(RAW-002をCompany IRでも遵守)。v1はFormat非依存のCanonicalizer
を作らず、安全なCanonicalizationが存在しない場合は`RAW_CHANGE_REQUIRES_
INSPECTION`とする方針を踏襲する(実際にCanonicalizerが必要になる
Container形式のDownloadをこのRoundでは行っていないため、対象コード自体
が無い)。

### PIT Semantics(market_public_at/provider_available_at/retrieved_at分離)

`build_company_ir_document()`は`provider_available_at`引数を**Signature
に一切持たない**設計にした(誤用が構造的に不可能、PIT-002/PIT-003の
「HTTP Last-Modifiedをprovider_available_atへ変換してはならない」を
Docstringだけでなく型で強制する)。`market_public_at`は呼び出し側が
明示的にEXACT Basisで確認済みTimestampを渡した場合のみ設定され、値が
無いのに`market_public_at_basis`だけEXACTにする矛盾状態は`ValueError`
でFail Closedする(IR-007)。HTTP Last-Modifiedは`CompanyIrDocument
Metadata.http_last_modified_raw`へOpaqueなstrとしてのみ保持し、
`datetime`へ変換しない(IR-008)。`retrieved_at`はSafe Lower Boundとして
Evidence変換時の`available_at`Fallback先になる(D0049/D0050で確立した
Common Core原則をそのまま再利用、新規Evidence変換関数は作らなかった、
IR-009/IR-014)。

### Historical PIT Limitation(明示的な限界)

今回Fetchが成功しても、そのDocumentが過去のある時刻に実際にCompany IR
Website上で取得可能だったことを遡って証明できない(Current Retrieval
!= Historical Website Snapshot)。将来必要になった場合はForward Snapshot
観測(D0051で設計したPoC)を使う設計とし、このRoundでは実装していない。

### Document != Evidence != Event

`document_kind`は常に`DocumentKind.UNKNOWN`に固定し、Title文字列から
Event種別を自動分類しない(IR-010)。`disclosure_document_to_evidence()`
(EDINET/TDnetと共通のCommon Core関数)をCompany IR専用の変更無しで再利用
できることを実際に確認した(D0045のProvider非依存設計Goalの実証)。
Evidence Contentにbullish/buy/好調等の解釈語が含まれないことをTestで
直接確認済み(IR-010)。

### Duplicate/Entity Mapping(保守的なFail Closed)

重複判定はExact Raw Hash一致のみを安全な自動候補とし、Title/日付/
Filenameの類似だけからの同一Document判定は行わない
(`company_ir_normalize.py`が`DocumentRelationship`/`DuplicateRelation
Kind`のいずれもImportしないことをIR-011で直接確認)。`entity_id`
(発行体識別)は呼び出し側が明示的に確認済み値を渡さない限り常に`None`
のまま(Ticker/CodeをCompany名文字列から推測しない、IR-014)。

### Common Core Integration

Company IR固有のSemantics(Compliance判定、Header Allowlist、Redirect
Domain区別)はAdapter/Normalizer層(`company_ir.py`/`company_ir_
normalize.py`)に閉じ込め、Common Core(`lib/disclosures/model.py`/
`evidence.py`)へは一切追加しなかった。Catalog登録は`build_company_ir_
dataset_descriptor()`(`implementation_status=SKELETON`、`pit_available=
False`、Known Limitationsを明記)のみ追加。

### Tests(IR-001〜IR-014、実装からのコピーではなくSkill v1 RuleからExpected値を導出)

`13_tests/test_company_ir_adapter.py`(14件)・`13_tests/test_company_
ir_normalize.py`(15件)、合計29件(Reviewer Pass後の追加2件を含む、後述)。
実Networkへの接続は一切行わず、FakeSession/FakeResponseのみ使用。

IR-003(Raw Hash Mismatch Is Not Revision)専用のTest関数は本Source
自身には存在しないが、Lab全体を横断するEDINET/TDnetでの既存構造Test
(`13_tests/test_pit_principles.py::test_defense_in_depth_provider_
normalizer_files_never_construct_document_relationship`、`lib/
disclosures/providers/*.py`をGlob)がCompany IRの2 File追加を自動的に
Coverしている(新規Testコード追加無しで、skeptic-reviewerが同種の指摘を
したIR-011と同じ形の「Lab全体の構造Testが自動拡張する」実例)。

### Reviewer Pass(pit-auditor 1回・skeptic-reviewer 1回、Findingsは全て独立に再確認の上で採否判定)

1. **pit-auditor**: `1 FINDING(highest severity: LOW)`。指摘: `build_
   company_ir_document()`がFetch Payloadから`ComplianceCheckResult`を
   再構築するがAudit Trail用のMetadataとしてのみ扱い、`automated_
   retrieval`の再確認を行っていない(`CompanyIrAdapter.fetch_document_
   raw()`を経由しない手組みのPayloadを渡された場合、Compliance未確認
   でもNormalize可能だった)。PIT/Timestampには影響しないためLOWと
   分類されたが、直接コードを読んで再確認した上で、この設計そのものが
   このLabの「構造的に誤用不可能にする」方針(RAW-001等と同じ)に
   反すると判断し修正した: `build_company_ir_document()`内で`assert_
   retrieval_allowed()`を再度呼ぶよう変更(`bash 2a30ad6`)。回帰Test
   1件追加。
2. **skeptic-reviewer**: `PASS_WITH_CONCERNS`。4件のFinding(MEDIUM x2、
   LOW x2)、いずれも独立に再確認した:
   - **[MEDIUM、採用・修正]** `ComplianceCheckResult`のFail Closed Gate
     (`assert_retrieval_allowed()`)が`automated_retrieval`のみを検査し、
     `terms_checked`/`robots_checked`がFalseのまま`automated_retrieval=
     ALLOWED`だけを主張する内部矛盾を防いでいなかった。実際に該当Codeを
     読み再確認の上、`ComplianceCheckResult.__post_init__`へ自己矛盾
     Guardを追加(`bash ee60c74`)。新しいrobots.txt/利用規約自動解析
     Engineを追加したわけではなく、既存4 Field間の単純な整合性Checkに
     留める設計とした(Reviewer自身もこの区別を明記済み)。
   - **[MEDIUM、採用]** Source Integration Skill v1(PIT-*/RAW-*/
     EVIDENCE-*/SOURCE-*)には、このRoundで実際に必要になったCompliance
     Gate・認証情報らしきURL拒否・HTTP Header Allowlistのいずれにも
     対応するRule IDが存在しなかった(実際にコード中の`Section N`引用が
     `SKILL.md`に存在しない番号体系を参照していることから、このGapが
     Skill自身ではなくRound個別のTask指示で埋められたことが直接確認
     できる、というReviewerの指摘を検証し確認した)。`COMPLY-001〜003`
     として`SKILL.md`へ追記した(`bash ee60c74`、詳細はSkill v1 Field
     Test節参照)。
   - **[LOW、対応せずKnown Limitationとして記録]** `entity_id=None`が
     既定の場合(Company IRでは典型)、既存Common Core`disclosure_
     document_to_evidence()`の`entity_id or internal_document_id`
     Fallbackにより`EvidenceRecord.related_codes`が空Tupleになる。
     これはEDINET/TDnetと共有するCommon Core側の既存挙動であり
     Company IR固有のBugではないため、このRoundではCommon Coreを変更
     しない(Company IR固有Semanticsをこのタイミングで一般Common Core
     へ押し込まない、という本Round自身の原則に反するため)。下記Known
     Limitationsに明記。
   - **[LOW、対応不要と判断]** Test ID `IR-003`が単独のTest関数として
     存在しない点の指摘。上記Tests節に説明を追記した(既存Lab全体構造
     Testが自動的にCoverしているため、専用Test追加は不要と判断)。

### Live/Local Validation: このRoundではLive Fetchを一度も試みていない(意図的)

EDINET/TDnetのRoundとは異なり、このRound自身はCompany IR Websiteへの
`curl`等によるLive接続確認を一度も行っていない。理由: EDINET/TDnetは
単一の公開制度APIであり確認対象は接続性のみだったが、Company IRは
企業ごとに異なるWebsiteであり、robots.txt/利用規約を確認しないまま
特定企業のURLへFetchすること自体がこのRound自身が課した`Compliance
CheckResult`原則(未確認ならFail Closed)に反するため。したがって
`COMPANY_IR_LOCAL_VALIDATION_GUIDE.md`はFixture-based Validationのみを
実施し、実在URLへのLive Validationは、Userが個別に対象企業のrobots.txt/
利用規約を確認した上でローカル環境で行うことを前提とする手順のみを
提供した。`implementation_status=SKELETON`のまま(EDINETの`CONNECTED`・
TDnetの`NOT_IMPLEMENTED`いずれとも異なる、実コードはあり疑似Sessionで
Test済みだが実SiteへのLive到達は未実施という中間状態)。

### Source Integration Skill v1 Field Test結果(隠さず記録)

過去の巨大な設計Promptを再注入せず、`SKILL.md`(v1)+ このRound個別の
Task指示のみでCompany IRを実装した結果:

- **A. Skillだけで保たれたRule**: PIT-001〜004(UNKNOWN非0/market_
  public_at!=provider_available_at/market_public_atへのFallback禁止/
  retrieved_atのSafe Lower Bound位置付け)、RAW-001〜002(Immutable・
  Hash不一致からのRevision推測禁止)、EVIDENCE-001〜002(Document!=
  Evidence!=Event・解釈語禁止)、SOURCE-001〜002(推測禁止・Ephemeral
  URL非永続識別子扱い、Company IRでは該当挙動自体は無いが原則として
  適用)。いずれもSkillのRule ID単体を読むだけで、旧Promptを再確認する
  ことなく設計・実装できた。
- **B. Skillに無く、このRound個別のTask指示で追加確認が必要だった
  Rule**: Compliance Gate(robots.txt/利用規約Fail Closed)・認証情報
  らしきURL拒否・HTTP Header Allowlist(いずれも今回のskeptic-reviewer
  Findingで正式に確認された、上記COMPLY-*参照)。
- **C. Company IR固有の事情 vs D. 一般的なSkill Gap**: Bで見つかった
  Gapは**一般的なSkill Gap**と判定した(Company IR固有の事情ではない
  — 将来Newsサイト・Blog等、規制当局が運営しない任意のWebsiteを
  Sourceとする場合には必ず同様のCompliance判断が必要になるため)。
  Company IR固有の事情としては、`publishing_entity`と`disclosure_
  system`(Venue)が同一主体(発行体自身)になるという`DISCLOSURE_
  ARCHITECTURE.md`追記(本Decision冒頭のCommit`ecfb634`参照)のみ。
- **E. Skill v1.1の必要性**: 上記Bを`COMPLY-001〜003`として本Round内で
  既に`SKILL.md`へ反映済み(次Round以降ではv1.1相当の内容を含んだ状態
  から開始できる)。
- **F. Golden Prompt Parity(`GOLDEN_PROMPT_PARITY.md`)への影響**:
  当該Docは4A.5.1-5時点のRequirement-by-Requirement Mappingであり、
  Company IRはそのAudit後に追加されたSourceのため対象外。次回Golden
  Prompt Parity Auditを行う際は`COMPLY-*`も対象へ含める必要がある
  (このRoundでは`GOLDEN_PROMPT_PARITY.md`自体は更新しない、Scope外)。

### Known Limitations

- 実在のCompany IR Websiteへ、このSession・Userのローカル環境いずれ
  からもLive Fetchを一度も実施していない(`implementation_status=
  SKELETON`のまま)。
- Company IR専用の診断Script(EDINET/TDnetのような)は未作成
  (`COMPANY_IR_LOCAL_VALIDATION_GUIDE.md` §F)。
- Compliance確認(robots.txt/利用規約)を自動化する仕組みをこのLabは
  持たない(意図的な設計判断)。どの企業が実際にAutomated Retrievalを
  許可しているかの一覧・DatabaseもこのLabは持たない。
- `entity_id=None`が既定の場合、`disclosure_document_to_evidence()`
  (Common Core、EDINET/TDnetと共有)の既存Fallback挙動により
  `EvidenceRecord.related_codes`が空Tupleになる(skeptic-reviewer
  Finding、上記参照)。Company IR固有の新規Bugではなく、Common Core
  側の既存挙動をこのRoundでは変更しない。
- Historical PIT Reconstructionはできない(今Company IR Pageを取得
  しても、そのDocumentが過去のある時刻から実際にWebsite上で取得可能
  だったことを遡って証明できない)。
- `scripts/lab_source_health.py`のCompany IR向け拡張はこのRoundでは
  行っていない(§31相当、低Cost拡張の余地はあるが本Round Scope外とし、
  Known Limitationとして記録するに留めた)。

### このDecisionでやらないこと

Phase4B-4のCompletion Report後、次Phaseへ進むことなく完全に停止する。
TDnetのStatus(`CODE_COMPLETE_AWAITING_ADDON_LOCAL_VALIDATION`)は
変更していない。Company IRをEvent Engine/News Engine/Monitoring
Engine/全企業Crawlerへ拡張する作業には一切着手していない。

## D0053 追記 — Phase4B-4: Local Live Validation Round、このSessionからのEgress確認結果(EGRESS_BLOCKED)

D0053完了後、ユーザーからLocal Live Validation Round開始の指示があり、
実際にCompany IR URLへのLive Fetchを試みる前段階として、このSession
自身のNetwork Egress可否を先に確認した(D0046/D0047のEDINET/TDnet
Roundと同じ手順)。

### 確認方法と結果

`curl`で以下2件へ接続を試行した:

1. `https://www.google.com/` → `CONNECT tunnel failed, response 403`
2. `https://global.toyota/en/robots.txt`(Live Validation Candidateとして
   検討していた実企業Domainの1つ、Toyota Global IR) → 同じく`CONNECT
   tunnel failed, response 403`

対照として、既知にAllowlistされているHost(`https://pypi.org/`)への
接続は`HTTP_CODE:200`で成功した。Agent Proxy自身の`/__agentproxy/
status`Endpointも`recentRelayFailures`として`connect_rejected`
(`"gateway answered 403 to CONNECT (policy denial or upstream
failure)"`、対象`www.google.com:443`)を記録しており、これは特定の
Company IR Siteに固有の問題ではなく、このSession自体の組織Egress
Policyが任意の外部Host(Company IR Domain含む)への接続を一貫して
拒否していることを意味する。

`/root/.ccr/README.md`(Agent Proxy自身のTroubleshooting Doc)は
「403/407はOrganizationのEgress Policyによる拒否であり、retryや
回避策を試みず、Blockされた事実を報告すること」と明記しているため、
これ以上の接続試行(WebFetch等別経路での回避を含む)は行わなかった。

### このRoundでの結論

- **Compliance確認(robots.txt/利用規約)以前に、このSession自体が
  Company IR Websiteへ技術的に到達できない**(D0046/D0047のEDINET/
  TDnetと同種の`EGRESS_BLOCKED`)。したがってPre-Fetch Compliance
  Report(§4)・Live Fetch(§5)・Offline Replay(§8)・PIT Proof
  (§9)のいずれも実施していない(実施していないことを実施したかの
  ように記録しない、Documentation Integrity原則)。
- 実装Code(`company_ir.py`/`company_ir_normalize.py`)・Test・Skill
  (`COMPLY-001〜003`)への変更は本Roundでは行っていない(Live Fetchが
  一度も実行できていないため、Live Failureから見つかったRegression
  Testも無い)。
- `lib/disclosures/catalog.py`の`build_company_ir_dataset_descriptor()`
  `known_limitations`へ、この確認結果を追記した。
- pit-auditor/skeptic-reviewerはこのRoundでは実行していない(Code/
  Architecture変更が無いため、Reviewer起動コストをかける対象が無い、
  ユーザー指示§14の「小規模Validationで既存Architecture変更が無ければ
  不要なReviewer大量起動はしない」に従う)。

### Completion Classification(ユーザー指示§16準拠)

A〜Dのいずれにも厳密には該当しない(A〜DはいずれもCompliance確認
(robots.txt/利用規約)の可否を前提とした分類だが、本Roundの実際の
制約はそれ以前のNetwork Egress自体である)。最も近い記述は
**B相当だが理由が異なる**: `CODE_COMPLETE_AWAITING_LOCAL_LIVE_
VALIDATION`のまま変更しない(Statusは変更不要、Company IR Catalogの
`implementation_status=SKELETON`も変更しない)。TDnetのStatus
(`CODE_COMPLETE_AWAITING_ADDON_LOCAL_VALIDATION`)は変更していない。

### このDecisionでやらないこと

Crawler化・Company IR Monitoring・PDF Semantic Extraction・Phase4Cへの
着手はいずれも行っていない。TDnet Local Validationも同時に開始して
いない。

## D0054 — Phase4C: Positioning / Supply-Demand Data Foundation(設計・実装)

Positioning/需給Data(信用取引・空売り・投資部門別売買・株主構成等)を
PIT-safe/source-aware/reproducibleな形でこのLabへ取り込むためのData
Foundationを新設した。**Investment Signal(Short Squeeze Score等)・
BUY/SELL判定は一切実装していない**(Data Foundationまで、Phase4C要件
§1/§21)。

### Repository Reality Check

既存`lib.evidence.model`(`RevisionHistory`/`SourceVersion`/
`AvailabilityBasis`/`AvailabilitySemantics`/`ValueAvailability`)・
`lib.fundamentals`(Envelope+Metric分離・`build_revision_histories()`・
`fundamentals_as_of()`パターン)・`lib.schemas.price_data`
(`RawOHLCVBar`/`AdjustedOHLCVBar`、`session_close_at`によるAvailability
規約、`apply_split_adjustments_as_of`等のCorporate Action PIT機構)・
`lib.sources.entity_registry`(PIT-aware Identifier Mapping)を先に確認
した。`lib.sources.catalog.DataCapability.POSITIONING`は既にPhase3D
(D0040)時点で列挙型として存在していた(未使用のまま)。

### Source Candidate Research(data-source-researcher Agent、2026-08-18)

J-Quants V2の`weekly_margin_interest`(信用取引週末残高)・`short-ratio`
(業種別空売り比率)・`short-sale-report`(個別銘柄空売り残高報告)・
`trades_spec`(投資部門別売買状況)、およびJPX直接公開Websiteを調査した。
結果は全てSEARCH-SNIPPET-DERIVED(UNVERIFIED)——このSession自身の
Network Egressが組織Policyにより公式Document URLへ一貫してBlockされて
おり(`EDINET_SOURCE_ONBOARDING.md`と同じ制約)、WebFetchは全て失敗した。
Endpoint Path自体が矛盾する検索結果(`short-sale-report`)、Plan Tier
情報が単一の未検証情報源のみ(`trades_spec`のLight Plan利用可能性)、
Publication Lagが4候補いずれも不明、という状態だった。詳細は
`POSITIONING_ARCHITECTURE.md`「Source候補」節・`VALIDATION_BACKLOG.md`
参照。

### 実装したSource #1のみ、Source #2は明示的に見送り

Candidate Sourceを検証した結果、確信を持って実装できるのは
**Price/Volume-derived Liquidity Metric**(既存J-Quants Price Bar
Connection、Adapter/Field名の新規推測不要)のみと判断した。J-Quants
Positioning Endpoint群はField名・Wire Schema・Publication Lag・Endpoint
Pathのいずれも未確認であり、この状態で実装するとFundamentals(Phase4A)
で実際に発生したField名推測ミスと同種のRiskを繰り返す(Phase4Cユーザー
要件§5「推測禁止」・§28「Specが確認できないFieldはUNKNOWN」に反する)。
ユーザー自身の完了基準(§42-3)が「可能なら2系統目も統合、ただし
Qualityを犠牲にしない」と明示的に許容していたため、Source #2は
`NOT_IMPLEMENTED`のCatalog登録(4件、`lib/positioning/catalog.py`)と
`VALIDATION_BACKLOG.md`への記録のみに留めた。

### Common Positioning Model(新規Versioning機構は作らない)

`lib/positioning/model.py`の`PositioningRecord`はLong-form 1レコード
(entity × metric × period × source)。PIT/Revision管理は`lib.evidence.
model.RevisionHistory`/`SourceVersion`をそのまま再利用し、Positioning
専用の新しいVersioning Primitiveは作らなかった(Fundamentalsと同一の
Primitive)。`lib/positioning/normalize.py`の`build_revision_histories()`
はSource非依存であり、Source固有のAvailability Semanticsは呼び出し側が
`resolve_available_at`Callbackとして渡す設計(normalize.py自身はどの
Sourceの`available_at`計算方法も知らない、将来Source追加時にnormalize.py
を変更する必要が無いようにするため)。

`metric_type`(例: `TURNOVER_VALUE`、`VOLUME_MOVING_AVERAGE_20D`)は
Source固有のまま保持し、共通Scoreへ潰さない(ユーザー要件§31)。

### Source #1: Price/Volume-derived Liquidity(`lib/positioning/derived/price_derived.py`)

`TURNOVER_VALUE`(売買代金、close×volume、未調整`RawOHLCVBar`から単日
算出)と`VOLUME_MOVING_AVERAGE_ND`(トレーリングN日平均出来高、株式分割
調整済み`AdjustedOHLCVBar`から算出、`window`/`minimum_periods`を明示
Parameter化、既定は満window必須)を実装した。Availability(いつ利用可能に
なったか)は`session_close_at(observation_end)`を`AvailabilityBasis.
INFERRED`として使う——これは新しい規約ではなく、既存`lib.schemas.
price_data.provider_event_available_at()`(AdjFactor Corporate Action
Eventの利用可能時刻)や`BacktestEngine`が既に`PointInTimeRecord.
available_at`として採用している確立済みの規約をそのまま再利用したもの。
`market_public_at`は常に`None`/`UNKNOWN`(価格取引そのものに個別の
公表時刻という概念が無いため、確認できないTimestampを推測で埋めない)。

### Evidence Layer(Common Core、新規Primitiveなし)

`lib/positioning/evidence.py`の`positioning_record_to_evidence()`は
`lib.fundamentals.evidence.disclosure_metric_to_evidence()`と同じ
D0049/D0050 PIT Bugfix方針を踏襲する: `source.available_at`には常に
`record.retrieved_at`(Observed Factとしての下限)を使い、
`market_public_at`へのFallbackは行わない。`EvidenceRecord`/
`SourceMetadata`(`lib.evidence.model`)を変更なしで再利用した(Company
IR・Fundamentalsに続き、Provider非依存Common Core設計の3件目の実証)。

### Tests(POS-001〜012、実装からのコピーではなくPhase4C要件から導出)

`13_tests/test_positioning_model.py`(7件)・`test_positioning_price_
derived.py`(13件)・`test_positioning_pit.py`(13件)、合計33件を新規
追加。実Network接続無し、合成Bar Dataのみ使用。Reviewer Pass後、
skeptic-reviewer指摘への対応として`test_positioning_catalog.py`
(7件)を追加、最終合計40件(下記Reviewer Pass節参照)。

### Documentation

`POSITIONING_ARCHITECTURE.md`(新規)・`VALIDATION_BACKLOG.md`(新規、
既存TDnet/Company IR/EDINET Backlog項目 + 新規Positioning候補4件 +
Source #1自身のLocal Real Data Validation未実施を一覧化、重複管理を
避けるため各項目のAuthoritative Docへのリンクのみ保持)。

### このDecisionでやらないこと

J-Quants Positioning Endpoint(信用取引・空売り・投資部門別売買)の
Adapter実装、JPX直接Sourceの実装、いずれも着手していない
(`NOT_IMPLEMENTED`のまま)。Investment Signal化(Short Squeeze Score
等)・Expectations Engine・Portfolio Sizingには一切着手していない。
Continuous Monitoring/Scheduler/Alertは実装していない。

### Reviewer Pass(pit-auditor 1回・skeptic-reviewer 1回、Findingsは全て独立に再確認の上で採否判定)

1. **pit-auditor**: `CLEAN`(Finding無し)。9項目全て(Publication Lag/
   Period-end Leakage・Current-state Leakage・UNKNOWN Fallback・Revision
   誤用・Entity Mapping・Frequency・Determinism・`AvailabilityBasis.
   INFERRED`の妥当性・Regression Scope)を確認済みとして報告。Regression
   確認については「Bash Toolが無くGit Diffを自身で実行できない」という
   限定を自己申告していたため、`git diff --stat`で該当範囲外に変更が
   無いことを別途直接確認した(Company IR/EDINET Roundと同じ手順)。
2. **skeptic-reviewer**: `PASS_WITH_CONCERNS`。7件のFinding(MEDIUM x2、
   LOW-MEDIUM x1、LOW x4)、いずれも独立に再確認した:
   - **[MEDIUM、採用・修正]** `lib/positioning/catalog.py`の5つの
     Descriptor Builderに専用Testが1件も無かった(`lib.fundamentals.
     catalog`/`lib.disclosures.catalog`には`SourceCatalog`統合Testが
     存在する既存慣行から外れていた、CLAUDE.md「新機能・バグ修正には
     必ずテストを追加する」にも反する)。実際にGrepで確認の上、
     `13_tests/test_positioning_catalog.py`(新規7件)を追加した。
   - **[MEDIUM、Decision記録として採用・コード変更はせず]**
     `lib/positioning/normalize.py`の`AvailableAtResolver`Callback
     抽象化(Source固有Availability計算を呼び出し側へ委譲する設計)は、
     `lib.fundamentals.normalize.build_revision_histories()`(固定の
     内部関数`_provider_available_at_and_basis()`を直接呼ぶのみ)の
     単純な再利用ではなく、このRound自身が導入した新しい一般化である、
     という指摘を確認した(実際に非Test呼び出し元は`price_derived.
     resolve_available_at`の1つのみ)。ここに明記する: これは
     Fundamentalsパターンの単純な再利用の主張ではなく、D0054が既に
     Source #2以降(信用取引・空売り・投資部門別売買)それぞれが
     Price-derived Metricとは全く異なるAvailability Semanticsを持ちうる
     ことを見越した意図的な先行一般化である。抽象化自体はCallback 1個の
     追加のみで新しいClass/Schemaを伴わないため、過剰設計とまでは判断
     しなかった(コード変更は行わない)。
   - **[LOW-MEDIUM、Known Limitationとして記録、コード変更はせず]**
     `build_revision_histories()`を同一`series_id`+同一`observation_
     end`のRecordに対して複数回(再処理等で)呼び出した場合、`resolve_
     available_at()`が`observation_end`のみに依存し`retrieved_at`を
     見ないため、`available_at`が同一Timestampになる複数`SourceVersion`
     が生じうる。`RevisionHistory.as_of()`のTie-break(`max()`、Python
     の実装上先勝ち)がList結合順序に依存してしまう、という指摘を確認
     した。この問題は`RevisionHistory`自体(Fundamentalsも含め全Source
     共通のPrimitive)に内在する既存の一般的挙動であり、Positioning固有の
     新規Bugではない。このRoundでは実際の再取り込みPipeline/Scriptを
     一切実装していない(Data Foundationのみ、Ingestion Glueは範囲外)
     ため、この問題が実際に発現する呼び出し経路が現時点で存在しない。
     Known Limitationとして記録するに留め、Ingestion Pipeline実装時に
     再検討する。
   - **[LOW、Known Limitationとして記録]** `build_volume_moving_
     average_records()`が入力`bars`内の`session_date`重複を検証しない
     (重複があれば移動平均へ二重計上されうる)。このLab内の他の価格Bar
     消費関数も同様に「呼び出し元が既に重複排除済み」という前提に立って
     おり(System Boundary以外での検証を追加しない、CLAUDE.md方針)、
     Positioning固有の新規問題ではないと判断し、コード変更はせず前提を
     明記するに留めた。
   - **[LOW、対応不要と判断]** `evidence.py`の`retrieved_at`が
     `session_close_at`より前である可能性を検証していない点、
     `PRICE_DERIVED`と`jquants`という異なる`source_id`がCatalog上で
     Source数の誤解を招きうる点、`VALIDATION_BACKLOG.md`が各行で
     「阻害要因」欄に短い要約を含めている点——いずれもReviewer自身が
     「既存の開示された設計判断」「Catalog UXの観察に留まる」「1行要約は
     許容範囲」と評価しており、独立確認の上で対応不要と判断した。

### 追加Known Limitations(Reviewer Pass後)

- `build_revision_histories()`を同一Series+同一観測期間終了日に対して
  複数回呼び出した場合のTie-break挙動(List結合順序依存)は未対応。
  実際のIngestion Pipelineを実装する際に再検討が必要。
- `build_volume_moving_average_records()`は入力Bar列の`session_date`
  重複を検証しない(上流が重複排除済みという前提)。
- `lib/positioning/catalog.py`の5 Descriptorは`SourceCatalog`への
  実際のWiring(Application起動時の一元登録)がまだ無い(Fundamentals/
  Disclosuresと同じく、既存の慣行のまま)。

## D0055 — Phase4D: Japan Macro Data Foundation(設計、Adapter未実装)

日本のMacro/Economic Data(CPI・GDP・失業率・賃金・政策金利等)を
PIT-safe/revision-aware/reproducibleな形でこのLabへ取り込むためのData
Foundationを新設した。**Economic Forecast・Regime Detection・BUY/SELL
判断は一切実装していない**(Observationまで、Phase4D要件§1/§2)。

### 事前の補足指示(このRound開始直前にユーザーから受領)

External Copilot Reviewが再度Phase4A.5.1へのFIX_BEFORE_IMPLEMENTATION
指摘を行ったが、ユーザーの明示的判断により再オープンしなかった。5件の
指摘(retrieval_mode/retrieval_provenance・EvidenceCandidate provisional
lifecycle・Event Extractor/Indexer runtime assertions・TDnet/EDINET/
J-Quants provider timestamp semantics mapping・available_at==as_ofの
新Tie-breaker)はいずれも「現在Repositoryに存在しないComponentへの
言及」を理由に自動採用しないことが明示され、Reviewer Evidence Standard
(CONFIRMEDには具体的File/Function/Execution Path/Trigger/Impact/
Detectionが必要、"存在するはず"だけでは不可)がこのRound全体に適用される
ことが再確認された。Golden Prompt PartyのRequirement-by-Requirement +
Negative Requirement追跡強化はFuture Improvement Candidateとして記録する
のみに留め、このRound自体のBlockerにはしない。

### Repository Reality Check

`lib.evidence.model`(`RevisionHistory`/`SourceVersion`/`AvailabilityBasis`
/`ValueAvailability`)・`lib.fundamentals`/`lib.positioning`(Phase4Cで
確立したLong-form Record + Source非依存`build_revision_histories()`
Callback Pattern)を先に確認した。

### Source Candidate Research(data-source-researcher Agent、2026-08-18)

e-Stat(CPI・労働力調査)・日本銀行(政策金利)・内閣府/ESRI(GDP QE)・
厚生労働省(賃金)の5候補を調査した。結果は全てSEARCH-SNIPPET-DERIVED
(UNVERIFIED)——このSession自身のNetwork Egressが`e-stat.go.jp`/
`boj.or.jp`/`esri.cao.go.jp`/`mof.go.jp`等の公式Document URLへ一貫して
Blockされており(curlで直接再確認済み、`EDINET_SOURCE_ONBOARDING.md`と
同じ制約)、WebFetchは全て失敗した。最重要のPIT論点(Vintage/Revision-
History問い合わせ機構の有無)についても、5候補いずれからも確証が得られ
なかった(Inconclusive、Leaning Negative——判明したのはBase Year改定時の
「接続指数」によるRebasing/Continuity Patchであり、Vintage Archiveとは
別物)。詳細は`MACRO_ARCHITECTURE.md`「Source候補」節・`VALIDATION_
BACKLOG.md`参照。

### Adapterは1件も実装しない(ユーザー要件§33に基づく正直なStatus)

検索Snippetのみを根拠にAdapterを実装しない、というユーザー要件§33に
従い、このRoundでは5候補全てを`implementation_status=NOT_IMPLEMENTED`
のまま`lib/macro/catalog.py`へ登録し、Validation Status=`DESIGN_
COMPLETE_AWAITING_SPEC_VERIFICATION`を`known_limitations`へ明記した
(Positioning Phase4Cの`NOT_IMPLEMENTED`+Validation Status自由記述
Patternをそのまま踏襲、新規Schema変更は行わない)。

### Common Macro Model(新規Versioning機構は作らない)

`lib/macro/model.py`の`MacroRecord`はLong-form 1レコード
(series × reference_period × source)。PositioningがEntity中心
だったのに対し、MacroはSeries Identity中心になる(§23)ため、
Entity固有Fieldは持たず`series_code`(Provider公式識別子、未確認なら
`None`)を持つ。PIT/Revision管理は`lib.evidence.model.RevisionHistory`/
`SourceVersion`をそのまま再利用し、Macro専用の新しいVersioning
Primitiveは作らなかった(Fundamentals/Positioningと同一のPrimitive)。

**Vintage(1次速報 -> 2次速報 -> 確報)は新概念を発明せず、既存
`SourceVersion`の系列としてそのまま表現できる**、という設計判断が
このRoundの中心的な発見だった。`vintage_label`はSourceが明示的に確認
できた場合のみ保持する自由記述Fieldとし、公開順序だけからの推測は
禁止する(EVIDENCE-003と同じ原則)。

`lib/macro/normalize.py`の`build_revision_histories()`は`lib.
positioning.normalize`と同型のSource非依存`resolve_available_at`
Callback Patternを踏襲する。ただし意図的に**コードとしては共有せず
個別実装**とした——`PositioningRecord.observation_end`と`MacroRecord.
reference_period_end`のようにField名が異なるため、無理にProtocol
抽象化で共通化するとかえって複雑になると判断した(External Copilot
Reviewが直前に警告した「推測だけでArchitectureを増やさない」という
指示にも沿う、過剰な汎用化を避ける判断)。

### Frequency Common Core昇格

`lib.positioning.model.Frequency`はDAILY/WEEKLY/MONTHLY/EVENT_DRIVEN/
UNKNOWNのみで、MacroがGDP(QUARTERLY)等に必要とするMembershipを欠いて
いた。第2の意味が食い違いうるFrequency Enumを`lib/macro`側へ複製する
ことは、このLabがRevisionHistory/SourceVersionについて一貫して避けて
きた「同じ意味のPrimitiveを複数持たない」原則に反する。したがって
`Frequency`を`lib.evidence.model`(Common Core)へ昇格し、QUARTERLY/
ANNUALを追加した(値の意味変更は無し)。`lib.positioning.model`は
Re-exportにより既存呼び出し元との互換性を維持する。既存Positioning
Testを1件、新しいMembership全体を確認する形へ更新した(完全一致
Assertionから部分集合Assertionへ変更)。

### Evidence Layer(Common Core、新規Primitiveなし)

`lib/macro/evidence.py`の`macro_record_to_evidence()`はFundamentals/
Positioningと同じD0049/D0050 PIT Bugfix方針を踏襲する:
`source.available_at`には常に`record.retrieved_at`を使い、
`market_public_at`へのFallbackは行わない。`EvidenceRecord`/
`SourceMetadata`を変更なしで再利用した(Company IR・Fundamentals・
Positioningに続き、Provider非依存Common Core設計の4件目の実証)。

### Tests(MACRO-001〜015、実装からのコピーではなくPhase4D要件から導出)

`13_tests/test_macro_model.py`(12件)・`test_macro_pit.py`(21件)・
`test_macro_catalog.py`(7件)、合計40件を新規追加。実Network接続無し、
合成Record Dataのみ使用。Phase4C(Positioning)のskeptic-reviewer
Findingで「Catalog Descriptor群にTest Coverageが無かった」Gapが指摘
された教訓を活かし、このRoundは最初からCatalog Testを含めた。

### Source Integration Skill v1 Field Test

- **A. Skillだけで守れたRule**: PIT-001〜004(UNKNOWN非0/`market_public_
  at`優先Fallback禁止/`retrieved_at`のSafe Lower Bound位置付け)・
  RAW-002(Hash不一致からのRevision推測禁止)・EVIDENCE-001〜003
  (Document != Evidence != Event、時系列だけからのRelationship推測禁止)
  ・SOURCE-001(Source固有Field意味論を推測しない)——いずれもSkill単体で
  Positioning Phase4Cの経験を踏まえた設計をそのまま踏襲できた。
- **B. Macro固有で追加確認が必要だったRule**: Vintage/Revision Stage
  (Preliminary/Second Preliminary/Final)の扱い方(既存`SourceVersion`で
  表現できるという判断自体はSkillに無く、このRound自身の設計判断)、
  Reference Period vs Release Timingの分離(既存PIT-*Ruleの一般化として
  導出可能だったが、Macro固有の用語[Quarter Leakage等]はUser Task指示
  から得た)。
- **C. Macro固有の事情 vs D. 一般的なSkill Gap**: 上記Bは**Macro固有の
  事情**と判定した(Vintage概念自体は他Sourceには無い、Disclosure/
  Positioningでは複数Versionの意味が「訂正」or「別Metric」のいずれか
  だったが、Macroでは「同一測定対象の精度向上」という第3の意味を持つ
  ため)。ただし「複数Version = 既存RevisionHistoryで表現可能」という
  判断パターン自体は今後他Sourceにも再利用できる可能性があり、Concrete
  Evidence(今回のMacro実例)を伴う一般化候補として記録するに留める
  (このRoundではSkill本文への追記は行わない、Evidence不足のPreliminary
  な段階のため)。
- **E. Skill v1.1の必要性**: 無し(このRoundでは新規Rule追加を行わな
  かった、上記Cの判断)。
- **F. Golden Prompt Parityへの影響**: 無し(このRoundはSkillを変更して
  いない)。

### Known Limitations

- Adapterを1件も実装していない(5候補全て`NOT_IMPLEMENTED`、Validation
  Status=`DESIGN_COMPLETE_AWAITING_SPEC_VERIFICATION`)。
- e-Stat/BOJ/ESRI/総務省/厚労省いずれも公式仕様をこのSessionから直接
  確認できていない(`EGRESS_BLOCKED`、curlで直接再確認済み)。
- Vintage/Revision-History問い合わせ機構の有無(Q5、最重要PIT論点)は
  5候補いずれについてもInconclusive(Leaning Negative)のまま。
- `lib/macro/normalize.py`の`build_revision_histories()`は`lib.
  positioning.normalize`と意図的にコード非共有(Field名の違いにより
  Protocol抽象化はPremature Generalizationと判断)。
- `lib/macro/catalog.py`の5 Descriptorは`SourceCatalog`への実際の
  Wiring(Application起動時の一元登録)がまだ無い(既存の慣行のまま)。
- Forward Snapshot Collector(Vintage観測用)は未実装(Procedure/将来
  要件としてのみ`MACRO_ARCHITECTURE.md`に記録)。

### Reviewer Pass(pit-auditor 1回・skeptic-reviewer 1回、Findingsは全て独立に再確認の上で採否判定)

1. **pit-auditor**: `1 FINDING(highest severity: LOW)`。指摘: `lib.
   evidence.model.RevisionHistory.as_of()`の`max(candidates, key=...)`
   Tie-breakは、複数Versionが同一`available_at`に並んだ場合Python
   `max()`の仕様上「Listで最初に出現した候補」を返す(1次速報・2次速報が
   Date-only Granularityにより偶然同一`available_at`へ解決される場合、
   どちらが返るかはRecordの投入順序に依存する)。実際にコードを読み
   `lib/evidence/model.py:222`の`max()`呼び出しを直接確認した上で、
   Phase4C(Positioning)で発見された同種のTie-break Gapと同一のFinding
   分類(全Capability共通のCommon Core Primitiveの既存挙動であり、この
   Roundが持ち込んだ新規Bugではない)と判断し、Common Core自体の変更は
   行わず、現在の挙動(投入順序依存)を明示的に固定するTestを追加した
   (`test_tie_on_identical_available_at_is_input_order_dependent_known_
   limitation`、`bash b72639a`)。あわせて、pit-auditor自身がBash Tool
   不足のため確認できなかった「意図した範囲外のFile変更が無いこと」を
   `git diff --stat`で別途直接確認した(意図した範囲外の変更は無し)。
2. **skeptic-reviewer**: `PASS_WITH_CONCERNS`。5件のFinding(MEDIUM x2、
   LOW-MEDIUM x1、LOW x1、+Checked Clean多数)、いずれも独立に再確認した:
   - **[MEDIUM、採用・修正]** `build_revision_histories()`は`series_id`
     のみでGroupingし、`macro_as_of()`はGroup内で`available_at`最大の
     1件のみを返す。したがって`series_id`が`reference_period`を含まない
     場合、異なる期間(例: 6月分・7月分CPI)のRecordが同一Seriesへ
     Collapseし、より新しい期間の値しか到達できなくなる、という指摘を
     実際にCode(`normalize.py`の`series_id`単独Grouping、`lib.
     evidence.model`の`as_of()`単一Version返却)を読んで再確認した。
     Fundamentals(`series_id = "|".join([internal_code, metric_type,
     fiscal_year_target, cur_per_type, scope, accounting_standard])`)
     と同じ「series_id構築は呼び出し側/Normalizerの責務、Dataclass自体は
     構造的に強制しない」という既存責務分担そのものは妥当と判断したが、
     この責務をModel Docstringが明記していなかったため、`MacroRecord`
     Docstringへ明記し、失敗Pattern(Collapse)と正しいPattern
     (Period込みSeries ID)の両方を固定するTestを追加した
     (`bash c7fc8f8`)。
   - **[MEDIUM、採用・修正]** 同根の指摘として、`series_id`が
     `seasonal_adjustment`/`metric_name`等の他の区別軸も一意に含まない
     限り、異なるSeries(例: SAとNSA)が同一`series_id`のもとで Silent
     Mergeされうる、という指摘も確認し、同じDocstring追記で対応した
     (区別すべき軸を明示的に列挙)。
   - **[LOW-MEDIUM、対応せず、設計判断として記録]**
     `lib/macro/normalize.py`と`lib/positioning/normalize.py`の
     `build_revision_histories()`が、`event_at`の参照Field名
     (`reference_period_end` vs `observation_end`)以外ほぼ同一実装で
     あり、「Field名の違いにより共通化するとかえって複雑になる」という
     DECISIONS.md記載の理由が、実際の差分の小ささ(属性名1つ)に比べて
     誇張されている、という指摘を確認した。指摘の正確性は認めつつ、
     Positioning Round(4C)の同種Callback Patternについてもコード共有を
     見送った経緯・External Copilot Review直後の「推測だけでArchitecture
     を増やさない」というユーザー指示との整合を優先し、Cross-Capability
     Protocol抽象化は依然として見送る判断を維持した(コード変更はせず、
     このRound内の判断根拠として記録するに留める)。
   - **[LOW、対応せず、Known Limitationとして記録]** MACRO-015の
     禁止語Listが、現在のCode構造(`content`の大半がEnum/日付由来で
     構造的に解釈語混入不可能)に対しては実質的に「常に通過するTest」に
     なっており、唯一のLeakage経路である`metric_name`(自由記述)に
     対しても、Listの語彙が狭い(例: 「上振れ」「下振れ」等の婉曲的
     解釈語は含まない)、という指摘を確認した。Reviewer自身も「現時点で
     実際にExploitされる経路は無い(Adapterが無くmetric_nameは全てTest
     記述のため)」と評価しており、Forward-looking Guardとして許容できる
     と判断し、コード変更はしなかった。将来Adapterが`metric_name`を
     実Provider Textから構築するようになった時点で語彙拡充を再検討する。

### Known Limitations(Reviewer Pass後、追加分)

- `RevisionHistory.as_of()`のTie-break(同一`available_at`の複数Version)
  は投入順序依存(全Capability共通のCommon Core既存挙動、Macro固有では
  ない)。
- `series_id`の一意性(Reference Period・Seasonal Adjustment等を含めた
  構築)は`MacroRecord`が構造的に強制せず、呼び出し側/将来Adapterの責務
  (Fundamentalsと同じ責務分担)。
- `lib/macro/normalize.py`は`lib/positioning/normalize.py`とほぼ同型の
  実装をコードとして共有していない(意図的、Cross-Capability抽象化を
  見送った判断)。
- MACRO-015の禁止語Listは現在のCode構造に対しては構造的に常時通過する
  Testであり、将来`metric_name`が実Provider Textを含むようになった際に
  語彙拡充が必要になる可能性がある。

### このDecisionでやらないこと

Economic Forecast・Regime Detection・BUY/SELL判断・Expectations/
Consensus・Macro Scoring・Sector Rotation Signal・Central Bank NLP・
News・Portfolio Sizing・Automated Trading・Heavy Monitoring・Mass
Source Crawling・Statistical Strategy Validationのいずれにも着手して
いない。TDnet/Company IR/Positioningの既存Validation Backlogは同時に
消化していない。Phase4Aへの再着手は行っていない。

## D0056 — Phase4E-1: Global Market Data Foundation(設計、Adapter未実装)

海外の株価指数・為替・国債利回り・コモディティ・Volatility Indexを
PIT-safe/timezone-aware/source-aware/reproducibleな形でこのLabへ取り込む
ためのData Foundationを新設した。**Market Regime判定・Investment Signal
・日本株結論(「NASDAQ下落=日本IT株SELL」等)は一切実装していない**
(Observationまで、Phase4E-1要件§1/§2)。

### Phase4E全体のSplit

Phase4E(Global Market/News/Consensus統合)は4分割(4E-1 Global Market
Data・4E-2 Japan News・4E-3 Global News・4E-4 Consensus/Expectations
Inputs)されたユーザー指示に従い、このRoundは**4E-1のみ**を対象とし、
News/Consensusには着手していない。

### Repository Reality Check

`lib.market_calendar`(日本市場の休日判定、Timezone処理は固定UTC+9
Offset)・`lib.evidence.model`(`RevisionHistory`/`SourceVersion`/
`AvailabilityBasis`/`ValueAvailability`/`Frequency`)・`lib.positioning`/
`lib.macro`(Long-form Record + Source非依存`build_revision_histories()`
Callback Pattern)を先に確認した。`lib.sources.catalog.DataCapability.
GLOBAL_MARKET`はPhase3D時点で既に定義済み(未使用のまま)だったため
新規Enum追加不要だった。既存Repositoryに海外市場Dataへの接続は一切無く、
Positioningの Price-derived Seriesのような「ゼロリスクで再利用できる
既存接続」に相当するものが無かった。

### Source Candidate Research(data-source-researcher Agent、2026-08-18)

FRED(セントルイス連銀)・ECB(Frankfurter経由)・CBOE・US Treasury・Yahoo
Finance(`yfinance`)・Alpha Vantage・Twelve Data・Nasdaq Data Link等を
調査した。結果はほぼ全てSEARCH-SNIPPET-DERIVED(UNVERIFIED)——
`fred.stlouisfed.org`/`home.treasury.gov`/`api.fiscaldata.treasury.gov`/
`www.cboe.com`/`www.alphavantage.co`/`stooq.com`/`www.ecb.europa.eu`
等へのWebFetchは全て失敗した(`EGRESS_BLOCKED`)。唯一直接読めたのは
`pypi.org`/`github.com`経由の`fredapi`/`yfinance`/Frankfurter Wrapperの
README(いずれも第三者OSS Wrapperの説明であり、一次Provider文書ではない)。

**FRED**が「単一APIキーでEquity Index/FX/Rate/Volatilityを横断できる
Umbrella候補」として最優先で推奨された。特筆すべき所見: (1) FRED上の
`SP500`/`DJIA`はS&P DJIとの2014年Licensing Agreementにより過去10年分
Rolling Windowにしかアクセスできない(複数独立Snippetで収斂)、(2)
FRED/ALFRED APIが`realtime_start`/`realtime_end`によるVintage Query
機構を持つという記述(複数第三者Wrapper経由で収斂、これまでのLab
Sourceの中で最も具体的な前向きPIT保証候補)、(3) CBOE VIXのRTH算出
Windowは9:30am-4:15pm ET(Closeは4:15pm ETでありEquity市場4:00pm Closeと
異なる)、(4) FX(USD/JPY・EUR/USD)はFRED H.10由来の「NY正午Buying Rate」
という歴史的記述と、ECB Frankfurter経由の「16:00 CET Reference Rate
(取引用途非推奨とECB自身が明記)」という、性質の異なる2種類のOfficial
Reference Rateが見つかった——どちらも市場実勢Rateとは別概念であり
混同しない。詳細は`GLOBAL_MARKET_ARCHITECTURE.md`「Source候補」節・
`VALIDATION_BACKLOG.md`参照。

### Adapterは1件も実装しない(ユーザー要件§8に基づく正直なStatus)

検索Snippetのみを根拠にAdapterを実装しない、というユーザー要件に従い、
このRoundでは5候補(`fred_sp500`/`fred_dexjpus`/`fred_dexuseu`/
`fred_dgs10`/`fred_vixcls`)全てを`implementation_status=NOT_IMPLEMENTED`
のまま`lib/global_market/catalog.py`へ登録し、Validation Status=
`DESIGN_COMPLETE_AWAITING_SPEC_VERIFICATION`を`known_limitations`へ
明記した(Positioning Phase4C/Macro Phase4Dと同じPattern踏襲)。

### Common Global Market Model(新規Versioning機構は作らない)

`lib/global_market/model.py`の`GlobalMarketRecord`はLong-form 1レコード
(series × session_date × source)。PIT/Revision管理は`lib.evidence.model.
RevisionHistory`/`SourceVersion`をそのまま再利用し、Global Market専用の
新しいVersioning Primitiveは作らなかった(Fundamentals/Positioning/
Macroと同一のPrimitive、4件目の実証)。

**Timezone/DSTがこのRound最大の設計論点だった**。`lib.market_calendar`の
固定UTC+9 Offset方式は日本にDSTが無いため正しいが、米国/欧州市場への
再利用は誤り(DST期間中は1時間ズレる)と判断し、`GlobalMarketRecord.
market_timezone: str`にIANA Timezone名を保持させ、実際のAvailability
判定は`zoneinfo.ZoneInfo`でDST-aware datetimeを構築する設計とした
(`lib.market_calendar`の拡張ではなく、意図的に独立した設計)。1月
(EST, UTC-5)と7月(EDT, UTC-4)で実際にUTC Offsetが異なることをTestで
直接検証した(`GLOBAL-003`)。

`IndexReturnType`(PRICE_RETURN/TOTAL_RETURN/NET_RETURN)・`PriceType`
(SPOT/FRONT_MONTH_FUTURES/CONTINUOUS_FUTURES)・`AdjustmentStatus`
(ADJUSTED/UNADJUSTED/PROVIDER_TRANSFORMED)は、Macroの`SeasonalAdjustment`
と同じ正当化根拠(Source固有Field名Mappingではなく、複数Sourceに横断
して現れる経済的に意味のある構造的区別軸)によりCommon Model Fieldへ
昇格させた。

`lib/global_market/normalize.py`の`build_revision_histories()`は
`lib.positioning.normalize`/`lib.macro.normalize`と同型のSource非依存
`resolve_available_at`Callback Patternを踏襲し、意図的にコード非共有
(Field名の違い、Phase4C/4D双方で既に判断済みの方針を維持)とした。

### series_idはCaller/Adapterの責務(Macro D0055の教訓を先取り適用)

Macro Phase4Dのskeptic-reviewerが発見した「`series_id`がReference
Periodを含まないとCollapseする」Findingと同型の失敗モードが、Global
Marketでは`session_date`について起こりうると判断し、今回は独立して
発見されるのを待たず、実装と同時に`GlobalMarketRecord`Docstringへ
責務を明記し、`test_series_id_without_session_date_causes_cross_
session_collapse_known_limitation`としてPinning Testを追加した(D0055
Findingの再発防止を実装時に先取りした初めてのケース)。

### Evidence Layer(Common Core、新規Primitiveなし)

`lib/global_market/evidence.py`の`global_market_record_to_evidence()`は
Fundamentals/Positioning/Macroと同じD0049/D0050 PIT Bugfix方針を踏襲
する: `source.available_at`には常に`record.retrieved_at`を使い、
`market_public_at`へのFallbackは行わない。`EvidenceRecord`/
`SourceMetadata`を変更なしで再利用した(5件目の実証)。

### Japan Decision-Time Leakage(ユーザーが最も重視した論点)

`global_market_as_of()`は`decision_at`がどのTimezoneのtz-aware
datetimeでも受け取り、Python datetime比較の内部UTC正規化にPIT判定を
委譲する設計とした(独自のTimezone変換Logicを実装しない)。同一瞬間を
UTC表現とJST表現で渡しても判定結果が一致すること(`GLOBAL-002`)、
日本時間の同日朝には前日の米国市場Closeがまだ観測不可能であり翌朝には
観測可能になること(`GLOBAL-001`)を直接Testで検証した。

### Tests(GLOBAL-001〜014、実装からのコピーではなくPhase4E-1要件から導出)

`13_tests/test_global_market_model.py`(15件)・
`test_global_market_pit.py`(20件)・`test_global_market_catalog.py`
(9件)、合計44件を新規追加。実Network接続無し、合成Record Dataのみ
使用。Positioning/Macroのskeptic-reviewer Findingで「Catalog Descriptor
群にTest Coverageが無かった/後追いだった」Gapが指摘された教訓を活かし、
このRoundは最初からCatalog Testを含めた。

### Known Limitations

- Adapterを1件も実装していない(5候補全て`NOT_IMPLEMENTED`、Validation
  Status=`DESIGN_COMPLETE_AWAITING_SPEC_VERIFICATION`)。
- FRED/ECB/CBOE/US Treasuryいずれも公式仕様をこのSessionから直接確認
  できていない(`EGRESS_BLOCKED`)。
- FRED/ALFREDのVintage Query機構(`realtime_start`/`realtime_end`)は
  最も有望な前向きPIT保証候補だが、実際に文書通り機能するかはこの
  Roundでは未確認(次の最優先検証項目)。
- `lib/global_market/normalize.py`は`lib/positioning/normalize.py`/
  `lib/macro/normalize.py`とほぼ同型の実装をコードとして共有していない
  (意図的、Cross-Capability抽象化を見送った判断の3件目)。
- Continuous FuturesのRoll Methodology・Total Return Index算出方法は
  未実装(`PriceType`/`IndexReturnType`という区別のFieldのみ用意)。
- `lib/global_market/catalog.py`の5 Descriptorは`SourceCatalog`への
  実際のWiring(Application起動時の一元登録)がまだ無い(既存の慣行の
  まま)。

### Reviewer Pass(pit-auditor 1回・skeptic-reviewer 1回、Findingsは全て独立に再確認の上で採否判定)

1. **pit-auditor**: `4 FINDINGS(highest severity: HIGH)`。4件とも実際に
   コードを読み・再現Scriptを実行して独立に再確認した上で対応した。
   - **[HIGH、採用・修正]** `market_timezone`は非空Checkのみで、実際に
     IANA Timezone Databaseで解決可能かも、DSTを正しく反映するZoneかも
     検証していなかった。`ZoneInfo("EST")`が実際にJuly/Januaryとも
     固定UTC-5を返す(このRoundが排除しようとした`lib.market_calendar`
     固定Offsetと同じ誤りを再現する)ことを直接実行して確認した。
     `GlobalMarketRecord.__post_init__`へ、`ZoneInfo(...)`で解決可能か
     つ`"UTC"`またはArea/Location形式(`"/"`を含む)であることを要求する
     Validationを追加し(`bash ec35014`)、Pinning Test(`test_fixed_
     offset_legacy_timezone_alias_rejected`)を追加した。
   - **[HIGH、独立に再確認の上でCommon Core既存挙動と判定、Pinning Test
     のみ追加]** `global_market_record_to_evidence()`経由で`lib.
     evidence.retrieval.filter_usable_at()`(既に稼働中のCross-Capability
     Evidence取得経路)へ渡した場合のPIT判定は`record.retrieved_at`のみを
     基準にし、`global_market_as_of()`が使うDST-aware Session Close
     Resolverを一切参照しない、という指摘を実際にCode(`evidence.py`の
     `available_at=record.retrieved_at`、`lib/evidence/model.py`の
     `is_usable_at`)を読んで再現Testで確認した。ただし同じ構造の
     `retrieved_at`基準Fallback(PIT-003/PIT-004原則そのもの)は
     `lib/positioning/evidence.py`(既にCONNECTEDなAdapterを持つ)・
     `lib/macro/evidence.py`にも同一に存在すると確認したため、これは
     このRoundが持ち込んだGlobal Market固有のBugではなく、Evidence
     Layer全体に共通するCommon Core既存Patternと判断した。Common Core
     (`lib/evidence/`)自体の変更、または3 Capability全てへの変更は
     このRoundのScope外(Global Market固有の具体的Evidenceのみに基づく
     Architecture拡張をしない、というユーザー指示に反する)と判断し、
     Common Core自体は変更せず、乖離を`test_global_market_as_of_and_
     evidence_filter_usable_at_can_disagree_known_limitation`として
     固定した(`bash ec35014`)。将来、Evidence Layer全体のPIT Gate設計を
     Capability横断で見直す価値がある候補として`VALIDATION_BACKLOG.md`
     へ記録する。
   - **[MEDIUM、採用・修正]** `observation_time`(tz-aware)と`session_date`
     +`market_timezone`の組み合わせが構造的に矛盾しうる(例:
     `observation_time`をmarket_timezone基準のLocal日付へ変換すると
     `session_date`と異なる暦日になる)という指摘を実際に構築・確認した
     (UTC 2026-08-19 05:00はNY Localでは8/19 01:00になり、
     `session_date=8/18`とは矛盾する)。`__post_init__`へCross-field
     Validationを追加し(`bash ec35014`)、Pinning Testを追加した。
   - 4件目の指摘(`RevisionHistory.as_of()`のTie-break、同一`available_at`
     ケース)はMacro D0055で既に確認済み・Pinning済みのCommon Core既知
     挙動が本Moduleにも構造的に適用されることを再確認したもので、
     Global Market固有の新規Findingではない、とpit-auditor自身が明記
     している(LOW)。Global Market自身の`_us_close_resolver`Patternの
     元では同一`session_date`のRecordがこのTie-breakへ実際に到達しうる
     ことを示すPinning Testが無かった点のみをGapとして認め、追加は
     見送った(GLOBAL-007の`series_id`未区別Pinning Testが実質的に同型の
     Tie-break挙動を既にExerciseしているため、重複Testを追加する必要は
     無いと判断)。
2. **skeptic-reviewer**: `PASS_WITH_CONCERNS`。1件のMEDIUM・2件のLOW、
   いずれも独立に再確認した:
   - **[MEDIUM、採用・修正]** 「series_id session_date Collapse Lessonを
     先取り適用した」という主張は`session_date`軸についてのみ真であり、
     `model.py`Docstring自身が挙げる他の軸(`index_return_type`/
     `price_type`/`currency`)には同型のPinning Testが1件も無かった、
     という指摘を、実際に全44 Testを読んで(`index_return_type`/
     `price_type`/`currency`を同一`series_id`で構築するTestが存在しない
     ことをgrepでも確認)採用した。`index_return_type`軸について
     Pinning Test(`test_series_id_without_index_return_type_causes_
     cross_type_collapse_known_limitation`)を追加し(`bash a5bffec`)、
     `price_type`/`currency`軸は個別Test未追加のままKnown Limitationとして
     Docstringに明記した。
   - **[LOW、採用・修正]** `instrument_category`と`index_return_type`/
     `price_type`の組み合わせが経済的に整合しているかの構造検証が無い、
     という指摘を確認した。これは`series_id`一意性と同じ既存の責務分担
     (呼び出し側/将来Normalizerの責務)であり偽の保証はしていないと
     判断したが、明示していなかったため`model.py`Docstringへ追記した
     (`bash a5bffec`)。
   - **[LOW、対応せず、Known Limitationとして記録]** GLOBAL-010の従来
     Testが「DocumentRelationship非Import」という構造Checkのみで、
     「Raw値変更だけではRevisionと自動判定しない」という実質的な主張を
     直接検証していなかった、という指摘を確認し、実質的な検証を行う
     新Test(`test_global010_raw_value_change_for_same_series_and_
     session_does_not_set_is_correction`)を追加した上で、従来の構造
     Testも(別の有効な確認事項として)維持した(`bash a5bffec`)。

### このDecisionでやらないこと

Market Regime判定・Investment Signal・BUY/SELL判断・Cross-Asset Signal・
Portfolio Sizing・Continuous Futures Engine・News NLP・Automated
Tradingのいずれにも着手していない。Japan News(4E-2)・Global News
(4E-3)・Consensus/Expectations Inputs(4E-4)には進んでいない。TDnet/
Company IR/Positioning/Macroの既存Validation Backlogは同時に消化して
いない。

## D0057 — Cross-Capability PIT Gate Consistency Review(調査のみ、Validation Backlog #21の解消)

Phase4E-1(D0056)のpit-auditorが報告したValidation Backlog #21
(「Global Marketの`as_of()`経路とEvidence経路のAvailability Semanticsに
差がある」)のみを調査した。**Phase4E-2へは進んでいない。** 差があること
自体をBugと決めつけず、既存Decision(D0042/D0049/D0050)を先に読んだ上で、
実Code(6 Capability: Fundamentals/Disclosures/Positioning/Macro/Global
Market + `lib/evidence/`共通層)のExecution Pathを直接追跡し、Classification
(NO_BUG/SAFE_BUT_UNCLEAR/CURRENT_DEFECT/ARCHITECTURE_GAP)を決定した。

### §1 既存Decisionの再確認(D0042/D0049/D0050)

D0042が既に「Market Information Study(A系統、`market_public_at`)」と
「Reproducible System Simulation(B系統、`provider_available_at`相当、
このLabのPIT判定の既定基準)」を区別し、`SourceMetadata`のDocstringが
`available_at`を「provider_available_at相当」と明記していることを確認した
(`lib/sources/catalog.py:80`)。D0049/D0050は「`market_public_at`への
Fallback禁止、`retrieved_at`はObserved Safe Availability Timestamp」を
確立した。この2つのDecisionはいずれも「Evidence経路のavailable_atが
どう計算されるべきか」を扱っており、「as_of経路の`resolve_available_at`
がSession/Period完了時刻を推定する場合、それとEvidence経路がどう関係
するか」は扱っていなかった——D0057はこの未検討だった接点を扱う。

### §2 実Code確認(File/Function/Timestamp Semantics)

| Capability | as_of経路のavailable_at生成 | Evidence経路のavailable_at生成 |
|---|---|---|
| Fundamentals | `lib/fundamentals/normalize.py::_provider_available_at_and_basis()` — `market_public_at`優先(Anchor)、Basis常にUNKNOWN(既定で`as_of()`除外) | `lib/fundamentals/evidence.py::disclosure_metric_to_evidence()` — 常に`envelope.retrieved_at`(D0049で確定) |
| Disclosures | `lib/disclosures/normalize.py::_provider_available_at_and_basis()` — 同上Pattern、TDnetは`market_public_at`にEXACT Basisを持つため`disclosures_as_of()`既定(PROVIDER_AVAILABLE_AT系統)では逆に**常に除外**される(provider_available_atはUNKNOWNのまま) | `lib/disclosures/evidence.py::disclosure_document_to_evidence()` — `provider_available_at`確認済みなら優先、無ければ`document.retrieved_at`(D0050で確定) |
| Positioning | `lib/positioning/derived/price_derived.py::resolve_available_at()` — `session_close_at(observation_end)`、Basis=INFERRED(既定で`as_of()`に含まれる) | `lib/positioning/evidence.py::positioning_record_to_evidence()` — 常に`record.retrieved_at` |
| Macro | 呼び出し側が渡す`resolve_available_at`(このRound未実装Adapterのため実例なし) | `lib/macro/evidence.py::macro_record_to_evidence()` — 常に`record.retrieved_at` |
| Global Market | 同上(未実装Adapter) | `lib/global_market/evidence.py::global_market_record_to_evidence()` — 常に`record.retrieved_at` |

**Positioningのみが実際にConnectedなAdapter(J-Quants Price経由)を持つ**
ため、これが最も具体的な確認対象になった。`lib/data_sources/jquants.py`
は`retrieved_at=datetime.now(UTC)`(実際のHTTP Fetch時刻)を設定しており、
これがSession Closeより前になることを構造的に禁止する仕組みは無い
(例えば取引時間中にDaily Quotesを取得した場合、当日分の未確定行が
含まれうる)。

**共通層の構造的差異(重要)**: `lib.evidence.model.SourceVersion`
(as_of経路)は`availability_basis`(EXACT/OBSERVED/INFERRED/UNKNOWN)を
持ち、`RevisionHistory.as_of()`はUNKNOWNを既定除外する。一方
`lib.sources.catalog.SourceMetadata`(Evidence経路)には`availability_
basis`に相当するField自体が存在しない(`dataclasses.fields()`で直接
確認、`test_evidence_record_source_metadata_has_no_availability_basis_
field`)。したがってEvidence経路には「この値は推定である」ことを示す
構造的な手段が無く、`retrieved_at`をそのまま確定値として扱う。

**Repository Reality Check(重要な否定的事実)**: `positioning_record_to_
evidence`/`disclosure_metric_to_evidence`/`disclosure_document_to_
evidence`/`macro_record_to_evidence`/`global_market_record_to_evidence`
のいずれも、また`lib.evidence.retrieval.retrieve_evidence()`/`filter_
usable_at()`も、Repository Root直下の`scripts/`(`Japanese_Equity_Lab/`
配下ではない。`Japanese_Equity_Lab/scripts/`というDirectoryは存在しない)・
Root直下の`app.py`(既存Screening Tool、`core/`を使う別Toolであり
`Japanese_Equity_Lab/lib`とは無関係)のいずれからも一切呼び出されていない
(`grep`で確認済み、pit-auditorが独立に`Japanese_Equity_Lab/lib`を実際に
Importしている4件のRoot `scripts/*.py`——`lab_source_health.py`/
`jquants_financial_summary_diagnostic.py`/`fetch_jquants_local_snapshot.py`
/`jquants_lab_pipeline.py`——を個別に再確認し、いずれも該当Functionを
Importしていないことを確定した、D0057 Reviewer Pass参照)。`*_as_of()`
系関数群も同様に本番未接続。**唯一実際に配線されているPIT判定Pipeline
(`scripts/jquants_lab_pipeline.py` → `lib.backtest.engine.BacktestEngine`)
は、`lib.point_in_time.PointInTimeRecord`という別の・より古いPrimitive
(単一の`available_at=session_close_at(...)`のみを使う、Evidence/as_of
二重推定Patternとは無関係)を使っており、このRoundが調査した対立構造
そのものには触れていない**(pit-auditor Finding、D0057 Reviewer Pass、
ARCHITECTURE_GAP判定を補強する追加証拠)。つまり**このLabのEvidence/
as_of層全体が、現時点では実際に配線された本番Pipeline(Backtest
System B)を持たない、Library Codeのみの状態**である。

### §3 Capability Matrix(Timestamp Semantics)

| Capability | Observation timestamp | Published timestamp | Provider availability | Retrieved timestamp | Canonical available_at(as_of) | Evidence available_at | as_of visibility rule | AvailabilityBasis |
|---|---|---|---|---|---|---|---|---|
| Fundamentals | `FundamentalMetric`の`fiscal_year_target`等(期間概念、時刻ではない) | `envelope.market_public_at`(DiscDate/DiscTime由来、Basis=EXACT/UNKNOWN) | UNKNOWN(未観測) | `envelope.retrieved_at` | `market_public_at`優先Anchor、Basis常にUNKNOWN | `retrieved_at`固定 | `RevisionHistory.as_of()`、Latest-wins | as_of: UNKNOWN固定。Evidence: Field無し |
| Disclosures | `DisclosureDocument`の開示対象期間 | `document.market_public_at`(TDnetはEXACT、EDINETはUNKNOWN) | `document.provider_available_at`(常にUNKNOWN、現行Normalizerでは未確認) | `document.retrieved_at` | 既定(PROVIDER_AVAILABLE_AT系統)は`provider_available_at`のみ参照、UNKNOWNのため常に除外 | `provider_available_at`確認済みなら優先、無ければ`retrieved_at` | `disclosures_as_of()`、Set Filter(Latest-winsではない) | as_of: `market_public_at_basis`/`provider_available_at_basis`。Evidence: Field無し |
| Positioning | `observation_start`/`observation_end`(Bar日) | `record.market_public_at`(常に`None`、Price-derivedでは未使用) | UNKNOWN(未観測、Fieldは無くBasisのみ`resolve_available_at`が付与) | `record.retrieved_at`(実HTTP Fetch時刻) | `session_close_at(observation_end)`、Basis=INFERRED | `retrieved_at`固定 | `positioning_as_of()`、Latest-wins | as_of: INFERRED(既定で含む)。Evidence: Field無し |
| Macro | `reference_period_start`/`end` | `record.market_public_at` | 未実装Adapterのため実例なし | `record.retrieved_at` | 呼び出し側実装依存(未実装) | `retrieved_at`固定 | `macro_as_of()`、Latest-wins | as_of: 呼び出し側依存。Evidence: Field無し |
| Global Market | `session_date` | `record.market_public_at` | 未実装Adapterのため実例なし | `record.retrieved_at` | 呼び出し側実装依存(未実装、Phase4E-1では`_us_close_resolver`がTest内のみ存在) | `retrieved_at`固定 | `global_market_as_of()`、Latest-wins | as_of: 呼び出し側依存。Evidence: Field無し |

### §4 System A / System B / 第三の概念(Market Observation Completion Time)

D0042のSystem A(`market_public_at`、公表時刻)/System B
(`provider_available_at`相当、`available_at`)の2分類は、Disclosure的
Event(会社が特定時刻に開示する)を念頭に設計されていた。Positioning/
Macro/Global Marketの`resolve_available_at`Pattern(`session_close_at`
等)は、**どちらでもない第三の概念**を扱っている: ユーザーTask仕様§3の
「Market Observation Completion Time」——市場という制度がその観測を
確定させた時刻(東証の大引け等)——である。これは`market_public_at`
(特定Entityが能動的に公表する行為)ではなく、`retrieved_at`(このLabが
実際に取得した行為)でもない、市場構造由来の第三の時刻概念である。

**`lib.schemas.price_data.provider_event_available_at()`のDocstring
(既存、Phase3A由来)は、これを明示的にSystem Bの代理として扱う設計判断を
既に記録していた**: 「このEventの存在がResearch Labにとって知り得るのは、
その日のBarデータ自体が取得可能になる時刻(=市場のその日の大引け)と
同じである」。すなわち、**Session Close推定はSystem Bの推定戦略の1つ
として意図的に選ばれたものであり、System Aでも第四の概念でもない**。
`AvailabilityBasis.INFERRED`(EXACTではない)というTagが、この推定の
性質(確認されたProvider Timestampではなく、市場構造からの推論)を
正確に表現している。

**結論**: as_of経路(Session Close推定)とEvidence経路(`retrieved_at`
Observed Fact)は、**同じTarget概念(System B)を指す、2つの独立した
推定戦略**である。「本来同じ時計を表すべきか」(ユーザーTask仕様§2C)への
回答は**Yes**——両方ともSystem Bの推定である。「異なるなら、意図された
Layer separationか」(§2D)への回答は**部分的にYes**: 推定戦略が異なる
こと自体は意図的な設計(EXACT Timestampが無い場合の代替手段として
両方とも正当)だが、**2つの推定戦略が構造的に整合する(例:
`retrieved_at >= available_at`が常に成り立つ)ことを保証する仕組みは
存在しない**——これは意図されたLayer Separationではなく、単に「まだ
検討されていなかった接点」である。

### §5 Failure Example(実際にTestで再現)

Positioning(実Adapter)で、`retrieved_at`がSession Closeの6時間前
(例: 取引時間中のBatch取得、または将来Providerが未確定Intraday値を
返すケース)である場合:

- `positioning_as_of()`(as_of経路): Session Close前として正しく`None`
  を返す。
- `positioning_record_to_evidence()` → `filter_usable_at()`
  (Evidence経路): `retrieved_at`のみを基準にするため、同じ`decision_at`
  で誤って「利用可能」と判定する。

逆に`retrieved_at`がSession Closeの後(=このLabの現行運用が実際に想定
する通常の順序)であれば、Evidence経路はas_of経路より**常に保守的**
(遅い、または同じ)になり、乖離しない(`test_evidence_path_agrees_
with_as_of_path_when_retrieved_after_session_close`で確認)。

### §6 Classification: D. ARCHITECTURE_GAP

- **NO_BUGではない**: 両経路は「異なる意味」ではなく「同じTarget概念
  (System B)への異なる推定戦略」であり、それらが構造的に整合する保証が
  無いことは単なる仕様上の相違として片付けられない。
- **CURRENT_DEFECTではない**: §2で確認した通り、Evidence経路・as_of
  経路のいずれも、実際に本番`scripts/`・`app.py`から呼び出されている
  Execution Pathが現在存在しない。両者を連結し実際にPIT判定へ使う
  Consumerが無いため、「現在誤った投資判断・誤ったBacktest結果を生んで
  いる」というCURRENT_DEFECTの要件(具体的Execution Path上のTrigger/
  Impact)を満たさない。
- **ARCHITECTURE_GAP**: 「現在Leakageはないが、将来統合時に意味論衝突が
  起こる」に該当する。将来Backtest System B(Evidence経由でPIT判定する
  実際のPipeline)を配線する際、または`retrieve_evidence()`を本番接続
  する際に、この2経路のどちらを「正」とするかを明示的に決めないと、
  同じ`GlobalMarketRecord`/`PositioningRecord`について矛盾した
  Availability判定が起こりうる。
- SAFE_BUT_UNCLEARではない(単なるDocumentation不足ではなく、実際に
  Testで異なる結果を再現できる構造的な相違であるため、より強い
  ARCHITECTURE_GAPに分類する)。

### §7 このRoundでのCode変更方針: なし(Common Core非変更)

分類がARCHITECTURE_GAPであるため、ユーザー指示§10「ARCHITECTURE_GAPなら
原則Backlogへ」に従い、**`lib/`配下のいずれの本番Codeも変更しない**
(`git status`で確認: 新規Test File 1件のみ)。特に以下は行っていない:

- `EvidenceRecord`/`SourceMetadata`への`availability_basis`相当Field
  追加(新Schema拡張、ユーザー指示§11で明示的に禁止)。
- Evidence経路のavailable_at計算をas_of経路のResolverと連携させる変更。
- 2経路のどちらかを「正」と決める設計判断(これは将来Backtest System B
  設計時にユーザーの判断を仰ぐべき論点であり、このRoundの調査だけでは
  決定しない)。

### §8 Tests(Semantic Contractの固定、Timestampの一致を強制するTestではない)

`13_tests/test_pit_gate_cross_capability_semantics.py`(新規、6件):

1. `test_as_of_path_available_at_is_independent_of_retrieved_at` —
   as_of経路がSession Closeのみに依存し`retrieved_at`を無視することの
   構造確認(Positioning実Adapter)。
2. `test_evidence_path_available_at_is_independent_of_session_close` —
   Evidence経路が`retrieved_at`のみに依存しSession Closeを無視すること
   の構造確認(Positioning実Adapter)。
3. `test_evidence_path_leaks_earlier_than_as_of_path_when_retrieved_
   before_session_close` — Failure Exampleの直接再現(§5)。
4. `test_evidence_path_agrees_with_as_of_path_when_retrieved_after_
   session_close` — Well-behaved Orderingでは乖離しないことの確認
   (Failure Exampleとの対比)。
5. `test_evidence_record_source_metadata_has_no_availability_basis_
   field` — `SourceMetadata`に`availability_basis`相当Fieldが構造的に
   存在しないことの確認(`dataclasses.fields()`直接検査)。
6. `test_global_market_records_the_same_divergence_pattern_
   independently` — Global Marketでも同型のPatternが再現することの
   最小Sanity Check(D0056の既存Pinning Testと重複させず、Positioning/
   Global Marketで同型であること自体の確認に限定)。

### §9 Documentation変更

`DECISIONS.md`(このEntry)のみ。`lib/`配下のDocstring変更は行っていない
(§7参照、Common Core非変更方針のため)。

### §10 Validation Backlog Disposition

`VALIDATION_BACKLOG.md`行21(「Evidence Layer PIT Gate Capability横断
レビュー」)を、D0057の調査完了を反映する形で更新した(削除はしない
——ARCHITECTURE_GAPは「対応済み」ではなく引き続きBacklog項目として残す、
ユーザー指示§10「原則Backlogへ」に従う。ただし内容を「未調査」から
「調査完了・設計判断待ち」へ更新し、この結論[D0057]を指すよう改訂)。

### §11 Reviewer Pass(pit-auditorのみ、ユーザー指示§13に従う)

`pit-auditor`(Read-only)を実施。`3 FINDINGS(highest severity: LOW)`、
いずれも独立に再確認の上で採否判定した:

1. **[LOW、採用・修正]** `test_evidence_path_agrees_with_as_of_path_
   when_retrieved_after_session_close`という名称は、実際にはTest本体の
   中間Case(`decision_at_between`)がas_of経路とEvidence経路の**不一致**
   (as_of経路のみ利用可能と判定)を示しており、「一致する」という名称は
   不正確、という指摘を実際にTest本体を読んで確認した。名称を`test_
   evidence_path_never_leaks_earlier_than_as_of_path_when_retrieved_
   after_session_close`へ修正し、Docstringも「一致」ではなく「Leakageの
   方向が`retrieved_at < available_at`の場合に限られる」という正確な
   主張へ書き直した(`bash`未Commit、このRound内で修正)。
2. **[LOW、採用・修正]** D0057本文が「`scripts/`・`app.py`」とだけ記述し、
   これらがRepository Root直下(`Japanese_Equity_Lab/`配下ではない)に
   あること、`app.py`が実際には無関係な既存Screening Toolであることを
   明記していなかった、という指摘を確認した。pit-auditor自身が独立に
   Root直下`scripts/*.py`のうち`Japanese_Equity_Lab/lib`を実際にImport
   する4件(`lab_source_health.py`/`jquants_financial_summary_
   diagnostic.py`/`fetch_jquants_local_snapshot.py`/`jquants_lab_
   pipeline.py`)を特定し、いずれも該当Functionを呼んでいないことを
   再確認した上で追加提供した知見(`scripts/jquants_lab_pipeline.py` →
   `lib.backtest.engine.BacktestEngine`が実際に配線されている唯一の
   PIT判定Pipelineだが、`lib.point_in_time.PointInTimeRecord`という
   別の古いPrimitiveを使っており、このRoundが調査したEvidence/as_of
   二重推定Patternには触れていない)を含め、§2 Repository Reality Check
   へ反映した(ARCHITECTURE_GAP判定を補強する追加の肯定的証拠)。
3. **[LOW、対応不要、情報提供のみ]** `include_unknown_availability=True`
   Opt-in時のLeakage(D0049 §5-1 Follow-up、既存の別Finding)がD0057の
   Capability Matrixに明記されていない、という指摘。pit-auditor自身が
   「これはD0057が扱う対象[as_of経路 vs Evidence経路の乖離]とは異なる
   別のFinding[Opt-in Flagの誤用]であり、混同されていないことの確認
   目的で提供した」と明記しており、対応不要と判断した(D0057 Scope外の
   既存Finding、正しく分離されたまま)。

Blocker/High/Medium Findingは無し。pit-auditor自身が「実際に配線された
PIT判定Pipelineが`lib.point_in_time`という別Primitiveを使っている」
という新しい肯定的証拠を独立に発見・提供したことも記録する。

### §12 最終回帰確認

`pytest`(Lab)・`ruff check`・`ruff format --check`・`mypy`
(`core app.py scripts Japanese_Equity_Lab/lib`)いずれもclean。
`git diff --stat -- core/ app.py tests/`は空Diff。今回の変更File一覧は
`13_tests/test_pit_gate_cross_capability_semantics.py`(新規)・
`DECISIONS.md`・`VALIDATION_BACKLOG.md`のみ。

### このDecisionでやらないこと

`retrieval_mode`新Schema・Replay Architecture・Event Engine・Indexer・
Global Provider Adapter・FRED Integration・Macro Adapter・Phase4E-2
(Japan News)・大規模Common Core再設計のいずれにも着手していない。
2つの推定戦略のどちらを「正」とするかの設計判断も行っていない
(将来Backtest System B設計Round向けにBacklogとして残す)。

## D0058 — Phase4E-2: Japan News Data Foundation(設計、Adapter未実装)

日本語Newsの記事Metadata(見出し・公開時刻・出所・Provenance)を
PIT-safe/provenance-preserving/reproducibleな形でこのLabへ取り込むための
Data Foundationを新設した。**Sentiment判定・Event抽出・Investment
Conclusion・BUY/SELLは一切実装していない**(Observationまで、Phase4E-2
要件§2/§3)。

### D0057(Backlog #21)の扱い

事前指示通り、D0057が確認したARCHITECTURE_GAP(as_of経路とEvidence経路の
Availability推定戦略の相違)はこのRoundでは解決しない。Evidence Common
Schema再設計・`availability_basis`相当Field追加・Backtest PIT Gate統一・
EvidenceのBacktest接続のいずれも行っていない。`lib.news.evidence.news_
article_to_evidence()`はEvidence Recordを生成できるが、`lib.evidence.
retrieval.filter_usable_at()`等のBacktest経路へは一切接続していない
(`test_news015_*`で構造的に固定)。Validation Backlog #21は維持したまま。

### Repository Reality Check

`lib.evidence.model`(`RevisionHistory`/`SourceVersion`/`AvailabilityBasis`
/`AvailabilitySemantics`)・`lib.disclosures`(Document-shaped Set-Filter
as_of Pattern)・`lib.sources.entity_registry.EntityRegistry`・`lib.sources.
providers.NewsProvider`(Phase3D由来のProtocol、`fetch_news(start_at,
end_at)`、既に存在し再利用可能)を先に確認した。

**重要な発見**: Phase3D由来の`lib.evidence.news.NewsEvent`が既に存在した
が、`event_type`必須Field・見出し類似度による自動Duplicate分類
(`classify_news_relation()`)を持ち、Event抽出後を前提としたSchemaで
あることが判明した。Phase4E-2要件(Event抽出禁止§24、Headline Similarity
Is Not Duplicate§28)とは設計思想が異なるため、**再利用・拡張せず**
(既存File・既存Test`test_evidence_news.py`いずれも無変更)、`lib/news/`
をその手前の層(Metadata Ingest層)として新設した。詳細は
`JAPAN_NEWS_ARCHITECTURE.md`「`lib.evidence.news.NewsEvent`との境界」節。

### Source Candidate Research(data-source-researcher Agent、2026-08-18)

PR TIMES・JPX News Releases・FSA・METI・BOJ「What's New」・Nikkei・
Reuters Japan/Refinitiv・Bloomberg・Kyodo News/Jiji Press・@Press・
共同通信PRワイヤー等を調査した。結果は全てSEARCH-SNIPPET-DERIVED
(UNVERIFIED)——`prtimes.jp`/`developers.prtimes.com`/`www.jpx.co.jp`/
`www.fsa.go.jp`/`jp.reuters.com`等へのWebFetchは全て失敗した
(`EGRESS_BLOCKED`)。

**PR TIMES**が最も構造的に有望な候補として推奨された(会社別/リリース別
RSSの存在が複数独立Snippetで裏付けられ、`{company_id}.{release_seq}`
という2部構成数値識別子Schemeも示唆)。ただし2つの重大なGapが未解決:
(1) 全文保存・再配布Terms(企業規約第6条相当、未読)が制限的な可能性、
(2) 公開Article/RSS自体が実際に露出するTimestamp Fieldの粒度(著者用UI
側の10分刻みScheduling機能からの示唆のみで、公開側の実際のField仕様は
未確認)。Nikkeiは公式RSSが確認できず(有料Paywallサイトへのscrapingが
必要、このLabの「Structured Sourceを優先」原則に反する)。Bloomberg/
Reuters/Refinitiv/QUICKはいずれもEnterprise契約が必要で、個人がローカル
実行するという本Labの前提(ルートCLAUDE.md)にそぐわない。詳細は
`JAPAN_NEWS_ARCHITECTURE.md`「Source候補」節・`VALIDATION_BACKLOG.md`
参照。

### Adapterは1件も実装しない(ユーザー要件§8に基づく正直なStatus)

検索Snippetのみを根拠にAdapterを実装しない、というユーザー要件に従い、
このRoundでは4候補(`prtimes_press_release`/`jpx_news_releases`/
`fsa_press_release`/`meti_news_release`)全てを`implementation_status=
NOT_IMPLEMENTED`のまま`lib/news/catalog.py`へ登録し、Validation Status=
`DESIGN_COMPLETE_AWAITING_SPEC_VERIFICATION`を`known_limitations`へ
明記した(Positioning Phase4C/Macro Phase4D/Global Market Phase4E-1と
同じPattern踏襲)。BOJ「What's New」RSSはPhase4E-1の既存`boj_policy_rate`
Catalog Entry(Macro Capability)との対象重複可能性があり、このRoundでは
新規登録を見送った(Known Limitationとして記録)。

### Common News Model(Document-shaped、Disclosuresの前例を踏襲)

`lib/news/model.py`の`NewsArticleRecord`はDocument-shaped 1レコード
(記事単位)。Positioning/Macro/Global MarketのSeries-shaped Long-form
とは異なり、News記事はそれぞれ独立した意味を持ち複数記事が同時に
「見えている」状態が正しいため、`lib/disclosures/model.py`の
`DisclosureDocument`と同型のField構成(`published_at`/`published_at_
basis`、`provider_available_at`/`provider_available_at_basis`、
`retrieved_at`)を採用した(RevisionHistory/SourceVersionは使わない、
Positioning/Macro/Global Marketとは異なる設計判断)。

`lib/news/view.py`の`news_as_of()`は`lib.disclosures.view.disclosures_
as_of()`と同じ「Set Filter」(Latest-winsではない)。`lib/news/evidence.py`
の`news_article_to_evidence()`のavailable_at優先順位も`disclosure_
document_to_evidence()`(D0050)と同一(provider_available_at確認済み優先、
無ければretrieved_at、published_atへのFallback禁止)。

### Article Identity、Duplicate Handling(Safe Tierのみ)

`source_native_id`を優先Identity候補とし、`canonical_url`はIdentityに
使わない(Phase4E-2要件§11)。`lib/news/normalize.py`は`find_same_source_
native_id_signals()`(同一source_native_id)と`find_exact_raw_content_
duplicate_groups()`(Raw Payload行全体Hash完全一致)のみを提供する——
見出し類似度・URL類似度・時刻近接からの自動Duplicate判定(Potential
Tier)は実装せず、`test_news007_no_headline_or_url_based_duplicate_
function_exists_in_normalize`で構造的に固定した(既存`lib.evidence.
news.classify_news_relation()`より厳格な基準、Phase4E-2要件§28)。

### Compliance / Entity Mapping

`ContentAvailability`(FULL_TEXT/HEADLINE_ONLY/METADATA_ONLY/REFERENCE_
ONLY/UNKNOWN)Enumで、Source固有のTerms/Licenseによる全文保存可否の
差異を「全文保存必須」という前提をCommon Coreへ埋め込まずに表現する
(Phase4E-2要件§19/§34)。`entity_id`はSourceが構造化されたEntity識別子を
提供した場合のみ設定し、見出しText Matchingでは設定しない(§21、既存
`EntityRegistry`を再利用する設計、新規Entity Mapping機構は作らない)。

### Tests(NEWS-001〜015、実装からのコピーではなくPhase4E-2要件から導出)

`13_tests/test_news_model.py`(16件)・`test_news_pit.py`(25件)・
`test_news_catalog.py`(8件)、合計49件を新規追加。実Network接続無し、
合成Record Dataのみ使用。NEWS-016(Historical API Response Is Not
Historical Snapshot)はAdapter自体が無く再現するExecution Pathが無い
ため、Macro/Global Marketと同じくCode Testではなく`JAPAN_NEWS_
ARCHITECTURE.md`のKnown Limitationとして文書化するに留めた。Positioning
Phase4C/Macro Phase4D/Global Market Phase4E-1のskeptic-reviewer Finding
(「Catalog Descriptor群にTest Coverageが無かった/後追いだった」)の教訓を
活かし、このRoundは最初からCatalog Testを含めた。

### Source Integration Skill v1 Field Test

- **A. Skillだけで守れたRule**: PIT-001〜004(UNKNOWN非0/`published_at`
  優先Fallback禁止/`retrieved_at`のSafe Lower Bound位置付け)・RAW-002
  (Hash不一致からのRevision推測禁止)・SOURCE-001(Source固有Field意味論
  を推測しない)・SOURCE-004(Originating Source/Delivery Provider分離、
  PR TIMES=発行企業/PRTIMES delivery providerで直接適用)——いずれも
  Skill単体で既存Capability群の経験を踏まえた設計をそのまま踏襲できた。
- **B. News固有で追加確認が必要だったRule**: Document-shaped記事群への
  Set Filter as_of適用の判断自体(Skillに明記は無いが、Disclosuresの
  既存前例から導出可能だった)、`lib.evidence.news.NewsEvent`との境界
  判断(Skill/既存Docに明記が無く、このRound自身の分析で導出)。
- **C. News固有の事情 vs D. 一般的なSkill Gap**: 上記Bは**News固有の
  事情**と判定した(Event層Scaffoldとの境界判断は、他Capabilityには
  存在しない固有の状況——Positioning/Macro/Global Marketには対応する
  「先に存在したEvent層Placeholder」が無かった)。
- **E. Skill v1.1の必要性**: 無し(このRoundでは新規Rule追加を行わ
  なかった)。
- **F. Golden Prompt Parityへの影響**: 無し(このRoundはSkillを変更して
  いない)。

### Known Limitations

- Adapterを1件も実装していない(4候補全て`NOT_IMPLEMENTED`、Validation
  Status=`DESIGN_COMPLETE_AWAITING_SPEC_VERIFICATION`)。
- PR TIMES/JPX/FSA/METIいずれも公式仕様をこのSessionから直接確認できて
  いない(`EGRESS_BLOCKED`)。
- PR TIMESの全文保存・再配布Terms、公開側Timestamp Field粒度は未確認
  (次の最優先検証項目)。
- BOJ「What's New」RSSは既存Macro Catalog(`boj_policy_rate`)との対象
  重複可能性があり、このRoundでは新規Catalog登録を見送った。
- `updated_at`Fieldを実際に設定する経路(Source側Update/Correction通知
  の検出方法)は未設計。
- NEWS-016(Historical API Response Is Not Historical Snapshot)は
  Code Testではなく文書上のKnown Limitationとして記録するに留めた
  (Adapter未実装のため再現不能)。
- `lib/news/catalog.py`の4 Descriptorは`SourceCatalog`への実際のWiring
  (Application起動時の一元登録)がまだ無い(既存の慣行のまま)。

### Reviewer Pass(pit-auditor 1回・skeptic-reviewer 1回、Findingsは全て独立に再確認の上で採否判定)

1. **pit-auditor**: `2 FINDINGS(highest severity: LOW)`。2件とも独立に
   再確認の上で対応した。
   - **[LOW、採用・修正]** `news_as_of()`のFuture Injection/UNKNOWN除外
     Guardが、既定(PROVIDER_AVAILABLE_AT系統)のTestでしかExerciseされて
     おらず、MARKET_PUBLIC_AT系統でも同じGuardが直接Testで確認されて
     いなかった、という指摘を実際に`test_news_pit.py`全体を読んで確認
     した(Code自体は両系統で同じ3つのGuardを共有する対称的構造だが、
     Test Coverageが非対称だった)。`test_news002_unknown_published_at_
     excluded_by_default_under_market_public_at_semantics`・`test_
     news013_future_article_not_visible_under_market_public_at_
     semantics`を追加した(`bash 9229280`)。
   - **[LOW、対応不要、情報提供のみ]** `updated_at`Fieldの設定経路未設計
     という指摘は、既に`JAPAN_NEWS_ARCHITECTURE.md`/DECISIONS.md Known
     Limitationsで正直に開示済みであり、実害を及ぼすExecution Pathも
     現状無い(Adapter未実装)ことをpit-auditor自身が確認・追認した。
2. **skeptic-reviewer**: `PASS_WITH_CONCERNS`。2件のMEDIUM・1件の
   LOW-MEDIUM・1件のLOWを独立に再確認した:
   - **[MEDIUM、採用・修正]** `find_same_source_native_id_signals()`が
     `source_native_id`のみでGroupingしており`source_id`でScopeして
     いない、という指摘を実際にCodeを読んで確認した(4候補中`source_
     native_id`のGlobal一意性が確認できたSourceは無い)。Grouping Keyを
     `(source_id, source_native_id)`のTupleへ変更し(`source_id`は
     `__post_init__`で非空必須の既存Field、追加Costゼロ)、異なるSource
     間の誤検出が起きないことを直接検証する新規Test(`test_news008_
     same_native_id_from_different_sources_is_not_flagged`)を追加した
     (`bash 9bd5d51`)。
   - **[MEDIUM、Documentationで対応]** `news_article_to_evidence()`が
     常に`EvidenceType.FACT`を付与しており、`lib.evidence.model`自身の
     Evidence Type定義(FACT vs CLAIM、発言の存在自体はFACTだが内容の
     真偽は別)との緊張関係を検討していなかった、という指摘を確認した。
     PR TIMES(`COMPANY_PRIMARY`)の見出しは発行企業自身の自由記述であり、
     TDnetの定型的な文書Title(Disclosures Evidenceが同じくFACT扱いする
     前例)とは性質が異なりうる。ただし現時点でこのEvidenceを実際に
     消費するExecution Path・実Adapterのいずれも存在しないため
     (`test_news015_*`確認済み)、Code変更(新しいClaim判定Logic導入)は
     このRoundでは行わず、`evidence.py`のDocstringへ「FACTは『この見出し
     の記事が公開された』というMeta-level事実であり、見出し内容自体の
     真偽を主張しない」ことを明記し、将来PR TIMES等実Adapter実装時に
     再検討すべきKnown Limitationとして記録した(`bash 9bd5d51`)。
   - **[LOW-MEDIUM、採用・修正]** `lib.evidence.news.NewsEvent`との境界
     判断(妥当な設計判断だが)が、D0057境界(Backlog #21 + Structural
     Test)と同じ厳密さでTrackingされていなかった、という指摘を確認した。
     `VALIDATION_BACKLOG.md`行26を追加し、D0057境界Testと同じAST解析
     手法で`lib/news/`のいずれのModuleも`lib.evidence.news`をImportしな
     いことを固定する`test_news_modules_never_import_evidence_news_
     event_scaffold`を追加した(`bash 9bd5d51`)。
   - **[LOW、対応せず、Known Limitationとして記録]** `NewsDuplicate
     RelationKind.UNKNOWN`が実質的に到達不能なMemberである、という
     指摘を確認したが、これは`lib.disclosures.model.DuplicateRelation
     Kind`が既に持つ同型のPatternをそのまま踏襲したものであり、この
     Round固有の新規Dead Codeではないと判断し、変更しなかった。

Blocker/High Findingはいずれのpassでも無し。

### このDecisionでやらないこと

Global News(4E-3)・Consensus/Expectations(4E-4)・News Sentiment・Event
Extraction・Topic Model・Embeddings/Vector DB・LLM Summarization
Pipeline・Continuous Crawler・Monitoring/Alerts・Backtest統合・Decision
Engine統合・BUY/SELL・Regime判定のいずれにも着手していない。D0057
(Validation Backlog #21)は解決していない(維持)。TDnet/Company IR/
Positioning/Macro/Global Marketの既存Validation Backlogは同時に消化して
いない。

---

## D0059 — Phase4E-3: Global News Data Foundation(既存NewsArticleRecordの拡張、Adapter未実装)

海外発News記事のMetadata(見出し・公開時刻・出所・多言語・配信経路・
Provenance)をPIT-safe/multilingual-aware/timestamp-aware/provenance-
preservingな形でこのLabへ取り込むための拡張を行った。**Sentiment判定・
Event抽出・Impact Scoring・日本株へのMapping・Investment Conclusion・
BUY/SELLは一切実装していない**(Observationまで、Phase4E-3要件§30/§31)。

### 最重要の設計判断: 専用Modelを作らず、既存NewsArticleRecordを拡張

ユーザー要件§3が明示的に指示した通り、まずPhase4E-2の`NewsArticleRecord`/
既存原則を確認し、専用のGlobal News Modelを即座に作らなかった。
Repository Reality Checkの結果、`language`は既にPhase4E-2からFirst-class
Fieldであり、Global News固有要件(多言語Identity・Syndication・地理・
Timezone Provenance)は全て既定`None`のOptional Field追加のみで表現
可能と判断した。追加した9Field: `original_article_id`/`translated_from_
article_id`/`language_variant`/`wire_origin`/`publisher`/`country`/
`region`/`jurisdiction`/`source_declared_timezone`。

**検証方法**: 拡張後、既存Japan News Test(`test_news_model.py`/`test_
news_pit.py`、計53件)を無変更のまま再実行し、全て成功することを確認
した(`bash 5930d12`)。詳細は`GLOBAL_NEWS_ARCHITECTURE.md`参照。

### lib/news/normalize.py・view.py・evidence.pyはFunction本体を1行も変更していない

ユーザー要件§27(既存`news_as_of()`がGlobal Newsに安全に再利用できるか
確認し、必要な場合のみ最小限拡張する)に対し、`13_tests/test_global_
news_pit.py`(GNEWS-001〜018、24件)を新設して既存Function群をGlobal
Newsの実際のシナリオ(複数Timezoneを跨ぐPublished/Provider Availability・
翻訳記事・Syndication・曖昧Timezone略称)で駆動し、既存Semanticsが
そのまま正しく機能することを確認した。「拡張が要るかどうかを確認する」
という要件を、確認Testを書くことで実行した(`bash e1725fd`)。

### Multilingual Identity(§9〜11、最重要論点の一つ)

同じ出来事についての英語/日本語/フランス語記事は必ずしも同じArticleでは
ない、というユーザー要件の核心原則をArticle Identity判定から直接反映
した: `source_id`+`source_native_id`(Safe Tier)のみでArticle Identity
を判定し、`language`/`original_article_id`/`translated_from_article_id`/
`language_variant`はArticle Identity判定に一切使わない
(GNEWS-006で構造的に確認)。翻訳記事は自動的にDuplicateとしてFlagされ
ない。これらのFieldはSourceが明示的に確認できた場合のみ設定し、翻訳
Content類似度だけからの推測は行わない。

### Syndication: Publisher / Wire Origin / Retrieval Sourceの3層分離(§12)

Source Integration Skillの`SOURCE-005`(TDnet統合で確立した3層分離)を
News Syndicationへ適用した: `wire_origin`(記事の原典Wire Service)・
`publisher`(実際に掲載したWebsite/媒体)・`source_id`(既存Field、
このLabの実際のRetrieval Source)を独立に記録する。ReutersとBloomberg
がそれぞれ同じEventについて書いた記事はArticle自体が別物であり
(GNEWS-007、Article Identity != Event Identity、§20)、同じ`wire_origin`
でも`publisher`が異なれば自動的に同一Articleとはみなさない(GNEWS-008)。

### Timezone Safety(§14、Global Newsで最も重要な論点)

tz-aware datetimeのみを受け付ける既存原則(naive datetime拒否)を継続。
EST/CST/IST等の曖昧なTimezone略称は一意のIANA Timezoneへ自動変換
しない——D0056(Global Market)で確認した`ZoneInfo("EST")`固定UTC-5問題
と同じ懸念が、今回のGlobal News Source候補調査(SEC RSS)でも実際に
再確認された。新規`source_declared_timezone`Field(Sourceが記事に添えた
Timezone文字列を**そのまま**保持する)を追加し、`lib/news/`のいずれの
Function(`normalize`/`view`/`evidence`)からも読まれないことをSource
全文に対する文字列探索(GNEWS-016のAST走査とは異なる手法)で固定した
(GNEWS-004、`test_gnews004_source_declared_timezone_is_never_read_
by_normalize_view_or_evidence`)。曖昧な略称値もそのまま
文字列として保持され、解析・変換されない(`test_gnews004_ambiguous_
abbreviation_stored_as_is_without_iana_conversion`)。異なるTimezoneを
跨ぐPublished/Provider Availability(US Eastern基準とCET基準)でも
`news_as_of()`が正しくUTC比較で動作することをGNEWS-001/GNEWS-003で
実際のReal `zoneinfo.ZoneInfo`を使って確認した。

### D0057との境界、NewsEventとの境界(いずれも維持、解決しない)

`news_article_to_evidence()`は既存Functionのまま適用可能だが、この
Roundでも一切Backtest/Decision Engineへ接続しない(§28)。D0057
(ARCHITECTURE_GAP、Validation Backlog #21)は未解決のまま維持し、
Phase4E-2の`test_news015_*`に加えGNEWS-016(`test_gnews016_news_
evidence_module_never_imports_retrieval_or_filter_usable_at`)で
Global Newsの文脈でも同じ境界をAST走査で再確認した。`lib.evidence.
news.NewsEvent`(Event層)との分離もPhase4E-2から無変更のまま維持し
(`NewsArticleRecord`拡張後も`event_type`Fieldは追加していない)、
既存Structural Test(`test_news_modules_never_import_evidence_news_
event_scaffold`)は拡張後も無変更のまま成功する。

### Source Candidate Landscape(data-source-researcher Agent、2026-08-18)

Reuters/LSEG・Bloomberg・AP・AFP・SEC・Federal Reserve・US Treasury・
ECB・Bank of England・英国政府(gov.uk)・EC Press Corner・PBOC・GDELT・
NewsAPI.org・Google News RSS・LSE RNS・Nasdaqを調査した。全て`EGRESS_
BLOCKED`のためSEARCH-SNIPPET-DERIVED(UNVERIFIED)に留まった。

Wire Service勢(Reuters/LSEG・Bloomberg・AP・AFP)はEnterprise契約前提で
あり個人ローカル実行という本Labの前提にそぐわないため除外。政府/中央
銀行RSS群は概ね無料・認証不要だがPIT関連詳細が軒並み未確認——SEC RSSの
"EST"年間固定Timezone Label疑義とUS TreasuryのRSS実Replay Bug(2021年)
は、Government RSS全般に対する具体的なPIT Risk事例として特に重要と
判断した。GDELT DOC 2.0は最もTimezone Documentationが明確な候補だが
News全文ではなくEvent-level Metadataの配信である点を正直に記録した。
NewsAPI.orgは全文再配布不可というTerms自体が明確だが全文保存前提の
このLabの用途に合わないため除外。Google News RSSは非公式・無Document
のため除外。詳細は`GLOBAL_NEWS_ARCHITECTURE.md`「Source Candidate
Landscape」節参照。

### Adapterは1件も実装しない(ユーザー要件§33に基づく正直なStatus)

`gdelt_doc_2`(VERIFIED_SECONDARY)・`sec_press_release`
(PRIMARY_OFFICIAL)の2件のみを`implementation_status=NOT_IMPLEMENTED`
のまま`lib/news/catalog.py`へ登録し、Validation Status=`DESIGN_
COMPLETE_AWAITING_SPEC_VERIFICATION`を`known_limitations`へ明記した
(`bash 7f4a88d`)。

### Tests(GNEWS-001〜018、実装からのコピーではなくユーザー要件から導出)

`13_tests/test_global_news_pit.py`(24件)・`test_global_news_catalog.py`
(10件)、合計34件を新規追加。実Network接続無し、合成Record Dataのみ
使用(実際のTimezoneはReal `zoneinfo.ZoneInfo`を使うが、実Network越しの
確認ではなく構文としてのTimezone Objectの使用)。

### このDecisionでやらないこと

Consensus/Expectations(4E-4)・NewsEvent Reconciliation・D0057(Validation
Backlog #21)の解決・News Sentiment・Event Extraction・Topic Model・
Embeddings/Vector DB・LLM Summarization Pipeline・Translation
Pipeline・Continuous Crawler・Monitoring/Alerts・Backtest統合・Decision
Engine統合・BUY/SELL・Regime判定のいずれにも着手していない。TDnet/
Company IR/Positioning/Macro/Global Market/Japan Newsの既存Validation
Backlogは同時に消化していない。

### Reviewer Pass(pit-auditor 1回・skeptic-reviewer 1回、Findingsは全て独立に再確認の上で採否判定)

1. **pit-auditor**: `3 FINDINGS(highest severity: MEDIUM)`。3件とも独立に
   Code(`lib/news/normalize.py`/`view.py`/`13_tests/test_global_news_
   pit.py`)を直接読んで再確認の上で対応した。
   - **[MEDIUM、採用・修正]** GNEWS-016のAST走査が`node.module`/
     `alias.name`をそのまま比較していたため、`from lib.evidence import
     retrieval`のような「Packageをimportして属性経由でAccessする」形の
     D0057境界違反を見逃す構造だった、という指摘を実際にTest Codeを
     読んで確認した(現時点で実際の違反は無い、Test自体の検出漏れ)。
     `ImportFrom`のFully Qualified Path(`f"{node.module}.{alias.name}"`)
     を組み立てて判定するよう修正した。
   - **[LOW、Documentationで対応]** GNEWS-004(`source_declared_timezone`
     未参照確認)は実装上「AST走査」ではなく「Source全文への文字列探索」
     である、という指摘を確認した(GNEWS-016と混同されて`GLOBAL_NEWS_
     ARCHITECTURE.md`/DECISIONS.mdの両方で"AST走査"と誤記されていた)。
     安全性そのものは文字列探索でも同等以上に確認できているため
     Code変更は行わず、両Documentの文言を「Source全文に対する文字列
     探索(GNEWS-016のAST走査とは異なる手法)」へ訂正した。
   - **[LOW、採用・修正]** GNEWS-002が`timestamp is None`(Timestamp自体
     が無い)分岐しか踏んでおらず、「Timestampはあるが`_basis`が未確認」
     というGDELT/SEC RSS等のScraped Timestampで現実的に起こりうる分岐を
     確認していなかった、という指摘を`view.py`のGuard Logicと突き合わせて
     確認した。`test_gnews002_unconfirmed_basis_excluded_even_when_
     timestamp_itself_is_present_and_past`を追加した。
2. **skeptic-reviewer**: `PASS_WITH_CONCERNS`。3件のMEDIUM・1件の
   LOW-MEDIUM・2件のLOWを独立に`lib/news/normalize.py`のFunction本体を
   読んで再確認した:
   - **[MEDIUM、Test追加で対応]** GNEWS-006が「構造的に確認」と説明され
     つつ、実際には`source_native_id`が異なる2記事を使っており、その差
     だけで結果が決まる(`translated_from_article_id`等を読んでいない
     ことの直接証拠にならない)、という指摘を`normalize.py`を読んで確認
     した。GNEWS-004と同じ手法(Source全文への文字列探索)で翻訳関連
     Field名自体が`normalize.py`/`view.py`/`evidence.py`のいずれにも
     登場しないことを直接確認する`test_gnews006_translation_fields_
     never_read_by_normalize_view_or_evidence`を追加した。
   - **[MEDIUM、Documentationで対応]** GNEWS-007/GNEWS-008(Cross-source
     Duplicate/Syndication)が「意味論的にEventを区別した」証拠として
     説明されていたが、`find_same_source_native_id_signals()`は
     `headline`/`wire_origin`/`publisher`のいずれも一切読まないため、
     異なる`source_id`を持つ記事は実際の内容に関わらず常にPass-Through
     される、という指摘を`normalize.py`の関数本体を読んで確認した(Code
     自体は既存の安全な設計、Test/Documentationの説明が実際の証明範囲を
     超えていた)。該当Testのdocstring、`GLOBAL_NEWS_ARCHITECTURE.md`
     該当節を「`source_id`によるScopingがAnyのContentに対して安全側に
     倒れることのPinning Testであり、Event Identity認識の証明ではない」
     という正確な表現へ訂正した。
   - **[MEDIUM、Documentationで対応]** GNEWS-013(No Event Inference)の
     2Testが、実際にはInference Logic自体が存在しないFieldへNoneを渡して
     Noneが返るだけのStrawman Checkである、という指摘を確認した(model.py
     の`__post_init__`にHeadline/Language解析Logicが無いことは事実、
     このRoundにはAdapterが無いためInference Logic自体が実在しない)。
     該当Testのdocstringと`GLOBAL_NEWS_ARCHITECTURE.md`該当節へ、これらが
     「将来Adapter実装時のRegression Guard」であり「洗練されたInference
     試行への防御を証明したもの」ではない旨を明記した。
   - **[LOW-MEDIUM、Test追加で対応]** 新規9Field中`region`/`jurisdiction`
     の2つがどのTestからも一度も値を渡されておらず(`13_tests/`全体を
     Grepして確認)、ルートCLAUDE.mdの「新機能には必ずTestを追加する」
     原則に反する、という指摘を確認した。`test_region_and_jurisdiction_
     are_stored_as_given_not_inferred`/`test_region_and_jurisdiction_
     default_to_none_when_not_supplied`を追加した。
   - **[LOW、Test追加で対応]** `find_exact_raw_content_duplicate_groups()`
     がこのRoundの新規Test(`test_global_news_pit.py`)から一度も呼ばれて
     おらず、Global Newsシナリオでの確認が漏れていた(このRound自身の
     Reviewer Focus Areaが明示的に指名していた関数であるにも関わらず)、
     という指摘をFile全体のGrepで確認した。
     `test_find_exact_raw_content_duplicate_groups_detects_pagination_
     overlap_in_global_feed`を追加した。
   - **[LOW、対応不要、既にDocument済みと確認]** `wire_origin`/`publisher`
     /`source_id`、`country`/`region`/`jurisdiction`がCross-field整合性
     検証を持たないFree-text Fieldである、という指摘は、`model.py`
     Docstring(SOURCE-005の3層分離を意図的にそのまま適用した設計)で
     既に明記済みであり、このRoundにAdapterが1件も無いため実害を及ぼす
     Execution Pathも現状無いことを確認した。

Blocker/High Findingはいずれのpassでも無し。修正後、全Test(`13_tests/
test_global_news_pit.py`は24件→29件、Lab全体は887件)を再実行し成功を
確認した(`bash <このCommit>`)。

---

## D0060 — Phase4E-4: Consensus / Expectations Inputs Data Foundation(設計・実装、Adapter未実装)

将来Expectations Engineに必要となる「その時点でProviderが観測していた
Analyst Consensus/Estimate」を、PIT-safe/vintage-aware/source-aware/
provenance-preserving/reproducibleな形で表現するData Foundationを新設
した。**Beat/Miss・Surprise・Priced-in・Investment Conclusion・
Expectations Engine本体・Backtest統合は一切実装していない**
(Observationまで、Phase4E-4要件§1)。

### Repository Reality Check(最重要の設計判断)

`lib.evidence.model`(`RevisionHistory`/`SourceVersion`/
`AvailabilityBasis`)・`lib.fundamentals.model`(`PeriodType`/
`ConsolidationScope`)・`lib.sources.catalog`(`DataCapability.
EXPECTATIONS`が既に存在)を先に確認し、Consensus専用のVersioning
Frameworkを新設しない、という判断を最初に固定した(Phase4E-4要件§7)。
新設したのは`StatisticType`/`ForecastHorizon`のみ——既存Capability群に
相当する概念が存在しない、Consensus固有の区別軸である。

`ConsolidationScope`/`PeriodType`はFundamentalsのModuleから直接Import
して再利用する(独自の重複Enumを作らない)。`accounting_scope`は
`ConsolidationScope | None`(Optional)として扱い、Fundamentals自身の
Enumへ`UNKNOWN` Memberを追加する変更は一切行っていない(Fundamentalsの
既存Behaviorへの影響ゼロ、既存Testも無変更のまま成功)。

### Vintage / Forecast Evolution != Correction

Vintage管理は`lib.evidence.model.RevisionHistory`/`SourceVersion`を
そのまま再利用し(Fundamentals/Positioning/Macro/Global Marketと同一
Primitive)、`lib.consensus.normalize.build_revision_histories()`は
`is_correction`を常に`False`のまま構築する(Sourceが明示的に
Correctionと述べない限り`True`へ変更しない、`lib.macro.normalize`/
`lib.positioning.normalize`と同じEVIDENCE-003原則の踏襲)。

### consensus_as_of の命名衝突回避

Providerが返す"As of"値(`ConsensusRecord.provider_stated_as_of`)は、
Snapshot計算時刻・Analyst Cutoff時刻・Website表示日等Source-specificな
意味を持ち、統一的な`provider_available_at`の代用にならない
(Phase4E-4要件§13)。Record Field名`provider_stated_as_of`とPIT View
Function名`lib.consensus.view.consensus_as_of()`を意図的に区別する
命名にし、混同を防いだ。`provider_stated_as_of`が`normalize.py`/
`view.py`/`evidence.py`のいずれからも実際にAttribute Accessされない
ことをAST走査で構造的に確認した(CONS-003)。

### Fiscal Period Identity

`period_type`(Fundamentals由来)・`target_period_start`/`target_
period_end`(Explicit Period)・`provider_target_period_id`(Provider
Native識別子)を優先Identityとし、`forecast_horizon`(Relative Label、
新設)は補助情報に留める(Phase4E-4要件§17〜19)。`fiscal_year_end`を
独立Fieldとして保持し、Calendar Yearとの混同を防ぐ(CONS-026)。

### Source Candidate Research(data-source-researcher Agent、2026-08-19)

LSEG/Refinitiv I/B/E/S・Bloomberg BEst・FactSet Estimates・S&P Capital
IQ・Visible Alpha・QUICK・IFIS Japan・Nikkei NEEDS/Compass・Alpha
Vantageを調査した。ほぼ全てが`EGRESS_BLOCKED`だったが、data-source-
researcher Agentが2つの非公式Client Code(GitHub上、実際に読めた、
`VERIFIED_SECONDARY`)を確認し、**Alpha Vantageの`EARNINGS_ESTIMATES`
Endpointの存在自体が確認できなかった**(存在しない可能性が高いと
判断し、Catalog登録を見送った)。

**Wire Enterprise勢**(LSEG/Bloomberg/**FactSet Estimates PIT
Consensus**/S&P Capital IQ/Visible Alpha)はTerminal/Platform契約前提の
Enterprise専用と判断しCatalog未登録(個人ローカル実行という本Labの
前提にそぐわない)。当初FactSetのみ「Timestamp Semantics最も具体的
だから」という理由でBenchmark参照目的の例外としてCatalog登録して
いたが、skeptic-reviewer Findingで他4候補への除外基準(ENTERPRISE
専用)と直接矛盾していることが指摘され、統一してCatalog未登録へ変更
した(詳細情報は`CONSENSUS_ARCHITECTURE.md`のSource Landscape節に
残す)。**QUICK Consensus**(Japan Coverage最強の主張、data-source-
researcher推奨順位1位)・**IFIS Japan**(PIT根拠が他候補より弱いことを
正直に開示)の2候補のみCatalogへ登録した。Nikkei CompassはService終了
を確認し除外、Nikkei NEEDSはSell-side Consensus自体の存在が未確認の
ため登録見送り。詳細は`CONSENSUS_ARCHITECTURE.md`「Source Candidate
Landscape」節参照。

### Adapterは1件も実装しない(ユーザー要件§9に基づく正直なStatus)

検索Snippetのみを根拠にAdapterを実装しない、というユーザー要件に従い、
2候補全てを`implementation_status=NOT_IMPLEMENTED`のまま`lib.consensus.
catalog`へ登録し、Validation Status=`DESIGN_COMPLETE_AWAITING_SPEC_
VERIFICATION`を`known_limitations`へ明記した。

### Company Guidance / Actual Boundary

`ConsensusRecord`にはGuidance/Actual専用に見えるField名(`guidance_
value`/`actual_value`/`actual_or_forecast`等)を一切持たない
(CONS-012/CONS-013で確認)。ただしこれは特定Field名の不在確認に限られ、
`value`Field自体はFundamentalsと同型のGeneric Numeric Fieldであり、
分離の実効性はModule境界のConvention Levelで担保される旨をTest
Docstring自身に明記した(skeptic-reviewer Finding、Phase4E-4:
CONS-029/030が既に採用していた「Mechanical Pinning」という自己限定的
説明を、この確認にも一貫して適用した)。Company GuidanceもActual
Resultも既存`lib.fundamentals`側の責務であり、このModuleへ複製しない。

### Tests(CONS-001〜030、実装からのコピーではなくPhase4E-4要件から導出)

`13_tests/test_consensus_pit.py`(37件)・`test_consensus_catalog.py`
(9件)、合計46件を新規追加。実Network接続無し、合成Record Dataのみ
使用。以下3点をこのRound最初から反映した(前Round Reviewer Findingの
予防的適用、詳細は`CONSENSUS_ARCHITECTURE.md`「Reviewer教訓の反映」
節):

1. 「Fieldが読まれていないこと」の確認はAST Attribute Access走査
   (Phase4E-3 pit-auditor Findingの教訓)。
2. 「Moduleをimportしていないこと」の確認はFully Qualified Path走査
   (Phase4E-3 pit-auditor Finding、GNEWS-016検出漏れの教訓)。
3. Forbidden Term Scanは、Module自身のDocstringが「〜を生成しない」と
   説明するために使う語自体(例: "beat"という語が「Beat/Missを生成
   しない」という説明文に含まれる)を誤検出しないよう、AST Docstring
   除外Textで実施する——このRound自身の実装中に実際に遭遇し
   (`lib.consensus.model`のDocstring)、その場で修正した。

CONS-016(Historical API Response Is Not Historical Vintage)はAdapter
自体が無く再現するExecution Pathが無いため、News/Global Market/Macroと
同じくCode Testではなく`CONSENSUS_ARCHITECTURE.md`のKnown Limitation
として文書化するに留めた。

### Known Limitations

- Adapterを1件も実装していない(2候補全て`NOT_IMPLEMENTED`、
  Validation Status=`DESIGN_COMPLETE_AWAITING_SPEC_VERIFICATION`)。
- QUICK/IFISいずれも公式仕様をこのSessionから直接確認できていない
  (`EGRESS_BLOCKED`)。
- QUICK Consensusが個人/自営業者でも契約可能なTierを持つかが最大の
  未解決論点(次の最優先検証項目)。
- `entity_id`(Canonical Entity Registry)へのMapping手法は未設計。
- Individual Analyst Estimate(v1では扱わない、Phase4E-4要件§26)は
  `ConsensusRecord`のField構成に含まれていない。
- CONS-016はCode Testではなく文書上のKnown Limitationとして記録する
  に留めた(Adapter未実装のため再現不能)。
- `lib/consensus/catalog.py`の2 Descriptorは`SourceCatalog`への実際の
  Wiring(Application起動時の一元登録)がまだ無い(既存の慣行のまま)。
- CONS-020(`_module_never_imports`)のAST走査は、相対Import・Package
  経由の属性Access・動的Importには対応しないBlind Spotがある(pit-
  auditor Finding、Phase4E-4、LOW)。現状`lib/consensus/`はAbsolute
  Importのみで実害は無いが、将来Refactorでこの Guard の厳密性に依存
  する場合はFunctional Checkの追加を検討する必要がある。

### Reviewer Pass(pit-auditor 1回・skeptic-reviewer 1回、Findingsは全て独立に再確認の上で採否判定)

1. **pit-auditor**: `2 FINDINGS(highest severity: LOW)`。2件とも独立に
   Code(`13_tests/test_consensus_pit.py`)を直接読んで再確認の上で
   対応した。
   - **[LOW、採用・修正]** `test_cons004_no_available_at_timestamp_
     excluded_by_default`という名前が「除外される」と主張しながら、
     実際のAssertion(`is not None`)は「除外されない」ことを示して
     おり矛盾していた、という指摘を実際にTest Codeを読んで確認した
     (Test Helper`_resolver`が楽観的にretrieved_at/OBSERVED Basisへ
     Fallbackするため)。Testを`test_cons004_resolver_fallback_to_
     retrieved_at_is_a_caller_choice_not_a_framework_guarantee`へ
     Renameしてこの挙動を正確に説明し、CONS-004本来の主張(Timestamp
     が無くResolverが誠実にUNKNOWN Basisを返す場合は除外される)を
     直接検証する`test_cons004_pessimistic_resolver_reporting_
     unknown_basis_is_excluded_by_default`を追加した。
   - **[LOW、Documentationで対応]** `_module_never_imports()`のAST
     走査が、Phase4E-3で修正した`from X import Y`型の検出漏れは正しく
     閉じているものの、相対Import・Package経由の属性Access・動的
     Importには対応しないBlind Spotが残る、という指摘を実際にHelper
     関数のCodeを読んで確認した(現状`lib/consensus/`はAbsolute
     Importのみで実害は無いことをGrepで確認済み)。Code変更ではなく
     `CONSENSUS_ARCHITECTURE.md`/DECISIONS.mdのKnown Limitationとして
     記録した。
2. **skeptic-reviewer**: `PASS_WITH_CONCERNS`。1件のHIGH・3件のMEDIUM・
   1件のLOWを独立にCode/Documentを読んで再確認した:
   - **[HIGH、採用・修正]** `ConsensusRecord.series_id`のDocstringが
     列挙する構築責務Axis一覧から`source_id`(Provider)が抜けており、
     このRound最大の原則「Provider AのMean != Provider BのMean」を
     `series_id`構築の場面で徹底する記述が無かった、という指摘を
     `model.py`/`CONSENSUS_ARCHITECTURE.md`を読んで確認した(`lib.
     macro.model.MacroRecord`のDocstringがSourceを責務一覧の筆頭に
     挙げている前例より弱い記述になっていた)。両Documentの一覧へ
     `source_id`を明示的に追加し、この原則との結び付きを説明する文言
     を加えた。
   - **[MEDIUM、Documentationで対応]** CONS-012/013が「Guidance/
     Actual値Fieldが無いことを構造的に確認した」と説明されていたが、
     実際に確認しているのは特定Field名の不在のみであり、`value`Field
     自体はGeneric Numeric Fieldで型レベルの強制は無いという限界が
     あった、という指摘を確認した。CONS-029/030が既に採用していた
     「Mechanical Pinning、意味論的証明ではない」という自己限定的な
     説明を、Test Docstring・両Documentへ一貫して適用した。
   - **[MEDIUM、Documentationで対応]** `adjustment_status: str | None`
     Fieldが、Module Docstring・Architecture Doc・DECISIONS.mdの
     いずれにも説明が無く、Test Coverageも皆無だった、という指摘を
     確認した(`lib.global_market.model.AdjustmentStatus`という類似
     名の既存Enumがあるにも関わらず転用しなかった理由も未説明だった)。
     Module Docstringへ「Global MarketのAdjustmentStatusとは異なる
     概念であり転用しない」という理由を明記し、Round-trip Testを
     追加した。
   - **[MEDIUM、採用・修正]** FactSetを「ENTERPRISE専用だがBenchmark
     参照目的」という別基準でCatalog登録していたことが、同じ理由
     (ENTERPRISE専用)で他4候補(LSEG/Bloomberg/S&P Capital IQ/
     Visible Alpha)を除外していた基準と直接矛盾しており、Catalog
     自体の目的(`lib.sources.catalog`Module Docstringが定める「実装
     候補の検索可能な一覧」)とも合わない、という指摘を確認した。
     FactSetのCatalog Descriptorを削除し、他のENTERPRISE専用候補と
     同じく`CONSENSUS_ARCHITECTURE.md`のSource Landscape節でのみ記録
     する扱いへ統一した(登録候補は`quick_consensus_japan`/`ifis_
     japan_consensus`の2件のみに変更)。
   - **[LOW、対応不要、既に適切な設計と確認]** CONS-028(Evidence
     Content Forbidden Term Scan)が固定Templateに対する検証であり
     現時点では自明に成功する、という指摘を確認したが、これは将来の
     Regression Guardとして正当な設計であり(Templateへ解釈語が
     混入する変更を検知する)、Code変更は行わなかった。

Blocker/High Findingはいずれのpassでも(HIGH1件を除き)重大な機能欠陥
ではなくDocumentation/Catalog設計の一貫性問題だった。修正後、全Test
(`test_consensus_pit.py`は35件→37件、`test_consensus_catalog.py`は
9件のまま[1件を`test_no_registered_candidate_is_flagged_enterprise_
only`へ差し替え]、Lab全体+Screening Tool合計933件)を再実行し成功を
確認した。

---

## D0061 — Phase4 Integrated Data Foundation Audit / Phase5 Readiness Gate(監査のみ、実装無し)

Phase4A〜4E-4で構築した10 Capability(Fundamentals/EDINET/TDnet/
Company IR/Positioning/Japan Macro/Global Market/Japan News/Global
News/Consensus)を横断的に監査し、Phase5(仮説事前登録・PIT-safeな
Datasetでの反証可能な検証)開始の可否を判定した。**新しいData Source
は追加していない。新しいCode変更は原則ゼロ**(Reviewer Pass対応分を
除く)。詳細な全内容は`PHASE5_READINESS.md`にのみ記録し、ここでは
要点と結論のみを記す(重複管理を避ける、§46)。

### Repository Reality Check(今回のAuditで最も重要な発見)

`scripts/jquants_lab_pipeline.py`(Repo Root、`Japanese_Equity_Lab/`
配下ではない)を実際に読み、**このLabで実際にBacktest Signal評価まで
配線されているのはJ-Quants Price + PIT Universe + `lib.point_in_time.
PointInTimeRecord` Gateのみ**であることを確認した。`lib.backtest.
engine.BacktestEngine.run()`のSignatureを直接確認し、Fundamentals/
Disclosures/Positioning/Macro/Global Market/News/Consensus/
`EvidenceRecord`のいずれも引数に持たないことを確認した。`lib.evidence.
model.filter_usable_at()`(Evidence経路のPIT Filter)は`lib/evidence/`
自身の外から一件も呼ばれていない(Grep確認)。この事実がD0057 #21の
Phase5 Blocker判定(下記)の直接的な根拠になる。

なお、この過程で使用した`Explore` Agentが、当初「`scripts/
jquants_lab_pipeline.py`は存在しない」という誤った報告をした(Prompt
がAgentの探索範囲を`Japanese_Equity_Lab/`配下のみに誤って限定していた
ため)。Main Claude自身が直接`find`/`Read`で再確認し、Repo Root配下に
実在することを確認した上で上記結論を確定した(Reviewer Evidence
Standardの「Agent Findingを鵜呑みにせず実Codeで独立再確認する」原則を
Main Claude自身の調査ミスに対しても適用した一例)。

### Capability Readiness Matrix(要約、全文は`PHASE5_READINESS.md`)

第6の区別を新たに明示した: **REAL DATA CONNECTED != PIT-SAFE USABLE**
(既存5原則§3に追加)。EDINETが好例——`implementation_status=CONNECTED`
で実データ疎通・Parseは確認済みだが、`pit_available=False`固定かつ
Documents Listが日次で書き換わるため「Historical Point-in-Time
Reconstructionはできない」とDocstring自身が明記している(実データ
接続済みであることと、PIT-safeにBacktestで使えることは別軸)。

READY_FOR_PHASE5: J-Quants Price、PIT Universe(いずれもPhase5対象外の
既存Primitiveだが参考として記録)。READY_WITH_RESTRICTIONS: この
Labelは単一の均質なTierではない(skeptic-reviewer Finding、下記
Reviewer Pass参照)——Fundamentals(`WIRING_UNDESIGNED`: 実データ4銘柄
Validated済みだが、Backtest Signal Loopへの接続点自体が`BacktestEngine.
run()`にまだ存在せず、検証以前に新規設計が必要)、Positioning
price_derived_liquidity(`VALIDATION_PENDING`: 上流Price BarはReal
Data Validated、既にCONNECTED配線済みで残るのはReal-data End-to-End
検証のみ)——両者の残作業は性質が異なり同程度に「Phase5で使える」
わけではないことを明示する。NOT_READY_FOR_PHASE5: EDINET(PIT不可)・
TDnet・Company IR・Positioning需給4候補・Japan Macro・Global Market。
NOT_RELEVANT_TO_PHASE5_V1: Japan News・Global News・Consensus
(Scope外であって禁止ではない、§45)。

### Validation Backlog Classification

既存33件は一切削除・書き換えしていない。全件へPhase5 Dependencyを
付与した(`PHASE5_READINESS.md` C節)。**BLOCKS_PHASE5に分類された
項目はゼロ件**。TDnet(#1)・Company IR(#2/#3)はBLOCKS_SPECIFIC_
CAPABILITY_ONLY(該当Capabilityを使う場合のみ)、Positioning
price_derived(#10)はSHOULD_RESOLVE_BEFORE_PHASE6(推奨だが必須では
ない)、残り(Macro/Global Market/News/Consensus関連19件)はLONG_TERM_
VALIDATIONまたはOPTIONAL。

### D0057 / Backlog #21 — NON_BLOCKER(条件付き)

判定基準§34(A実際に使用 AND B Concrete Failure Mode AND C既存Guardで
防げない)のAが不成立(Evidence経路はPhase5含め本番Callerがゼロ)ため
NON_BLOCKER。ただし**Phase5 v1が`EvidenceRecord` → `filter_usable_at()`
→ Backtestという経路を新規に配線した瞬間、#21はBLOCKERへ転化する**
条件付き判定である旨を明記した。Backlog #21はOPENのまま維持、今回
Common Coreは一切変更していない(§11で明示禁止された`retrieval_mode`
/Evidence Availability再設計/新Indexer/Event Engineのいずれにも
着手していない)。

### RevisionHistory Tie-break — NON_BLOCKER

§12基準A〜Dで評価: Phase5 v1候補(Fundamentals/Positioning
price_derived)いずれも実データで同一`available_at`衝突の発生実績が
無く(A=いいえ)、§34の「Concrete Failure Mode」要求を満たさないため
NON_BLOCKER。既存Macro向けPinning Test(`test_tie_on_identical_
available_at_is_input_order_dependent_known_limitation`)は維持、新規
Secondary Key追加は行っていない(§12末尾の明示禁止に従う)。

### NewsEvent Reconciliation — NON_BLOCKER

Japan/Global NewsがPhase5 v1 Scope外(`NOT_RELEVANT_TO_PHASE5_V1`)の
ため無関係。Backlog #26はOPENのまま維持、Event Layer/Reconciliation
Layerいずれも実装していない(§13で明示禁止)。

### Phase5 PIT Source of Truth(推奨、実装無し)

Phase5 v1は既存の実配線Pipeline(`BacktestEngine`+`PointInTimeRecord`
+`PriceHistorySource`/`AsOfAdjustedPriceHistory`+
`ListingBasedUniverseProvider`)を、実際にSignal評価されるBacktest
Executionの唯一のPIT Source of Truthとする。Capability-level `*_as_of()`
はBacktest Executionへまだ接続せず、Research観察専用のOffline Read
Pathとして扱う。Evidence経路(`filter_usable_at()`)はPhase5 v1では
一切使用しない。二重Gateを曖昧に併用しない、という§32要求への回答
として、この単一の推奨を明示した(実装は次Round)。

### Entity/Series Identity、Catalog、Status Consistency

Macro/Global Market/Consensusの`series_id`Caller責務パターンに
Collapse Riskがあることは既存Decisionで確認済み(Macro/Global Market
はPinning Test化済み)。Phase5 v1が実際に使うFundamentals/Positioning
price_derivedはいずれも実データでCollapse無く動作確認済み。Catalogは
全10 Capabilityとも単独Descriptor登録のみ(一元Instantiate無し、
既存の一貫した設計、今回Registry再設計はしていない)。
`ImplementationStatus`と自由記述Validation Statusの矛盾する組み合わせ
(例: `NOT_IMPLEMENTED`+`LIVE_VALIDATED`)は発見されなかった。

### Phase5 v1 Allowed / Forbidden Data

`PHASE5_READINESS.md` I節/J節に全文記録。Allowed: J-Quants Price・PIT
Universe・Fundamentals(要新規配線設計)・Positioning price_derived
(Backlog #10解消推奨)。Forbidden: EDINET(PIT不可)・TDnet・Company
IR・Positioning需給4候補・Japan Macro・Global Market・Japan News・
Global News・Consensus(理由はSPEC_UNVERIFIED/FIXTURE_ONLY/NO_
HISTORICAL_VINTAGE等、Capabilityごとに異なる)。いずれもModel/
Architecture/Fixture Testの存在自体は維持する(架空Adapterを作る・
既存Codeを削除する、いずれも行っていない)。

### Proposed Phase5 v1 Scope(提案のみ、実装しない)

PIT-safe Dataset Contractの明文化・Price+PIT Universeのみでの単純な
仮説の一気通貫Backtest・Train/Validation/Locked Test分割の`Experiment
Registry`上での表現設計・Fundamentals新規配線設計、の4項目を次Round
の課題として提案した(`PHASE5_READINESS.md` N節)。今回は実装しない。

### Reviewer Pass(pit-auditor 1回・skeptic-reviewer 1回、Findingsは全て独立に再確認の上で採否判定)

1. **pit-auditor**: `2 FINDINGS(highest severity: LOW)`。この監査は
   Claims-Verificationとして実施(A〜I節の各主張を実Codeへ直接照合)、
   Main Claude自身も独立に`git diff --stat ba8d33b..866feca -- core/
   app.py tests/ scripts/`を実行しProtected Path無変更を再確認した
   (pit-auditor自身はBash Tool制約でこの点を検証できなかったため)。
   - **[LOW、採用・修正]** Section Aの`scripts/jquants_lab_pipeline.py`
     Import一覧が「のみ」と主張しつつ、実際には`lib.data_sources.
     base/convert`・`lib.market_calendar`・`lib.registry.provenance`・
     `lib.reproducibility`・`lib.schemas.experiment/hypothesis`・
     `lib.snapshot`・`lib.strategies.fixed_pipeline_validation`を省略
     していたことを実際にFileを読んで確認した。完全なImport一覧へ
     修正し、重要なのは列挙の完全性ではなくPhase4 Capability/Evidence
     Moduleが一切含まれないことである旨を明記した。
   - **[LOW、採用・修正]** Section CのBacklog #26行が「E節で個別判定」
     と誤って参照していた(正しくはF節)ことを確認し修正した。
2. **skeptic-reviewer**: `PASS_WITH_CONCERNS`。1件のHIGH・1件のMEDIUM
   を独立にDocument/実Code両方を読んで再確認した:
   - **[HIGH、採用・修正]** `READY_WITH_RESTRICTIONS`という単一Label
     が、性質の全く異なる2種類の残作業(Fundamentals=Backtest接続点
     自体が未設計、Positioning=既にConnected配線済みで検証のみ残る)
     を同一Tierに見せてしまうという指摘を、Document自身のSection A/
     K/Nの記述と突き合わせて確認した。B-1表のLabelへ
     `(WIRING_UNDESIGNED)`/`(VALIDATION_PENDING)`のSub-tagを付与し、
     両者が同程度にPhase5で使える状態ではないことを明記する注記を
     追加した。DECISIONS.md本entryの該当箇所も同様に修正した。
   - **[MEDIUM、採用・修正]** E節(RevisionHistory Tie-break)の
     NON_BLOCKER判定が、§12 Aの問い(「発生し得るか」)に対し
     「4銘柄で未観測」という弱い論拠を主根拠にしていた、という指摘を
     確認した(より強い論拠は「そもそもPhase5 v1では自動Signal Loop
     に未接続のため実行経路自体が存在しない」というA節/K節の結論から
     直接導かれるもの)。E節の構成を、より強い論拠を主根拠として先に
     示す形へ差し替え、「4銘柄で未観測」は補助的根拠かつ小標本である
     旨を明記する形へ修正した。将来Fundamentals配線設計時にこの判定を
     無条件に引き継がず再評価すべき旨もN節item 4へ追記した。

Blocker/Highはいずれのpassでも重大な事実誤認ではなくDocumentation
Calibration/Cross-reference/論拠強度の問題だった(判定結論自体
[NON_BLOCKER×2、Blockerゼロ件]はいずれのReviewerもそのまま支持)。
Code変更は無し(Docのみ)。修正後、`pytest`(Lab+Screening Tool合計
933件)・`ruff check`・`ruff format --check`・`mypy`いずれもclean、
`git diff --stat -- core/ app.py tests/ scripts/`で変更が無いことを
再確認した。

## D0062 — Phase5 v1: Hypothesis Validation Pipeline実装 + Pre-run Review

D0061のPhase5 Readiness Gate(READY_WITH_RESTRICTIONS、Allowed Data =
Price + PIT Universeのみ)を受け、Phase5 v1 Hypothesis Validation
Pipelineを実装した。

**A. アーキテクチャ**: 新規`Japanese_Equity_Lab/lib/research/`
Package。既存`lib.schemas.hypothesis.Hypothesis`のLOCK-based
Immutability Patternをそのまま踏襲した`Preregistration`
(`preregistration.py`、DRAFT/PREREGISTERED、Core Fields hashによる
改ざん検知、`revise()`による新ID発行、Train/Validation/Locked Test
3期間の厳密な時系列非重複を`__post_init__`で強制)。`DatasetContract`
(`dataset_contract.py`、データ取得・PIT機構・調整方法等の宣言のみ、
データ自体は保持しない)。`LockedTestGate`/`FileBackedLockedTestGate`
(`locked_test.py`、RESEARCH_RULES.md「Hidden Test隔離」Roadmap
[RESEARCH→VALIDATION→LOCKED_TEST→FUTURE_PAPER_TRADE]をそのまま実装、
一度Unlockした後の再Unlockを拒否、Unlock状態はJSON Lines追記専用で
プロセスをまたいで永続化)。`PreregistrationRegistry`
(`registry.py`、`ExperimentRegistry`と同じ追記専用Pattern)。
`run_split()`(`runner.py`、新規Backtest Engineは作らず既存
`lib.backtest.engine.BacktestEngine`をそのまま呼ぶ薄いWrapper、
Preregistration状態Gate・Locked Test Gateを追加)。既存`Experiment`
schemaへ`preregistration_id`/`dataset_contract_hash`をOptional
追加(拡張、複製ではない)。原則ベースTest `VAL-001`〜`VAL-027`
(`13_tests/test_research_validation_pipeline.py`)。

**B. First Hypothesis(H0001: Short-term Reversal)**:
`04_hypotheses/H0001_2026-08-19_short_term_reversal.md`。直近5営業日
Trailing Close-to-Close Returnが負ならBUY、10営業日保有
(`lib/strategies/short_term_reversal.py`)。既存
`lib.strategies.fixed_pipeline_validation`(20営業日Momentum→
60営業日保有、Pipeline配線確認専用)と機構的に対称だが符号が逆であり、
RESEARCH_RULES.mdが既に記録する「燃え尽きた期間」
(2022-01-04〜2024-12-30・7203/6758/8056/3626)とはMechanism・
パラメータ・対象期間の全てで区別した。Preregistration
(`PREREG0001`)は`scripts/phase5_v1_short_term_reversal.py`
`build_preregistration()`で構築し`.preregister()`で固定、
`06_backtests/preregistrations.jsonl`へ記録済み。

**C. データ境界**: このセッションはJ-Quants公式APIへ接続できない
(EGRESS_BLOCKED)ため、Train/Validation/Locked Testの全期間は
既存の合成Fixture(`13_tests/fixtures/synthetic_jquants_v2_bars.json`、
2026-01-05〜2026-07-03、7203/6758/9984/TOPIX_SYNTH)内に収まるよう
選定した(Train 2026-01-05〜03-04、Validation 03-05〜05-01、
Locked Test 05-05〜07-03)。この一連の実験は明示的に**Smoke Run
(Pipeline配線・Infrastructure Validation)であり投資判断のEvidenceでは
ない**(Preregistration/DatasetContract双方に明記)。実データでの
Locked Test実行はユーザーが自身のPCで別途実行する(Local Validation
Guideを別途用意、D0063以降で言及予定)。

**D. Pre-run Reviewの結果と修正**:

1. **[BLOCKER→修正済み] Split境界を越えたPrice参照**: pit-auditorが
   検出。`scripts/phase5_v1_short_term_reversal.py`の
   `_load_fixture_price_data`が常にTrain〜Locked Test全期間の
   データを取得していたため、`TradingCalendar.range_end`がsplit
   自身のend_sessionより先まで伸び、`BacktestEngine`のRight
   Censoring(D0037)がend_session側で機能せず、Train/ValidationのTrade
   がSplit境界を越えた後続期間(最悪Locked Test期間)のPriceで決済
   されうる状態だった。実際に無効化前のTRAIN実行
   (`BT_PHASE5_V1_H0001_SMOKE_TRAIN`、Registryに保持したまま無効化)は
   `censored_count=0`だったが、修正後の再実行
   (`BT_PHASE5_V1_H0001_SMOKE_V2_TRAIN`)では`censored_count=4`と
   なり、正しくRight Censoringが機能することを確認した。
   修正は2段階: (a)`_load_fixture_price_data`をsplit自身の
   end_sessionまでのみデータ取得するよう修正、(b)`lib/research/
   runner.py`の`run_split()`に`SplitBoundaryLeakageError`による
   構造的Gateを追加(trading_calendar.range_end/benchmark_barsが
   end_sessionを越えていれば即座に失敗、将来の呼び出し側の同種Bugを
   恒久的に検知)。修正確認のため再度pit-auditorを実行し、CLEAN
   (残存Riskはprice_historyの独立range検証が無い点のみだが、
   BacktestEngineのExit解決順序[Calendar先→Price後]に構造的に
   依存する形で間接的にカバーされていることをコード追跡で確認、
   MEDIUM未満のObservationとしてrunner.pyのコメントへ明記)。
   回帰Test`VAL-027`を追加(`13_tests/test_research_validation_
   pipeline.py`)。
2. **[MEDIUM→修正済み] lookback_daysの構造的強制が無かった**:
   skeptic-reviewerが検出。`run_split`は`holding_period_days`のみ
   Preregistrationとの一致を検証しており、`lookback_days`は
   `lib.strategies.short_term_reversal.DEFAULT_CONFIG`という
   Module定数を呼び出し側が直接使うだけで、Preregistrationとの
   一致がCode上保証されていなかった(Module定数が静かに書き換わっても
   検知できない)。`config_from_preregistration_parameters()`
   (`lib/strategies/short_term_reversal.py`)を新設し、実行時の
   Strategy Configを必ずPreregistration.parametersから導出する
   よう`scripts/phase5_v1_short_term_reversal.py`を修正。
   単体Test追加(`13_tests/test_short_term_reversal_strategy.py`)。
3. **[LOW→Backlog、このRoundでは変更しない] Alternative
   Explanationsがやや一般的**: skeptic-reviewerが、5営業日
   Lookback/10営業日Holdという具体的なSignal形状に対して最も
   直接的な代替説明である「Bid-Ask Bounce/Microstructure Noise」
   が、既存の2つの代替説明(取引コスト以下のノイズ/対象期間・銘柄
   依存)の中で明示的に区別されていない、と指摘。この指摘は妥当だが、
   Preregistrationの`alternative_explanations`は既に`.preregister()`
   で固定済みのCore Fieldであり、`allowed_adjustments`は
   Transaction Cost前提の変更のみを許可している(Signal・
   Alternative Explanations等の変更は不許可、Phase5 v1要件§51)。
   Preregistration自身が課すこの制約を尊重し、このRoundでは
   `revise()`による新Preregistration発行は行わず、H0002以降の
   Preregistration Templateへの反映事項としてBacklogに記録する。
4. **[LOW→Backlog] Threshold選定(5日/10日)の理由づけが薄い**:
   「燃え尽きた期間の戦略との対称性・単純性」以外の定量的根拠が
   無い、との指摘。妥当な指摘だが、Preregistrationが既に固定済み
   であるため#3と同じ理由でこのRoundでは変更しない。
5. **[LOW→既知の限界として記録] SmokeデータのUniverse Coverageが
   弱い**: Fixtureの7203が単調増加系列のため、5営業日Trailing
   Returnが負になることが無く、Train/Validation双方で実質的に
   9984銘柄のみがSignalを生成していた(`stock_by_stock_
   distribution`で確認)。Pipeline配線確認としては機能するが、
   複数銘柄でのSignal発火を確認する検証としては弱い。実データでの
   Local Validation実行時にはこの制約は無い(合成データ固有の限界)。

**E. Regression**: `ruff check`/`ruff format --check`/`mypy`
(`core app.py scripts Japanese_Equity_Lab/lib`)いずれもclean、
`pytest`(Lab+Screening Tool)974件全てpass。
`git diff --stat -- core/ app.py tests/`で変更が無いことを確認
(Screening Tool不変)。

## D0063 — Phase5 v1: Locked Test実行・Final Review・Closure

D0062の続き。Locked Test split(`PREREG0001`の`locked_test_period`
2026-05-05〜07-03)を`LockedTestGate`経由で一度だけUnlockし
(`06_backtests/locked_test_audit.jsonl`、reason/actor記録)、一度だけ
実行した(`BT_PHASE5_V1_H0001_SMOKE_V2_TEST`)。

**Final pit-audit(post-Locked-Test)**: CLEAN。Unlock機構の正当性
(単一Unlock Record・Gate Enforcement)、Split境界の正しさ(D0062で
修正済みのBugが再発していないこと、`censored_count`の妥当性)、
Feature/Target計算のPIT安全性(Locked Test開始前のPrice HistoryはLookback
Warmupとして正当、Signal自体はLocked Test期間内のDecision Dateのみで
生成)、Forbidden Data Capability不使用、Reproducibility Fingerprintの
整合性(strategy_hashが全split共通=パラメータ不変の直接証拠)を確認した。

**Final skeptic-review(post-Locked-Test)**: PASS_WITH_CONCERNS。
MEDIUM(3 splitとも実質的に単一銘柄[9984]のみでのBacktestであることを
Conclusionへ明記すべき)→`12_reports/experiment/BT_PHASE5_V1_H0001_
SMOKE_V2_2026-08-19_report.md`と`H0001_...md`双方へ明記して対応。
LOW(H0001.md自体に「投資判断のEvidenceではない」旨が無い)→H0001.mdへ
追記して対応。Cherry-pick・Data Snooping・Benchmark誤認については
Findingなし(3 splitとも一貫して`excess_return`が負・`win_rate=0.0`
であり選択的な強調の余地が無いこと、Preregistrationが1版のみで
`revise()`が無いこと、`allowed_adjustments`が一度も適用されていない
ことを確認済み)。

**Conclusion**: `INSUFFICIENT_EVIDENCE`(SUPPORTED/PARTIALLY_
SUPPORTED/INCONCLUSIVE/CONTRADICTEDのいずれでもない)。Locked Test
の`excess_return`はPreregistrationのFalsification Condition
(`<=0`)を機械的に満たしたが、合成Fixtureデータかつ実質的に単一銘柄・
3トレードのみという極小サンプルであるため、Short-term Reversal仮説
そのものへのEvidenceとしては不十分、という誠実な結論とした
(理由の詳細は上記Reportを参照)。実データでのLocked Test実行手順は
`PHASE5_V1_LOCAL_VALIDATION_GUIDE.md`として別途用意した。

**Closure**: `PHASE5_VALIDATION_ARCHITECTURE.md`(`lib/research/`の
設計判断まとめ)を新規作成。Regression(`ruff`/`mypy`/`pytest`)は
Completion Report側で最終確認する。Phase5 v1のScopeはこれで完了とし、
Phase5 v2・Fundamentals/Positioning接続・News/Macro/Consensus使用・
D0057解決・Portfolio/Decision Engine・自動売買のいずれもこのRoundでは
着手しない(Phase5 v1 kickoff要件§73)。

## D0064 — Phase5 v1.1: Real-Data Validation Experiment(Code Complete、実行はローカル待ち)

D0062/D0063(Phase5 v1、合成FixtureによるSmoke Run)を受け、H0001を
**実際のJ-Quants Price + PIT Universeデータ**で検証するRound。目的は
「儲かる戦略を発見すること」ではなく「Phase5 v1 Pipelineが実データ上でも
End-to-Endで正しく・再現可能に動作するか」(Primary Question)と、
副次的に「H0001に実データ上でさらなる調査に値するEvidenceがあるか」
(Secondary Question)を構造的に分離して確認すること。

**A. Repository Reality Check**: このセッションのEgressは
`api.jquants.com:443`/`jpx.gitbook.io:443`いずれもProxy Status Endpoint
(`/__agentproxy/status`)の`recentRelayFailures`で`connect_rejected`
(403、Policy Denial)と確認。`.env`/`JQUANTS_API_KEY`もこのセッションには
存在しない。したがって**実データでのRun自体はこのセッションでは実行
できない**(Phase5 v1.1要件§37に従い、Fake/Mockで代替して「実行した」と
主張しない)。

**B. 実装(`scripts/phase5_v1_1_h0001_real_data.py`、新規)**: 新しい
Backtest Engineは作らず、Phase5 v1で確立済みの`lib.research.*`
(`Preregistration`/`DatasetContract`/`run_split`/`FileBackedLockedTest
Gate`/`PreregistrationRegistry`)をそのまま再利用する薄いDriver。

1. **Preregistration Lineage**: `PREREG0001`(Phase5 v1のSmoke Run)を
   `Preregistration.revise()`し、`preregistration_id=PREREG0001_R1`・
   `parent_preregistration_id=PREREG0001`として新規発行。
   `dataset_contract_id`/`universe_definition`/Train・Validation・
   Locked Test 3期間/`benchmark`のみ上書きし、`primary_metric`/
   `parameters`(`lookback_days=5`/`holding_period_days=10`)/
   `falsification_condition`/`forbidden_capabilities`/
   `alternative_explanations`/`secondary_metrics`/`allowed_adjustments`
   は全て親からそのまま継承(Hypothesis Drift禁止、Phase5 v1.1要件
   §6/§22)。合成H0001のExperiment/Preregistrationは一切上書き・削除
   しない(§5/§36)。`experiment_id=BT_PHASE5_V1_1_H0001_R1`
   (`_TRAIN`/`_VALIDATION`/`_TEST`Suffix)は合成Smoke Runの
   `BT_PHASE5_V1_H0001_SMOKE_V2_*`と明確に別ID。
2. **Dataset Contract**(`DC0002_JQUANTS_REAL_V1`): `/v2/equities/
   bars/daily`・`/v2/markets/calendar`・`/v2/indices/bars/daily/
   topix`・`/v2/equities/master`の実データを宣言。
3. **Real Data Coverage Check**(`--step coverage-check`): Strategy
   Return/Signal件数を一切計算せず、行数・日付Coverage・欠損Bar・
   Corporate Action件数・TOPIX Coverage・PIT Universe該当銘柄数のみを
   表示する(§8/§11、`test_realval003_*`で構造的に保証)。
4. **Real Benchmark**: 実TOPIX(`/v2/indices/bars/daily/topix`)を使用。
   公式公表済みの過去Index値は当時の実際の構成銘柄を反映済みであり、
   「現在の構成銘柄を過去へ遡及適用する」形のLook-aheadを構造的に含まない
   ため、新規Benchmark Engineを作らずにPIT安全性を満たす(§17/§18)。
5. **Universe**: `lib.universe.ListingBasedUniverseProvider`
   (実`/v2/equities/master`由来)を`run_split()`へ渡し、Current
   Universeは使用しない(§12)。
6. **Missing Bars / Split境界**: Phase5 v1で確立済みの`BacktestEngine`
   Missing Bar処理(欠損はUNEXECUTABLE等で明示、0埋め・Flat Price埋め
   なし)と`SplitBoundaryLeakageError`(D0062)をそのまま継承・再利用
   (§14/§46、新規変更なし)。

**C. Pre-run Review**:

1. **pit-auditor MEDIUM(修正済み)**: `lib.universe.UniverseSnapshot.
   resolution`/`survivorship_bias_unresolved`は`BacktestEngine.run()`
   内部でdecision_dateごとに解決されるが、`BacktestMetrics`に該当Field
   が無いため`Experiment`Recordへ伝播しない。`lib/backtest/engine.py`/
   `BacktestMetrics`(複数の既監査済みPipelineが共有)を変更するのは
   このRoundの「最小限のReal-data統合Gapのみ」というScope(§46)を
   超えるため、より小さい修正を選択: `_run_and_record()`が各Split境界
   (開始・終了)で`universe_provider.as_of()`を独自に呼び、
   `resolution`(+`survivorship_bias_unresolved`)のSummaryを
   `Experiment.notes`の`universe_resolution=[...]`として記録する。
   回帰Test(`test_pit_audit_medium_fix_run_and_record_persists_
   universe_resolution_into_notes`、Fake Adapter + tmp-path Registryで
   End-to-Endに`Experiment.notes`の内容を検証)を追加。
2. **pit-auditor LOW(修正済み)**: `DatasetContract.delisting_
   handling`が「PIT UniverseによりSurvivorship Bias防止」を無条件の
   既成事実として記述していたが、実際の`/v2/equities/master`の
   Delisting Field網羅性は未検証であるため、設計意図であり保証では
   ない旨へ文言を修正。
3. **pit-auditor LOW(修正済み、文書化のみ)**: `/v2/equities/master`
   をTrain/Validation/Locked Testの各Split実行ごとに独立して
   (`as_of`Pin留めなしで)取得しているため、実Master Dataが取得
   タイミング間で変化した場合、3 splitが厳密に同一のUniverse基盤を
   共有する保証はない。ただし各Splitの`SnapshotManifest`/
   `dataset_hash_from_snapshots`により個別のRaw Snapshotとして記録
   されるため、サイレントな不整合ではない(再現性検証時にSnapshot
   Hashを比較すれば検出可能)。`DatasetContract.notes`へ明記。
4. **skeptic-reviewer LOW × 3(修正済み)**: (a)モジュールDocstring
   「Result Inspection Cannot Precede Preregistration」の保証根拠が
   誤って「Import欠如」(構造的)と書かれていたが、実際は`lib.
   strategies`/`lib.backtest.engine`をModule Top-levelでImportして
   いる(他Stepで使用するため)。実際の保証は「`step_coverage_check()`
   の関数本体がこれらを呼ばない」という振る舞い的なものであり、
   Docstringを訂正。(b) Primary Question(Pipeline検証)とSecondary
   Question(Hypothesis検証)の区別をDocstringへ明記(§7)。
   (c)既定`--codes`(7203/6758/8056/3626)がRESEARCH_RULES.mdの
   「燃え尽きた期間」記録と同じ銘柄集合であり、独立したUniverse選定
   根拠が無いことをDocstringへ明記。
5. **副次的に発見・修正した実装Gap(Reviewer指摘ではなく自己発見)**:
   `main()`が`load_dotenv()`を呼んでいなかった(既存の`jquants_lab_
   pipeline.py`/`fetch_jquants_local_snapshot.py`は両方とも呼んでいる
   のに、このScriptだけ欠落していた)。`.env`にAPIキーを設定しても
   環境変数へ別途Exportしない限りローカル実行時に「JQUANTS_API_KEY が
   設定されていません」で失敗する状態だった。`main()`冒頭へ
   `load_dotenv()`を追加し、構造Testで回帰防止。

**D. Test**: `Japanese_Equity_Lab/13_tests/test_phase5_v1_1_real_data_
script.py`(新規、11Test、REALVAL-002/003/006/007/009/010相当+
pit-auditor MEDIUM修正の回帰Test+`load_dotenv()`回帰Test)。
REALVAL-004/005/008相当は既存`VAL-027`/`lib.backtest.engine`Test/
`VAL-016`が既にCoverするため重複させない(Module Docstringに明記)。
実ネットワーク通信は一切行わず、`JQuantsAdapter`のDependency
Injection Point(既存`test_data_sources.py`と同じPattern)を使用。

**E. 実行状態**: **`CODE_COMPLETE_AWAITING_LOCAL_REAL_DATA_RUN`**。
実データでのTrain/Validation/Locked Test実行は、このセッションの
Egress制約によりこのRoundでは行っていない(§37/§49に従い、実行した・
COMPLETEだと主張しない)。ユーザー自身のローカル環境での実行手順は
`PHASE5_V1_LOCAL_VALIDATION_GUIDE.md`(新Scriptの実際のCLIを使う形へ
全面更新)を参照。`06_backtests/preregistrations.jsonl`/
`experiment_registry.jsonl`に`PREREG0001_R1`/`BT_PHASE5_V1_1_H0001_R1_*`
は**まだ記録されていない**(このセッションでは`step_preregister`/
`_run_and_record`を実Registryに対して一度も実行していないことを
`grep`で確認済み)。

**F. Regression**: `ruff check`/`ruff format --check`/`mypy`
(`core app.py scripts Japanese_Equity_Lab/lib`)いずれもclean、
`pytest`(Lab+Screening Tool)985件全てpass。
`git diff --stat -- core/ app.py tests/`で変更が無いことを確認
(Screening Tool不変)。Phase5 v1.1のScopeはこれで完了とし、H0002・
Fundamentals/Positioning接続・Phase5 v2・D0057解決・Portfolio/
Decision Engine・自動売買のいずれもこのRoundでは着手しない
(Phase5 v1.1 kickoff要件§51)。

## D0065 — Phase5 v1.1: Real-Data Availability Constraint Resolution(PREREG0001_R1放棄、PREREG0001_R2再設計)

D0064後、ユーザーがローカル環境で`scripts/phase5_v1_1_h0001_real_
data.py --step coverage-check`を実際に実行した。この結果、当初の
`PREREG0001_R1`期間設計(Train 2015-2019/Validation 2020-2021/Locked
Test 2025)は現在の契約プラン下で取得不能と判明した。このRoundは
その事実をResearch Historyへ誠実に記録し、Resultを一切見ないまま
新しい期間設計(`PREREG0001_R2`)へ再設計することが目的である。
**新しいStrategy・パラメータ探索は行っていない。**

**A. Observed API Behavior(このRepositoryが直接確認した事実)**:

| Request範囲 | 結果 |
|---|---|
| 2022-01-04 〜 2022-12-30 | 取得成功 |
| 2025-01-06 〜 2025-12-30 | 取得成功 |
| 2021-01-04 〜 2021-12-30 | HTTP 400 |
| 2020-01-06 〜 2021-12-30 | HTTP 400 |
| 2015-01-05 〜 2025-12-30 | HTTP 400 |

7203/TOPIX/Trading Calendar/PIT Universeの基本経路自体は2022年・
2025年の両方で正常動作しており、`step_coverage_check()`のPipeline
配線自体に問題は無い。Strategy Return/Signal件数は一切確認していない
(Coverage Checkのみ)。

**B. User-reported Plan Constraint(このRepositoryが未検証、区別して
記録)**: ユーザーの認識では現在の契約プラン(Light、D0031で既出)は
過去約5年分のみ履歴取得可能。このセッションはJ-Quants公式ドキュメント
(`jpx.gitbook.io`)へ引き続き接続できない(EGRESS_BLOCKED)ため、
この「約5年」という具体的な数字を公式仕様として確認したものではない。
**Aの表(Observed API Behavior)とBのUser-reported Plan Constraintは
明確に別カテゴリとして記録する**(Observed Factを未検証の推測で
上書きしない、CLAUDE.md「未確認のSource仕様を推測で埋めない」原則)。
2021年と2022年の間に境界があるというObserved Factは、Bの「約5年」
という認識と整合的ではあるが、Aの表それ自体から導かれる結論は
「2022-01-04以降・2025-12-30以前の範囲では少なくとも単年Requestは
成功する」ことのみである。

**C. `PREREG0001_R1`の状態**: **`DESIGN_ABANDONED_PRE_RUN`**
(Formal Run前にData Availability制約により実行不能と判明したため
放棄)。重要な点として、`PREREG0001_R1`は`Preregistration.
preregister()`によってRegistry(`06_backtests/preregistrations.
jsonl`)へ一度も記録されていない(D0064時点でもこのRoundの時点でも
`grep`で0件を確認済み)。したがって**Immutability違反やSilent
Overwriteは発生していない** — `PREREG0001_R1`は単にコード上の定数・
`PHASE5_V1_LOCAL_VALIDATION_GUIDE.md`上の期間案として存在した
「実行前に破棄された計画」であり、Research Registry上のRecordを
書き換えたわけではない。この区別(Registry上のRecordの改ざん
禁止 vs 未実行の計画の変更)は重要であり、後者は当然自由に変更できる。
この経緯自体は消さず、この節として記録する(RESEARCH_RULES.md
「失敗した実験を削除しない」の精神を、実行前の計画放棄にも適用)。

**D. `PREREG0001_R2`の設計(新しいLineage、Resultは一切見ずに決定)**:
`scripts/phase5_v1_1_h0001_real_data.py`の`PREREGISTRATION_ID`/
`EXPERIMENT_ID`定数を`PREREG0001_R2`/`BT_PHASE5_V1_1_H0001_R2`へ
変更した(`PARENT_PREREGISTRATION_ID=PREREG0001`は不変、Lineageは
兄弟関係— `R1`を`revise()`したのではなく、未実行の`R1`計画を
破棄して`PREREG0001`から新規に`R2`を`revise()`する)。変更した
Core Fieldsは実データ固有のもの(`dataset_contract_id`/`universe_
definition`/3期間/`benchmark`)のみで、`primary_metric`/
`parameters`(`lookback_days=5`/`holding_period_days=10`)/
`falsification_condition`/`forbidden_capabilities`/`alternative_
explanations`/`secondary_metrics`/`allowed_adjustments`は一切
変更しない(既存Test`test_realval010_build_real_preregistration_
uses_revise_lineage`が構造的に保証)。

提案期間(Aで確認済みの2022-2025の範囲内、Chronological・非重複):

- Train: 2022-01-04 〜 2023-12-29(約2年)
- Validation: 2024-01-04 〜 2024-12-30(約1年)
- Locked Test: 2025-01-06 〜 2025-12-30(約1年、単独Requestとして
  既に取得成功を確認済み)

**Train/Validation比率(2年/1年)の根拠**(skeptic-reviewer LOW
Finding対応): Locked Test=2025年は独立に取得成功を確認済みの範囲と
一致させることを優先して固定した。残る2022-2024の2年をTrain/
Validationへどう配分するかは、機械学習における一般的な「学習データを
検証データより多く確保する」慣行(Trainを厚めに)以上の、Result依存の
根拠は無い。境界(2023-12-29/2024-01-04)をこれ以外の日付にする
具体的な理由も無い。この点はskeptic-reviewerに指摘されるまで明示
していなかったため、ここに明記する — Strategy Resultを見て選んだ
比率ではないが、「2年/1年」以外の配分(例: 1年/2年)を排除する
積極的な理由も無いことを正直に記録する。

**重要な未確認事項**: `_load_real_price_data()`は`train_period_start`
から各Splitのend_sessionまでを1Requestで要求する設計のため、Locked
Test実行時には2022-01-04〜2025-12-30という約4年分が単一Requestに
なる。Aで確認済みなのは単年Requestの成功と、2015年を含む11年
Requestの失敗のみであり、**2022年以降だけに限定した複数年単一
Requestが成功するかどうかは未確認**。したがって`PREREG0001_R2`は
**このRoundでは`preregister()`によってRegistryへ`freeze`していない**
(このセッション自身がEGRESS_BLOCKEDのため、この確認ができない)。
ユーザーが`PHASE5_V1_LOCAL_VALIDATION_GUIDE.md` C節の追加Coverage
Check(`--start 2022-01-04 --end 2025-12-30`)を実行して成功を確認した
後、同Guide E節の`--step preregister`コマンドで初めてFreezeする
(この段取り自体もResult非依存、純粋なAPI到達可否確認)。

**E. Universe再検討**: 7203/6758/8056/3626をそのまま使用する(変更
しない)。より広いPIT Universe(`lib.universe`)から機械的・
事前定義可能な方法(例: `/v2/equities/master`のPrime Market
共通株式をCode昇順で先頭K件選ぶ等、Strategy Resultに依存しない
選定Rule)で選ぶ代替案を検討したが、このRoundでは実施しない。
理由: (1)現行`step_coverage_check()`は`--codes`で指定された銘柄の
Universe該当性のみを報告する設計であり、全Universe列挙には新しい
出力機能の追加が必要(Phase5 v1.1要件§46「最小限のReal-data統合Gap
のみ」のScopeを超える)、(2)このRoundの目的はStrategyやUniverseの
改善ではなくData Availability制約への対応であり、Universe変更を
同時に行うと変更の原因が混在する。4銘柄に独立した選定根拠が無い
という限界(D0064で既出)は解消されないままBacklogとして残す。
Universe変更を将来行う場合は、既存の`revise()` Lineage機構により
`PREREG0001`(または`R2`)の子として新しいIDを発行し、既存の
Preregistration/Experiment RecordをSilent Overwriteしない
(D0064で確立済みの原則をそのまま適用)。

**F. Confirmation-Bias / Research-Integrity Review**: このRoundの
再設計案が以下のBiasを含まないか、独立したskeptic-reviewer(read-only、
コードは変更しない)に確認させた。

- **Period Cherry-picking**: 提案期間(2022-2025)はAで確認した
  「取得可能」範囲の外側を一切含まない機械的な選択であり、複数の
  候補期間からStrategy Resultを見て選んだものではない(そもそも
  Strategyは一度も実行していない)。
- **Post-hoc Redesign**: このRound自体がPost-hoc Redesignだが、
  その理由は純粋なAPI到達可否(HTTP 400)であり、Strategy Resultの
  観測を理由とした変更ではない。Falsification ConditionもPrimary
  Metricも不変。skeptic-reviewerが確認した追加の間接経路として、
  D0037の合成Fixture以前のE2E疎通確認(20営業日Momentum・燃え尽きた
  期間)で「Censoring[`OUTSIDE_DATA_RANGE`]が期間末尾に集中する」
  という定性的観察が過去に得られていたが、これはExecution/Censoring
  Timing一般の事実であり、H0001(5営業日Reversal)のReturn自体には
  接続しない。実データのReturn数値自体はRepository内のどこにも
  永続化されていない(Registry・Report・Archiveいずれも確認済み)。
- **Insufficient History**: Train+Validation+Locked Testの合計が
  約4年(約1000営業日 × 4銘柄)しかない。5営業日Reversal・10営業日
  保有という短期Strategyであるため、営業日単位のSample数自体は
  Phase5 v1のSmoke Runより大幅に増える見込みだが、複数の市場Regime
  (景気循環・金利環境の変化等)を跨いだ検証は構造的に不可能。
  **`LIMITED_REAL_DATA_WINDOW`として明示的に記録する**(既存の
  `INSUFFICIENT_EVIDENCE` Conclusion Categoryとは別軸の、データ
  提供期間そのものの限界を指すLabelとして、Backlogおよび将来の
  Conclusion Recordで使用する)。skeptic-reviewerのMEDIUM Finding:
  RESEARCH_RULES.md「Sample Metricsの用語とholding期間の重複」節
  (`unique_entry_dates`が`trade_count`より著しく少ない場合は
  「多数の独立した検証」ではなく「少数の市場局面への賭け」である
  ことを明記せよ、という既存Rule)が、4銘柄・10営業日保有という
  このRoundの設計にまさに該当する状況にもかかわらず、当初のGuide
  Falsifiable Checklistに含まれていなかった。`PHASE5_V1_LOCAL_
  VALIDATION_GUIDE.md` H節へ`unique_entry_dates`/`trade_count`の
  比較を明示的な確認項目として追加した(この節末尾に反映)。
- **Universe Cherry-picking / Burned-period Contamination(結合評価)**:
  最も重要な指摘。当初この2つを別々のBullet(4銘柄は変更していない
  こと、期間重複)として個別に評価していたが、skeptic-reviewerの
  MEDIUM Findingにより、**両者を独立に評価するのは不十分**と判断を
  改めた。提案したTrain+Validation期間(2022-01-04〜2024-12-30)は、
  RESEARCH_RULES.mdの「燃え尽きた期間」記録(2022-01-04〜
  2024-12-30・同じ4銘柄[7203/6758/8056/3626]・20営業日Momentum→
  60営業日保有)と**日付範囲・銘柄の両方が完全に一致**する。「燃え尽きた」
  の定義は期間・銘柄・Strategyパラメータの組み合わせ全体であり、
  H0001のMechanism(5営業日Reversal・10営業日保有、燃え尽きた組み合わせ
  の20/60営業日Momentumとは符号・長さとも異なる)は技術的には異なる
  組み合わせのため、Rule上は違反ではない。しかし、**日付軸・銘柄軸の
  いずれか一方でも独立していれば残る「未見性」の余地が、両軸とも
  一致することで完全に失われている**(skeptic-reviewerの表現:
  「技術的な組み合わせの違いはBlindnessを完全には回復しない」)。
  これはAvailability制約から機械的に強制されたものであり
  Confirmation Biasの意図は無い(Strategy Resultを見て期間を選んだ
  のではなく、逆にResultを見る前に制約から導出された)が、この
  重複の「技術的にはRule違反ではない」という結論と「Evidence
  としての解釈上は真のOut-of-Sample Testより弱く扱うべき」という
  結論は両立する、とskeptic-reviewerと合意した。

  **構造的なCommitment(narrativeだけで終わらせない)**: 当初はこの
  懸念をDECISIONS.mdの記述だけに留めていたが、skeptic-reviewerの
  指摘(「三か月後に忘れられても何も失敗しない」)を受け、
  `PHASE5_V1_LOCAL_VALIDATION_GUIDE.md` H節(Falsifiable Checklist)
  へ以下を明示的な必須確認項目として追加した(このRoundの一部として
  既に反映済み): 将来のConclusion Recordは、(1)ticker重複と
  period重複を結合した一文で明示すること(片方だけの言及では不可)、
  (2)この重複のためEvidence Strengthを真のOut-of-Sample Testより
  弱く扱うことを明記すること。これによりQ節(Trade/Ticker
  Concentration)・R節(Synthetic vs Real Comparison)への反映が
  「書き忘れられる」リスクを、Checklist上の必須項目として構造化した
  (完全な強制[Testによる自動検証]ではなく、人間が従うChecklistでの
  強制である点は限界として残る — 将来Round候補としてBacklogに記録)。

**G. PIT Review**: このRoundはコード変更が定数名(`PREREG0001_R1`
→`_R2`、`EXPERIMENT_ID`同様)とDocstring/Guide文面のみであり、
`lib.research.*`/`lib.backtest.engine`本体には一切触れていない。
D0064で確認済みのPIT機構(Split境界Gate・PIT Universe・Missing Bar
処理・Real Benchmark)はそのまま維持される。新しい期間案
(Train 2022-01-04〜2023-12-29/Validation 2024-01-04〜2024-12-30/
Locked Test 2025-01-06〜2025-12-30)はChronological・非重複であり、
`Preregistration.__post_init__`が構造的に強制する制約を満たす。

**H. Files Changed**: `scripts/phase5_v1_1_h0001_real_data.py`
(定数`PREREGISTRATION_ID`/`EXPERIMENT_ID`を`_R1`→`_R2`、
Docstringを新期間・R1放棄の経緯・燃え尽きた期間との重複説明へ
更新)、`Japanese_Equity_Lab/13_tests/test_phase5_v1_1_real_data_
script.py`(ハードコードされた`"PREREG0001_R1"`Literal 2箇所を
`"PREREG0001_R2"`へ更新)、`PHASE5_V1_LOCAL_VALIDATION_GUIDE.md`
(全面更新、Observed API Behavior表・追加Coverage Check手順・
新期間案・燃え尽きた期間との重複の明示を追加)。

**I. 実行状態**: 引き続き**`CODE_COMPLETE_AWAITING_LOCAL_REAL_
DATA_RUN`**。`PREREG0001_R2`はこのRoundでも`preregister()`により
Registryへ記録していない(C節の未確認Multi-year Request確認を
ユーザーがローカルで実施した後にFreezeする設計、D節参照)。
Train/Validation/Locked Testはこのラウンドでも実行していない。

**J. Regression**: `ruff check`/`ruff format --check`/`mypy`
(`core app.py scripts Japanese_Equity_Lab/lib`)いずれもclean、
`pytest`(Lab+Screening Tool)985件全てpass(定数変更に伴う
Test文字列更新2箇所を含む)。`git diff --stat -- core/ app.py
tests/`で変更が無いことを確認(Screening Tool不変)。H0002・
Parameter Search・Fundamentals/Positioning接続・Phase5 v2・
D0057解決・Portfolio/Decision Engineのいずれもこのラウンドでは
着手しない。

## D0066 — Phase5 v1.1: Accidental Preregistration Reconciliation(PREREG0001_R1採用、R2発行取消)

D0065の再設計(`PREREG0001_R2`として発行予定だった2022-2025期間案)を
実行に移す過程で、ユーザーのローカルPC上でID/Process上の事故が発生した。
このRoundはResearch Historyを一切削除・改竄せず、既存Architectureに
沿って最小限の修復で整合させることのみを目的とする。**新しいHypothesis
・Strategy・Universe・Periodの探索は一切行っていない。**

**A. 実際に何が起きたか(ユーザー報告、このセッションはUncommitted
Local Fileを直接検証できないため、報告内容として記録する)**:
ユーザーが最新版を`git pull`する前の旧Version Script(`PREREGISTRATION_
ID`定数がまだ`"PREREG0001_R1"`のまま、かつCLI引数は2022-2025設計の
日付を渡した状態)で`--step preregister`を実行した。その結果、
`06_backtests/preregistrations.jsonl`(Uncommitted、`git status`で
`M`)へ、**中身はD0065で設計した2022-2025のReal-data案そのものだが
IDが`PREREG0001_R1`**というRecordが`PREREGISTERED`状態で追記された。
その後`git pull`し、現在のScriptは(前Roundの結果)`PREREGISTRATION_
ID = "PREREG0001_R2"`を指すようになっていたため、IDが食い違った。

**B. 不整合の原因**: 単純なID/Timing事故であり、Result依存の
Redesignではない。旧Scriptが偶然`PREREG0001_R1`という定数を保持して
いた時点(このセッションが後のRoundで`R2`へRenameする前)で、
ユーザーが既にD0065時点で決定済みだった2022-2025の期間・Universe・
Dataset Contract・Benchmark・ParameterをCLI引数として渡して実行した
ため、「新しい設計が旧IDでFreezeされた」という結果になった。

**C. Research Integrity Impact(実装されたImmutability/Lineage
Semanticsと照合した判定)**:

- **Preregistration Integrity**: **損なわれていない**。
  `lib/research/preregistration.py`の`Preregistration.preregister()`
  は一度呼ばれた後は`PreregistrationImmutabilityError`なしに変更
  できず、`revise()`のみが新IDでの派生を許す。今回の事故はこの
  機構を一切迂回・破壊していない — 単に「どのIDでFreezeされたか」
  という表面的なLabelの食い違いであり、Freezeされた中身(Core
  Fields)自体は一度もRewriteされていない。
- **Confirmatory Status**: **損なわれていない**。`PreregistrationRegistry.
  record()`は重複ID拒否のみを行い、Freeze後にStrategy Return/Signal
  Performanceを見る経路をそもそも持たない。ユーザーは今回の事故の
  前にも後にもTrain/Validation/Locked Testのいずれも実行しておらず
  (§5、ユーザー報告)、Coverage Check(Row数・Missing Bar・PIT
  Universe該当数のみ)以外の観測は一切行われていない。したがって
  「Resultを見てからDesignを決めた」という懐疑対象になる経路が
  存在しない。
- **Locked Test Integrity**: **損なわれていない**。`06_backtests/
  locked_test_audit_real.jsonl`はまだ作成されていない(Unlock未実施)。
  `FileBackedLockedTestGate`のUnlock記録が無いため、Locked Test
  Access自体が構造的に不可能な状態のまま。

**D. 検討した選択肢**:

- **A. R1をAccidentalとして履歴に残し、予定通りR2を正式発行する**:
  却下。R1の中身がR2として発行する予定だった内容と一致するため、
  実質的に同一Experimentの重複Preregistrationを2つ作ることになる
  (Decision Principle #4「Unnecessary experiment proliferationを
  避ける」に反する)。
- **B. R1のCore DesignがR2と同一であることを確認した上でR1を正式な
  Real-data Preregistrationとして採用し、Script/D0065側をR1へ整合
  させる**: **採用**。理由はEを参照。
- **C. 既存Architecture上の正式なabandon/supersede/invalidate
  mechanismを使う**: 該当する専用Mechanismは存在しない
  (`PreregistrationRegistry`はrecord/all/getのみを提供し、削除・
  状態変更APIを持たない、既存の`PreregistrationStatus`もDRAFT/
  PREREGISTEREDのみで「Abandoned」等の中間状態を持たない)。新設する
  ことも検討したが、これは「単なるID事故」のためだけに恒久的な
  新Registry機構を追加することになり、Decision Principle #6
  「今回だけのための複雑なRegistry機構を作らない」に反するため
  見送った。既存の`revise()` Lineage機構(親Recordを変更せず新ID
  で派生する)は、あくまで「Result後に設計を変える」ケース向けの
  Mechanismであり、今回のような「Result前のID Label訂正」には
  そのまま適合しない — これもBの選択(Registry Dataそのものには
  一切触れず、Repository側[Script定数・Doc]をRegistryの実データへ
  合わせる)を後押しする理由になった。

**E. 採用した整合方法(Option B)**: `PREREG0001_R1`(ユーザーの
Registry上に既に`PREREGISTERED`状態で存在するRecord)を正式な
Phase5 v1.1 Real-data Preregistrationとして採用する。`PREREG0001_R2`
は発行しない(取消)。**`preregistrations.jsonl`のRecord自体は一切
変更しない**(手作業削除・書き換え・`git restore`によるRevert、
いずれも行わない — このセッションはそもそもUncommittedな
ローカルFileへ直接アクセスできないため、変更しようにも変更できない、
という制約もこの判断を後押しする)。修復は完全に「Repository側
(Script定数・Docstring・Guide・DECISIONS.md)がRegistry上の実データ
に合わせて自分自身を訂正する」形で行った。これはPrinciple順位1-3
(History不変・Result未閲覧の維持・Immutability非侵害)を自動的に
満たしつつ、Principle 4-6(不要な複製回避・既存Architecture優先・
新規機構不要)も満たす、最小の修復である。

**F. Registry / Preregistration State After Reconciliation**:
`06_backtests/preregistrations.jsonl`はこのセッションからは変更
していない(ユーザーのローカルEnvironmentにある`PREREG0001`+
`PREREG0001_R1`の2Record構成を、そのまま正式な状態として扱う)。
`06_backtests/experiment_registry.jsonl`/`locked_test_audit_real.
jsonl`への新規Recordはこのラウンドでも一切追加していない(Train/
Validation/Locked Testを実行しないため)。

**G. Code Changes**: `scripts/phase5_v1_1_h0001_real_data.py`の
`PREREGISTRATION_ID`/`EXPERIMENT_ID`定数を`_R2`→`_R1`へ戻し、
`Experiment.notes`/`DatasetContract.notes`内の`H0001-R2`Literalも
`H0001-R1`へ戻した。Docstringの「Preregistration Lineage」節・
「対象銘柄の既定値について」節・末尾の使い方例を、今回の2段階の
経緯(放棄された最初のR1計画→R2として計画→事故でR1として実際に
Freeze→R1をそのまま採用)が正確に伝わるよう書き直した。
`PHASE5_V1_LOCAL_VALIDATION_GUIDE.md`はC節(Multi-year Coverage
Checkが既に成功済みであることを反映、978 sessions/4銘柄・
missing_open=0・missing_close=0・TOPIX 978 bars・6758 Corporate
Action 1件・4銘柄PIT Universe eligible)・D/E/F/G節(ID表記を
`_R1`へ統一、E節は「既にFreeze済み、再実行不要」という案内へ
書き換え)を更新した。`Japanese_Equity_Lab/13_tests/test_phase5_
v1_1_real_data_script.py`のHardcoded Literal 2箇所(`"PREREG0001_
R2"`→`"PREREG0001_R1"`)・Module Docstring Title・前Roundで追加した
回帰Testの名前(`_r2_`→`_real_data_`、中身のDate Assertionは変更
なし)を更新した。`lib/research/*`・`lib/backtest/engine.py`等の
Core Library・`Preregistration`/`PreregistrationRegistry`の実装は
一切変更していない(既存Architectureをそのまま使う、新規Mechanism
は追加しない)。

**H. Tests / Regression**: Code Behaviorの変更は無い(定数値と
Docstring/Testのラベル文字列のみ)ため、新規Targeted Testは追加して
いない。既存の回帰Test(前Roundで追加した`test_d0065_r2_period_
design_satisfies_chronological_non_overlap`、Nameのみ`test_d0065_
real_data_period_design_satisfies_chronological_non_overlap`へ
Rename)は`PREREG0001_R1`という新しいID文字列の下でも、D0065の
実際の6期間日付が`Preregistration.__post_init__`のChronological
Checkを通過することを引き続き検証する。`ruff check`/`ruff format
--check`/`mypy`(`core app.py scripts Japanese_Equity_Lab/lib`)
いずれもclean、`pytest`(Lab+Screening Tool)986件全てpass。
`git diff --stat -- core/ app.py tests/`で変更が無いことを確認
(Screening Tool不変)。

**I. 実行状態**: 引き続き**`CODE_COMPLETE_AWAITING_LOCAL_REAL_
DATA_RUN`**。Train/Validation/Locked Testはこのラウンドでも実行
していない。Locked Testはunlockしていない。Strategy Parameter・
Universe・Periodのいずれも変更していない。次にユーザーがローカルで
打つべきコマンドは`PHASE5_V1_LOCAL_VALIDATION_GUIDE.md` F節
(`--step train`)から(E節のPreregisterは既に完了済み、再実行不要)。
H0002・Parameter Search・Fundamentals/Positioning接続・Phase5 v2・
D0057解決・Portfolio/Decision Engineのいずれもこのラウンドでは
着手しない。

## D0067 — Phase5 v1.1: Real-Data Final Audit & Phase Close(PARTIALLY_SUPPORTED、COMPLETE)

ユーザーがローカルPCでTrain/Validation/Locked Test(`PREREG0001_R1`)を
実行し、Registry(`preregistrations.jsonl`/`experiment_registry.jsonl`/
`provenance.jsonl`/`locked_test_audit_real.jsonl`)をCommit `d0da7c3`
としてPushした。このRoundはその実際のArtifactをGitHub上の実体
(Promptの数値ではなく)から再確認し、Final PIT Audit・Final Skeptic
Reviewを実施した上でPhase5 v1.1のClose判定を行う。**新しいExperiment・
Strategyは作らず、Locked Testも再実行しない。**

**A. Repository Reality Check**: `git pull`により4File(`preregistrations.
jsonl`/`experiment_registry.jsonl`/`provenance.jsonl`/`locked_test_
audit_real.jsonl`)への追記のみを確認(Commit差分は+8行、Code変更
ゼロ)。`preregistrations.jsonl`の`PREREG0001_R1`はD0065/D0066の設計
(Train 2022-01-04〜2023-12-29/Validation 2024-01-04〜2024-12-30/
Locked Test 2025-01-06〜2025-12-30/Universe 7203,6758,8056,3626/
`DC0002_JQUANTS_REAL_V1`/実TOPIX/`lookback_days=5`・`holding_period_
days=10`/`parent_preregistration_id=PREREG0001`)と完全一致する
ことを直接確認した。Secret Scan(`api[_-]?key|bearer|authorization`
等)は4Fileいずれもゼロ件。

**B. Actual Run(Promptの数値と独立に再取得)**:

| Split | trade_count | signal_count | excess_return | benchmark_return |
|---|---|---|---|---|
| TRAIN | 139 | 951 | 0.0001435822588633272 | 0.0058431085163198814 |
| VALIDATION | 68 | 443 | 0.0021762375148616083 | 0.006866127907086497 |
| LOCKED TEST | 70 | 445 | 0.004588670657621604 | 0.010445853377711749 |

いずれもPrompt記載値とByte-for-byte一致(独立再確認、Promptを
Source of Truthとして扱っていない)。

**C. Locked Test Integrity**: `locked_test_audit_real.jsonl`は1行のみ
(`unlocked_at=2026-08-19T13:26:58Z`、Validation`created_at=13:26:09`
より後・Locked Test`created_at=13:27:47`より前、正しい順序)。
`experiment_registry.jsonl`の`BT_PHASE5_V1_1_H0001_R1_TEST`は1件のみ。
`FileBackedLockedTestGate`/`LockedTestGate.unlock()`・`ExperimentRegistry.
record()`はいずれも重複を構造的に拒否する実装であることをコード
(`lib/research/locked_test.py`/`lib/registry/experiment_registry.py`)
から確認済み — Unlock回数=1・Run回数=1は「たまたま1回だった」ではなく
「2回目は構造的に拒否される」ことの直接証拠。Unlock Reasonは
「Train and Validation completed with no parameter, universe,
benchmark, or metric changes」であり、Post-lock Retuningは無い。

**D. Final PIT Audit**: pit-auditorを実データPathへ実行、**CLEAN**。
NEXT_SESSION_OPEN執行・`AsOfAdjustedPriceHistory`/`assert_no_
lookahead`・Split境界Gate(`SplitBoundaryLeakageError`)・6758の
Corporate Action(Case B、`announced_at=None`、`build_provider_
derived_adjusted_bars`によるEx-date前のみ調整)・`survivorship_bias_
unresolved`の解釈(7203/6758/8056/3626全て`delisting_date=None`の
ため`_auto_detect_survivorship_bias()`が保守的にPARTIALを返す設計
通りの挙動、この4銘柄自体は期間中未上場廃止のためTrade自体への
実害は低いという評価付き)、いずれも実装と再取得したArtifactの両方
から確認。唯一のLimitationは、Raw J-Quants Payload(`01_data/raw/
jquants/`、Git管理外)がこのセッションから閲覧不能なため、個別
`AdjFactor`値そのものは検証できず、Code Pathの構造的正しさの確認に
留まる、という点(NO_OBSERVED_CASEとして記録)。

**E. Final Skeptic Review**: **PASS_WITH_CONCERNS**。Main Claudeが
実Artifactと照合し確認した主要Finding:

1. **[HIGH、確認済み]** `excess_return = average_return -
   benchmark_return`(`lib/backtest/engine.py`)であり、
   `transaction_cost_adjusted_return`を経由しない。Primary Metricは
   構造的にTransaction Cost非依存。
2. **[MEDIUM、確認済み]** 3 splitとも`transaction_cost_adjusted_
   return`が`average_return`とByte-for-byte一致(Cost前提0bpsのまま、
   Allowed Adjustmentを行使していない)。
3. **[MEDIUM、確認済み]** `sector_benchmark_return`/`sector_excess_
   return`は3 splitとも`null`。RESEARCH_RULES.mdのSector Benchmark
   要件は今回のExperimentでは満たされていない。
4. **[MEDIUM、確認済み]** `stock_by_stock_distribution`は銘柄別平均
   Returnのみを保持し、銘柄別Trade件数・集中度・PnL寄与度は現行
   Schemaで再現不能(構造的Persistence Gap)。
5. **[MEDIUM、確認済み]** `04_hypotheses/H0001_...md`がSynthetic
   Smoke Runの記述のみで、実データExperimentの完了を反映していな
   かった → このRoundで更新(下記H節)。
6. **[HIGH、要再確認としてFlag]** 燃え尽きた期間との二重重複
   (D0065/D0066)について、実際のConclusion Recordが「結合した1文
   で明示・Evidence Strength明示的Downgrade」というGuide §Hの要求
   通りの文言になっているかは、skeptic-reviewer自身は本文を見ていない
   ため確認できないとの指摘 → 本D0067・Conclusion Record(`12_reports/
   experiment/BT_PHASE5_V1_1_H0001_R1_2026-08-19_report.md`)で直接
   確認・反映済み(Negative Evidence節・Conclusion節参照)。
7. **[LOW]** Multiple Testing分母の明記が無かった → Conclusion Record
   へ追加(`ExperimentRegistry.summary()`実測値)。

いずれもFabrication・PIT違反・Locked Test Access迂回は検出されず、
全てDocumentation/Disclosure上のGapであり、Main Claudeが独立に
Repo Evidenceで再確認した上でConclusion Record・H0001.mdへ反映した
(コード変更は無し、Strategy改善目的の変更は一切行っていない)。

**F. Falsification Evaluation**: Locked Test `excess_return =
0.004589 > 0`。Falsification Condition(`<= 0`)は成立しない
→ **仮説はこのExperimentでは棄却されない**。ただし`not falsified`
は`proven`ではない(kickoff要件、Conclusion節で明示)。

**G. Final Conclusion**: **`PARTIALLY_SUPPORTED`**(SUPPORTED /
INCONCLUSIVE / CONTRADICTED / INSUFFICIENT_EVIDENCEのいずれでもない)。
3 split全てPositiveという事実を機械的にSUPPORTEDへ変換せず、
統計的有意性の欠如・Transaction Cost非考慮・燃え尽きた期間との
二重重複・Sector Benchmark未実施・Trade集中度不明・Universe
Resolution PARTIALという複数のNegative Evidenceを踏まえて判断した。
Pipeline Validation(Primary Question、実データ上でPreregistration
固定・Split分離・Locked Test隔離・PIT安全性を保ったままEnd-to-Endで
正常動作)はSUPPORTEDと明示的に分離して記録する。詳細は
`12_reports/experiment/BT_PHASE5_V1_1_H0001_R1_2026-08-19_report.md`
参照。BUY/SELL判断ではない。

**H. Documentation**: `04_hypotheses/H0001_2026-08-19_short_term_
reversal.md`の実行結果節を、Synthetic Smoke RunとReal-Data
Experimentを明示的に分離した形へ更新(実データ実行が完了済みである
ことを反映)。`12_reports/experiment/BT_PHASE5_V1_1_H0001_R1_2026-08
-19_report.md`を新規作成(Facts/Unknowns/Result/Negative Evidence/
Locked Test Integrity/Reviewer Findings/Conclusion/Synthetic vs
Real Comparison/Reproducibility)。

**I. Research Registry / History**: Synthetic H0001(`PREREG0001`)・
D0064の`PREREG0001_R1`放棄計画・D0065の再設計・D0066の事故経緯、
いずれも削除・改変していない(D0064〜D0066は本Roundで一切書き換え
ていない)。実Experiment(`PREREG0001_R1`・`BT_PHASE5_V1_1_H0001_R1_*`)
はRegistryへ追記済み。Registry上書きは発生していない
(`AppendOnlyViolationError`が構造的に保証)。

**J. Code Changes**: このRoundはコード変更なし(`lib/`・`scripts/`
とも無変更)。Strategy Performance改善目的の変更は行っていない。
CURRENT_DEFECTと呼べるPIT/Locked Test Integrity上の問題は発見され
なかった(Final pit-audit CLEAN)。

**K. Tests / Regression**: Code変更が無いためTargeted Testも追加して
いない。`ruff check`/`ruff format --check`/`mypy`(`core app.py
scripts Japanese_Equity_Lab/lib`)いずれもclean、`pytest`(Lab+
Screening Tool)986件全てpass。`git diff --stat -- core/ app.py
tests/`で変更が無いことを確認(Screening Tool不変)。

**L. Completion Gate判定**: 以下17項目全てをActual Repo Evidenceで
確認し、全て満たすことを確認した: (1)実J-Quants Run実行済み、
(2)PIT Universe使用、(3)実TOPIX Benchmark使用、(4)Preregistration
Integrity維持(D0066のID事故もImmutability非侵害、C節・D0066参照)、
(5)Train完了、(6)Validation完了、(7)Locked Test Unlock1回、
(8)Locked Test Run1回、(9)Post-lock Retuning無し、(10)PIT Audit
Pass(CLEAN)、(11)Skeptic Review完了(PASS_WITH_CONCERNS、Finding
全て文書化対応済み)、(12)Negative Evidence保持、(13)Final
Conclusion記録済み(PARTIALLY_SUPPORTED)、(14)Reproducibility
Metadata十分(`strategy_hash`/`dataset_contract_hash`/`code_commit`
記録済み、Raw Snapshot自体はGit管理外という既知の制約付き)、
(15)Secret不在、(16)Forbidden Capability不在(既存REALVAL-007構造
Testで保証継続)、(17)Regression Clean。

**Phase5 v1.1のPhase Statusを`COMPLETE`へ昇格する。** ただしこれは
「Pipelineが実データ上で正しく動作することが実証された」ことを
指し、「H0001が有効な投資戦略である」ことを意味しない
(`PARTIALLY_SUPPORTED`、G節参照)。H0002・Parameter Exploration・
Phase5 v2・Fundamentals/Positioning接続・D0057解決・Portfolio/
Decision Engineのいずれもこのラウンドでは着手しない。

## D0068 — Post-Phase5: Codex Audit Adoption & Safe Cleanup(SessionSchedule削除)

外部のCodexによるIndependent Engineering Audit(Main Repositoryを
Read-onlyで走査、`git archive HEAD`の隔離コピー上でCall Graph調査・
削除実験・Test実行まで実施済み)をEvidence Inputとして受け取った。
このRoundの方針: Codexの報告は鵜呑みにしないが、Repository全体を
ゼロから再調査もしない — 提示されたExact Path/Symbol/Caller Search
/Import Search/Test結果をSpot-checkし、矛盾が無ければそのまま採用
判断へ進む(Heavy Investigation=Codex、Spot Verification+Architecture
Judgment=Main Claude、という役割分担)。

**採用した変更**: `lib/market_calendar.py`の`SessionSchedule`
(dataclass)・`session_schedule()`(factory関数)を削除した。

Spot-check(Codexの主張を独立に再確認、範囲を広げずに実施):
Repository全体をExact Match検索した結果、両Symbolの出現は定義箇所
(`market_calendar.py`)とDECISIONS.md本文中の1箇所(過去の設計経緯の
説明文、コードではない)のみで、他の19ファイル(`lib.market_calendar`
をImportする全ファイル、`test_market_calendar.py`含む)のいずれも
この2 Symbolを一切参照していないことを確認した。動的Dispatch
(`getattr`/`importlib`/`globals()[...]`等によるMarket Calendar経由の
参照)・`__all__`によるRe-export・Star Importのいずれも無い。
実際に使われているのは同モジュール内の独立した`session_open_at()`/
`session_close_at()`(Phase5 v1.1 Real-Data Scriptが直接Import)で
あり、これらは削除対象に含まれず無変更。Codexの「Isolated Copyで
削除後もBaselineと同じPass数・Failure数」という主張は、このSession
自身でも削除後に`13_tests/test_market_calendar.py`(10件)・Phase5
関連Test(68件)・全Regression(986件、Claude標準環境)を実行し直接
再確認した(986/986 pass、新規Failure無し)。

**採用しなかった/据え置いたFinding**:

- `core/cache.py`の`Cache.get_forecast`/`Cache.set_forecast`:
  CodexはHigh ConfidenceでDELETE_CANDIDATEとしたが、`core/`/`app.py`/
  root `tests/`はScreening Tool Protected Pathsであり、Complexity
  Cleanupを理由にPolicyを解除しない。削除しない。Backlogへ
  「Externally Unused Candidate(Codex確認済み、Protected Path
  のため未着手)」として記録するに留める。
- Catalog Invariant Testsのparameterization・Fixture Helperの統合:
  CodexはSAFE_NOWとしたが、Test Case Identity/Failure Mode/Semantic
  Coverageの完全維持をこのRound内で確認する時間的余裕が無く、少しでも
  疑義があれば見送るという方針(§5)に従いこのRoundでは着手しない。
  将来の専用Roundの候補として残す。
- Phase5 Two-CLI Orchestration統合・`AppendOnlyJsonlStore`共通化・
  Generic As-of Resolver・`BacktestEngine.run`/`compute_metrics`/
  `jquants_lab_pipeline.run_pipeline`のRefactor・Evidence Path
  統合・D0057解決・Phase4 Capability削除・Root Screening App
  再構成: CodexもREFACTOR_AFTER_MORE_VALIDATIONまたはFuture
  Capability扱いであり、このRoundでは一切着手しない(Large Refactor
  禁止)。

**Research-Safety Impact**: `PointInTimeRecord`/PIT Universe
Semantics/`AsOfAdjustedPriceHistory`/Corporate Action PIT Semantics/
Preregistration Immutability/Locked Test隔離/Experiment・Research
Registry Semantics/Provenance/Reproducibility Hash/Append-only
History/Negative Evidence/UNKNOWN・Fail-closed/Principle・Semantic・
Adversarial Testsのいずれも変更していない(削除した2 Symbolは
これらのいずれからも参照されていなかったことをSpot-checkで確認済み)。

**Regression**: `ruff check`/`ruff format --check`/`mypy`
(`core app.py scripts Japanese_Equity_Lab/lib`)いずれもclean、
`pytest`(Lab+Screening Tool)986件全てpass(Claude標準環境、
Codexの報告したWindows Baseline[978 pass/8 environment-caused
failure]とは異なるが、新規Failureが無いことのみを確認基準とした
— Codex Windows Baselineをこの環境のTruthとして採用し直すことは
しない、§9)。`git diff --stat -- core/ app.py tests/`で変更が
無いことを確認(Screening Tool不変)。

Phase5 v2・H0002・Large Refactor・D0057解決・Phase4 Capability削除・
Portfolio/Decision Engineのいずれもこのラウンドでは着手しない。

## D0069 — Post-Phase5 Hardening A: Experiment Observability & Reproducibility

Phase5 v1.1 COMPLETE後、D0067(Final Audit)のskeptic-reviewerが実際に
指摘した2件のInfrastructure Gap(新規仮説の探索ではない)のみを対象に、
最小限のHardeningを行った。H0001 Locked Testの再実行・再Unlock・
Parameter/Universe/Benchmark/Metricの変更は一切行っていない
(このRoundはCode変更のみで、Registryへの新規Experiment記録は無い)。

**Gap 1 — Ticker-level Observability**: `BacktestMetrics`
(`lib/backtest/engine.py`)は銘柄別平均リターン(`stock_by_stock_
distribution`)のみを保持し、銘柄別trade数・trade数シェアを事後検証
できなかった(D0067「Trade/Ticker集中度は不可逆的に未回収」指摘に
対応)。`compute_metrics()`が既に内部で構築している`stock_perf: dict[str,
list[float]]`(銘柄別リターンのlist)から、`len(rs)`(trade数)と
`len(rs)/executed_count`(全trade数に占める比率)を追加集計するだけで
実装できたため、新しいデータ収集経路は不要だった。追加した2 Field
(`stock_by_stock_trade_count: dict[str, int]` / `stock_by_stock_trade_
share: dict[str, float]`)はいずれも既存の3 Field(`year_by_year_
performance`等)と同じ`field(default_factory=dict)`パターンを踏襲し、
`BacktestMetrics(**d)`(`lib/registry/experiment_registry.py`の
`_metrics_from_dict`)がキー欠如時に既定値`{}`へ自動fallbackするため、
過去のExperiment RecordのMigrationは不要(後方互換、追記専用Registry
は無変更)。過去のH0001-R1記録(既に固定済み)はこのRoundで一切
書き換えていない。

**Gap 2 — Reproducibility**: 既存の`ReproducibilityFingerprint`
(`lib/schemas/experiment.py`)は`code_commit`+`git_dirty`のみを持ち、
`git_dirty=True`の場合に実際どこがcommit内容と異なるのかを再現できな
かった(H0001-R1の実記録で`code_commit=8011cb6...`・`git_dirty=true`
だったことがD0067で確認済み)。ユーザーからの明示的な制約により、
「`git_dirty==true`なら実行禁止」という設計にはしていない —
Experiment Registry・Reportの生成自体がこのRun自身のworking treeを
変化させるため(`06_backtests/*.jsonl`・`12_reports/`等への書き込み)、
Run開始前にcleanでもRun終了時には必然的にdirtyになりうる。この
汚染を避けるため、gitのcommit/diff状態を一切見ず、呼び出し側が
明示的に指定したSourceパス(`lib/`ディレクトリと実行中のScript自身)
配下の`*.py`ファイル内容だけをhash化する`source_code_state_hash()`
(`lib/reproducibility.py`)を新設した。対象パスに生成物ディレクトリ
(`06_backtests/`・`12_reports/`等)や`.env`を含めない限り、これらは
構造的にhash入力へ混入しない(`*.py`拡張子のみを対象にする点も
Secrets誤混入への追加防御)。gitに一切依存しないため、git repository
外や過去のcommitに関わらず動作する。`ReproducibilityFingerprint`へ
`source_code_state_hash: str | None = None`を追加Field(既定None)で
追加し、`scripts/phase5_v1_1_h0001_real_data.py`・`scripts/phase5_v1_
short_term_reversal.py`・`scripts/jquants_lab_pipeline.py`の3 Script
(全てのReproducibilityFingerprint構築箇所)へ配線した。H0001-R1の
Train/Validation/Locked Testは既にRegistry上に確定記録済みで
`ExperimentRegistry.record()`はexperiment_id重複をAppendOnlyViolation
Errorにするため、`phase5_v1_1_h0001_real_data.py`のこの変更が過去の
H0001-R1記録を書き換えることは構造的に不可能であり、また再実行も
していない。

**後方互換**: 追加した3 Field(`stock_by_stock_trade_count`/
`stock_by_stock_trade_share`/`source_code_state_hash`)はいずれも
Optional/既定値付きで、既存のJSON Lines Registry(追記専用)は無変更。
過去のRecordのMigrationは行っていない。`13_tests/test_experiment_
registry.py`に、新Fieldのキー自体が無い旧形式Recordが引き続き
読み込めることを直接確認する回帰Testを追加した(`price_adjustment`の
既存後方互換Testと同じパターン)。

**Research-Safety Impact**: PIT Semantics/`PointInTimeRecord`/PIT
Universe/Corporate Action Timing/Preregistration Semantics/Locked
Test Semantics/H0001のParameter・Conclusion/既存の実データ結果値の
いずれも変更していない。H0001 Locked Testは再実行していない(この
Roundで実行したのは新規追加した回帰Test[Synthetic/Fixture入力の
みを使用]のみ)。

**Tests**: `13_tests/test_backtest_engine.py`(Gap1の3 Test:
Trade数/Shareの直接確認・trade0件時のZeroDivision非発生・単一銘柄
集中Caseの直接確認)、`13_tests/test_reproducibility.py`(Gap2の
6 Test: 決定性・内容変化での差分・非.pyファイル除外・出力Directory
非混入・空Source時のNone・単一ファイルSource対応)、
`13_tests/test_experiment_registry.py`(新Field往復保持2件+旧形式
Record後方互換2件)を追加。

**Regression**: `ruff check`/`ruff format --check`/`mypy`
(`core app.py scripts Japanese_Equity_Lab/lib`)いずれもclean、
`pytest`(Lab+Screening Tool)997件全てpass(既存986件+新規11件、
新規Failure無し)。`git diff --stat -- core/ app.py tests/`で
変更が無いことを確認(Screening Tool Protected Paths不変)。

H0002・Strategy最適化・Parameter探索・Phase5 v2・Transaction Cost
較正・PIT Universe再設計・D0057解決・Portfolio/Decision Engine・
Complexity Refactorのいずれもこのラウンドでは着手しない。

## D0070 — Post-Phase5 Hardening B: Codex Transaction Cost Audit Finding Resolution

Codexによる独立Transaction Cost Audit(判定PASS_WITH_CONCERNS)のFindingのうち、
ChatGPT reviewでACCEPT済みの4件(Gross/Net Semantic・excess_return母集団
mismatch・Effective Cost Provenance・Non-finite Cost)のみを最小修正した。
「compute_metrics()を外部callerが誤用してnet値を渡す可能性」はActual
Production Callerで再現しないためNOT CURRENT DEFECTとしてOut of Scopeとし、
新しいTransaction Cost Frameworkは作らない(ユーザー指示)。

**Audited HEADについての実測結果(§9 Output A、重要な食い違い)**: ユーザーから
提示されたAudited HEAD(`e8eb683791482d12000e712e915fd9613c2903be`)は、
`git log --all`(fetch後)でこのRepository(ローカル・origin両方)のどのBranch
にも存在しないことを確認した。またFinding2が「既に存在する」と述べた
`gross_excess_return`/`net_excess_return`のPairwise実装、Finding3が述べた
`SplitRunResult.effective_config_hash`、Finding3が述べた`ExecutionAssumptions`
は、実際のRepository全文検索(grep)でいずれも0件で、着手前の時点では
存在しなかった。これはCodexが監査した対象がこのSession手元のRepository
State(直前のRound、D0069時点のHEAD `84e4fd6`)と完全には一致していない
可能性を示す(ローカル/Remote差異は本Session過去のD0066でも実例あり)。
ユーザーからの「鵜呑みにせず、しかしゼロから全部を再調査もしない」という
指示に従い、Finding自体が指す**問題(Defect)の実在**は独立に`lib/backtest/
engine.py`/`lib/research/runner.py`の実コードを読んで直接確認した上で
(全4件とも実際に確認できた、下記参照)、「解決策が既に存在する」という
Findingの前提部分だけを外し、Main Claude自身がFinding記載の設計原則に
沿って新規実装した。

**Finding1確認(Gross/Net Semantic Clarity)**: `lib/backtest/engine.py`の
`BacktestEngine.run()`は`gross_return = exit_bar.open / entry_bar.open - 1`
を計算し、そのまま`TradeResult(..., net_pretax_return=gross_return)`へ
代入していた(取引コスト控除前の値がnet-suffixedなFieldに入っていた)。
`TradeResult`クラスDocstring自体は元から正しく「取引コスト控除前・税引前の
gross return」と説明していたため、意味論自体に矛盾は無かったが、Field名
そのものは誤解を招く。Field名は互換のため変更せず、`gross_pretax_return`
という読み取り専用Property Aliasを追加した。

**Finding2確認・修正(excess_return Population Mismatch)**: `BacktestEngine.
run()`は、各tradeについてBenchmarkのEntry/Exit両方のBarが揃っている場合の
みそのtradeのBenchmark Returnを`matched_benchmark_returns`へ追加していた
一方、`average_return`(→`excess_return`の一方の項)は全executed trade
(Benchmark欠損の有無を問わない)から計算していた。すなわち`excess_return
= average_return(全trade) - benchmark_return(matched部分集合のみ)`という
異なる母集団同士の差分になっていた(Benchmark Barが1件でも欠損すれば
発生する実際のDefect)。修正: `compute_metrics()`に新しいOptional引数
`benchmark_returns_by_trade`(tradesと同じ長さ・同じ順序、対応が取れない
tradeは`None`)を追加し、`BacktestEngine.run()`はtrade単位で位置揃えした
Benchmark Returnの列を渡すよう変更した。渡された場合、`gross_excess_return`
/`net_excess_return`/`excess_return`(`excess_return`は`gross_excess_return`
と同値、Option A)はいずれも「両方観測できたtradeのみ」の同一母集団で
計算する。対応が取れるtradeが1件も無い場合はNone(異なる母集団のまま
残さない)。`benchmark_returns_by_trade`を渡さない直接呼び出し(Event
Study等の既存呼び出し元)は、trade単位の対応情報が無いため従来通りscalar
同士の単純差分にfallbackする(既存呼び出し元・既存Testとの後方互換を
保つため)。`BacktestMetrics`へ`gross_excess_return`/`net_excess_return`
(いずれも`float | None = None`)を追加。過去に記録済みのH0001-R1 Experiment
Recordは追記専用Registryのため一切書き換えていない(この修正は将来の
Experiment記録にのみ影響する)。

**Finding3確認・修正(Effective Cost Provenance)**: `scripts/phase5_v1_1_
h0001_real_data.py`・`scripts/phase5_v1_short_term_reversal.py`はいずれも
`run_split()`へ`transaction_cost`引数を渡していなかった(既定の`Transaction
CostConfig()`=0bpsがそのまま実行された)。両Scriptとも独自に`config_hash =
hash_json_safe({"split": ..., "preregistration_id": ...})`を組み立てて
おり、実際に有効だったTransaction Cost設定を全く反映しないHashだった。
`SplitRunResult`(`lib/research/runner.py`)へ`effective_config_hash`
(`run_split()`が実際に`BacktestEngine.run()`へ渡した`BacktestRunConfig`
全体、Transaction Cost含む、から`hash_json_safe(asdict(config))`で計算)と
`effective_transaction_cost_bps`(同Configの`round_trip_bps()`)を追加し、
Single Source of Truthとした。両Scriptの`config_hash`計算をこの
`result.effective_config_hash`の再利用へ置き換え(重複Hashロジックを
作らない)、`effective_transaction_cost_bps`は既存の`notes`文字列パターン
(D0067 Pre-run PIT Audit対応で確立済みのUniverse Resolution記録と同じ
慣習)へ追記して人間可読な形でも残るようにした。`ExecutionAssumptions`と
いう専用型は新設していない(Frameworkを作らないというユーザー指示)。
H0001-R1は既にRegistryへ確定記録済み(Append-only、experiment_id重複は
`AppendOnlyViolationError`)のため、この変更が過去記録を書き換えることは
構造的に不可能であり、また再実行もしていない。

**Finding4確認・修正(Non-finite Cost)**: `TransactionCostConfig.
__post_init__`は`commission_bps < 0 or slippage_bps < 0`のみを検査して
おり、`NaN < 0`がPythonでは`False`になるためNaNを素通りさせていた
(`+inf`/`-inf`は`< 0`判定自体は正しく動くが、Cost計算を無意味な値に
する点で同様に問題)。`math.isfinite()`によるNaN/±inf拒否を`>=0`
チェックの前に追加した。

**後方互換**: `BacktestMetrics.gross_excess_return`/`net_excess_return`は
`float | None = None`のOptional追加Fieldで、旧Experiment Recordはこの
キーを持たなくても`BacktestMetrics(**d)`のデフォルト適用で読み込める。
`ReproducibilityFingerprint`自体は変更していない(`config_hash`という
既存Fieldの計算式のみが将来のRunから変わる)。`SplitRunResult`は
Experiment Registryへ直接Serializeされない中間結果のため、後方互換
Migrationの対象外(唯一の構築箇所である`run_split()`のみを更新)。

**Research-Safety Impact**: PIT Semantics/`PointInTimeRecord`/PIT Universe/
Corporate Action Timing/Preregistration Semantics/Locked Test Semantics/
H0001のParameter・Conclusion/既存の実データ結果値のいずれも変更していない。
H0001 Locked Testは再実行していない(Synthetic/Fixture入力のみを使う
既存Test Harness `test_phase5_v1_1_real_data_script.py`の`_FakeAdapter`
経由でのみ`_run_and_record()`を呼び出した)。

**Tests**: `13_tests/test_backtest_engine.py`にFinding1(2件)・Finding2
(4件)・Finding4(4件)、`13_tests/test_phase5_v1_1_real_data_script.py`に
Finding3(既存の`_FakeAdapter`End-to-End Harnessを再利用した1件、
config_hashがlegacy式と一致しないこと・`effective_transaction_cost_bps`
がnotesに残ることを確認)を追加。

**Regression**: `ruff check`/`ruff format --check`/`mypy`(`core app.py
scripts Japanese_Equity_Lab/lib`)いずれもclean、`pytest`(Lab+Screening
Tool)1009件全てpass(既存997件+新規12件、新規Failure無し)。
`git diff --stat -- core/ app.py tests/`で変更が無いことを確認
(Screening Tool Protected Paths不変)。

H0002・Strategy最適化・Parameter探索・Phase5 v2・実Broker Cost較正・
Liquidity/Market Impact・PIT Universe再設計・D0057解決・Research/
Discovery/Decision/Portfolio Engine・Complexity Refactorのいずれも
このラウンドでは着手しない。

## D0071 — Japanese Equity Lab: Token-Efficient AI Development Policy

Production機能追加ではなく、AI開発Process(Claude Code / Codex /
Sub-agentのToken消費)に関する運用Policy Decisionである。**Quality /
Research Safety > Token Saving**を最上位原則とし、「AIに読む量を
我慢させる」のではなく「不要なContextを読ませない」ことをToken削減の
目的とする(More Context/Agent/Token = Better Quality/Researchでは
ないことも明記)。

**Repo Reality First(実施済み)**: `git rev-parse HEAD`
(`27db177...`)・`git status --short`(clean)・`git branch --show-current`
(`claude/investment-strategy-pipeline-jyfby5`)を確認した上で、関係する
既存文書のみを選択的に読んだ(`CLAUDE.md`両階層・`CLAUDE_CODE_RESEARCH_
WORKFLOW.md`・`AUDIT_MANIFEST.md`該当Section・DECISIONS.md該当Section
[4A.5.1系・D0052]、全文探索はしていない)。

**既存Policyとの重複回避(§1要件通り)**: 調査の結果、以下が既に存在する
ことを確認したため、新規文書は作らず既存文書へ統合した:
- Context層分類(`ALWAYS`/`ON_DEMAND`/`TASK_ONLY`/`EVIDENCE_ONLY`、
  `CLAUDE_CODE_RESEARCH_WORKFLOW.md`「Context Architecture」、4A.5.1-3)
- Reviewer/Author分離・3 Subagentの役割(同File冒頭)
- Codex Task粒度・Safety-Critical Boundary・Repo Access Gateの前提
  (`AUDIT_MANIFEST.md` §E/G/H、Post-Phase5 Complexity Auditで既に導入
  済み)
- Research Safety原則本体(`Japanese_Equity_Lab/CLAUDE.md`「安全原則・
  禁止事項」「Claude Code Guardrails」・`RESEARCH_RULES.md`)

これらは重複記載せず、`CLAUDE_CODE_RESEARCH_WORKFLOW.md`の新設Section
(「Token-Efficient AI Development Policy」)から相互参照するのみとした。
新規に明文化した内容(既存慣行の追認であり新規Toolingではない):

1. Task Prompt Policy(Thin Task Router、巨大Master Promptの複製禁止)
2. Primary Scope Policy(PRIMARY_SCOPE明示、拡大時は理由記録、Safety
   目的のScope拡大は常に許可)
3. **Codex Report ≠ Source of Truth**(D0068・D0070で実際に運用した
   Spot-check慣行の明文化。特にD0070ではAudited HEADがこのRepositoryの
   どのBranchにも存在せず、Finding本文の「既に実装済み」という前提の
   一部が誤りだった実例を明記し、この原則の根拠として引用した)
4. 1 Codex Task = 1つの明確な調査質問、Codex Evidence Rule(HEAD/Path/
   Symbol/Caller/Test/Search Evidence要求、無条件に真実扱いしない)
5. Agent Policy(Task Independence > Agent数、既定0 Agent、出力budget
   [STATUS/CONFIRMED FINDINGS/EXACT PATHS・SYMBOLS/RISKS/
   RECOMMENDATION]、既存3 Subagentの運用方針自体は変更なし)
6. Task Complexity分類(SMALL/MEDIUM/LARGE/SAFETY_CRITICAL)とVerification
   厚みの対応表、Investigation Stop Rule
7. File Re-read Policy・Verification Staging(targeted→relevant→full
   regression)・Diff/Log段階読み(`git diff --stat`→変更File→Hunk)・
   Stage Handoff Summary(ただしEvidenceの代替にはしない)
8. Documentation Policy(このSection自体を実践例として明記)
9. 「Token節約が上書きしないもの」— PIT/availability/provenance/
   falsification/contradictory evidence/UNKNOWN/Locked Test/
   preregistration整合性/append-only/backward compatibility/final
   regressionのいずれもToken理由で省略しないことを明記
10. Desired Operating Flow(既存2Workflow図を置き換えない追加の俯瞰図)

**変更していないもの**: `Japanese_Equity_Lab/CLAUDE.md`(ALWAYS層は
増やさないという既存原則4A.5.1-3 §3を維持)・`AUDIT_MANIFEST.md`
(Scope変更なしのため無編集)・`.claude/skills/`・`.claude/agents/`・
コード・Test・Registry・Preregistrationのいずれも無変更。Regression
実行は本Round不要と判断した(Doc-only変更、`.py`Fileを1つも変更して
いないため`post_edit_quality_gate.sh`のruff/mypy/pytestは実質的に
no-opで完走することのみ確認、`git diff --stat -- core/ app.py tests/`
も空を確認)。

Production機能追加・H0002・Phase5 v2・新Tooling/Hook/Agent種別の追加
にはこのRoundでは着手しない。

## D0072 — Stage 3 v1: Research Artifact(1企業 + as_of、PIT-safe Evidence合成)

Research Engineの最小Vertical Sliceを実装した。**Research != Decision**
(BUY/SELL/target price/position sizingに相当するFieldは`ResearchArtifact`
のどこにも存在しない、構造的禁止、Phase5 VAL-026と同じPattern)。

**新規Module**: `lib/evidence/research_artifact.py`(`ResearchArtifact`/
`NarrativeCase`/`DataGap`/`ConfidenceLevel`/`DataGapStatus`/
`ResearchConclusion`/`build_research_artifact()`/`price_derived_record_
to_evidence()`)、`lib/registry/research_artifact_registry.py`
(`ResearchArtifactRegistry`、既存`ExperimentRegistry`と同じAppend-only
JSON Linesパターン)。新しいEvidence Frameworkは作らず、既存の
`EvidenceRecord`/`EvidencePacket`/`build_evidence_packet()`/
`ResearchQuestion`/`filter_usable_at()`/`RecordMeta`/Append-only Registry
慣行をそのまま再利用した。

**要件v1充足**: versioned Artifact(`artifact_version`/
`supersedes_artifact_id`、`Hypothesis.revise()`と同じLineage)・Evidence
ID lineage(`included_evidence_ids`)・Bull/Base/Bear(Evidence参照無しの
主張を`__post_init__`で拒否、捏造防止)・SUPPORTS/CONTRADICTS/
ALTERNATIVE_EXPLANATION/NEUTRAL/UNKNOWN(`build_evidence_packet()`を
再利用)・Data/Evidence/Research Confidence 3軸分離・MISSING/UNAVAILABLE/
UNVERIFIED/UNKNOWN(`DataGap`、Bear Caseとは別Field、missing source !=
negative evidence)・Research Conclusion・INSUFFICIENT_EVIDENCE
Abstention(Evidence 0件時に他Conclusionを構造的に禁止)・Append-only
永続化。

**D0057との関係(場当たり的に回避しない)**: このModuleはEvidence Pathの
実際の最初のConsumerである。D0057(ARCHITECTURE_GAP)が確認した
「Positioning Evidence Path(`positioning_record_to_evidence()`、
`retrieved_at`基準)がas_of Path(`resolve_available_at()`、Session
Close基準)より早く「利用可能」と誤判定しうる」問題に対し、
`lib/positioning/evidence.py`/`lib/positioning/derived/price_derived.py`
のいずれも変更せず(D0057自体の解決はこのRoundのScope外)、新規
`price_derived_record_to_evidence()`がas_of Pathの既存の安全な規約
(`resolve_available_at()`)を採用することで、この新規Consumerだけを
安全側にした。

### pit-auditor Review(実施・全4件を独立に再確認の上で対応)

Codex/外部Reviewではなく、このLabの`pit-auditor`Subagent(Read-only)へ
実装完了後にReviewを依頼した(`PIT AUDIT: 4 FINDINGS(highest severity:
HIGH)`)。ユーザー指示・Lab既存方針(Reviewer Findingは無条件に真実
扱いせずMain Claudeが実Codeで再検証する)に従い、全FindingをMain Claude
自身が実際に該当Fileを読み直して再確認した上で対応した。

1. **[HIGH、CONFIRMED、修正済み]** `capability=DataCapability.
   POSITIONING`というTagだけでは、安全な`price_derived_record_to_
   evidence()`(このModule)と、既存の`positioning_record_to_evidence()`
   (D0057でLeak Risk確認済み)のどちらで構築されたEvidenceかを区別
   できない — 両者とも同じ`DataCapability.POSITIONING`をTagし、
   `EvidenceRecord`/`SourceMetadata`のいずれにも構築元を示すFieldが
   無いため。実際に`lib/positioning/evidence.py`を読み直し、同じ
   Price-derived `PositioningRecord`形状が両Converterへ渡せることを
   独立に確認した(CONFIRMED)。**修正**: `build_research_artifact()`
   へ`_uses_session_close_availability()`検証を追加した。新しいField
   追加はせず(Common Core Schema変更はD0057自身が見送った判断であり
   踏襲)、`price_derived_record_to_evidence()`の出力が持つ観測可能な
   性質(`available_at`が`session_close_at(value_date)`と厳密に一致
   する)を直接確認し、一致しないPOSITIONING Evidenceをfail closedで
   拒否する。回帰Test
   (`test_build_research_artifact_rejects_positioning_evidence_from_
   unsafe_converter`)で、既存`positioning_record_to_evidence()`経由の
   Evidenceが実際に拒否されることを直接確認した。
2. **[MEDIUM、CONFIRMED、既知の限界として文書化]** PIT安全性の検証は
   `build_research_artifact()`にのみ存在し、`ResearchArtifact`を直接
   構築(`build_research_artifact()`を経由しない)した場合や
   `ResearchArtifactRegistry.record()`単体では再検証されない。実際に
   `ResearchArtifact.__post_init__`/`ResearchArtifactRegistry.record()`
   を読み直し、いずれもTimestamp検証を持たないことを確認した
   (CONFIRMED)。**対応**: 既存の`Hypothesis`/`SplitRunResult`等でも
   Builder関数を経由しない直接構築自体は禁止していないという既存慣行
   に合わせ、`ResearchArtifact`のDocstringへ「本番用途は必ず
   `build_research_artifact()`を経由すること」を明記するに留めた
   (`ResearchArtifactRegistry`が`evidence_pool`を受け取って再検証する
   設計への拡張は、このRoundの「最小Vertical Slice」の範囲を超える
   ためBacklog、Stage 3 v1では実施しない)。
3. **[LOW、CONFIRMED、修正済み]** `price_derived_record_to_evidence()`
   が計算する`AvailabilityBasis.INFERRED`は`EvidenceRecord`に保持され
   ない(`SourceMetadata`にBasis相当のFieldが無いため、既存の全
   Evidence Converterに共通する制約)。既存`positioning_record_to_
   evidence()`のDocstringにはこの制約への注意書きがあるが、新規関数の
   Docstringに同等の注意書きが無かった(CONFIRMED)。**修正**:
   Docstringへ同等の注意書きを追加した。
4. **[LOW、CONFIRMED、修正済み]** `evidence_pool`内で`evidence_id`が
   重複する場合(呼び出し側のBug)、Future Leakage判定・Evidence捏造
   判定のSet演算が意図しない挙動になりうる。呼び出し側のBugが前提の
   低優先度指摘だが、対応コストが低いため採用した。**修正**:
   `build_research_artifact()`冒頭で`evidence_id`の重複を検知し
   `ValueError`にする。

### Tests

`13_tests/test_research_artifact.py`(24件、Research != Decision・
Evidence捏造防止・Future Leakage防止・Allowed Default Data fail
closed・Confidence 3軸分離・INSUFFICIENT_EVIDENCE Abstention・missing
source != negative evidence・CONTRADICTS/ALTERNATIVE_EXPLANATIONの
生存確認・Versioned Lineage・D0057安全化・pit-auditor Finding回帰2件・
Acceptance End-to-End)、`13_tests/test_research_artifact_registry.py`
(5件、Append-only・重複拒否・delete/update無し・`latest_for()`・
旧Record後方互換読み込み)。

### Regression

`ruff check`/`ruff format --check`/`mypy`(`core app.py scripts
Japanese_Equity_Lab/lib`)いずれもclean、`pytest`(Lab+Screening Tool)
1032件全てpass(既存1009件+新規23件、pit-auditor Finding対応で回帰Test
2件追加、新規Failure無し)。`git diff --stat -- core/ app.py tests/`で
変更が無いことを確認(Screening Tool Protected Paths不変)。

### このRoundで着手していないもの

Discovery Engine・Expectations Engine・Decision Engine・Portfolio
Engine・新規Data Provider・H0002・Phase5 v2・D0057自体の解決(2経路の
どちらを正とするかを決める設計変更)・Agent階層のいずれにも着手して
いない。Macro/News/Consensus(EXPECTATIONS)/non-price Positioning/
Availability未確認のhistorical disclosureは既定で使用しない
(`DEFAULT_ALLOWED_CAPABILITIES`によりfail closed)。

## D0073 — Stage 3.1: Real-Data Research Acceptance(実データ0件、BLOCKED)

Stage 3 v1(`ResearchArtifact`、D0072)を「新しいEngineを作らず、既存
Repoで確認できる実データ1件」でDogfoodする試みを実施した。**結論:
このSessionから到達可能な範囲に、Fundamentals/Disclosures/Positioning
いずれについても実データ(非Fixture)が1件も存在しない。** ユーザーの
明示指示「Research内容を埋めるためにEvidenceを捏造しない。使える
Evidenceが少なければ、その不足自体を結果として残す」に従い、実データを
Fixtureで代替する・Evidenceを捏造する・SUPPORTED/INCONCLUSIVEを無理に
出すのいずれも行わず、この不足そのものをこのEntryとして記録する。

**確認した事実(すべてこのRound内で直接確認、推測なし)**:

1. `Japanese_Equity_Lab/01_data/`配下(`fundamentals/`・`point_in_time/`・
   `sectors/`・`prices/`・`corporate_events/`・`processed/`・`market/`)は
   いずれも`.gitkeep`のみでデータファイルが0件。
2. `01_data/raw/`には`fixture/`のみが存在し、中身はPhase5 Backtest
   Smoke Test用の合成Data(`equity_bars`/`benchmark`/`trading_calendar`/
   `daily_quotes`、`01_data/README.md`が「`fixture/`配下(合成データ)」
   と明記)。Fundamentals/Disclosures/Positioning Domainのデータは
   1件も含まれず、仮に含まれていたとしても合成データである以上使用
   できない。
3. `01_data/raw/jquants/`(実データの置き場、`.gitignore`対象)は
   このSessionのファイルシステム上に**存在しない**(過去に一度も
   Fetchされていない、または本Container起動時に持ち越されていない)。
4. `JQUANTS_API_KEY`は未設定、`.env`ファイルもRepository Root配下に
   存在しない。
5. このSessionから`https://api.jquants.com/`への通信はProxy Level で
   Block されている(`curl`が`CONNECT tunnel failed, response 403`)。
   長期的に確認済みのEGRESS_BLOCKED制約(Phase5 v1.1以降繰り返し確認)
   がこのRoundでも変わっていないことを再確認した。

**実施しなかったこと(禁止事項の遵守)**: 新規Provider実装・新規Fetch
Engine構築・UNKNOWN Availabilityの上書き・Fixtureを実データと称して
使用・Evidence 0件のままSUPPORTED/PARTIALLY_SUPPORTEDを捻出、のいずれも
行っていない。`build_research_artifact()`・
`ResearchArtifactRegistry`・Evidence Converter群(`disclosure_metric_
to_evidence()`/`disclosure_document_to_evidence()`/`price_derived_
record_to_evidence()`)はいずれも無変更(実行を妨げるコード上の欠陥は
見つかっていないため、「実行阻害要因が見つかった場合のみ本番Code変更」
の条件に該当しない)。

**このRoundでの結論**: Stage 3 v1自体の実装(D0072)に欠陥があるという
証拠はない — 阻害要因はCodeではなくDataの不在である。次にStage 3.1を
再試行する場合、ユーザー自身のローカルPC上で(`local-validation`
Skillに従い)既存の`JQuantsAdapter`/`fetch_jquants_local_snapshot.py`を
使って最低1銘柄分のFundamentals(および可能であればDisclosures/Price)
Raw SnapshotをFetchし、`01_data/raw/jquants/`(または同等のLocal
Snapshot)として保存した上で、それを本Sessionへ持ち込む(または
ユーザー環境で直接本Round相当の処理を実行する)必要がある。このLabの
既存の禁止事項(新規Provider・H0002・D0057解決)はいずれも今回の
結論に影響しない — 単に「実データそのものがこのSession内に存在
しない」という、Provider/Architecture以前の問題である。

**Code変更・Test追加**: 無し(コード上の実行阻害要因が見つからなかった
ため、`13_tests/`への新規Test追加もこのRoundでは不要と判断した — Test
すべき新しいCode Pathが無い)。`git diff --stat -- core/ app.py tests/`
で変更が無いことを確認(Screening Tool Protected Paths不変)。Regression
は本Entry・DECISIONS.md追記のみのDoc-only変更のため、Lab全体Regression
の再実行は不要と判断した(D0071 Round同様、Doc-onlyはCode Regression
Scope外)。

## D0074 — Stage 3.1: Real-Data Research Acceptance再試行(ユーザーのローカルPC環境、実行成功)

D0073がBLOCKEDと判定した根拠(実データ0件・Egress遮断)は、D0073自身が
明記した通りその時点のセッション固有の状態だった。今回、ユーザーの
ローカルPC上の別セッションで再確認したところ、以下の事実が確認された
(いずれも直接確認、推測なし):

1. **Egress**: `api.jquants.com`への直接TLS接続を確認(`curl -v`、
   実際のAWS API Gateway応答`x-amzn-RequestId`/`{"message": "The api
   key is required."}`)。Proxy Blockではなく到達可能。
2. **JQUANTS_API_KEY**: 環境変数はSETされていたが、値が実際のAPIキー
   ではなくクリップボード貼り付け用PowerShellコマンド文そのものだった
   (設定ミス、ユーザー環境固有の問題でありCode欠陥ではない)。今回は
   このKeyを使った新規Fetchは行っていない。
3. **Local Raw Snapshot**: `Japanese_Equity_Lab/01_data/raw/
   local_snapshot_input/`(`.gitignore`対象)に、2026-08-16に取得済みの
   実J-Quants Local Snapshot(Financial Summary + Daily Bars、7203/6758/
   8056/3626の4銘柄)が既に存在していた。D0073の「実データ0件」は
   このRoundのセッションには当てはまらない。

### 実施内容(`scripts/stage3_1_research_artifact_7203.py`、新規)

新しいJ-Quants Client・新しいEvidence Framework・新しいEngineは作らず、
既存の`LocalSnapshotAdapter`/`parse_financial_summary_payload`/
`equity_bars_payload_to_raw_bars`/`build_research_artifact`(D0072)を
そのまま再利用し、1社(7203、トヨタ自動車、選定はInvestment
Recommendationではない)+ 明示的`as_of`(2024-11-15T15:00 JST)で
`build_research_artifact()`を実データでEnd-to-End実行した。新規API
呼び出しは一切行っていない(既存Local Snapshotのみ使用)。

**Historical PIT Safetyを「実データである」ことの根拠にしなかった**:
今回のSnapshotの`retrieved_at`は実際には2026-08-16頃(ファイルmtime
起源)である。既存の2つのPIT機構を無変更のまま適用した結果:

- Fundamentals(`disclosure_metric_to_evidence()`、`available_at=
  envelope.retrieved_at`固定、D0049）: 主要Metric(sales/operating_
  profit/net_profit/eps/ordinary_profit)についてEvidence 80件を構築
  したが、`retrieved_at`(2026-08-16)が`as_of`(2024-11-15)より後のため
  `filter_usable_at()`により**全80件が構造的に除外された**。これは
  欠陥ではなく意図通りのFail Closed動作であり、`DataGap`
  (status=UNAVAILABLE)として記録した。
- Positioning(price-derived、`price_derived_record_to_evidence()`、
  `session_close_at(observation_end)`基準でretrieved_atと無関係、
  D0057を安全側に回避する既存Consumer）: 直近10 Session分のTurnover
  Value + Volume Moving Average(20D)、Evidence 20件のうち**18件が
  `as_of`時点で利用可能と判定された**。除外された2件(2024-11-15分)は
  `session_close_at(2024-11-15)`が15:30 JST(2024-11-05のTSE取引時間
  延長を`lib.market_calendar`が正しく反映)であり、`as_of`の15:00 JST
  より後だったため——これもFail Closedの正しい動作であり、意図的に
  `as_of`を調整して回避することはしなかった(値の推測補完・Filter回避
  はいずれも行っていない)。
- Disclosures(EDINET/TDnet): 7203向けの実Documentは未取得のため
  `DataGap`(status=MISSING)。Consensus/Macro/News/Expectations:
  Phase5 v1 Scope外(`DEFAULT_ALLOWED_CAPABILITIES`が構造的に強制、
  変更していない）。

結果、`ResearchArtifact`(`artifact_id=ART_STAGE3_1_7203_20241115_V1`)
はPositioning Evidence 18件のみを`included_evidence_ids`に持ち、Bull/
Bear Caseはいずれも空(Evidence無し)、Base CaseはPositioning Evidenceの
記述統計のみを参照、`conclusion=INSUFFICIENT_EVIDENCE`・
`research_confidence=INSUFFICIENT`(`__post_init__`の整合性検証を
満たす）で構築された。Evidence捏造・Fail Closed回避はいずれも発生して
いない(`ResearchArtifactRegistry`(`lib/registry/research_artifact_
registry.py`)の`record()`で`Japanese_Equity_Lab/02_company_research/
7203_Toyota_Motor/research_artifacts.jsonl`(`.gitignore`対象外、この
Round初のRegistry永続化先として選定——`06_backtests/`と同型のAppend-only
Registryだが、Backtestではなく企業別Researchのため`02_company_research/
<証券コード>_<企業名>/`配下に置いた)へ記録済み)。

### Code変更

`scripts/stage3_1_research_artifact_7203.py`(新規、運用スクリプト、
`core`/`app.py`/`lib/`のいずれも無変更)。`git status --short`で
`lib/`等既存Production Codeへの変更が無いことを確認済み。

### Regression(訂正: Full Regression未実施だった点を訂正。件数表記の誤りはD0072側にあった)

初版は「`lib/`/`core/`/`app.py`を変更していないためLab全体Regressionは
不要」と判断していたが、これは誤り — `scripts/stage3_1_research_
artifact_7203.py`という新規`.py`File自体を追加しており、D0071 §7
(Verification Staging: targeted→relevant→full regression)の基準に
従えばFull Regressionが必要だった。本Roundで訂正し、実際にFull
Regressionを実行した。

**件数表記について**: 初版は「`test_research_artifact.py`(24件)・
`test_research_artifact_registry.py`(5件)、計23件」と書いており、
「24+5=23」という表記の整合性自体が誤りだった。`--collect-only`で
直接数え直したところ、`test_research_artifact.py`は実際には**18件**
(D0072本文中の「24件」という記載自体が誤り——本Entryでは訂正しない、
D0072は既にRegistryへ記録済みのため上書きせず、この食い違いのみここに
記録する)・`test_research_artifact_registry.py`は5件で、**合計23件が
正しい数値**だった。つまり初版の「23件」という合計自体はたまたま
正しく、直す必要は無かった。

**Full Regression結果**(`.venv/Scripts/python.exe -m pytest tests/
Japanese_Equity_Lab/13_tests/ -q`、Windows実Venv):
1031 passed, 1 failed。失敗は`Japanese_Equity_Lab/13_tests/
test_protected_path_hook.py::test_hook_warns_on_protected_screening_
tool_paths`のみで、`git stash`で本Round差分(DECISIONS.md追記・新規
Script・新規Registry出力)を一時退避しSyncした`origin`のPristine HEAD
(`a5d637c`)上で同一Testを再実行しても同じ失敗が再現することを直接確認
した(=本Roundの変更とは無関係な既存環境問題、`.claude/hooks/
protected_path_warning.sh`のWindows Git Bash上でのPath正規化/`jq`
呼び出し起因と推定、Hook自体は修正していない)。`test_research_
artifact.py`(実18件)・`test_research_artifact_registry.py`(5件)は
Full Regressionの一部として引き続き全件pass(計23件)。H0001 Locked
Testは実行していない。

### Quality Gate(ruff / mypy、`requirements-dev.txt`の既存宣言を使用)

`postEdit`Hook(`.claude/hooks/post_edit_quality_gate.sh`)は
`.venv/bin/python`というUnix Venv Layoutを前提としており、この
Windows環境の実際のVenv(`.venv/Scripts/python.exe`)を見つけられず
`python3`(Microsoft Store版、Package無し)へFallbackして毎回失敗する
(本Roundの変更とは無関係な既存Hookの環境依存Bug、Hook自体は指示通り
修正していない)。

`requirements-dev.txt`(`ruff>=0.6`・`mypy>=1.11`、既存宣言)から
`.venv/Scripts/python.exe -m pip install -r requirements-dev.txt`で
インストールし(ruff 0.16.4・mypy 2.3.1が解決された、Versionを独自に
選定してはいない)、実際に実行した:

- `ruff check .`: 新規Scriptに5件の指摘(未使用変数1・行長超過2・
  未使用Import1[後続修正で判明]・未使用Helper関数1)を検出、いずれも
  修正(`ruff format`含む)し、最終的に`All checks passed!`(288 File)。
- `ruff format --check .`: 最終的に全File整形済み。
- `mypy core app.py scripts Japanese_Equity_Lab/lib`: **QUALITY_GATE_
  ENV_BLOCKED**。`.venv/Lib/site-packages/numpy/__init__.pyi:737: error:
  Type statement is only supported in Python 3.12 and greater [syntax]`
  で即座に停止する。`pyproject.toml`の`[tool.mypy] python_version =
  "3.11"`と、`requirements-dev.txt`解決済みのnumpy Stub(3.12構文使用)
  の非互換が原因(`git stash`でPristine HEAD上でも同一Errorを確認済み、
  本Round起因ではない)。numpy/mypyのVersion Pin変更は「勝手にVersionを
  選ぶ」ことになるため今回は行っていない。

### Stage 4候補(初版の断定を訂正)

初版は「Fundamentals Evidence経路へのPolling Log機構、またはA系統の
正式サポートを追加すべき」と断定的に記載したが、これは過大な主張
だった。今回のRoundで実際にCONFIRMEDなのは以下のみ:

- B系統(`disclosure_metric_to_evidence()`、`available_at=envelope.
  retrieved_at`固定)経路では、Historical Fundamentalsが構造的に
  全除外されること(直接確認済み、80件中0件usable)。
- A系統(`AvailabilitySemantics.MARKET_PUBLIC_AT`、`published_at`
  基準)という既存Capability自体は`lib/fundamentals/view.py`の
  `as_of_by_semantics()`に既に存在するが、これが`ResearchArtifact`
  Evidence経路(`disclosure_metric_to_evidence()`→`filter_usable_at()`)
  へ安全に接続可能かどうかは、**今回のRoundでは未検証**(`disclosure_
  metric_to_evidence()`はSemantics引数を持たず、`available_at`を
  常にB系統固定で構築するため、A系統をEvidence経路へ繋ぐには何らかの
  追加設計が要る——ただしそれがPolling Log新設という重い解決策を要する
  のか、既存A系統Viewの再利用で足りるのかは未調査)。

したがって次の候補は「Polling Log機構を追加する」と断定せず、
**「Fundamentals A系統/B系統のAvailability Pathを狭く監査し、
既存A系統(`as_of_by_semantics(availability_semantics=MARKET_PUBLIC_AT)`)
の再利用でEvidence経路への安全な接続が足りるか、それとも実際に
Polling Log相当の新規観測機構が必要かを判断する」**という調査Task
とする(このRoundでは調査・実装いずれも着手していない)。

### Registry Output(`research_artifacts.jsonl`)のCommit方針

`Japanese_Equity_Lab/02_company_research/7203_Toyota_Motor/
research_artifacts.jsonl`の内容を確認した — Secret(APIキー等)・Raw
Payload(生のJ-Quants Response)のいずれも含まない。含むのはArtifact
ID・企業Code・as_of・Evidence ID一覧・Bull/Base/Bear要約文・DataGap・
Confidence・Conclusionのみ(Evidence本体ではなく、そのID参照のみ)。

`.gitignore`を確認した結果、`02_company_research/`にも本Fileパターンにも
除外ルールは無い。一方、同型のAppend-only Registry(`lib/registry/
research_artifact_registry.py`はD0072で「既存`ExperimentRegistry`と
同じAppend-only JSON Linesパターン」と明記済み)である
`Japanese_Equity_Lab/06_backtests/{experiment_registry,provenance,
preregistrations,locked_test_audit,locked_test_audit_real}.jsonl`は
いずれも`git ls-files`で追跡済み(=既にCommit対象として運用されている)
ことを確認した。したがって「明確な既存方針が無い」わけではなく、
**既存の同型Registryは一貫してCommit対象として扱われている**、という
Precedentがある。ただし`02_company_research/`配下という新しいPath自体は
今回が初のRegistry設置であり、この判断が正しいかはユーザー確認を要する
ため、本Roundではgit addせず報告に留める(Commit実行はしていない)。

## D0075 — Fundamentals A-Path → ResearchArtifact Minimal Bridge(A/B Availability Semanticsの明示的分離)

D0074で確認されたFundamentals Availability Architecture Gap(B系統
(`disclosure_metric_to_evidence()`、`available_at=envelope.retrieved_at`
固定)経路では、Local Snapshotのretrieved_at(実際には2026-08-16頃)が
歴史的`as_of`より後になるため、Historical Fundamentalsが構造的に全除外
される)を最小限解消した。**Polling Logは実装していない**(B系統の
Future Capabilityとして保留、要件通り)。

### 事前確認(Before Implementation)

「Codex Fundamentals PIT Audit」という文書をリポジトリ全体(DECISIONS.md・
`12_reports/`・`AUDIT_MANIFEST.md`含む)から`grep`したが**見つからな
かった**(該当ゼロ件)。HEADはLocal/Remoteとも`15edf30`で同期済み
(未Sync分は無い)。したがってこのRoundは、この文書の内容ではなく、
ユーザー自身が指示中で明示したArchitecture Decision(A系統/B系統の定義)
と、実際に読み直したD0049(`lib/fundamentals/evidence.py`のPIT Bugfix)
・D0057(Cross-Capability PIT Gate、Positioning Evidence Pathの2経路
不一致)・D0072(ResearchArtifact、POSITIONING構築元検証のPrecedent)・
D0074(A系統再検証)を根拠に設計・実装した。ユーザー提示のArchitecture
Decision(A=Market Information Research/B=Reproducible System
Simulation)は、実Codeで確認した`lib.evidence.model.AvailabilitySemantics`
(`MARKET_PUBLIC_AT`/`PROVIDER_AVAILABLE_AT`、D0042で新設済みのEnum)の
既存定義と完全に一致することを確認した(新規Enum追加は不要と判断)。

### Architecture Decision(既存Enumの再利用のみ、新規Enumは追加していない)

- A = `AvailabilitySemantics.MARKET_PUBLIC_AT`(既存Enum、Market
  Information Research、「その時点で市場へ公表済みだった情報」)。
- B = `AvailabilitySemantics.PROVIDER_AVAILABLE_AT`(既存Enum、
  Reproducible System Simulation、「その時点でLab/Providerから実際に
  取得可能だった情報」、既定)。

### 実施内容

1. **`lib/fundamentals/evidence.py`(新規関数追加のみ、既存
   `disclosure_metric_to_evidence()`は無変更)**: `source_version_to_
   evidence_market_public_at(version: SourceVersion, *, entity_code:
   str) -> EvidenceRecord`を追加。Flow: `fundamentals_as_of(availability_
   semantics=MARKET_PUBLIC_AT)`が選定した`SourceVersion`のみを受け取り、
   `available_at=version.published_at`(市場公表時刻そのもの)を使う。
   `version.published_at is None`(UNKNOWN)の場合は`ValueError`で
   fail closed(要件v1-3)。`SourceMetadata.source_type`へ`MARKET_
   PUBLIC_AT_SOURCE_TYPE`("JQUANTS_FINS_SUMMARY_MARKET_PUBLIC_AT")と
   いうTag文字列を付与——新しいSchema Fieldは追加せず、既存の自由文字列
   Fieldへ異なる値を入れるだけでA/B構築元を判別可能にする(D0072
   pit-auditor HIGH Finding[POSITIONING構築元検証]と同じ設計思想を
   Fundamentalsへ適用)。
2. **`lib/evidence/research_artifact.py`**: `ResearchArtifact`へ
   `fundamentals_availability_semantics: AvailabilitySemantics =
   PROVIDER_AVAILABLE_AT`(既定=B系統、後方互換)Fieldを追加。`build_
   research_artifact()`へ同名引数(既定値同じ)を追加し、`evidence_pool`
   内のFUNDAMENTAL capability Evidenceの実際の構築元(`source.
   source_type == MARKET_PUBLIC_AT_SOURCE_TYPE`か否か)と、宣言された
   `fundamentals_availability_semantics`が一致しない場合、POSITIONING
   の`_uses_session_close_availability()`と同型のfail closed Validation
   で`ValueError`にする(A/B混在防止、要件v1-5)。
3. **`lib/registry/research_artifact_registry.py`**: `_artifact_to_
   dict`/`_artifact_from_dict`へ`fundamentals_availability_semantics`
   のSerialize/Deserializeを追加。旧Record(このField無し)は`.get()`
   Defaultで`PROVIDER_AVAILABLE_AT`として後方互換Load可能(既存の
   `data_gaps`後方互換Patternと同じ、回帰Testで確認)。
4. **`scripts/stage3_1_research_artifact_7203.py`**: `--semantics
   {B,A}`(既定B)を追加。B実行は既存Behaviorとbyte-identical
   (`fundamentals_evidence_built=80 usable=0`・`positioning usable=18`、
   再実行で確認済み)。A実行は`build_revision_histories()`→
   `fundamentals_as_of(availability_semantics=MARKET_PUBLIC_AT)`→
   `source_version_to_evidence_market_public_at()`のFlowで、主要Metric
   (sales/operating_profit/net_profit/eps/ordinary_profit)のうち
   `value_availability=PRESENT`のみ(IFRS下でNOT_APPLICABLEな
   ordinary_profitは除外——実装中に一度この絞り込みを漏らし、20series
   全件が「選定」されたが中身が空文字列のMetricを含んでいたBugを発見・
   修正した)を対象に、実際に`as_of`(2024-11-15T15:00 JST)時点で市場
   公表済みだった16件のみをEvidence化した(16 series評価・16件選定・
   16件全件usable、80件を無理に通したわけではないことを実行結果で確認、
   要件v1-8)。

### Source Vintage Guard(要件v1-7、大きなFrameworkは作っていない)

J-Quants Financial Summaryが「訂正前値を必ずhistorical rowとして保持
する」ことを公式仕様から完全確認できていないため、A系統実行のArtifactは
Source-vintage completenessをSUPPORTEDと断定しない。既存の`ConfidenceLevel`
(`data_confidence=LOW`・`research_confidence=LOW`)・`DataGap`
(`status=UNVERIFIED`、topic="J-Quants Financial Summary Source Vintage
Completeness")のみで表現し、新しいProvider Validation Frameworkは
作っていない。`conclusion=ResearchConclusion.INCONCLUSIVE`(SUPPORTED/
PARTIALLY_SUPPORTEDへは倒さない)。

### PIT Safety(A/B/Future Leakage)

`fundamentals_as_of()`自体(D0042既存実装、無変更)が`published_at <=
decision_at`の候補のみに絞り込み最新Versionを選ぶため、Future Revision/
Correctionのas_of以前への漏洩は構造的に発生しない——このBridge自体は
selection Logicを持たない(要件v1-6)。B系統(`disclosure_metric_to_
evidence()`)は一切変更していない(D0049 rollbackなし)。D0057自体
(Positioning Evidence Path 2経路不一致の一般解決)にも着手していない
(Do Not §10)。

### Tests(新規17件、全てpass)

- `13_tests/test_fundamentals_evidence_market_public_at.py`(新規、6件):
  A path開示前unavailable・A path開示後usable・future revision非leak・
  future correction非leak・UNKNOWN market_public_at拒否(Bridge単体+
  `fundamentals_as_of()`両方)。
- `13_tests/test_research_artifact.py`(既存24件[実18件]に4件追加、
  計22件[実測]): Semantics既定値記録(B変更なし確認)・A Semantics記録・
  B evidence宣言時のA混在拒否・A宣言時のB混在拒否・A path開示前PIT除外。
- `13_tests/test_research_artifact_registry.py`(既存5件に1件追加、
  計6件): 旧Record(Field無し)の後方互換Load。

### Regression

`pytest tests/ Japanese_Equity_Lab/13_tests/`: **1042 passed, 1 failed**
(失敗は`test_protected_path_hook.py::test_hook_warns_on_protected_
screening_tool_paths`のみ、D0074で確認済みの既存環境問題[Windows Git
Bash上の`protected_path_warning.sh`]と同一、本Round無関係)。`ruff
check .`/`ruff format --check .`いずれも`All checks passed!`(初回
`ruff check`で新規Fileに軽微な指摘[未使用変数・行長超過]2件、`ruff
format`で解消)。`mypy core app.py scripts Japanese_Equity_Lab/lib`は
D0074と同一の**QUALITY_GATE_ENV_BLOCKED**(numpy stub/python_version
非互換、pre-existing、本Round起因ではない)。`git diff --stat -- core/
app.py tests/`で変更が無いことを確認済み(Screening Tool Protected
Paths不変)。H0001 Locked Testは実行していない。

### このRoundでやらないこと(Do Not §10、遵守確認)

Polling/first-seen Log実装・D0049 rollback・D0057一般解決・新規Provider・
Stage 4広範実装・Expectations Engine・Decision Engine・Discovery Engine・
H0001再実行のいずれにも着手していない。`generic available_at`を
`market_public_at`へ戻す変更(既存`disclosure_metric_to_evidence()`)も
行っていない。

## D0076 — Stage 3.2: MARKET_PUBLIC_AT Real-Data Acceptance(D0075のDogfood、Code変更なし)

D0075で実装したFundamentals A-Path Bridgeを、既存7203 Local Snapshot
(新規Fetchなし、Raw Snapshot無変更)で実際に実行し、B系統(既定)との
比較・Research Usefulness評価・次のBottleneck特定を行った。**新機能は
追加していない、Code欠陥も発見されなかったため無変更。**

### 実行結果(`scripts/stage3_1_research_artifact_7203.py --semantics
{B,A}`、いずれも既存artifact_idのためAppendOnlyViolationErrorで
Persistenceは拒否されたが、Print出力はRegistry書き込み前に実行される
ため前Round[D0075]の記録値とByte-identicalであることを確認した——
決定論的な再現性の直接確認、Registryの重複拒否も期待通り機能):

| 項目 | B(既定、retrieved_at基準) | A(MARKET_PUBLIC_AT) |
|---|---|---|
| Fundamentals raw(PRESENTのみ、全20開示×主要Metric) | 80 | 16 series評価 |
| as_of選択後 | (B系統はSeries選択を経ない) | 16(16/16選択、全series該当) |
| Fundamentals usable Evidence | 0 | 16 |
| Positioning usable | 18 | 18(A/Bで不変) |
| Total Evidence | 18 | 34 |
| data_confidence | LOW | LOW |
| evidence_confidence | MEDIUM | MEDIUM |
| research_confidence | INSUFFICIENT | LOW |
| conclusion | INSUFFICIENT_EVIDENCE | INCONCLUSIVE |

### A-Path選択内容の直接検証(Read-only Inspection Script、Repo変更なし)

16件の内訳を実際に読み出して確認した: `sales`/`operating_profit`/
`net_profit`/`eps`の4 Metric × `1Q`(2024-08-01公表、対象期2024-06-30)・
`2Q`(2024-11-06公表、対象期2024-09-30)・`3Q`(2024-02-06公表、対象期
2023-12-31)・`FY`(2024-05-08公表、対象期2024-03-31)の4 Period、全て
`ActualOrForecast.ACTUAL`(Forecast/Guidance系Metricは今回のKey Metric
Setに含めていない、Bridge自体の制約ではなくScript側のScope選択)。
`ordinary_profit`はIFRS下`NOT_APPLICABLE`のため実装中に一度誤って
20 series全件を選定してしまうBugを作りかけたが、`value_availability=
PRESENT`絞り込みを追加して修正済み(D0075で記録済み、本Roundで再確認の
み、新規修正なし)。4 Period(1Q/2Q/3Q/FY)は`PeriodBasis.CUMULATIVE`
(累計値)であり、かつ1Q/2Qは会計年度2025年3月期、3Q/FYは2024年3月期
(異なる会計年度)であるため、この4値をそのまま「直近4四半期の連続
Trend」として単純比較すると異なる会計年度の累計期間を混同する
(Growth評価をPARTIALに留めた理由、下記)。

### Source Vintage Constraint(推測禁止、確認事項のみ)

A系統でEvidenceが16件usableになったことは、「2026年取得Snapshotが
2024年当時のOriginal Provider Snapshotを完全に保存している」ことを
意味しない。J-Quants Financial SummaryのHistorical Revision/Correction
Completenessは今回も確認していない(確認する手段がこのRoundには無い)。
`data_confidence=LOW`・`research_confidence=LOW`・`DataGap(status=
UNVERIFIED、topic="J-Quants Financial Summary Source Vintage
Completeness")`として既存Confidence/DataGap機構へ反映済み(D0075と
同一の扱いを維持、この制約を消すための推測・断定は行っていない)。

### Research Usefulness Evaluation(実際のEvidence内容に基づく判定)

| Section | 判定 | 根拠 |
|---|---|---|
| Business/Earnings | SUPPORTED_BY_DATA | Sales/OP/NP実績4期分(ACTUAL)を直接確認できる |
| Growth | PARTIAL | 4期分はあるが異なる会計年度のCUMULATIVE値混在のため単純比較不可、真のYoY比較(例: 2Q FY2025 vs 2Q FY2024)はas_of選択の性質上1系列につき1Versionのみ保持のため今回のEvidence Poolには含まれない |
| Financial Quality | UNAVAILABLE | TA/Eq/EqAR/CFO/CFI/CFF等はそもそも`lib.fundamentals.normalize._METRIC_FIELD_MAP`に未マッピング(A/B系統どちらの問題でもない、Normalize層の既存制約) |
| Guidance | UNAVAILABLE | 会社予想系Metric(`*_current_year_forecast`等)は今回のScript実行のKey Metric Setに含めていない(Bridge自体はForecast Metricも同じ経路で扱える設計、次Roundで追加可能な狭いScope) |
| Valuation | UNAVAILABLE | 生Close PriceがEvidence化されていない(Positioning EvidenceはTurnover Value/Volume MAのみ)・BPS未マッピングのため、PER/PBR等の倍率を計算できない |
| Catalysts | UNAVAILABLE | Disclosure Documents(EDINET/TDnet)・NewsともにMISSING DataGap |
| Risks | UNAVAILABLE | 同上、定性的Risk Factor記述の情報源が無い |

### Bull/Base/Bear

`scripts/stage3_1_research_artifact_7203.py`の既存実装(D0075時点)が
そのまま要件を満たしていることを確認した(追加変更なし): Bull/Bear
Caseはいずれも空(方向性のあるClaimを主張しない、Evidence無し)。Base
Caseのみ、実際にincluded_evidence_idsに含まれる34件(Fundamentals
16 + Positioning 18)を`supporting_evidence_ids`として参照する記述的
要約(Research != Decision、Narrative完成を目的にしていない)。

### Key Question: 次にResearch Qualityを最も制限しているものは何か

**Valuation dataと判定した**(想像ではなく今回のActual Run結果から
消去法で評価):

- Consensus/Expectations・Macro: Phase5 v1 Scope外(`DEFAULT_ALLOWED_
  CAPABILITIES`が構造的に除外、そもそも今回の対象外であり「次に閉じる
  べきGap」ではない)。
- Disclosure content/News/Catalysts: 依然MISSING。ただしEDINET/TDnet
  接続は既存`PHASE5_READINESS.md`監査で`NOT_READY_FOR_PHASE5`(License/
  Spec未確認)と既に判定済みの大きめのGapであり、新規Provider統合相当の
  作業を要する。
- Source Vintage reliability: Confidenceの天井を作っているが、
  「何も評価できない」原因ではなく「評価の確からしさを下げる」制約
  である(質的に異なる種類の制限)。
- Research synthesis: 今回のMechanical Pipeline自体は正しく機能して
  おり、Synthesis能力自体のGapではない。
- **Valuation data**: 今回のRunで唯一「材料(生Close Price・EPS)は
  ほぼ手元にあるのに、Evidence化されていないために計算できない」
  という、Scopeが狭く・新規Provider不要な残存Gapである(Price Data
  自体は既存`01_data/raw/local_snapshot_input/`に既にある、Positioning
  Evidence Converterが生Priceを持たないだけ)。

### Do Not(§7、遵守確認)

Polling Log・D0057一般解決・新規Provider・Expectations/Decision/
Discovery/Portfolio Engine・H0002・Phase5 v2・BUY/SELL・target price・
Optimizationのいずれにも着手していない。

### Code Change / Verification

Code変更なし(Execution/Semantic Defect未発見、「データが足りない」は
Code欠陥として扱っていない)。Verification Policy(§10)に従い、Code
変更が無いためTargeted Smokeのみ実施(`--semantics B`/`--semantics A`
再実行、いずれも前Round[D0075]記録値とByte-identicalな出力を確認)。
Full Regression・`ruff`/`mypy`は本Roundでは再実行していない(Code変更
無しのため、D0071/D0074と同じ判断基準)。既知のWindows Hook/mypy
Environment Issue(D0074/D0075既出)は本Roundでも未修正。H0001 Locked
Testは実行していない。

### Persistence

Runtime ResearchArtifact(A/B双方)はLocal保持のまま(`02_company_
research/7203_Toyota_Motor/research_artifacts.jsonl`、Registry
Long-term Commit Policy未確定のため今回もCommit対象外)。Raw Snapshot
も無変更・Commit対象外。本RoundでCommitするのはこのDECISIONS.md追記
(Doc-only)のみ。

## D0077 — Stage 3.3: LATEST_REPORTED_FY_PER v1(Valuation: Price + Fundamental Denominator → 決定論的Derived Fact)

D0076で特定した残存Gap(「生Close PriceとFY実績EPSはほぼ手元にあるのに、
Evidence化されていないために計算できない」)へ対応し、新しい`lib.valuation`
モジュールを新設した。新規Provider・新規Price/Fundamentals取得経路は作らず、
既存の`session_close_at`(PIT Price Selector)・D0075 Fundamentals A-Path
Bridge(`fundamentals_as_of(availability_semantics=MARKET_PUBLIC_AT)`)・
`detect_corporate_action_events_from_equity_bars`・`ProvenanceStore`/
`ProvenanceLink`をそのまま再利用する。

### Metric定義とArchitecture Guard

- Metric名は`LATEST_REPORTED_FY_PER`のみ。「Trailing PER」「TTM PER」とは
  呼ばない(TTM合算は四半期を合算する新しいDerivation Logicが必要になり、
  v1のScopeを超えるため今回は構築しない)。
- `LATEST_REPORTED_FY_PER = 選定Close Price ÷ 市場公表済みの最新FY実績EPS`
  (会社発表の通期実績値そのまま、四半期累計値ではない)。「割安/割高」
  「Cheap/Expensive」「BUY/SELL」「target price」等のInterpretationは
  一切含まない、単なる比率のFact(禁止語チェックをTestで直接確認)。
- `DataCapability.VALUATION`(`lib.sources.catalog`)を新設し、
  `DEFAULT_ALLOWED_CAPABILITIES`へ追加した。`MARKET_PRICE`単独にも
  `FUNDAMENTAL`単独にも属さない、Price+Fundamentalの2入力を要する
  Derived Fact専用の分類。

### PIT安全性

- Price Selector: `session_close_at(bar.session_date) <= as_of`を満たす
  最新Barのみを選ぶ(`select_latest_close_bar`)。Intraday Priceは推測
  しない。7203/as_of=2024-11-15 15:00 JSTで実データ検証: 2024-11-15
  Close(2704)は当日大引け未確定のため拒否され、2024-11-14 Close(2666、
  前日大引け確定済み)が選定されることを確認。
- EPS Denominator: D0075 A-Path(`fundamentals_as_of(availability_
  semantics=MARKET_PUBLIC_AT)`)が選定した`SourceVersion`を呼び出し側
  から受け取り、`build_latest_reported_fy_per()`内で`metric_type=eps`・
  `actual_or_forecast=ACTUAL`・`period_type=FY`・`consolidation_scope=
  CONSOLIDATED`であることをDefense-in-depthで再検証する(Series選定
  自体はD0075のBridgeで既に実装済みのため二重実装しない)。`published_at`
  がUNKNOWN、またはas_ofより後(Future Disclosure Leakage)の場合は
  fail closed(`ValueError`/`LookAheadBiasError`)。
- Corporate Action Guard: `fiscal_period_end <= event.effective_date <=
  price_date`のWindowに、Split/Reverse-Split等のShare Basis変更Event
  が1件でも検出された場合、Record自体を生成しない(`None`、fail closed、
  値の推測補正はしない)。v1ではEPS/BPSのSplit Adjustmentは実装しない。
  7203の今回Snapshotでは`detect_corporate_action_events_from_equity_
  bars()`によるEvent検出0件を実データで確認した。

### Provenance

`LatestReportedFyPerRecord`はPrice(`price_date`/`price_value`/
`price_available_at`)とEPS(`eps_value`/`fiscal_period_end`/
`published_at`/`source_version_id`)の両方のLineage情報を型付きFieldと
して保持する。既存`ProvenanceStore`/`ProvenanceLink`は`to_id`が同一の
複数`ProvenanceLink`(`from_type="price_bar"`と`from_type=
"fundamental_source_version"`)をそのまま許容するため、Dual-Parent
Provenanceは既存契約内で正直に表現できることを確認した
(`PROVENANCE_SCHEMA_GAP`には該当しない、Testで2件のParent Linkを直接
確認)。単一Primary Sourceへの偽装はしていない。

### Evidence / ResearchArtifact統合

`latest_reported_fy_per_to_evidence()`は`EvidenceType.FACT` +
`DataLayer.DERIVED` + `DataCapability.VALUATION`のEvidenceRecordを生成
する。`available_at = max(price_available_at, published_at)`(Price/EPS
両方が実際に公開された時刻のうち遅い方)。D0049(B系統`available_at`
Fallback禁止)には抵触しない(このEvidence自体がB系統を名乗っていない
ため)。ResearchArtifactは`EvidenceRelation.NEUTRAL`でVALUATION Evidence
を受理し、Bull/Bear Caseへ自動反映しない(Confidence自動昇格もしない)
ことをTestで確認した。

### 実データ検証(7203、既存Local Snapshot、Hard-code無し)

`as_of=2024-11-15 15:00 JST`で`build_latest_reported_fy_per()`を実行
(Read-onlyの検証Scriptから、`scripts/stage3_1_research_artifact_7203.py`
と同じLocal Snapshot Loadingパターンを再利用、Repo/`02_company_
research/7203_Toyota_Motor/`は無変更):

- Price = 2666(price_date=2024-11-14、実データからPIT Selectorが計算)
- FY実績EPS(連結) = 365.94(envelope=ENV_7203_20240424575411、
  published_at=2024-05-08 13:55 JST)
- `LATEST_REPORTED_FY_PER` = 2666 / 365.94 ≈ 7.2853(≈7.29x)
- Corporate Action Event検出数 = 0

割安/割高等の判断はしていない(「計算可能」の確認に留める)。

### Tests

`13_tests/test_valuation_latest_reported_fy_per.py`(13件、全てPASS):
Price Selector(同日Close拒否/前日Close選定/未確定時None)、FY実績EPS
選定、2Q累計EPS拒否、Future Disclosure拒否、UNKNOWN published_at拒否、
Corporate Action Guard(あり→fail closed/なし→成功)、Entity Mismatch
拒否、Evidence(DERIVED+VALUATION、禁止語不在)、Dual-Parent Provenance、
ResearchArtifactのVALUATION受理。Fundamentals A/B Guard・B系統の不変性
は既存Regression Suiteで確認(専用の新規Testは追加していない、既存
Testが引き続きPASSすることで確認)。

### Verification

- `ast.parse` + Import解決: 全対象ファイルOK。
- Targeted(`test_valuation_latest_reported_fy_per.py`): 13/13 PASS。
- Relevant(`-k "fundamental or research_artifact or catalog or
  evidence"`): 295/295 PASS。
- Full Regression(`13_tests/`): 1018/1019 PASS。唯一の失敗は
  `test_protected_path_hook.py::test_hook_warns_on_protected_screening_
  tool_paths`で、今回のScope外(`lib/valuation`等とは無関係な
  Repo Root Hookスクリプトのテスト)。既存の未修正Test(D0071/D0074/
  D0075で既出のWindows/Encoding系Environment Issue、`core/models.py`等
  非Japanese_Equity_Labパスに対するBash Hookの挙動)であることを、
  無関係な既存Test(`test_fundamentals_view.py`)でも同一のmypy
  Environment Issueが再現することと合わせて確認した——本Round由来の
  Regressionではない。
- `ruff check`: 対象ファイル全てPASS(初回`E501`1件は`__import__`経由の
  遠回しなImportを通常のTop-level Importへ書き換えて解消)。
- `ruff format --check`: 対象ファイル全てPASS(`builder.py`の1関数
  シグネチャを`ruff format`で整形)。
- `mypy`(`lib/valuation/`・`lib/sources/catalog.py`・`lib/evidence/
  research_artifact.py`): Success、0 issues。Test File側は既知の
  Windows/numpy/Python 3.14 Environment Issue(`numpy/__init__.pyi`の
  `type`文構文、Python 3.12+専用構文が今回のmypyバージョンで誤検出)が
  Pristine HEADの既存Testファイルでも同一再現するため
  `QUALITY_GATE_ENV_BLOCKED`として記録、修正はしない。

### Commit対象

`lib/valuation/`(新規)・`lib/sources/catalog.py`・`lib/evidence/
research_artifact.py`・`13_tests/test_valuation_latest_reported_fy_per.py`
・このDECISIONS.md追記。`02_company_research/7203_Toyota_Motor/`
(Runtime JSONL、既存D0075/D0076由来、今回変更なし)とRaw Snapshotは
今回もCommit対象外(既存方針を継続)。

### Do Not(遵守確認)

Forward PER・PBR・Stage 4のいずれにも着手していない。既存の禁止Hook
問題(`test_protected_path_hook.py`)・H0001 Locked Testの再実行もして
いない。

## D0078 — Stage 3.4: Valuation-Integrated Real Research Acceptance(D0077のResearchArtifact統合Dogfood、Measurement Only・Code変更なし)

D0077で完成した`LATEST_REPORTED_FY_PER`を、7203の実データFundamentals
A-Path(D0075)+ Positioning(D0072)と1つのEvidence Poolへ統合し、
`build_research_artifact()`経由でReal ResearchArtifactを構築、次の
Research Bottleneckを実測した。**新機能は追加していない、Code欠陥も
発見されなかったため無変更(scratch実行のみ、Repo変更なし)。**

### 実行結果(Read-only Scratch Script、既存`scripts/
stage3_1_research_artifact_7203.py --semantics A`と同じLoadingパターン
+ D0077 Valuation Moduleを追加統合、`build_research_artifact()`のみ
使用・`ResearchArtifact(...)`直接構築はしていない)

| Evidence種別 | usable件数 |
|---|---|
| Fundamentals(A系統、MARKET_PUBLIC_AT) | 16 |
| Positioning(price-derived) | 18 |
| Valuation(LATEST_REPORTED_FY_PER) | 1 |
| **Total** | **35** |

`artifact_id=ART_STAGE3_4_7203_20241115_A_VALUATION_V2`(Local
`02_company_research/7203_Toyota_Motor/research_artifacts.jsonl`へ記録
済み、Commit対象外)。`data_confidence=LOW`/`evidence_confidence=
MEDIUM`/`research_confidence=LOW`/`conclusion=INCONCLUSIVE`——Valuation
Evidenceが1件増えたことだけを理由に機械的に引き上げていない(D0075/D0076
と同水準を維持)。

**V1→V2の訂正(Append-Only、V1は削除・上書きせず保持)**: 初回組立てた
`base_case`のNarrative Summaryに「倍率が割安/割高かは...判断しない」
という否定文を書いたが、たとえ否定形でも§4で明示的に禁止された語
(割安/割高)がArtifact内に文字列として残ること自体を避けるため、
「その水準についての方向性のある判断はしない」という言い換えへ訂正した
`ART_STAGE3_4_7203_20241115_A_VALUATION_V2`(`supersedes_artifact_id=
ART_STAGE3_4_7203_20241115_A_VALUATION_V1`)を新規記録した。V1は
Registryに残したまま(Append-Only、元Artifactを削除・上書きしない
という要件どおり)。V2のArtifact全体を機械的にScanし、禁止語(Cheap/
Expensive/Undervalued/Overvalued/Attractive/Bullish/Bearish/BUY/SELL/
target price/割安/割高/買い/売り/魅力的/目標株価)が0件であることを
確認した。

### Valuation Interpretation Boundary(§4の実装確認)

`LATEST_REPORTED_FY_PER=7.2853`(≈7.29x)は`SUPPORTED_BY_DATA`として
Base Caseへ含めたが、これが高いか低いかの判断(Interpretation)は
Peer/Historical Baselineが無いため`UNAVAILABLE`のまま分離して保持した
(Bull/Bear Caseへ倍率単独を理由に追加していない)。

### Research Usefulness Re-evaluation(実Evidenceに基づく分類)

| 項目 | 分類 | 根拠 |
|---|---|---|
| Business / Earnings | SUPPORTED_BY_DATA | sales/operating_profit/net_profit/eps/ordinary_profitのACTUAL実績値(1Q/2Q/3Q/FY、16 series)を確認 |
| Growth | PARTIAL | 複数期間の実績値はあるが、D0076で既出のとおり選定された4期が異なる会計年度(2024/3期3Q・FYと2025/3期1Q・2Q)の累計値混在であり、YoY成長率の計算Logic自体が未実装(値の推測補完はしていない) |
| Financial Quality | UNAVAILABLE | **今回実測**: Raw Local Snapshot(`financial_summary_7203.json`)にはBPS/ROE/TA(総資産)/Eq(純資産)/EqAR/CFO/CFI/CFF等のField自体は存在するが、`lib.fundamentals.normalize.parse_financial_summary_payload()`はP&L項目(sales/operating_profit/net_profit/eps/ordinary_profit)とそのCompany Forecastのみを`FundamentalMetric`化しており、これらはParse対象外(実Parser Capability Gap、単なるRaw Data不足ではない) |
| Guidance | PARTIAL | **今回実測**: Company Forecast(`sales_current_year_forecast`/`operating_profit_current_year_forecast`/`net_profit_current_year_forecast`/`eps_current_year_forecast`とその`next_year_forecast`版、`ActualOrForecast.COMPANY_FORECAST`で正しくLabel付け済み)は既に`parse_financial_summary_payload()`でParse済みだが、今回のKey Metric Set(Scope選択)には含めなかった。新規Parsing Codeは不要、Evidence Pool Scopeへの追加のみで済む |
| Valuation Multiple | SUPPORTED_BY_DATA | D0077 `LATEST_REPORTED_FY_PER`=7.2853 |
| Valuation Interpretation | UNAVAILABLE | Peer/Historical Baseline無し(上記参照) |
| Catalysts | OUT_OF_SCOPE | News/Disclosure Document Capabilityは`DEFAULT_ALLOWED_CAPABILITIES`に含まれず、7203向けの実Disclosure Documentも未取得 |
| Risks | UNAVAILABLE | 同上(Disclosure Document Content未取得) |
| Expectations / Priced-in(Consensus) | OUT_OF_SCOPE | Consensus/Analyst Estimates Adapter未実装(Phase5 v1 Scope外、既定で不使用) |

### Key Measurement: 次のResearch Quality制限要因

「実装が簡単だから」ではなく実Evidenceから判断した結果:

**最大のBottleneck = Valuation Interpretation(比較基準の不在)**。
D0077でValuation Multiple自体はSUPPORTED_BY_DATAになったが、その直後に
「高いか低いか判断できない」という壁に直接ぶつかった(今回のRoundで
実際に観測した制約)。このうち:

- **Historical Valuation Context(自社の過去Multiple推移)**: 既存
  `01_data/raw/local_snapshot_input/`(7203の2024年通期Bar・20件の
  開示)だけで、複数のas_of時点について既存`build_latest_reported_fy_
  per()`をそのまま繰り返し適用すれば計算できる(新規Provider・新規
  Parsing不要、Orchestrationのみ追加)——最もTractableな解消経路。
- **Peer Valuation Context**: Local Snapshotには他に6758/8056/3626の
  実データも存在するが、これらが7203と同業種の意味あるPeerかは未検証
  (`equities_master.json`のSector情報を今回確認していない)。Data存在
  ≠ 意味のあるPeer Setであるため、今回は弱いCandidateとして扱う。
- **Consensus/Analyst Expectations**: 完全に未取得、新規Provider統合
  相当(最も大きいGap、今回のScope外)。

### 副次的発見(今回実測、次Roundへの参考)

- **Guidance**: Data自体は既にParse済み・Label付け済み(新規Parsing
  Code不要)。Financial Qualityとは異なる種類のGapである(Wiring Gap
  であり、Parser Capability Gapではない)。
- **Financial Quality**: Raw Fieldは存在するが未Parseの実Parser
  Capability Gap(新しいField Mappingが必要、Guidanceより一段重い作業)。

この区別自体が今回のMeasurementの主要な成果の一つ。

### What Improved From D0076

D0076時点では「生Close PriceとFY実績EPSはほぼ手元にあるのに、Evidence
化されていないために計算できない」ことが唯一の明示Gapだった。D0077で
そのGapを解消し、本Round(D0078)で実際にResearchArtifactへ統合・実測
した結果、Evidence件数はFundamentals16+Positioning18のみ(D0076時点の
34件)からValuation1件を加えた35件へ増加。Confidence/Conclusionは意図
的に据え置き(INCONCLUSIVE/LOW、Evidence 1件増加だけを理由に昇格しない)。

### Good Company != Good Stock Check

Business/Earnings Fact(実績P&L)とValuation Fact(倍率そのもの)を
両方Evidence Poolへ含めたが、Bull/Base/Bear Caseのいずれにも「良い
企業」「良い株」の判断や、投資期待Returnについての言及を含めていない
ことを確認した(NarrativeはFactの列挙のみ、方向性のある結論を導いて
いない)。

### Code Change Policy(遵守確認)

Production Code変更なし。Read-only Scratch Scriptによる統合Acceptance
のみ(Repo外Scratchpadで実行、Repoへは追加していない)。実行上の
Semantic Defectは発見されなかった(「新しいResearch項目が足りない」は
Code Defectとして扱っていない、§10どおり)。

### Verification

Code変更が無いため、Targeted Smokeのみ実施
(`test_valuation_latest_reported_fy_per.py`13/13 PASS)。Full
Regression・`ruff`/`mypy`は本Roundでは再実行していない(Code変更無し、
D0071/D0074/D0076と同じ判断基準)。既知のWindows Hook/mypy Environment
Issueは本Roundでも未修正。H0001 Locked Testは実行していない。

### Persistence / Commit対象

Runtime ResearchArtifact(3件目、V1+V2両方)はLocal保持のまま
(`02_company_research/7203_Toyota_Motor/research_artifacts.jsonl`、
Commit対象外・既存2件は無変更)。Raw Snapshotも無変更・Commit対象外。
本RoundでCommitするのはこのDECISIONS.md追記(Doc-only)のみ。

### Do Not(§遵守確認)

Forward PER・PBR・Expectations Engineのいずれにも着手していない。
H0001 Locked Testの再実行もしていない。

## D0079 — Stage 3.5: Historical Valuation Context Real-Data Acceptance(D0078最大Bottleneckの検証、Measurement Only・Code変更なし)

D0078で確認された最大のResearch Bottleneck「Valuation Interpretation(比較
基準の不在)」について、既存7203 Local Snapshot(Price + Fundamentals)だけを
使い、D0077 `build_latest_reported_fy_per()`を2024年の複数PIT時点へ繰り返し
適用してHistorical Valuation Contextを構築できるかを実測した。新規Metric定義・
新規Provider・新規Parsingはいずれも追加していない(Read-only Scratch Script、
Repoへは未追加)。

### 実行方法

`scripts/stage3_1_research_artifact_7203.py`と同じLocal Snapshot Loading
パターンを再利用。2024年の各月について、実データのSession Date集合から
機械的に月末最終取引Sessionを選び(手書き日付なし)、`market_calendar.
session_close_at()`(ハードコードした15:00/15:30ではなく、2024-11-05の
取引時間延長制度変更を自動反映する既存関数)でas_ofを構築。各as_ofについて
`fundamentals_as_of(availability_semantics=MARKET_PUBLIC_AT)`でFY実績・連結
EPS Series(`series_id=7203|eps|CURRENT_FISCAL_YEAR|FY|CONSOLIDATED|IFRS`、
今回実測で確認: 7203はこのSeries以外にIFRS以外のFY実績連結EPS Seriesを持たず、
単一Series)を選定し、対応するMetric/Envelopeを取得した上で
`build_latest_reported_fy_per()`をそのまま呼び出した。Corporate Action Guard
用のPrice Payloadは、最古のGuard Window開始点(2023-03-31、Jan〜Apr 2024
AnchorのFY実績EPS基準期)をカバーするため2023-01-01〜2024-12-31を取得した。

### 実行結果(実データ、7203)

```
ANCHORS_ATTEMPTED=12
VALID_OBSERVATIONS=12
UNAVAILABLE_OBSERVATIONS=0
```

| as_of(月末Session Close) | price_date | price | FY実績EPS(連結) | EPS公表日 | PER |
|---|---|---|---|---|---|
| 2024-01-31 15:00 | 2024-01-31 | 3000.0 | 179.47(FY2023/3) | 2023-05-10 | 16.7159 |
| 2024-02-29 15:00 | 2024-02-29 | 3621.0 | 179.47(FY2023/3) | 2023-05-10 | 20.1761 |
| 2024-03-29 15:00 | 2024-03-29 | 3792.0 | 179.47(FY2023/3) | 2023-05-10 | 21.1289 |
| 2024-04-30 15:00 | 2024-04-30 | 3638.0 | 179.47(FY2023/3) | 2023-05-10 | 20.2708 |
| 2024-05-31 15:00 | 2024-05-31 | 3401.0 | 365.94(FY2024/3) | 2024-05-08 | 9.2939 |
| 2024-06-28 15:00 | 2024-06-28 | 3290.0 | 365.94(FY2024/3) | 2024-05-08 | 8.9905 |
| 2024-07-31 15:00 | 2024-07-31 | 2949.0 | 365.94(FY2024/3) | 2024-05-08 | 8.0587 |
| 2024-08-30 15:00 | 2024-08-30 | 2759.5 | 365.94(FY2024/3) | 2024-05-08 | 7.5409 |
| 2024-09-30 15:00 | 2024-09-30 | 2542.5 | 365.94(FY2024/3) | 2024-05-08 | 6.9479 |
| 2024-10-31 15:00 | 2024-10-31 | 2682.5 | 365.94(FY2024/3) | 2024-05-08 | 7.3304 |
| 2024-11-29 15:30 | 2024-11-29 | 2551.5 | 365.94(FY2024/3) | 2024-05-08 | 6.9725 |
| 2024-12-30 15:30 | 2024-12-30 | 3146.0 | 365.94(FY2024/3) | 2024-05-08 | 8.5970 |

`as_of`のTime部分が2024-11-05以降で自動的に15:00→15:30へ切り替わっている
ことを確認した(`session_close_at()`が制度変更を正しく反映、手書きTimeは
使っていない)。

Current Reference(D0077/D0078と同一as_of=2024-11-15 15:00 JST): `PER=
7.2853`(≈7.29x、D0077/D0078と完全一致、再計算しても同一値)。

統計(Valid 12点のみ):

```
HISTORICAL_MIN=6.9479
HISTORICAL_MEDIAN=8.7938
HISTORICAL_MAX=21.1289
CURRENT_PERCENTILE=16.7 (n=12、Current以下のHistorical Monthly Point割合)
```

「割安/割高」等の方向性判断はしていない。Percentileは12点のうち何点が
Current値以下かを示すFactとしてのみ記録する。

### PIT安全性 / Corporate Action

全12 Anchorで`published_at <= as_of`(Future Disclosure Leakage無し)、
`price session_close_at <= as_of`を満たすPrice Barのみ選定。Corporate Action
Guard(`detect_corporate_action_events_from_equity_bars()`、2023-01-01〜
2024-12-31のPrice Payload全体をScan)はEvent検出0件(D0077の2024単年結果と
一致)。全12 AnchorでGuardによる除外は発生していない
(`UNAVAILABLE_OBSERVATIONS=0`)。EPS Denominator選定は全期間`accounting_
standard=IFRS`で一貫しており、会計基準変更によるSeries分裂は発生していない
(実測で確認)。

### Sample Sufficiency(§8の実装確認)

**12点を「長期Historical Valuation」と誇張しない。** 今回のLocal Snapshotの
Price Bar Coverageは実測の結果`2024-01-04〜2024-12-30`(245 Session)のみで
あり、**2024年が取得可能な唯一の年**(2024年より前のPrice Barはこの
Local Snapshotに存在しない)。したがって2024年を超えてAnchorを増やすことは
今回のLocal Snapshotのままでは不可能(新規Fetchが必要、今回はScope外)。

さらに、12点のうちFY実績EPS Denominatorは実質2種類(Jan〜Apr: FY2023/3実績
179.47、May〜Dec: FY2024/3実績365.94)にしか分かれない。したがって12点は
独立した12個のValuation Regimeではなく、「1年間のPrice変動 × 2つの開示
Denominator」という限定的な構造を持つ。この点を明示せずに「12点のHistorical
Range」とだけ報告すると実態より豊富に見える誤解を招くため、明記する。

**HISTORICAL_CONTEXT_STATUS = HISTORICAL_CONTEXT_PARTIAL**(SUPPORTEDではなく
PARTIAL): 実データからPIT安全に計算できた点自体はUNAVAILABLE 0件で完全に
成功したが、Windowが単年かつDenominator Regimeが実質2種類のみのため、
Confidenceを機械的にSUPPORTEDへ引き上げない。

### Peer Valuationの実行可能性(D0078の"弱いCandidate"を実測で検証)

D0078では「Local Snapshotに他に6758/8056/3626が存在するが、7203と同業種の
意味あるPeerかは未検証」と留保していた。今回`01_data/raw/local_snapshot_
input/equities_master.json`のSector Code(S17=17-Sector、S33=33-Sector)を
実データで確認した結果:

| Code | S17 | S33 |
|---|---|---|
| 7203(トヨタ自動車) | 6 | 3700 |
| 6758 | 9 | 3650 |
| 8056 | 10 | 5250 |
| 3626 | 10 | 5250 |

**7203と同一S17/S33を持つ銘柄は残り3件中0件**(全て異なるSector)。したがって
既存Local SnapshotだけではPeer Valuationは構築できないことを実測で確定した
(D0078時点の「未検証の弱いCandidate」を「検証済みかつ現状データでは不成立」
へ更新)。新しいPeer Universe取得は新規Provider/新規Fetch相当のためScope外。

### ResearchArtifact統合(§9の判断)

今回はMeasurementのみ。既存`ART_STAGE3_4_7203_20241115_A_VALUATION_V2`への
Historical Context統合は行っていない。Historical Contextを再利用可能な
Evidence/Derived Factとして正式導入する場合、最小実装候補は「複数as_ofに
対する`build_latest_reported_fy_per()`のOrchestration Wrapper + 統計Summary
のEvidence化」であり、新しいCore Metric定義・新しいCorporate Action Logicは
不要と判断できる(が、本Roundでは実装しない、§9の指示通り)。

### 次のResearch Bottleneck再評価(実測に基づく)

D0078の3候補のうち2つが今回のRoundで実測により評価が変わった:

- **Longer Historical Valuation History**: 実測の結果、既存Local Snapshotの
  Price Coverageが2024年単年のみであることが判明し、**現状データでは拡張
  不可**(新規Fetch必須、今回Scope外)。D0078時点で最もTractableと見積もって
  いたが、実際には既存データの限界に即座に到達した。
- **Peer Valuation Context**: 上記の通りSector Code実測により**既存4銘柄では
  0/3が同業種、構築不可**と確定。
- **Consensus/Analyst Expectations**: 未着手(既存判断を維持、最大の新規実装
  Gap)。

したがって、既存Local Snapshotの範囲内で新規Provider無しに前進可能な
Research項目は、D0078で副次的に確認された次の2つに絞られる:

| 項目 | 種別 | 今回の判断 |
|---|---|---|
| Financial Quality(BPS/ROE/TA/Eq/CFO/CFI/CFF) | Parser Capability Gap(Raw Fieldは存在、未Parse) | **次点候補として推奨** |
| Guidance(Company Forecast) | Wiring Gap(Parse済み、Evidence Pool Scope未追加) | 実装コストは最小だが、Valuation Interpretation自体への寄与は間接的 |

**推奨: Financial Quality**。Historical/Peerの両方の比較基準構築が今回の
実測で行き止まりになったため、「Valuation Multiple単体をどう解釈するか」
という問いには、比較基準ではなく企業の財務健全性という別軸(高いか低いかの
判断ではなく、低い倍率が財務的な脆弱性の反映なのか単なる市場評価のズレ
なのかを区別する材料)からアプローチする以外に、既存Local Snapshotで
Tractableな経路が残っていない。実装が最小だからではなく、Historical/Peer
両方が実測でDead Endになったという消去法の結果として選定した。

### Code Change Policy(§13遵守確認)

Production Code変更なし。Read-only Scratch Script
(`stage3_5_historical_valuation_context_7203.py`、Repo外Scratchpadで実行、
Repoへは追加していない)による測定のみ。「2024年より前のPrice Barが無い」
「Peer候補3件が0/3で同業種不一致」はいずれもCode Defectではなくデータの
限界として記録する(§13どおり)。

### Verification

Code変更が無いため、Targeted Smokeのみ実施
(`test_valuation_latest_reported_fy_per.py`13/13 PASS)。Full Regression・
`ruff`/`mypy`は本Roundでは再実行していない(既存判断基準を継続)。H0001
Locked Testは実行していない。

### Persistence / Commit対象

`02_company_research/7203_Toyota_Motor/`・Raw Snapshotはいずれも今回無変更・
Commit対象外。Historical Context Scratch Outputも長期保存Policy未決定のため
Repoへコミットしない(Repo外Scratchpadに保持)。本RoundでCommitするのは
このDECISIONS.md追記(Doc-only)のみ。

### Do Not(§遵守確認)

Forward PER・PBR・Peer Selection・Consensus・Expectations Engine・DCF・
target price・BUY/SELL・Decision Engine・Portfolio Engine・新規Providerの
いずれにも着手していない。D0057 General Fix・H0001 Locked Testの再実行も
していない。

## D0080 — Stage 3.6: Cash Flow Financial Quality v1(CFO/CFI/CFFのみ、Codex Financial Quality Readiness AuditでREADY_WITH_GUARDSと判定された最小Slice)

D0079後のFinancial Quality Readiness Auditで示された最小Slice(CFO/CFI/CFF)
のみを既存Fundamentals A-Pathへ追加した。TA/Eq/ShEq/EqAR/BPS/ROE(Stock/
Point-in-Time系指標)は`PeriodBasis.POINT_IN_TIME`が未実装のため今回は
追加しない(意味論上のGapを埋めずに追加すると誤った累計/時点の混同を招く)。

### Metric定義(§1-3)

3つのみ追加: `cash_flow_from_operations`(CFO)・`cash_flow_from_investing`
(CFI)・`cash_flow_from_financing`(CFF)。いずれも`ActualOrForecast.ACTUAL`・
`FiscalYearTarget.CURRENT_FISCAL_YEAR`・`ConsolidationScope.CONSOLIDATED`・
`PeriodBasis.CUMULATIVE`(既存Sales/OP/NP等と同じ累計Flow、2Q値を2Q単独へ
Derivationしない)。`lib/fundamentals/normalize.py`の`_METRIC_FIELD_MAP`へ
3エントリ追加のみ(既存Mapping・既存Metric Type名との衝突無し)。

**実データで確認**: 7203 Local Snapshot(全20件のDisclosure)全件でCFO/CFI/
CFFフィールドが実在し、`CurPerSt`が常にFY開始日(1Q/2Q/3Qいずれも)である
ことを実測で確認した(2Qの`CurPerSt`が2024-04-01であり、Q2単独開始日
2024-07-01ではないことをTestで明示的に確認、2Q値をQ2 standalone値と誤解釈
しないことの裏付け)。CFIは全期間で負値、CFFは正負混在(実データで負値・
0の双方が有効なDecimalとして扱われることを確認)。

### Evidence Converter(§4-6)

既存`source_version_to_evidence_market_public_at()`(P&L用、`SourceVersion`
のみを引数に取り、series_id文字列以外にperiod_start/period_endを保持
しない)は変更していない。新規`financial_quality_metric_to_evidence_
market_public_at()`(`lib/fundamentals/evidence.py`)を追加し、`SourceVersion`
に加えて対応する`FundamentalMetric`/`DisclosureEnvelope`を受け取ることで、
`content`へperiod_start/period_end/period_type/period_basis/
consolidation_scope/accounting_standardを型付きFieldから直接埋め込む
(series_id文字列のfree-form parseはしていない)。`source_type=
MARKET_PUBLIC_AT_SOURCE_TYPE`・`available_at=version.published_at`は
既存A系統と完全に同一のPIT Semanticsを再利用しており、`build_research_
artifact()`のA/B混在Guard(`source.source_type`ベース)をそのまま通過する
ことをTestで確認した。Unit/Currencyは`FundamentalMetric.currency`/`.unit`
が確認できない限り`UNIT_STATUS_UNVERIFIED`("UNVERIFIED"、"JPY"/"yen"/"円"
等の推測は一切していない)。Defense-in-depthとして`metric.metric_id !=
version.source_version_id`・`metric.envelope_id != envelope.envelope_id`
はfail closedで`ValueError`にする(既存`build_latest_reported_fy_per()`と
同じ設計方針)。

### Interpretation Boundary(§7の実装確認)

Evidence Contentは常に「CFO=Xとして開示された」というFACT文言のみで、
「healthy」「strong」「良い」「健全」等の解釈語は一切含めていない(禁止語
Scanで確認)。符号(正負)自体は単なるDecimal値として保持するのみで、
これ単体からResearch Conclusionを導いていない。

### 実データ受け入れ(§10、7203、as_of=2024-11-15 15:00 JST)

`fundamentals_as_of(availability_semantics=MARKET_PUBLIC_AT)`でas_of時点の
最新CFO/CFI/CFFを確認(hard-code無し、Local Snapshotから読み取り):

| metric | value | period_start | period_end | published_at |
|---|---|---|---|---|
| cash_flow_from_operations | 1817177000000 | 2024-04-01 | 2024-09-30 | 2024-11-06 13:55 JST |
| cash_flow_from_investing | -3085752000000 | 2024-04-01 | 2024-09-30 | 2024-11-06 13:55 JST |
| cash_flow_from_financing | -289752000000 | 2024-04-01 | 2024-09-30 | 2024-11-06 13:55 JST |

想定通り、2024-11-06公表のFY2025 2Q Disclosureがas_of時点で利用可能な最新
2Q累計Cash Flowとして選定された。

### Stage 3.1/ResearchArtifact統合実測(§11、Read-only Scratch、Repo未追加)

A系統Key Metric SetへCFO/CFI/CFFを追加し(既存P&L 5 Metric Typeは無変更)、
`build_research_artifact()`経由で実測:

| 項目 | 件数 |
|---|---|
| Fundamentals series評価対象(P&L 16 + Cash Flow 12) | 28 |
| Fundamentals A系統Evidence usable | 28 |
| うちCash Flow(CFO/CFI/CFF、1Q/2Q/3Q/FY各1件ずつ選定) | 12 |
| Positioning usable | 18 |
| **Total Artifact Evidence** | **46** |

Cash Flowが12件なのは、既存P&L Metric(Sales/OP等)と同じく、A系統が
period_type(1Q/2Q/3Q/FY)ごとに独立したSeriesとしてas_of時点の最新値を
選定する既存挙動(D0075)をそのまま踏襲した結果であり、CFO/CFI/CFFの
3 Metric × 4 Period Type = 12(新しいSelection Logicは追加していない)。
既存P&L 16件は無変更。Valuation Evidence(D0077)は今回のScratch Scriptへは
含めていない(Scope外、Cash Flow単体の測定に限定)。

### Financial Quality再評価(§12)

**Cash Flow Coverage = SUPPORTED_BY_DATA**(CFO/CFI/CFFがas_of時点で
PIT安全に取得できることを実データで確認)。ただし**Overall Financial
Quality = PARTIAL**(Balance Sheet/ROE/BPS等のStock系指標は未実装のため、
Cash Flowの符号だけで企業のFinancial Qualityを「良い/悪い」と判断しない、
今回もそのような判断は一切していない)。

### Source Vintage / Confidence(§16)

D0075 Source Vintage Guard(UNVERIFIED)を継続。Cash Flow Evidence追加を
理由に`data_confidence`/`research_confidence`を自動昇格しない。

### Do Not(§13遵守確認)

`PeriodBasis.POINT_IN_TIME`・TA・Eq・ShEq・EqAR・BPS・ROE・Forward PER・
PBR・Peer・Historical Valuation extension・Guidance wiring・Consensus・
Expectations・News・Disclosure・Decision Engine・Portfolio Engine・D0057
General Fix・新規Provider・H0001 Locked Testのいずれにも着手していない。

### Tests(§14)

新規: `13_tests/test_fundamentals_financial_quality_evidence.py`(9件)、
`13_tests/test_fundamentals_normalize.py`へCash Flow専用13件追加、
`13_tests/test_research_artifact.py`へA/B混在Guard確認2件追加(計24件
新規)。Fixture(`financial_summary_v2.json`)は既存行へCFO/CFI/CFF追加+
1Q/2Q(FY開始日基準のPeriod境界確認用)2行追加(既存行は削除・変更なし)。

### Verification(§15)

- Syntax/Compile: 全対象ファイルOK(`ast.parse`)。
- Targeted(新規24件): 全PASS。
- Relevant(`-k "fundamental or research_artifact or catalog or
  evidence"`): 319/319 PASS。
- Full Regression(`13_tests/`): 1042/1043 PASS。唯一の失敗は
  `test_protected_path_hook.py::test_hook_warns_on_protected_screening_
  tool_paths`で、D0074/D0075/D0077と同一の既知Windows Hook Environment
  Issue(今回のScopeと無関係、修正していない)。
- `ruff check`: 対象ファイル全てPASS。
- `ruff format --check`: 初回2ファイルで長い行/未整形を検出、`ruff format`
  で整形して解消(内容の変更なし)。
- `mypy`(`lib/fundamentals/normalize.py`・`lib/fundamentals/evidence.py`):
  Success、0 issues。Test File側はD0077と同一の既知Windows/numpy/Python
  3.14 Environment Issue(`numpy/__init__.pyi`のPython 3.12+専用構文)が
  Pristine HEADの既存Testファイルでも再現するため`QUALITY_GATE_ENV_
  BLOCKED`として記録、修正していない。H0001 Locked Testは実行していない。

### Persistence / Commit対象(§18)

`lib/fundamentals/normalize.py`・`lib/fundamentals/evidence.py`・
`13_tests/test_fundamentals_normalize.py`(既存へ追記)・
`13_tests/test_fundamentals_financial_quality_evidence.py`(新規)・
`13_tests/test_research_artifact.py`(既存へ追記)・
`13_tests/fixtures/financial_summary_v2.json`(既存へ追記)・このDECISIONS.md
追記をCommit対象とする。Raw Snapshot・`02_company_research/7203_Toyota_
Motor/`(今回無変更)はいずれもCommit対象外。Historical Valuation Context
関連(D0079)は今回のScope外、無変更。

## D0081 — Stage 3.7: Balance Sheet Point-in-Time v1(TA/ShEq/EqARのみ、Codex Stock Metric / Point-in-Time Semantics AuditでREADY_WITH_GUARDSと判定された最小Set)

D0080 Cash Flow Financial Quality v1の次Sliceとして、Balance Sheet系Fact
(TA/ShEq/EqAR)をPIT-safeに追加した。BPS/Eq/ROE/PBRは実装していない。

### Architecture Decision(§1)

`lib/fundamentals/model.py`の`PeriodBasis`へ`POINT_IN_TIME = "POINT_IN_TIME"`
を追加した(既存`CUMULATIVE`/`STANDALONE`の値は無変更、`{member.value for
member in PeriodBasis} == {"CUMULATIVE", "STANDALONE", "POINT_IN_TIME"}`を
Testで確認)。新しい`MetricNature` enum等は作っていない。

### Explicit PeriodBasis Mapping(§2)

`_METRIC_FIELD_MAP`の型を`tuple[str, ActualOrForecast, FiscalYearTarget,
ConsolidationScope]`から`tuple[str, ActualOrForecast, FiscalYearTarget,
ConsolidationScope, PeriodBasis]`へ変更し、全23エントリ(既存20 + 新規3)が
PeriodBasisを明示するようにした。Normalizer末尾の暗黙`period_basis=
PeriodBasis.CUMULATIVE`一律設定は廃止し、各Descriptorの値をそのまま使う
方式へ変更した。既存P&L/EPS/Forecast/Cash Flow(20エントリ)は意味を
再設計せず、全て明示的に`CUMULATIVE`を指定(既存挙動を完全維持)。新規
Stock Metric(3エントリ)のみ`POINT_IN_TIME`。`_METRIC_FIELD_MAP`の全
Descriptorが5要素Tupleであることを構造Testで確認した(暗黙defaultが
残っていないことの確認)。

### Metric追加(§3-4)

3つのみ: `total_assets`(TA)・`provider_reported_sheq`(ShEq)・
`provider_reported_eqar`(EqAR)。ShEq/EqARの正式Provider長名称が未確認の
ため、`provider_reported_`接頭辞で意味を過剰確定しない中立的な名称を採用
(`shareholders_equity`等の確定的な名称は使わない)。Raw Payloadに別Field
`Eq`が実在し値がShEqと異なることを実データで確認したため、統合していない。
全て`ActualOrForecast.ACTUAL`・`FiscalYearTarget.CURRENT_FISCAL_YEAR`・
`ConsolidationScope.CONSOLIDATED`・`PeriodBasis.POINT_IN_TIME`。

### Stock Period Semantics(§5)

Stock MetricのPeriodType(1Q/2Q/3Q/FY)は「どのDisclosure cadenceで報告
されたSnapshotか」を表すのみで、その期間を累積した値という意味ではない
ことをTestで明示的に確認した(`current_period_start`を値の期間開始として
扱わない)。

### Evidence Converter(§6-7)

D0080の`financial_quality_metric_to_evidence_market_public_at()`を再利用し、
`metric.period_basis`でTyped Branchするよう拡張した:
`CUMULATIVE`(Cash Flow等)は`period=start..end`を含む既存Content書式を
Byte-Equivalentに維持(既存`test_fundamentals_financial_quality_evidence.py`
のCash Flow系Testが無変更でPASSすることを確認)。`POINT_IN_TIME`(Stock)は
`period_start`を表示せず、代わりに`value_date=current_period_end`を明示。
それ以外の`PeriodBasis`(将来の`STANDALONE`等)は暗黙のContent生成をせず
`ValueError`でfail closed(Test確認済み)。Unit/Currencyは引き続き
`UNIT_STATUS_UNVERIFIED`("JPY"/"yen"/"円"の推測は一切していない)。

### TA/ShEq/EqAR(§8-10)

いずれもProvider供給のRaw Fieldをそのまま使い、Labで再計算・上書きしない。
実データ(7203、全20件のDisclosure)でTA/ShEq/EqARが全件に実在すること、
`EqAR ≈ ShEq/TA`が丸め誤差0.001未満で整合すること(2024-11-06 2Q:
34368513000000/89169296000000≈0.3855 vs Provider EqAR=0.385)を確認した
うえで、Provider供給のEqAR自体(raw_value="0.385")がそのままMetric.valueと
して保持され、ShEq/TAの計算結果で上書きされていないことをTestで確認した
(Validation目的の確認に限定、Primary ValueはRaw provider EqAR)。0.385は
Percentage表示("38.5%")等へ変換せず、Raw Decimal Representationのまま
保持している。

### 実データ受け入れ(§13、7203、as_of=2024-11-15 15:00 JST)

`fundamentals_as_of(availability_semantics=MARKET_PUBLIC_AT)`でas_of時点の
最新TA/ShEq/EqAR(2Q cadence)を確認(hard-code無し、Local Snapshotから
読み取り):

| metric | source_field | value | value_date | period_type | published_at |
|---|---|---|---|---|---|
| total_assets | TA | 89169296000000 | 2024-09-30 | 2Q | 2024-11-06 13:55 JST |
| provider_reported_sheq | ShEq | 34368513000000 | 2024-09-30 | 2Q | 2024-11-06 13:55 JST |
| provider_reported_eqar | EqAR | 0.385 | 2024-09-30 | 2Q | 2024-11-06 13:55 JST |

想定通り、2024-11-06公表のFY2025 2Q Disclosureがas_of時点で利用可能な最新
2Q Balance Sheet Snapshotとして選定された。

### 異なるPeriodTypeのSnapshot共存(§12)

TA/ShEq/EqARそれぞれについて、1Q/2Q/3Q/FYのas-of-latest Evidenceが同時に
存在することを実測で確認した(1Q=2024-06-30、2Q=2024-09-30、3Q=
2023-12-31[まだFY2025 3Qが未開示のため]、FY=2024-03-31)。これはPIT Leak
ではなく既存Series Key(PeriodType込み)の設計どおりの挙動。`max(value_date)
=2024-09-30`が現在の最新Snapshotであることをmeasurementとして報告したのみ
で、新しい「最新Balance Sheet Selector」はProductionへ追加していない。

### Stage 3.1/ResearchArtifact統合実測(§14、Read-only Scratch、Repo未追加)

A系統Key Metric SetへTA/ShEq/EqARを追加し(既存P&L/Cash Flow Evidenceは
無変更)、`build_research_artifact()`経由で実測:

| 項目 | 件数 |
|---|---|
| Fundamentals series評価対象(P&L 16 + Cash Flow 12 + Balance Sheet 12) | 40 |
| Fundamentals A系統Evidence usable | 40 |
| うちCash Flow(D0080から無変更) | 12 |
| うちBalance Sheet(TA/ShEq/EqAR、1Q/2Q/3Q/FY各1件ずつ) | 12 |
| Positioning usable | 18 |
| **Total Artifact Evidence** | **58** |

### Financial Quality再評価(§15)

**Cash Flow Coverage = SUPPORTED_BY_DATA**(D0080から変わらず)。
**Balance Sheet Coverage = SUPPORTED_BY_DATA**(TA/ShEq/EqARがas_of時点で
PIT安全に取得できることを実データで確認)。**Overall Financial Quality =
PARTIAL**(BPS/ROE/PBR/Debt Metrics等の派生比率が未実装のため。TA/ShEq/
EqARの値だけから健全性・危険性の判断はしていない)。

### Interpretation Boundary(§16)

Evidence Content・DECISIONS本文いずれにも「healthy/unhealthy/strong/weak/
safe/risky/good/bad/健全/脆弱/安全/危険/良い/悪い/undervalued/overvalued/
cheap/expensive/割安/割高」等の解釈語を含めていない(禁止語Scanで確認)。

### Do Not(§20遵守確認)

BPS・Eq・ROE・PBR・Forward PER・Guidance wiring・Consensus・
Expectations・Peer・新規Historical Fetch・新規Provider・`MetricNature`
enum・Latest Balance Sheet Engine・Decision Engine・Portfolio Engine・
D0057 General Fix・H0001 Locked Testのいずれにも着手していない。

### Migration / Regression Safety(§19)

`lib/`全体を`grep`し、`PeriodBasis`を参照する箇所が`lib/fundamentals/
model.py`/`lib/fundamentals/normalize.py`以外に存在しない(Exhaustive
Match/Set Check相当のコードが無い)ことを確認したうえでEnum追加を行った。
既存`CUMULATIVE`/`STANDALONE`のTest・値は全てPASSしたまま。

### Tests(§17-18)

新規/置換: `test_fundamentals_model.py`へPeriodBasis後方互換Test2件、
`test_fundamentals_normalize.py`の旧`test_period_basis_is_always_
cumulative_never_derived_standalone`を「Flow=CUMULATIVE/Stock=
POINT_IN_TIME/STANDALONE自動生成なし」の3Test+構造Test1件へ置換し、
Stock Metric専用Test8件を追加、`test_fundamentals_financial_quality_
evidence.py`へPOINT_IN_TIME系Test7件(Content分岐・Unit/Currency・A-path
Tag・Future Disclosure除外・UNKNOWN published_at拒否・Future Revision
非漏洩・未対応PeriodBasisのFail Closed)を追加、`test_research_artifact.py`
のA/B混在Guard Testを拡張しStock Evidenceも同一Poolへ混在できることを
確認(計41件新規/置換)。Fixture(`financial_summary_v2.json`)は既存行へ
TA/ShEq/EqAR追加(FY/1Q/2Q)+ Zero/Negative値確認用2Field追加(既存Assertion
に影響する変更なし)。

### Verification(§21)

- Syntax/Compile: 全対象ファイルOK。
- Targeted(新規/置換41件): 全PASS。
- Relevant(`-k "fundamental or research_artifact or catalog or
  evidence"`): 339/339 PASS。
- Full Regression(`13_tests/`): 1062/1063 PASS。唯一の失敗は
  `test_protected_path_hook.py::test_hook_warns_on_protected_screening_
  tool_paths`で、D0074/D0075/D0077/D0080と同一の既知Windows Hook
  Environment Issue(今回のScopeと無関係、修正していない)。
- `ruff check`: 対象ファイル全てPASS。
- `ruff format --check`: 対象ファイル全てPASS(追加整形不要)。
- `mypy`(`lib/fundamentals/model.py`・`normalize.py`・`evidence.py`):
  Success、0 issues。Test File側はD0080と同一の既知Windows/numpy/Python
  3.14 Environment Issueが再現するため`QUALITY_GATE_ENV_BLOCKED`として
  記録、修正していない。H0001 Locked Testは実行していない。

### Source Vintage / Confidence(§22)

D0075 Source Vintage Guard(UNVERIFIED)を継続。Balance Sheet Evidence
追加を理由に`data_confidence`/`research_confidence`を自動昇格しない。

### Persistence / Commit対象(§24)

`lib/fundamentals/model.py`・`normalize.py`・`evidence.py`・
`13_tests/test_fundamentals_model.py`・`test_fundamentals_normalize.py`
(既存へ追記)・`test_fundamentals_financial_quality_evidence.py`(既存へ
追記)・`test_research_artifact.py`(既存へ追記)・`13_tests/fixtures/
financial_summary_v2.json`(既存へ追記)・このDECISIONS.md追記をCommit
対象とする。Raw Snapshot・`02_company_research/7203_Toyota_Motor/`(今回
無変更)はいずれもCommit対象外。

## D0082 — Stage 3.8: Financial Quality Integrated Research Acceptance(D0080 Cash Flow + D0081 Balance Sheet + D0077 ValuationをReal ResearchArtifactへ統合、Measurement Only・Code変更なし)

D0080(Cash Flow)とD0081(Balance Sheet)を、既存P&L(D0075)・Positioning・
Valuation(D0077)と1つの実ResearchArtifactへ統合し、次のResearch Quality
Bottleneckを実測した。**新機能は追加していない、Code欠陥も発見されな
かったため無変更(Read-only Scratch Script、Repoへは追加していない)。**

D0081実装ログのDECISIONS.md D0081節をRead-onlyで確認したが、重複段落は
存在しなかった(Edit Tool呼び出し表示上の重複はTool UIの差分プレビューに
起因するもので、実際のCommit済みMarkdownには反映されていなかった)。
Doc-only Cleanupは不要と判断し、何も変更していない。

### 実行結果(7203、as_of=2024-11-15 15:00 JST、既存Local Snapshotのみ)

| Evidence種別 | usable件数 |
|---|---|
| P&L(A系統、sales/OP/NP/EPS等) | 16 |
| Cash Flow(CFO/CFI/CFF、D0080) | 12 |
| Balance Sheet(TA/ShEq/EqAR、D0081) | 12 |
| Positioning(price-derived) | 18 |
| Valuation(LATEST_REPORTED_FY_PER、D0077) | 1 |
| **Total** | **59** |

`artifact_id=ART_STAGE3_8_7203_20241115_A_INTEGRATED_V1`(`build_research_
artifact()`経由、直接構築はしていない、Local登録はしていない)。
`VALUATION_MULTIPLE=7.2853`(D0077/D0078/D0079と完全一致)。
`data_confidence=LOW`/`evidence_confidence=MEDIUM`/`research_confidence=
LOW`/`conclusion=INCONCLUSIVE`(Evidence件数増加を理由に機械的昇格していない)。

### Latest Balance Sheet Snapshot(§5)

`max(value_date)`をMeasurementとして報告: TA/ShEq/EqARのうち最新のvalue_
dateは`2024-09-30`(2Q cadence、published_at=2024-11-06 13:55 JST)。1Q
(2024-06-30)・3Q(2023-12-31、FY2025 3Q未開示のため)・FY(2024-03-31)の
Evidenceも同時に存在するが、いずれも「Current Balance Sheet」と呼んで
いない。新しいSelector EngineはProductionへ追加していない。

### Research Usefulness再評価(実Evidenceに基づく)

| 項目 | 分類 | 根拠 |
|---|---|---|
| Business / Earnings | SUPPORTED_BY_DATA | P&L 16件(sales/OP/NP/EPS等の実績値) |
| Growth | PARTIAL | D0076/D0078から不変(異なる会計年度の累計値混在、YoY計算未実装) |
| Cash Flow Coverage | SUPPORTED_BY_DATA | CFO/CFI/CFF 12件、1Q/2Q/3Q/FY全Cadence確認 |
| Balance Sheet Coverage | SUPPORTED_BY_DATA | TA/ShEq/EqAR 12件、同上 |
| Overall Financial Quality | PARTIAL | BPS/ROE/PBR/Debt Metrics未実装のため、Cash Flow+Balance Sheetが揃っても総合判断はできない |
| Guidance | PARTIAL(不変) | 今回実測: 15series中15件がas_of時点で公表済み(Parser Gapではなく引き続きWiring Gap、Evidence Poolへは今回も追加せず) |
| Valuation Multiple | SUPPORTED_BY_DATA | LATEST_REPORTED_FY_PER=7.2853 |
| Valuation Interpretation | UNAVAILABLE | D0079測定済み: Historical Context=PARTIAL(単年・実質2 Regime)、Peer=構築不可(Sector不一致0/3) |
| Catalysts | OUT_OF_SCOPE | Disclosure Document Capability未取得(DEFAULT_ALLOWED_CAPABILITIES外) |
| Risks | UNAVAILABLE | 同上 |
| Expectations / Priced-in(Consensus) | OUT_OF_SCOPE | Adapter未実装 |

### Financial Quality Boundary(§8遵守確認)

Evidence Content・Narrative・DECISIONS本文いずれにも「healthy/unhealthy/
strong/weak/safe/risky/good/bad/健全/脆弱/安全/危険/良い/悪い/
undervalued/overvalued/cheap/expensive/割安/割高/BUY/SELL」を含めていない
ことを機械的Scanで確認した(EqAR=0.385等のRatio自体はFactとして保持する
のみ)。**このRound中に1件、Narrative草稿に「財務健全性」という表現を
書いてしまい(「健全」を部分文字列として含む)、機械的Scanで検出した。**
D0078のV1→V2訂正(「割安/割高」がたとえ否定文でも文字列として残ること
自体を避ける)と同じ原則に従い、Scratch Script内で「個々の値の大小・
符号だけから、企業や株価の水準についての方向性のある判断はしない」へ
言い換えて再Scanし、0件であることを確認した(この訂正はScratch Script内
のみ、Repoへの影響なし)。

### BPS再評価(§9)

**今回の実測で新たに確認**: `BPS`は`TA`/`ShEq`/`EqAR`と同じくProvider
供給のRaw Fieldとして存在するが、**FY Disclosureでのみ値を持ち、1Q/2Q/3Q
では空文字列**(実データで確認、`ROE`も同じFY限定Pattern)。したがって
BPSを追加しても、as_of=2024-11-15時点で得られる最新値は2024-05-08公表の
FY2024/3実績(半年以上前)に留まり、既存TA/ShEq/EqAR(2024-11-06公表、
2024-09-30時点)より鮮度が劣る。実装自体はTA/ShEq/EqARと完全に同一Pattern
(新規Architecture不要)だが、**Research Quality全体への追加寄与は小さい**
(既にSUPPORTED_BY_DATAのBalance Sheet Coverage軸を補強するのみで、新しい
Research軸を開かない上、鮮度の面ではむしろ既存Evidenceより劣る)。

### Guidance再評価(§10)

D0078の判定(Parser Gapではなく Wiring Gap)を今回Actual Repoで再確認:
`sales_current_year_forecast`/`operating_profit_current_year_forecast`/
`net_profit_current_year_forecast`/`eps_current_year_forecast`(Next-Year
Forecast含む)は評価対象15 series中15件全てがas_of時点で公表済みと確認
できた(直近: 2024-11-06公表のCurrent Year Forecast、Sales=46兆円/OP=
4.3兆円/NP=3.57兆円/EPS=268.77、いずれもLocal Snapshotから読み取り、
hard-code無し)。Guidanceは四半期ごとに更新される(BPS/ROEのFY限定Pattern
とは異なる)。今回もEvidence Poolへは追加していない(§10の指示どおり、
評価のみ)。

### 次のBottleneck判断(§11、実装容易性のみで決めない)

3軸(Research Qualityへの寄与 × 現在のData Surface × Semantic Safety)で
評価:

- **BPS/ROE**: Data Surface即座に利用可能(Architecture上TA/ShEq/EqARと
  同一)だが、既にSUPPORTED_BY_DATAのBalance Sheet軸を補強するのみで
  新しいResearch軸を開かない、かつFY限定Cadenceのため鮮度面で既存
  Evidenceに劣る(今回実測で判明)。
- **Guidance Wiring**: Data Surface即座に利用可能(15/15件確認済み、
  Parser Gapなし)。既存Actual実績とは異なる「会社自身の将来見通し」
  という**新しいResearch軸**を開く。四半期更新のためBPS/ROEより鮮度が
  高い。Semantic Safetyも既存`ActualOrForecast.COMPANY_FORECAST`
  Labelingで担保済み(ルートCLAUDE.md規約1「予想値には必ずラベルと出典日」
  にも合致)。
- **Historical/Peer Valuation拡張**: D0079で既にData Surface側がBlocked
  と確定(Price Snapshotが2024年単年のみ、既存4銘柄はSector不一致)。
  新規Fetch必須のため今回Scope外(§18 Do Not)。
- **Disclosure Content(EDINET/TDnet)**: Catalysts/Risks軸を完全に開く
  大きなResearch Quality寄与があるが、新しいDocument取得経路が必要で
  Wiringより重い実装。
- **Consensus/Expectations**: 最大のGapだが、Expectations Engine相当の
  新規実装が必要(§18 Do Not)。
- **Source Vintage Reliability**: J-Quants公式仕様への疎通不能という
  Session固有の制約(D0043以来継続)によりCode変更では解消できない。

**推奨 = Guidance Wiring**。実装容易性(BPS/Guidanceは同程度に軽い)では
決めず、(1) BPSは既存軸の補強に留まり鮮度面でも劣る、(2) Guidanceは
新しいResearch軸を開き鮮度も高い、という実測結果の差で選定した。

### Good Company != Good Stock Check(§12)

P&L・Cash Flow・Balance Sheet・Valuation Multiple全てが揃っても、Bull/
Base/Bear Caseのいずれにも投資期待Return・BUY/SELL判断は含めていない
ことを確認した(Narrativeは統合されたFactの列挙のみ)。

### Confidence(§13)

Evidence件数が35(D0078)→59(今回)へ増加したが、`data_confidence`/
`research_confidence`は自動昇格していない(LOW据え置き)。Source Vintage
Completenessは引き続きUNVERIFIED。

### Code Change Policy(§14)

Production Code変更なし。Read-only Scratch Script
(`stage3_8_integrated_acceptance_7203.py`、Repo外Scratchpadで実行)による
統合Measurementのみ。実行上のSemantic Defectは発見されなかった。

### Verification(§15)

Code変更が無いため、Targeted Smokeのみ実施: `test_fundamentals_financial_
quality_evidence.py`(16件)・`test_valuation_latest_reported_fy_per.py`
(13件)・`test_research_artifact.py`(24件)、計53件全てPASS。Full
Regression・`ruff`/`mypy`は本Roundでは再実行していない(Code変更無し、
D0071/D0074/D0076/D0078/D0079と同じ判断基準)。H0001 Locked Testは実行
していない。

### Persistence / Commit対象(§16)

Runtime ResearchArtifact(`ART_STAGE3_8_7203_20241115_A_INTEGRATED_V1`)は
Local Registryへ記録していない(Scratch Script内でのMeasurementのみ、
`02_company_research/7203_Toyota_Motor/`は今回無変更)。Raw Snapshotも
無変更。本RoundでCommitするのはこのDECISIONS.md追記(Doc-only)のみ。

### Do Not(§18遵守確認)

BPS実装・ROE・PBR・Guidance実装・Forward PER・Consensus・Expectations
Engine・Peer・新規Historical Fetch・新規Provider・Decision Engine・
Portfolio Engine・D0057 General Fixのいずれにも着手していない。H0001
Locked Testの再実行もしていない。

## D0083 — Stage 3.9: Company Guidance Wiring v1(Current Fiscal Year Company Forecastのみ、D0082で最大の次候補と実測されたGuidance WiringをEvidence Poolへ接続)

D0082で実測された次候補(Guidance Wiring)を最小実装した。既にNormalizer
でParse済みの会社予想Metric(sales/operating_profit/net_profit/eps、
current_year_forecastのみ)を、明示的に`COMPANY_FORECAST`とLabelした
PIT-safe Evidenceとしてはじめて`ResearchArtifact`へ接続した。Next-Year
Forecast・Forward PERはいずれも今回実装していない。

### Critical Forecast Semantics(§2の実装確認)

`lib/fundamentals/evidence.py`へ新規`guidance_metric_to_evidence_market_
public_at()`を追加した。D0080/D0081の`financial_quality_metric_to_
evidence_market_public_at()`はそのまま流用していない(CUMULATIVE Branchの
`period=current_period_start..current_period_end`表示は、Company全体の
FY Forecastを「この開示のCurrent Period(1Q/2Q/3Q等)の予想」であるかの
ように誤表現するため)。新Converterは`forecast_period_start`/
`forecast_period_end`に`envelope.current_fiscal_year_start`/`.
current_fiscal_year_end`のみを使い、`current_period_start`/`.
current_period_end`は一切参照しない。`metric.period_type`(1Q/2Q/3Q/FY)は
`disclosure_period_type`としてのみContentへ含める(Forecast Horizonとして
扱わない)。

### Structural Guards(§5)

Converter自身が以下をfail closedで検証する: `metric.actual_or_forecast !=
ActualOrForecast.COMPANY_FORECAST`(ACTUAL Metricの誤混入防止)、
`metric.fiscal_year_target != FiscalYearTarget.CURRENT_FISCAL_YEAR`
(Next-Year ForecastをSilent Acceptせず`ValueError`、v1はCurrent Yearのみ)、
`metric.metric_id != version.source_version_id`、`metric.envelope_id !=
envelope.envelope_id`(既存Defense-in-depth Pattern)、
`version.published_at is None`。全てTestで確認済み。

### Availability != Forecast Horizon(§7)

`source.available_at`/`published_at`は既存A系統と同じく`version.
published_at`のまま(Forecast Period Endが未来でもEvidenceの利用可能時刻を
未来にしない)。`EvidenceRecord.value_date`は`forecast_period_end`との
整合性がActual Repoで確認できていないため、既定の`None`のままとした
(安易な代入をしない、Testで確認)。

### Unit/Currency(§8)

引き続き`UNIT_STATUS_UNVERIFIED`("JPY"/"yen"/"円"の推測は一切していない)。

### 実データ受け入れ(§12、7203、as_of=2024-11-15 15:00 JST)

`fundamentals_as_of(availability_semantics=MARKET_PUBLIC_AT)`でas_of時点の
最新Current-Year Company Forecastを確認(hard-code無し、Local Snapshotから
読み取り):

| metric_type | source_field | value | forecast_period | disclosure_period_type | published_at |
|---|---|---|---|---|---|
| sales_current_year_forecast | FSales | 46000000000000 | 2024-04-01..2025-03-31 | 2Q | 2024-11-06 13:55 JST |
| operating_profit_current_year_forecast | FOP | 4300000000000 | 2024-04-01..2025-03-31 | 2Q | 2024-11-06 13:55 JST |
| net_profit_current_year_forecast | FNP | 3570000000000 | 2024-04-01..2025-03-31 | 2Q | 2024-11-06 13:55 JST |
| eps_current_year_forecast | FEPS | 268.77 | 2024-04-01..2025-03-31 | 2Q | 2024-11-06 13:55 JST |

D0082測定時の概算値と完全一致した(hard-codeではなくSnapshot読み取りで
再現)。`LATEST_GUIDANCE_PUBLISHED_AT=2024-11-06 13:55 JST`。

**副次的発見(今回実測)**: FY Cadence Disclosure(2024-05-08)では
`current_year_forecast`系Fieldが全て空文字列であり、代わりに`next_year_
forecast`系Field(NxFSales等)にFY2025向けの初回Guidanceが入っていることを
確認した。これは欠陥ではなく、FY実績開示時点では「Current Year」の予想が
既に無意味になる(その期が終わったばかりのため)という構造上自然な挙動
であり、FY Cadenceの`current_year_forecast` Evidenceが存在しないことの
説明となる。

### 複数Disclosure Cadence(§11)

1Q/2Q/3Q Cadenceそれぞれについて、as-of-latestのCurrent-Year-Forecast
Evidenceが同時に存在することを実測で確認した(1Q=2024-08-01公表、2Q=
2024-11-06公表)。**3Q Cadenceの値は2024-02-06公表(旧FY2024向けの3Q時点
Guidance)のまま**であり、FY2025向けの3Q Guidanceはまだ開示されていない
(次回3Q開示は2025-02が想定)。これは「1つのCurrent Guidance」ではなく、
異なるCadence・異なる対象年度のSnapshotが混在しうることの実例であり、
DECISIONS本文でも「Current Guidance」と一括りにせず、各値に
`disclosure_period_type`/`published_at`/`forecast_period`を必ず併記する。
新しいLatest Guidance Selector等はProductionへ追加していない。

### Stage 3.1/ResearchArtifact統合実測(§14、23、Read-only Scratch、Repo未追加)

D0082のIntegrated ArtifactへGuidance Evidenceを追加し、`build_research_
artifact()`経由で実測:

| Evidence種別 | usable件数 |
|---|---|
| P&L(D0075、無変更) | 16 |
| Cash Flow(D0080、無変更) | 12 |
| Balance Sheet(D0081、無変更) | 12 |
| Guidance(Stage 3.9、新規) | 12 |
| Positioning(無変更) | 18 |
| Valuation(D0077、無変更) | 1 |
| **Total** | **71** |

`artifact_id=ART_STAGE3_9_7203_20241115_A_GUIDANCE_V1`(`build_research_
artifact()`経由、直接構築はしていない、Local登録はしていない)。既存
P&L/Cash Flow/Balance Sheet/Positioning/Valuation Evidence件数はいずれも
D0082から不変。`VALUATION_MULTIPLE=7.2853`も不変。

### Interpretation Boundary(§13遵守確認)

Evidence Content・Narrative・DECISIONS本文いずれにも「optimistic/
conservative/beat/miss/upside/downside/上振れ/下振れ/強気/弱気/達成可能/
未達見込み」および既存の禁止語群を含めていないことを機械的Scanで確認した
(0件)。Forecast Revision Relationshipの推論(「上方修正した」等)も
生成していない(単一`FundamentalMetric`のみを扱う既存D0043原則を維持)。

### Guidance Research Status再評価(§15)

**Guidance Coverage = SUPPORTED_BY_DATA**(Current Year Forecast 4 Metric
Type × 3 Cadence = 12件、PIT安全に取得できることを実データで確認)。
**Guidance Interpretation**は別軸として引き続き扱わない(会社予想が存在
すること自体から方向性判断を作らない、Forecast vs Actualの比較Derived
Factも今回作っていない)。

### No Latest-Guidance Engine Yet(§16遵守確認)

`latest_guidance_published_at`はAcceptance Measurementとしてのみ算出した
(`max(published_at)`)。Latest Guidance Selector・Forecast Revision
Engine・Guidance Trend EngineのいずれもProductionへ追加していない。

### Forward PER Boundary(§18遵守確認)

`FEPS=268.77`が利用可能になったが、Forward PERは今回実装していない
(次Bottleneck候補としてのみ評価、§次のBottleneck判断参照)。

### 次のBottleneck判断(§24、実装容易性のみで決めない)

Guidance追加後のActual Artifactを踏まえ、3軸(Research Qualityへの寄与 ×
Data Surface × Semantic Safety)で評価:

- **Forward PER(Company Forecast EPS基準)**: Data Surface即座に利用可能
  (FEPS=268.77が既にEvidence化済み)。D0077の`LATEST_REPORTED_FY_PER`と
  対になる新しいValuation軸(実績basisとForecast basisの並置)を開く。
  Semantic Safetyは、既存`LATEST_REPORTED_FY_PER`のPIT設計(Price Selector
  + Corporate Action Guard)をForecast EPS Denominatorへ再利用できるため
  比較的低リスクと見積もれる——ただし「Forward」という言葉自体が
  Investment Interpretationと混同されやすく、Naming/Boundary設計は要
  注意。
- **BPS**: D0082で既に「既存Balance Sheet軸の補強のみ、FY限定Cadenceで
  鮮度が劣る」と判定済み、変わらず優先度低。
- **ROE**: BPSと同じFY限定Cadence制約、同様に優先度低。
- **Latest Guidance Selector / Guidance Revision**: 今回Measurementで
  「1つのCurrent Guidanceに一括りにできない」ことを確認したが、Selector
  Engine自体はSemantic Safety上まだ時期尚早(Cadence横断でどれを
  "Latest"とすべきかの定義がPIT/Coverage両面で未確定)。
- **Disclosure Content / Consensus / Peer / Historical拡張**: D0079/D0082
  で確認済みのとおり、いずれもより重い新規統合(新規Document取得・新規
  Provider・新規Fetch)が必要でScope外。

**推奨 = Forward PER(Company Forecast EPS基準)を次のResearch Bottleneck
候補として評価してよいが、今回は実装しない**(§18 Do Not、§30 Output
指示どおり自動着手しない)。

### Confidence(§27)

Evidence件数が59(D0082)→71(今回)へ増加したが、`data_confidence`/
`research_confidence`は自動昇格していない(LOW据え置き)。Source Vintage
Completenessは引き続きUNVERIFIED。

### Tests(§19-22)

新規: `13_tests/test_fundamentals_guidance_evidence.py`(23件、Converter
Guard・Forecast Horizon・A-path Real Selection)、`test_fundamentals_
normalize.py`へGuidance専用Test3件追加、`test_research_artifact.py`へ
A/B混在Guard Test(Guidance参加確認+単独Reject確認)2件追加(計28件
新規)。Fixture(`financial_summary_v2.json`)は既存7203行(FY/1Q/2Q)へ
FSales/FOP/FNP/FEPS追加、6758行へZero/Negative Forecast確認用Field追加
(既存Assertionに影響する変更なし)。

### Verification(§26)

- Syntax/Compile: 全対象ファイルOK。
- Targeted(新規28件): 全PASS。
- Relevant(`-k "fundamental or evidence"`): 282/282 PASS。
- ResearchArtifact関連(`-k "research_artifact"`): 32/32 PASS。
- Valuation関連(`-k "valuation"`): 13/13 PASS。
- Full Regression(`13_tests/`): 1089/1090 PASS。唯一の失敗は
  `test_protected_path_hook.py::test_hook_warns_on_protected_screening_
  tool_paths`で、D0074/D0075/D0077/D0080/D0081と同一の既知Windows Hook
  Environment Issue(今回のScopeと無関係、修正していない)。
- `ruff check`: 対象ファイル全てPASS。
- `ruff format --check`: 初回1ファイルで長い行を検出、`ruff format`で
  整形して解消(内容の変更なし)。
- `mypy`(`lib/fundamentals/evidence.py`): Success、0 issues。Test File側は
  D0080/D0081と同一の既知Windows/numpy/Python 3.14 Environment Issueが
  再現するため`QUALITY_GATE_ENV_BLOCKED`として記録、修正していない。
  H0001 Locked Testは実行していない。

### Persistence / Commit対象(§29)

`lib/fundamentals/evidence.py`・`13_tests/test_fundamentals_guidance_
evidence.py`(新規)・`test_fundamentals_normalize.py`(既存へ追記)・
`test_research_artifact.py`(既存へ追記)・`13_tests/fixtures/financial_
summary_v2.json`(既存へ追記)・このDECISIONS.md追記をCommit対象とする。
Raw Snapshot・`02_company_research/7203_Toyota_Motor/`(今回無変更)・
Scratch ScriptはいずれもCommit対象外。

### Do Not(§25遵守確認)

Next-Year Guidance Wiring・Forecast Revision Interpretation・Forward PER
実装・BPS・ROE・PBR・Peer・Consensus・Expectations Engine・新規Provider・
新規Historical Fetch・Decision Engine・Portfolio Engine・D0057 General
Fixのいずれにも着手していない。H0001 Locked Testの再実行もしていない。

## D0084 — Stage 3.10: Current FY Company Forecast PER v1 + D0077 Non-Positive EPS Hardening

D0083でPIT安全にEvidence化されたCurrent Fiscal Year Company Forecast EPS
(FEPS)とcompleted-session Closeを組み合わせ、`CURRENT_FY_COMPANY_
FORECAST_PER`という新しいValuation Derived Factを実装した。同時にCodex
Auditで確認されたD0077既存欠陥(EPS<=0の無条件除算)を狭くHardeningした。

### Architecture Decision(§1)

Codex Audit Verdict = READY_WITH_GUARDS、採用Architecture = Option A
(新Record + 新Builder)。新Metric名は`CURRENT_FY_COMPANY_FORECAST_PER`
(genericな`FORWARD_PER`は使わない、Consensus Forward EPSではなく会社
自身のCurrent FY Forecast EPSであることを明示)。D0077の`LATEST_
REPORTED_FY_PER`とはDenominator選定・Target Semantics・Corporate Action
Windowがいずれも異なるため、共通Builderへ早期に統合しなかった(§3)。
再利用したのは`select_latest_close_bar()`・`session_close_at()`・
Corporate Action Window Predicate(`has_share_basis_action_in_window()`、
D0077の`_has_share_basis_action_in_window()`をPublic化して再利用)・
`positive_eps_or_none()`(新設、D0077/D0084共通)のみ。

### 新Record(§2)

`lib/valuation/model.py`へ`CurrentFyCompanyForecastPerRecord`を追加
(entity_code/as_of/price系/eps_value/forecast_period_start/forecast_
period_end/guidance_published_at/source_version_id/source_field/
fiscal_year_target/disclosure_period_type/consolidation_scope/
accounting_standard/calculation_expression/multiple/corporate_action_
basis_statusを型付きFieldとして保持)。`DENOMINATOR_TYPE_CURRENT_FY_
COMPANY_FORECAST_EPS_CONSOLIDATED`を新設。既存`LatestReportedFyPerRecord`
のField/意味は変更していない。

### Current FY Forecast EPS Candidate Contract(§4)とTyped Selector(§5)

`lib/valuation/current_fy_forecast_builder.py`(新規Module)へ:

- `select_current_fy_company_forecast_eps_candidate()`: `(SourceVersion,
  FundamentalMetric, DisclosureEnvelope)`のTuple集合から、§4の全Contract
  (metric_type=eps_current_year_forecast、source_field=FEPS、
  COMPANY_FORECAST、CURRENT_FISCAL_YEAR、CONSOLIDATED、PRESENT、value>0、
  published_at非UNKNOWN・as_of以前、metric/version/envelope相互ID一致、
  Decimal(version.value)==metric.value、current_fiscal_year_start/end
  非None・start<=end)を満たす候補だけへ絞り込み、`forecast_period_start
  <= as_of.date() <= forecast_period_end`でWindow Filterし、`(forecast_
  period_start, forecast_period_end)`をTarget FY識別子としてGroup化する。
  異なるTargetが複数残る場合・同一published_atで値/metric_idが異なる
  Candidateが複数残る場合はいずれも`ValueError`でfail closed(推測で
  選ばない)。`selected.values()`から適当に1件取ることを禁止した設計を
  実装で体現した。
- `build_current_fy_company_forecast_per()`: Selectorを経由しない直接
  呼び出しにも安全なよう、§4のContractを全てDefense-in-depthで再検証する
  (D0083 Guidance Converterを代わりのValidatorとして使わない)。

### Forecast Horizon != Disclosure Current Period(§2、D0083から継続)

`forecast_period_start`/`forecast_period_end`は常に`envelope.current_
fiscal_year_start`/`.current_fiscal_year_end`のみを使い、`current_
period_start`/`.current_period_end`は一切参照しない。`disclosure_
period_type`はDisclosure Cadenceを表すのみ。

### Coverage Boundary(§6)

`CURRENT_FISCAL_YEAR`限定。FEPSが空でNxFEPSに新年度予想が存在する期間
でも、NxFEPSへFallbackしない(D0083で確認済みのFY Cadence Disclosure
特有の挙動と整合)。Candidateが無ければ`None`(正しいCoverage Gap)。
Generic`LATEST_COMPANY_FORECAST_FY_PER`は作っていない。

### Forecast-Specific Corporate Action Guard(§9)

D0077 Actual EPS用のWindow(`fiscal_period_end..price_date`)をそのまま
流用せず、Forecast v1専用のWindow(`forecast_period_start <= action.
effective_date <= price_date`、両端Inclusive)を使う。1件でもEventが
Window内にあればRecordを生成しない。Provider FEPSのShare Basisへの
独自Adjustmentはしていない。

### Non-Positive EPS(§10)とD0077 Hardening(§11-12)

`positive_eps_or_none()`(`lib/valuation/builder.py`新設、D0077/D0084
共通)を導入し、EPS<=0の場合は`CURRENT_FY_COMPANY_FORECAST_PER`/
`LATEST_REPORTED_FY_PER`いずれもRecordを生成しない(`None`、fail
closed)。**D0077の既存欠陥Hardening**: `build_latest_reported_fy_per()`
は以前EPSを無条件除算していた(EPS=0で`ZeroDivisionError`、EPS<0で
Negative PERをそのまま通常のValuation Multiple FACTとして生成)。今回
この2ケースいずれも`None`を返すよう修正した。**既存Positive Path
(7203、multiple≈7.2853)のBehaviorは完全に維持されていることをTestで
確認した**(`test_positive_eps_path_unchanged_after_hardening`)。

**Codex Audit Finding 6 Hardening(§12)**: `build_latest_reported_fy_
per()`へ、`eps_metric.metric_id == eps_version.source_version_id`・
`eps_version.source_record_id == eps_metric.series_id`・
`Decimal(eps_version.value) == eps_metric.value`のDefense-in-depth
Validationを追加した(既存13件のTestが無変更でPASSすることを確認済み、
既存Test Helperがこれらの不変条件を既に満たしていたため)。

### Provenance(§17)

D0077と同じPattern(Evidence Converter自体は内部でProvenance登録せず、
呼び出し側/Test側が`ProvenanceStore`へ`price_bar`/`fundamental_source_
version`の2 Parent Linkを追加する)をそのまま踏襲した。

### 実データ受け入れ(§25、7203、as_of=2024-11-15 15:00 JST)

hard-code無し、Local Snapshotから読み取り:

```
REAL_PRICE=2666.0 (price_date=2024-11-14)
REAL_FEPS=268.77
REAL_FORECAST_PERIOD=2024-04-01..2025-03-31
REAL_GUIDANCE_PUBLISHED_AT=2024-11-06 13:55:00+09:00
REAL_CORPORATE_ACTION_EVENTS=0
CURRENT_FY_COMPANY_FORECAST_PER=9.919261822376009227220299885(≈9.9193x)
LATEST_REPORTED_FY_PER=7.285347324698037929715253867(≈7.2853x、D0077-D0083と完全一致・不変)
```

2024-11-15 15:00 JST時点の当日Close(2704)は15:30大引け未確定のため拒否
され、2024-11-14 Close(2666)が選定されたことを実データで確認した(D0077
と同一挙動)。

### Stage 3.1/ResearchArtifact統合実測(§26、Read-only Scratch、Repo未追加)

D0083のIntegrated ArtifactへCurrent FY Company Forecast PER Evidenceを
1件追加し、`build_research_artifact()`経由で実測:

| Evidence種別 | usable件数 |
|---|---|
| P&L(D0075、無変更) | 16 |
| Cash Flow(D0080、無変更) | 12 |
| Balance Sheet(D0081、無変更) | 12 |
| Guidance(D0083、無変更) | 12 |
| Positioning(無変更) | 18 |
| Valuation(Actual FY PER 1件 + Current FY Company Forecast PER 1件) | 2 |
| **Total** | **72** |

`artifact_id=ART_STAGE3_10_7203_20241115_A_FORECASTPER_V1`。既存P&L/Cash
Flow/Balance Sheet/Guidance/Positioning Evidence件数はいずれもD0083から
不変。Actual FY PER Multipleも不変。禁止語Scan(cheap/expensive/
undervalued/overvalued/attractive/upside/downside/割安/割高/買い/売り/
BUY/SELL)は0件。

### Valuation Multiple Coverage再評価(§27)

**Actual FY basis + Current FY Company Forecast basisの両方が
SUPPORTED_BY_DATAまで言える**(実データで2種類のMultipleを同時に取得・
Evidence化できることを確認)。**Valuation Interpretationは依然UNAVAILABLE
/PARTIAL**(D0079で確認済みのHistorical Comparator/Peer不足が未解消の
まま)。9.9193そのものから「高い/安い」の判断は一切していない。

### Do Not Build Actual-vs-Forecast Delta Yet(§19遵守確認)

`Forecast PER - Actual PER`・`Forecast PER / Actual PER`・Actual EPS vs
Forecast EPSの比較・Earnings Decline/Growth Interpretation・Priced-in
Interpretationはいずれも作っていない(2つのMultipleを同一ResearchArtifact
内へ並べて保持できることを確認したのみ)。

### 次のBottleneck測定(§28)

Actual Resultから評価:

- **Actual-vs-Company-Forecast EPS Derived Fact**: Data Surfaceは既に
  両方揃っている(Actual FY EPS=365.94、Current FY Forecast EPS=268.77)
  が、比較Derived Fact自体を作ると即座にGrowth/Decline方向のNarrativeを
  誘発しやすく、Semantic Safety上最も慎重な設計が必要(単なるDelta表示
  でも「減益」という含意を持ちうる)。
- **Generic Latest Published Company Forecast FY PER**: D0083/D0084で
  「異なるCadenceが異なるTarget FYを指しうる」構造が既に明確になった
  ため、Genericな「Latest」Selector自体の必要性はまだ低い(Current FY
  限定Scopeで十分に実用的なCoverageを確認済み)。
- **Next-Year Guidance Wiring**: 実装コストはCurrent FY版と同程度に
  低いが、Research Quality上はActual-vs-Forecast同様、まだ比較対象が
  無い単独のNext-Year Multipleを作ることになり、寄与は限定的。
- **BPS/ROE・Historical/Peer拡張・Disclosure Content・Consensus**:
  D0082/D0079で既に評価済みの理由(FY限定Cadenceで鮮度劣化・Data Surface
  Blocked・より重い新規統合が必要)から変わらず優先度低〜Scope外。

**推奨候補は次回のRoundで評価**(自動実装しない、§25/§18 Do Not
遵守)。

### Confidence(§29)

Evidence件数が71(D0083)→72(今回)へ増加したが、`data_confidence`/
`research_confidence`は自動昇格していない(LOW据え置き)。Source Vintage
Completenessは引き続きUNVERIFIED。

### Tests(§20-24)

新規: `13_tests/test_valuation_current_fy_company_forecast_per.py`
(38件、Selector 14件・Join/Value 8件・Price/Corporate Action 8件・
Evidence/Provenance 8件)。`test_valuation_latest_reported_fy_per.py`へ
D0077 Hardening確認Test6件追加(計44件新規)。

### Verification(§30)

- Syntax/Compile: 全対象ファイルOK。
- Targeted(新規44件): 全PASS。
- Fundamentals/Guidance関連(`-k "fundamental or guidance or evidence"`):
  292/292 PASS。
- ResearchArtifact/Valuation関連(`-k "research_artifact or valuation"`):
  88/88 PASS。
- Full Regression(`13_tests/`): 1133/1134 PASS。唯一の失敗は
  `test_protected_path_hook.py::test_hook_warns_on_protected_screening_
  tool_paths`で、D0074以来の既知Windows Hook Environment Issue(今回の
  Scopeと無関係、修正していない)。
- `ruff check`: 対象ファイル全てPASS。
- `ruff format --check`: 対象ファイル全てPASS(整形適用済み)。
- `mypy`(`lib/valuation/model.py`・`builder.py`・`evidence.py`・
  `current_fy_forecast_builder.py`): Success、0 issues。Test File側は
  既知のWindows/numpy/Python 3.14 Environment Issueが再現するため
  `QUALITY_GATE_ENV_BLOCKED`として記録、修正していない。H0001 Locked
  Testは実行していない。

### Persistence / Commit対象(§32)

`lib/valuation/model.py`・`builder.py`・`evidence.py`・
`current_fy_forecast_builder.py`(新規)・`13_tests/test_valuation_
current_fy_company_forecast_per.py`(新規)・`test_valuation_latest_
reported_fy_per.py`(既存へ追記)・このDECISIONS.md追記をCommit対象と
する。Raw Snapshot・`02_company_research/7203_Toyota_Motor/`(今回無
変更)・Scratch ScriptはいずれもCommit対象外。

## D0085 — Stage 3.11: Post-Valuation Research Bottleneck Re-measurement(D0084完了後、Buildせず次候補を再測定、Production Code変更なし)

D0084完了時点の7203 Integrated ResearchArtifact(72 Evidence)を基準に、
次に追加すべきResearch Capabilityを、実装せずActual Repo調査+実データ
再確認のみで再測定した。

### 実行結果(D0084 Scratch Scriptを再実行、Repo未変更で再現性確認)

```
PL=16 CashFlow=12 BalanceSheet=12 Guidance=12 Positioning=18 Valuation=2
Total=72
LATEST_REPORTED_FY_PER≈7.2853
CURRENT_FY_COMPANY_FORECAST_PER≈9.9193
forbidden_term_hits=[]
```

D0084から完全に不変(Repo無変更のため当然だが、hard-code再現ではなく
実行して確認)。

### Actual Repo調査による新規判明事項(推測ではなく確認)

1. **Disclosure Content(EDINET)**: `01_data/raw/EDINET/edinet_document_
   S100TD9S_type1_smoketest.bin`が実在し、中身は7203(EDINET Filer Code
   `E02144`)の**実XBRL Document**(`2024-05-08`付、既存FY実績/Guidance
   Workと同一の開示日)であることを確認した。ただし`EDINET_LOCAL_
   VALIDATION_GUIDE.md`により、`EdinetAdapter`はRaw HTTP Fetchのみで
   `DisclosureDocument`へのField Mapping(Title/DocKind/公表時刻等の
   Metadata)は実施しておらず、そのMetadataは別のEDINET Documents List
   API呼び出しが必要(ローカルには存在しない、このSessionはEDINET関連
   Hostへ疎通不可)。したがって「Codeはあるが実データがfixtureのみ」
   ではなく、**「実Document本体はローカルにあるが、それをEvidence化する
   ために必要なMetadata取得が新規Fetch相当でBlocked」**という、より
   精密な状態であることが判明した。さらに`lib/disclosures/model.py`の
   設計自体が「本文Semantic Extraction(数値抽出・Event分類・Claim
   抽出)はScope外(将来Phase)」と明記しており、Wiringが完了しても
   得られるのは「Documentが公開されたというFACT」のみで、Catalysts/
   Risksの内容そのものは依然埋まらないことも確認した。
2. **Consensus/Expectations**: `lib/consensus/`(Phase4E-4、`catalog.py`
   /`evidence.py`/`model.py`/`normalize.py`/`view.py`、計631行)が既に
   存在し、`RevisionHistory`/`SourceVersion`等Fundamentals既存Primitive
   を再利用したPIT-safe/Vintage-aware Data Foundationとして設計済みで
   あることを確認した。ただし実Provider Adapter(Finnhub等)・実7203
   Consensusデータはいずれも存在しない(`lib/data_sources/`にConsensus
   系Adapter無し、Local Snapshotにも無し)。したがって「未着手」ではなく
   「Data Foundationは完成済み、Provider接続のみが無い」状態であることが
   判明した(既存Round(D0078等)の「Adapter未実装」という表現は正しい
   が、Data Foundationの完成度についての新情報)。
3. **Source Vintage Reliability**: D0075 Source Vintage Guardの原文
   ("J-Quants Financial Summaryが「訂正前値を必ずhistorical rowとして
   保持する」ことを公式仕様から完全確認できていない")を再確認した。
   これはCode Gapでも Historical Snapshot Gapでもなく、**Provider
   Verification Gap**(公式仕様への疎通不能というSession制約に起因、
   D0043以来継続)であり、今回のSessionでCodeによって解消できるもの
   ではないことを確認した。
4. **Historical Valuation Context / Peer Valuation**: Price Snapshot
   Coverage(`2024-01-04`〜`2024-12-30`、245 Session)を再実行で再確認
   した。D0079から不変。新規Fetchなしでは拡張不可。

### Capability Comparison Table(§17)

| Capability | Research Impact | Data Availability | PIT Readiness | Semantic Safety | Implementation Cost | What It Unlocks | Current Blocker | Verdict |
|---|---|---|---|---|---|---|---|---|
| Actual-vs-Forecast EPS | Medium | High | High | **Low** | Low | 実績/予想の橋渡しFactのみ | なし(Data Ready) | 非推奨(Semantic Risk) |
| Growth/YoY | **High** | High | High | Medium | Medium | D0076以来のPARTIAL Gapを解消、新Research軸 | なし(Data Ready) | **推奨** |
| Next-Year Guidance | Low-Medium | High | High | High | Low | 季節的Coverage Gap(年3か月程度)のみ | なし(Data Ready) | 低優先(影響小) |
| Guidance Revision/Trend | Medium | High | High | **Low** | Medium | Forecast推移の可視化 | なし(Data Ready) | 非推奨(Semantic Risk) |
| Disclosure Content | High(理論上) | **Blocked** | Unverified | High | Blocked | Document公開FACTのみ(本文内容は別Phase) | 新規Fetch必須(EDINET Host疎通不可) | **Blocked** |
| Consensus/Expectations | High | **Blocked**(Foundationのみ) | Architecture Ready | Medium-High | High | Valuation Interpretationの比較基準 | NEW_PROVIDER_REQUIRED | **Blocked** |
| Historical Valuation | High(理論上) | **Blocked** | N/A | N/A | 新規Fetch必須 | 自己Historical比較基準 | Price Snapshot単年のみ | **Blocked**(D0079不変) |
| Peer Valuation | High(理論上) | **Blocked** | N/A | N/A | 新規Fetch/新規銘柄必須 | Peer比較基準 | Sector不一致0/3 | **Blocked**(D0079不変) |
| BPS/ROE | Low | High | High | High | Low | 既存Balance Sheet軸の補強のみ | なし | 低優先(D0082判定継続) |
| Source Vintage Reliability | High(理論上) | N/A | N/A | N/A | **Code非対応** | Confidence昇格 | 公式仕様疎通不可(Session制約) | **Blocked** |

### Verdict Rationale(§18、実装容易性のみで選ばない)

Blocked(Disclosure Content・Consensus・Historical・Peer・Source
Vintage)を除いた残り5候補のうち、Next-Year Guidance・BPS/ROEは低実装
コストだが影響が限定的(既存軸の補強、または季節的な狭いGapのみ)。
Actual-vs-Forecast EPSとGuidance Revision/TrendはいずれもSemantic
Safetyが低い(前者は異なる会計年度のActual/Forecastを並べることで
「減益」を暗示しやすく、後者はForecast推移の提示が「上方修正/下方修正」
という文言の自動生成へ直結しやすい、§9で明示的に禁止)。

Growth/YoYのみが、(1) D0076以来のNamed Gap(Growth=PARTIAL)を直接
解消する、(2) 既存RevisionHistoryが複数年分の同一Period Type実績を
既に保持しておりData Surfaceは即座に利用可能、(3) Actual-to-Actualの
比較でありActual-vs-Forecastより方向性を暗示しにくい、(4) D0084で
実装したTarget FY Grouping SelectorのPatternがそのまま転用できる、
という4条件を同時に満たした。

### Good Company != Good Stock(§13遵守確認)

本Round自体はMeasurementのみで、いかなるCapabilityも実装していない。
Growth/YoYを推奨したこと自体も投資判断ではなく、次のResearch Capability
選定の優先順位付けに留まる。

### Do Not(§15遵守確認)

Production Code変更なし。Raw Snapshot変更なし。新規Fetchなし。H0001
Locked Testは実行していない。

### Verification(§16)

Code変更が無いため、D0084のScratch Script(`stage3_10_current_fy_
forecast_per_acceptance_7203.py`)をRead-onlyで再実行し、既存Evidence
Countと両Valuation Multipleが再現することのみ確認した(Targeted Smoke
相当)。Full Regressionは実施していない。

### Persistence / Commit対象

このDECISIONS.md追記(Doc-only)のみCommit対象。Raw Snapshot・
`02_company_research/7203_Toyota_Motor/`(今回無変更)・Scratch Script
はいずれもCommit対象外。
