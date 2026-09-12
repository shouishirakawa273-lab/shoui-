# 09_knowledge/

再利用可能な知見。`lib/schemas/knowledge.Knowledge` / `SurpriseLogEntry` に対応する。
**成功だけでなく失敗もKnowledgeとして残す。**

- `validated_patterns/`: 検証済みで再現性があったパターン。
- `failed_patterns/`: 検証したが機能しなかったパターン(削除しない)。
- `market_regimes/`: 特定の市場環境でのみ機能した/しなかった知見。
- `sector_patterns/`: セクター固有の知見。
- `behavioral_biases/`: 市場参加者の行動バイアスに関する知見。
- `surprises/`: `SurpriseLogEntry`(予想と違ったこと)。

ファイル名は内容が分かる名前(例: `earnings_revision_underreaction.md`、
`low_pbr_high_roe.md`)。企業固有の情報は `02_company_research/` へ。
