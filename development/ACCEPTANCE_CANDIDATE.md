# Japanese Equity Lab — acceptance candidate entry point

Updated2026-10-17 Japan. This is the entry point for the current synthetic integration acceptance candidate. It is a new documentation index on the unmerged PR18 branch, not a replacement for frozen specifications or a formal FROZEN/merge acceptance.

## Which version to use

- Candidate including existing evidence:598e8d25010e4ed1b13e4a7be570a62124b840ac; Git tree e77815ba4c399fd7110c6029e5869f2d34e712f2.
- Independently reviewed integration code:9b36bbe765596f67d4ec2a4a68dfef43f03ee852. The candidate adds only DECISIONS/result/evidence documents after that code; no production or test changes.
- Live review: [PR18](https://github.com/shouishirakawa273-lab/shoui-/pull/18), branch codex/integrated-research-portfolio.
- Machine-readable snapshot: [2026-10-17_ACCEPTANCE_CANDIDATE.json](2026-10-17_ACCEPTANCE_CANDIDATE.json). It records the observed PR heads/CI at the date above. Live branches may subsequently move; complete SHAs govern reproducibility.
- The frozen/main development baseline is not this Draft stack. Last recorded accepted predecessor071cff9c18632461c207a08c20e7c721a983221b is an ancestor; its historical acceptance is not newly re-audited here.

These pins intentionally precede this entry-point documentation commit, avoiding a self-referential commit/manifest loop. Later documentation-only commits do not change the pinned calculation candidate.

## What the candidate does

One synthetic company: explicit period macro driver→exposure bridge→baseline/replay fundamentals→valuation→conditional scenario returns→desired portfolio risk→rule-based construction→risk recheck. The actual typed records pass between APIs; the complete artifact preserves their hashes, source refs, assumptions, rejection reasons and unsupported checks.

Expected example:BASE operating income100→120, per-share value75→91; price80/dividend3/entry1/exit2 gives net -5/81→11/81. Desired capital weight0.8/cash0.2 breaches company0.5 and sector0.6 limits. Construction produces weight0.5/cash0.5/releasedcash0.3 and passes only the declared company/sector/cash constraints. A refusal is an expected diagnostic artifact, not a successful real-product result.

## Run and inspect

Use an isolated clean checkout at the complete candidate SHA, or the existing current checkout only after confirming its code matches. Preserve other working changes. CI uses Python3.11; local tests use the project's existing virtual environment. Requirements files use lower bounds and are not an exact dependency/environment lock; byte-identical environment reconstruction across future package releases is not certified.

From repository root with the existing project interpreter on Windows:

```text
.venv/Scripts/python.exe -B Japanese_Equity_Lab/scripts/integrated_research_portfolio_demo.py
.venv/Scripts/python.exe -B Japanese_Equity_Lab/scripts/integrated_research_portfolio_demo.py --future-driver
.venv/Scripts/python.exe -B Japanese_Equity_Lab/scripts/integrated_research_portfolio_demo.py --bad-joint-binding
```

No external access/file writes. Success and refusals emit JSON, with synthetic=true, empirical_validation=false, product_acceptance=false. Inspect rejection and stage output, not exit0 alone. Expected canonical success artifact_hash:2d908e887ef4ed3a95529a59bb077f18bf4bd94266a9fbdd74249defe84e4f91. Preexisting independent executions established separate-process/different-cwd identity; this documentation consolidation did not rerun them or a full code review.

## Evidence and contracts

| Slice | Contract/result | Evidence |
|---|---|---|
| D0110.1–.4 synthetic foundation | [D0110 acceptance](2026-10-16_D0110_TECHNICAL_ACCEPTANCE.md) | evidence/d0110/; original306/47 runs have documented command/probe-history limits |
| Company→valuation connection | [Integration result](2026-10-15_EXPOSURE_VALUATION_INTEGRATION_RESULT.md) | Existing result describes scope; real-company metric compatibility remains open |
| D0111 return calculation | [D0111 result](2026-10-16_D0111_RESULT.md) | evidence/d0111/ and closure/;100pass/1excluded, initial CI type errors corrected |
| D0112 conditional risk | [D0112 result](2026-10-17_D0112_RESULT.md) | evidence/d0112/;134pass/1excluded |
| D0113 rule construction | [D0113 result](2026-10-17_D0113_RESULT.md) | evidence/d0113/;156pass/1excluded |
| Full selected vertical path | [Integrated result](2026-10-17_INTEGRATED_PATH_RESULT.md) and [spec](2026-10-17_INTEGRATED_PATH_SPEC.md) | evidence/integrated-path/;171pass/1excluded,197-source mypy, independent object-identity/Fraction/hash/rejection probes |
| Existing BLS capture operation | [Capture result](2026-10-16_BLS_CAPTURE_RESULT.md) | evidence/bls-capture/; fixed operational code is separate from this candidate |

Local counts belong to separate runs with different scopes and MUST NOT be summed as unique tests. Independent design-audit conclusions are recorded in results; full independent transcripts are not separate persisted review artifacts. Candidate check-runs117317395586 and117317431684 are both success as directly observed via GitHub API. Remote success does not certify local counts, source truth or empirical performance. No H0001/Locked Test was run.

## PR ancestry and exclusions

Directly observed through GitHub API: required ancestor chain [3](https://github.com/shouishirakawa273-lab/shoui-/pull/3)→[7](https://github.com/shouishirakawa273-lab/shoui-/pull/7)→[8](https://github.com/shouishirakawa273-lab/shoui-/pull/8)→[9](https://github.com/shouishirakawa273-lab/shoui-/pull/9)→[10](https://github.com/shouishirakawa273-lab/shoui-/pull/10)→[11](https://github.com/shouishirakawa273-lab/shoui-/pull/11)→[12](https://github.com/shouishirakawa273-lab/shoui-/pull/12)→[13](https://github.com/shouishirakawa273-lab/shoui-/pull/13)→[14](https://github.com/shouishirakawa273-lab/shoui-/pull/14)→[15](https://github.com/shouishirakawa273-lab/shoui-/pull/15)→[16](https://github.com/shouishirakawa273-lab/shoui-/pull/16)→[17](https://github.com/shouishirakawa273-lab/shoui-/pull/17)→[18](https://github.com/shouishirakawa273-lab/shoui-/pull/18). All13 were open, Draft and unmerged at observation. Local ancestry confirmed each listed preceding branch is included in the pinned candidate. This is dependency evidence, not authorization or a merge instruction.

Sibling PR4→5→6 (pretax impact/preflight/SMM source archive) are also Draft/open/unmerged, but NOT ancestors of this candidate. Their production capabilities are not delivered by this checkout; no accidental merge into the operating-income route. The separate codex/development-governance branch is likewise not an ancestor. Its old product/organization documents are historical reference, not files available in this candidate; this index points to the contracts actually present. No need to integrate sibling code merely to make PR numbers contiguous.

## Acceptance gates still open

| Gate | Current evidence | Unmet release condition |
|---|---|---|
| Synthetic selected vertical route | Independently verified, candidate CI success | Formal integration into accepted branch remains unperformed; all Drafts retained |
| Real company/PIT | Current SMM input readiness is blocked | Eligible operating-income-compatible evidence, genuine raw/time provenance, price/dividend/share basis and common period/cutoff bundle |
| Macro/forecast effectiveness | BLS capture-only operates separately | Own model/version, authorized consensus source, preregistration before predictions, qualified paired releases and enough prospective history |
| Portfolio scenario/policy validity | Explicit caller-attested synthetic joint scenarios/limits | Evidence supporting joint assumptions and policy suitability; unsupported theme/event/liquidity/correlation/VaR/stress checks cannot be called passed |
| Real operating deployment | BLS collector alone was deployed | General analysis/input ingestion, persistence/recovery, user-facing operation and reproducible environment are not accepted as a production system |

SMM same-issue repeated search remains stopped; do not substitute company names onto synthetic inputs. See [SMM readiness](2026-10-16_D0111_SMM_INPUT_READINESS.md) and [bounded supplementary check](2026-10-17_D0111_SUPPLEMENTARY_EVIDENCE.md). D0110.1/.2 event measurement and.4 comparison are separate from this vertical route; not empirically certified by the integration. Do not invent an automatic event→driver causal connection.

The expanded portfolio roadmap exceeds the earlier single-company five-gate scope. Whole-product percentage and remaining completion time remain unassessed; no module counts/old weights converted into a percentage. No new D-number or optional feature is required by this consolidation.

## Operational separation and next boundary

BLS Windows task JapaneseEquityLab-BlsCpiCapture uses fixed snapshot codef075802dcafd35451b84f301ec00907c74536738 at ops/bls-runtime-f075802 and stores ops/bls-data-v2 outside the Git checkout. This runtime was not changed or re-audited today. Last separate observation in the supplementary record was October17 00:20 Japan success, later than planned00:15; no fresh execution or uptime claim is made here. Data capture is not paired own-forecast history. The development heartbeat is PAUSED; data collection does not imply background code development.

No merge/FROZEN, source/frozen/runtime/scheduler modifications or new tests in this documentation step. Next mandatory work requires a qualified real input/experiment contract or separately authorized branch acceptance action, not another synthetic feature to inflate apparent completeness. Routine merge/FROZEN prohibition remains in force.
