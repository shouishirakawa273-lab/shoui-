# 承認台帳

FROZEN宣言、Locked解除、製品受入、マージはこのファイルへの1行追記で成立する。追記のない変更はFROZEN扱いにしない。

- 適用開始: 2026-11-21（`development/w0/2026-11-21/W0_CLOSURE.md` §2）
- 過去には遡及しない。2026-11-21以前の承認状態は `W0_CLOSURE.md` §1 のとおりUNKNOWN恒久確定
- 形式: `日付 / 対象 / 種別 / 承認者 / 根拠commit`
- 新しい行は末尾に追記する。既存行は書き換えない

| 日付 | 対象 | 種別 | 承認者 | 根拠commit |
| --- | --- | --- | --- | --- |
| 2026-11-21 | `codex/development-governance` → `main` | マージ | owner | `2dfa1a8` |
| 2026-11-21 | `codex/smm-source-archive-case` → `main` | マージ | owner | `67a0a7f` |
| 2026-11-21 | 既定ブランチを `claude/repo-creation-setup-ejmkje` から `main` へ変更 | 正本ブランチ決定 | owner | `W0_CLOSURE.md` §3 |
| 2026-11-21 | W0を受入としてクローズ、W1移行の停止を解除 | 製品受入（W0工程） | owner | `W0_CLOSURE.md` |
