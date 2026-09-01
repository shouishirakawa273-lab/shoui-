---
name: pit-audit
description: >-
  Audits Japanese Equity Lab code, tests, and data pipelines for
  Point-in-Time (look-ahead) leakage: timestamp confusion,
  revision/restatement leakage, survivorship bias, forward-fill leakage.
  Use when reviewing fundamentals/PIT/revision/universe/backtest code or
  before closing a Phase. Read only, reports findings, never fixes them.
paths: Japanese_Equity_Lab/**
---

# PIT Audit

You are auditing for Point-in-Time (look-ahead) leakage in the Japanese Equity
Research Lab (`Japanese_Equity_Lab/`). This is an audit, not a fix pass:
**report findings, do not edit files.** If invoked as the `pit-auditor`
subagent, this restriction is structural (no write tools); if invoked inline,
follow it as an instruction anyway — do not slip into fixing what you find.

## Scope

Audit whatever code/tests/docs are named in the request, or — if none are
named — the most recently changed files under `Japanese_Equity_Lab/lib/`,
`Japanese_Equity_Lab/scripts/`, and `Japanese_Equity_Lab/13_tests/`
(`git diff`/`git log` to find them).

## Timestamp fields to trace

For every record type touched, confirm which of these fields exist, whether
they're populated, and whether the code ever conflates two of them:

- `published_at` / `market_public_at` — when the market could have known.
- `provider_available_at` / `available_at` — when this Lab's data pipeline
  could have known (must not default to `market_public_at` unless the basis
  is genuinely `EXACT`, per `lib.evidence.model.AvailabilityBasis`).
- `retrieved_at` — when this session fetched it (never a PIT boundary).
- `decision_at` / `execution_at` — when a hypothetical decision/trade would
  have been made.

## Checklist

**General PIT / leakage:**
- Future revision leakage (a later-arriving value used before its
  `available_at`/`published_at`)
- Restatement leakage (latest-restated values silently replacing
  as-reported historical values)
- Corporate action leakage (adjustment factors applied before they were
  knowable)
- PIT Universe leakage (a security included in a past universe that it
  wasn't actually a PIT member of)
- Survivorship bias (delisted/renamed securities silently dropped from
  historical universes)
- Delisting handling / listing-date handling (off-by-one or missing bounds)
- Provider availability fallback (silently substituting `market_public_at`
  or `retrieved_at` when `provider_available_at` is genuinely unknown)
- Missing timestamp inference (guessing a time-of-day, or deriving a date
  from an opaque identifier like `DiscNo`, instead of leaving it unknown)
- End-of-sample censoring (a position/window that runs past the data's end
  treated as a normal exit rather than censored)
- As-of boundary correctness (`<=` vs `<`, timezone-naive vs tz-aware
  comparisons)
- Forward-fill leakage (treating "last known value" as "current value"
  across a gap that wasn't actually observed)
- Future raw records leaking into past views (an `as_of()`/`fundamentals_as_of()`
  call that returns a record whose availability postdates `decision_at`)

**Fundamentals-specific** (`lib/fundamentals/`):
- Actual vs. Forecast conflated into one series
- Current FY vs. Next FY conflated
- Cumulative vs. standalone period values conflated (e.g. 2Q cumulative
  treated as Q2 standalone)
- Consolidated vs. non-consolidated conflated
- Accounting standard ignored where it changes null semantics (e.g. an
  IFRS/USGAAP field with no JGAAP equivalent treated as `0` instead of
  `NOT_APPLICABLE`)
- Correction vs. forecast revision conflated (a later disclosure treated as
  correcting an earlier one without a confirmed revision relationship)
- Raw coverage vs. research window conflated (assuming a fetch's requested
  date range bounds what was actually returned)

## Output format

Report findings only — do not modify files. For each finding:

```
### [SEVERITY] <one-line summary>
- Evidence: <file path>:<line/function/test name>
- Risk: <why this would distort a research result, concretely>
- Suggested Verification: <what to check/run to confirm or rule this out>
```

Severity: `BLOCKER` (would silently corrupt results) / `HIGH` / `MEDIUM` / `LOW`.

If a checked area passes, say so explicitly — list what was checked and
confirmed clean, not just what failed. A silent "no findings" is not
distinguishable from "didn't check"; an explicit PASS list is.

End with a one-line overall verdict: `PIT AUDIT: CLEAN` or
`PIT AUDIT: N FINDINGS (highest severity: X)`.
