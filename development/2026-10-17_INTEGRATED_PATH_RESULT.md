# Analysis-to-portfolio integrated synthetic acceptance result

2026-10-17 Japan. Fixed reviewed code9b36bbe765596f67d4ec2a4a68dfef43f03ee852; base505fd456d5ac10612be414acf8fa624e40b53a9b (Draft PR17). Accepted as a bounded synthetic integration; not product/real-company acceptance, merge or FROZEN.

## What is connected

One process now passes actual typed outputs through company exposure bridge→both fundamental forecasts→both valuations→D0111 scenario returns→D0112 desired portfolio risk→D0113 construction→output risk. It does not merely concatenate independent demo summaries or replace handoffs with convenient numeric fixtures.

The report retains full request, sources/references, valuation/cash/basis inputs, all intermediate records and hashes, both desired and constructed portfolios, audit/rejection reasons, fixed rules and artifact hash. It explicitly states synthetic=true, empirical_validation=false and product_acceptance=false even on success. Legacy production modules and previous demos are unchanged.

Example: independent synthetic copper-period assumption100→110 produces BASE operating income100→120 and value75→91. Price80/dividend3/entry1/exit2 gives conditional net -5/81→11/81. Desired weight0.8/cash0.2 violates company0.5 and sector0.6 caps; this is a valid diagnostic, so construction proceeds. Explicit rule produces weight0.5/cash0.5, releasedcash0.3 and D0112 declared constraints pass. Macro baseline/replay comparisons retain the same holdings within each portfolio. Desired-versus-constructed differences arise from allocation policy, not causal macro effects. One company with cash is not diversification or a recommendation.

## Reproduce

From repository root with project Python:

```text
.venv/Scripts/python.exe -B Japanese_Equity_Lab/scripts/integrated_research_portfolio_demo.py
.venv/Scripts/python.exe -B Japanese_Equity_Lab/scripts/integrated_research_portfolio_demo.py --future-driver
.venv/Scripts/python.exe -B Japanese_Equity_Lab/scripts/integrated_research_portfolio_demo.py --bad-joint-binding
```

First command emits the full path JSON. Future driver fails at the bridge with all downstream valuations/returns/risk/construction null. Incorrect joint comparison binding fails at PORTFOLIO_RISK after valid upstream analysis, with no desired-risk success or construction result. These refusal demonstrations exit0 after emitting a rejection artifact; inspect rejection/status, never equate process exit with economic/product acceptance. No network or file writes. Absolute script path works from another working directory.

## Independent evidence

Read-only design audit at the fixed complete SHA found no blockers. Separate verifier used specification/diff without prior writer self-evaluation, then recorded before/after same SHA and clean status:

- Explicit7-test-file allowlist171 passed/1 deselected, exit0. H0001/Locked not run.
- CI-equivalent mypy197 source files, no issues, exit0.
- Public-call wrappers independently captured actual object identity for forecast→valuation, valuation→returns, return→position and desired→construction handoffs.
- Independent Fraction formulas all3 scenarios/both sides,0.8/0.5 portfolio weighting, downside after aggregation, cash/releasedcash and desired versus final constraint status.
- All nested records/artifact hashes, binding and derived lineage, input/context invariance.
- Separate processes/different cwd reproduce full JSON for success and both rejection cases; no downstream successful placeholders.
- Frozen288 Git content unchanged base→reviewed SHA and reviewed SHA→working. Raw-byte equality across newline normalization not claimed.

Commands/cwd/SHA/exit, probe and all3 emitted artifacts retained under development/evidence/integrated-path/. Null Git status denotes no status output. Design conclusion is a coordinator record of the separate agent's report, not a separately persisted full transcript. Writer scoped lint/format passed before commit. Remote CI is checked separately at published HEAD; local test counts are not remote log counts. No closure review required.

## Acceptance boundary and remaining gaps

This verifies one synthetic vertical route across existing D0110.3/D0109/valuation/D0111/D0112/D0113 APIs. D0110.1 surprise, D0110.2 observational response and D0110.4 forecast evaluation are separate paths; this artifact does not certify a complete empirical macro mechanism or all roadmap branches.

Real-company compatible inputs/raw evidence/PIT, credible joint scenarios and share basis, policy suitability, theme/event/liquidity/correlation/VaR/CVaR/stress checks, execution mechanics and real forecast/portfolio effectiveness remain open. Existing unsupported-risk flags propagate even when declared constraints pass. Hashes establish internal integrity, not source authenticity or economic truth. Fixed synthetic output is not a historical SYSTEM_OBSERVED claim.

The old single-company G1..G5 and tentative weights do not measure the expanded portfolio roadmap. No entire-product percentage or delivery date is inferred. Synthetic route integration is now available, but real-product acceptance remains incomplete and the Draft stack unmerged. No additional D-number, optimizer, UI/loader framework or repeated SMM source investigation added. Runtime/scheduler/sources/frozen files preserved; no prohibited tests/merge/FROZEN.
