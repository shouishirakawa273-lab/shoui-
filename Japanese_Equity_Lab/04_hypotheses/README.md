# 04_hypotheses/

Hypothesis Registry。`lib/schemas/hypothesis.Hypothesis` に対応する。
**仮説は必ずバックテスト前に登録する**(RESEARCH_RULES.md 原則1)。

ファイル名は `H<連番>_<日付>_<内容>.md`(例: `H0001_2026-08-16_earnings_revision_underreaction.md`)。

`status`: `DRAFT` → `LOCKED` → `TESTED` → `REJECTED` / `PAPER` → `VALIDATED`。
LOCKED後に条件を変える場合は元のファイルを書き換えず、新しいHypothesis ID
(`H0002`等)を新規ファイルとして発行し、`parent_hypothesis_id` で系譜を残す
(`Hypothesis.revise()` 参照)。
