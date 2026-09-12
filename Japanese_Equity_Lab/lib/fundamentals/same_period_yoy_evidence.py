"""`SamePeriodYoYChangeRecord`をEvidence化する(Stage 3.12、D0086)。

Phase4A(Fundamentals)/D0077/D0084と同じ原則: FACTのみを記述し、
Interpretationを一切加えない。「-2.03%」はFactだが「-2.03%だから減益」は
Interpretationであり、この関数からは生成できない・生成すべきでもない
(禁止語チェックは呼び出し側Testで直接確認する)。

このDerived Factは純Fundamentals-to-Fundamentals(Price非依存)のため、
新しい`DataCapability`は追加しない——既存`DataCapability.FUNDAMENTAL`を
`DataLayer.DERIVED`として使う(Opaque Architecture Expansion禁止、要件
v1-13)。`source_type`は既存A系統Bridge(`lib.fundamentals.evidence.
MARKET_PUBLIC_AT_SOURCE_TYPE`)をそのまま再利用する——Current/Prior双方が
`AvailabilitySemantics.MARKET_PUBLIC_AT`で選定されたVersionのみを使う
Derived Factであるため、`build_research_artifact()`のA/B混在Guardが
このEvidenceも正しくA系統として扱えるようにする(D0080/D0081/D0083と
同じ理由)。
"""

from __future__ import annotations

from lib.evidence.model import DataLayer, EvidenceRecord, EvidenceType
from lib.fundamentals.evidence import MARKET_PUBLIC_AT_SOURCE_TYPE
from lib.fundamentals.same_period_yoy_model import SOURCE_ID, SamePeriodYoYChangeRecord
from lib.sources.catalog import DataCapability, PrimaryOrSecondary, SourceAuthorityClass, SourceMetadata


def same_period_yoy_change_to_evidence(
    record: SamePeriodYoYChangeRecord,
    *,
    source_authority_class: SourceAuthorityClass,
    originating_source: str,
    delivery_provider: str,
) -> EvidenceRecord:
    """`available_at`はCurrent/Prior双方が実際に市場公表済みになった、最も遅い
    時刻を採用する(D0077/D0084のPrice/Fundamental Dual-Sourceと同じ考え方:
    `max(record.current_published_at, record.prior_published_at)`)。通常は
    Currentのpublished_atがPriorより後になるはずだが、推測せず`max()`を使う
    (要件v1-15)。

    `value_date=record.current_period_end`(D0080 Cash Flow Evidence
    (`financial_quality_metric_to_evidence_market_public_at()`のCUMULATIVE
    Branch)と同じ既存Semanticsに揃える、要件v1-15)。
    """
    available_at = max(record.current_published_at, record.prior_published_at)
    content = (
        f"{record.entity_code}: {record.underlying_metric_type}, "
        f"current({record.current_period_type}, {record.current_period_start.isoformat()}.."
        f"{record.current_period_end.isoformat()})={record.current_value}, "
        f"prior({record.current_period_type}, {record.prior_period_start.isoformat()}.."
        f"{record.prior_period_end.isoformat()})={record.prior_value}, "
        f"{record.calculation_expression} = {record.change_ratio}"
        f"({record.metric_type}、consolidation_scope={record.consolidation_scope}、"
        f"accounting_standard={record.accounting_standard or 'UNKNOWN'}、"
        f"current_published_at={record.current_published_at.isoformat()}、"
        f"prior_published_at={record.prior_published_at.isoformat()})"
    )
    source = SourceMetadata(
        source_id=(
            f"{SOURCE_ID}_{record.entity_code}_{record.underlying_metric_type}_"
            f"{record.current_period_end.isoformat()}_{record.current_source_version_id}"
        ),
        source_type=MARKET_PUBLIC_AT_SOURCE_TYPE,
        provider_name=SOURCE_ID,
        source_authority_class=source_authority_class,
        primary_or_secondary=PrimaryOrSecondary.PRIMARY,
        # このDerived Fact自体は独立したretrieved_at概念を持たない(D0077/D0084と
        # 同じ理由、Current/Priorそれぞれのretrieved_atはRecordが保持しない)。
        retrieved_at=available_at,
        published_at=record.current_published_at,
        available_at=available_at,
        originating_source=originating_source,
        delivery_provider=delivery_provider,
    )
    return EvidenceRecord(
        evidence_id=(
            f"EVID_{SOURCE_ID}_{record.entity_code}_{record.underlying_metric_type}_{record.current_period_end.isoformat()}"
        ),
        evidence_type=EvidenceType.FACT,
        layer=DataLayer.DERIVED,
        capability=DataCapability.FUNDAMENTAL,
        content=content,
        source=source,
        value_date=record.current_period_end,
        related_codes=(record.entity_code,),
    )


__all__ = ["same_period_yoy_change_to_evidence"]
