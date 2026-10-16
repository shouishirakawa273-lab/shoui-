# D0111 one-company input readiness: Sumitomo Metal Mining

Date: 2026-10-16 (Japan). Company candidate: Sumitomo Metal Mining, securities code5713. Current API requires an explicit entity ID matching both valuations and price; the securities code alone is not a certified entity/basis mapping.
Status: BLOCKED_INPUT_EVIDENCE. No company return was calculated, no numeric input was invented, and no new source research or tests were run.

## Evidence boundaries

Read existing local secondary records: handoff/2026-10-14_D0110_3_SMM_SOURCE_FIT.md, 2026-10-14_SMM_SOURCE_CONDITIONS.md and 2026-10-14_SMM_INPUT_CONTRACT_FIT.md. They reference the company's 2026-08-10 presentation, pages15/19, but this round did not retrieve or authenticate that PDF. Their quoted numbers are inherited observations, not newly independently verified source facts. Copies are retained as secondary evidence under development/evidence/d0111-readiness/.

The existing investigation limit for the same SMM accounting issue is exhausted. This round read the conclusions only and did not repeat searches. It does not conclude that compatible evidence cannot exist.

At inspected HEAD ed80f4a, tracked data/ contains only .gitkeep; the working data/ directory also contained only .gitkeep. No SMM price/dividend/basis evidence appeared in tracked development/evidence. This is a scoped inventory, not a claim about every branch, external account or the user's other files.

The financial_summary_v2.json fixture explicitly combines synthetic disclosure rows and a few values previously observed for another company without verified date/row correspondence. It is not a substitute for a real SMM PIT dataset. D0111 demo is explicitly synthetic. BLS capture is a US CPI index series and supplies none of the company-specific inputs below.

## Input matrix and release conditions

| Input | Existing evidence | Readiness / next qualifying evidence |
|---|---|---|
| Source documents and observation times | Prior notes reference one company presentation; raw source archive not established on current branch | Preserve actual bytes/hash/source and actual retrieval time; no invented historical SYSTEM_OBSERVED |
| Compatible baseline/replay valuation pair | Synthetic pair only; SMM sensitivity described as pretax, existing forecast/valuation route uses operating income | Primary blocker: operating-income-compatible sensitivity or a verifiable accounting reconciliation with matching scope/period/assumptions; not a label/tax-rate substitution |
| Financial period and common cutoff | Prior notes identify a forecast vintage with March/December assumptions; joint applicability unresolved | Explicit period/version/scope and verified evidence availability. No historical hour inferred from publication date |
| Macro target scenarios and driver assumptions | No qualified SMM pair; direction, joint use and inventory coverage remain unresolved | Separately supported scenario assumptions/target roster; do not derive period driver from event-window association |
| Baseline sales/margins, multiple and balance sheet | No qualified SMM bundle identified | Source-linked compatible values, units/currency/shares and availability; same multiple/BS for both sides |
| Reference price | No qualified SMM record identified | Positive Decimal, source, entity/currency, observed<=available<=cutoff, documented adjusted/unadjusted basis |
| Shares / price and valuation basis | No qualified SMM attestation identified | Both valuation hashes, priceID/sharecount and basis evidence/confirmation; inspect corporate actions for selected period. Caller attestation does not authenticate the source |
| Dividend | No qualified period assumption identified | Explicit per-share assumption for (cutoff,exit], source/research rationale and pre-cutoff availability. Do not insert subsequent actual dividends retrospectively |
| Entry/exit costs | No explicit cost policy for this company example | Declared nonnegative per-share assumptions, currency and rationale/time. An explicit zero policy is possible; a missing value is not zero |
| Exit mapping | No qualified mapping identified | Target financial period, future exit date, explicit conditional-realization rationale and availability<=cutoff |

No arbitrary historical cutoff or exit date has been selected merely to make the API pass. Choose them when eligible evidence can support the intended observation/research basis. A newly observed source can support a current/future research experiment; it does not prove past pipeline availability.

## Outcome and next actionable boundary

The current API is structurally capable of accepting an eligible real bundle; available evidence is not yet eligible. Building more return formulas or downloading an isolated stock price does not resolve the upstream profit-metric blocker.

Resume when new compatible primary evidence or an already-qualified baseline/replay bundle becomes available. First authenticate and reconcile that evidence within a bounded new task, then fill the downstream matrix and execute the unchanged API. No additional-company search, broad metric redesign, new provider contract or probability model is authorized by this readiness check. Keep partial input records non-executable and explicitly incomplete.

This establishes one-company readiness requirements, not real-company technical acceptance or investment effectiveness. No H0001/Locked Test, frozen change, runtime/scheduler change, merge or FROZEN.
