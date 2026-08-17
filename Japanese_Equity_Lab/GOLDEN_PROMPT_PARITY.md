# Golden Prompt Parity Audit — Source Integration Skill v1(4A.5.1-5)

## スコープの正直な限定(Documentation Integrity)

この監査は本来「旧Source Integration Promptの各Requirementを、逐語的に
`SKILL_RULE`/`SOURCE_SPECIFIC_RULE`/`INTENTIONALLY_REMOVED`へMapping
する」ことを理想とする。しかし**この元の生Promptテキストは、このSession
自体が過去SessionのCompaction(要約)後に開始しているため、逐語的な形では
このContextに存在しない**。これを実施済みであるかのように装うことは
D0049で発生した「実施していないReviewを実施済みと書く」誤りの再発になる
ため、絶対にしない。

代わりに、**`DECISIONS.md`(D0043/D0045/D0046+追記/D0047/D0048/D0049/
D0050)と`EDINET_SOURCE_ONBOARDING.md`/`TDNET_SOURCE_ONBOARDING.md`
(特に`EXTERNAL_OFFICIAL_SPEC_VERIFICATION`節、ユーザー申告内容を
Contemporaneousに記録した箇所)を、Requirementの権威ある記録として使う**。
これはこのLab自身が「なぜDECISIONS.mdへ記録するのか」という目的
(後から検証可能にするため)にまさに合致する代替であり、逐語Prompt
Parityの完全な代替ではないが、恣意的な省略でもない(このScope限定
自体を隠さず明記する)。

## Requirement-by-Requirement Mapping

| # | Requirement(出典) | Mapping | 根拠(Rule ID / Doc / 理由) |
|---|---|---|---|
| 1 | Fundamentalは`code/date/sales/profit`のようなWide Tableへ早期に潰さない(D0043 §Disclosure単位) | `SOURCE_SPECIFIC_RULE` | `lib/fundamentals/model.py`のSchema設計そのもの(`DisclosureEnvelope`/`FundamentalMetric`分離)。Common Core Ruleにするには一般性が低く、Fundamentals固有のSchema設計判断としてモデルへ残す |
| 2 | Actual/Forecast/Period/Scopeを混同しない(D0043) | `SOURCE_SPECIFIC_RULE` | Fundamentals固有のEnum設計(`ActualOrForecast`/`FiscalYearTarget`等)。Common Coreへは一般化せず |
| 3 | 未確認のSource仕様を推測で埋めない、公式仕様が確認できなければUNKNOWN(D0043全体、`source-onboarding` Skillの既存原則) | `SKILL_RULE` | `SOURCE-001`(Source固有Field意味論を推測しない) |
| 4 | Document != Event、本文Semantic Extractionはこの段階では行わない(D0045 Core Principle) | `SKILL_RULE` | `EVIDENCE-001` |
| 5 | `DocumentRelationship`は明示的根拠がある場合のみ、時系列だけから推測しない(D0045) | `SKILL_RULE` | `RAW-002`(Raw Hash不一致からの推測禁止として一般化。時系列推測禁止という上位原則も同じRuleの一部として扱う) |
| 6 | Append-only、過去Documentを新Documentで上書きしない(D0045) | `SKILL_RULE` | `RAW-001` |
| 7 | `originating_source`と`delivery_provider`を分離する(D0042、D0045以降全Source共通) | `SKILL_RULE` | 現行v1のRule ID一覧には未採番。**Gap認定**(下記「見つかったGap」参照) |
| 8 | EDINET: `disclosure2.edinet-fsa.go.jp`等、公式Doc/APIへこのSessionから疎通できない(D0046 §2/§24) | `INTENTIONALLY_REMOVED` | Session固有のNetwork Policy事実であり、Rule化する意味的内容を持たない(再現性のあるRuleではなく、単発のEnvironment Finding)。理由: `local-validation` Skillが既にこの種の状況への対応手順を持つため、重複した新Ruleは作らない |
| 9 | EDINET: 未知のDocType/Codeは`UNKNOWN`へfail closed、即例外で全処理停止しない(D0046追記) | `SKILL_RULE` | `SOURCE-001` |
| 10 | EDINET: Raw Artifact Identity != Document Content Identity、Canonical Hashを別途持つ(D0046追記2) | `SKILL_RULE` | `RAW-003` |
| 11 | EDINET: Raw Hash不一致だけで訂正・改版と判定しない(D0046追記2) | `SKILL_RULE` | `RAW-002` |
| 12 | EDINET: ZIP展開時のPath Traversal/Symlink/暗号化/Zip Bomb対策(D0046追記2 skeptic-reviewer Finding対応) | `SOURCE_SPECIFIC_RULE` | ZIP形式固有のSafety実装(`edinet_zip.py`)。Container形式ごとに異なるためCommon Core化しない(RAW-003のDocstring内で明示済み) |
| 13 | TDnet: `/v2/td/files`・`/v2/td/bulk`のURLは15分で失効、永続識別子として扱わない(D0048、ユーザー申告) | `SKILL_RULE` | `SOURCE-002` |
| 14 | TDnet: `DiscDate`+`DiscTime`は`market_public_at`相当、provider availabilityとは別(D0048 §2、ユーザー申告) | `SKILL_RULE` | `PIT-002`の適用例。Source-specific詳細(具体的なField名)は`TDNET_SOURCE_ONBOARDING.md` §7が保持 |
| 15 | TDnet: Rate Limit(J-Quants経由、D0048 §2) | `SOURCE_SPECIFIC_RULE` | 具体的な数値はProvider固有Planに依存するため`TDNET_SOURCE_ONBOARDING.md`側に残す |
| 16 | Fundamentals: `available_at`は`market_public_at`へFallbackしない(D0049) | `SKILL_RULE` | `PIT-003` |
| 17 | Fundamentals: `retrieved_at`はObserved Safe Availability(D0049) | `SKILL_RULE` | `PIT-004` |
| 18 | Fundamentals: 単一Metricから新旧比較文言を生成しない(D0049 §2) | `SKILL_RULE` | `EVIDENCE-002` |
| 19 | Disclosures Common Core: 同型のFallback Bugを`lib/disclosures/evidence.py`でも修正(D0050) | `SKILL_RULE` | `PIT-003`(D0049と同一Rule、Module横断で同じRuleが適用される好例としてこのAuditに明記) |
| 20 | UNKNOWN Basisは既定で除外、Fallback先にしない(D0040以降、複数Decisionで反復確認) | `SKILL_RULE` | `PIT-001` |
| 21 | Evidence Contentに解釈語(bullish/buy等)を含めない(D0043/D0045共通) | `SKILL_RULE` | `EVIDENCE-002` |
| 22 | Reviewer Agent(pit-auditor/skeptic-reviewer)はCodeを変更しない、Main Claudeのみ修正する(全Phase共通、`CLAUDE_CODE_RESEARCH_WORKFLOW.md`) | `SKILL_RULE`ではなく既存の`CLAUDE_CODE_RESEARCH_WORKFLOW.md`側で扱う | Source Integration固有ではなくAgent Governance全体のRuleのため、このSkillへ複製しない(4A.5.1-2のTest対象) |

## 見つかったGap(Auditの結果、隠さず記録)

**#7(`originating_source`/`delivery_provider`分離、D0042)がRule ID一覧に
未採番だった。** これはSource統合において実際に繰り返し重要になっている
原則(EDINET-via-J-QuantsとEDINET直接取得の区別等)であり、Golden Prompt
Parity Auditの目的(要件の落ちを見つけること)が実際に機能した例として
記録する。**対応**: `SKILL_RULE`として`SOURCE-004`(Originating Source
とDelivery Providerは分離して記録する)をSource Integration Skill v1へ
追加する(このRound内で追記、下記「対応」参照)。

## Adversarial Test Scenarios(ユーザー指定の3例)

いずれも「新しいTestを書く前に、既存Coverageで実際に検証済みかを確認する」
という方針(既存Testの重複回避、D0050の教訓)に従い、まず既存Testを確認し、
実際に検証済みであることを確認した(架空の安心ではなく実測結果)。

1. **provider availability UNKNOWNを与えた時、market_public_atへ
   Fallbackしてよいと解釈しない**
   - 検証済み: `13_tests/test_pit_principles.py::test_pit_p01_unusable_
     between_market_public_at_and_retrieved_at`(Fundamentals/Disclosures
     両方でParametrize済み)、`13_tests/test_fundamentals_evidence_pit.py`
     ・`13_tests/test_disclosures_evidence_pit.py`(D0049/D0050の詳細
     Regression)。

2. **raw hash changedを与えた時、revision detectedと自動解釈しない**
   - 検証済み: `13_tests/test_edinet_zip_canonicalize.py::test_edinet_
     zip_module_never_constructs_document_relationship`、
     `13_tests/test_pit_principles.py::test_defense_in_depth_provider_
     normalizer_files_never_construct_document_relationship`
     (Lab全体のProvider層へ一般化済み)。

3. **TDnet DiscDate+DiscTimeを与えた時、J-Quants provider_available_at
   と同一視しない**
   - 検証済み: `13_tests/test_tdnet_normalize.py::test_provider_
     available_at_always_unknown_no_fallback`(`market_public_at`が
     確認できても`provider_available_at`は常に`None`/`UNKNOWN`のまま
     であることを直接確認)、`13_tests/test_disclosures_evidence_pit.py::
     test_tdnet_style_document_uses_retrieved_at_not_market_public_at_
     despite_exact_value`。

**3例とも、新規Test追加は不要だった(既存Coverageで実際に検証済み)。**
これ自体がGolden Prompt Parity Auditの価値を示す結果である — 要件が
Skillへ正しく反映されているだけでなく、Test Suiteでも実際に守られている
ことを確認できた。

## 対応: SOURCE-004の追加

上記Gapを踏まえ、`Source Integration Skill v1`
(`.claude/skills/source-integration/SKILL.md`)へ以下を追加する:

```
### SOURCE-004: Originating SourceとDelivery Providerは分離して記録する

情報の原典(originating_source)と、それをこのLabへ届けたProvider
(delivery_provider)は別概念であり分離する。同じ原典を複数Provider経由で
取得した場合の比較や、Provider障害・遅延・変換による差異の追跡に使う。
```

## Reviewer Review

`skeptic-reviewer`によるReviewをこのAudit完成後に実施する(下記
Completion Report参照)。Reviewer FindingはEvidence再確認の上で
採否を判定し、自動採用しない。
