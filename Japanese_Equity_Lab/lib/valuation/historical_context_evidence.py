"""`LatestReportedFyPerHistoricalContextRecord`をEvidence化する(Stage 3.15、D0089)。

`lib.valuation.evidence.latest_reported_fy_per_to_evidence()`(D0077)と同じ
原則: FACTのみを記述し、Interpretationを一切加えない。「Current PERが
Historical Sampleの中央値より低い」はFactだが「だから割安」はInterpretation
であり、この関数からは生成できない・生成すべきでもない(禁止語Chekは呼び出し側
Testで直接確認する)。

30件のHistorical PER Observationを30件のEvidenceとしてResearchArtifactへ
個別追加しない(要件v1 §21)。Historical Contextは常に1件のEvidenceとして
表現する——個々のHistorical/Current PER Observationとのlineageは
`verify_historical_context_provenance()`がProvenanceStore経由で検証する。
"""

from __future__ import annotations

from lib.evidence.model import DataLayer, EvidenceRecord, EvidenceType
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
) -> None:
    """Context Evidenceへ登録済みのProvenanceLinkが、Recordが保持する31件の
    Parent Observation ID(30 Historical + 1 Current)と過不足なく一致するかを
    検証する(要件v1 §17-19、Dangling/Missing/Duplicate Parent Guard)。

    `ProvenanceStore.parents_of()`(Stage 3.15、Multi-Parent Retrieval
    Hardening)を使う——`trace_to_origin()`は複数親Targetを1件へ潰すため
    使わない。Fake String Lineage(Recordが持つIDと無関係な文字列をLinkへ
    登録すること)・Missing Parent・Duplicate Parentをいずれも`ValueError`で
    fail closedにする。
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


__all__ = ["latest_reported_fy_per_historical_context_to_evidence", "verify_historical_context_provenance"]
