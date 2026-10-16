# D0111 v1 scope and acceptance gates

Date: 2026-10-16 (Japan). Inspected HEAD: ed80f4a3d038937110b8b7d307edeeccfbfdb28b; final code58470d850bf06c2a8160e5955931ff5efef03b2b. Draft PR #14. This is a current development decision, not recovered historical requirements or a FROZEN record.

## Scope decision

The explicit v1 calculation design is complete for the current scope. Do not repeatedly redesign it while waiting for empirical history. The unavailable original D0111 requirements remain a traceability limitation, not evidence of unspecified required features. Any later recovered material must be reconciled as a separately recorded scope change.

| Gate | Status | Evidence / remaining condition |
|---|---|---|
| Bull/Base/Bear gap, gross/net return, bear downside | Synthetic engineering accepted | IMPLEMENTATION_SPEC.md and RESULT.md; independent100pass/1deselected |
| Shared baseline/replay conditions, scenario deltas | Synthetic engineering accepted | Same cutoff/model/multiple/BS/price/cash/basis/exit contract; no causal attribution |
| PIT, integrity, Decimal reproduction, invalid-input rejection | Synthetic engineering accepted | Independent initial and closure evidence; same complete demo JSON/hash |
| Public forecast→valuation→return example | Synthetic engineering accepted | scripts/d0111_demo.py; entirely synthetic, no empirical certification |
| Published checks | Passed at ed80f4a | GitHub jobs116992936194/116992964404; no remote test count inferred |
| Real-company input bundle | BLOCKED_INPUT_EVIDENCE | Companion SMM input-readiness record; no actual complete pair available |
| Real-company point-in-time replay | Not accepted | Requires valid complete bundle, then fixed-SHA independent execution |
| Forecast effectiveness | Not evaluated | Own forecasts/consensus/prospective registration/history and prespecified assessment are separate dependencies |
| Integration into accepted branch | Not merged | Draft stack retained; no merge/FROZEN authority exercised |

## Required next work and stop conditions

1. Keep v1 formulas/API fixed while assembling one company's evidence-qualified input bundle.
2. For the chosen Sumitomo Metal Mining case, resolve operating-income compatibility before spending work connecting downstream price/dividend feeds. Do not rename pretax income as operating income or use taxes as a bridge.
3. If compatible baseline/replay is available, assemble common cutoff, price and share basis, dividend/cost assumptions and exit mapping. Future assumptions can be explicit research judgments with real creation/availability times; they need not be reported future facts. Missing values cannot silently become zero.
4. Only a complete eligible set proceeds to public API execution and independent fixed-SHA real-company validation. Partial data can be preserved as evidence but yields no successful company return.

No new probability weighting, trading decision, source-arithmetic recertification, multi-company expansion or accounting overhaul is needed for this slice. A CLI/UI and persistence beyond existing evidence are optional until a usable real input set demonstrates a concrete need.

Independent read-only gate reconciliation by a separate design agent at ed80f4a reached the same separation: minimal calculation satisfied, overall historical scope not certified, real-company gate open. No tests/network were repeated in this gate review. Whole-product completion percentage remains unassessed; gate counts are not a percentage.

## Authority

Current implementation contract: development/2026-10-16_D0111_IMPLEMENTATION_SPEC.md.
Implementation/evidence: development/2026-10-16_D0111_RESULT.md and development/evidence/d0111/.
This scope/gate record clarifies development acceptance only. All remain on the unmerged Draft branch. Earlier parallel draft is historical; it is not an additional competing implementation contract.
