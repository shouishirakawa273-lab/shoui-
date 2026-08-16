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

## D0014 — Corporate Actionsの取得元が未実装のため、Phase2のPipelineはsplit調整なし

**判断**: `scripts/jquants_lab_pipeline.py`は`RawOHLCVBar` -> `AdjustedOHLCVBar`の変換に
`apply_split_adjustments(bars, actions=[])`を使う(=常に無調整)。理由は、
J-Quantsから「株式分割の公表時刻(announced_at)」を取得する具体的なエンドポイントを
このセッションでは検証できておらず、確度の低い実装をするより「未調整であることを
明示する」方が安全なため。RawとAdjustedを明示的に分離する変換ステップ自体は必ず通す
(=`RawOHLCVBar`をそのまま返さず、`AdjustedOHLCVBar`(factor=1.0)へ変換してから
Backtest Engineに渡す)。

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
