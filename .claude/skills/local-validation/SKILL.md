---
name: local-validation
description: >-
  Standard procedure for handing off real-API validation to the user's
  local PC when this Claude Code environment cannot reach the external
  API directly. Use whenever a new or changed Data Source Adapter needs
  real-data confirmation and this session's network egress is blocked.
  Windows PowerShell output. Never prints secret values.
paths: Japanese_Equity_Lab/**
---

# Local Validation

Use this when a Data Source's official network egress is unreachable from
this Claude Code environment, so real-API validation has to happen on the
user's local PC instead. Applies to any source, not just J-Quants — reuse
this structure for TDnet/EDINET/Macro/News adapters in later Phases too.

## Principles

- **Start small.** Never hand the user a command that pulls the full
  market or a multi-year range on the first attempt. Smoke-test one code,
  one short date range, first.
- **Never print a secret value.** Not the API key, not a bearer token, not
  a session cookie. A *presence* check is fine; the value itself is not.
- **PowerShell, not bash**, for anything the user runs locally on Windows.
- Every command block must be copy-pasteable as-is — no placeholder the
  user has to remember to fill in without it being obviously a placeholder
  (use `<CODE>`-style angle brackets for anything that must be substituted).

## Secret presence check (never the value)

```powershell
if ($env:JQUANTS_API_KEY) {
    "API key is set"
} else {
    "API key is NOT set"
}
```

Never generate or suggest `echo $env:JQUANTS_API_KEY` (or any language's
equivalent) — that prints the secret itself. Apply the same presence-only
pattern to every future source's credential variable name.

## Output sections

Produce all of the following, in order, tailored to the specific source
and adapter being validated:

**A. Sync command** — how the user pulls the latest branch/commit locally
(`git fetch` / `git checkout` / `git pull`, as appropriate).

**B. Safe API key presence check** — the pattern above, adapted to the
source's actual credential env var name.

**C. Small smoke test** — the smallest possible real call: one code (or
equivalent minimal unit), a short date range, using the project's existing
fetch script/CLI rather than a one-off script.

**D. Raw snapshot fetch** — the command that persists the smoke-tested
response as a local raw snapshot file, using this Lab's existing snapshot
tooling (not a new ad hoc save mechanism).

**E. Raw inspection** — how to open/read the saved raw file directly
(`Get-Content`, or a `python -c` one-liner) so the user sees the actual
wire format before anything is normalized.

**F. Diagnostic command** — this Lab's existing read-only diagnostic
script for the data type in question, if one exists (e.g.
`scripts/jquants_financial_summary_diagnostic.py`), run against the
snapshot from step D.

**G. Offline rerun** — a command that re-runs the relevant
normalization/analysis purely from the saved local snapshot, with no
network call, to confirm offline reproducibility (per this Lab's Offline
principle, D0042).

**H. Expected observations** — a short, falsifiable list of what the user
should see if things are working (e.g. "N records", "DiscDate values
within/outside the requested range are both fine", "no traceback"). This
lets the user self-check without needing to paste output back for trivial
cases.

**I. What to paste back** — tell the user exactly what terminal output (if
any) is worth pasting back into the conversation, and reassure them not to
paste anything containing the secret value itself.

## Do not

- Do not request the user paste the API key itself into chat.
- Do not suggest disabling TLS verification, editing hosts files, or any
  other network-bypass workaround for this session's own egress block —
  that block is the reason local validation exists in the first place.
- Do not escalate from a single-code smoke test straight to a bulk/mass
  fetch without an explicit go-ahead from the user after the smoke test
  succeeds.
