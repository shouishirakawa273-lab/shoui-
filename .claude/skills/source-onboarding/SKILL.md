---
name: source-onboarding
description: >-
  Pre-connection research checklist for a new external Data Source in
  Japanese Equity Lab (TDnet, EDINET, Macro stats, News, etc). Use before
  implementing any new Data Source Adapter, in Phase4B and later.
  Produces a Source Onboarding Report of confirmed facts, marking
  anything unconfirmed as UNKNOWN rather than guessing.
paths: Japanese_Equity_Lab/**
---

# Source Onboarding

Before any new Data Source is connected (Phase4B: TDnet/EDINET/Company IR
onward), research and record the following. **Do not guess.** Any item you
cannot confirm from an official/primary source is `UNKNOWN` — that is a
valid, expected answer, not a failure to complete this checklist.

Prefer official/primary documentation (the provider's own API docs,
official spec pages, regulator publications) over secondary sources. Blogs,
GitHub repos, and social media are acceptable only as supplementary
context when no official source exists for a specific item, and must be
labeled as such (this mirrors `SourceAuthorityClass` in
`lib/sources/catalog.py` — do not treat a blog post as equivalent evidence
to an official spec).

**`SourceAuthorityClass` is a category, not a trust score.** Don't rank
sources by a numeric confidence; classify them (`PRIMARY_OFFICIAL` /
`COMPANY_PRIMARY` / `VERIFIED_SECONDARY` / `SECONDARY` / `SOCIAL` /
`USER_SUPPLIED`) and keep that separate from whether a specific claim
turns out to be correct.

**Separate Originating Source from Delivery Provider from the start.**
If this data reaches the Lab through an intermediary (e.g. EDINET data
delivered via a J-Quants-style aggregator), record both
`originating_source` and `delivery_provider` — see D0042/D0043 in
`DECISIONS.md` for why this Lab keeps them distinct.

## Checklist

**Identity & access**
- Source identity (official name, not a colloquial one)
- Originating Source vs. Delivery Provider (may be the same)
- Official documentation URL(s)
- API version
- Authentication method
- Plan / contract requirement (free tier vs. paid, what each unlocks)
- Cost
- License / redistribution restrictions (can retrieved data be stored,
  and for how long — relevant to `RawSnapshotStore`)

**Coverage & availability**
- Historical coverage (how far back)
- Current availability (is it actively updated)
- Update timing (when new data appears relative to the event it describes)
- Rate limit (plan-wide)
- Endpoint-specific rate limit, if different from the plan-wide limit
- Pagination mechanism
- Bulk/file download availability (vs. per-record API calls only)

**Revision & correction semantics**
- Correction semantics (can a past record be corrected, and how is that
  signaled)
- Deletion semantics (can a record be removed, and how is that signaled)
- Revision semantics (how a later value relates to an earlier one — is
  there a confirmable parent/child relationship, or must revisions be kept
  as independent time series like this Lab does for `/v2/fins/summary`)

**PIT timestamp semantics** (see `EVIDENCE_MODEL.md` for the Lab's model)
- Public timestamp (when the market/public could see it)
- Provider availability timestamp (when *this* pipeline could have
  fetched it — do not assume this equals the public timestamp without a
  confirmed reason, per D0043)
- Retrieved timestamp semantics (does the provider expose one, or is it
  purely this Lab's own fetch time)

**Identity mapping**
- Entity identifiers the source uses (ticker, code, corporate number, etc.)
- Code mapping approach into this Lab's Canonical Entity Registory
  (`lib/sources/entity_registry.py`) — never join raw provider codes
  directly across sources

**Schema**
- Null / blank semantics (what does an empty/missing field mean — and can
  that be confirmed, or is it `UNKNOWN` per-field like this Lab's
  `ValueAvailability`)
- Declared schema (what the docs say the fields are)
- Observed wire schema (what a real response actually contains — these can
  differ, per D0043's `/v2/fins/summary` findings; keep both recorded
  separately, never silently coerce one to match the other)
- Schema evolution history/policy (does the provider version its schema,
  add fields without notice, etc.)

**Storage**
- Raw storage policy implications (any restriction on retaining raw
  payloads long-term)
- File/PDF/XBRL availability (if the source is document-based, not just
  JSON/CSV)
- Checksum/hash availability (can integrity of a downloaded artifact be
  verified independently of this Lab's own `RawSnapshotStore` hash)

**Known limitations**
- Anything above that resolved to `UNKNOWN`, listed explicitly, not
  buried in prose

## Output format

Produce a **Source Onboarding Report**: one line per checklist item, each
either a confirmed fact with its source citation, or `UNKNOWN`. Do not
implement a connector, an adapter, or any fetch logic — this skill produces
research only. Do not retrieve, request, or handle an API key.
