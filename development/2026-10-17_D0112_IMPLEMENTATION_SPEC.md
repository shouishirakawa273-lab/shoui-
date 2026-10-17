# D0112 Portfolio Risk v1 — recovered role and new implementation contract

2026-10-17 Japan. Starting8ebd6d0e3e460290bbd9dbfc717b3ec7654be762, Draft PR15. User approved continuing to D0112 after verifying existing plans.

## Recovered evidence versus new design

The user-supplied architecture attachment c16209b0-07f1-400b-a26c-ee60698e8e2e/貼り付けたテキスト.txt contains D0112 Portfolio Risk Engine at line1219 and D0112 Portfolio Risk/D0113 Portfolio Construction at lines1384–1386. This is supplied conversation material, not a recovered detailed frozen specification. Its old percentages/delivery estimates are not adopted. All formulas/types/policies below are new explicit v1 engineering choices.

Existing lib/schemas/portfolio_rules.py expresses position/sector/theme/cash/event/liquidity constraints as a legacy schema. Do not modify or pretend full enforcement of that schema. v1 implements company/sector/cash constraints only; theme/event/liquidity/correlation/VaR/stress calibration remain unsupported and must be labelled. D0113 optimization, selection, orders and recommendations are out of scope.

## Inputs and definitions

New lib/portfolio_risk namespace, dedicated test and synthetic script only; existing code/frozen288 unchanged. Accept an immutable request with requestID, tuple of positions, cashweight, policy, common currency/decisioncutoff/exit_at, jointscenario attestation ref/available_at, cash-zero-return assumption ref/available_at and calculated_at. Each position has unique positionID, finite Decimal capitalweight>0, existing ReturnComparison, sector string and sector evidence ref/available_at. Entity comes from comparison.terms.price.entity_id; permit multiple positions of the same entity but aggregate company exposure and reject inconsistent sectors for that entity.

Weights are fractions of total starting capital INCLUDING entry costs in the denominator used by each D0111 net-before-tax return. They are not market-value weights and not an allocation recommendation. Long-only, no borrowing/shorts/FX/rebalancing. Sum(position weights)+cashweight exactly1 under fixed Decimal context; cash0..1. Policy explicitly declares maxcompany/maxsector (0..1), minimumcash(0..1), policyID/ref/available_at. Zero-position all-cash is allowed only with explicit common time/currency/attestations; no fake asset scenario inputs.

All records' hash integrity verified; every input comparison must have three unique BULL/BASE/BEAR enum scenarios, valid terms hash and matching common currency/cutoff/exit_at, aware timestamps and comparison.calculated_at<=request.calculated_at. Own calculated_at>=cutoff, cutoff<exit. Attestation/policy/sector/cash assumption availability<=cutoff. No backdating or inferred metadata. Comparison integrity does not authenticate economic truth; consume supplied existing return arithmetic without re-certifying source valuation.

Jointscenario attestation explicitly asserts that same-named BULL/BASE/BEAR across constituents are jointly applicable under its referenced common assumptions. Scenario-name coincidence alone is insufficient; this attestation is caller supplied, not statistical correlation or scenario authenticity proof. Each side uses the same holdings weights; no optimizing one arm. Entirely synthetic if any constituent carries SYNTHETIC; all-cash example labels synthetic explicitly via request mode. Reject synthetic constituents passed as real mode. Real mode remains NOT_EMPIRICALLY_VALIDATED.

## Outputs and arithmetic

For each scenario and side, portfolio conditional net-before-tax return=sum(weight_i * constituent net-before-tax return_i), cash contribution explicitly0. Delta=replay-baseline. Portfolio bear downside=max(0,-portfolio BEAR net), computed AFTER aggregation, not sum of standalone downside. It is conditional scenario loss, not maximum loss, VaR, CVaR, risk probability, realized performance or capital guarantee.

Return sorted company/sector weights, cashweight, explicit breaches for company>maxcompany, sector>maxsector, cash<minimumcash (equality satisfies limits). Concentration may be reported without implying sector labels are independently verified. Policy pass means only these declared constraints pass. Output unsupported checks list even on pass. Output references full request/inputs or hashed request, policy and attestation refs, all comparison hashes, fixed decimal rule version, result hash, labels CALLER_ATTESTED_JOINT_SCENARIOS/CONDITIONAL_ONLY/PRE_TAX/NON_ANNUALIZED/NO_PROBABILITY_WEIGHTING/NOT_PORTFOLIO_OPTIMIZATION/SOURCE_ARITHMETIC_NOT_REVALIDATED plus mode.

Fixed Context precision50 HALF_EVEN Emin-999999/Emax999999 explicit flags/traps, caller context/input unchanged. Nonfinite/bad metadata/mismatch/unknown sector/hash/PIT/duplicate IDs/weights invalid fail closed as ValueError; decimal range failures ValueError. Canonical position order by positionID before hashing/summing for deterministic input order independence; no mutable input repair. Canonical company/sector/scenario output order.

## Acceptance

At least two fictional companies, nonzero cash, explicit jointly applicable scenario assumptions. Build D0111 comparisons through public APIs (existing synthetic builder may be used with properly rehashed entity/forecast lineage, not a falsely named real company). Independent weighted Fraction/Decimal calculation all scenarios and both sides; offsetting bear case proves aggregate downside before floor. Samecompany aggregation, inclusive constraint bounds, failures one field at a time, all-cash, deterministic reorder/context/hash, no input mutation. A standalone public-API synthetic demo must disclose assumptions and unsupported checks, with no network/file writes.

Full CI-equivalent mypy and scoped lint/format; only new portfolio test and needed scenario-return/valuation integration allowlist, exclude H0001/Locked. One code writer, separate read-only design and independent verifier pinned to complete SHA; do not share writer self-evaluation first. Review1 plus blocker closure1 maximum. Result/spec/evidence to new Draft PR based on PR15, no merge/FROZEN/scheduler/source modifications. Existing overall product G1..G5 measure the earlier single-company path only; D0112/13 expands roadmap and cannot be rolled into old weights to claim percentage. Whole-product percentage remains unassessed.

## Pre-implementation audit resolutions

Exact capital conservation and limit comparison use exact Decimal rational values (e.g. Fraction(Decimal)), not rounded context sums: tiny overweight or threshold excess must not disappear. Reported arithmetic may be rounded under the fixed calculation context, but violations use exact exposures. No unannounced tolerance. Joint-scenario attestation includes the canonical sorted tuple of all constituent comparison hashes, preserving multiplicity; require exact match. Cash-only binding is empty and explicitly declared. Cash0return is an assumption, not a safety/interest guarantee; no dividend reinvestment or duplicate cost deduction. Unknown placeholder sector values (empty/UNKNOWN/UNCLASSIFIED) rejected.
