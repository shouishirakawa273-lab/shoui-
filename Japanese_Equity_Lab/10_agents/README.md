# 10_agents/

サブエージェントの役割定義(Phase1は設計のみ、実行可能なagent実装はPhase4)。

1つの万能AIに全てを判断させない。以下の役割を分離する。

| Agent | 役割 |
|---|---|
| Portfolio Manager | 全体統括。他Agentの結果をまとめる。自分で都合の良いデータだけ選ばない。 |
| Data | 市場・企業データ取得と品質管理。Point-in-Timeを重視。 |
| Fundamental | 決算・IR・業績・Valuationを分析。 |
| Quant | バックテスト、統計分析、分布分析。 |
| Macro | TOPIX、海外株、為替、金利、セクター等を分析。 |
| Hypothesis | 情報源から検証可能な仮説を作る。収益性を決めつけない。 |
| Skeptic | 他Agentと独立して、bias・overfitting・sample不足等を批判的に確認する(下記参照)。 |
| Knowledge | 売買判断をしない。再利用可能な知見の抽出のみ行う。成功だけでなく失敗も保存する。 |

## Skeptic Agentの確認項目(特に重要)

Look-ahead bias / Survivorship bias / Overfitting / Multiple testing / Sample不足 /
特定銘柄依存 / 特定年度依存 / 特定Sector依存 / Benchmark未考慮 / 取引コスト /
説明できないパラメータ。過去の議論を与えず、完成した結果を第三者としてレビューする。
