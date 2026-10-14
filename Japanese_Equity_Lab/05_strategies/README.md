# 05_strategies/

Strategy定義。`lib/schemas/strategy.Strategy` に対応する。
Hypothesisが `VALIDATED` になった後に、実行可能な形(Signal定義)へ落とし込む。

ファイル名は `S<連番>_<内容>.md`(例: `S0001_earnings_revision_underreaction.md`)。

`status`: `ACTIVE` / `WATCH` / `DEGRADED` / `RETIRED`(Strategy Decay。RESEARCH_RULES.md参照)。
登録時に `retirement_criteria`(例: 直近12か月Alpha < 0)を必ず明記する。
Portfolio Construction(組み合わせ方のルール)はここではなく `00_config/` を参照
(`lib/schemas/portfolio_rules.PortfolioRules`)。
