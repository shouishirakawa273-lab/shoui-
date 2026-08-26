"""ResearchArtifact: 1企業 + 明示的as_ofについて、PIT-safeなEvidenceだけから
構造化Research Artifactを生成する最小Vertical Slice(Stage 3 v1)。

**Research != Decision。** BUY/SELL/target price/position sizingに相当する
Fieldはこのモジュールのどこにも存在しない(構造的禁止、
`13_tests/test_research_artifact.py::test_research_artifact_carries_no_buy_sell_field`
参照、Phase5の`test_val026_split_run_result_carries_no_buy_sell_field`と
同じパターン)。

新しいEvidence Frameworkは作らない。既存の`Hypothesis`/`EvidenceRecord`/
`EvidencePacket`/`RevisionHistory`/`ResearchQuestion`/domain as-of view/
`ProvenanceStore`をそのまま再利用する。このモジュールが新規に追加するのは
「Evidenceの集合からBull/Base/Bear + 3軸Confidence + Conclusionを持つ
Research Artifactを組み立てる」という薄い合成層のみ。

## D0057との関係(Positioning Evidence Pathを安全に扱う)

D0057(ARCHITECTURE_GAP)は、Positioning(価格由来)Dataについて、Evidence
Path(`lib.positioning.evidence.positioning_record_to_evidence()`、
`record.retrieved_at`のみを基準にavailable_atを決定)とas_of Path
(`lib.positioning.derived.price_derived.resolve_available_at()`、Session
Close基準・`AvailabilityBasis.INFERRED`)が異なるAvailability推定戦略で
あり、`retrieved_at`がSession Closeより早い場合(例: 取引時間中の
Intraday取得)にEvidence PathがAs-of Pathより早く「利用可能」と誤判定
しうることを確認した(D0057 §5 Failure Example)。

このモジュールはResearch Artifactにとって最初の実際のEvidence Path
Consumerであるため、D0057を場当たり的に回避せず、`positioning_record_to_
evidence()`を直接は使わない。代わりに`price_derived_record_to_evidence()`
が`resolve_available_at()`(as_of Pathの既存の安全な規約)をこのモジュール
自身のEvidence構築に用いる。`lib/positioning/evidence.py`/`lib/positioning/
derived/price_derived.py`のいずれも変更しない — これはD0057自体の解決
(2経路のどちらを正とするかを決める設計変更)ではなく、新規Consumerとして
より安全な既存の選択肢を採用しただけである。

## Allowed Default Data(Stage 3 v1のScope境界)

`DEFAULT_ALLOWED_CAPABILITIES`に含まれないCapabilityのEvidenceが
`evidence_pool`に混入した場合、`build_research_artifact()`は既定で
`ValueError`にする(fail closed)。Macro/News/Consensus(EXPECTATIONS)/
non-price Positioningを既定で使わないという要件を、文書だけでなく構造的に
強制する。

## Capability Tagだけでは安全な構築元を区別できない(pit-auditor HIGH Finding対応)

`capability=DataCapability.POSITIONING`というTagだけでは、
`price_derived_record_to_evidence()`(このModule、安全)と`lib.positioning.
evidence.positioning_record_to_evidence()`(既存、D0057で確認された
retrieved_at基準のLeak Riskあり)のどちらで構築されたEvidenceかを
区別できない — `EvidenceRecord`/`SourceMetadata`のいずれにも構築元を示す
Fieldが無いため(Common Core Schemaへの新規Field追加はD0057自身が
明示的に見送った判断であり、このModuleでも行わない)。

したがって`build_research_artifact()`は、POSITIONING capabilityの
Evidenceについて追加で「`available_at`が`session_close_at(value_date)`と
厳密に一致するか」を検証する(`_uses_session_close_availability()`)。
これは新しいFieldを追加せず、`price_derived_record_to_evidence()`の
出力が持つ観測可能な性質(available_atがSession Close時刻そのもの)を
直接確認する検証であり、`positioning_record_to_evidence()`の出力
(available_at=retrieved_at、実際のFetch時刻でありSession Close時刻と
厳密に一致することは通常無い)を構造的にfail closedで拒否する。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from lib.errors import LookAheadBiasError
from lib.evidence.model import DataLayer, EvidenceRecord, EvidenceRelation, EvidenceType, filter_usable_at
from lib.evidence.packet import EvidencePacket, build_evidence_packet
from lib.evidence.retrieval import ResearchQuestion
from lib.market_calendar import session_close_at
from lib.positioning.derived.price_derived import resolve_available_at
from lib.positioning.model import PositioningRecord
from lib.schemas.base import RecordMeta
from lib.sources.catalog import DataCapability, PrimaryOrSecondary, SourceAuthorityClass, SourceMetadata

DEFAULT_ALLOWED_CAPABILITIES: frozenset[DataCapability] = frozenset(
    {DataCapability.FUNDAMENTAL, DataCapability.DISCLOSURE, DataCapability.POSITIONING}
)


class ConfidenceLevel(StrEnum):
    """Data/Evidence/Research Confidenceの3軸に共通して使う段階(要件v1-5)。

    `INSUFFICIENT`は「低い」ではなく「判定材料が無い」ことを表す
    (0点への暗黙変換ではない、`AvailabilityBasis.UNKNOWN`と同じ思想)。
    """

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INSUFFICIENT = "INSUFFICIENT"


class DataGapStatus(StrEnum):
    """MISSING/UNAVAILABLE/UNVERIFIED/UNKNOWNの分離(要件v1-6)。

    「Evidenceが無いこと」自体を1種類のUNKNOWNへ潰さない。理由が違えば
    今後の対応(再取得・別Source探索・単に待つ)も変わるため区別する。
    """

    MISSING = "MISSING"  # そもそも取得を試みていない/Sourceが存在しない
    UNAVAILABLE = "UNAVAILABLE"  # 存在するはずだがas_of時点でまだ利用可能でない(PIT除外)
    UNVERIFIED = "UNVERIFIED"  # 取得できたが独立した確認が取れていない
    UNKNOWN = "UNKNOWN"  # 状態自体が判定不能(推測しない)


class ResearchConclusion(StrEnum):
    """このArtifactのResearch Conclusion(要件v1-7、v1-8)。

    BUY/SELL/HOLD等の投資判断語は一切含めない(Research != Decision)。
    `INSUFFICIENT_EVIDENCE`は正式なConclusionであり、Evidence不足を
    無理にPositive/Negativeへ倒さない(RESEARCH_RULES.md 0.5節と同じ思想)。
    """

    SUPPORTED = "SUPPORTED"
    PARTIALLY_SUPPORTED = "PARTIALLY_SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    INCONCLUSIVE = "INCONCLUSIVE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(kw_only=True, frozen=True)
class DataGap:
    """1件の「取得できなかった/確認できなかった」Topic(要件v1-6)。

    **missing source != negative evidence(Safety要件)**: `DataGap`は
    Bear Case Evidenceではない。この型がBull/Base/Bear Caseとは別Fieldに
    保持されることで、Absenceが自動的にNegative扱いされることを構造的に
    防ぐ(`ResearchArtifact.data_gaps`参照)。
    """

    topic: str
    status: DataGapStatus
    note: str = ""


@dataclass(kw_only=True, frozen=True)
class NarrativeCase:
    """Bull/Base/Bearいずれか1つのCase(要件v1-3)。

    `supporting_evidence_ids`に無いEvidenceについてこのCaseがFACTを主張
    することは許可しない(Evidence捏造禁止、`ResearchArtifact.__post_init__`
    がEvidencePacketに存在しないIDを拒否する)。
    """

    summary: str
    supporting_evidence_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass(kw_only=True, frozen=True)
class ResearchArtifact(RecordMeta):
    """1企業 + as_of についてのPIT-safe Research Artifact(Stage 3 v1)。

    **Research != Decision**: BUY/SELL/target price/position sizingに
    相当するFieldはこのDataclassに存在しない(構造的禁止)。

    `artifact_id`は`(entity_code, as_of, artifact_version)`の組を一意に
    識別する(呼び出し側が発行、このモジュール自体はID採番Policyを持たない)。
    `supersedes_artifact_id`は同一Researchの改訂版であることを示す
    (`Hypothesis.revise()`/`SourceVersion.supersedes_version_id`と同じ
    Append-only Lineageパターン、既存を上書きしない、要件v1-1)。

    **既知の限界(pit-auditor MEDIUM Finding)**: `__post_init__`はBull/
    Base/Bearの参照整合性・0件Evidence時のAbstention整合性のみを検証し、
    `included_evidence_ids`に列挙されたIDが実際にas_of時点でPIT-safeで
    あったかまでは検証できない(`ResearchArtifact`自体はEvidenceの
    Timestampへアクセスしないため)。本番用途では必ず`build_research_
    artifact()`(Future Leakage・Capability・POSITIONING構築元検証を
    実施する)を経由して構築すること。直接構築(このDataclassを直接
    呼ぶこと)はTest/内部用途に限る(既存の`Hypothesis`/`SplitRunResult`
    等、他Schemaでも直接構築自体は禁止していない、同じ既存慣行)。
    """

    artifact_id: str
    entity_code: str
    as_of: datetime
    research_question_id: str
    evidence_packet_id: str
    bull_case: NarrativeCase
    base_case: NarrativeCase
    bear_case: NarrativeCase
    data_confidence: ConfidenceLevel
    evidence_confidence: ConfidenceLevel
    research_confidence: ConfidenceLevel
    conclusion: ResearchConclusion
    conclusion_rationale: str
    artifact_version: int = 1
    supersedes_artifact_id: str | None = None
    included_evidence_ids: tuple[str, ...] = field(default_factory=tuple)
    data_gaps: tuple[DataGap, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.as_of.tzinfo is None:
            raise ValueError("as_of はtz-awareである必要があります")
        if self.artifact_version < 1:
            raise ValueError("artifact_version は1以上である必要があります")

        referenced = set(self.bull_case.supporting_evidence_ids)
        referenced |= set(self.base_case.supporting_evidence_ids)
        referenced |= set(self.bear_case.supporting_evidence_ids)
        unknown_refs = referenced - set(self.included_evidence_ids)
        if unknown_refs:
            raise ValueError(
                f"artifact_id={self.artifact_id}: Bull/Base/BearがEvidencePacketに存在しない"
                f"evidence_idを参照しています(Evidence捏造防止): {sorted(unknown_refs)}"
            )

        if not self.included_evidence_ids and self.conclusion != ResearchConclusion.INSUFFICIENT_EVIDENCE:
            raise ValueError(
                f"artifact_id={self.artifact_id}: Evidenceが0件のためconclusionは"
                "INSUFFICIENT_EVIDENCEである必要があります(Evidenceなしでの結論を禁止する、要件v1-8)"
            )
        if (
            self.conclusion == ResearchConclusion.INSUFFICIENT_EVIDENCE
            and self.research_confidence != ConfidenceLevel.INSUFFICIENT
        ):
            raise ValueError(
                f"artifact_id={self.artifact_id}: conclusion=INSUFFICIENT_EVIDENCEの場合、"
                "research_confidenceもINSUFFICIENTである必要があります(矛盾した状態を禁止する)"
            )


def price_derived_record_to_evidence(
    record: PositioningRecord,
    *,
    layer: DataLayer,
    source_authority_class: SourceAuthorityClass,
    originating_source: str,
    delivery_provider: str,
) -> EvidenceRecord:
    """Price/Volume-derived `PositioningRecord`を、D0057で確認された安全な
    as_of Path規約(`resolve_available_at()`)でEvidence化する。

    `lib.positioning.evidence.positioning_record_to_evidence()`は
    `record.retrieved_at`のみをavailable_atとするため、Intraday取得
    (retrieved_atがSession Closeより早い)の場合にas_of Pathより早く
    「利用可能」と誤判定しうる(D0057 §5 Failure Example)。この関数は
    `positioning_record_to_evidence()`を使わず、代わりにas_of Pathと同じ
    `resolve_available_at()`(Session Close基準、`AvailabilityBasis.
    INFERRED`)をavailable_atとして採用する。`lib/positioning/evidence.py`/
    `lib/positioning/derived/price_derived.py`のいずれも変更しない
    (D0057自体は解決せず、この新規Consumerが安全側を選んだだけ)。

    **`AvailabilityBasis`は保持されない(pit-auditor LOW Finding)**:
    `resolve_available_at()`が返す`AvailabilityBasis.INFERRED`はこの
    Evidenceには保持されない(`SourceMetadata`にBasis相当のFieldが無い、
    `lib.positioning.evidence.positioning_record_to_evidence()`Docstring
    と同じ制約)。厳密なB系統PIT判定・Basis考慮が必要な場合は
    `lib.positioning.derived.price_derived.resolve_available_at()`または
    `lib.positioning.view.positioning_as_of()`を直接使うこと。
    """
    available_at, _basis = resolve_available_at(record)
    value_display = record.raw_value if record.raw_value is not None else record.value_availability.value
    period_display = (
        record.observation_start.isoformat()
        if record.observation_start == record.observation_end
        else f"{record.observation_start.isoformat()}〜{record.observation_end.isoformat()}"
    )
    content = f"{record.entity_code}: {record.metric_type}({period_display}, {record.frequency.value})={value_display}"
    source = SourceMetadata(
        source_id=record.record_id,
        source_type=record.source_id,
        provider_name=record.source_id,
        source_authority_class=source_authority_class,
        primary_or_secondary=PrimaryOrSecondary.PRIMARY,
        retrieved_at=record.retrieved_at,
        published_at=record.market_public_at,
        available_at=available_at,
        originating_source=originating_source,
        delivery_provider=delivery_provider,
        provenance_id=record.provenance_id,
    )
    return EvidenceRecord(
        evidence_id=f"EVID_{record.record_id}",
        evidence_type=EvidenceType.FACT,
        layer=layer,
        capability=DataCapability.POSITIONING,
        content=content,
        source=source,
        value_date=record.observation_end,
        related_codes=(record.entity_code,),
        provenance_id=record.provenance_id,
    )


def _uses_session_close_availability(evidence: EvidenceRecord) -> bool:
    """POSITIONING capability Evidenceのavailable_atが、実際に
    `resolve_available_at()`(Session Close基準)から導出されたものかを
    検証する(pit-auditor HIGH Finding対応)。

    `value_date`(=`observation_end`)から`session_close_at()`を再計算し、
    `available_at`と厳密に一致するかを確認する。`price_derived_record_to_
    evidence()`の出力は常にこの等式を満たす。`positioning_record_to_
    evidence()`の出力(`available_at=retrieved_at`)は、実際のFetch時刻が
    Session Closeの瞬間と厳密に一致しない限り満たさない。`value_date`が
    無いEvidenceは検証不能としてFalse(fail closed、推測しない)。
    """
    if evidence.value_date is None:
        return False
    return evidence.source.available_at == session_close_at(evidence.value_date)


def build_research_artifact(
    *,
    artifact_id: str,
    entity_code: str,
    question: ResearchQuestion,
    evidence_pool: Sequence[EvidenceRecord],
    relations: Mapping[str, EvidenceRelation],
    bull_case: NarrativeCase,
    base_case: NarrativeCase,
    bear_case: NarrativeCase,
    data_confidence: ConfidenceLevel,
    evidence_confidence: ConfidenceLevel,
    research_confidence: ConfidenceLevel,
    conclusion: ResearchConclusion,
    conclusion_rationale: str,
    data_gaps: Sequence[DataGap] = (),
    conflicting_evidence_ids: Sequence[str] = (),
    excluded_candidate_sources: Sequence[str] = (),
    missing_expected_sources: Sequence[str] = (),
    artifact_version: int = 1,
    supersedes_artifact_id: str | None = None,
    allowed_capabilities: frozenset[DataCapability] = DEFAULT_ALLOWED_CAPABILITIES,
) -> tuple[ResearchArtifact, EvidencePacket]:
    """PIT-safe Evidence PoolからResearchArtifactを組み立てる(Stage 3 v1 Entry Point)。

    **Future Evidence Leakage防止(Safety要件)**: `evidence_pool`は
    `filter_usable_at(evidence_pool, question.as_of)`でas_of時点で利用
    可能なものだけに絞ってから`EvidencePacket`を構築する。呼び出し側が
    誤ってas_of後のEvidenceを`relations`/Narrative Caseで参照していた
    場合は、Silent Dropせず`LookAheadBiasError`で即座に失敗させる
    (Defense-in-depth、D0057 Test Suiteと同じ設計思想)。

    **Allowed Default Data(Safety要件)**: `evidence_pool`に`allowed_
    capabilities`(既定`DEFAULT_ALLOWED_CAPABILITIES`= Fundamental/
    Disclosure/Positioningのみ)以外のCapabilityが含まれる場合、fail
    closedで`ValueError`にする。Macro/News/Consensus(EXPECTATIONS)を
    既定で使わないという要件を、文書だけでなく構造的に強制する。呼び出し側
    が明示的に別のCapability集合を許可したい場合のみ`allowed_capabilities`
    を指定する。

    **多数決・自動分類は行わない**: `relations`(EvidenceとHypothesis/
    Research Questionとの関係)は呼び出し側が明示的に1件ずつ判定した結果を
    渡す(`build_evidence_packet()`と同じ設計、新しいDiscovery/Expectations
    Engineはここでは作らない)。

    **POSITIONING Evidenceの構築元検証(pit-auditor HIGH Finding対応)**:
    `capability=DataCapability.POSITIONING`というTagだけでは、安全な
    `price_derived_record_to_evidence()`と、D0057で確認されたLeak Riskが
    ある既存`positioning_record_to_evidence()`のどちらで構築された
    Evidenceかを区別できない。したがってPOSITIONING capabilityの
    Evidenceは追加で`_uses_session_close_availability()`を満たす必要が
    あり、満たさない場合はfail closedで`ValueError`にする。

    **evidence_idの重複防止**: `evidence_pool`内で`evidence_id`が重複する
    場合、Future Leakage判定・Evidence捏造判定のいずれも別の
    `EvidenceRecord`を指してしまう可能性があるため、`ValueError`にする。
    """
    if question.as_of.tzinfo is None:
        raise ValueError("question.as_of はtz-awareである必要があります")

    pool_id_list = [e.evidence_id for e in evidence_pool]
    if len(pool_id_list) != len(set(pool_id_list)):
        duplicates = sorted({eid for eid in pool_id_list if pool_id_list.count(eid) > 1})
        raise ValueError(f"evidence_poolにevidence_idの重複があります(区別不能なため禁止): {duplicates}")

    disallowed = {e.capability for e in evidence_pool} - allowed_capabilities
    if disallowed:
        raise ValueError(
            "evidence_poolにStage 3 v1のDefault許可Capability外のEvidenceが含まれています"
            f"(fail closed): {sorted(c.value for c in disallowed)}。"
            "許可する場合は呼び出し側がallowed_capabilitiesを明示的に指定すること。"
        )

    unsafe_positioning = [
        e for e in evidence_pool if e.capability == DataCapability.POSITIONING and not _uses_session_close_availability(e)
    ]
    if unsafe_positioning:
        raise ValueError(
            "evidence_poolにPOSITIONING capabilityのEvidenceが含まれていますが、available_atが"
            "Session Close基準(price_derived_record_to_evidence()のresolve_available_at())と"
            "一致しません(fail closed、D0057 Finding)。lib.positioning.evidence."
            "positioning_record_to_evidence()(D0057で確認されたLeak Riskあり)ではなく、"
            "このModuleのprice_derived_record_to_evidence()でEvidenceを構築してください: "
            f"{sorted(e.evidence_id for e in unsafe_positioning)}"
        )

    usable_evidence = filter_usable_at(evidence_pool, question.as_of)
    usable_ids = {e.evidence_id for e in usable_evidence}
    pool_ids = {e.evidence_id for e in evidence_pool}

    referenced_ids = set(relations) | set(conflicting_evidence_ids)
    referenced_ids |= set(bull_case.supporting_evidence_ids)
    referenced_ids |= set(base_case.supporting_evidence_ids)
    referenced_ids |= set(bear_case.supporting_evidence_ids)
    # evidence_pool自体に存在するが、as_of時点でまだ利用可能でなかったIDのみを
    # Leakageとして扱う(そもそもevidence_pool自体に存在しないIDは
    # ResearchArtifact.__post_init__のEvidence捏造チェックが別途検知する)。
    truly_leaked = (referenced_ids - usable_ids) & pool_ids
    if truly_leaked:
        raise LookAheadBiasError(
            f"as_of({question.as_of.isoformat()})時点でまだ利用可能でないEvidenceが"
            f"参照されています(Future Leakage防止): {sorted(truly_leaked)}"
        )

    packet_id = f"PKT_{artifact_id}"
    packet = build_evidence_packet(
        packet_id=packet_id,
        research_question=question.text,
        as_of=question.as_of,
        evidence_pool=usable_evidence,
        relations=relations,
        conflicting_evidence_ids=conflicting_evidence_ids,
        excluded_candidate_sources=excluded_candidate_sources,
        missing_expected_sources=missing_expected_sources,
    )

    artifact = ResearchArtifact(
        artifact_id=artifact_id,
        entity_code=entity_code,
        as_of=question.as_of,
        research_question_id=question.question_id,
        artifact_version=artifact_version,
        supersedes_artifact_id=supersedes_artifact_id,
        evidence_packet_id=packet.packet_id,
        included_evidence_ids=packet.included_evidence_ids,
        bull_case=bull_case,
        base_case=base_case,
        bear_case=bear_case,
        data_gaps=tuple(data_gaps),
        data_confidence=data_confidence,
        evidence_confidence=evidence_confidence,
        research_confidence=research_confidence,
        conclusion=conclusion,
        conclusion_rationale=conclusion_rationale,
    )
    return artifact, packet


__all__ = [
    "DEFAULT_ALLOWED_CAPABILITIES",
    "ConfidenceLevel",
    "DataGap",
    "DataGapStatus",
    "NarrativeCase",
    "ResearchArtifact",
    "ResearchConclusion",
    "build_research_artifact",
    "price_derived_record_to_evidence",
]
