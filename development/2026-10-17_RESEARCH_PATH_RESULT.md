# Connected synthetic research path result

Date2026-10-17 Japan. Reviewed code SHA2a458a848966a52a1f1bcddd738a8a4c3bcc7a3c; base51c36eb01d0be6fab0240be804f91766016960f7 (Draft PR14). Engineering acceptance: synthetic connection/reproduction only. No real-company product-gate acceptance, merge or FROZEN.

## Delivered

One public-API path now carries actual exposure bridge baseline/replay forecasts into valuation and then D0111 scenario returns. No independent replacement forecasts are manufactured at the handoff. Full request, source references, intermediate results/hashes, multiple/BS, shared cash/price/basis/exit terms, result and artifact hash are emitted in one JSON report. It uses the existing explicitly fictional input builder, not a company disclosure or a test helper.

The selected BASE period copper assumption100→110 changes operating income100→120 and per-share value75→91; Bull/Bear remain unchanged. With reference price80, dividend3, entry1, exit2, net return is -5/81→11/81. These are conditional, unweighted, pretax/nonannualized assumptions, not performance evidence. No observed FX window or CPI result is automatically converted into the copper assumption.

From repo root:

```text
.venv/Scripts/python.exe -B Japanese_Equity_Lab/scripts/research_path_demo.py
.venv/Scripts/python.exe -B Japanese_Equity_Lab/scripts/research_path_demo.py --future-driver
```

The first emits the complete synthetic path. The second emits bridge rejection with phase/reason and null valuations/returns/terms; it intentionally exits normally after producing a rejection report, so callers must inspect rejection/status rather than treating exit0 as economic acceptance. No external retrieval or file writes. Absolute script invocation works from another working directory.

## Independent evidence

Initial read-only design audit at the fixed code SHA found no blockers. A separate verifier independently checked the same SHA, with no writer self-evaluation supplied first. No closure review was required.

- Explicit four-file allowlist:107 passed/1 deselected, exit0. H0001/Locked excluded.
- CI-equivalent mypy:193 source files, no issues, exit0.
- Independent Fraction arithmetic for all scenarios, cross-stage forecast/valuation/return references and hashes, input/context invariance, future-driver refusal and separate-process/different-cwd JSON identity.
- Frozen288 Git diff empty base→reviewed SHA and reviewed SHA→working; no raw-byte equality claim across CRLF normalization.
- Before/after full SHA and clean state, commands/cwd/exit and emitted success/rejection examples retained under development/evidence/research-path/. null Git status in JSON denotes no status output.

The design-audit summary is recorded here from the separate agent's report; it is not a separately persisted full review transcript. Local scoped lint/format completed successfully before code commit. Remote CI is tracked separately on the published documentation HEAD; do not infer remote test counts from local counts.

## Completion backlog after this slice

Synthetic G3/G4/G5 connection/reproduction/explanation evidence is now present. G1 real-data/PIT, G2 economically justified company exposure, real-company G3–G5 acceptance and empirical forecast validity remain open. This example is not a generic real-input loader or saved-input replay service. No extra parser/storage/UI is declared mandatory without a concrete accepted input contract.

SMM remains blocked on operating-income-compatible evidence; the bounded source search is not reopened. BLS capture remains active under its unchanged fixed runtime, and does not create paired forecast history. Next dependency is an eligible real-input bundle or separately scoped design of the own-model/consensus/preregistration experiment; neither may be fabricated from this demo. Whole-product percentage and completion date remain unassessed.
