"""Global Market MetricからEvidenceを作る(Phase4E-1)。

「NASDAQ下落」という事実の記述から「日本IT株SELL」を導くような解釈は
一切生成しない。作れるのはFACTのみ(例:「NASDAQ Compositeの2026-08-18
(US Eastern)Sessionは12345.67として記録された」まで)。BUY/SELL/Bullish/
Bearish等の解釈語はここでは一切使わない(Phase4E-1要件§3/§29、`lib.
evidence.model`のDEFAULT PROCESS = ADVERSARIAL / CONCLUSION = NEUTRAL
UNTIL SUPPORTED原則)。

`lib.macro.evidence`/`lib.positioning.evidence`と同じD0049/D0050 PIT
Bugfix方針を踏襲する: `source.available_at`には常に`record.retrieved_at`
を使い、`market_public_at`へのFallbackは行わない。
"""

from __future__ import annotations

from lib.evidence.model import DataLayer, EvidenceRecord, EvidenceType
from lib.global_market.model import GlobalMarketRecord
from lib.sources.catalog import DataCapability, PrimaryOrSecondary, SourceAuthorityClass, SourceMetadata


def global_market_record_to_evidence(
    record: GlobalMarketRecord,
    *,
    source_authority_class: SourceAuthorityClass,
    originating_source: str,
    delivery_provider: str,
) -> EvidenceRecord:
    """観測された値そのものをFACTとして記述するのみ(解釈を加えない)。"""
    value_display = record.raw_value if record.raw_value is not None else record.value_availability.value
    content = (
        f"{record.series_id}: {record.metric_name}({record.session_date.isoformat()}, "
        f"{record.market_timezone}, {record.frequency.value})={value_display}"
    )
    # market_public_atへはFallbackしない(Fundamentals D0049/D0050・Positioning/Macroと同じ方針)。
    source = SourceMetadata(
        source_id=record.record_id,
        source_type=record.source_id,
        provider_name=record.source_id,
        source_authority_class=source_authority_class,
        primary_or_secondary=PrimaryOrSecondary.PRIMARY,
        retrieved_at=record.retrieved_at,
        published_at=record.market_public_at,
        available_at=record.retrieved_at,
        originating_source=originating_source,
        delivery_provider=delivery_provider,
        provenance_id=record.provenance_id,
    )
    return EvidenceRecord(
        evidence_id=f"EVID_{record.record_id}",
        evidence_type=EvidenceType.FACT,
        layer=DataLayer.NORMALIZED,
        capability=DataCapability.GLOBAL_MARKET,
        content=content,
        source=source,
        value_date=record.session_date,
        provenance_id=record.provenance_id,
    )
