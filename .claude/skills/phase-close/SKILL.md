---
name: phase-close
description: >-
  Standard end-of-Phase closing procedure for Japanese Equity Lab (scope
  check, regression, docs, PIT/adversarial review, status verdict).
  Invoke explicitly with /phase-close when a Phase's work is believed
  done; Claude does not run this on its own.
disable-model-invocation: true
paths: Japanese_Equity_Lab/**
---

# Phase Close

This is a checklist you work through and report against — it is not a
script that commits or pushes anything by itself.

**This skill never commits or pushes by default.** Only stage, commit, or
push if the task prompt that invoked `/phase-close` explicitly asked for
it. Otherwise, stop after reporting the verdict and let the user decide.

**This skill never advances to the next Phase on its own.** Reporting
`COMPLETE` is a status report, not permission to start the next Phase —
that requires a separate, explicit instruction from the user.

## Procedure

Work through all 15 steps. Don't skip a step because it seems redundant
with an earlier one — report each explicitly so the record is complete.

1. **Phase scope**: Restate what this Phase was supposed to cover, from the
   task prompt or the relevant `DECISIONS.md` entry that opened it.
2. **Acceptance criteria**: List the specific criteria the Phase was
   supposed to satisfy (from the kickoff instructions), and check each one.
3. **git diff**: Review the full diff of everything changed this Phase
   (`git diff` against the last relevant commit, or `git status` if
   uncommitted). Confirm it matches the stated scope — nothing unrelated
   crept in.
4. **Protected paths**: Confirm `core/`, `app.py`, `tests/` (the existing
   Screening Tool) show zero changes: `git diff --stat -- core/ app.py tests/`
   must be empty, unless this Phase explicitly targets the Screening Tool.
5. **Lab pytest**: Run `pytest Japanese_Equity_Lab/13_tests/ -q` (or
   `cd Japanese_Equity_Lab && pytest 13_tests/ -q`). All tests must pass.
6. **Screening Tool pytest**: Run `pytest tests/ -q` from the repo root.
   All tests must pass, and the count should match what it was before this
   Phase (no tests silently deleted or skipped to "fix" a failure).
7. **ruff**: Run `ruff check .` and `ruff format --check .` from the repo
   root. Both must be clean.
8. **mypy**: Run `mypy core app.py scripts Japanese_Equity_Lab/lib` from
   the repo root. Must be clean.
9. **Documentation update**: Confirm the Phase's design decisions and any
   spec deviations are written down, not just implemented — check
   `RESEARCH_RULES.md`, `DATA_SOURCE_ARCHITECTURE.md`, `EVIDENCE_MODEL.md`,
   `README.md` for whichever of these the Phase actually touched
   conceptually.
10. **DECISIONS.md**: Confirm a `DECISIONS.md` entry exists for this Phase
    (or this Phase's follow-up), with unverified/assumed items clearly
    marked as such, not stated as confirmed fact.
11. **Known Limitations**: Confirm unresolved/unverified items are listed
    explicitly somewhere durable (a `DECISIONS.md` limitations section, a
    Catalog descriptor's `known_limitations`, etc.), not silently dropped.
12. **PIT Audit result**: Run or reference a `pit-audit` pass (inline, or
    via the `pit-auditor` subagent) over this Phase's changes if the Phase
    touched PIT-relevant code (fundamentals, universe, revision, backtest
    timing). Record the verdict.
13. **Adversarial Review result**: Run or reference an `adversarial-review`
    pass (inline, or via the `skeptic-reviewer` subagent) over this Phase's
    implementation/hypothesis, if applicable. Record the verdict.
14. **git status**: Confirm the working tree is in the state you think it
    is — nothing unexpectedly staged, nothing unexpectedly still dirty.
15. **Completion status**: Assign one of:
    - `COMPLETE` — everything above passes and no external/local validation
      is outstanding.
    - `CODE_COMPLETE_AWAITING_LOCAL_VALIDATION` — code, tests, and docs are
      done, but real external validation (e.g. a live API this session
      cannot reach) is still needed before calling it fully done.
    - `BLOCKED` — something above failed and can't be resolved without a
      decision from the user (spec ambiguity, a failing check with no safe
      fix, a missing credential).
    - `PARTIAL` — some acceptance criteria are met and some are knowingly
      deferred; state exactly which.

## Output format

Report each of the 15 steps with a short pass/fail/note line, then the
final Completion Status with a one-sentence justification. If any step
failed, say what would need to happen to pass it — don't silently mark a
failing step as passing to reach `COMPLETE`.
