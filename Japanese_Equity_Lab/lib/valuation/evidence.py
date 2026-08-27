"""`LatestReportedFyPerRecord`をEvidence化する(D0077)。

Phase4A(Fundamentals)/Phase4C(Positioning)と同じ原則: FACTのみを記述し、
Interpretationを一切加えない。「7.29x」はFactだが「7.29xだから割安」は
Interpretationであり、この関数からは生成できない・生成すべきでもない
(禁止語チェックは呼び出し側Testで直接確認する)。
"""

from __future__ import annotations

from lib.evidence.model import DataLayer, EvidenceRecord, EvidenceType
from lib.sources.catalog import DataCapability, PrimaryOrSecondary, SourceAuthorityClass, SourceMetadata
from lib.valuation.model import SOURCE_ID, LatestReportedFyPerRecord


def latest_reported_fy_per_to_evidence(
    record: LatestReportedFyPerRecord,
    *,
    source_authority_class: SourceAuthorityClass,
    originating_source: str,
    delivery_provider: str,
) -> EvidenceRecord:
    """`available_at`は2入力(Price/Fundamentals)が両方利用可能になった、最も遅い
    時刻を採用する(要件v1-9): ``max(record.price_available_at, record.
    published_at)``。

    **この方式を採用した理由(要件v1-9で要求された確認、意味的衝突は無いと
    判断した)**: `price_available_at`(`session_close_at`基準)は、この
    LabのPrice PITでは既にA/B系統の区別なく単一の可用性境界として扱われて
    いる(D0072のPositioning Evidence前例、`price_derived_record_to_
    evidence()`も同じ`session_close_at`をそのまま`available_at`に使う)。
    一方`record.published_at`はFundamentals A系統
    (`AvailabilitySemantics.MARKET_PUBLIC_AT`)の市場公表時刻そのもの
    (`build_latest_reported_fy_per()`は`SourceVersion.published_at`のみを
    使い、B系統の`retrieved_at`は一切参照しない)。両者とも「一般に公開
    された時刻」という共通の意味を持つため、遅い方を取ることが「両方が
    実際にPublicになった時刻」として意味的に整合する。D0049(B系統の
    `available_at`Fallback禁止)には抵触しない——このEvidence自体が
    B系統を名乗っていないため。
    """
    available_at = max(record.price_available_at, record.published_at)
    content = (
        f"{record.entity_code}: {record.calculation_expression} = {record.multiple}"
        f"({record.metric_type}、{record.denominator_type}、"
        f"consolidation_scope={record.consolidation_scope}、"
        f"accounting_standard={record.accounting_standard or 'UNKNOWN'})"
    )
    source = SourceMetadata(
        source_id=f"{SOURCE_ID}_{record.entity_code}_{record.price_date.isoformat()}_{record.source_version_id}",
        source_type=SOURCE_ID,
        provider_name=SOURCE_ID,
        source_authority_class=source_authority_class,
        primary_or_secondary=PrimaryOrSecondary.PRIMARY,
        # このDerived Fact自体は独立したretrieved_at概念を持たない
        # (Price/EPSそれぞれのretrieved_atはRecordが保持しない、要件v1-6の
        # Field一覧参照)。下限としてavailable_atをそのまま使う。
        retrieved_at=available_at,
        published_at=record.published_at,
        available_at=available_at,
        originating_source=originating_source,
        delivery_provider=delivery_provider,
    )
    return EvidenceRecord(
        evidence_id=f"EVID_{SOURCE_ID}_{record.entity_code}_{record.price_date.isoformat()}",
        evidence_type=EvidenceType.FACT,
        layer=DataLayer.DERIVED,
        capability=DataCapability.VALUATION,
        content=content,
        source=source,
        value_date=record.price_date,
        related_codes=(record.entity_code,),
    )


__all__ = ["latest_reported_fy_per_to_evidence"]
