# 08_portfolio/

- `holdings/`: 現在の実際の保有銘柄。
- `watchlist/`: 監視銘柄。
- `shadow_portfolio/`: AIが出した候補全体の追跡(人間が選ばなかった銘柄も含めて追跡し、
  「戦略選定の価値」と「人間の最終選択の価値」を分離する。RESEARCH_RULES.md参照)。
- `decision_log/`: 実際のBUY/HOLD/SELL判断の記録(最終判断は必ず人間が行う)。

ファイル名は `<日付>_<ticker or ポートフォリオ名>.md` 等、内容が分かる形にする。
