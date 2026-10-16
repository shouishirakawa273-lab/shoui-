# Completion backlog and next bounded implementation

2026-10-17 Japan. Starting HEAD51c36eb01d0be6fab0240be804f91766016960f7. Product scope is the five gates recorded in branch codex/development-governance:development/2026-10-14_PRODUCT_ACCEPTANCE.md, not the entire Lab.

| Gate | Available engineering evidence | Remaining mandatory acceptance | Dependency |
|---|---|---|---|
| G1 actual data/PIT | BLS capture-only scheduled acquisition; company source/integrity primitives | Eligible real-company input set and actual availability/source bytes | External/company evidence; SMM blocked |
| G2 macro→company profit | Exposure bridge with explicit assumptions, synthetic independent verification | Valid company metric/direction/basis/coverage and independently justified period assumptions | Company evidence; event response must not become driver automatically |
| G3 profit→valuation→returns | Valuation and D0111 v1 public APIs, independent synthetic tests | Connect actual bridge forecast outputs to returns on shared explicit terms; later real-company acceptance | Single synthetic integration is actionable now; real inputs blocked |
| G4 reproduce | Separate D0110 and D0111 deterministic demos | One executable path carrying the actual bridge outputs into valuation/returns with all intermediate lineage; later eligible historical replay | Synthetic integration actionable now; historical evidence blocked |
| G5 explanation/operation | Per-module evidence and rejection labels, BLS receipts | One path report with assumptions/source refs/intermediate values/hashes/limits and failure propagation | Synthetic report actionable now; actual company explanation follows data |

Selected necessary slice: one deterministic synthetic exposure→forecast→valuation→scenario-return executable report. Existing D0111 demo constructs its own forecasts; existing D0110 demo stops at valuation. Do not present this integration as a new financial formula or actual company acceptance. G1..G5 remain unaccepted as complete real-product gates. Whole-product percentage/time-to-completion unassessed; no unverified weighted score.

## Acceptance fixed before implementation

New scripts/research_path_demo.py and one dedicated test only. Existing production/frozen files and demos unchanged. Reuse scripts.d0110_demo.synthetic_bridge_request as explicit synthetic input builder (no test helpers); call public compute_exposure_bridge, evaluate_forward_valuation and compare_scenario_returns in sequence, passing the actual BridgeResult baseline/replay forecasts rather than constructing unrelated replacements.

Report JSON contains full hashable request, bridge and forecasts, multiple/balance sheet, valuation pair, shared return terms and return result, format/version, fixed cutoff, synthetic=true/empirical_validation=false and limitations. Include top-level artifact hash excluding itself. All phases use explicit fixed Decimal context and caller context remains unchanged. No dependence on wall-clock, network or filesystem output. Script prints JSON; identical invocation from another working directory reproduces artifact hash. Explicit assumptions are not event-derived causal evidence.

Inject future_driver option for negative-path verification: nonSUCCESS bridge prevents valuation and return creation; report rejection phase/reason and null downstream values. Do not construct successful placeholders. Other contract violations may remain explicit exceptions rather than silently repaired outcomes. No claims of general real-input JSON parser or persisted replay infrastructure in this bounded example.

Nonzero price80/dividend3/entry1/exit2 with explicit shared basis and horizon; selected BASE copper assumption100→110 gives operating income100→120, multiple8/net debt50/shares10 gives value75→91. D0111 net -5/81→11/81. Non-target forecasts/scenarios unchanged. Independently verify arithmetic, cross-stage IDs/hashes and exact results, input/context invariance, future-driver rejection, separate-process CLI/cwd reproduction. Do not use the old demo's different synthetic company identity without aligning new terms to actual request entity.

Single writer; read-only design audit and independent verification on one complete fixed SHA with no writer self-evaluation passed first. Initial review1+blocker closure1 max. Explicit new-test/necessary3 existing-file allowlist; H0001/Locked excluded. Full CI-equivalent mypy and scoped lint/format before publication. No merge/FROZEN/new real-data research/scheduler changes or additional company expansion.
