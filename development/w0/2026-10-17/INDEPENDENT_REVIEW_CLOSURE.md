# W0 independent static review

Reviewed 2026-10-17. Fixed document HEAD: `54b15cbf5ef7f85b0c0d43f2df6b1974bcf1ccbc`; code baseline: `0e915c81fafc26535001680e5fbd0b9c5fc1eb67`. Reviewer did not author W0. Read-only review except this memo. No tests/collection, data API requests, credential reads, research calculations or Git mutations.

## Decision

W0's principal factual distinctions are supported. Full W0 acceptance remains conditional on the freeze-traceability gap below. No code defect is alleged and no retesting is requested.

### Blocking: incomplete historical FROZEN traceability

`development/w0/2026-10-17/BRANCH_AND_FREEZE_MAP.md:17` indexes D0107 onward, while `:23` leaves all earlier declarations unindexed. `W0_RESULT.md:20` correctly says the 288-path check is not all-FROZEN coverage. `Japanese_Equity_Lab/DECISIONS.md:17752,17930,18099` alone show earlier D0104/05/06 declarations. The requested W0 condition requires FROZEN targets to be traceable. Honest UNKNOWN disclosure prevents overclaiming but does not itself complete that inventory.

Minimum closure: enumerate historical declarations with source entry/line, module, declared file/test scope, fixed SHA/manifest where available, and explicit unresolved boundaries. Do not infer all 288 paths are formally frozen or rerun historical writers. If that is deferred, label W0 incomplete on this condition rather than fully accepted.

## Supported checks

- Independently compared every one of 288 inventory baseline/candidate Git blob IDs to actual Git objects: 288 checked, zero mismatches. This confirms only that manifest's protection scope.
- `git diff --stat` baseline to reviewed HEAD: seven new W0 documentation/evidence files only, 2164 additions. Initial status clean.
- Default tree at `4a931eb12b9567a6d78593decc69053ff37d38e0` contains no Lab. Merge object `071cff9c18632461c207a08c20e7c721a983221b` has parents `1688d712095bf90b03e8cc9b38244f856a32aab2` and `794da6b5d1e0b6a748b983736c83191d7a65bd06`, matching PR2 historical merge. Current remote state was not independently refetched; saved JSON is observation evidence, not authoritative live status.
- `lib/backtest/engine.py:502-512,559-580` (under Japanese_Equity_Lab) confirms price-bar-only signal interface; existing fundamentals views do not prove event-signal wiring.
- `lib/research/locked_test.py:63-96` confirms experiment-ID gate and nonempty actor text, not identity authentication or cross-experiment period isolation. Prior-viewed periods cannot become unseen through new IDs.
- `.github/workflows/ci.yml:35-44` confirms three ignored research files plus name filtering. `13_tests/test_research_validation_pipeline.py:238-247,310-321` includes temporary-path registry/gate tests, supporting safe-test over-exclusion as a possibility, not blanket permission to restore all tests. Full import/runtime side-effect classification remains W2 work.
- `DECISIONS.md:13707-13713,13814-13815` supports distinguishing historical Light wording and past Standard-era observations from present subscription rights. UNKNOWN current contract is appropriate without fresh account evidence.

## Nonblocking documentation/evidence limitations

- `CURRENT_STATE_SOT.md:26` and `W0_RESULT.md:3` reference an INDEPENDENT_REVIEW.md not yet present in reviewed commit. Publish this independent conclusion or equivalent before calling the package complete.
- `remote_state.json` has no structured retrieval timestamp/provenance field; document-level date exists. Add observation metadata when preserving existing results; no data refetch needed for this closure.
- Full test side effects, human data-view history, historical raw hash verification, present API entitlement, and product stable-branch selection remain explicitly unconfirmed. W0 must not turn these into verified facts. W1 implementation is not authorized by this review.

## Single closure check (2026-10-17)

Fixed HEAD `31c047d796c8926289ffa51362ca886cb1de8e83`, clean status. Compared against initial reviewed HEAD: only four W0 documentation/evidence files changed; no source, CI, tests, data or registry changes. INDEPENDENT_REVIEW.md now exists. Remote metadata truthfully states date-only observation precision and no independent refetch. New freeze index is explicitly a search-entry list, not a formally accepted freeze inventory. W0_RESULT.md:5 expressly holds full W0 completion and prohibits W1 transition pending the missing historical declaration-to-file/SHA reconciliation. No local home path patterns were found in the W0 package by the scoped text search.

Documentation closure accepted: missing-link/provenance and incomplete-status presentation addressed. Original substantive all-FROZEN traceability blocker remains open and is accurately handed forward. W0 full acceptance remains withheld; no further review iteration requested. No tests or collection executed.
