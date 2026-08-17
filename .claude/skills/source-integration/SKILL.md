---
name: source-integration
description: >-
  Concrete, Rule-ID-based checklist for integrating or modifying a Data
  Source Adapter/Normalizer in Japanese Equity Lab (currently EDINET and
  TDnet; applies to any future Disclosure/Fundamental Source too). Use
  when writing or reviewing code in lib/disclosures/providers/,
  lib/fundamentals/, or lib/disclosures/evidence.py and
  lib/fundamentals/evidence.py. Extracted from real EDINET/TDnet
  integration history (D0043/D0045/D0046/D0048/D0049/D0050), not written
  from first principles — every rule below cites the real incident or
  code it comes from.
paths: Japanese_Equity_Lab/**
---

# Source Integration Rules(v1、4A.5.1-4)

このSkillは、新しいSourceを実際にRepositoryへ接続した経験(EDINET/TDnet)
から抽出した**具体的な禁止事項**の一覧である。「PITに気をつける」
「rawを保存する」のような抽象的な要約は書かない。各Ruleには、それが
実際にどのIncident/Codeから来たかを明記する(架空の一般論ではない)。

Rule ID自体は暫定であり、今後の統合経験に応じて追加・再編してよい
(Golden Prompt Parity Audit実施時に見直すことを想定)。

## PIT-*(Point-in-Time)

### PIT-001: UNKNOWNはFalseでも0でもない

`AvailabilityBasis.UNKNOWN`/`ValueAvailability.UNKNOWN`は、Pythonの
`if not x`や`x or default`のような暗黙変換で「無い」「偽」「0」として
扱ってはならない。値が不明であることそのものを保持する。

- **実装**: `RevisionHistory.as_of()`(`lib/evidence/model.py`)と
  `disclosures_as_of()`(`lib/disclosures/view.py`)は、`availability_
  basis`/`market_public_at_basis`が`UNKNOWN`のRecordを**既定で除外**する
  (`include_unknown_availability=False`)。UNKNOWNを「使えない」の意味で
  安全側に倒すのはこの除外Logicであり、UNKNOWN自体を0やFalseへ変換して
  いるわけではない。
- **回帰Test**: `13_tests/test_pit_principles.py::test_pit_p06_*`

### PIT-002: market_public_at != provider_available_at

市場公表時刻(A系統、`market_public_at`)と、このLabのProvider経由で実際に
参照可能になった時刻(B系統、`provider_available_at`)は別概念であり、
どちらか一方だけを見て研究すると異なる結論になりうる(D0042)。

- **実装**: `lib.evidence.model.AvailabilitySemantics`
  (`MARKET_PUBLIC_AT`/`PROVIDER_AVAILABLE_AT`)。

### PIT-003: market_public_atはUnknown Provider Availabilityの代替にしない

`provider_available_at`が未確認(`UNKNOWN` Basis)の場合でも、
`available_at`へ`market_public_at`をFallbackさせてはならない。
`market_public_at`は通常`provider_available_at`より**早い**ため、これを
`available_at`(PIT判定の直接基準)へ代入すると、実際にはまだ研究所側で
取得可能でなかった時点を「利用可能だった」と誤認する(Future Leakage)。

- **実際のIncident**: D0049(`lib/fundamentals/evidence.py`)とD0050
  (`lib/disclosures/evidence.py`)で、**独立した2つのModuleが同型の
  このBugを持っていた**。旧実装は`available_at = envelope.market_public_at
  or envelope.retrieved_at`のような`or`式で、`market_public_at`が
  存在すればそちらを優先してしまっていた。
- **回帰Test**: `13_tests/test_fundamentals_evidence_pit.py`、
  `13_tests/test_disclosures_evidence_pit.py`、
  `13_tests/test_pit_principles.py::test_pit_p01_*`/`test_pit_p02_*`。

### PIT-004: retrieved_atはObserved Safe Availability Timestampであり、正確なProvider Availabilityそのものではない

`provider_available_at`が未確認の場合、`available_at`の代わりに
`retrieved_at`(「少なくともこの時刻には研究所が取得済みだった」という
Observed Fact)を使う。ただしこれは**下限としての安全な代用**であり、
「Providerが正確にいつ利用可能にしたか」を意味しない(実際には
`retrieved_at`より前から利用可能だった可能性がある。それでも
`market_public_at`より安全側 — Future Leakageを起こさない — なので
代用として選ばれている)。

- **実装**: `disclosure_metric_to_evidence()`/`disclosure_document_to_
  evidence()`のDocstringに明記。

## RAW-*(Raw Artifact)

### RAW-001: Raw Artifactはimmutable

一度保存したRaw Snapshotを上書きしない(Append-only)。同一`snapshot_id`
への再保存はエラーにする。

- **実装**: `lib.snapshot.RawSnapshotStore.save()`、
  `AppendOnlyViolationError`(`lib/errors.py`)。
- **回帰Test**: `13_tests/test_snapshot.py::test_duplicate_snapshot_id_
  is_rejected`、`13_tests/test_tdnet_integration.py::test_raw_snapshot_
  append_only_rejects_overwrite`。

### RAW-002: Raw Hash不一致 != Revision

同一Documentを複数回取得した際にRaw Bytesの Hash(`raw_retrieval_hash`)
が変わったからといって、それだけで「Documentが訂正・改版された」と
自動推論してはならない。

- **実際のIncident**: D0046追記2。同一`docID`のEDINET Documentを2回
  Downloadしたところ、Outer ZIP SHA-256は変化したが、ZIP内部の全Member
  (filename/size/CRC/content hash)は完全に一致していた。原因は
  `OBSERVED_BEHAVIOR`(ZIP Member Timestampが変化)としてのみ記録し、
  断定しない。
- **実装**: `lib.disclosures.providers.edinet_zip`は`DocumentRelationship`
  /`DuplicateRelationKind`のいずれもImportしない(構造Testで確認)。
- **回帰Test**: `13_tests/test_edinet_zip_canonicalize.py::test_edinet_
  zip_module_never_constructs_document_relationship`、
  `13_tests/test_pit_principles.py::test_defense_in_depth_provider_
  normalizer_files_never_construct_document_relationship`(EDINET単体
  からLab全体のProvider層へ一般化済み)。

### RAW-003: Raw Artifact Identity != Document Content Identity

Container形式(ZIP等)のRaw Artifactでは、Container Metadata(Timestamp・
圧縮方式・Member順序)が異なるだけでArtifact全体のHashは変わりうるが、
実際のDocument Content(各Memberの中身)は同一でありうる。両者を区別する
2種類のHashを別々に持つ。

- **実装**: `raw_retrieval_hash`(このRetrievalで実際に取得したArtifact
  そのもののHash)と`compute_canonical_zip_content_hash()`
  (Container Metadataを除外し、Member内容のみから決定論的に計算した
  Hash、`lib/disclosures/providers/edinet_zip.py`)。
- **重要な境界**: Canonicalizerは**Container形式ごとに固有の実装が必要**
  であり、全Sourceへ強制しない。TDnetは現状Document本体(PDF)を一切
  Fetchしていない(`tdnet_normalize.py`の`docs_raw`はOpaque値として
  保持するのみ)ため、この時点でTDnet用Canonicalizerは**存在しないし
  必要でもない**(対象コード自体が無い)。

## EVIDENCE-*(Evidence Semantics)

### EVIDENCE-001: Document != Evidence解釈 != Event

「この会社がこのTitleの文書を公開した」という事実(FACT)と、文書本文の
意味内容(会社予想・経営陣の見通し等)は分離する。本文Semantic
Extraction(数値抽出・Event分類・Claim抽出)はSource Integration時点では
行わない。

- **実装**: `lib/disclosures/model.py`モジュールDocstring「Core
  Principle」、`disclosure_document_to_evidence()`は開示という事実のみを
  `EvidenceType.FACT`として記述する。

### EVIDENCE-002: 開示という事実だけからPositive/Bullish/Buyの解釈を作らない

Evidence Content(`disclosure_document_to_evidence()`/`disclosure_
metric_to_evidence()`が生成する文字列)には、bullish/buy/sell/好調/
割安/強気等の解釈語を一切含めない。単一Metric/単一Documentから
Revision文言(「100→120へ変更」等)を生成することも禁止する(単一時点の
Metricからは新旧比較を導出できない)。

- **実装**: `disclosure_metric_to_evidence()`Docstring「Revision Wording
  上の注意」。
- **回帰Test**: `13_tests/test_fundamentals_evidence_pit.py`の
  interpretive-language absence Test。

## SOURCE-*(Source-specific)

### SOURCE-001: Source固有Field意味論を推測しない

公式仕様で確認できない値の意味は`UNKNOWN`のまま保持し、推測で埋めない。
未知のProvider Code/DocTypeは`UNKNOWN`へfail closedし、警告Logを残す
(即例外で全処理停止はしない)。

- **実装**: `edinet_normalize.py`の`unknown_member`(各Enum固有の
  UNKNOWN)への変換、`logger.warning("edinet: 未知の%s値 ...")`。

### SOURCE-002: Ephemeral URLは永続識別子として扱わない

一部Sourceが返すDownload URL(署名付きURL等)は短時間で失効する。
これをDocumentの永続識別子として保存・比較してはならない。

- **実際のIncident**: TDnetの`/v2/td/files`・`/v2/td/bulk`が返す
  Download URLは15分で失効する(ユーザー確認済み仕様、D0048)。
- **実装**: `lib/disclosures/providers/tdnet.py`モジュールDocstring
  「Ephemeral URL Safety」節。

### SOURCE-003: Current Provider History != Historical Provider Snapshot

現在のAPI Responseから、過去のある時点でProviderがどう見えていたかを
遡って完全再現できるとは主張しない(例: Entity識別子の対応付けは
`valid_from`/`valid_until`で時期ごとに区別する、`lib.sources.
entity_registry.EntityRegistry`)。将来のForward Snapshot観測(継続的な
保存)と、過去のPIT再構築(Historical Provider PIT Reconstruction)は
別の主張であり混同しない。

- **実装**: `EntityRegistry.resolve(as_of=...)`(現在のMappingを過去の
  Decisionへ混入させない)。
- **回帰Test**: `13_tests/test_pit_principles.py::test_pit_p07_*`。

## Source-specific Rulesとの境界

上記はSource非依存のCommon Core Ruleである。各Providerの`*_normalize.py`
固有の制約(例: EDINETの`market_public_at`は現状常に`None`/`UNKNOWN`、
TDnetは`DiscDate`+`DiscTime`から`market_public_at`を構築するが
`AvailabilityBasis.EXACT`は使わない)は、このSkillへ丸ごとCopyせず、
既存の`EDINET_SOURCE_ONBOARDING.md`/`TDNET_SOURCE_ONBOARDING.md`/
`DISCLOSURE_ARCHITECTURE.md`/`TDNET_ARCHITECTURE.md`から個別参照する
(重複による将来の食い違いを避ける)。

## Golden Prompt Parity

このSkillの内容が、過去のSource Integration関連User Promptの要件を
落としていないかは、別途`Requirement-by-Requirement` Auditで確認する
(4A.5.1-5、`GOLDEN_PROMPT_PARITY.md`参照)。
