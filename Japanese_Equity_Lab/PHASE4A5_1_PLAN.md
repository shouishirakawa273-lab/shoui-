# Phase4A.5.1 — Research Engineering Hardening: Implementation Plan(設計固定、未実装)

**このDocumentはDesign/Scope/Implementation Orderの確定のみを行う。コード実装は
次Round以降。** `.claude/skills/`・`.claude/agents/`・`lib/`・`13_tests/`・
`.claude/settings.json`はこのRoundで一切変更していない。変更したのはこのFile
(新規)と`DECISIONS.md`(D0051要約エントリ)のみ。

このPlanは、実Repositoryの現状確認(`lib/`・`13_tests/`・`.claude/skills/`・
`.claude/agents/`・`.claude/settings.json`・`DECISIONS.md`・既存Architecture
Doc群を実際に読んだ結果)に基づく。存在しないComponentを存在すると仮定した
箇所は無い。確認方法(Read/Grep)を全項目に付記する。

---

## A. Repository Reality Check

凡例: `EXISTS`(実装済み、追加不要)/`PARTIAL`(一部実装、拡張余地あり)/
`MISSING`(未実装)/`NOT_NEEDED`(この規模の個人研究基盤には過剰)。

| # | Component | Status | Evidence(実際に読んだFile) |
|---|---|---|---|
| 1 | PIT/Look-ahead監査Skill+Subagent(`pit-audit`/`pit-auditor`) | `EXISTS` | `.claude/skills/pit-audit/SKILL.md`, `.claude/agents/pit-auditor.md` |
| 2 | Adversarial Review Skill+Subagent(`adversarial-review`/`skeptic-reviewer`) | `EXISTS` | `.claude/skills/adversarial-review/SKILL.md`, `.claude/agents/skeptic-reviewer.md` |
| 3 | Source Onboarding Skill+Subagent(`source-onboarding`/`data-source-researcher`) | `EXISTS` | `.claude/skills/source-onboarding/SKILL.md`, `.claude/agents/data-source-researcher.md` |
| 4 | Phase Close Skill(`phase-close`、`disable-model-invocation: true`) | `EXISTS` | `.claude/skills/phase-close/SKILL.md` |
| 5 | Local Validation Skill(`local-validation`) | `EXISTS` | `.claude/skills/local-validation/SKILL.md` |
| 6 | Reviewer Agentの構造的Read-only化(`tools: Read, Grep, Glob`のみ) | `EXISTS` | 3 Subagent frontmatterを直接確認(`Write`/`Edit`/`Bash`不在) |
| 7 | Author/Reviewer分離のWorkflow文書化 | `EXISTS` | `CLAUDE_CODE_RESEARCH_WORKFLOW.md` |
| 8 | Deterministic Hook: PostToolUse品質ゲート(ruff/mypy/pytest) | `EXISTS` | `.claude/settings.json`, `.claude/hooks/post_edit_quality_gate.sh` |
| 9 | Hook候補(Secret Guard/Protected Path Warning/Phase Validation) | `PARTIAL`(提案のみ、未導入) | `HOOKS_PROPOSAL.md` |
| 10 | Raw Snapshot Immutability(Append-only、Tamper検出) | `EXISTS` | `lib/snapshot.py`(`AppendOnlyViolationError`/`SnapshotTamperedError`実装済み) |
| 11 | Secret Leakage Guard(Snapshot保存時) | `EXISTS`(Snapshot保存経路のみ) | `lib/snapshot.py::_assert_no_secret_like_keys` |
| 12 | Secret Guard(git commit時、`HOOKS_PROPOSAL.md`案A相当) | `MISSING` | 上記は「保存するJSONの中身」のGuardであり、「Bashコマンド自体」を見るPreToolUse Hookは無い |
| 13 | Construction-time Ordering Invariant(available_at >= published_at) | `PARTIAL` | `lib/point_in_time.py::PointInTimeRecord.__post_init__`は`available_at < published_at`をraise。**しかし**`lib/sources/catalog.py::SourceMetadata`・`lib/evidence/model.py::SourceVersion`・`lib/disclosures/model.py::DisclosureDocument`の`__post_init__`はtz-aware確認のみで、この順序は一切検査していない(3ファイルとも実際に読んで確認)。**D0049/D0050のBugが2箇所で独立に発生し得た構造的根本原因はここ** |
| 14 | PIT Compliance Test(Principle-derived、Cross-cutting) | `PARTIAL` | `13_tests/test_point_in_time.py`・`test_available_at_vs_retrieved_at.py`・`test_pit_as_of_adjustment.py`・`test_fundamentals_pit_real_dates.py`・`test_fundamentals_evidence_pit.py`・`test_disclosures_evidence_pit.py`はいずれも個別Module実装に付随したTestであり、Module横断でPrinciple単体から導出された単一Suiteは無い |
| 15 | UNKNOWN Basis既定除外(`RevisionHistory.as_of`) | `EXISTS` | `lib/evidence/model.py::RevisionHistory.as_of`(`include_unknown_availability=False`既定) |
| 16 | Entity Registry as-of解決(Current-State Leakage対策) | `EXISTS` | `lib/sources/entity_registry.py::EntityRegistry.resolve(as_of=...)`、`13_tests/test_entity_registry.py`で回帰確認済み |
| 17 | Artifact Difference Workflow(Raw vs Canonical Hash) | `EXISTS`(EDINET限定) | `lib/disclosures/providers/edinet_zip.py::compute_canonical_zip_content_hash`、D0046追記2、`13_tests/test_edinet_zip_canonicalize.py`(18件) |
| 18 | Forward Snapshot観測の反復実施Procedure | `MISSING`(材料はEXISTS) | D0046追記2は1回限りの手動観測。`RawSnapshotStore`自体は反復保存を構造的にサポートするが、反復観測のProcedureとしては未文書化 |
| 19 | Lightweight System Health(Lab向け) | `MISSING` | `scripts/`配下(Lab)にHealth相当のScriptは無い。`scripts/schema_health_check.py`はRoot直下でありScreening Tool(`core/`)専用、Protected範囲、流用不可 |
| 20 | Context Architecture(Always/On-demand分離) | `PARTIAL`(暗黙に実践済み、未分類・未文書化) | `CLAUDE.md`は意図的に短く(常時Ruleのみ)、詳細は`.claude/skills/`・`CLAUDE_CODE_RESEARCH_WORKFLOW.md`へ分離済み(既にLayer0/Layer1相当の分離が存在する)。`DECISIONS.md`(268KB)は常に全文読まずGrep/Offset読みで運用されている(本Session含め実践済み)が、これを`ALWAYS`/`ON_DEMAND`/`TASK_ONLY`/`EVIDENCE_ONLY`として明示分類したDocumentは無い |
| 21 | Rule ID体系(`PIT-001`等) | `MISSING` | Repository全体をGrepし0件 |
| 22 | Golden Prompt Parity Audit(旧Prompt→Skill Rule対応表) | `MISSING` | D0044はSkill実装内容の要約のみで、要件単位の対応表(旧Prompt Requirement → Skill Rule / Source-specific Rule / Intentionally Removed)は存在しない |
| 23 | Agent Governance機械的Enforcement | `PARTIAL` | Tool Allowlist・`disable-model-invocation`は実装済み(D0044実装時に手動で1回確認)。**しかしこれを継続的に守るRegression Testは無い**(Frontmatterが将来誤って書き換えられても検知するTestが無い) |
| 24 | Main Claude Single Writer原則の機械的強制 | `MISSING`(現状はProse/Convention) | `CLAUDE.md`の文章のみで、Hook/Permission Configによる強制は無い |
| 25 | 大量並列Agent運用の抑制方針 | `EXISTS`(方針としては既に一貫) | このSession含め全Phaseの実績が「少数の明確なRole」であり、大量並列Research Agentの実績は無い(Repository運用実態から確認) |

**総括**: このLabはPhase4A.5(D0044)で「Documentation上のGuardrail」を、
D0049/D0050で「実際にBugを発見・修正・記録するProcess」を、それぞれ実証済み
である。Phase4A.5.1の実質的な価値は、**新しい概念を追加すること自体ではなく、
D0049/D0050で実際に露呈した1個の構造的Gap(#13)と、それを繰り返さないための
Regression化(#14, #21, #23)** に集約される。

---

## B. Final Phase4A.5.1 Scope(概要、詳細はO)

MUSTは4件、SHOULDは4件のみに絞る(詳細分類はセクションO)。過剰な新規
Architecture(Event Extractor/Indexer/Replay基盤/大規模Observability)は
このPhaseの対象外(ユーザー指示§11通り)。

---

## C. Implementation Order(依存関係込み)

ユーザー提示のCandidate Order(§14)を実Repository確認結果に基づき一部
入れ替えた。理由は各Stepに付記する。

```
4A.5.1-1  PIT Compliance Test Suite(新規 13_tests/test_pit_principles.py)
4A.5.1-2  Agent Governance Structural Tests(新規 13_tests/test_agent_governance.py)
4A.5.1-3  Deterministic Hook: Protected Path Warning のみ実装
4A.5.1-4  Context Architecture 分類表(CLAUDE_CODE_RESEARCH_WORKFLOW.mdへ追記)
4A.5.1-5  Artifact Difference Workflow 一般化Doc(DISCLOSURE_ARCHITECTURE.mdへ追記)
4A.5.1-6  Lightweight System Health 読み取り専用Script(scripts/lab_source_health.py)
4A.5.1-7  Golden Prompt Parity Audit(既存5 Skillの要件対応表)
4A.5.1-8  Source Integration Skill v1(4A.5.1-7の結果を使って構築)
4A.5.1-9  Forward Snapshot PoC Procedure Doc(EDINET、実行はUser側で後日)
```

**ユーザーCandidate Orderからの変更点と理由**:

- **Agent Governance(元#5)を#2へ前倒し**: 他の項目に一切依存せず、既存
  Frontmatter(#6/#23、EXISTS/PARTIAL)を検査するだけの独立Testであり、
  後回しにする理由が無い。かつD0044の手動確認(一度きり)をRegression化
  する緊急性はPIT Testに次いで高い(Reviewer Agentが将来誤ってWrite権限を
  持つことを検知できないままにしておく期間を最小化したい)。
- **Deterministic Hooks(元#6)を#3へ前倒し、範囲をProtected Path Warningのみに縮小**:
  Secret Guard(commit時)は既存の`_assert_no_secret_like_keys`(#11、
  EXISTS)で主要な実害経路は塞がれているため緊急性が低い(`SHOULD`止まり)。
  Optional Phase Validationは既存PostToolUse Hook(#8)と機能重複が大きく
  `NOT_NOW`。Protected Path Warningのみ、他Stepに依存せず低Cost・高Valueと
  判断し前倒し。
- **Source Integration Skill v1(元#3)とGolden Prompt Parity Audit(元#4)を
  #7-8へ後ろ倒し**: Context Architecture分類(#4)を先に済ませておかないと、
  Skill化の際に「何をSkillへ・何をALWAYS Ruleへ・何をTASK_ONLYへ残すか」の
  判断基準が無いまま作業することになり、Skill自体を作り直すリスクがある。
  依存関係上、後ろに置くのが安全。
- **Forward Snapshot PoC(元#7)を最後へ**: コード的な依存は無いが、実際の
  観測(複数日にわたるRetrieval)はUser側のローカル実行が必要で、このLabの
  制御下にない時間がかかる。Main Claudeが進められる他のStepを先に終わらせて
  おく方が合理的。
- **Artifact Difference Workflow一般化(元#8)を#5へ前倒し**: 新規コードが
  ゼロ(既存`edinet_zip.py`の境界を文書化するのみ)で、他Stepとの依存も無い。
  実際に確認した結果(下記K参照)、TDnetは現状Document本文(PDF/ZIP)を
  一切Fetchしていない(`docs_raw`はOpaque Raw値として保持するのみ、
  `lib/disclosures/providers/tdnet_normalize.py`で確認)ため、一般化の
  対象コードが今は存在しない。したがってこのStepは実質「境界を正確に
  文書化するだけ」の軽量作業であり、早期に片付けられる。

各Stepは独立してCommit可能な単位を意図している(1 Stepの完了 = 1回の
`pit-auditor`/regression/commit、必要ならSkeptic Reviewも)。

---

## D. PIT Compliance Test Design(コードはまだ書かない、設計のみ)

新規ファイル`13_tests/test_pit_principles.py`を想定。既存Module別Testの
重複ではなく、**Principle単体から導出され、特定のFunction実装に依存しない**
Testのみをここへ集める(既に十分なCoverageがある項目はここへ複製しない)。

| # | Name | Principle | Priority |
|---|---|---|---|
| T1 | `test_visibility_separation_market_vs_provider_across_modules` | Setup: `market_public_at=15:00`, `provider_available_at=15:05`(basis=EXACT), `retrieved_at=15:06`, `decision_at=15:03`。Attack: A系統(`disclosures_as_of(..., MARKET_PUBLIC_AT)`)とB系統(`EvidenceRecord.is_usable_at`)を同一Fixtureへ両方適用。Expected: A系統は`published_at=15:00<=15:03`で可視、B系統は`available_at=15:05>15:03`で不可視、という**分岐そのもの**を確認(現状`test_tdnet_integration.py`はTDnet固有Fixtureで類似確認済みだが、Provider横断の汎用形としては無い)。Bug prevented: A/B系統混同(D0042の核心)。Existing dependency: `lib/disclosures/view.py`, `lib/evidence/model.py`。 | MUST |
| T2 | `test_unknown_availability_boundary_15_03_vs_15_06_parametrized_across_fundamentals_and_disclosures` | D0049/D0050で実際に使った15:00/15:03/15:06のシナリオを、`disclosure_metric_to_evidence`と`disclosure_document_to_evidence`の**両方に対して同一Parametrizeで**適用し、2 Moduleが将来分岐しないことを保証する(2つの独立したBugが同型だったという実績を踏まえ、次に3つ目のModuleが増えても同じ保証が要求されるようにする)。Bug prevented: D0049型Bugの再発・第三Module目での再発。Existing dependency: `lib/fundamentals/evidence.py`, `lib/disclosures/evidence.py`。 | MUST |
| T3 | `test_construction_time_ordering_gap_is_a_known_documented_gap` | **現状のGapをそのまま記録するTripwire**(修正ではない)。`SourceMetadata`/`SourceVersion`/`DisclosureDocument`を`published_at=15:00, available_at=14:00`(意味的に疑わしい順序)で構築し、**現状は例外を出さず構築が成功すること**を明示的にAssertする(`pytest.raises`ではなく、逆に「まだ раises しない」ことを記録)。このTestがある日突然Failし始めたら「誰かがConstructor Validationを追加した」ことを意味し、その変更がDECISIONS.mdへ記録されているかを確認するきっかけになる。Bug prevented: 無言のArchitecture Driftの検知漏れ。**ユーザーの4-1-C「Source semanticsによって成立し得る場合は勝手にinvalidと決めない」との整合上、これは今回Constructorレベルの拒否を追加する提案ではない**(セクションNのOpen Questionへ)。Existing dependency: `lib/sources/catalog.py`, `lib/evidence/model.py`, `lib/disclosures/model.py`。 | SHOULD |
| T4 | `test_future_injection_rejected_via_filter_usable_at` | `lib.point_in_time`層(古いPrice PIT)では`test_future_available_at_is_rejected_even_if_retrieved_long_ago`が既にあるが、新しいEvidence層(`EvidenceRecord.is_usable_at`/`filter_usable_at`)に対する同種の直接Testが無い。未来`available_at`のEvidenceを`filter_usable_at`へ渡して除外されることを確認。Bug prevented: Evidence層でのFuture Injection。Existing dependency: `lib/evidence/model.py::filter_usable_at`。 | MUST |
| T5 | (提案しない — 既存で十分) | Current-State Leakage(Entity Mapping)は`13_tests/test_entity_registry.py`(`test_resolve_returns_mapping_valid_at_as_of`等)で既に確認済み。重複を避けるため新規追加しない。 | N/A(既存確認のみ) |
| T6 | (提案しない — 既存で十分) | Snapshot Overwrite保護は`AppendOnlyViolationError`のTest(`test_snapshot.py`、`test_raw_snapshot_append_only_rejects_overwrite`)で既に確認済み。 | N/A(既存確認のみ) |
| T7 | `test_unknown_basis_never_treated_as_falsy_or_substitutable` | `AvailabilityBasis.UNKNOWN`をPythonの`if not basis`や`basis or AvailabilityBasis.EXACT`のような暗黙変換パターンでコードが扱っていないことを、`RevisionHistory.as_of`の`include_unknown_availability`既定Falseの直接確認(既存Test Jに近いが、D0049固有ではなくPrinciple単体として独立させる)＋ `ValueAvailability.UNKNOWN`が`0`や`False`と等価に扱われる箇所が無いことをGrepベースで構造確認する形にする。Bug prevented: `UNKNOWN → False`/`UNKNOWN → 0`(ユーザーが繰り返しChecklistに挙げている典型Failure Mode)。Existing dependency: `lib/evidence/model.py`, `adversarial-review` Skillの既存Checklist項目と重複しない範囲でCode-levelに絞る。 | MUST |
| T8 | `test_no_test_file_asserts_the_pre_fix_available_at_equals_market_public_at_pattern` | **メタTest**。`13_tests/`配下の全Test SourceをGrepし、`available_at == .*market_public_at`(またはFundamentals側`available_at == .*envelope\.market_public_at`)という、D0049/D0050の**Bugそのものの形**をAssertしているTestが無いことを構造確認する。D0050はこのPatternが`test_tdnet_integration.py`に実在したことで発覚した実績があるため、再発を機械的に検知できるようにする。Bug prevented: 「Tests are not Truth」の再発(このRoundの最大の教訓そのもの)。Existing dependency: なし(純粋にGrepベース)。 | MUST(最優先) |
| T9 | `test_raw_hash_mismatch_never_treated_as_revision_generalized` | `edinet_zip.py`固有の`test_edinet_zip_module_never_constructs_document_relationship`をLab全体(Common Core含む)へ一般化し、「Raw Hash不一致だけでは`is_correction`/`DocumentRelationship`/`DuplicateRelationKind`を構築しない」という原則をSource非依存でGrep確認する。Bug prevented: 将来のSourceでD0046追記2と同型の誤判定が起きること。Existing dependency: `lib/disclosures/model.py`(`DuplicateRelationKind`)。 | SHOULD |
| T10 | `test_availability_basis_fields_default_to_unknown_not_exact` | `dataclasses.fields()`でSchema内の`*_basis: AvailabilityBasis`型Fieldを列挙し、既定値が全て`AvailabilityBasis.UNKNOWN`であって`EXACT`ではないことを構造確認する(将来Fieldが追加された際、既定を安全側以外に設定してしまう回帰を防ぐ)。Bug prevented: 新規Schema Field追加時の既定値ミス。Existing dependency: `lib/evidence/model.py`, `lib/disclosures/model.py`。 | SHOULD |
| T11 | `test_invalid_ordering_when_source_semantics_confirmed_valid_is_not_falsely_rejected` | T3の裏側。将来「available_atがpublished_atより早いことが構造的に正当なSource」(例: 埋め込み配信等、現状this Labには存在しない仮想例)が出てきた場合に備え、**このRoundではConstructor Levelでの拒否を実装しない**という決定自体をTestではなくOpen Questionとして残す(セクションN)。 | N/A(Test化せず、Open Questionへ) |

**合計 実質新規Test数: 8件(T1, T2, T3, T4, T7, T8, T9, T10)** — ユーザー要求
「最低10件程度」に対し、T5/T6/T11で「既存で十分/Test化しない」という判断も
明示した上で8件を新規提案する。8件は「10件程度」よりやや少ないが、**水増しで
無意味な重複Testを追加しない**という設計判断であり、この判断自体をこの
セクションに明記する(T5/T6の「既存で十分」の判断根拠を隠さない)。

---

## E. Context Architecture Plan

### 現状の暗黙の階層(既に実践されている)

- **Layer 0 相当**: `Japanese_Equity_Lab/CLAUDE.md`(98 words、常時Rule)。
- **Layer 1 相当**: `.claude/skills/*/SKILL.md`(Task種別ごとにOn-demand
  Preload)。
- **Layer 2 相当**: `DECISIONS.md`(268KB)・`*_ARCHITECTURE.md`・
  `*_SOURCE_ONBOARDING.md`。本Session含め、これらは全文Readされず、
  `grep -n "^## D00"` → 該当行のみ`offset`/`limit`指定Readという運用が
  実際に行われている(このPlan作成でも同じ手法を使った)。
- **Layer 3 相当**: 各Round冒頭のUser Task Prompt(Goal/Scope/禁止事項)。
- **Layer 4 相当**: `01_data/raw/`配下のRaw Snapshot、`13_tests/fixtures/`。

### 提案(Documentationのみ、新規Tooling不要)

`CLAUDE_CODE_RESEARCH_WORKFLOW.md`へ、既存Doc群を`ALWAYS`/`ON_DEMAND`/
`TASK_ONLY`/`EVIDENCE_ONLY`へ明示分類した表を追記する(実装Order #4)。
例(確定ではなく提案。実施時に細部を精査):

| Doc | 分類 | 理由 |
|---|---|---|
| `CLAUDE.md`(root/Lab両方) | `ALWAYS` | 既に短い。変更しない。 |
| `.claude/skills/*/SKILL.md` | `ON_DEMAND` | 既にTask種別でPreloadされる設計。 |
| `DECISIONS.md` | `ON_DEMAND`(Grep経由のみ) | 全文Readしない運用を明文化するだけ。既存の268KBを分割・要約しない(要約によるRule消失を防ぐ、ユーザー§5-2)。 |
| `RESEARCH_RULES.md`/`*_ARCHITECTURE.md` | `ON_DEMAND` | 関連Task時のみ。 |
| 各Round冒頭のTask Prompt | `TASK_ONLY` | Roundごとに破棄。 |
| Raw Snapshot/Fixture | `EVIDENCE_ONLY` | 必要な範囲のみ、全件Readしない。 |

**重要な禁止事項の明記**: この分類作業自体が「`DECISIONS.md`を要約して
短くする」プロジェクトに変質しないよう、**分類表の追加以外の既存Doc編集は
このStepに含めない**ことを明記する(ユーザー§5-2「Semantic Compressionに
よる重要Rule消失を防ぐ」を、実装時にも徹底する)。

---

## F. Source Integration Skill v1 Plan

### Rule ID 案(確定ではなく提案、実装時に精査)

`PIT-*`:
- `PIT-001` UNKNOWNはFalseでも0でもない(既存`adversarial-review`
  Checklistの`unknown → zero`/`unknown → false`と対応)。
- `PIT-002` `market_public_at` != `provider_available_at` != `retrieved_at`。
- `PIT-003` `available_at`を`market_public_at`へFallbackしない
  (D0049/D0050で確定した最重要規約)。
- `PIT-004` `available_at`は`retrieved_at`より前にできない(未確認の場合は
  `retrieved_at`を下限として使う)。

`RAW-*`:
- `RAW-001` Raw Artifactはimmutable(Append-only、`RawSnapshotStore`)。
- `RAW-002` Raw Hash不一致 != Revision(D0046追記2)。
- `RAW-003` Raw Artifact Identity != Document Content Identity
  (Container形式のSourceのみ、Canonical Hashが別途必要)。

`EVIDENCE-*`:
- `EVIDENCE-001` Document(開示という事実) != Event(本文の意味内容)。
- `EVIDENCE-002` Evidence Relation(SUPPORTS/CONTRADICTS等)はHypothesis
  依存(Evidence自体は保持しない)。

`SOURCE-*`:
- `SOURCE-001` Source固有Field意味論を推測しない(公式仕様未確認は
  UNKNOWN)。
- `SOURCE-002` Ephemeral URL(署名付きURL等)は永続識別子として扱わない。
- `SOURCE-003` Originating Source != Delivery Provider(D0042)。

### Common Core Rule と Source-specific Rule の境界

- Common Core Rule(`PIT-*`/`RAW-001,002`/`EVIDENCE-*`/`SOURCE-003`):
  `lib/disclosures/evidence.py`・`lib/fundamentals/evidence.py`・
  `lib/evidence/model.py`のような、Source非依存Moduleに適用。
- Source-specific Rule: 各Providerの`*_normalize.py`固有の制約
  (例: EDINETの`market_public_at`は常に`None`/`UNKNOWN`、TDnetは
  `DiscDate`+`DiscTime`から構築するが`AvailabilityBasis.EXACT`は
  使わない、等)。これらはSkill本体ではなく、既存の各`*_SOURCE_
  ONBOARDING.md`/`*_ARCHITECTURE.md`から個別参照する形を維持し、
  Skillへ丸ごとCopyしない(重複による将来の食い違いリスクを避ける)。

**実装しない**: このRoundではRule IDをコードやSKILL.mdへ実際に書き込まない。
次Round(#7→#8)で、Golden Prompt Parity Auditの結果を踏まえてから実施。

---

## G. Golden Prompt Parity Plan

### 監査対象

D0044で実装済みの5 Skill(`pit-audit`/`adversarial-review`/`phase-close`/
`source-onboarding`/`local-validation`)は、いずれも当時のUser Long Prompt
から作られたが、**要件単位の対応表は記録されていない**(D0044自体は
実装内容の要約のみ)。

### 実施方法(次Round)

1. D0044を開始したUser Prompt(このSession履歴に残っている実際の指示文)
   を要件ごとに箇条書きへ分解する。
2. 各要件について、現在のSKILL.md/AGENT.mdの該当箇所を`Grep`で特定する。
3. 各要件を `SKILL_RULE` / `SOURCE_SPECIFIC_RULE` / `INTENTIONALLY_
   REMOVED`(理由必須)のいずれかへ分類する。
4. 対応表を`CLAUDE_CODE_RESEARCH_WORKFLOW.md`または新規
   `GOLDEN_PROMPT_PARITY.md`へ記録する。
5. 可能であれば`skeptic-reviewer`(Read-onlyでSKILL.md/元Prompt双方を
   比較検証できる)にParity Auditを依頼する(ユーザー§5-2/§19)。

**このRoundでは実施しない**(実施には元Prompt全文の再構成が必要で、
このPlan Round自体のScope(設計固定)を超える作業量になるため、次Round
の最初のStepとして計画するに留める)。

---

## H. Agent Governance Plan

| 何を | 手段 | 現状 |
|---|---|---|
| Reviewer Agentは書き込み不可 | Tool Allowlist(`tools:`frontmatter) | `EXISTS`(machine enforcement) |
| `phase-close`は自動起動しない | `disable-model-invocation: true` | `EXISTS`(machine enforcement) |
| 上記2つが将来壊れていないこと | **新規** Structural Test | `MISSING` → 4A.5.1-2で追加 |
| Main Claude Single Writer | `CLAUDE.md`の文章 | Documentation-onlyのまま維持(Hookでの強制は§4-3ユーザー指示通り見送り、"全変更をHuman PR approval必須にもしない"との整合) |
| Phase遷移の明示性(自己判断で次Phaseへ進まない) | `phase-close`Skillの`disable-model-invocation`+ Task Promptでの明示確認 | 維持(Hook化しない、意味論判定はDeterministic Hook向きではない) |

**新規Structural Test設計(4A.5.1-2、コードはまだ書かない)**:
`13_tests/test_agent_governance.py`案。`.claude/agents/*.md`と
`.claude/skills/*/SKILL.md`のFrontmatterを`yaml.safe_load`でParseし、
1. 3 Subagentいずれも`tools`に`Write`/`Edit`/`Bash`/`NotebookEdit`を
   含まないこと。
2. `phase-close`の`disable-model-invocation`が`true`であること。
3. Skill名・Agent名がそれぞれ重複していないこと(D0044の一度きり確認を
   永続Regression化)。
4. 各SubagentのPreload Skill名(`skills:`)が実在するSkillディレクトリ名と
   一致すること。

---

## I. Hook Plan

| Hook候補 | Trigger | Protected property | False-positive risk | Failure behavior | Need now? |
|---|---|---|---|---|---|
| Protected Path Warning | `PreToolUse`, matcher `Edit\|Write`, path pattern `^(core/\|app\.py\|tests/)` | 既存Screening Toolへの意図しない変更 | 低(将来Screening Tool自体の意図的改修時のみNoise。**Block ではなく Warning に留める**設計とし、必要な場合はUserが承認して続行できるようにする) | Warn(non-blocking推奨、`exit 0`+メッセージ出力。誤ってBlockして正当な作業を止めるリスクを避ける) | **Yes**(4A.5.1-3。このLabで最も頻繁に確認している事項であり、毎Round手動`git diff --stat`に依存している現状を構造的に補強する価値が高い) |
| Secret Guard(commit時) | `PreToolUse`, matcher `Bash`, `git commit`/`git add`パターン | `.env`/APIキーらしき文字列のCommit | 中(誤検知でCommitが止まるリスク、`HOOKS_PROPOSAL.md`既記載の懸念のまま) | Block(`exit 2`) | **Not now**(既存`_assert_no_secret_like_keys`がRaw Snapshot経路を、`.gitignore`が`.env`をそれぞれ別レイヤーで守っており、二重投資の優先度は低い。SHOULDとして記録のみ) |
| Optional Phase Validation | `PreToolUse`, matcher `Bash`, `git commit`パターン | Commit直前の再Quality Gate | 低 | Block | **Not now**(既存PostToolUse Hookが全Edit後に既にpytest/ruff/mypyを実行しており機能重複) |

**Experimental Agent Hooksは使用しない**(ユーザー§4-2指示通り)。

---

## J. Forward Snapshot PoC Plan(EDINET)

### 何を保存するか

既存`RawSnapshotStore`をそのまま使い、新規Storage機構は作らない。
`snapshot_id`命名規則のみ新設: `edinet_historical_docs_{YYYYMMDD}_{seq}`
のように、**同一の対象期間**を複数日にわたって繰り返しFetchし、それぞれを
別Snapshotとして保存する(既存Append-only設計と両立、新規コード不要)。

保存されるもの(既存Manifest Fieldそのまま): `retrieved_at`・
`request_parameters`・`content_hash`・`record_count`。加えてEDINET Document
本体をDownloadした場合は既存`raw_retrieval_hash`(Adapter出力)と
`compute_canonical_zip_content_hash()`の結果Hex Digestを、**Byte列自体は
保存せずHash値のみ**記録する(D0046追記2の運用方針をそのまま踏襲)。

### 何を証明できるか

- 同一Historical Documents Listへの複数回Retrievalで、Raw Payload
  (Outer Hash)自体が変化するかどうか(D0046の実観測=変化するとの前例あり)。
- 同一docIDのDocument本体を複数回Downloadした際、Canonical Content Hash
  が本当に安定しているか(D0046追記2の1回限りの観測を複数回・複数docIDへ
  拡張できるかの確認)。

### 何を証明できないか(過剰主張しない)

- **過去のPIT(このRound以前の時点でEDINETがどう見えていたか)を遡って
  再現することはできない**(Forward Snapshot PoCはこれから先の観測のみを
  蓄積する。ユーザー§8の区別通り)。
- 観測期間中に何も変化が無かったとしても、「EDINETが将来も不変である」
  ことの証明にはならない(観測は確率的Evidenceであり、仕様保証ではない)。

**実施タイミング**: TDnet Add-on Local Validation(Phase4B-3の残タスク)
より後にUserのローカル環境で実施(ユーザー§8指示通り)。このRoundでは
Procedure文書化のみ計画し、実行はしない。

---

## K. Artifact Difference Workflow Plan

### 一般化できる部分

- **概念**: `Raw Artifact Identity != Document Content Identity`という
  原則自体(D0046追記2 B節)はSource非依存で正しい。
- **Raw Hash不一致 != Revision**という規約(D0046追記2 E節)もSource非依存。
  T9(セクションD)でGrep確認をLab全体へ一般化する。

### 一般化してはいけない部分(Source依存)

- `compute_canonical_zip_content_hash()`自体はZIP Container形式に特化した
  実装であり、他のContainer形式(署名付きPDF、独自Archive形式等)へ
  そのまま適用できない。**Format非依存の抽象Canonicalizer Interfaceを
  今回設計しない**(過剰Engineering、ユーザー§9「全Sourceへ強制しない」
  指示通り)。
- **TDnetは現状Document本体(PDF)を一切Fetchしていない**ことを実際に
  確認した(`lib/disclosures/providers/tdnet_normalize.py`、`Docs`Fieldは
  `docs_raw`としてOpaque値のまま保持するのみで、PDF Byte自体をDownload
  するAdapter Methodは存在しない、`lib/disclosures/providers/tdnet.py`に
  ZIP/PDF Fetch用のMethodが無いことをGrepで確認)。したがって「TDnetへの
  一般化」は現時点で**対象コードが存在しないため考慮不要**(`NOT_NEEDED`、
  UNKNOWNですらない — 検討対象自体が無い)。TDnet Document本体Fetchが
  将来実装された場合に、その時点でPDF固有のCanonicalization要否を
  改めて調査する。

---

## L. System Health Plan

### 最小Field案(読み取り専用、新規State永続化なし)

既存の`RawSnapshotStore`のManifest群(`01_data/raw/*/*.manifest.json`)と
`SourceCatalog`の`DatasetDescriptor`(`implementation_status`・
`known_limitations`)を**そのままScanするだけ**の読み取り専用Scriptとして
設計する(新規Schema・新規永続Stateはゼロ)。

想定Output(案):

| Field | 導出元 |
|---|---|
| Source名・Capability | `DatasetDescriptor.source_id`/`capability` |
| Implementation Status | `DatasetDescriptor.implementation_status`(既存Enum) |
| Known Limitations | `DatasetDescriptor.known_limitations`(既存Field) |
| Last snapshot retrieved_at(Source別) | `RawSnapshotStore`配下のManifestを走査し最新の`retrieved_at`を集計 |
| Snapshot件数 | 同上のCount |
| PIT Compliance Status | Dで新設するTest Suite(4A.5.1-1)の直近実行結果を参照(Test自体は`pytest`で実行、このScriptはTest結果ファイルを読むだけ、Test実行はしない) |

**大規模Infrastructure(Grafana/Prometheus/PagerDuty/SLA/On-call)は導入しない**
(ユーザー§10指示通り)。Dashboard化はこのRoundでもしない(Scriptの標準出力
のみ)。

**実装Location案**: `Japanese_Equity_Lab/scripts/lab_source_health.py`
(既存`scripts/jquants_financial_summary_diagnostic.py`と同じ「読み取り専用
診断Script」パターンを踏襲、Root直下`scripts/schema_health_check.py`
(Screening Tool専用、Protected)とは完全に別Namespace)。

---

## M. Deferred Items

- **Phase5+**: Hidden Test隔離実装・FDR・Placebo・Walk-forward・Locked
  Test・Factor Neutralization(RESEARCH_RULES.md §Hidden Test隔離に既に
  Roadmapとして記録済み、D0042)。
- **`DecisionEvidenceLog`が`used_evidence_ids`の実際のPIT妥当性を自動検証
  する機能**: 現状`lib/evidence/decision_log.py`はID文字列のみを保持し
  EvidenceRecord自体を持たないため、独立に検証できない(Schema-only、
  Phase5以降のAgent実装時に検討。**現在Repositoryに存在しないComponent
  への言及であり、`FUTURE_REQUIRED_CAPABILITY`に分類、PLAUSIBLE FUTURE
  FAILUREであってCURRENT REPOSITORY DEFECTではない**)。
- **Company IR(Phase4B-4)**: 未着手。
- **TDnet Add-on Local Validation**: `CODE_COMPLETE_AWAITING_ADDON_LOCAL_
  VALIDATION`のまま、このRoundでは変更しない。
- **TDnet Forward Snapshot**: Add-on Local Validation後に検討(ユーザー
  §8指示通り)。
- **TDnet Document本体(PDF)のCanonicalization**: 対象コードが存在しない
  ため検討自体が時期尚早(K節参照)。
- **Format非依存Canonicalizer抽象Interface**: 過剰Engineering、着手しない。
- **Golden Prompt Parity Auditの実施(表の中身)**: このRoundでは方法論の
  みで、実際の対応表作成は次Round。
- **Source Integration Skill v1本体の実装**: Rule ID案のみ、SKILL.md
  自体はこのRoundでは書かない。
- **Construction-time Ordering Invariant(T3で発見したGap)の修正**: 意図的に
  修正しない(Schema変更・Behavior変更の判断が必要なためこのRoundのScope
  外、セクションNのOpen Questionとして残す)。

---

## N. Open Questions(本当に決定不能な事項のみ)

1. **T3で確認した`available_at >= published_at`の未検証Gap
   (`SourceMetadata`/`SourceVersion`/`DisclosureDocument`)を、将来
   Constructor Levelで`raise`する設計へ変更すべきか?**
   Repositoryからは「常に真であるべき」という明文原則(D0042の3項:
   `market_public_at != provider_available_at`)は読み取れるが、「常に
   `available_at >= published_at`」という**大小関係の断定**は、ユーザー
   自身が§4-1-Cで「Source semanticsによって成立し得る場合は勝手に
   invalidと決めない」と釘を刺している通り、今この場でMain Claudeが
   独断で決めるべきではない。`PointInTimeRecord`(旧Price層)は既に
   この方向で`raise`しているため既存Precedentはあるが、Evidence層
   (`SourceMetadata`等)は複数Source(TDnet/EDINET/Fundamentals)を
   横断する分、例外ケースが本当に無いか一段階慎重な確認が要る。
   → **次Round開始時にUserへ確認**(T3はTripwireとして記録するに留め、
   Constructor変更はしない)。

---

## O. Final Recommended Scope

### MUST(次Roundで必ず実施)

1. PIT Compliance Test Suite: T1, T2, T4, T7, T8(セクションD)
2. Agent Governance Structural Test(セクションH)

### SHOULD(次Round内で時間が許せば、少なくとも次々Roundまでに)

3. PIT Compliance Test Suite: T3, T9, T10(セクションD)
4. Deterministic Hook: Protected Path Warning(セクションI)
5. Context Architecture 分類表(セクションE)
6. Artifact Difference Workflow 一般化Doc(セクションK)

### COULD(価値はあるが緊急ではない)

7. Lightweight System Health Script(セクションL)
8. Golden Prompt Parity Audit 実施(セクションG)
9. Source Integration Skill v1 本体実装(セクションF)

### NOT_NOW(このPhaseでは着手しない)

- Secret Guard(commit時Hook)
- Optional Phase Validation Hook
- Forward Snapshot PoC 実行(Procedure文書化のみCOULD、実行はTDnet
  Add-on後)
- Format非依存Canonicalizer抽象化
- Constructor-level Ordering Invariant変更(セクションN)
- 大量並列Research Agent運用の標準化
- Full Observability Infrastructure

---

## 参照

- D0049(`DECISIONS.md`): Fundamentals Evidence PIT Bugfix
- D0050(`DECISIONS.md`): Disclosure Common Core PIT Bugfix
- D0044(`DECISIONS.md`): Phase4A.5 Guardrails
- D0042(`DECISIONS.md`): Phase4 Architecture Cleanup(A系統/B系統区別の初出)
- D0046追記2(`DECISIONS.md`): Raw Artifact Identity != Document Content
  Identity
