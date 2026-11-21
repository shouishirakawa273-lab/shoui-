# 正本と監査証拠の所在

2026-10-14。既存契約を上書きしない参照索引。正本は単一ファイルではなく、用途と受入SHAで識別する。

## 既存の根拠文書

- Japanese_Equity_Lab/README.md: 方針文書の索引。Phase表記だけで現在の完成度を判定しない。
- Japanese_Equity_Lab/INVESTMENT_POLICY.md、RESEARCH_RULES.md: 目的・研究/PIT/検証原則。
- Japanese_Equity_Lab/EVIDENCE_MODEL.md、各ARCHITECTURE.md: データ・証拠・各層の契約。
- Japanese_Equity_Lab/DECISIONS.md: 仕様変更・受入・FROZENの履歴。後日公開前の状態記述と実際の公開状態が違う場合は時点を区別する。
- Japanese_Equity_Lab/VALIDATION_BACKLOG.md: 未解決の実世界検証項目の既存索引。詳細の重複コピーを避ける。
- Japanese_Equity_Lab/10_agents/README.md: 研究用Agentの役割。本development文書は開発担当の分業であり、研究Agentの置換ではない。
- 本フォルダのPRODUCT_ACCEPTANCE、DEVELOPMENT_ORGANIZATION: 今回承認された完成品受入・開発運用基準。コードや既存milestoneの受入を自動成立させない。

## 固定された監査対象

設計監査と独立検証はそれぞれ初回判断を独立に行い、同一HEAD fba60cbc42b76021000a24663dce34fd51b13aeaを確認した。
そのHEADはPR #4のコード対象。PR #3を含む統合HEADとして扱わない。
両者とも読取のみ、テスト未実行。以下は設計・コードの静的根拠確認であり、数値実行検証の合格ではない。

| 所見 | 根拠（上記SHA） |
|---|---|
| READMEのPhase3D表記は後続工程の完成度を示さない | Japanese_Equity_Lab/README.md:83、DECISIONS.md:18245以降 |
| 完成品の一貫受入表が不足 | README方針索引、既存文書名と契約の照合。全成果物を網羅監査したとの主張ではない |
| 公開情報再構成とprovider再現を区別する必要 | RESEARCH_RULES.md:586、EVIDENCE_MODEL.md:42、MACRO_ARCHITECTURE.md:98 |
| pretax基盤はOI評価へ接続していない | lib/profit_impact/calculation.py、lib/valuation/engine.py:133、DECISIONS.md:19075 |
| store再計算は実会社の過去event-to-return再現完成ではない | lib/profit_impact/store.py:149、lib/evaluation/model.py:37 |
| caller確認・sourceラベルだけで原資料の意味を独立証明しない | lib/profit_impact/calculation.py、DECISIONS.md:19080 |

主担当が公開APIで確認したPR状態:
- PR #3: a698832337a9b0d70f0a1a8c09cd74769ec60f2d、Draft、未マージ。
- PR #4: fba60cbc42b76021000a24663dce34fd51b13aea、Draft、未マージ。
- 共通base: 071cff9c18632461c207a08c20e7c721a983221b、claude/investment-strategy-pipeline-jyfby5。

監査担当自身はremote状態を検証していない。公開状態と独立静的監査の証拠を区別する。
文書専用branchは上記baseから作成し、既存コード・FROZEN資料を変更しない。
この文書の公開もマージ・milestone正式受入・FROZENとは別。受入済み実装の基準はbase、未受入実装の基準は各PRのSHAとする。
競合する文書は対象範囲・日付・明示的受入・SHAで照合し、矛盾を報告する。後の日付だけで凍結契約を無効にしない。
