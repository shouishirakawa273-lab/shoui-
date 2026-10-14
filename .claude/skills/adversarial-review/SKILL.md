---
name: adversarial-review
description: >-
  Adversarially reviews an implementation or research hypothesis in
  Japanese Equity Lab for hidden assumptions, bias, and overfitting risk,
  without defaulting to a negative conclusion. Use after implementing a
  strategy/hypothesis/data pipeline change, or when asked to
  skeptic-review something. Read only, reports findings, never fixes
  them, never issues buy/sell judgments.
paths: Japanese_Equity_Lab/**
---

# Adversarial Review

**DEFAULT PROCESS = ADVERSARIAL. CONCLUSION = NEUTRAL UNTIL SUPPORTED.**
This mirrors `RESEARCH_RULES.md` §0.5 ("DEFAULT STANCE = DISCONFIRM, NOT
CONFIRM") — the same principle applied to code/design review instead of
evidence retrieval.

You are reviewing someone else's (possibly your own, from an earlier turn)
implementation or research design as an independent skeptic, not as its
author. Two failure modes to avoid equally:

- **Confirmation**: accepting the implementation's own framing and checking
  only what it claims to check.
- **Negative bias**: manufacturing problems to appear thorough, or
  concluding "this is broken" without evidence. A clean implementation
  should get a clean review.

This skill never issues a buy/sell judgment or a trading recommendation —
that is out of scope regardless of what the review finds.

## Checklist

Work through whichever of these apply to what's being reviewed:

- Hidden assumptions (unstated preconditions the code/design relies on)
- Confirmation bias (a test or check written to validate the author's
  expectation rather than to falsify it)
- Selection bias (a sample, universe, or date range chosen after seeing
  results)
- Survivorship bias
- Look-ahead leakage (if PIT-specific, prefer the dedicated `pit-audit`
  skill for depth; still flag here if obviously present)
- Multiple testing (many variants tried, one reported, no correction)
- Overfitting (parameter choices that fit noise in a specific sample)
- Convenient fixture (a test fixture shaped to make the implementation pass
  rather than to represent real data)
- Test tailored to implementation (test asserts what the code happens to
  do, not what it should do)
- Silent fallback (an error or missing case swallowed and replaced with a
  default instead of surfaced)
- `unknown → zero` (treating an unresolved/missing value as `0`)
- `unknown → false` (treating an unresolved/missing boolean as `False`,
  e.g. via Python truthiness on an empty string)
- `missing → no event` (absence of a record treated as evidence nothing
  happened, rather than evidence of nothing observed)
- `missing → not applicable` (empty value assumed structurally inapplicable
  without a confirmed reason)
- Schema drift (a provider field rename/addition silently mishandled)
- Provider semantics mismatch (assuming an endpoint behaves like a similar
  one — e.g. assuming date-range filtering that isn't actually supported)
- Origin source vs. delivery provider confusion (crediting data to the
  wrong party, e.g. attributing EDINET-origin data to J-Quants without
  distinguishing `originating_source` from `delivery_provider`)
- Conflicting evidence suppression (contradictory findings dropped rather
  than kept alongside supporting ones)
- Alternative explanations (is the result explained by something other than
  the hypothesis under test?)
- Absence of a counterfactual (no comparison against what would have
  happened without the change, or against a benchmark)
- Accidental benchmark advantage (the comparison benchmark isn't actually
  comparable — different universe, period, or cost assumptions)
- Result-dependent parameter choice (a threshold/window picked after
  looking at the outcome it produces)
- Retrospective hypothesis rewriting (the stated hypothesis was quietly
  adjusted to match what the data showed)

## Output format

For each finding:

```
### [SEVERITY] Claim being challenged: <what the implementation/design asserts or assumes>
- Counterargument: <why this may not hold>
- Alternative explanation: <if applicable — what else could produce the same result>
- Evidence needed: <what would resolve the question>
- Severity: BLOCKER / HIGH / MEDIUM / LOW
```

End with a verdict: `PASS`, `PASS_WITH_CONCERNS`, or `FAIL`, with a one-line
reason. `PASS` requires stating what was checked, not just the absence of
findings.
