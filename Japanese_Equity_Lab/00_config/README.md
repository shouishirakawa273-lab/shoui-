# 00_config/

実行時設定を置く。ユニバース定義・Portfolio Constructionルール等。

- `portfolio_rules.example.json`: `lib/schemas/portfolio_rules.PortfolioRules` の例。
  実運用のルールは `PR_<用途>.json`(例: `PR_default.json`)のように用途が分かる名前で追加する。

秘密情報(APIキー等)はここに置かない。親リポジトリの `.env` を参照する(ルートCLAUDE.md参照)。
