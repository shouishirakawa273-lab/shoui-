"""`LatestReportedFyPerHistoricalContextRecord`をEvidence化する(Stage
3.15/3.15.1、D0089/D0090)。

`lib.valuation.evidence.latest_reported_fy_per_to_evidence()`(D0077)と同じ
原則: FACTのみを記述し、Interpretationを一切加えない。「Current PERが
Historical Sampleの中央値より低い」はFactだが「だから割安」はInterpretation
であり、この関数からは生成できない・生成すべきでもない(禁止語Chekは呼び出し側
Testで直接確認する)。

30件のHistorical PER Observationを30件のEvidenceとしてResearchArtifactへ
個別追加しない(要件v1 §21)。Historical Contextは常に1件のEvidenceとして
表現する——個々のHistorical/Current PER Observationとのlineageは
`verify_historical_context_provenance()`がProvenanceStore + EvidenceRegistry
経由で検証する(D0090: 単なるID集合の一致だけでなく、実際にEvidence Nodeが
Registryに存在し、期待するType/Layer/Capability/Entity/PITを満たすことまで
確認する)。
"""

from __future__ import annotations

from lib.evidence.model import DataLayer, EvidenceRecord, EvidenceType
from lib.registry.evidence_registry import EvidenceRegistry
from lib.registry.provenance import ProvenanceStore
from lib.sources.catalog import DataCapability, PrimaryOrSecondary, SourceAuthorityClass, SourceMetadata
from lib.valuation.model import (
    SOURCE_ID_LATEST_REPORTED_FY_PER_HISTORICAL_CONTEXT,
    LatestReportedFyPerHistoricalContextRecord,
)


def latest_reported_fy_per_historical_context_to_evidence(
    record: LatestReportedFyPerHistoricalContextRecord,
    *,
    source_authority_class: SourceAuthorityClass,
    originating_source: str,
    delivery_provider: str,
) -> EvidenceRecord:
    """`available_at`はRecordが既に保持する合成値(全Parent PER Recordの
    `available_at`最大値、`lib.valuation.historical_context_builder`が算出
    済み)をそのまま使う(要件v1 §20)。

    `SourceMetadata.published_at`は`None`にする(要件v1 §20): この合成
    Derived Fact自体はExternal Publication Eventを持たない(市場・企業が
    「このHistorical Contextを公表した」という事実は存在しない)ため、
    存在しないPublication Timestampを無理に作らない(`SourceMetadata.
    published_at`は`datetime | None`で既にNoneを許容するSchema、新しい
    Field追加は不要)。
    """
    content = (
        f"{record.entity_code}: {record.metric_type}(as_of={record.current_reference_as_of.isoformat()})。"
        f"Historical Sample: {record.historical_sample_start_as_of.isoformat()} .. "
        f"{record.historical_sample_end_as_of.isoformat()}"
        f"(anchor_frequency={record.anchor_frequency.value}、sample_count={record.sample_count}、"
        f"minimum_sample_count={record.minimum_sample_count})。"
        "Denominator Regimes: "
        + "; ".join(
            f"fiscal_period_end={r.fiscal_period_end.isoformat()}、eps={r.eps_value}、count={r.observation_count}"
            for r in record.denominator_regimes
        )
        + f"(distinct_denominator_regime_count={record.distinct_denominator_regime_count})。"
        f"historical_min={record.historical_min}、historical_median={record.historical_median}"
        f"(median_method={record.median_method})、historical_max={record.historical_max}。"
        f"current_reference_price_date={record.current_reference_price_date.isoformat()}、"
        f"current_per={record.current_per}。"
        f"current_percentile={record.current_percentile}"
        f"(percentile_method={record.percentile_method}、percentile_scale={record.percentile_scale})。"
        f"current_minus_historical_median={record.current_minus_historical_median}。"
        f"context_status={record.context_status.value}。"
        f"attempted_anchor_count={record.attempted_anchor_count}、"
        f"excluded_future_anchor_count={record.excluded_future_anchor_count}、"
        f"unavailable_denominator_count={record.unavailable_denominator_count}、"
        f"corporate_action_excluded_count={record.corporate_action_excluded_count}。"
    )
    source = SourceMetadata(
        source_id=(
            f"{SOURCE_ID_LATEST_REPORTED_FY_PER_HISTORICAL_CONTEXT}_{record.entity_code}_"
            f"{record.current_reference_as_of.date().isoformat()}"
        ),
        source_type=SOURCE_ID_LATEST_REPORTED_FY_PER_HISTORICAL_CONTEXT,
        provider_name=SOURCE_ID_LATEST_REPORTED_FY_PER_HISTORICAL_CONTEXT,
        source_authority_class=source_authority_class,
        primary_or_secondary=PrimaryOrSecondary.PRIMARY,
        retrieved_at=record.available_at,
        published_at=None,
        available_at=record.available_at,
        originating_source=originating_source,
        delivery_provider=delivery_provider,
    )
    return EvidenceRecord(
        evidence_id=(
            f"EVID_{SOURCE_ID_LATEST_REPORTED_FY_PER_HISTORICAL_CONTEXT}_{record.entity_code}_"
            f"{record.current_reference_as_of.date().isoformat()}"
        ),
        evidence_type=EvidenceType.FACT,
        layer=DataLayer.DERIVED,
        capability=DataCapability.VALUATION,
        content=content,
        source=source,
        value_date=record.current_reference_price_date,
        related_codes=(record.entity_code,),
    )


_PARENT_LINK_TO_TYPE = "valuation_evidence"


def verify_historical_context_provenance(
    record: LatestReportedFyPerHistoricalContextRecord,
    *,
    context_evidence_id: str,
    provenance_store: ProvenanceStore,
    evidence_registry: EvidenceRegistry,
) -> None:
    """Context Evidenceへ登録済みのProvenanceLinkが、Recordが保持する31件の
    Parent Observation ID(30 Historical + 1 Current)と過不足なく一致するかを
    検証する(要件v1 §17-19、Dangling/Missing/Duplicate Parent Guard)。

    `ProvenanceStore.parents_of()`(Stage 3.15、Multi-Parent Retrieval
    Hardening)を使う——`trace_to_origin()`は複数親Targetを1件へ潰すため
    使わない。Fake String Lineage(Recordが持つIDと無関係な文字列をLinkへ
    登録すること)・Missing Parent・Duplicate Parentをいずれも`ValueError`で
    fail closedにする。

    **Parent Node Existence検証(Stage 3.15.1、D0090)**: 従来はExpected ID
    集合とLink ID集合のSet Equalityのみを確認しており、それらのIDが実際に
    Evidence Nodeとして存在するかは検証していなかった(架空IDでもLinkさえ
    貼れば通ってしまう)。`evidence_registry`を必須Inputとし、31件全ての
    `from_id`について、対応する`EvidenceRecord`が実在し、かつ以下を満たす
    ことを検証する: `EvidenceType.FACT`・`DataLayer.DERIVED`・
    `DataCapability.VALUATION`・`entity_code`が`record.entity_code`と一致
    (`related_codes`に含まれる)・`available_at <= record.current_reference_
    as_of`。いずれか1件でも満たさなければ`ValueError`でfail closedにする。
    """
    expected_parent_ids = set(record.historical_observation_ids) | {record.current_per_observation_id}

    links = provenance_store.parents_of(_PARENT_LINK_TO_TYPE, context_evidence_id)
    registered_ids = [link.from_id for link in links]
    if len(set(registered_ids)) != len(registered_ids):
        duplicates = sorted({oid for oid in registered_ids if registered_ids.count(oid) > 1})
        raise ValueError(
            f"context_evidence_id={context_evidence_id}: ProvenanceLinkに重複したfrom_idがあります"
            f"(Duplicate Parent Guard): {duplicates}"
        )

    registered_set = set(registered_ids)
    missing = expected_parent_ids - registered_set
    unexpected = registered_set - expected_parent_ids
    if missing or unexpected:
        raise ValueError(
            f"context_evidence_id={context_evidence_id}: 登録済みParent LinkがRecordの"
            f"Observation IDと一致しません(fail closed、Fake/Dangling Lineage防止): "
            f"missing={sorted(missing)} unexpected={sorted(unexpected)}"
        )

    for parent_id in sorted(registered_set):
        parent_evidence = evidence_registry.get(parent_id)
        if parent_evidence is None:
            raise ValueError(
                f"context_evidence_id={context_evidence_id}: Parent evidence_id={parent_id}が"
                "EvidenceRegistryに存在しません(fail closed、架空/未登録IDへのLineageを許可しない)"
            )
        problems: list[str] = []
        if parent_evidence.evidence_type != EvidenceType.FACT:
            problems.append(f"evidence_type={parent_evidence.evidence_type.value}(FACTが必要)")
        if parent_evidence.layer != DataLayer.DERIVED:
            problems.append(f"layer={parent_evidence.layer.value}(DERIVEDが必要)")
        if parent_evidence.capability != DataCapability.VALUATION:
            problems.append(f"capability={parent_evidence.capability.value}(VALUATIONが必要)")
        if record.entity_code not in parent_evidence.related_codes:
            problems.append(f"related_codes={parent_evidence.related_codes}(entity_code={record.entity_code}を含まない)")
        if parent_evidence.source.available_at > record.current_reference_as_of:
            problems.append(
                f"available_at={parent_evidence.source.available_at.isoformat()}"
                f"(current_reference_as_of={record.current_reference_as_of.isoformat()}より後)"
            )
        if problems:
            raise ValueError(
                f"context_evidence_id={context_evidence_id}: Parent evidence_id={parent_id}が"
                f"Historical Context Parentとして不適格です(fail closed): {'; '.join(problems)}"
            )


__all__ = ["latest_reported_fy_per_historical_context_to_evidence", "verify_historical_context_provenance"]
