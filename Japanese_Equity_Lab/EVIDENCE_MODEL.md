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

`retrieved_at`(研究所がいつ取得したか)・`published_at`(発行者/取引所がいつ
公表したか、= market_public_at相当)・`available_at`(**この特定のProvider経由で
いつ参照可能になったか**、= provider_available_at相当)・`effective_at`
(必要な場合のみ、制度の施行日等)を区別する。既存`lib.point_in_time`の
`available_at`/`retrieved_at`分離と同じ思想をMulti-Sourceへ拡張したもの。

`EvidenceRecord.is_usable_at(decision_at)`は`source.available_at`のみを基準に
判定し、`retrieved_at`の新しさに影響されない(後日取得した古い情報が、実際より
早く「使えた」ことにならない)。

### market_public_atとprovider_available_atの分離、2種類のPIT研究(D0042)

例: 15:30に会社が決算公表(`published_at`)、J-Quants Light経由では18:00に
取得可能になった(`available_at`)、Research Labが実際に取得したのは18:03
(`retrieved_at`)。この3つは全て異なりうる。既存のField(published_at/
available_at/retrieved_at)で十分表現できるため、Fieldを増やしすぎず
Semanticsを明文化する形で対応した。

Historical Researchには少なくとも2種類ある。

- **A. Market Information Study**: 「市場参加者がいつ情報を知り得たか」
  (`published_at`基準)。
- **B. Reproducible System Simulation**: 「このResearch LabのData Pipelineでは
  いつ情報を取得できたか」(`available_at`基準)。**このLabのPIT判定は既定でB系統**。

`lib.evidence.model.AvailabilitySemantics`(`MARKET_PUBLIC_AT`/
`PROVIDER_AVAILABLE_AT`)と`lib.schemas.experiment.Experiment.
availability_semantics`(`str | None`、既定`None`=未記録)で、どちらの基準を
使用したExperimentかを追跡できる。

### Originating SourceとDelivery Providerの分離(D0042)

`SourceMetadata.originating_source`(情報の原典、例: `"EDINET"`)と
`delivery_provider`(それをResearch Labへ届けたProvider、例: `"JQUANTS"`)は
別概念であり分離する。EDINET由来の情報をJ-Quants経由で取得した場合
`originating_source="EDINET"` `delivery_provider="JQUANTS"`、直接EDINET APIから
取得した場合は両方`"EDINET"`。同じ原典を複数Providerから取得した場合の比較、
Provider障害・遅延・変換による差異の追跡、Provenanceの正確な保持に使う。
両方Optional(既定`None`)で既存`SourceMetadata`利用箇所との後方互換を維持する。

## Source AuthorityとEvidence Contentの信頼性を分離する(D0041)

`SourceAuthorityClass`(PRIMARY_OFFICIAL/COMPANY_PRIMARY/VERIFIED_SECONDARY/
SECONDARY/SOCIAL/USER_SUPPLIED)は、**信頼度の単純な順位・点数ではなく、
Sourceの性質を表すカテゴリである。** 将来、`PRIMARY_OFFICIAL=100点、
SOCIAL=10点`のような単純なスコアリングや、Authority Classに基づく多数決・
重み付け投票に使ってはならない(「情報件数の多数決を禁止する」という
RESEARCH_RULES.md「0.5」の原則と同様の理由による)。

例えば企業IR(`COMPANY_PRIMARY`)は、「会社が営業利益予想を100億円と発表した」
という事実の確認には非常に強いSourceである一方、「今後も需要は堅調である」という
経営陣の将来見通しの真偽まで自動的に高信頼とみなしてはならない。前者は
`EvidenceType.FACT`(発表したこと自体は事実)、後者は`EvidenceType.CLAIM`
(内容の真偽は別、上記Evidence Type表参照)であり、**Source Authority(出所の
位置づけ)とEvidence Content(内容そのものの信頼性)は常に分離して扱う。**

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
  is_correction / `revision_reason`(訂正理由、任意、D0042) / value / event_at /
  published_at / first_seen_at / available_at / retrieved_at /
  source_version_at / `availability_basis`
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

## Value Availability(`lib.evidence.model.ValueAvailability`、Phase4A実装、D0043)

Normalized Fundamental Record(`lib.fundamentals.model.FundamentalMetric`)に
おける、数値欠落の意味を区別するためのStored Value State。**NULLを0へ変換しない
という契約を型で表現する。** D0042時点の2値予約(`NOT_YET_FETCHED`/
`NOT_APPLICABLE`)から、Phase4A実装時に4値へ再設計した:

- `PRESENT`: 値が実際に開示されている。
- `NOT_APPLICABLE`: 会計基準上、そもそも存在しない指標(0ではない。例: IFRS/
  USGAAPで経常利益相当Fieldが存在しない場合)。会計基準から明示的に確認できる
  場合のみこの値を使い、Rawが単に空文字列というだけでは断定しない
  (`lib.fundamentals.normalize.resolve_value_availability()`)。
- `MISSING_OR_UNSPECIFIED`: Provider側で値が空/未指定だが、理由が
  会計基準起因と確認できない(単なる欠損の可能性を含む)。
- `UNKNOWN`: Provider値のParseに失敗した等、状態自体を確定できない。

**`NOT_YET_AVAILABLE`は意図的に含めない。** これはMetric Value自体の属性ではなく、
As-of Query(`lib.fundamentals.view.fundamentals_as_of()`)の結果側に属する
概念であり、該当Recordが存在しない場合は`None`を返すことで表現する
(Value StateとTemporal Usabilityの分離、D0043 Additional Safety Corrections)。

実際のFundamental Record Schema(`DisclosureEnvelope`/`FundamentalMetric`)は
`lib/fundamentals/`としてPhase4Aで実装済み(Field名は未検証、
`DATA_SOURCE_ARCHITECTURE.md`「Phase4A Fundamental Schema Contract」・
DECISIONS.md D0043参照)。actual/company_forecast/next_year_forecast、
quarterly period(1Q〜5Q/FY/OTHER)、cumulative vs standalone、consolidated/
non_consolidated、disclosure_date/time/number、document_type、
accounting_standard、revision/correction、currency/unitはいずれも別Field/
別Recordとして区別する。

## Ablation Lineage(`lib.schemas.experiment.Experiment.used_data_capabilities`)

将来、Fundamental + Momentum + Positioning + News + Macroという
Strategy/Predictionがあった場合、News無し・Macro無し・Positioning無し等を
比較できるよう、「どのData Capabilityを使用したExperimentか」を
`Experiment.used_data_capabilities`(`tuple[str, ...]`)で追跡可能にする。
既存Experimentとの後方互換のため既定値は`()`(「未記録」であり「何も使っていない」
という意味ではない)。**Ablation Engine自体はPhase3Dでは実装しない。**
