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
