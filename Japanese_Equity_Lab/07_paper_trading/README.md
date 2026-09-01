# 07_paper_trading/

Paper Trade記録。`lib/schemas/paper_trade.PaperTrade` に対応する(frozen、後から理由を書き換えない)。

Backtestで良好だった戦略は、実資金の前に必ずここでPaper Tradingを行う。

ファイル名/記録単位は `PT<連番>_<ticker>_<日付>.json`。
`selected_by_human` フィールドで、AIが出した候補全体(Shadow Portfolio)と
人間が実際に選んだ銘柄(Actual Portfolio)を区別する(`08_portfolio/shadow_portfolio/` 参照)。
