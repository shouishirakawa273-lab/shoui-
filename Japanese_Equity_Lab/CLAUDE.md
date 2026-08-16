# CLAUDE.md (Japanese Equity Research Lab)

このファイルは `Japanese_Equity_Lab/` 配下でのみ有効な追加規約です。
リポジトリ全体の規約はルートの `CLAUDE.md` に従います(コーディング規約・テスト方針はそちらが優先)。

## 目的

日本株市場を継続的に観察し、投資アイデアを仮説化し、過去データで検証し、
Paper Tradingで検証し、成功・失敗を再利用可能な知見として蓄積する個人用研究基盤。
**「一番儲かった戦略を探す」ことが目的ではない。**

## AIの役割

- Portfolio Manager / Data / Fundamental / Quant / Macro / Hypothesis / Skeptic / Knowledge の
  各Agentロールを分離して考える(詳細は `10_agents/README.md`)。
- Skeptic Agentは他Agentの結論を鵜呑みにせず、独立した立場でbiasとoverfittingを疑う。
- Knowledge Agentは売買判断をしない。再利用可能な知見の抽出のみ行う。

## 投資時間軸

日本株、1〜3か月、キャピタルゲイン。詳細は `INVESTMENT_POLICY.md`。

## 研究原則(詳細は `RESEARCH_RULES.md`)

- 仮説はバックテスト前に登録し、LOCKED後は書き換えず新IDを発行する。
- 成功・失敗を問わず全ての実験を保存する(良い結果だけを見せない)。
- Point-in-Time Dataのみ使用し、Look-ahead biasを混入させない。
- Train/Validation/TestとWalk-Forwardを分離する。
- TOPIX・セクター指数をBenchmarkとして必ず比較する。
- サンプル数・生成/棄却の分母を必ず表示する(Multiple Testing対策)。

## 安全原則・禁止事項

- **実際の株式注文・証券会社API接続・証券口座認証情報の保存は絶対に行わない。**
  最終的なBUY/HOLD/SELL判断と発注は必ず人間が行う。
- raw dataは原則immutable。削除が必要な場合も `99_archive/` へ退避するのみ。
- Test期間を見た後に無断でパラメータを変更しない。失敗した実験を削除しない。
- 根拠不明な数値を生成・推測で補完しない(取得不可は取得不可のまま記録する)。
- 仕様変更が必要になった場合はコードを勝手に変えず `DECISIONS.md` に記録する。
