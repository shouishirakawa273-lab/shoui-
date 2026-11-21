# W0クローズと前向き管理基準の採用

基準日 2026-11-21。対象は `development/w0/2026-10-17/` のW0成果物一式。

**判定: W0を受入としてクローズし、W1移行の管理上の停止を解除する。** ただし過去の承認原証拠の不足はUNKNOWNとして恒久確定する。本クローズは、過去に正式承認が存在したことの証明ではない。

## 採用した経路

`development/w0/2026-10-17/FREEZE_INDEPENDENT_REVIEW.md` の "Remaining blocking original evidence" は2つの経路を提示していた。

1. 既存の承認チャット・受入manifestの原証拠を回収する
2. 歴史的な受入・FROZEN宣言とは明示的に分離した、新しい前向き管理基準をオーナーが採用する

オーナーは **2** を選択した。理由は、原証拠の所在が不明であり、無期限の探索が研究再開を妨げていること。`W0_RESULT.md:5` の保留判定はこの選択により解除されるが、保留の**原因**は解消されていない（下記「本クローズが主張しないこと」）。

## 1. 探索の打ち切りとUNKNOWN恒久確定

以下は今後も探索せず、UNKNOWNとして確定する。将来これらを根拠に「承認済み」と述べない。

| 項目 | 出典 | 確定扱い |
| --- | --- | --- |
| Stage 3.15 の正式な全凍結範囲 | `FREEZE_EARLY_AUDIT.md` | UNKNOWN恒久 |
| Stage 3.17 の共有sources catalog等を含む完全境界 | `FREEZE_EARLY_AUDIT.md` | UNKNOWN恒久 |
| D0098.1 hook変更のowner解除・再凍結SHA | `FREEZE_EARLY_AUDIT.md` | UNKNOWN恒久 |
| D0104/05/06 以前の宣言の受入台帳 | `INDEPENDENT_REVIEW.md` | UNKNOWN恒久 |
| 当時のJ-Quants raw/manifest・HTTP原証拠の保全所在とhash照合 | `W0_RESULT.md:20` | UNKNOWN恒久 |
| 過去の全期間利用・人による閲覧履歴 | `W0_RESULT.md:21` | UNKNOWN恒久（2025/2026を未見データとして扱わない方針は維持） |

`FREEZE_DECLARATION_INDEX.md` の169件索引、`freeze_inventory.json`、`historical_freeze_inventory.json` は証拠として保存する。これらは完全な受入台帳ではないという `W0_RESULT.md:5` の留保をそのまま維持する。

## 2. 今後の承認ルール（前向き管理基準）

2026-11-21以降に適用する。過去には遡及しない。

> FROZEN宣言、Locked解除、製品受入、マージは、`development/APPROVALS.md` に1行追記することで成立する。形式は `日付 / 対象 / 種別 / 承認者 / 根拠commit`。追記のない変更はFROZEN扱いにしない。

一人開発の実行可能性を優先し、署名・自動照合・Workflowによる強制は導入しない。`W0_RESULT.md:33` のとおり、承認権限はオーナーに留保される。

## 3. 正本ブランチの決定

`W0_RESULT.md:30` が求めていた決定。

- 研究の正本・将来の安定ブランチを **`main`** とする
- `main` は `codex/w0-research-current-state` から作成し、全21ブランチの上位集合であることをGitHub Compare APIで確認済み（どのブランチも `main` に対して ahead=0）
- 既定ブランチを `claude/repo-creation-setup-ejmkje`（2026-08-14、`Japanese_Equity_Lab/` 不在）から `main` へ変更した
- これにより `W0_RESULT.md:15` の「既定ブランチにLabが無い」と、Daily Health Checkが研究基盤を対象にしていなかった問題は解消される
- 既存の21ブランチは削除しない。参照用に残す

## 4. マージ承認の記録

`W0_RESULT.md:30` は正本ブランチの決定とマージ承認を分離するよう求めている。別の承認として記録する。

| ブランチ | 取り込み内容 | 承認理由 |
| --- | --- | --- |
| `codex/development-governance` | `development/` のガバナンス記録4件 | 衝突なし。記録の散逸防止 |
| `codex/smm-source-archive-case` | `Japanese_Equity_Lab/lib/profit_impact/` 一式、テスト100件、SMM pretax sensitivity fixture、開示pilot manifest、仕様・検証記録 | 単位・指標不一致時に税引前/純利益/セグメント利益から営業利益への変換を拒否する fail-closed 設計を保全するため。この設計は当該ブランチにのみ存在し、既定ブランチ移行で取り残される状態だった |

`Japanese_Equity_Lab/DECISIONS.md` の衝突は、append-only ログへの両側追記。15節すべてを日付順（2026-10-14のprofit-impact節を先、w0系列の2026-10-14〜10-17を後）に保持して解決した。節の削除・書き換えはしていない。

テスト結果: `Japanese_Equity_Lab/13_tests` で 2706 passed / 10 failed。失敗10件はすべて `test_post_edit_quality_gate_hook.py` で、マージ前の `codex/w0-research-current-state` でも同一の10件が失敗する（ローカルvenv前提のため本環境では再現不能）。マージ起因の退行はない。新規取り込み分の `test_profit_impact.py` / `test_profit_impact_preflight.py` は100件全通過。

## 5. 現契約のオーナー申告

`EVIDENCE_REGISTER.md` は `CURRENT_PLAN=UNKNOWN` としていた。`W0_RESULT.md:31` が指定する方法（秘密を含めないオーナー申告）により更新する。

- **オーナー申告（2026-11-21）**: J-Quants スタンダードプラン加入中、API取得・利用可能
- スタンダードプランの公開条件: 月額3,300円（税込）、データ提供期間は過去10年分
- 本記録は申告であり、契約dashboardや契約書による独立検証ではない。rate上限、全銘柄カバレッジ、上場廃止銘柄の取得範囲、予想データの完全供給は依然UNKNOWN（W3対象）

## 6. W0_RESULT.md 移行条件への対応

| 移行条件（`W0_RESULT.md:30-33`） | 対応 |
| --- | --- |
| 研究の正本・将来の安定ブランチの採用先を決める | §3で `main` に決定 |
| 既定変更・既存Draftのマージ承認と分離する | §3と§4を別の承認として記録 |
| 現契約の確認方法を承認する | §5でオーナー申告方式を採用・実施 |
| 過去raw成果物の所在確認を承認する | **不承認**。§1でUNKNOWN恒久確定とし、探索を打ち切る |
| 既使用/閲覧済み/UNKNOWN/将来予約の区別を決める | **未決**。W1（最小版）で決定する。2016–2023/2024/2025 の分割案は提案段階であり、本文書では承認しない |
| Locked解除・製品受入・FROZEN・マージの権限留保 | 維持。§2のルールがその行使方法を定める |

## 7. 本クローズが主張しないこと

- 過去に正式な承認やFROZEN宣言が存在したことの証明ではない
- `CAPABILITY_MATRIX.md` の各UNKNOWN、`EVIDENCE_REGISTER.md` のデータ適格性UNKNOWN（§5で更新した契約申告を除く）は解消していない
- `W0_RESULT.md:22` の「凍結288の照合は全FROZEN境界の網羅監査ではない」という留保は維持する
- 研究成果・製品の受入ではない。W0は現状の可視化であり、その性格は変わらない
- `W0_RESULT.md:24` の独立監査の区別は維持する。本クローズは外部独立監査ではなく、オーナー判断の記録である

## 次工程

W1（データ利用履歴・期間隔離の最小版）へ移行可。W2以降の順序と各工程の受入基準は、別文書「Japanese_Equity_Lab 完成までの方針書」で定義する。
