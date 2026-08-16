# EVIDENCE_MODEL.md

Evidence Model(Phase3D、DECISIONS.md D0040)の文書。DEFAULT STANCE = DISCONFIRM,
NOT CONFIRMという上位原則(RESEARCH_RULES.md「0.5 情報収集の上位原則」参照)を
Schemaレベルで強制するための設計をまとめる。

## Evidence Type(`lib.evidence.model.EvidenceType`)

情報を同一Fieldへ潰さない。5種類を明確に区別する。

| Type | 定義 | 例 |
| --- | --- | --- |
| FACT | 発生した事実そのもの | TDnetでの「会社予想営業利益を100億→120億へ修正」 |
| CLAIM | 主体が述べたこと自体はFACTだが、内容(将来見通し等)の真偽は別 | 会社IRの「需要は今後も堅調と考えている」 |
| INTERPRETATION | 二次情報源による解釈・要約 | 新聞の「市場予想を上回る上方修正」 |
| OPINION | 個人・SNS等の見解 | Xの「まだ全然織り込まれていない」 |
| IDEA | 投資アイデアの種(Hypothesis化される前) | 既存`lib.schemas.idea.Idea`と同種 |

`Hypothesis`(`lib.schemas.hypothesis.Hypothesis`)はEvidence Typeに含めない。
EvidenceそのものではなくEvidenceから導かれる仮説であり、既存の別schemaとして扱う。

## Derived Relation(`lib.evidence.model.EvidenceRelation`)

Hypothesisが存在する場合のみ付与できる、Evidenceとの関係。**Evidence自体には
一切保持しない**(`EvidenceRecord`にこの値のFieldは無い)。

| Relation | 意味 |
| --- | --- |
| SUPPORTS | Hypothesisを支持する |
| CONTRADICTS | Hypothesisと矛盾する |
| ALTERNATIVE_EXPLANATION | 異なるメカニズムを示唆する(単純な支持/矛盾ではない) |
| NEUTRAL | Hypothesisの評価に無関係・非診断的 |
| UNKNOWN | 関係を判定できない |

`lib.evidence.packet.build_evidence_packet()`が、呼び出し側(人間または将来Agent)
から明示的に与えられた`relations: Mapping[evidence_id, EvidenceRelation]`を
そのままカテゴリへ振り分ける。**自動分類エンジンはPhase3Dでは実装しない**
(Schemaのみ)。

## Source Metadata と PIT(`lib.sources.catalog.SourceMetadata`)

`retrieved_at`(研究所がいつ取得したか)・`published_at`(発行者がいつ公表したか)・
`available_at`(市場参加者が当時実際に参照可能になった日時)・`effective_at`
(必要な場合のみ、制度の施行日等)を区別する。既存`lib.point_in_time`の
`available_at`/`retrieved_at`分離と同じ思想をMulti-Sourceへ拡張したもの。

`EvidenceRecord.is_usable_at(decision_at)`は`source.available_at`のみを基準に
判定し、`retrieved_at`の新しさに影響されない(後日取得した古い情報が、実際より
早く「使えた」ことにならない)。

## Raw / Normalized / Derived(`lib.evidence.model.DataLayer`)

- **Raw**: Providerから取得した原文・Payload。既存`lib.snapshot.RawSnapshotStore`で
  Immutableに保存する(変更なし)。
- **Normalized**: Research Lab共通Schema(`EvidenceRecord`)へ変換したもの。
- **Derived**: AI要約・Event抽出・Sentiment・企業Mapping等。

**AIが生成したDerived DataがRaw Factを上書きしてはならない。**
`EvidenceRecord.ai_derived_provenance`(`AiDerivedProvenance`: model_provider/
model_name/model_version/prompt_version/prompt_hash/input_evidence_ids/
retrieval_plan_hash/generated_at)が設定されている場合、`layer`は`DERIVED`で
ある必要があると`__post_init__`で強制する(`ValueError`)。AI要約・Event抽出等も
再現性/比較可能性の対象とする。

Raw → Normalized → Derived → EvidencePacket → Decision Evidence Logのlineageは、
既存`lib.registry.provenance.ProvenanceStore.trace_to_origin()`でそのまま
追跡できる(`13_tests/test_evidence_lineage.py`参照)。

## Revision / Vintage管理(`SourceVersion` / `RevisionHistory`)

決算の後日訂正・Macro統計のRevision・PDF差し替え・News更新等を表現する。

- `SourceVersion`: source_record_id / source_version_id / supersedes_version_id /
  is_correction / value / event_at / published_at / first_seen_at / available_at /
  retrieved_at / source_version_at / `availability_basis`
- `AvailabilityBasis`: EXACT(公式に確認)/ OBSERVED(研究所が観測)/
  INFERRED(制度的ルールから推定)/ UNKNOWN(不明)。**UNKNOWNの場合、
  available_atをpublished_at等から推測補完しない。**
  `RevisionHistory.as_of(decision_at)`は既定でUNKNOWNのVersionをPIT利用不可として
  除外する(安全側デフォルト、`include_unknown_availability=True`で明示的opt-in)。
- `RevisionHistory.as_of(decision_at)`: decision_at時点で利用可能だった最新の
  Versionを返す(将来のRevisionをLeakしない)。`latest()`はPIT非考慮であり、
  過去Decisionへそのまま流用してはならない。

## News(`lib.evidence.news`)

`NewsScope`(JAPAN/GLOBAL)を明示的に分離しつつ、共通`NewsEvent` Schema
(published_at/scope/country/event_type/entities/affected_sectors/
affected_codes/source/headline/summary/confidence/provenance)で扱う。

Dedup Semanticsとして以下を区別する(単純Dedupで記事を削除しない)。

| Relation | 意味 | 扱い |
| --- | --- | --- |
| EXACT_DUPLICATE | 同一記事の重複取得 | クラスタとして全メンバーを保持(代表選択は表示側の責務) |
| SYNDICATED_COPY | 同じ配信元記事の転載 | 全メンバーを保持 |
| SAME_EVENT_CLUSTER | 独立に報じた別記事(内容・論調が異なりうる) | 全メンバーを保持(Contradictory reportingを保持する) |
| DISTINCT | 無関係 | 単独クラスタ |

想定Pipeline: News Feed → Metadata ingest → Deduplication → Event extraction →
Entity/Country/Sector Mapping → Japanese Equity Relevance Scoring →
Relevant Retrieval → Deep Analysis。Phase3Dでは`NewsEvent` SchemaとDeduplication
までを実装し、Relevance Scoring(AI)はPhase5/6。Global Event → Economic
Transmission → Japanese Sector → Japanese Companyという伝播関係(例:
「US Data Center Capex増 → 電力需要増 → 変圧器需要増 → 銅需要増 → 日本の電気機器
メーカー」)の推論は実装しない(Schema上、`affected_sectors`/`affected_codes`が
将来のGraph構造への拡張余地として存在するのみ)。

## Relevant Retrieval(`lib.evidence.retrieval`)

「Dataが多いほど全部AIに渡す」設計を禁止する。例: 「BIPROGYのQ1決算後下落は
構造的減速か、一時的な期ずれか」という問いにはEarnings/Guidance/Prior
Earnings/TDnet Disclosure/IR Material/Pre-Post Earnings Price/Volume/関連
Japan IT・DX News/Consensus等が必要だが、Copper price等明確に関連しないDataは
Defaultでは渡さない。

`ResearchQuestion` → `plan_retrieval(requested_capabilities=...)` →
`RetrievalPlan`(`DataCapability`全種について含める/除外する理由を記録、
空文字列は許容しない) → `retrieve_evidence(plan, evidence_pool,
decision_at=...)`(Capability一致 かつ PIT利用可能なEvidenceのみ返す)。
Retrieverの選択自体も`RetrievalPlan.decisions`で後から監査できる。

LLMによるRetrieval Selection(「関連しそうなCapabilityをAIが選ぶ」)はPhase3Dでは
実装しない。呼び出し側が明示的に指定した`requested_capabilities`に基づいて
機械的に判定するのみ(将来Agentがここへ差し込む余地を残す設計)。

## EvidencePacket(`lib.evidence.packet`)

将来Agentへ渡すEvidenceの単位。

- research_question / as_of / included_evidence_ids /
  excluded_candidate_sources / retrieval_reason / missing_expected_sources /
  positive_evidence / negative_evidence / alternative_explanation_evidence /
  contradictory_evidence / unknowns / provenance_id

**Conclusion/Verdict/Supportedに相当するFieldを意図的に持たない。**
Evidence不足を自動でPositive/Negativeへ昇格させる経路がSchema上そもそも
存在しない(`13_tests/test_evidence_packet.py::
test_evidence_packet_has_no_overall_verdict_field`で`dataclasses.fields()`により
構造的に確認する)。

`build_evidence_packet()`は、呼び出し側から明示的に与えられた
`relations: Mapping[evidence_id, EvidenceRelation]`をそのままカテゴリへ
振り分けるだけで、件数による判定・上書きは一切行わない(情報件数の多数決を禁止する)。
`conflicting_evidence_ids`を指定したEvidenceは`relations`での分類に関わらず
`contradictory_evidence`へ入り、Conflicting Sourcesの自動統合(どちらか一方を
機械的に選ぶこと)を避ける。`relations`に含まれないevidence_id(=関係が未判定)は
`unknowns`へ入る(INSUFFICIENT_EVIDENCEを黙ってPositive/Negativeへ倒さない)。

### Anti-Confirmation Test(`13_tests/test_evidence_packet.py`)

1. Positive Evidenceしか無いFixtureでも、`missing_expected_sources`で
   「反証探索を行っていないこと」自体を明示的に表現できる。
2. Social Opinion(SOCIAL Authority)が10件`SUPPORTS`でも、Primary Official
   Fact(PRIMARY_OFFICIAL Authority)1件の`CONTRADICTS`は消えない・上書きされない。
3. `EvidencePacket`に`verdict`/`conclusion`/`supported`等に相当するFieldが
   一切存在しない。
4. Conflicting Sources(矛盾する2件のFACT)は、どちらか一方へ自動統合されず、
   両方が`contradictory_evidence`へ保持される。
5. Evidence皆無の場合でも、`positive_evidence`等へ自動的に何かが昇格することはない。

## Decision Evidence Log(`lib.evidence.decision_log`)

将来のAI判断について、Used Evidence / Not-Used-or-Unavailable Evidence /
Main Drivers / Contradictions / Unknownsを保存できるSchema。

```
Prediction -> Actual Result -> Which Evidence Helped? -> Which Evidence Misled?
-> Missing Evidence? -> Knowledge Update
```

という検証を将来行うための土台。**ここではまだBUY/SELL Agentを実装しない。**
`predicted_outcome`/`actual_outcome`は将来の検証用に空のまま保存できるFieldとして
用意するのみ。

## Ablation Lineage(`lib.schemas.experiment.Experiment.used_data_capabilities`)

将来、Fundamental + Momentum + Positioning + News + Macroという
Strategy/Predictionがあった場合、News無し・Macro無し・Positioning無し等を
比較できるよう、「どのData Capabilityを使用したExperimentか」を
`Experiment.used_data_capabilities`(`tuple[str, ...]`)で追跡可能にする。
既存Experimentとの後方互換のため既定値は`()`(「未記録」であり「何も使っていない」
という意味ではない)。**Ablation Engine自体はPhase3Dでは実装しない。**
